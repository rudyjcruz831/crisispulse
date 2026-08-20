from datetime import datetime
from pathlib import Path

import polars as pl

from pipelines.build_features import build_features
from pipelines.clean_gkg import clean_files
from pipelines.inspect_features import build_feature_report


SAMPLE = Path(__file__).parents[1] / "data" / "sample" / "gkg_sample.tsv"


def test_batch_clean_deduplicates_across_input_files(tmp_path: Path) -> None:
    output = tmp_path / "batch.parquet"
    stats = clean_files([SAMPLE, SAMPLE], output, "flood", "weak")
    frame = pl.read_parquet(output)

    assert stats.input_files == 2
    assert stats.input_rows == 10
    assert stats.disaster_rows == 8
    assert stats.duplicate_rows == 5
    assert stats.output_rows == 3
    assert frame["source_file"].to_list() == [SAMPLE.name] * 3


def test_hourly_features_are_duplicate_adjusted_and_include_velocity(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.parquet"
    feature_path = tmp_path / "features.parquet"
    pl.DataFrame(
        {
            "seen_at": [
                datetime(2026, 8, 20, 12, 0),
                datetime(2026, 8, 20, 12, 15),
                datetime(2026, 8, 20, 12, 30),
                datetime(2026, 8, 20, 13, 0),
            ],
            "country_code": ["US", "US", "US", "US"],
            "adm1_code": ["USLA", "USLA", "USLA", "USLA"],
            "disaster_type": ["flood", "flood", "flood", "flood"],
            "source_domain": ["one.test", "two.test", "three.test", "four.test"],
            "duplicate_group_id": ["story-1", "story-1", "story-2", "story-3"],
            "disaster_match_strength": ["high", "high", "weak", "weak"],
            "tone": [-2.0, -4.0, -3.0, -1.0],
        }
    ).write_parquet(clean_path)

    stats = build_features(clean_path, feature_path)
    features = pl.read_parquet(feature_path).sort("window_start")

    assert stats.input_rows == 4
    assert stats.feature_rows == 2
    assert stats.hourly_windows == 2
    assert stats.regions == 1
    first = features.row(0, named=True)
    second = features.row(1, named=True)
    assert first["region_id"] == "US:USLA"
    assert first["article_count"] == 3
    assert first["estimated_unique_story_count"] == 2
    assert round(first["duplicate_ratio"], 6) == round(1 / 3, 6)
    assert first["article_velocity"] is None
    assert second["high_confidence_article_count"] == 0
    assert second["weak_article_count"] == 1
    assert second["article_velocity"] == -1

    report = build_feature_report(feature_path, top=1)
    assert report["feature_rows"] == 2
    assert report["regions"] == 1
    assert len(report["top_signals"]) == 1


def test_ambiguous_location_is_routed_to_unknown_region(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.parquet"
    feature_path = tmp_path / "features.parquet"
    pl.DataFrame(
        {
            "seen_at": [datetime(2026, 8, 20, 12, 0), datetime(2026, 8, 20, 12, 15)],
            "country_code": ["US", "US"],
            "adm1_code": ["USNH", "USHI"],
            "disaster_type": ["flood", "flood"],
            "source_domain": ["ambiguous.test", "hawaii.test"],
            "duplicate_group_id": ["story-1", "story-2"],
            "disaster_match_strength": ["high", "high"],
            "tone": [-2.0, -3.0],
            "location_selection_status": ["ambiguous_region", "single_region"],
        }
    ).write_parquet(clean_path)

    build_features(clean_path, feature_path)
    features = pl.read_parquet(feature_path)
    unknown = features.filter(pl.col("region_id") == "UNKNOWN").row(0, named=True)
    hawaii = features.filter(pl.col("region_id") == "US:USHI").row(0, named=True)

    assert unknown["country_code"] is None
    assert unknown["adm1_code"] is None
    assert unknown["location_review_article_count"] == 1
    assert unknown["location_confident_article_count"] == 0
    assert hawaii["location_review_article_count"] == 0
    assert hawaii["location_confident_article_count"] == 1
