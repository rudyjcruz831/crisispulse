"""Build a stable daily article-quality review sample from permanent history."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import tempfile
from collections import defaultdict, deque
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
    "matched_disaster_themes",
    "url_topic_relevance",
    "publisher_title",
    "publisher_title_relevance",
    "quality_flags",
}
SAMPLE_VERSION = 1
DEFAULT_SAMPLE_SIZE = 24
DEFAULT_LOOKBACK_DAYS = 7
MAX_EXISTING_SAMPLE_BYTES = 512 * 1024
ARTICLE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


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
    url = _safe_existing_url(value.get("url"))
    if not url:
        return None
    return {
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
        or payload.get("version") != SAMPLE_VERSION
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
    return {
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
    eligible = all_eligible
    if eligible.height:
        latest_seen_at = eligible["seen_at"].max()
        if isinstance(latest_seen_at, datetime):
            cutoff = latest_seen_at - timedelta(days=lookback_days)
            recent = eligible.filter(pl.col("seen_at") >= cutoff)
            if recent.height >= size:
                eligible = recent

    selected: list[tuple[dict[str, Any], str]] = []
    bucket_order = ("high_match", "headline_conflict", "ambiguous_match")
    target_size = min(size, eligible.height)
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
            )
            for article in existing_articles
            if article["article_id"] in rows_by_id
        ]

    if existing_articles is None:
        buckets: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for row in eligible.select(sorted(REQUIRED_COLUMNS)).iter_rows(named=True):
            bucket = _review_bucket(row)
            row["_rank"] = _stable_rank(
                str(row.get("article_id") or ""),
                current_date,
            )
            buckets[bucket].append(row)
        for bucket, rows in list(buckets.items()):
            buckets[bucket] = deque(sorted(rows, key=lambda row: row["_rank"]))

        while len(selected) < target_size and any(buckets.values()):
            for bucket in bucket_order:
                if buckets[bucket] and len(selected) < target_size:
                    selected.append((buckets[bucket].popleft(), bucket))

    fetched_titles: dict[str, str] = {}
    if title_cache_path is not None:
        title_urls = [
            str(row.get("canonical_url") or "")
            for row, _ in selected
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
        )
        for row, bucket in selected
    }
    if existing_articles:
        articles = [
            rendered.get(article["article_id"], article)
            for article in existing_articles
        ]
    else:
        articles = [
            rendered[str(row.get("article_id") or "")]
            for row, _ in selected
        ]
    payload = {
        "version": SAMPLE_VERSION,
        "sample_date": current_date.isoformat(),
        "archive_articles": archive.height,
        "eligible_articles": eligible.height,
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
    args = parser.parse_args()
    stats = build_quality_sample(
        args.archive,
        args.output,
        size=args.size,
        lookback_days=args.lookback_days,
        existing_sample_path=args.existing_sample,
    )
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
