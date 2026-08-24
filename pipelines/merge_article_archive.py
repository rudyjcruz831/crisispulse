"""Merge cleaned flood articles into a permanent, compressed archive."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

from pipelines.publisher_titles import normalize_publisher_title


KEY_COLUMN = "article_id"
TITLE_ENRICHMENT_COLUMNS = {
    "article_id",
    "canonical_url",
    "disaster_match_strength",
    "publisher_title",
    "publisher_title_relevance",
    "quality_flags",
}


@dataclass
class ArticleArchiveStats:
    existing_rows: int
    input_rows: int
    new_rows: int
    updated_rows: int
    archive_rows: int
    high_confidence_rows: int
    weak_confidence_rows: int
    archive_bytes: int


def _preserve_title_enrichment(
    existing: pl.DataFrame,
    current: pl.DataFrame,
) -> pl.DataFrame:
    """Carry permanent titles into overlapping rows and recompute their guard."""
    if not TITLE_ENRICHMENT_COLUMNS.issubset(existing.columns) or not TITLE_ENRICHMENT_COLUMNS.issubset(current.columns):
        return current
    existing_by_id = {
        str(row["article_id"]): row
        for row in existing.select(sorted(TITLE_ENRICHMENT_COLUMNS)).iter_rows(
            named=True
        )
    }
    rows = current.to_dicts()
    changed = False
    for row in rows:
        article_id = str(row.get("article_id") or "")
        previous = existing_by_id.get(article_id)
        if previous is None:
            continue
        url = str(row.get("canonical_url") or "")
        if normalize_publisher_title(row.get("publisher_title"), url):
            continue
        previous_title = normalize_publisher_title(
            previous.get("publisher_title"),
            url,
        )
        if not previous_title:
            continue
        relevance = str(previous.get("publisher_title_relevance") or "unknown")
        if relevance not in {"supporting", "mismatch", "unknown"}:
            relevance = "unknown"
        flags = [
            str(flag)
            for flag in (row.get("quality_flags") or [])
            if flag != "publisher_title_topic_mismatch"
        ]
        strength = str(row.get("disaster_match_strength") or "")
        if strength == "high" and relevance == "mismatch":
            strength = "weak"
            flags.append("publisher_title_topic_mismatch")
        row["publisher_title"] = previous_title
        row["publisher_title_relevance"] = relevance
        row["disaster_match_strength"] = strength
        row["quality_flags"] = flags
        changed = True
    if not changed:
        return current
    return pl.from_dicts(rows, schema=current.schema, strict=False).select(current.columns)


def merge_article_archive(
    input_path: Path,
    archive_path: Path,
) -> ArticleArchiveStats:
    """Upsert one cleaned batch and verify it before replacing the archive.

    A current row replaces an older row with the same stable article ID. This
    lets later title and quality checks improve an existing archived article.
    The archive is written to a temporary zstd Parquet file, read back, and
    verified before the previous archive is replaced.
    """
    current = pl.read_parquet(input_path)
    if KEY_COLUMN not in current.columns:
        raise ValueError(f"article dataset is missing column: {KEY_COLUMN}")

    if archive_path.exists():
        existing = pl.read_parquet(archive_path)
        if set(existing.columns) != set(current.columns):
            raise ValueError("existing article archive schema does not match the batch")
        existing = existing.select(current.columns)
    else:
        existing = pl.DataFrame(schema=current.schema)

    current_unique = current.unique(
        subset=[KEY_COLUMN],
        keep="last",
        maintain_order=True,
    )
    current_unique = _preserve_title_enrichment(existing, current_unique)
    current_ids = current_unique.select(KEY_COLUMN)
    existing_ids = existing.select(KEY_COLUMN).unique()
    updated_rows = current_ids.join(existing_ids, on=KEY_COLUMN, how="inner").height
    new_rows = current_ids.join(existing_ids, on=KEY_COLUMN, how="anti").height

    retained = existing.join(current_ids, on=KEY_COLUMN, how="anti")
    archive = pl.concat([retained, current_unique], how="vertical_relaxed").unique(
        subset=[KEY_COLUMN],
        keep="last",
    )
    sort_columns = [
        column for column in ("seen_at", KEY_COLUMN) if column in archive.columns
    ]
    if sort_columns:
        archive = archive.sort(sort_columns, nulls_last=True)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
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

        verified_ids = pl.read_parquet(temporary_path, columns=[KEY_COLUMN]).unique()
        missing_ids = current_ids.join(verified_ids, on=KEY_COLUMN, how="anti")
        if missing_ids.height:
            raise RuntimeError(
                f"article archive verification failed for {missing_ids.height} rows"
            )

        os.replace(temporary_path, archive_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    strength_column = "disaster_match_strength"
    if strength_column in archive.columns:
        high_rows = archive.filter(pl.col(strength_column) == "high").height
        weak_rows = archive.filter(pl.col(strength_column) == "weak").height
    else:
        high_rows = 0
        weak_rows = 0

    return ArticleArchiveStats(
        existing_rows=existing.height,
        input_rows=current.height,
        new_rows=new_rows,
        updated_rows=updated_rows,
        archive_rows=archive.height,
        high_confidence_rows=high_rows,
        weak_confidence_rows=weak_rows,
        archive_bytes=archive_path.stat().st_size,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    stats = merge_article_archive(args.input, args.archive)
    print(json.dumps({**asdict(stats), "archive": str(args.archive)}, indent=2))


if __name__ == "__main__":
    main()
