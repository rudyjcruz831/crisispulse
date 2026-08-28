"""Safely append verified publisher-title provenance to native article reviews."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import polars as pl

from pipelines.publisher_titles import (
    SUCCESS_TTL,
    TITLE_PARSER_VERSION,
    normalize_publisher_title,
)
from pipelines.train_article_classifier import load_latest_native_reviews


MAX_REVIEW_LOG_BYTES = 4 << 20
MAX_REVIEW_LINE_BYTES = 64 << 10
MAX_CACHE_BYTES = 4 << 20
REVIEW_LOCK_TIMEOUT_SECONDS = 5.0
REVIEW_LOCK_STALE_SECONDS = 60 * 60
REQUIRED_ARCHIVE_COLUMNS = {"article_id", "canonical_url", "source_domain"}


@dataclass(frozen=True)
class BackfillStats:
    latest_reviews: int
    eligible_corrections: int
    appended_corrections: int
    dry_run: bool


def _publisher_group(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().casefold().rstrip(".")
    if "://" in candidate:
        try:
            candidate = (urlsplit(candidate).hostname or "").casefold().rstrip(".")
        except ValueError:
            return None
    candidate = re.sub(r"^(?:www\d*|amp|m)\.", "", candidate)
    return candidate or None


def _cache_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _load_successful_cache(path: Path, current_time: datetime) -> dict[str, str]:
    if path.stat().st_size > MAX_CACHE_BYTES:
        raise ValueError("publisher title cache exceeds safety limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("publisher title cache is invalid") from error
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("version") != TITLE_PARSER_VERSION
        or not isinstance(entries, dict)
    ):
        raise ValueError("publisher title cache is invalid")
    successful: dict[str, str] = {}
    for url, entry in entries.items():
        if not isinstance(url, str) or not isinstance(entry, dict):
            continue
        if entry.get("status") != "ok":
            continue
        fetched_at = _cache_time(entry.get("fetched_at"))
        if (
            entry.get("parser_version") != TITLE_PARSER_VERSION
            or fetched_at is None
            or fetched_at > current_time
            or current_time - fetched_at > SUCCESS_TTL
        ):
            continue
        title = normalize_publisher_title(entry.get("title"), url)
        if title:
            successful[url] = title
    return successful


@contextmanager
def _review_lock(review_path: Path):
    lock_path = review_path.with_name(review_path.name + ".lock")
    deadline = time.monotonic() + REVIEW_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                lock_age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if lock_age > REVIEW_LOCK_STALE_SECONDS:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("article review log is busy")
            time.sleep(0.025)
            continue
        os.close(descriptor)
        break
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _archive_by_id(path: Path) -> dict[str, dict[str, Any]]:
    schema = pl.read_parquet_schema(path)
    missing = REQUIRED_ARCHIVE_COLUMNS.difference(schema)
    if missing:
        raise ValueError(f"article archive is missing columns: {sorted(missing)}")
    archive = pl.read_parquet(path, columns=sorted(REQUIRED_ARCHIVE_COLUMNS))
    if archive["article_id"].n_unique() != archive.height:
        raise ValueError("article archive must contain one row per article_id")
    return {
        str(row["article_id"]): row
        for row in archive.iter_rows(named=True)
    }


def _verified_corrections(
    reviews: list[dict[str, Any]],
    archive: dict[str, dict[str, Any]],
    cached_titles: dict[str, str],
    reviewed_at: str,
) -> list[dict[str, Any]]:
    corrections: list[dict[str, Any]] = []
    for review in reviews:
        if int(review.get("decision_schema_version", 1)) != 2:
            continue
        if review.get("title_source"):
            continue
        archived = archive.get(str(review["article_id"]))
        if archived is None:
            continue
        review_url = review.get("url")
        if not isinstance(review_url, str) or review_url != archived.get("canonical_url"):
            continue
        review_domain = _publisher_group(review.get("source_domain"))
        archive_domain = _publisher_group(archived.get("source_domain"))
        if not review_domain or not archive_domain or review_domain != archive_domain:
            continue
        cached_title = cached_titles.get(review_url)
        review_title = normalize_publisher_title(review.get("title"), review_url)
        if not cached_title or not review_title or cached_title != review_title:
            continue
        correction = dict(review)
        correction["title_source"] = "publisher_metadata"
        correction["reviewed_at"] = reviewed_at
        corrections.append(correction)
    return corrections


def backfill_review_title_sources(
    review_path: Path,
    archive_path: Path,
    title_cache_path: Path,
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> BackfillStats:
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    reviews = load_latest_native_reviews(review_path)
    archive = _archive_by_id(archive_path)
    cached_titles = _load_successful_cache(title_cache_path, current_time)
    timestamp = current_time.isoformat()
    corrections = _verified_corrections(reviews, archive, cached_titles, timestamp)
    if not apply or not corrections:
        return BackfillStats(len(reviews), len(corrections), 0, not apply)

    with _review_lock(review_path):
        reviews = load_latest_native_reviews(review_path)
        corrections = _verified_corrections(reviews, archive, cached_titles, timestamp)
        if not corrections:
            return BackfillStats(len(reviews), 0, 0, False)
        encoded_lines = [
            json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
            for record in corrections
        ]
        if any(len(line) > MAX_REVIEW_LINE_BYTES for line in encoded_lines):
            raise ValueError("generated review correction exceeds line safety limit")
        payload = b"".join(encoded_lines)
        descriptor = os.open(review_path, os.O_WRONLY | os.O_APPEND)
        try:
            current_size = os.fstat(descriptor).st_size
            if current_size > MAX_REVIEW_LOG_BYTES or current_size + len(payload) > MAX_REVIEW_LOG_BYTES:
                raise ValueError("article review log exceeds safety limit")
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise OSError("short append while writing review corrections")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return BackfillStats(len(reviews), len(corrections), len(corrections), False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--title-cache", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append verified corrections; omission performs a dry run",
    )
    args = parser.parse_args()
    stats = backfill_review_title_sources(
        args.reviews,
        args.archive,
        args.title_cache,
        apply=args.apply,
    )
    print(json.dumps(asdict(stats), indent=2))


if __name__ == "__main__":
    main()
