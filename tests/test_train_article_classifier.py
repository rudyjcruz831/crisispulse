import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from pipelines.train_article_classifier import (
    ArticleRow,
    build_readiness_report,
    load_latest_native_reviews,
    run_article_baseline,
    split_articles,
)


LABELS = (
    "reported_flooding",
    "flood_risk_warning",
    "heavy_rain_only",
    "not_flood_related",
)


def _article_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _review(
    article_id: str,
    decision: str,
    reviewed_at: datetime,
    *,
    schema_version: int = 2,
) -> dict[str, object]:
    return {
        "article_id": article_id,
        "title": "Reviewed headline",
        "url": f"https://publisher.example/articles/{article_id}",
        "source_domain": "publisher.example",
        "match_strength": "high",
        "review_bucket": "high_match",
        "decision": decision,
        "decision_schema_version": schema_version,
        "tags": [] if schema_version == 2 else None,
        "reviewed_at": reviewed_at.isoformat().replace("+00:00", "Z"),
    }


def _write_reviews(path: Path, reviews: list[dict[str, object]]) -> None:
    normalized = []
    for review in reviews:
        value = dict(review)
        if value.get("tags") is None:
            value.pop("tags")
        normalized.append(json.dumps(value))
    path.write_text("\n".join(normalized) + "\n", encoding="utf-8")


def _write_archive(path: Path, rows: list[dict[str, object]]) -> None:
    pl.from_dicts(
        rows,
        schema={
            "article_id": pl.String,
            "seen_at": pl.Datetime(time_unit="us"),
            "canonical_url": pl.String,
            "source_domain": pl.String,
            "duplicate_group_id": pl.String,
            "publisher_title": pl.String,
        },
        strict=False,
    ).with_columns(pl.col("seen_at").dt.replace_time_zone(None)).write_parquet(path)


def test_readiness_uses_latest_decision_and_reports_every_exclusion(tmp_path: Path) -> None:
    reviews_path = tmp_path / "article-reviews.jsonl"
    archive_path = tmp_path / "articles.parquet"
    now = datetime(2026, 8, 25, tzinfo=UTC)
    eligible_id = _article_id("eligible")
    corrected_id = _article_id("corrected")
    legacy_id = _article_id("legacy")
    no_text_id = _article_id("no-text")
    _write_reviews(
        reviews_path,
        [
            _review(eligible_id, "reported_flooding", now),
            _review(corrected_id, "reported_flooding", now),
            _review(corrected_id, "uncertain", now + timedelta(minutes=1)),
            _review(legacy_id, "relevant", now, schema_version=1),
            _review(no_text_id, "not_flood_related", now),
        ],
    )
    _write_archive(
        archive_path,
        [
            {
                "article_id": eligible_id,
                "seen_at": now,
                "canonical_url": "https://one.example/reported-flooding-affects-river-town",
                "source_domain": "www.one.example",
                "duplicate_group_id": "story-1",
                "publisher_title": "A publisher title whose source is not recorded",
            },
            {
                "article_id": corrected_id,
                "seen_at": now,
                "canonical_url": "https://two.example/flooding-affects-another-town",
                "source_domain": "two.example",
                "duplicate_group_id": "story-2",
                "publisher_title": "Unused uncertain title",
            },
            {
                "article_id": legacy_id,
                "seen_at": now,
                "canonical_url": "https://three.example/flooding-affects-third-town",
                "source_domain": "three.example",
                "duplicate_group_id": "story-3",
                "publisher_title": "Unused legacy title",
            },
            {
                "article_id": no_text_id,
                "seen_at": now,
                "canonical_url": "https://four.example/article/123456",
                "source_domain": "four.example",
                "duplicate_group_id": "story-4",
                "publisher_title": "Unproven publisher metadata is not silently used",
            },
        ],
    )

    report, prepared, _split = build_readiness_report(reviews_path, archive_path)

    assert report["latest_review_count"] == 4
    assert report["resolved_schema_v2_count"] == 2
    assert report["usable_training_rows"] == 1
    assert prepared.rows[0].text_source == "url_path"
    assert prepared.rows[0].publisher_group == "one.example"
    assert report["exclusion_counts"] == {
        "legacy_schema": 1,
        "missing_inference_text": 1,
        "uncertain": 1,
    }
    assert report["training_performed"] is False
    assert report["status"] == "not_ready"


def test_native_review_loader_rejects_external_or_unknown_schema_fields(tmp_path: Path) -> None:
    reviews_path = tmp_path / "external.jsonl"
    record = _review(
        _article_id("external"),
        "reported_flooding",
        datetime(2026, 8, 25, tzinfo=UTC),
    )
    record["external_dataset"] = "somewhere"
    _write_reviews(reviews_path, [record])

    with pytest.raises(ValueError, match="native CrisisPulse contract"):
        load_latest_native_reviews(reviews_path)


def test_split_promotes_story_groups_and_purges_final_publishers() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        ArticleRow(
            article_id=_article_id(f"row-{index}"),
            seen_at=start + timedelta(days=index),
            text=f"Headline number {index} about flooding",
            text_source="url_path",
            label=LABELS[index % len(LABELS)],
            publisher_group=f"publisher-{index}",
            story_group=f"story-{index}",
            language="unknown",
        )
        for index in range(20)
    ]
    # The oldest row shares a story with the final period, so it must move to
    # the final split. A different old row shares a final publisher and must be
    # purged from the earlier split.
    rows[0] = ArticleRow(**{**rows[0].__dict__, "story_group": rows[-1].story_group})
    rows[1] = ArticleRow(
        **{**rows[1].__dict__, "publisher_group": rows[-2].publisher_group}
    )

    split = split_articles(rows)
    split_story_sets = [
        {row.story_group for row in group}
        for group in (split.training, split.validation, split.test)
    ]
    test_publishers = {row.publisher_group for row in split.test}

    assert split.metadata["story_rows_promoted_to_newer_split"] == 1
    assert split.metadata["earlier_rows_purged_for_final_publishers"] == 1
    assert not (split_story_sets[0] & split_story_sets[2])
    assert not (
        test_publishers
        & {row.publisher_group for row in split.training + split.validation}
    )


def _write_smoke_dataset(review_path: Path, archive_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    phrases = {
        "reported_flooding": "river flooding damages homes in county",
        "flood_risk_warning": "official flood warning issued for county",
        "heavy_rain_only": "heavy rain and storms affect county travel",
        "not_flood_related": "city council approves new library project",
    }
    reviews: list[dict[str, object]] = []
    archive: list[dict[str, object]] = []
    for index in range(40):
        label = LABELS[index % len(LABELS)]
        url = f"https://publisher-{index}.example/{phrases[label].replace(' ', '-')}-{index}"
        article_id = _article_id(url)
        seen_at = start + timedelta(days=index)
        reviews.append(_review(article_id, label, seen_at + timedelta(hours=12)))
        archive.append(
            {
                "article_id": article_id,
                "seen_at": seen_at,
                "canonical_url": url,
                "source_domain": f"publisher-{index}.example",
                "duplicate_group_id": f"story-{index}",
                "publisher_title": None,
            }
        )
    _write_reviews(review_path, reviews)
    _write_archive(archive_path, archive)


def test_smoke_training_is_explicitly_non_evaluative_and_retains_predictions(
    tmp_path: Path,
) -> None:
    reviews_path = tmp_path / "article-reviews.jsonl"
    archive_path = tmp_path / "articles.parquet"
    report_path = tmp_path / "report.json"
    predictions_path = tmp_path / "predictions.parquet"
    _write_smoke_dataset(reviews_path, archive_path)

    report = run_article_baseline(
        reviews_path,
        archive_path,
        report_path,
        train=True,
        smoke_test=True,
        predictions_path=predictions_path,
    )

    assert report["status"] == "non_evaluative_smoke_test_completed"
    assert report["evaluation_tier"] == "NON_EVALUATIVE_SMOKE_TEST"
    assert report["training_performed"] is True
    assert report["production_readiness"]["ready"] is False
    assert report["smoke_test_readiness"]["ready"] is True
    assert "dummy_prior_test" in report["metrics"]["comparators"]
    assert "url_path" in report["metrics"]["test_slices"]["text_source"]
    assert "unknown" in report["metrics"]["test_slices"]["language"]
    assert report_path.is_file()
    assert predictions_path.is_file()
    predictions = pl.read_parquet(predictions_path)
    assert predictions.height > 0
    probability_columns = {
        column.removeprefix("probability_")
        for column in predictions.columns
        if column.startswith("probability_")
    }
    assert set(LABELS).issubset(probability_columns)


def test_train_mode_stays_blocked_when_production_gates_fail(tmp_path: Path) -> None:
    reviews_path = tmp_path / "article-reviews.jsonl"
    archive_path = tmp_path / "articles.parquet"
    report_path = tmp_path / "report.json"
    predictions_path = tmp_path / "predictions.parquet"
    _write_smoke_dataset(reviews_path, archive_path)

    report = run_article_baseline(
        reviews_path,
        archive_path,
        report_path,
        train=True,
        predictions_path=predictions_path,
    )

    assert report["status"] == "blocked_cpu_baseline"
    assert report["training_performed"] is False
    assert report_path.is_file()
    assert not predictions_path.exists()
