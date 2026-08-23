import json
from datetime import datetime

import polars as pl

from pipelines.export_dashboard import build_dashboard_snapshot


def test_dashboard_snapshot_prefers_candidates_and_summarizes_outputs(tmp_path):
    clean_path = tmp_path / "clean.parquet"
    feature_path = tmp_path / "features.parquet"
    anomaly_path = tmp_path / "anomalies.parquet"
    report_path = tmp_path / "report.json"
    outcome_report_path = tmp_path / "outcomes.json"
    model_report_path = tmp_path / "model-report.json"

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
    outcome_report_path.write_text(
        json.dumps(
            {
                "target": {
                    "name": "media_spread_6h",
                    "horizon_hours": 6,
                    "domain_threshold": 20,
                    "definition": "Twenty domains in a future hour.",
                },
                "eligible_rows": 100,
                "positive_outcomes": 7,
                "evaluation_ready_rows": 12,
                "candidate_predictions": 1,
                "evaluated_candidate_predictions": 0,
                "pending_predictions": [
                    {
                        "region_code": "UNKNOWN",
                        "window_start": "2026-08-20T19:00:00",
                        "matures_at": "2026-08-21T01:00:00",
                        "hours_remaining": 6,
                        "stories_at_detection": 8,
                        "domains_at_detection": 7,
                    }
                ],
                "precision": None,
                "recall": None,
            }
        ),
        encoding="utf-8",
    )
    model_report_path.write_text(
        json.dumps(
            {
                "model": {
                    "type": "logistic_regression",
                    "decision_threshold": 0.9979,
                    "scores_are_calibrated_probabilities": False,
                },
                "splits": {
                    "test": {
                        "prediction_start": "2026-08-19T19:00:00",
                        "prediction_end": "2026-08-20T19:00:00",
                    }
                },
                "training_rows": 44110,
                "validation_rows": 7619,
                "test_rows": 10025,
                "test_positives": 51,
                "validation_hours": 19,
                "test_hours": 25,
                "validation_metrics": {
                    "average_precision": 0.744424,
                    "precision": 0.95,
                    "recall": 0.655172,
                    "false_alerts_per_day": 1.263158,
                },
                "test_metrics": {
                    "average_precision": 0.685447,
                    "brier_score": 0.036326,
                    "precision": 0.852941,
                    "recall": 0.568627,
                    "f1": 0.682353,
                    "true_positives": 29,
                    "false_positives": 5,
                    "false_negatives": 22,
                    "predicted_alerts": 34,
                    "false_alerts_per_day": 4.8,
                },
                "pending_predictions": [
                    {
                        "region_code": "UNKNOWN",
                        "window_start": "2026-08-20T19:00:00",
                        "model_score": 0.948838,
                        "clears_alert_threshold": False,
                    }
                ],
                "guardrails": [
                    "This model forecasts news-domain spread, not physical disaster severity."
                ],
            }
        ),
        encoding="utf-8",
    )
    title_cache_path = tmp_path / "publisher-title-cache.json"
    title_cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "https://one.test/flood-report": {
                        "status": "ok",
                        "title": "Flooding closes roads across the county",
                        "fetched_at": "2099-01-01T00:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_dashboard_snapshot(
        clean_path,
        feature_path,
        anomaly_path,
        report_path,
        outcome_report_path=outcome_report_path,
        model_report_path=model_report_path,
        title_cache_path=title_cache_path,
    )

    assert snapshot["snapshot"]["clean_articles"] == 9
    assert snapshot["snapshot"]["story_groups"] == 5
    assert snapshot["snapshot"]["candidates"] == 1
    assert snapshot["signals"][0]["code"] == "UNKNOWN"
    assert snapshot["signals"][0]["status_label"] == "Candidate"
    assert [story["story_id"] for story in snapshot["latest_coverage"]] == ["g1"]
    assert snapshot["latest_coverage"][0]["title"] == (
        "Flooding closes roads across the county"
    )
    assert [
        source["domain"] for source in snapshot["latest_coverage"][0]["sources"]
    ] == ["one.test", "two.test"]
    assert len(snapshot["signals"][0]["evidence"]) == 1
    assert [
        source["domain"] for source in snapshot["signals"][0]["evidence"][0]["sources"]
    ] == ["one.test", "two.test"]
    assert snapshot["status_counts"]["insufficient_history"] == 0
    assert snapshot["forecast"]["eligible_windows"] == 100
    assert snapshot["forecast"]["positive_outcomes"] == 7
    assert snapshot["forecast"]["pending_predictions"][0]["region_code"] == "UNKNOWN"
    model = snapshot["forecast"]["model"]
    assert model["status"] == "ready"
    assert model["test_rows"] == 10025
    assert model["test_metrics"]["average_precision"] == 0.685447
    assert model["pending_predictions"][0]["model_score"] == 0.948838
    assert model["scores_are_calibrated_probabilities"] is False


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
            "title": "Hawaii flooding closes coastal roads",
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
    assert snapshot["signals"][0]["evidence"][0]["title"] == (
        "Hawaii flooding closes coastal roads"
    )
    assert snapshot["latest_coverage"] == []
