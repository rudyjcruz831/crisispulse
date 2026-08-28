import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from pipelines.build_quality_sample import (
    _sampling_lane,
    _sampling_split,
    _stable_rank,
    build_quality_sample,
)


def _write_archive(path: Path) -> None:
    base = datetime(2026, 8, 22, 12)
    rows = []
    for index in range(18):
        strength = "high" if index < 6 else "weak"
        mismatch = 6 <= index < 12
        rows.append(
            {
                "article_id": f"{index:064x}",
                "seen_at": base - timedelta(hours=index),
                "canonical_url": f"https://news.example/flood-story-{index}",
                "source_domain": "news.example",
                "location_name": "New Jersey",
                "disaster_match_strength": strength,
                "duplicate_group_id": f"story-{index}",
                "matched_disaster_themes": ["NATURAL_DISASTER_FLOODING"],
                "url_topic_relevance": "mismatch" if mismatch else "unknown",
                "publisher_title": "" if index else "Flood closes local road",
                "publisher_title_relevance": "unknown",
                "quality_flags": ["url_topic_mismatch"] if mismatch else [],
            }
        )
    pl.from_dicts(rows).write_parquet(path)


def test_daily_sample_is_stable_balanced_and_atomic(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_archive(archive_path)

    first = build_quality_sample(
        archive_path,
        first_path,
        size=12,
        sample_date=date(2026, 8, 23),
    )
    second = build_quality_sample(
        archive_path,
        second_path,
        size=12,
        sample_date=date(2026, 8, 23),
    )
    payload = json.loads(first_path.read_text(encoding="utf-8"))

    assert first == second
    assert first.sample_articles == 12
    assert first.high_match_articles == 4
    assert first.headline_conflict_articles == 4
    assert first.ambiguous_match_articles == 4
    assert payload == json.loads(second_path.read_text(encoding="utf-8"))
    assert payload["sample_date"] == "2026-08-23"
    assert payload["articles"][0]["title"]
    assert {item["title_source"] for item in payload["articles"]} <= {
        "manual_override",
        "publisher_metadata",
        "url_path",
        "unavailable",
    }
    assert len({item["article_id"] for item in payload["articles"]}) == 12
    assert not list(tmp_path.glob("*.partial"))


def test_same_day_sample_keeps_article_ids_while_refreshing_evidence(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    sample_day = date(2026, 8, 23)
    _write_archive(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=sample_day,
    )
    first = json.loads(output_path.read_text(encoding="utf-8"))
    first_ids = [article["article_id"] for article in first["articles"]]
    high_ids = [
        article["article_id"]
        for article in first["articles"]
        if article["review_bucket"] == "high_match"
    ]
    selected_high_rank = max(_stable_rank(article_id, sample_day) for article_id in high_ids)
    existing_ids = set(first_ids)
    candidate_index = 1000
    while True:
        candidate_id = f"{candidate_index:064x}"
        if (
            candidate_id not in existing_ids
            and _stable_rank(candidate_id, sample_day) < selected_high_rank
        ):
            break
        candidate_index += 1

    archive = pl.read_parquet(archive_path)
    updated_title = "Updated publisher evidence confirms physical flooding"
    archive = archive.with_columns(
        pl.when(pl.col("article_id") == first_ids[0])
        .then(pl.lit(updated_title))
        .otherwise(pl.col("publisher_title"))
        .alias("publisher_title")
    )
    newcomer = archive.row(0, named=True)
    newcomer.update(
        {
            "article_id": candidate_id,
            "seen_at": datetime(2026, 8, 23, 13),
            "canonical_url": "https://news.example/new-flood-story",
            "publisher_title": "New flood story that would displace an old card",
        }
    )
    pl.concat(
        [archive, pl.from_dicts([newcomer], schema=archive.schema)],
        how="vertical",
    ).write_parquet(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=sample_day,
    )
    second = json.loads(output_path.read_text(encoding="utf-8"))

    assert [article["article_id"] for article in second["articles"]] == first_ids
    refreshed = next(
        article for article in second["articles"] if article["article_id"] == first_ids[0]
    )
    assert refreshed["title"] == updated_title
    assert second["archive_articles"] == first["archive_articles"] + 1


def test_same_day_sample_does_not_expand_after_a_small_first_run(
    tmp_path: Path,
) -> None:
    full_archive_path = tmp_path / "full.parquet"
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    _write_archive(full_archive_path)
    full_archive = pl.read_parquet(full_archive_path)
    full_archive.head(5).write_parquet(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=date(2026, 8, 23),
    )
    first = json.loads(output_path.read_text(encoding="utf-8"))
    first_ids = [article["article_id"] for article in first["articles"]]
    full_archive.write_parquet(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=date(2026, 8, 23),
    )
    second = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(first_ids) == 5
    assert [article["article_id"] for article in second["articles"]] == first_ids
    assert second["archive_articles"] == 18


def test_same_day_sample_keeps_safe_cards_when_archive_rows_disappear(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    sample_day = date(2026, 8, 23)
    _write_archive(archive_path)
    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=sample_day,
    )
    first = json.loads(output_path.read_text(encoding="utf-8"))
    removed_id = first["articles"][0]["article_id"]
    ineligible_id = first["articles"][1]["article_id"]
    preserved = {
        article["article_id"]: article
        for article in first["articles"]
        if article["article_id"] in {removed_id, ineligible_id}
    }

    archive = pl.read_parquet(archive_path).filter(
        pl.col("article_id") != removed_id
    ).with_columns(
        pl.when(pl.col("article_id") == ineligible_id)
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(pl.col("canonical_url"))
        .alias("canonical_url")
    )
    archive.write_parquet(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=sample_day,
    )
    second = json.loads(output_path.read_text(encoding="utf-8"))
    second_by_id = {
        article["article_id"]: article for article in second["articles"]
    }

    assert [article["article_id"] for article in second["articles"]] == [
        article["article_id"] for article in first["articles"]
    ]
    assert second_by_id[removed_id] == preserved[removed_id]
    assert second_by_id[ineligible_id] == preserved[ineligible_id]


def test_new_utc_day_reselects_with_the_current_size(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    fresh_path = tmp_path / "fresh.json"
    _write_archive(archive_path)
    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=date(2026, 8, 23),
    )

    build_quality_sample(
        archive_path,
        output_path,
        size=9,
        sample_date=date(2026, 8, 24),
    )
    build_quality_sample(
        archive_path,
        fresh_path,
        size=9,
        sample_date=date(2026, 8, 24),
    )
    rotated = json.loads(output_path.read_text(encoding="utf-8"))
    fresh = json.loads(fresh_path.read_text(encoding="utf-8"))

    assert rotated["sample_date"] == "2026-08-24"
    assert len(rotated["articles"]) == 9
    assert rotated["articles"] == fresh["articles"]


def test_sample_falls_back_when_one_bucket_is_small(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    _write_archive(archive_path)
    archive = pl.read_parquet(archive_path).filter(
        pl.col("disaster_match_strength") == "weak"
    )
    archive.write_parquet(archive_path)

    stats = build_quality_sample(
        archive_path,
        output_path,
        size=9,
        sample_date=date(2026, 8, 23),
    )

    assert stats.sample_articles == 9
    assert stats.high_match_articles == 0
    assert stats.headline_conflict_articles > 0
    assert stats.ambiguous_match_articles > 0


def test_sample_prioritizes_selected_urls_for_publisher_title_fetching(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    _write_archive(archive_path)
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        return f"Verified publisher headline for story {url.rsplit('-', 1)[-1]}"

    build_quality_sample(
        archive_path,
        output_path,
        size=12,
        sample_date=date(2026, 8, 23),
        title_cache_path=tmp_path / "titles.json",
        title_fetcher=fetcher,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(calls) == 11
    assert all(item["title_source"] == "publisher_metadata" for item in payload["articles"])


def test_sample_uses_a_manual_override_without_fetching_that_url(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    _write_archive(archive_path)
    override_url = "https://news.example/flood-story-1"
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        return f"Verified publisher headline for story {url.rsplit('-', 1)[-1]}"

    build_quality_sample(
        archive_path,
        output_path,
        size=18,
        sample_date=date(2026, 8, 23),
        title_cache_path=tmp_path / "titles.json",
        title_fetcher=fetcher,
        title_overrides={
            override_url: "Supply and Delivery of a Mini Hydraulic Excavator"
        },
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    overridden = next(
        item for item in payload["articles"] if item["url"] == override_url
    )

    assert override_url not in calls
    assert overridden["title"] == "Supply and Delivery of a Mini Hydraulic Excavator"
    assert overridden["title_source"] == "manual_override"


def test_sample_never_presents_a_domain_or_opaque_id_as_a_headline(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    _write_archive(archive_path)
    archive = pl.read_parquet(archive_path).with_columns(
        pl.when(pl.col("article_id") == f"{1:064x}")
        .then(pl.lit("https://allafrica.com/stories/202608180433.html"))
        .otherwise(pl.col("canonical_url"))
        .alias("canonical_url")
    )
    archive.write_parquet(archive_path)

    build_quality_sample(
        archive_path,
        output_path,
        size=18,
        sample_date=date(2026, 8, 23),
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    opaque = next(
        item for item in payload["articles"]
        if item["url"] == "https://allafrica.com/stories/202608180433.html"
    )

    assert opaque["title"] == "Title unavailable — open publisher story"
    assert opaque["title_source"] == "unavailable"


def _review(article_id: str, decision: str, version: int = 2) -> dict[str, object]:
    return {
        "article_id": article_id,
        "title": "Reviewed flood article",
        "url": "https://news.example/reviewed-flood-article",
        "source_domain": "news.example",
        "match_strength": "high",
        "review_bucket": "high_match",
        "decision": decision,
        "decision_schema_version": version,
        "reviewed_at": "2026-08-23T10:00:00Z",
        "tags": [] if version == 2 else None,
    }


def test_smart_queue_excludes_completed_v2_and_prioritizes_legacy(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    review_path = tmp_path / "article-reviews.jsonl"
    _write_archive(archive_path)
    completed_id = f"{0:064x}"
    legacy_id = f"{17:064x}"
    records = [
        _review(completed_id, "reported_flooding"),
        {
            key: value
            for key, value in _review(legacy_id, "relevant", 1).items()
            if key != "tags"
        },
    ]
    review_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )

    build_quality_sample(
        archive_path,
        output_path,
        size=9,
        sample_date=date(2026, 8, 23),
        review_path=review_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["version"] == 2
    assert completed_id not in {
        article["article_id"] for article in payload["articles"]
    }
    assert payload["articles"][0]["article_id"] == legacy_id
    assert "needs_detailed_relabel" in payload["articles"][0]["selection_intent"][
        "reasons"
    ]
    assert [
        article["selection_intent"]["rank"] for article in payload["articles"]
    ] == list(range(1, 10))
    assert payload["selection_intent"]["target"] == "cpu_smoke"
    assert payload["selection_intent"]["class_minimum"] == 4


def test_same_day_queue_keeps_unresolved_cards_and_replenishes(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    review_path = tmp_path / "article-reviews.jsonl"
    _write_archive(archive_path)
    build_quality_sample(
        archive_path,
        output_path,
        size=9,
        sample_date=date(2026, 8, 23),
        review_path=review_path,
    )
    first = json.loads(output_path.read_text(encoding="utf-8"))
    completed_id = first["articles"][3]["article_id"]
    review_path.write_text(
        json.dumps(_review(completed_id, "heavy_rain_only")) + "\n",
        encoding="utf-8",
    )

    build_quality_sample(
        archive_path,
        output_path,
        size=9,
        sample_date=date(2026, 8, 23),
        review_path=review_path,
    )
    second = json.loads(output_path.read_text(encoding="utf-8"))

    unresolved_ids = [
        article["article_id"]
        for article in first["articles"]
        if article["article_id"] != completed_id
    ]
    second_ids = [article["article_id"] for article in second["articles"]]
    assert second_ids[:8] == unresolved_ids
    assert second_ids[8] not in set(unresolved_ids) | {completed_id}
    assert len(second["articles"]) == 9


def test_sampling_split_uses_current_chronological_boundaries() -> None:
    readiness = {
        "_validation_boundary": datetime(2026, 8, 20, 0),
        "_test_boundary": datetime(2026, 8, 22, 0),
    }

    assert (
        _sampling_split({"seen_at": datetime(2026, 8, 19, 23)}, readiness)
        == "training"
    )
    assert (
        _sampling_split({"seen_at": datetime(2026, 8, 20, 0)}, readiness)
        == "validation"
    )
    assert (
        _sampling_split({"seen_at": datetime(2026, 8, 22, 0)}, readiness)
        == "test"
    )
    assert _sampling_split({"seen_at": datetime(2026, 8, 23, 0)}, {}) is None

    aware_readiness = {
        "_validation_boundary": datetime(2026, 8, 20, 0, tzinfo=UTC),
        "_test_boundary": datetime(2026, 8, 22, 0, tzinfo=UTC),
    }
    assert (
        _sampling_split({"seen_at": datetime(2026, 8, 21, 0)}, aware_readiness)
        == "validation"
    )


def test_sampling_lane_separates_physical_rain_floods_and_metaphors() -> None:
    base = {
        "publisher_title": "",
        "disaster_match_strength": "weak",
        "url_topic_relevance": "unknown",
        "publisher_title_relevance": "unknown",
    }

    assert _sampling_lane({
        **base,
        "canonical_url": "https://news.example/music-industry-reels-from-a-slop-flood",
    }) == "not_flood_related"
    assert _sampling_lane({
        **base,
        "canonical_url": "https://news.example/two-rescued-from-flooded-cave",
    }) == "reported_flooding"
    assert _sampling_lane({
        **base,
        "canonical_url": "https://news.example/nepal-flood-toll-rises-as-lake-fears-ease-for-rescuers",
    }) == "reported_flooding"
    assert _sampling_lane({
        **base,
        "canonical_url": "https://news.example/heavy-rain-expected-this-weekend",
    }) == "heavy_rain_only"
    assert _sampling_lane({
        **base,
        "canonical_url": "https://news.example/heavy-rain-across-the-region",
    }) == "heavy_rain_only"


def test_smart_queue_selects_only_one_article_per_story_group(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    review_path = tmp_path / "article-reviews.jsonl"
    _write_archive(archive_path)
    archive = pl.read_parquet(archive_path).with_columns(
        pl.when(pl.col("article_id").is_in([f"{0:064x}", f"{1:064x}"]))
        .then(pl.lit("shared-syndicated-story"))
        .otherwise(pl.col("duplicate_group_id"))
        .alias("duplicate_group_id")
    )
    archive.write_parquet(archive_path)

    stats = build_quality_sample(
        archive_path,
        output_path,
        size=18,
        sample_date=date(2026, 8, 23),
        review_path=review_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    groups_by_id = dict(zip(archive["article_id"], archive["duplicate_group_id"], strict=True))
    selected_groups = [groups_by_id[article["article_id"]] for article in payload["articles"]]

    assert stats.sample_articles == 17
    assert len(selected_groups) == len(set(selected_groups))


def test_smart_queue_avoids_exact_syndicated_headline_duplicates(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.parquet"
    output_path = tmp_path / "sample.json"
    review_path = tmp_path / "article-reviews.jsonl"
    _write_archive(archive_path)
    duplicate_title = "Wet bank holiday forecast amid possible gales and thunder"
    archive = pl.read_parquet(archive_path).with_columns(
        pl.when(pl.col("article_id").is_in([f"{6:064x}", f"{7:064x}"]))
        .then(pl.lit(duplicate_title))
        .otherwise(pl.col("publisher_title"))
        .alias("publisher_title")
    )
    archive.write_parquet(archive_path)

    stats = build_quality_sample(
        archive_path,
        output_path,
        size=18,
        sample_date=date(2026, 8, 23),
        review_path=review_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert stats.sample_articles == 17
    assert sum(article["title"] == duplicate_title for article in payload["articles"]) == 1
