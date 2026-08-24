"""Gradually enrich the permanent article archive with publisher titles."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import polars as pl

from pipelines.clean_gkg import classify_disaster, publisher_title_relevance
from pipelines.publisher_titles import (
    fetch_publisher_titles,
    normalize_publisher_title,
    read_publisher_title,
)
from pipelines.publisher_title_overrides import load_publisher_title_overrides


STATE_VERSION = 1
DEFAULT_BATCH_SIZE = 12
REQUIRED_COLUMNS = {
    "article_id",
    "canonical_url",
    "disaster_type",
    "disaster_match_strength",
    "matched_disaster_themes",
    "publisher_title",
    "publisher_title_relevance",
    "quality_flags",
    "url_topic_relevance",
}


@dataclass
class ArticleTitleBackfillStats:
    archive_articles: int
    eligible_articles: int
    attempted_articles: int
    fetched_titles: int
    updated_articles: int
    invalidated_titles: int
    downgraded_articles: int
    promoted_articles: int
    remaining_without_titles: int
    cursor_article_id: str
    high_confidence_articles: int
    weak_confidence_articles: int
    archive_bytes: int


def _read_cursor(state_path: Path) -> str:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    if payload.get("version") != STATE_VERSION:
        return ""
    cursor = payload.get("cursor_article_id")
    return cursor if isinstance(cursor, str) else ""


def _write_state(state_path: Path, cursor: str, now: datetime) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=state_path.parent,
            prefix=f"{state_path.name}.",
            suffix=".partial",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                {
                    "version": STATE_VERSION,
                    "cursor_article_id": cursor,
                    "updated_at": now.astimezone(UTC).isoformat(),
                },
                temporary,
                indent=2,
            )
            temporary.write("\n")
        os.replace(temporary_path, state_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_verified_archive(archive: pl.DataFrame, archive_path: Path) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=archive_path.parent,
            prefix=f"{archive_path.name}.",
            suffix=".partial",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        archive.write_parquet(temporary_path, compression="zstd")
        verified = pl.read_parquet(temporary_path)
        if (
            verified.height != archive.height
            or verified.schema != archive.schema
            or not verified.equals(archive)
            or verified["article_id"].n_unique() != archive["article_id"].n_unique()
        ):
            raise RuntimeError("article title backfill verification failed")
        os.replace(temporary_path, archive_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _rotating_batch(
    candidates: list[dict[str, object]],
    cursor: str,
    batch_size: int,
) -> list[dict[str, object]]:
    ordered = sorted(candidates, key=lambda row: str(row["article_id"]))
    if not ordered:
        return []
    after_cursor = [row for row in ordered if str(row["article_id"]) > cursor]
    before_cursor = [row for row in ordered if str(row["article_id"]) <= cursor]
    return (after_cursor + before_cursor)[:batch_size]


def _base_match_strength(row: dict[str, object]) -> str:
    disaster_type = str(row.get("disaster_type") or "")
    themes = [str(value) for value in (row.get("matched_disaster_themes") or [])]
    strength, _ = classify_disaster(themes, disaster_type)
    if strength not in {"high", "weak"}:
        strength = str(row.get("disaster_match_strength") or "weak")
    if strength == "high" and row.get("url_topic_relevance") == "mismatch":
        return "weak"
    return strength


def backfill_article_titles(
    archive_path: Path,
    cache_path: Path,
    state_path: Path,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    fetcher: Callable[[str], str | None] = read_publisher_title,
    now: datetime | None = None,
    title_overrides: dict[str, str] | None = None,
) -> ArticleTitleBackfillStats:
    """Fetch one fair, bounded batch and atomically update the archive."""
    if batch_size < 1:
        raise ValueError("article title backfill batch size must be positive")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    overrides = (
        load_publisher_title_overrides()
        if title_overrides is None
        else title_overrides
    )
    archive = pl.read_parquet(archive_path)
    missing = REQUIRED_COLUMNS.difference(archive.columns)
    if missing:
        raise ValueError(f"article archive is missing columns: {sorted(missing)}")

    archive_rows = list(
        archive.select(sorted(REQUIRED_COLUMNS)).iter_rows(named=True)
    )
    candidates: list[dict[str, object]] = []
    for row in archive_rows:
        url = str(row.get("canonical_url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        if normalize_publisher_title(row.get("publisher_title"), url) is None:
            candidates.append(row)

    override_candidates = [
        row
        for row in archive_rows
        if str(row.get("canonical_url") or "") in overrides
        and normalize_publisher_title(
            row.get("publisher_title"),
            str(row.get("canonical_url") or ""),
        )
        != overrides[str(row.get("canonical_url") or "")]
    ]
    network_candidates = [
        row for row in candidates if str(row["canonical_url"]) not in overrides
    ]
    batch = _rotating_batch(
        network_candidates,
        _read_cursor(state_path),
        batch_size,
    )
    cursor = str(batch[-1]["article_id"]) if batch else ""
    urls = [str(row["canonical_url"]) for row in batch]
    titles = fetch_publisher_titles(
        urls,
        cache_path,
        fetcher=fetcher,
        now=current_time,
        max_fetches=batch_size,
        max_workers=3,
    )

    updates: dict[str, dict[str, object]] = {}
    invalidated = 0
    downgraded = 0
    promoted = 0
    for row in [*override_candidates, *batch]:
        article_id = str(row["article_id"])
        url = str(row["canonical_url"])
        raw_title = row.get("publisher_title")
        title = normalize_publisher_title(
            overrides.get(url) or titles.get(url),
            url,
        )
        existing_strength = str(row.get("disaster_match_strength") or "")
        base_strength = _base_match_strength(row)
        flags = [
            str(flag)
            for flag in (row.get("quality_flags") or [])
            if flag != "publisher_title_topic_mismatch"
        ]
        if title:
            disaster_type = str(row.get("disaster_type") or "")
            relevance = publisher_title_relevance(title, disaster_type)
            strength = base_strength
            if strength == "high" and relevance == "mismatch":
                strength = "weak"
                flags.append("publisher_title_topic_mismatch")
            if existing_strength == "high" and strength == "weak":
                downgraded += 1
            elif existing_strength == "weak" and strength == "high":
                promoted += 1
            updates[article_id] = {
                "publisher_title": title,
                "publisher_title_relevance": relevance,
                "disaster_match_strength": strength,
                "quality_flags": flags,
            }
        elif isinstance(raw_title, str) and raw_title.strip():
            if existing_strength == "weak" and base_strength == "high":
                promoted += 1
            updates[article_id] = {
                "publisher_title": None,
                "publisher_title_relevance": "unknown",
                "disaster_match_strength": base_strength,
                "quality_flags": flags,
            }
            invalidated += 1

    final_archive = archive
    if updates:
        rows = archive.to_dicts()
        for row in rows:
            update = updates.get(str(row.get("article_id") or ""))
            if update:
                row.update(update)
        updated_archive = pl.from_dicts(rows, schema=archive.schema, strict=False).select(
            archive.columns
        )
        _write_verified_archive(updated_archive, archive_path)
        final_archive = updated_archive

    if batch:
        _write_state(state_path, cursor, current_time)
    updated_with_titles = sum(
        1 for update in updates.values() if update.get("publisher_title")
    )
    resolved_missing_ids = {
        str(row["article_id"])
        for row in candidates
        if updates.get(str(row["article_id"]), {}).get("publisher_title")
    }
    return ArticleTitleBackfillStats(
        archive_articles=archive.height,
        eligible_articles=len(candidates),
        attempted_articles=len(batch),
        fetched_titles=len(titles),
        updated_articles=updated_with_titles,
        invalidated_titles=invalidated,
        downgraded_articles=downgraded,
        promoted_articles=promoted,
        remaining_without_titles=max(0, len(candidates) - len(resolved_missing_ids)),
        cursor_article_id=cursor,
        high_confidence_articles=final_archive.filter(
            pl.col("disaster_match_strength") == "high"
        ).height,
        weak_confidence_articles=final_archive.filter(
            pl.col("disaster_match_strength") == "weak"
        ).height,
        archive_bytes=archive_path.stat().st_size,
    )
