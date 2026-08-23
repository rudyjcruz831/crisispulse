import json
from datetime import datetime, timedelta

import polars as pl

from pipelines.build_outcomes import build_outcomes


def test_six_hour_outcomes_use_only_future_windows(tmp_path):
    start = datetime(2026, 8, 20, 0)
    input_path = tmp_path / "anomalies.parquet"
    output_path = tmp_path / "outcomes.parquet"
    report_path = tmp_path / "outcomes.json"
    domains = [20, 2, 3, 4, 20, 5, 0, 0, 0]
    candidates = [False, True, False, False, True, False, False, False, False]
    pl.DataFrame(
        {
            "window_start": [start + timedelta(hours=hour) for hour in range(9)],
            "region_id": ["US:TEST"] * 9,
            "disaster_type": ["flood"] * 9,
            "observed_feature_row": [True] * 9,
            "article_count": domains,
            "estimated_unique_story_count": domains,
            "high_confidence_story_count": domains,
            "unique_domain_count": domains,
            "baseline_history_hours": list(range(9)),
            "baseline_median": [0.0] * 9,
            "baseline_mad": [0.0] * 9,
            "robust_z_score": [None] * 9,
            "anomaly_status": [
                "candidate_anomaly" if candidate else "normal"
                for candidate in candidates
            ],
            "is_candidate_anomaly": candidates,
        }
    ).write_parquet(input_path)

    stats = build_outcomes(
        input_path,
        output_path,
        report_path,
        horizon_hours=3,
        domain_threshold=10,
    )
    outcomes = pl.read_parquet(output_path).sort("window_start")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert outcomes["label_media_spread_6h"].to_list() == [
        False,
        True,
        True,
        True,
        False,
        False,
        None,
        None,
        None,
    ]
    # The current-hour value of 20 at index zero is excluded from its own label.
    assert outcomes["future_max_domain_count"][0] == 4
    assert stats.eligible_rows == 6
    assert stats.pending_rows == 3
    assert stats.positive_outcomes == 3
    assert stats.evaluation_ready_rows == 6
    assert stats.evaluation_positive_outcomes == 3
    assert stats.evaluated_candidate_predictions == 2
    assert stats.true_positives == 1
    assert stats.false_positives == 1
    assert stats.false_negatives == 2
    assert report["precision"] == 0.5
    assert report["recall"] == 1 / 3
