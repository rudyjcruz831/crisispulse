"""Audit, train, and evaluate the local four-class article baseline safely.

This runner accepts only the native CrisisPulse append-only article review log.
It joins the latest review for each article to the permanent article archive so
that model inputs and chronological/group split metadata come from collection
time rather than review time. External datasets require a separate, audited
importer and are deliberately outside this module's input contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

import numpy as np
import polars as pl
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import FeatureUnion

from pipelines.deduplicate import display_headline_from_url
from pipelines.publisher_titles import normalize_publisher_title


DATASET_CONTRACT = "crisispulse_native_article_reviews_v2"
REPORT_SCHEMA_VERSION = 2
ARTICLE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_REVIEW_LOG_BYTES = 4 << 20
MAX_REVIEW_LINE_BYTES = 64 << 10
MAX_GEOGRAPHY_LOCATIONS = 250
CLASS_LABELS = (
    "reported_flooding",
    "flood_risk_warning",
    "heavy_rain_only",
    "not_flood_related",
)
CLASS_SET = set(CLASS_LABELS)
V2_LABELS = CLASS_SET | {"uncertain"}
V1_LABELS = {"relevant", "not_relevant", "uncertain"}
ALLOWED_REVIEW_FIELDS = {
    "article_id",
    "title",
    "title_source",
    "url",
    "source_domain",
    "match_strength",
    "review_bucket",
    "decision",
    "decision_schema_version",
    "tags",
    "reviewed_at",
}
REQUIRED_REVIEW_FIELDS = ALLOWED_REVIEW_FIELDS - {
    "decision_schema_version",
    "tags",
    "title_source",
}
REQUIRED_ARCHIVE_COLUMNS = {
    "article_id",
    "seen_at",
    "canonical_url",
    "source_domain",
    "duplicate_group_id",
    "publisher_title",
}
PUBLISHER_TITLE_SOURCE_COLUMNS = (
    "publisher_title_source",
    "title_source",
)
PUBLISHER_METADATA_SOURCES = {"publisher_metadata"}
REVIEW_TITLE_SOURCES = {
    "",
    "manual_override",
    "publisher_metadata",
    "url_path",
    "unavailable",
}
OPTIONAL_GEOGRAPHY_COLUMNS = {
    "location_name",
    "country_code",
    "latitude",
    "longitude",
    "location_selection_status",
}
TRUSTED_LOCATION_SELECTION_STATUSES = {"single_region", "dominant_region"}

PRODUCTION_MINIMUMS = {
    "total_rows": 500,
    "rows_per_class": 100,
    "article_dates": 30,
    "publisher_groups": 100,
    "text_coverage": 0.95,
    "training_rows_per_class": 60,
    "validation_rows_per_class": 15,
    "test_rows_per_class": 20,
}
SMOKE_MINIMUMS = {
    "total_rows": 16,
    "rows_per_class": 4,
    "article_dates": 3,
    "publisher_groups": 12,
    "text_coverage": 1.0,
    "training_rows_per_class": 2,
    "validation_rows_per_class": 1,
    "test_rows_per_class": 1,
}


@dataclass(frozen=True)
class ArticleRow:
    article_id: str
    seen_at: datetime
    text: str
    text_source: str
    label: str
    publisher_group: str
    story_group: str
    language: str
    location_name: str = ""
    country_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    location_selection_status: str = "missing"


@dataclass
class PreparedArticles:
    rows: list[ArticleRow]
    latest_review_count: int
    latest_reviewed_at: str
    resolved_v2_count: int
    exclusion_counts: dict[str, int]
    label_counts_before_text_filter: dict[str, int]
    safeguards: dict[str, Any]


@dataclass
class SplitArticles:
    training: list[ArticleRow]
    validation: list[ArticleRow]
    test: list[ArticleRow]
    metadata: dict[str, Any]


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"article review {field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"article review {field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(f"article review {field} must include a timezone")
    return parsed.astimezone(UTC)


def _validate_review(record: Any, line_number: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError(f"article review line {line_number} must be a JSON object")
    unknown = set(record).difference(ALLOWED_REVIEW_FIELDS)
    missing = REQUIRED_REVIEW_FIELDS.difference(record)
    if unknown:
        raise ValueError(
            "article review input does not match the native CrisisPulse contract; "
            f"line {line_number} has unsupported fields: {sorted(unknown)}"
        )
    if missing:
        raise ValueError(
            f"article review line {line_number} is missing fields: {sorted(missing)}"
        )
    article_id = record.get("article_id")
    if not isinstance(article_id, str) or not ARTICLE_ID_PATTERN.fullmatch(article_id):
        raise ValueError(f"article review line {line_number} has an invalid article_id")
    schema_version = record.get("decision_schema_version", 1)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError(
            f"article review line {line_number} has an invalid decision_schema_version"
        )
    decision = record.get("decision")
    if not isinstance(decision, str):
        raise ValueError(f"article review line {line_number} has an invalid decision")
    if schema_version in {0, 1} and decision not in V1_LABELS:
        raise ValueError(f"article review line {line_number} has an invalid schema-v1 decision")
    if schema_version == 2 and decision not in V2_LABELS:
        raise ValueError(f"article review line {line_number} has an invalid schema-v2 decision")
    tags = record.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError(f"article review line {line_number} has invalid tags")
    if schema_version in {0, 1} and tags:
        raise ValueError(f"article review line {line_number} gives tags to a legacy decision")
    _parse_timestamp(record.get("reviewed_at"), field="reviewed_at")
    for key, limit in (
        ("title", 1024),
        ("url", 2048),
        ("source_domain", 255),
        ("match_strength", 32),
        ("review_bucket", 64),
    ):
        value = record.get(key)
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"article review line {line_number} has an invalid {key}")
    title_source = record.get("title_source", "")
    if not isinstance(title_source, str) or title_source not in REVIEW_TITLE_SOURCES:
        raise ValueError(
            f"article review line {line_number} has an invalid title_source"
        )
    normalized = dict(record)
    normalized["decision_schema_version"] = 1 if schema_version == 0 else schema_version
    normalized["tags"] = tags
    normalized["title_source"] = title_source
    return normalized


def load_latest_native_reviews(path: Path) -> list[dict[str, Any]]:
    """Load the latest native decision per article in append order.

    Unknown fields are rejected instead of being treated as compatible external
    data. Legacy and uncertain decisions remain loadable for the audit report but
    are never eligible for model fitting.
    """
    size = path.stat().st_size
    if size > MAX_REVIEW_LOG_BYTES:
        raise ValueError(
            f"article review log exceeds the {MAX_REVIEW_LOG_BYTES}-byte safety limit"
        )
    latest: dict[str, dict[str, Any]] = {}
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if len(raw_line) > MAX_REVIEW_LINE_BYTES:
                raise ValueError(f"article review line {line_number} exceeds the safety limit")
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"article review line {line_number} is invalid JSON") from error
            record = _validate_review(value, line_number)
            latest[record["article_id"]] = record
    return list(latest.values())


def _normalize_publisher_group(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().casefold().rstrip(".")
    if not candidate:
        return None
    if "://" in candidate:
        candidate = (urlsplit(candidate).hostname or "").casefold().rstrip(".")
    candidate = re.sub(r"^(?:www\d*|amp|m)\.", "", candidate)
    if not candidate or len(candidate) > 253:
        return None
    return candidate


def _archive_text(
    row: dict[str, Any],
    title_source_column: str | None,
    review: dict[str, Any] | None = None,
) -> tuple[str | None, str]:
    canonical_url = str(row.get("canonical_url") or "")
    if title_source_column and row.get(title_source_column) in PUBLISHER_METADATA_SOURCES:
        title = normalize_publisher_title(row.get("publisher_title"), canonical_url)
        if title:
            return title, "publisher_metadata"
    # A review display title is model input only when its provenance and archive
    # binding prove that the same publisher-metadata acquisition path produced it.
    # Manual overrides, unavailable titles, missing provenance, and stored URL-path
    # display text remain audit evidence only.
    if review and review.get("title_source") == "publisher_metadata":
        archive_publisher = _normalize_publisher_group(row.get("source_domain"))
        review_publisher = _normalize_publisher_group(review.get("source_domain"))
        if (
            review.get("url") == canonical_url
            and archive_publisher
            and review_publisher == archive_publisher
        ):
            title = normalize_publisher_title(review.get("title"), canonical_url)
            if title:
                return title, "review_publisher_metadata"
    # URL-path text is generated by the same deterministic code available at
    # live inference. Unproven archive publisher titles and manual overrides are
    # intentionally not used.
    url_title = display_headline_from_url(canonical_url)
    if url_title:
        return url_title, "url_path"
    return None, "unavailable"


def _archive_location(row: dict[str, Any]) -> tuple[str, str, float | None, float | None, str]:
    """Return a validated article-mentioned location without inventing precision."""
    location_name = row.get("location_name")
    if not isinstance(location_name, str):
        location_name = ""
    location_name = " ".join(location_name.strip().split())[:240]

    country_code = row.get("country_code")
    if not isinstance(country_code, str):
        country_code = ""
    country_code = country_code.strip().upper()[:8]

    selection_status = row.get("location_selection_status")
    if not isinstance(selection_status, str):
        selection_status = "missing"
    selection_status = selection_status.strip().casefold()

    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
        latitude = None
    if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
        longitude = None
    if latitude is not None:
        latitude = float(latitude)
    if longitude is not None:
        longitude = float(longitude)
    if (
        latitude is None
        or longitude is None
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        latitude = None
        longitude = None

    return location_name, country_code, latitude, longitude, selection_status


def prepare_native_articles(review_path: Path, archive_path: Path) -> PreparedArticles:
    reviews = load_latest_native_reviews(review_path)
    schema = pl.read_parquet_schema(archive_path)
    missing = REQUIRED_ARCHIVE_COLUMNS.difference(schema)
    if missing:
        raise ValueError(f"article archive is missing columns: {sorted(missing)}")
    title_source_column = next(
        (column for column in PUBLISHER_TITLE_SOURCE_COLUMNS if column in schema),
        None,
    )
    selected_columns = sorted(
        REQUIRED_ARCHIVE_COLUMNS
        | ({title_source_column} if title_source_column else set())
        | ({"language"} if "language" in schema else set())
        | OPTIONAL_GEOGRAPHY_COLUMNS.intersection(schema)
    )
    archive = pl.read_parquet(archive_path, columns=selected_columns)
    if archive["article_id"].n_unique() != archive.height:
        raise ValueError("article archive must contain one row per article_id")
    archive_by_id = {
        str(row["article_id"]): row for row in archive.iter_rows(named=True)
    }

    rows: list[ArticleRow] = []
    exclusions: Counter[str] = Counter()
    labels_before_text: Counter[str] = Counter()
    resolved_v2_count = 0
    for review in reviews:
        version = int(review["decision_schema_version"])
        decision = str(review["decision"])
        if version != 2:
            exclusions["legacy_schema"] += 1
            continue
        if decision == "uncertain":
            exclusions["uncertain"] += 1
            continue
        if decision not in CLASS_SET:
            exclusions["unsupported_schema_or_label"] += 1
            continue
        resolved_v2_count += 1
        labels_before_text[decision] += 1
        archived = archive_by_id.get(str(review["article_id"]))
        if archived is None:
            exclusions["missing_archive_row"] += 1
            continue
        seen_at = archived.get("seen_at")
        if not isinstance(seen_at, datetime):
            exclusions["missing_seen_at"] += 1
            continue
        if seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=UTC)
        else:
            seen_at = seen_at.astimezone(UTC)
        publisher_group = _normalize_publisher_group(archived.get("source_domain"))
        if not publisher_group:
            exclusions["missing_publisher_group"] += 1
            continue
        story_group = archived.get("duplicate_group_id")
        if not isinstance(story_group, str) or not story_group.strip():
            exclusions["missing_story_group"] += 1
            continue
        text, text_source = _archive_text(archived, title_source_column, review)
        if not text:
            exclusions["missing_inference_text"] += 1
            continue
        language = archived.get("language", "unknown")
        if not isinstance(language, str) or not language.strip():
            language = "unknown"
        location_name, country_code, latitude, longitude, selection_status = (
            _archive_location(archived)
        )
        rows.append(
            ArticleRow(
                article_id=str(review["article_id"]),
                seen_at=seen_at,
                text=text,
                text_source=text_source,
                label=decision,
                publisher_group=publisher_group,
                story_group=story_group.strip(),
                language=language.strip().casefold(),
                location_name=location_name,
                country_code=country_code,
                latitude=latitude,
                longitude=longitude,
                location_selection_status=selection_status,
            )
        )

    return PreparedArticles(
        rows=sorted(rows, key=lambda row: (row.seen_at, row.article_id)),
        latest_review_count=len(reviews),
        latest_reviewed_at=(
            max(
                _parse_timestamp(review["reviewed_at"], field="reviewed_at")
                for review in reviews
            ).isoformat()
            if reviews
            else ""
        ),
        resolved_v2_count=resolved_v2_count,
        exclusion_counts=dict(sorted(exclusions.items())),
        label_counts_before_text_filter={
            label: labels_before_text[label] for label in CLASS_LABELS
        },
        safeguards={
            "input_contract": DATASET_CONTRACT,
            "external_dataset_support": "not_accepted_requires_separate_audited_importer",
            "license_rule": "external data cannot enter this native-only runner",
            "latest_decision_only": True,
            "review_time_used_as_feature_or_split_key": False,
            "title_source_column": title_source_column,
            "unproven_publisher_titles_used": False,
            "review_publisher_titles_require_exact_archive_url_and_domain": True,
            "unproven_review_titles_used": False,
            "manual_override_titles_used": False,
            "url_path_fallback_uses_live_inference_code": True,
        },
    )


def _split_index(count: int, fraction: float) -> int:
    return min(count - 1, max(1, math.floor(count * fraction)))


def split_articles(rows: list[ArticleRow]) -> SplitArticles:
    """Create a chronological split, then purge story and final publishers."""
    timestamps = sorted({row.seen_at for row in rows})
    if len(timestamps) < 3:
        raise ValueError("at least three distinct collection timestamps are required")
    validation_index = _split_index(len(timestamps), 0.70)
    test_index = _split_index(len(timestamps), 0.85)
    if test_index <= validation_index:
        test_index = min(len(timestamps) - 1, validation_index + 1)
    if test_index <= validation_index:
        raise ValueError("chronological history is too short for three splits")
    validation_start = timestamps[validation_index]
    test_start = timestamps[test_index]

    initial: dict[str, int] = {}
    for row in rows:
        if row.seen_at >= test_start:
            initial[row.article_id] = 2
        elif row.seen_at >= validation_start:
            initial[row.article_id] = 1
        else:
            initial[row.article_id] = 0

    newest_story_split: dict[str, int] = defaultdict(int)
    for row in rows:
        newest_story_split[row.story_group] = max(
            newest_story_split[row.story_group], initial[row.article_id]
        )
    story_promotions = 0
    assigned: dict[str, int] = {}
    for row in rows:
        split = newest_story_split[row.story_group]
        assigned[row.article_id] = split
        if split > initial[row.article_id]:
            story_promotions += 1

    final_publishers = {
        row.publisher_group for row in rows if assigned[row.article_id] == 2
    }
    publisher_purged = {
        row.article_id
        for row in rows
        if assigned[row.article_id] < 2 and row.publisher_group in final_publishers
    }
    splits = ([], [], [])
    for row in rows:
        if row.article_id in publisher_purged:
            continue
        splits[assigned[row.article_id]].append(row)

    story_sets = [{row.story_group for row in split} for split in splits]
    publisher_sets = [{row.publisher_group for row in split} for split in splits]
    story_overlap = bool(
        (story_sets[0] & story_sets[1])
        or (story_sets[0] & story_sets[2])
        or (story_sets[1] & story_sets[2])
    )
    final_publisher_overlap = bool(
        publisher_sets[2] & (publisher_sets[0] | publisher_sets[1])
    )
    metadata = {
        "method": "chronological_70_15_15_then_story_promotion_and_final_publisher_purge",
        "time_field": "seen_at",
        "validation_boundary": validation_start.isoformat(),
        "test_boundary": test_start.isoformat(),
        "story_rows_promoted_to_newer_split": story_promotions,
        "earlier_rows_purged_for_final_publishers": len(publisher_purged),
        "story_overlap_after_purge": story_overlap,
        "final_publisher_overlap_after_purge": final_publisher_overlap,
        "training_rows": len(splits[0]),
        "validation_rows": len(splits[1]),
        "test_rows": len(splits[2]),
    }
    if story_overlap or final_publisher_overlap:
        raise RuntimeError("article split leakage guard failed")
    return SplitArticles(splits[0], splits[1], splits[2], metadata)


def _class_counts(rows: Iterable[ArticleRow]) -> dict[str, int]:
    counts = Counter(row.label for row in rows)
    return {label: counts[label] for label in CLASS_LABELS}


def _gate(name: str, actual: Any, minimum: Any, passed: bool) -> dict[str, Any]:
    return {"name": name, "actual": actual, "minimum": minimum, "passed": passed}


def _readiness(prepared: PreparedArticles, split: SplitArticles | None, minimums: dict[str, Any]) -> dict[str, Any]:
    rows = prepared.rows
    counts = _class_counts(rows)
    dates = {row.seen_at.date() for row in rows}
    publishers = {row.publisher_group for row in rows}
    text_coverage = (
        len(rows) / prepared.resolved_v2_count if prepared.resolved_v2_count else 0.0
    )
    gates = [
        _gate("total_usable_rows", len(rows), minimums["total_rows"], len(rows) >= minimums["total_rows"]),
        _gate(
            "minimum_rows_in_each_class",
            min(counts.values(), default=0),
            minimums["rows_per_class"],
            all(count >= minimums["rows_per_class"] for count in counts.values()),
        ),
        _gate("distinct_article_dates", len(dates), minimums["article_dates"], len(dates) >= minimums["article_dates"]),
        _gate("publisher_groups", len(publishers), minimums["publisher_groups"], len(publishers) >= minimums["publisher_groups"]),
        _gate("inference_text_coverage", round(text_coverage, 6), minimums["text_coverage"], text_coverage >= minimums["text_coverage"]),
    ]
    split_counts: dict[str, dict[str, int]] = {}
    if split is None:
        gates.append(_gate("leakage_safe_split_computable", False, True, False))
    else:
        split_counts = {
            "training": _class_counts(split.training),
            "validation": _class_counts(split.validation),
            "test": _class_counts(split.test),
        }
        gates.extend(
            [
                _gate(
                    "training_rows_in_each_class_after_purge",
                    min(split_counts["training"].values(), default=0),
                    minimums["training_rows_per_class"],
                    all(value >= minimums["training_rows_per_class"] for value in split_counts["training"].values()),
                ),
                _gate(
                    "validation_rows_in_each_class_after_purge",
                    min(split_counts["validation"].values(), default=0),
                    minimums["validation_rows_per_class"],
                    all(value >= minimums["validation_rows_per_class"] for value in split_counts["validation"].values()),
                ),
                _gate(
                    "test_rows_in_each_class_after_purge",
                    min(split_counts["test"].values(), default=0),
                    minimums["test_rows_per_class"],
                    all(value >= minimums["test_rows_per_class"] for value in split_counts["test"].values()),
                ),
            ]
        )
    return {
        "ready": all(gate["passed"] for gate in gates),
        "gates": gates,
        "usable_class_counts": counts,
        "split_class_counts": split_counts,
    }


def _dataset_fingerprint(rows: Iterable[ArticleRow]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item.article_id):
        value = {
            **asdict(row),
            "seen_at": row.seen_at.isoformat(),
        }
        digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _geography_summary(rows: Iterable[ArticleRow]) -> dict[str, Any]:
    """Aggregate safe map points for the training report.

    Coordinates describe the primary place mentioned by the GDELT article row;
    they are not verified physical flood events. Ambiguous and invalid locations
    are counted but never plotted.
    """
    materialized = list(rows)
    grouped: dict[tuple[str, str, float, float], Counter[str]] = {}
    for row in materialized:
        if (
            row.location_selection_status not in TRUSTED_LOCATION_SELECTION_STATUSES
            or not row.location_name
            or row.latitude is None
            or row.longitude is None
        ):
            continue
        key = (
            row.location_name,
            row.country_code,
            round(row.latitude, 5),
            round(row.longitude, 5),
        )
        grouped.setdefault(key, Counter())[row.label] += 1

    locations = [
        {
            "location_name": location_name,
            "country_code": country_code,
            "latitude": latitude,
            "longitude": longitude,
            "article_count": sum(class_counts.values()),
            "class_counts": {
                label: class_counts[label] for label in CLASS_LABELS
            },
        }
        for (location_name, country_code, latitude, longitude), class_counts in grouped.items()
    ]
    locations.sort(
        key=lambda location: (
            -location["article_count"],
            location["location_name"].casefold(),
            location["latitude"],
            location["longitude"],
        )
    )
    mappable_rows = sum(location["article_count"] for location in locations)
    returned_locations = locations[:MAX_GEOGRAPHY_LOCATIONS]
    return {
        "meaning": "article_mentioned_locations_not_verified_events",
        "source": "gdelt_primary_location_from_permanent_article_archive",
        "usable_rows": len(materialized),
        "mappable_rows": mappable_rows,
        "unmappable_rows": len(materialized) - mappable_rows,
        "unique_locations": len(locations),
        "locations_returned": len(returned_locations),
        "truncated": len(locations) > len(returned_locations),
        "locations": returned_locations,
    }


def _metrics(labels: list[str], predictions: list[str]) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        labels,
        predictions,
        labels=list(CLASS_LABELS),
        zero_division=0,
    )
    return {
        "accuracy": round(float(accuracy_score(labels, predictions)), 6),
        "macro_f1": round(float(f1_score(labels, predictions, labels=list(CLASS_LABELS), average="macro", zero_division=0)), 6),
        "per_class": {
            label: {
                "precision": round(float(precision[index]), 6),
                "recall": round(float(recall[index]), 6),
                "f1": round(float(f1[index]), 6),
                "support": int(support[index]),
            }
            for index, label in enumerate(CLASS_LABELS)
        },
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=list(CLASS_LABELS)
        ).tolist(),
        "confusion_matrix_label_order": list(CLASS_LABELS),
    }


def _slice_metrics(
    rows: list[ArticleRow],
    labels: list[str],
    predictions: list[str],
    attribute: str,
) -> dict[str, Any]:
    indexes: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indexes[str(getattr(row, attribute))].append(index)
    return {
        value: {
            "rows": len(group_indexes),
            "metrics": _metrics(
                [labels[index] for index in group_indexes],
                [predictions[index] for index in group_indexes],
            ),
        }
        for value, group_indexes in sorted(indexes.items())
    }


def _rule_prediction(text: str) -> str:
    candidate = text.casefold()
    reported_specific = (
        r"\bflood(?:ed|ing|s)\b",
        r"\binundat(?:ed|ion)",
        r"\bunder water\b",
        r"\bwater rescues?\b",
        r"\boverflow(?:ed|ing|s)?\b",
    )
    warning = (
        r"\bflood (?:watch|warning|risk|alert|advisory)\b",
        r"\brisk of flood(?:ing|s)?\b",
        r"\b(?:may|could|expected to) flood\b",
    )
    rain = (
        r"\bheavy rain(?:fall)?\b",
        r"\btorrential rain\b",
        r"\bsevere weather\b",
        r"\brainfall\b",
        r"\bstorms?\b",
    )
    if any(re.search(pattern, candidate) for pattern in reported_specific):
        return "reported_flooding"
    if any(re.search(pattern, candidate) for pattern in warning):
        return "flood_risk_warning"
    if re.search(r"\bflood\b", candidate):
        return "reported_flooding"
    if any(re.search(pattern, candidate) for pattern in rain):
        return "heavy_rain_only"
    return "not_flood_related"


def _build_vectorizer(*, smoke_test: bool) -> FeatureUnion:
    minimum_document_frequency = 1 if smoke_test else 2
    return FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    min_df=minimum_document_frequency,
                    max_features=50_000,
                    strip_accents="unicode",
                    sublinear_tf=True,
                ),
            ),
            (
                "character",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=minimum_document_frequency,
                    max_features=50_000,
                    sublinear_tf=True,
                ),
            ),
        ]
    )


def _evaluate_model(
    split: SplitArticles,
    *,
    smoke_test: bool,
    abstention_threshold: float,
) -> tuple[dict[str, Any], pl.DataFrame]:
    train_text = [row.text for row in split.training]
    validation_text = [row.text for row in split.validation]
    test_text = [row.text for row in split.test]
    train_labels = [row.label for row in split.training]
    validation_labels = [row.label for row in split.validation]
    test_labels = [row.label for row in split.test]

    vectorizer = _build_vectorizer(smoke_test=smoke_test)
    train_matrix = vectorizer.fit_transform(train_text)
    validation_matrix = vectorizer.transform(validation_text)
    test_matrix = vectorizer.transform(test_text)
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=2_000,
        random_state=42,
        solver="lbfgs",
    )
    model.fit(train_matrix, train_labels)
    validation_predictions = model.predict(validation_matrix).tolist()
    test_predictions = model.predict(test_matrix).tolist()
    test_probabilities = model.predict_proba(test_matrix)
    probability_index = {label: index for index, label in enumerate(model.classes_)}
    maximum_probabilities = np.max(test_probabilities, axis=1)
    abstained = maximum_probabilities < abstention_threshold
    covered_indexes = np.flatnonzero(~abstained)
    covered_metrics: dict[str, Any] | None = None
    if covered_indexes.size:
        covered_metrics = _metrics(
            [test_labels[index] for index in covered_indexes],
            [test_predictions[index] for index in covered_indexes],
        )

    dummy = DummyClassifier(strategy="prior")
    dummy.fit(train_matrix, train_labels)
    dummy_predictions = dummy.predict(test_matrix).tolist()
    rule_predictions = [_rule_prediction(text) for text in test_text]
    metrics = {
        "model": {
            "type": "word_and_character_tfidf_class_balanced_logistic_regression",
            "validation": _metrics(validation_labels, validation_predictions),
            "test": _metrics(test_labels, test_predictions),
        },
        "comparators": {
            "dummy_prior_test": _metrics(test_labels, dummy_predictions),
            "frozen_keyword_rules_test": _metrics(test_labels, rule_predictions),
        },
        "test_slices": {
            "text_source": _slice_metrics(
                split.test,
                test_labels,
                test_predictions,
                "text_source",
            ),
            "language": _slice_metrics(
                split.test,
                test_labels,
                test_predictions,
                "language",
            ),
            "publisher_group": _slice_metrics(
                split.test,
                test_labels,
                test_predictions,
                "publisher_group",
            ),
        },
        "abstention": {
            "threshold": abstention_threshold,
            "abstained_rows": int(abstained.sum()),
            "covered_rows": int((~abstained).sum()),
            "coverage": round(float((~abstained).mean()), 6),
            "covered_test_metrics": covered_metrics,
            "threshold_was_tuned_on_test": False,
        },
        "feature_dimensions": int(train_matrix.shape[1]),
    }

    prediction_rows: list[dict[str, Any]] = []
    for index, row in enumerate(split.test):
        rendered: dict[str, Any] = {
            "article_id": row.article_id,
            "seen_at": row.seen_at.isoformat(),
            "text": row.text,
            "text_source": row.text_source,
            "publisher_group": row.publisher_group,
            "story_group": row.story_group,
            "language": row.language,
            "actual_label": row.label,
            "predicted_label": test_predictions[index],
            "maximum_probability": float(maximum_probabilities[index]),
            "abstained": bool(abstained[index]),
        }
        for label in CLASS_LABELS:
            rendered[f"probability_{label}"] = float(
                test_probabilities[index, probability_index[label]]
            )
        prediction_rows.append(rendered)
    return metrics, pl.from_dicts(prediction_rows)


def build_readiness_report(
    review_path: Path,
    archive_path: Path,
    *,
    smoke_test: bool = False,
) -> tuple[dict[str, Any], PreparedArticles, SplitArticles | None]:
    prepared = prepare_native_articles(review_path, archive_path)
    split: SplitArticles | None = None
    split_error: str | None = None
    try:
        split = split_articles(prepared.rows)
    except ValueError as error:
        split_error = str(error)
    production = _readiness(prepared, split, PRODUCTION_MINIMUMS)
    smoke = _readiness(prepared, split, SMOKE_MINIMUMS)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "dataset_contract": DATASET_CONTRACT,
        "dataset_fingerprint": _dataset_fingerprint(prepared.rows),
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "reviews": str(review_path),
            "archive": str(archive_path),
        },
        "status": (
            "ready_for_cpu_baseline"
            if production["ready"]
            else "ready_for_non_evaluative_smoke_test"
            if smoke_test and smoke["ready"]
            else "not_ready"
        ),
        "training_performed": False,
        "latest_review_count": prepared.latest_review_count,
        "latest_reviewed_at": prepared.latest_reviewed_at,
        "resolved_schema_v2_count": prepared.resolved_v2_count,
        "usable_training_rows": len(prepared.rows),
        "geography_summary": _geography_summary(prepared.rows),
        "label_counts_before_text_filter": prepared.label_counts_before_text_filter,
        "exclusion_counts": prepared.exclusion_counts,
        "safeguards": prepared.safeguards,
        "split": split.metadata if split else {"computable": False, "reason": split_error},
        "production_readiness": production,
        "smoke_test_readiness": smoke,
        "interpretation": {
            "pretraining": "This is a CPU classification baseline, not model pretraining from scratch.",
            "production_claim": "No readiness or offline result makes the model production-ready.",
            "balanced_queue_prevalence": "Human review-queue class balance is not real-world prevalence.",
            "smoke_test": "A smoke test only proves that the pipeline runs; its scores are non-evaluative.",
        },
    }
    return report, prepared, split


def run_article_baseline(
    review_path: Path,
    archive_path: Path,
    report_path: Path,
    *,
    train: bool = False,
    smoke_test: bool = False,
    predictions_path: Path | None = None,
    abstention_threshold: float = 0.55,
) -> dict[str, Any]:
    if not 0.0 < abstention_threshold < 1.0:
        raise ValueError("abstention threshold must be between zero and one")
    if smoke_test and not train:
        raise ValueError("--smoke-test is valid only with --train")
    if train and predictions_path is None:
        raise ValueError("training requires --predictions-output to retain raw predictions")

    report, _prepared, split = build_readiness_report(
        review_path,
        archive_path,
        smoke_test=smoke_test,
    )
    if train:
        readiness_key = "smoke_test_readiness" if smoke_test else "production_readiness"
        if not report[readiness_key]["ready"] or split is None:
            report["status"] = (
                "blocked_non_evaluative_smoke_test"
                if smoke_test
                else "blocked_cpu_baseline"
            )
            report["blocked_reason"] = (
                f"one or more {readiness_key.replace('_', ' ')} gates failed"
            )
        else:
            metrics, predictions = _evaluate_model(
                split,
                smoke_test=smoke_test,
                abstention_threshold=abstention_threshold,
            )
            assert predictions_path is not None
            predictions_path.parent.mkdir(parents=True, exist_ok=True)
            predictions.write_parquet(predictions_path, compression="zstd")
            report.update(
                {
                    "status": (
                        "non_evaluative_smoke_test_completed"
                        if smoke_test
                        else "offline_cpu_baseline_completed"
                    ),
                    "training_performed": True,
                    "evaluation_tier": (
                        "NON_EVALUATIVE_SMOKE_TEST"
                        if smoke_test
                        else "PRELIMINARY_OFFLINE_BASELINE"
                    ),
                    "metrics": metrics,
                    "raw_predictions": str(predictions_path),
                    "runtime": {
                        "scikit_learn_version": sklearn.__version__,
                        "random_seed": 42,
                        "execution_device": "CPU",
                    },
                }
            )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--train",
        action="store_true",
        help="Fit/evaluate only after every production readiness gate passes.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="With --train, permit the smaller gates and label all scores non-evaluative.",
    )
    parser.add_argument("--predictions-output", type=Path)
    parser.add_argument("--abstention-threshold", type=float, default=0.55)
    args = parser.parse_args()
    report = run_article_baseline(
        args.reviews,
        args.archive,
        args.report,
        train=args.train,
        smoke_test=args.smoke_test,
        predictions_path=args.predictions_output,
        abstention_threshold=args.abstention_threshold,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.train and not report["training_performed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
