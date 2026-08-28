"""Build a stable daily article-quality review sample from permanent history."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import polars as pl

from pipelines.deduplicate import display_headline_from_url
from pipelines.publisher_titles import (
    fetch_publisher_titles,
    normalize_publisher_title,
    read_publisher_title,
)
from pipelines.publisher_title_overrides import load_publisher_title_overrides


REQUIRED_COLUMNS = {
    "article_id",
    "seen_at",
    "canonical_url",
    "source_domain",
    "location_name",
    "disaster_match_strength",
    "duplicate_group_id",
    "matched_disaster_themes",
    "url_topic_relevance",
    "publisher_title",
    "publisher_title_relevance",
    "quality_flags",
}
SAMPLE_VERSION = 2
DEFAULT_SAMPLE_SIZE = 24
DEFAULT_LOOKBACK_DAYS = 7
MAX_EXISTING_SAMPLE_BYTES = 512 * 1024
ARTICLE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
RESOLVED_LABELS = (
    "reported_flooding",
    "flood_risk_warning",
    "heavy_rain_only",
    "not_flood_related",
)
CLASS_MINIMUM = 4
SPLIT_MINIMUMS = {"training": 2, "validation": 1, "test": 1}
SELECTION_REASONS = {
    "underrepresented_class",
    "underrepresented_split",
    "new_article_date",
    "new_publisher_group",
    "inference_text_available",
    "needs_detailed_relabel",
    "balanced_fallback",
}
WARNING_PATTERN = re.compile(
    r"\b(?:warning|watch|advisory|risk|forecast|expected|possible|threat)\b",
    re.I,
)
FLOOD_IMPACT_PATTERN = re.compile(
    r"\b(?:"
    r"casualt(?:y|ies)|damage[ds]?|dead|death(?:s)?|died|displaced|"
    r"evacuat(?:e|ed|es|ing|ion)|injur(?:ed|ies)|killed|missing|"
    r"rescu(?:e|ed|es|ing|ers)|stranded|toll|trapped"
    r")\b",
    re.I,
)
RAIN_PATTERN = re.compile(
    r"\b(?:cyclone|downpour|gale|hurricane|monsoon|precipitation|rain|rainfall|storm|thunder|thunderstorm|typhoon|waterlogging)s?\b",
    re.I,
)
FLOOD_PATTERN = re.compile(
    r"\b(?:flood(?:s|ed|ing)?|inundation|flash[- ]flood(?:s|ed|ing)?)\b",
    re.I,
)
FIGURATIVE_FLOOD_PATTERN = re.compile(
    r"\b(?:"
    r"flood(?:ed|ing)?\s+(?:by|of|the\s+internet\s+with|with)"
    r"|(?:applications?|complaints?|content|memes?|messages?|slop|tributes?)\s+flood(?:ed|ing)?"
    r")\b",
    re.I,
)


def _load_latest_reviews(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    from pipelines.train_article_classifier import load_latest_native_reviews

    return {row["article_id"]: row for row in load_latest_native_reviews(path)}


def _review_priority(review: dict[str, Any] | None) -> tuple[int, str]:
    if review is None:
        return 1, "unseen"
    if int(review.get("decision_schema_version", 1)) != 2:
        return 0, "legacy"
    if review.get("decision") == "uncertain":
        return 2, "uncertain"
    return 3, "completed"


def _story_group(row: dict[str, Any]) -> str:
    value = row.get("duplicate_group_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return str(row.get("article_id") or "")


def _selection_story_keys(row: dict[str, Any]) -> set[str]:
    keys = {f"group:{_story_group(row)}"}
    url = str(row.get("canonical_url") or "")
    title = normalize_publisher_title(row.get("publisher_title"), url) or _headline_from_url(url)
    if title:
        words = re.findall(r"[\w]+", title.casefold(), flags=re.UNICODE)
        if len(words) >= 4:
            keys.add("headline:" + " ".join(words))
    return keys


def _sampling_lane(row: dict[str, Any]) -> str:
    url = str(row.get("canonical_url") or "")
    text = " ".join(
        filter(
            None,
            (
                normalize_publisher_title(row.get("publisher_title"), url),
                _headline_from_url(url),
            ),
        )
    )
    bucket = _review_bucket(row)
    if FIGURATIVE_FLOOD_PATTERN.search(text):
        return "not_flood_related"
    has_flood = bool(FLOOD_PATTERN.search(text))
    has_rain = bool(RAIN_PATTERN.search(text))
    if has_flood and FLOOD_IMPACT_PATTERN.search(text):
        return "reported_flooding"
    if WARNING_PATTERN.search(text) and has_flood:
        return "flood_risk_warning"
    if bucket == "high_match" and (
        has_flood
        or row.get("url_topic_relevance") == "supporting"
        or row.get("publisher_title_relevance") == "supporting"
    ):
        return "reported_flooding"
    if has_flood and bucket != "headline_conflict":
        return "reported_flooding"
    if bucket != "high_match" and has_rain:
        return "heavy_rain_only"
    return "reported_flooding" if bucket == "high_match" else "not_flood_related"


def _readiness_context(review_path: Path | None, archive_path: Path) -> dict[str, Any]:
    context: dict[str, Any] = {
        "class_counts": {label: 0 for label in RESOLVED_LABELS},
        "distinct_article_dates": 0,
        "publisher_groups": 0,
        "inference_text_coverage": 0.0,
        "split_class_counts": {},
        "status": "unavailable",
        "usable_rows": 0,
        "_article_dates": set(),
        "_publisher_groups": set(),
        "_validation_boundary": None,
        "_test_boundary": None,
    }
    if review_path is None or not review_path.is_file():
        return context
    try:
        from pipelines.train_article_classifier import (
            prepare_native_articles,
            split_articles,
        )

        prepared = prepare_native_articles(review_path, archive_path)
        counts = Counter(row.label for row in prepared.rows)
        context.update(
            class_counts={label: counts[label] for label in RESOLVED_LABELS},
            distinct_article_dates=len({row.seen_at.date() for row in prepared.rows}),
            publisher_groups=len({row.publisher_group for row in prepared.rows}),
            inference_text_coverage=round(
                len(prepared.rows) / prepared.resolved_v2_count, 6
            ) if prepared.resolved_v2_count else 0.0,
            status="computed",
            usable_rows=len(prepared.rows),
            _article_dates={row.seen_at.date() for row in prepared.rows},
            _publisher_groups={row.publisher_group for row in prepared.rows},
        )
        try:
            split = split_articles(prepared.rows)
        except ValueError:
            split = None
        if split is not None:
            context["split_class_counts"] = {
                name: {
                    label: Counter(row.label for row in getattr(split, name))[label]
                    for label in RESOLVED_LABELS
                }
                for name in SPLIT_MINIMUMS
            }
            context["_validation_boundary"] = datetime.fromisoformat(
                split.metadata["validation_boundary"]
            )
            context["_test_boundary"] = datetime.fromisoformat(
                split.metadata["test_boundary"]
            )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        pass
    return context


def _sampling_split(row: dict[str, Any], readiness: dict[str, Any]) -> str | None:
    seen_at = row.get("seen_at")
    validation = readiness.get("_validation_boundary")
    test = readiness.get("_test_boundary")
    if not isinstance(seen_at, datetime) or not isinstance(validation, datetime) or not isinstance(test, datetime):
        return None
    seen_at = seen_at.replace(tzinfo=UTC) if seen_at.tzinfo is None else seen_at.astimezone(UTC)
    validation = validation.replace(tzinfo=UTC) if validation.tzinfo is None else validation.astimezone(UTC)
    test = test.replace(tzinfo=UTC) if test.tzinfo is None else test.astimezone(UTC)
    if seen_at >= test:
        return "test"
    if seen_at >= validation:
        return "validation"
    return "training"


@dataclass
class QualitySampleStats:
    archive_articles: int
    eligible_articles: int
    sample_articles: int
    high_match_articles: int
    headline_conflict_articles: int
    ambiguous_match_articles: int
    sample_date: str


def _headline_from_url(value: str) -> str | None:
    return display_headline_from_url(value)


def _review_bucket(row: dict[str, Any]) -> str:
    if row.get("disaster_match_strength") == "high":
        return "high_match"
    if "mismatch" in {
        row.get("url_topic_relevance"),
        row.get("publisher_title_relevance"),
    }:
        return "headline_conflict"
    return "ambiguous_match"


def _review_reason(bucket: str) -> str:
    return {
        "high_match": "Explicit flood theme; allowed to contribute to alerts",
        "headline_conflict": "Headline conflicts with the flood tag; blocked from alerts",
        "ambiguous_match": "Ambiguous flood tag; retained for audit but blocked from alerts",
    }[bucket]


def _stable_rank(article_id: str, sample_date: date) -> str:
    value = f"{sample_date.isoformat()}|{article_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _safe_existing_url(value: Any) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        return None
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    expected_port = 443 if parsed.scheme == "https" else 80
    if port not in {None, expected_port}:
        return None
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return None
    return value


def _validated_existing_article(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    article_id = value.get("article_id")
    if not isinstance(article_id, str) or not ARTICLE_ID_PATTERN.fullmatch(article_id):
        return None
    seen_at = value.get("seen_at")
    if not isinstance(seen_at, str):
        return None
    try:
        parsed_seen_at = datetime.fromisoformat(seen_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_seen_at.tzinfo is None:
        return None
    title = value.get("title")
    title_source = value.get("title_source", "")
    source_domain = value.get("source_domain")
    location_name = value.get("location_name")
    match_strength = value.get("match_strength")
    review_bucket = value.get("review_bucket")
    themes = value.get("themes")
    quality_flags = value.get("quality_flags")
    selection_intent = value.get("selection_intent")
    if not isinstance(title, str) or not 1 <= len(title) <= 240:
        return None
    if title_source not in {
        "",
        "manual_override",
        "publisher_metadata",
        "url_path",
        "unavailable",
    }:
        return None
    if not isinstance(source_domain, str) or len(source_domain) > 255:
        return None
    if not isinstance(location_name, str) or len(location_name) > 255:
        return None
    if match_strength not in {"high", "weak"}:
        return None
    if review_bucket not in {
        "high_match",
        "headline_conflict",
        "ambiguous_match",
    }:
        return None
    if not isinstance(themes, list) or len(themes) > 6:
        return None
    if not isinstance(quality_flags, list) or len(quality_flags) > 8:
        return None
    if any(not isinstance(item, str) or len(item) > 120 for item in themes):
        return None
    if any(not isinstance(item, str) or len(item) > 120 for item in quality_flags):
        return None
    if selection_intent is not None:
        reasons = selection_intent.get("reasons") if isinstance(selection_intent, dict) else None
        if (
            not isinstance(selection_intent, dict)
            or "sampling_lane" in selection_intent
            or not isinstance(selection_intent.get("rank"), int)
            or isinstance(selection_intent.get("rank"), bool)
            or not 1 <= selection_intent["rank"] <= 40
            or not isinstance(reasons, list)
            or not 1 <= len(reasons) <= len(SELECTION_REASONS)
            or any(not isinstance(reason, str) or reason not in SELECTION_REASONS for reason in reasons)
            or len(set(reasons)) != len(reasons)
            or selection_intent.get("sampling_split") not in {None, *SPLIT_MINIMUMS}
        ):
            return None
    url = _safe_existing_url(value.get("url"))
    if not url:
        return None
    article = {
        "article_id": article_id,
        "seen_at": parsed_seen_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "title": title,
        "title_source": title_source,
        "url": url,
        "source_domain": source_domain,
        "location_name": location_name,
        "match_strength": match_strength,
        "review_bucket": review_bucket,
        "review_reason": _review_reason(review_bucket),
        "themes": themes,
        "quality_flags": quality_flags,
    }
    if selection_intent is not None:
        article["selection_intent"] = selection_intent
    return article


def _existing_sample_articles(
    path: Path,
    sample_date: date,
) -> list[dict[str, Any]] | None:
    """Return today's safe sample cards, or None when they must be rebuilt."""
    try:
        if path.stat().st_size > MAX_EXISTING_SAMPLE_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("version") not in {1, SAMPLE_VERSION}
        or payload.get("sample_date") != sample_date.isoformat()
    ):
        return None
    articles = payload.get("articles")
    if not isinstance(articles, list) or not 1 <= len(articles) <= 40:
        return None
    validated: list[dict[str, Any]] = []
    for article in articles:
        validated_article = _validated_existing_article(article)
        if validated_article is None:
            return None
        validated.append(validated_article)
    article_ids = [article["article_id"] for article in validated]
    if len(set(article_ids)) != len(article_ids):
        return None
    return validated


def _render_item(
    row: dict[str, Any],
    bucket: str,
    fetched_titles: dict[str, str] | None = None,
    title_overrides: dict[str, str] | None = None,
    selection_intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seen_at = row.get("seen_at")
    if isinstance(seen_at, datetime):
        rendered_seen_at = seen_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
    else:
        rendered_seen_at = ""
    canonical_url = str(row.get("canonical_url") or "")
    override_title = normalize_publisher_title(
        (title_overrides or {}).get(canonical_url),
        canonical_url,
    )
    title = override_title or normalize_publisher_title(
        row.get("publisher_title"),
        canonical_url,
    )
    if not title and fetched_titles:
        title = normalize_publisher_title(
            fetched_titles.get(canonical_url),
            canonical_url,
        )
    url_title = _headline_from_url(canonical_url) if not title else None
    if override_title:
        rendered_title = override_title
        title_source = "manual_override"
    elif title:
        rendered_title = title
        title_source = "publisher_metadata"
    elif url_title:
        rendered_title = url_title
        title_source = "url_path"
    else:
        rendered_title = "Title unavailable — open publisher story"
        title_source = "unavailable"
    article = {
        "article_id": str(row.get("article_id") or "")[:64],
        "seen_at": rendered_seen_at,
        "title": rendered_title[:240],
        "title_source": title_source,
        "url": canonical_url[:2048],
        "source_domain": str(row.get("source_domain") or "")[:255],
        "location_name": str(row.get("location_name") or "")[:255],
        "match_strength": str(row.get("disaster_match_strength") or "")[:16],
        "review_bucket": bucket,
        "review_reason": _review_reason(bucket),
        "themes": [
            str(value)[:120]
            for value in (row.get("matched_disaster_themes") or [])[:6]
        ],
        "quality_flags": [
            str(value)[:120] for value in (row.get("quality_flags") or [])[:8]
        ],
    }
    if selection_intent is not None:
        article["selection_intent"] = selection_intent
    return article


def build_quality_sample(
    archive_path: Path,
    output_path: Path,
    *,
    size: int = DEFAULT_SAMPLE_SIZE,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    sample_date: date | None = None,
    title_cache_path: Path | None = None,
    title_fetcher: Callable[[str], str | None] = read_publisher_title,
    title_overrides: dict[str, str] | None = None,
    existing_sample_path: Path | None = None,
    review_path: Path | None = None,
) -> QualitySampleStats:
    if size < 3:
        raise ValueError("quality sample size must be at least 3")
    if lookback_days < 1:
        raise ValueError("lookback days must be positive")
    current_date = sample_date or datetime.now(UTC).date()
    overrides = (
        load_publisher_title_overrides()
        if title_overrides is None
        else title_overrides
    )
    archive = pl.read_parquet(archive_path)
    missing = REQUIRED_COLUMNS.difference(archive.columns)
    if missing:
        raise ValueError(f"article archive is missing columns: {sorted(missing)}")

    all_eligible = archive.filter(
        pl.col("canonical_url").is_not_null()
        & (
            pl.col("canonical_url").str.starts_with("http://")
            | pl.col("canonical_url").str.starts_with("https://")
        )
        & pl.col("seen_at").is_not_null()
    )
    latest_reviews = _load_latest_reviews(review_path)
    completed_ids = {
        article_id
        for article_id, review in latest_reviews.items()
        if _review_priority(review)[1] == "completed"
    }
    eligible = all_eligible
    if eligible.height:
        latest_seen_at = eligible["seen_at"].max()
        if isinstance(latest_seen_at, datetime):
            cutoff = latest_seen_at - timedelta(days=lookback_days)
            recent = eligible.filter(pl.col("seen_at") >= cutoff)
            if recent.height >= size:
                eligible = recent
    review_candidates = eligible.filter(
        ~pl.col("article_id").is_in(sorted(completed_ids))
    )

    selected: list[tuple[dict[str, Any], str, str, list[str], str | None]] = []
    bucket_order = ("high_match", "headline_conflict", "ambiguous_match")
    target_size = min(size, review_candidates.height)
    stable_path = existing_sample_path or output_path
    existing_articles = _existing_sample_articles(
        stable_path,
        current_date,
    )
    if existing_articles:
        rows_by_id = {
            str(row.get("article_id") or ""): row
            for row in all_eligible.select(sorted(REQUIRED_COLUMNS)).iter_rows(
                named=True
            )
        }
        selected = [
            (
                rows_by_id[article["article_id"]],
                _review_bucket(rows_by_id[article["article_id"]]),
                _sampling_lane(rows_by_id[article["article_id"]]),
                (article.get("selection_intent") or {}).get("reasons")
                or ["balanced_fallback"],
                (article.get("selection_intent") or {}).get("sampling_split"),
            )
            for article in existing_articles
            if article["article_id"] in rows_by_id
            and article["article_id"] not in completed_ids
        ]

    if existing_articles is None:
        readiness = _readiness_context(review_path, archive_path)
        readiness_computed = readiness["status"] == "computed"
        class_counts = readiness["class_counts"]
        split_counts = readiness["split_class_counts"]
        gaps = {
            label: max(0, CLASS_MINIMUM - class_counts[label])
            + sum(
                max(0, SPLIT_MINIMUMS[name] - counts[label])
                for name, counts in split_counts.items()
            )
            for label in RESOLVED_LABELS
        }
        lanes: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for row in review_candidates.select(sorted(REQUIRED_COLUMNS)).iter_rows(named=True):
            bucket = _review_bucket(row)
            row["_rank"] = _stable_rank(
                str(row.get("article_id") or ""),
                current_date,
            )
            lane = _sampling_lane(row)
            row["_bucket"] = bucket
            row["_lane"] = lane
            row["_priority"], row["_review_state"] = _review_priority(
                latest_reviews.get(str(row["article_id"]))
            )
            row["_new_date"] = (
                readiness_computed
                and readiness["distinct_article_dates"] < 3
                and row["seen_at"].date() not in readiness["_article_dates"]
            )
            row["_new_publisher"] = (
                readiness_computed
                and readiness["publisher_groups"] < 12
                and str(row.get("source_domain") or "").casefold()
                not in readiness["_publisher_groups"]
            )
            row["_inference_text"] = bool(
                normalize_publisher_title(
                    row.get("publisher_title"), str(row.get("canonical_url") or "")
                )
                or _headline_from_url(str(row.get("canonical_url") or ""))
            )
            row["_sampling_split"] = _sampling_split(row, readiness)
            row["_split_gap"] = (
                max(
                    0,
                    SPLIT_MINIMUMS[row["_sampling_split"]]
                    - split_counts[row["_sampling_split"]][lane],
                )
                if row["_sampling_split"] in split_counts
                else 0
            )
            lanes[lane if readiness_computed else bucket].append(row)
        for lane, rows in list(lanes.items()):
            lanes[lane] = deque(
                sorted(
                    rows,
                    key=lambda row: (
                        row["_priority"],
                        -row["_split_gap"],
                        not row["_new_date"],
                        not row["_new_publisher"],
                        not row["_inference_text"],
                        row["_rank"],
                    ),
                )
            )
        lane_order = (
            sorted(RESOLVED_LABELS, key=lambda label: (-gaps[label], label))
            if readiness_computed
            else list(bucket_order)
        )
        selected_story_keys: set[str] = set()

        while len(selected) < target_size and any(lanes.values()):
            active_priority = min(rows[0]["_priority"] for rows in lanes.values() if rows)
            for queue_lane in lane_order:
                if (
                    lanes[queue_lane]
                    and lanes[queue_lane][0]["_priority"] == active_priority
                    and len(selected) < target_size
                ):
                    row = lanes[queue_lane].popleft()
                    sampling_lane = row["_lane"]
                    story_keys = _selection_story_keys(row)
                    if story_keys & selected_story_keys:
                        continue
                    reasons = [] if readiness_computed else ["balanced_fallback"]
                    if readiness_computed and gaps[sampling_lane] > 0:
                        reasons.append("underrepresented_class")
                    if row["_split_gap"] > 0:
                        reasons.append("underrepresented_split")
                    if row["_review_state"] in {"legacy", "uncertain"}:
                        reasons.append("needs_detailed_relabel")
                    if row["_new_date"]:
                        reasons.append("new_article_date")
                    if row["_new_publisher"]:
                        reasons.append("new_publisher_group")
                    if row["_inference_text"]:
                        reasons.append("inference_text_available")
                    selected.append(
                        (
                            row,
                            row["_bucket"],
                            sampling_lane,
                            reasons or ["balanced_fallback"],
                            row["_sampling_split"],
                        )
                    )
                    selected_story_keys.update(story_keys)
    else:
        readiness = _readiness_context(review_path, archive_path)
        if review_path is not None:
            retained_ids = {
                article["article_id"]
                for article in existing_articles
                if article["article_id"] not in completed_ids
            }
            retained_story_keys: set[str] = set()
            for row, *_ in selected:
                retained_story_keys.update(_selection_story_keys(row))
            vacancies = max(0, min(size, len(retained_ids) + review_candidates.height) - len(retained_ids))
            if vacancies:
                class_counts = readiness["class_counts"]
                split_counts = readiness["split_class_counts"]
                gaps = {
                    label: max(0, CLASS_MINIMUM - class_counts[label])
                    + sum(
                        max(0, SPLIT_MINIMUMS[name] - counts[label])
                        for name, counts in split_counts.items()
                    )
                    for label in RESOLVED_LABELS
                }
                extras: list[dict[str, Any]] = []
                for row in review_candidates.select(sorted(REQUIRED_COLUMNS)).iter_rows(named=True):
                    article_id = str(row.get("article_id") or "")
                    if article_id in retained_ids:
                        continue
                    row["_rank"] = _stable_rank(article_id, current_date)
                    row["_lane"] = _sampling_lane(row)
                    row["_priority"], row["_review_state"] = _review_priority(
                        latest_reviews.get(article_id)
                    )
                    row["_sampling_split"] = _sampling_split(row, readiness)
                    row["_split_gap"] = (
                        max(
                            0,
                            SPLIT_MINIMUMS[row["_sampling_split"]]
                            - split_counts[row["_sampling_split"]][row["_lane"]],
                        )
                        if row["_sampling_split"] in split_counts
                        else 0
                    )
                    extras.append(row)
                extras.sort(
                    key=lambda row: (
                        row["_priority"],
                        -row["_split_gap"],
                        -gaps[row["_lane"]],
                        row["_rank"],
                    )
                )
                added = 0
                for row in extras:
                    if added >= vacancies:
                        break
                    story_keys = _selection_story_keys(row)
                    if story_keys & retained_story_keys:
                        continue
                    reasons = ["underrepresented_class"] if gaps[row["_lane"]] else ["balanced_fallback"]
                    if row["_split_gap"] > 0:
                        reasons.append("underrepresented_split")
                    if row["_review_state"] in {"legacy", "uncertain"}:
                        reasons.append("needs_detailed_relabel")
                    selected.append(
                        (
                            row,
                            _review_bucket(row),
                            row["_lane"],
                            reasons,
                            row["_sampling_split"],
                        )
                    )
                    retained_story_keys.update(story_keys)
                    added += 1

    fetched_titles: dict[str, str] = {}
    if title_cache_path is not None:
        title_urls = [
            str(row.get("canonical_url") or "")
            for row, *_ in selected
            if not normalize_publisher_title(
                row.get("publisher_title"),
                str(row.get("canonical_url") or ""),
            )
            and str(row.get("canonical_url") or "") not in overrides
        ]
        fetched_titles = fetch_publisher_titles(
            title_urls,
            title_cache_path,
            fetcher=title_fetcher,
            max_fetches=size,
            max_workers=6,
        )
    rendered = {
        str(row.get("article_id") or ""): _render_item(
            row,
            bucket,
            fetched_titles,
            overrides,
            selection_intent={
                "rank": index,
                "reasons": reasons,
                **({"sampling_split": sampling_split} if sampling_split else {}),
            },
        )
        for index, (row, bucket, lane, reasons, sampling_split) in enumerate(selected, start=1)
    }
    if existing_articles:
        existing_ids = {article["article_id"] for article in existing_articles}
        articles = [
            rendered.get(article["article_id"], article)
            for article in existing_articles
            if article["article_id"] not in completed_ids
        ]
        articles.extend(
            rendered[str(row.get("article_id") or "")]
            for row, *_ in selected
            if str(row.get("article_id") or "") not in existing_ids
        )
    else:
        articles = [
            rendered[str(row.get("article_id") or "")]
            for row, *_ in selected
        ]
    for rank, article in enumerate(articles, start=1):
        intent = article.get("selection_intent")
        if isinstance(intent, dict):
            intent["rank"] = rank
    payload = {
        "version": SAMPLE_VERSION,
        "sample_date": current_date.isoformat(),
        "archive_articles": archive.height,
        "eligible_articles": eligible.height,
        "queue_candidate_articles": review_candidates.height,
        "selection_intent": {
            "strategy": "training_readiness_v1",
            "target": "cpu_smoke",
            "usable_rows": readiness["usable_rows"],
            "usable_rows_minimum": 16,
            "class_counts": readiness["class_counts"],
            "class_minimum": CLASS_MINIMUM,
            "distinct_article_dates": readiness["distinct_article_dates"],
            "article_date_minimum": 3,
            "publisher_groups": readiness["publisher_groups"],
            "publisher_group_minimum": 12,
            "inference_text_coverage": readiness["inference_text_coverage"],
            "inference_text_minimum": 1.0,
            "split_class_counts": readiness["split_class_counts"],
            "split_class_minimums": SPLIT_MINIMUMS,
            "readiness_status": readiness["status"],
            "production_minimums": {
                "total_usable_rows": 500,
                "class_minimum": 100,
                "article_dates": 30,
                "publisher_groups": 100,
                "inference_text_coverage": 0.95,
                "split_class_minimums": {
                    "training": 60,
                    "validation": 15,
                    "test": 20,
                },
            },
        },
        "articles": articles,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f"{output_path.name}.",
            suffix=".partial",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        json.loads(temporary_path.read_text(encoding="utf-8"))
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    counts = {bucket: 0 for bucket in bucket_order}
    for article in articles:
        counts[str(article["review_bucket"])] += 1
    return QualitySampleStats(
        archive_articles=archive.height,
        eligible_articles=eligible.height,
        sample_articles=len(articles),
        high_match_articles=counts["high_match"],
        headline_conflict_articles=counts["headline_conflict"],
        ambiguous_match_articles=counts["ambiguous_match"],
        sample_date=current_date.isoformat(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--existing-sample",
        type=Path,
        help="optional same-day sample to preserve while refreshing its evidence",
    )
    parser.add_argument("--reviews", type=Path)
    args = parser.parse_args()
    stats = build_quality_sample(
        args.archive,
        args.output,
        size=args.size,
        lookback_days=args.lookback_days,
        existing_sample_path=args.existing_sample,
        review_path=args.reviews,
    )
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
