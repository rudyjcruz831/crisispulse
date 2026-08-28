import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

import pipelines.backfill_review_title_sources as backfill_module
from pipelines.backfill_review_title_sources import backfill_review_title_sources
from pipelines.publisher_titles import TITLE_PARSER_VERSION


ARTICLE_ID = "a" * 64
URL = "https://www.news.example/weather/flooding-closes-roads"
TITLE = "Flooding closes roads across the county"


def _review(**updates: object) -> dict[str, object]:
    record: dict[str, object] = {
        "article_id": ARTICLE_ID,
        "title": TITLE,
        "url": URL,
        "source_domain": "www.news.example",
        "match_strength": "high",
        "review_bucket": "high_match",
        "decision": "reported_flooding",
        "decision_schema_version": 2,
        "tags": ["road-closure"],
        "reviewed_at": "2026-08-24T10:00:00Z",
    }
    record.update(updates)
    return record


def _inputs(tmp_path: Path, review: dict[str, object] | None = None) -> tuple[Path, Path, Path]:
    review_path = tmp_path / "article-reviews.jsonl"
    archive_path = tmp_path / "archive.parquet"
    cache_path = tmp_path / "publisher-title-cache.json"
    review_path.write_text(json.dumps(review or _review()) + "\n", encoding="utf-8")
    pl.from_dicts(
        [
            {
                "article_id": ARTICLE_ID,
                "canonical_url": URL,
                "source_domain": "news.example",
            }
        ]
    ).write_parquet(archive_path)
    cache_path.write_text(
        json.dumps(
            {
                "version": TITLE_PARSER_VERSION,
                "entries": {
                    URL: {
                        "status": "ok",
                        "title": TITLE,
                        "fetched_at": "2026-08-24T11:00:00+00:00",
                        "parser_version": TITLE_PARSER_VERSION,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return review_path, archive_path, cache_path


def test_dry_run_is_default_and_does_not_write(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    before = paths[0].read_bytes()

    stats = backfill_review_title_sources(*paths)

    assert stats.eligible_corrections == 1
    assert stats.appended_corrections == 0
    assert stats.dry_run is True
    assert paths[0].read_bytes() == before


def test_apply_appends_exact_match_once_and_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _inputs(tmp_path)
    before = paths[0].read_bytes()
    real_write = os.write
    writes: list[bytes] = []

    def tracked_write(descriptor: int, payload: bytes) -> int:
        writes.append(payload)
        return real_write(descriptor, payload)

    monkeypatch.setattr(os, "write", tracked_write)
    applied_at = datetime(2026, 8, 25, 12, 30, tzinfo=UTC)
    stats = backfill_review_title_sources(*paths, apply=True, now=applied_at)
    after = paths[0].read_bytes()
    appended = json.loads(after[len(before) :])

    assert stats.appended_corrections == 1
    assert after.startswith(before)
    assert len(writes) == 1
    assert appended["title_source"] == "publisher_metadata"
    assert appended["reviewed_at"] == applied_at.isoformat()
    for field in (
        "article_id",
        "title",
        "url",
        "source_domain",
        "match_strength",
        "review_bucket",
        "decision",
        "decision_schema_version",
        "tags",
    ):
        assert appended[field] == _review()[field]


def test_apply_is_idempotent_after_provenance_correction(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    first = backfill_review_title_sources(*paths, apply=True)
    after_first = paths[0].read_bytes()

    second = backfill_review_title_sources(*paths, apply=True)

    assert first.appended_corrections == 1
    assert second.eligible_corrections == 0
    assert second.appended_corrections == 0
    assert paths[0].read_bytes() == after_first


@pytest.mark.parametrize(
    "mismatch",
    [
        "url",
        "domain",
        "title",
        "cache_status",
        "cache_version",
        "parser_version",
        "invalid_fetched_at",
        "naive_fetched_at",
        "future_fetched_at",
        "stale_fetched_at",
    ],
)
def test_mismatches_are_rejected(tmp_path: Path, mismatch: str) -> None:
    paths = _inputs(tmp_path)
    if mismatch == "url":
        archive = pl.read_parquet(paths[1]).with_columns(
            pl.lit("https://news.example/different").alias("canonical_url")
        )
        archive.write_parquet(paths[1])
    elif mismatch == "domain":
        archive = pl.read_parquet(paths[1]).with_columns(
            pl.lit("other.example").alias("source_domain")
        )
        archive.write_parquet(paths[1])
    else:
        cache = json.loads(paths[2].read_text(encoding="utf-8"))
        if mismatch == "title":
            cache["entries"][URL]["title"] = "Different verified publisher headline"
        elif mismatch == "cache_status":
            cache["entries"][URL]["status"] = "miss"
        elif mismatch == "cache_version":
            cache["version"] = TITLE_PARSER_VERSION - 1
        elif mismatch == "parser_version":
            cache["entries"][URL]["parser_version"] = TITLE_PARSER_VERSION - 1
        elif mismatch == "invalid_fetched_at":
            cache["entries"][URL]["fetched_at"] = "not-a-time"
        elif mismatch == "naive_fetched_at":
            cache["entries"][URL]["fetched_at"] = "2026-08-24T11:00:00"
        elif mismatch == "future_fetched_at":
            cache["entries"][URL]["fetched_at"] = "2030-01-01T00:00:00+00:00"
        else:
            cache["entries"][URL]["fetched_at"] = "2020-01-01T00:00:00+00:00"
        paths[2].write_text(json.dumps(cache), encoding="utf-8")
    before = paths[0].read_bytes()

    if mismatch == "cache_version":
        with pytest.raises(ValueError, match="publisher title cache is invalid"):
            backfill_review_title_sources(*paths, apply=True)
        assert paths[0].read_bytes() == before
        return

    stats = backfill_review_title_sources(*paths, apply=True)

    assert stats.eligible_corrections == 0
    assert paths[0].read_bytes() == before


def test_legacy_review_is_not_backfilled(tmp_path: Path) -> None:
    legacy = _review(decision="relevant", decision_schema_version=1)
    legacy.pop("tags")
    paths = _inputs(tmp_path, legacy)
    before = paths[0].read_bytes()

    stats = backfill_review_title_sources(*paths, apply=True)

    assert stats.eligible_corrections == 0
    assert paths[0].read_bytes() == before


def test_invalid_review_log_is_rejected_without_writing(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    paths[0].write_bytes(paths[0].read_bytes() + b"not-json\n")
    before = paths[0].read_bytes()

    with pytest.raises(ValueError, match="invalid JSON"):
        backfill_review_title_sources(*paths, apply=True)

    assert paths[0].read_bytes() == before


def test_apply_reloads_latest_review_while_holding_shared_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _inputs(tmp_path)
    newer = _review(decision="heavy_rain_only", tags=["newer-human-answer"])

    @contextmanager
    def interleaving_lock(_review_path: Path):
        with paths[0].open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(newer) + "\n")
        yield

    monkeypatch.setattr(backfill_module, "_review_lock", interleaving_lock)
    stats = backfill_review_title_sources(
        *paths,
        apply=True,
        now=datetime(2026, 8, 25, 12, 30, tzinfo=UTC),
    )
    appended = json.loads(paths[0].read_text(encoding="utf-8").splitlines()[-1])

    assert stats.appended_corrections == 1
    assert appended["decision"] == "heavy_rain_only"
    assert appended["tags"] == ["newer-human-answer"]
    assert appended["title_source"] == "publisher_metadata"
