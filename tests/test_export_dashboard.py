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
        {
            "article_id": ["a", "b", "c"],
            "seen_at": [datetime(2026, 8, 20, 19)] * 3,
            "country_code": [None, None, None],
            "adm1_code": [None, None, None],
            "location_selection_status": ["missing", "missing", "missing"],
            "canonical_url": [
                "https://one.test/flood-report",
                "https://two.test/flood-report",
                "javascript:alert(1)",
            ],
            "source_domain": ["one.test", "two.test", "unsafe.test"],
            "duplicate_group_id": ["g1", "g1", "g2"],
            "disaster_match_strength": ["high", "high", "high"],
            "matched_disaster_themes": [["FLOOD"], ["FLOOD"], ["FLOOD"]],
            "location_name": [None, None, None],
        }
    ).write_parquet(clean_path)
    pl.DataFrame(
        {
            "window_start": [datetime(2026, 8, 20, 18), datetime(2026, 8, 20, 19)],
            "article_count": [4, 5],
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

    assert snapshot["snapshot"]["clean_articles"] == 9
    assert snapshot["snapshot"]["story_groups"] == 5
    assert snapshot["snapshot"]["candidates"] == 1
    assert snapshot["signals"][0]["code"] == "UNKNOWN"
    assert snapshot["signals"][0]["status_label"] == "Candidate"
    assert len(snapshot["signals"][0]["evidence"]) == 1
    assert [
        source["domain"] for source in snapshot["signals"][0]["evidence"][0]["sources"]
    ] == ["one.test", "two.test"]
    assert snapshot["status_counts"]["insufficient_history"] == 0


def test_dashboard_snapshot_preserves_evidence_for_an_older_candidate(tmp_path):
    clean_path = tmp_path / "clean.parquet"
    feature_path = tmp_path / "features.parquet"
    anomaly_path = tmp_path / "anomalies.parquet"
    report_path = tmp_path / "report.json"
    pl.DataFrame({"article_id": ["a"]}).write_parquet(clean_path)
    pl.DataFrame(
        {
            "window_start": [datetime(2026, 8, 20, 19)],
            "article_count": [1],
            "estimated_unique_story_count": [1],
        }
    ).write_parquet(feature_path)
    pl.DataFrame(
        {
            "window_start": [datetime(2026, 8, 20, 19)],
            "region_id": ["US:USHI"],
            "high_confidence_story_count": [3],
            "unique_domain_count": [3],
            "baseline_median": [0.0],
            "robust_z_score": [None],
            "anomaly_status": ["candidate_anomaly"],
            "is_candidate_anomaly": [True],
        }
    ).write_parquet(anomaly_path)
    report_path.write_text(
        json.dumps(
            {
                "parameters": {"minimum_history_hours": 168},
                "scored_rows": 1,
                "hourly_windows": 1,
                "regions": 1,
                "candidate_anomalies": 1,
                "status_counts": [],
            }
        ),
        encoding="utf-8",
    )
    prior_evidence = [
        {
            "story_id": "story-1",
            "seen_at": "2026-08-20T19:00:00",
            "location": "Hawaii",
            "themes": ["FLOOD"],
            "sources": [
                {"domain": "spoofed.test", "url": "https://one.test/flood"},
                {"domain": "unsafe.test", "url": "javascript:alert(1)"},
            ],
        }
    ]
    previous_snapshot = {
        "signals": [
            {
                "code": "US:USHI",
                "window_start": "2026-08-20T19:00:00",
                "evidence": prior_evidence,
            }
        ]
    }

    snapshot = build_dashboard_snapshot(
        clean_path,
        feature_path,
        anomaly_path,
        report_path,
        previous_snapshot,
    )

    assert snapshot["signals"][0]["evidence"][0]["sources"] == [
        {"domain": "one.test", "url": "https://one.test/flood"}
    ]
