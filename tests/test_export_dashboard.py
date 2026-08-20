import json
from datetime import datetime

import polars as pl

from pipelines.export_dashboard import build_dashboard_snapshot


def test_dashboard_snapshot_prefers_candidates_and_summarizes_outputs(tmp_path):
    clean_path = tmp_path / "clean.parquet"
    feature_path = tmp_path / "features.parquet"
    anomaly_path = tmp_path / "anomalies.parquet"
    report_path = tmp_path / "report.json"

    pl.DataFrame(
        {"article_id": ["a", "b", "c"], "duplicate_group_id": ["g1", "g1", "g2"]}
    ).write_parquet(clean_path)
    pl.DataFrame(
        {
            "window_start": [datetime(2026, 8, 20, 18), datetime(2026, 8, 20, 19)],
            "estimated_unique_story_count": [2, 3],
        }
    ).write_parquet(feature_path)
    pl.DataFrame(
        {
            "window_start": [datetime(2026, 8, 20, 19), datetime(2026, 8, 20, 19)],
            "region_id": ["US:USHI", "UNKNOWN"],
            "high_confidence_story_count": [5, 8],
            "unique_domain_count": [5, 7],
            "baseline_median": [4.0, 2.0],
            "robust_z_score": [0.22, 7.25],
            "anomaly_status": ["normal", "candidate_anomaly"],
            "is_candidate_anomaly": [False, True],
        }
    ).write_parquet(anomaly_path)
    report_path.write_text(
        json.dumps(
            {
                "parameters": {"minimum_history_hours": 168},
                "scored_rows": 8,
                "hourly_windows": 2,
                "regions": 2,
                "candidate_anomalies": 1,
                "status_counts": [
                    {"anomaly_status": "normal", "row_count": 1},
                    {"anomaly_status": "candidate_anomaly", "row_count": 1},
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_dashboard_snapshot(
        clean_path, feature_path, anomaly_path, report_path
    )

    assert snapshot["snapshot"]["clean_articles"] == 3
    assert snapshot["snapshot"]["story_groups"] == 2
    assert snapshot["snapshot"]["candidates"] == 1
    assert snapshot["signals"][0]["code"] == "UNKNOWN"
    assert snapshot["signals"][0]["status_label"] == "Candidate"
    assert snapshot["status_counts"]["insufficient_history"] == 0
