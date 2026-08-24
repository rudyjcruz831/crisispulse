from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from pipelines.merge_article_archive import merge_article_archive


def _write_articles(
    path: Path,
    rows: list[tuple[str, datetime, str, str]],
) -> None:
    pl.DataFrame(
        {
            "article_id": [row[0] for row in rows],
            "seen_at": [row[1] for row in rows],
            "publisher_title": [row[2] for row in rows],
            "disaster_match_strength": [row[3] for row in rows],
        },
        schema={
            "article_id": pl.String,
            "seen_at": pl.Datetime(time_unit="us"),
            "publisher_title": pl.String,
            "disaster_match_strength": pl.String,
        },
    ).write_parquet(path)


def test_merge_creates_and_updates_verified_compressed_archive(tmp_path: Path) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    archive_path = tmp_path / "articles.parquet"
    _write_articles(
        first_path,
        [
            ("a", datetime(2026, 8, 20, 12), "Old title", "high"),
            ("b", datetime(2026, 8, 20, 13), "Second", "weak"),
        ],
    )
    _write_articles(
        second_path,
        [
            ("a", datetime(2026, 8, 20, 12), "Improved title", "high"),
            ("c", datetime(2026, 8, 20, 14), "Third", "high"),
        ],
    )

    first = merge_article_archive(first_path, archive_path)
    second = merge_article_archive(second_path, archive_path)
    archive = pl.read_parquet(archive_path).sort("article_id")

    assert first.existing_rows == 0
    assert first.new_rows == 2
    assert second.existing_rows == 2
    assert second.new_rows == 1
    assert second.updated_rows == 1
    assert second.archive_rows == 3
    assert second.high_confidence_rows == 2
    assert second.weak_confidence_rows == 1
    assert second.archive_bytes == archive_path.stat().st_size
    assert archive["article_id"].to_list() == ["a", "b", "c"]
    assert archive["publisher_title"].to_list() == [
        "Improved title",
        "Second",
        "Third",
    ]
    assert archive_path.read_bytes()[:4] == b"PAR1"
    assert not list(tmp_path.glob("*.partial"))


def test_empty_batch_preserves_existing_archive(tmp_path: Path) -> None:
    populated_path = tmp_path / "populated.parquet"
    empty_path = tmp_path / "empty.parquet"
    archive_path = tmp_path / "articles.parquet"
    _write_articles(
        populated_path,
        [("a", datetime(2026, 8, 20, 12), "Title", "high")],
    )
    _write_articles(empty_path, [])

    merge_article_archive(populated_path, archive_path)
    stats = merge_article_archive(empty_path, archive_path)

    assert stats.input_rows == 0
    assert stats.archive_rows == 1
    assert pl.read_parquet(archive_path)["article_id"].to_list() == ["a"]


def test_schema_mismatch_does_not_replace_archive(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.parquet"
    invalid_path = tmp_path / "invalid.parquet"
    archive_path = tmp_path / "articles.parquet"
    _write_articles(
        valid_path,
        [("a", datetime(2026, 8, 20, 12), "Title", "high")],
    )
    merge_article_archive(valid_path, archive_path)
    original = archive_path.read_bytes()
    pl.DataFrame({"article_id": ["b"], "different": [True]}).write_parquet(
        invalid_path
    )

    with pytest.raises(ValueError, match="schema"):
        merge_article_archive(invalid_path, archive_path)

    assert archive_path.read_bytes() == original


def test_overlapping_refresh_preserves_backfilled_title_and_guard(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    schema = {
        "article_id": pl.String,
        "canonical_url": pl.String,
        "disaster_match_strength": pl.String,
        "publisher_title": pl.String,
        "publisher_title_relevance": pl.String,
        "quality_flags": pl.List(pl.String),
    }
    pl.DataFrame(
        {
            "article_id": ["a"],
            "canonical_url": ["https://news.example/opaque/1"],
            "disaster_match_strength": ["weak"],
            "publisher_title": ["Funding applications open for technology companies"],
            "publisher_title_relevance": ["mismatch"],
            "quality_flags": [["publisher_title_topic_mismatch"]],
        },
        schema=schema,
    ).write_parquet(first_path)
    pl.DataFrame(
        {
            "article_id": ["a"],
            "canonical_url": ["https://news.example/opaque/1"],
            "disaster_match_strength": ["high"],
            "publisher_title": [None],
            "publisher_title_relevance": ["unknown"],
            "quality_flags": [[]],
        },
        schema=schema,
    ).write_parquet(second_path)

    merge_article_archive(first_path, archive_path)
    merge_article_archive(second_path, archive_path)
    row = pl.read_parquet(archive_path).row(0, named=True)

    assert row["publisher_title"] == "Funding applications open for technology companies"
    assert row["publisher_title_relevance"] == "mismatch"
    assert row["disaster_match_strength"] == "weak"
    assert "publisher_title_topic_mismatch" in row["quality_flags"]
