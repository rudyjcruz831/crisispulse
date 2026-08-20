from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from pipelines.score_anomalies import score_anomalies


def _feature_rows(signals: list[tuple[int, int, int]]) -> pl.DataFrame:
    start = datetime(2026, 8, 20, 0, 0)
    return pl.DataFrame(
        {
            "window_start": [start + timedelta(hours=hour) for hour, _, _ in signals],
            "region_id": ["US:USHI"] * len(signals),
            "country_code": ["US"] * len(signals),
            "adm1_code": ["USHI"] * len(signals),
            "disaster_type": ["flood"] * len(signals),
            "article_count": [stories for _, stories, _ in signals],
            "estimated_unique_story_count": [stories for _, stories, _ in signals],
            "high_confidence_story_count": [stories for _, stories, _ in signals],
            "unique_domain_count": [domains for _, _, domains in signals],
        }
    )


def test_short_history_refuses_to_create_anomaly(tmp_path: Path) -> None:
    input_path = tmp_path / "features.parquet"
    output_path = tmp_path / "anomalies.parquet"
    _feature_rows([(0, 1, 1), (1, 8, 8)]).write_parquet(input_path)

    stats = score_anomalies(
        input_path, output_path, lookback_hours=4, minimum_history_hours=3
    )
    scored = pl.read_parquet(output_path)

    assert stats.candidate_anomalies == 0
    assert scored["anomaly_status"].to_list() == [
        "insufficient_history",
        "insufficient_history",
    ]


def test_zero_filled_history_detects_supported_jump(tmp_path: Path) -> None:
    input_path = tmp_path / "features.parquet"
    output_path = tmp_path / "anomalies.parquet"
    report_path = tmp_path / "report.json"
    _feature_rows([(0, 0, 0), (3, 5, 5)]).write_parquet(input_path)

    stats = score_anomalies(
        input_path,
        output_path,
        report_path,
        lookback_hours=3,
        minimum_history_hours=3,
    )
    scored = pl.read_parquet(output_path)
    spike = scored.filter(pl.col("window_start") == datetime(2026, 8, 20, 3)).row(
        0, named=True
    )

    assert stats.scored_rows == 4
    assert stats.observed_feature_rows == 2
    assert stats.candidate_anomalies == 1
    assert spike["baseline_median"] == 0
    assert spike["baseline_mad"] == 0
    assert spike["anomaly_status"] == "candidate_anomaly"
    assert report_path.exists()


def test_raw_syndication_without_story_support_is_not_anomaly(tmp_path: Path) -> None:
    input_path = tmp_path / "features.parquet"
    output_path = tmp_path / "anomalies.parquet"
    frame = _feature_rows([(0, 0, 0), (3, 1, 8)]).with_columns(
        pl.when(pl.col("window_start") == datetime(2026, 8, 20, 3))
        .then(pl.lit(40))
        .otherwise(pl.col("article_count"))
        .alias("article_count")
    )
    frame.write_parquet(input_path)

    stats = score_anomalies(
        input_path, output_path, lookback_hours=3, minimum_history_hours=3
    )
    spike = pl.read_parquet(output_path).filter(
        pl.col("window_start") == datetime(2026, 8, 20, 3)
    ).row(0, named=True)

    assert stats.candidate_anomalies == 0
    assert spike["article_count"] == 40
    assert spike["anomaly_status"] == "below_minimum_support"
