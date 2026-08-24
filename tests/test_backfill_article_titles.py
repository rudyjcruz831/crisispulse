from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from pipelines import backfill_article_titles as backfill_module
from pipelines.backfill_article_titles import backfill_article_titles


def _write_archive(path: Path, count: int = 3) -> None:
    pl.DataFrame(
        {
            "article_id": [f"{index:064x}" for index in range(count)],
            "canonical_url": [f"https://news.example/item/{index}" for index in range(count)],
            "disaster_type": ["flood"] * count,
            "disaster_match_strength": ["high"] * count,
            "matched_disaster_themes": [["NATURAL_DISASTER_FLOODING"] for _ in range(count)],
            "publisher_title": [None] * count,
            "publisher_title_relevance": ["unknown"] * count,
            "quality_flags": [[] for _ in range(count)],
            "url_topic_relevance": ["unknown"] * count,
        },
        schema={
            "article_id": pl.String,
            "canonical_url": pl.String,
            "disaster_type": pl.String,
            "disaster_match_strength": pl.String,
            "matched_disaster_themes": pl.List(pl.String),
            "publisher_title": pl.String,
            "publisher_title_relevance": pl.String,
            "quality_flags": pl.List(pl.String),
            "url_topic_relevance": pl.String,
        },
    ).write_parquet(path)


def test_backfill_updates_titles_and_conservatively_downgrades_mismatch(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    _write_archive(archive_path, count=2)

    def fetcher(url: str) -> str:
        return (
            "Flooding forces residents to evacuate their homes"
            if url.endswith("/0")
            else "Funding applications open for technology companies"
        )

    stats = backfill_article_titles(
        archive_path,
        tmp_path / "cache.json",
        tmp_path / "state.json",
        batch_size=2,
        fetcher=fetcher,
        now=datetime(2026, 8, 24, 14, tzinfo=UTC),
    )
    archive = pl.read_parquet(archive_path).sort("article_id")

    assert stats.attempted_articles == 2
    assert stats.updated_articles == 2
    assert stats.downgraded_articles == 1
    assert archive["publisher_title_relevance"].to_list() == ["supporting", "mismatch"]
    assert archive["disaster_match_strength"].to_list() == ["high", "weak"]
    assert "publisher_title_topic_mismatch" in archive["quality_flags"][1]
    assert not list(tmp_path.glob("*.partial"))


def test_backfill_cursor_moves_past_recent_misses_without_starvation(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    cache_path = tmp_path / "cache.json"
    state_path = tmp_path / "state.json"
    _write_archive(archive_path)
    calls: list[str] = []

    def miss(url: str) -> None:
        calls.append(url)
        return None

    start = datetime(2026, 8, 24, 14, tzinfo=UTC)
    first = backfill_article_titles(
        archive_path,
        cache_path,
        state_path,
        batch_size=1,
        fetcher=miss,
        now=start,
    )
    second = backfill_article_titles(
        archive_path,
        cache_path,
        state_path,
        batch_size=1,
        fetcher=miss,
        now=start + timedelta(minutes=15),
    )

    assert first.cursor_article_id != second.cursor_article_id
    assert calls == ["https://news.example/item/0", "https://news.example/item/1"]
    assert second.remaining_without_titles == 3


def test_backfill_applies_audited_override_without_bypassing_batch_limit(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    _write_archive(archive_path)
    override_url = "https://news.example/item/2"
    calls: list[str] = []

    def miss(url: str) -> None:
        calls.append(url)
        return None

    stats = backfill_article_titles(
        archive_path,
        tmp_path / "cache.json",
        tmp_path / "state.json",
        batch_size=1,
        fetcher=miss,
        now=datetime(2026, 8, 24, 14, tzinfo=UTC),
        title_overrides={
            override_url: "Supply and Delivery of a Mini Hydraulic Excavator"
        },
    )
    archive = pl.read_parquet(archive_path).sort("article_id")

    assert calls == ["https://news.example/item/0"]
    assert stats.attempted_articles == 1
    assert stats.updated_articles == 1
    assert stats.remaining_without_titles == 2
    assert archive["publisher_title"][2] == (
        "Supply and Delivery of a Mini Hydraulic Excavator"
    )
    assert archive["publisher_title_relevance"][2] == "mismatch"
    assert archive["disaster_match_strength"][2] == "weak"


def test_backfill_removes_stale_title_mismatch_without_overriding_base_guards(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    _write_archive(archive_path)
    archive = pl.read_parquet(archive_path).with_columns(
        pl.lit("weak").alias("disaster_match_strength"),
        pl.lit("Title of the Page").alias("publisher_title"),
        pl.lit("mismatch").alias("publisher_title_relevance"),
        pl.lit(["publisher_title_topic_mismatch"]).alias("quality_flags"),
        pl.when(pl.col("article_id") == f"{2:064x}")
        .then(pl.lit(["NATURAL_DISASTER_FLOODED"]))
        .otherwise(pl.col("matched_disaster_themes"))
        .alias("matched_disaster_themes"),
        pl.when(pl.col("article_id") == f"{1:064x}")
        .then(pl.lit("mismatch"))
        .otherwise(pl.col("url_topic_relevance"))
        .alias("url_topic_relevance"),
    )
    archive.write_parquet(archive_path)

    stats = backfill_article_titles(
        archive_path,
        tmp_path / "cache.json",
        tmp_path / "state.json",
        batch_size=3,
        fetcher=lambda _: "Flooding closes roads across the county",
        now=datetime(2026, 8, 24, 14, tzinfo=UTC),
    )
    rows = pl.read_parquet(archive_path).sort("article_id")

    assert rows["disaster_match_strength"].to_list() == ["high", "weak", "weak"]
    assert rows["publisher_title_relevance"].to_list() == [
        "supporting",
        "supporting",
        "supporting",
    ]
    assert rows["quality_flags"].to_list() == [[], [], []]
    assert stats.promoted_articles == 1


def test_failed_archive_verification_keeps_archive_and_cursor_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    state_path = tmp_path / "state.json"
    _write_archive(archive_path, count=1)
    original = archive_path.read_bytes()
    real_read_parquet = pl.read_parquet

    def corrupt_verification(path, *args, **kwargs):  # noqa: ANN001
        frame = real_read_parquet(path, *args, **kwargs)
        return frame.head(0) if str(path).endswith(".partial") else frame

    monkeypatch.setattr(backfill_module.pl, "read_parquet", corrupt_verification)

    with pytest.raises(RuntimeError, match="verification"):
        backfill_article_titles(
            archive_path,
            tmp_path / "cache.json",
            state_path,
            batch_size=1,
            fetcher=lambda _: "Flooding closes roads across the county",
            now=datetime(2026, 8, 24, 14, tzinfo=UTC),
        )

    assert archive_path.read_bytes() == original
    assert not state_path.exists()
    assert not list(tmp_path.glob("*.partial"))
