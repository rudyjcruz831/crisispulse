import json
from datetime import datetime, timedelta

import polars as pl

from pipelines.train_media_spread import FEATURE_NAMES, train_media_spread_model


def test_media_spread_model_uses_embargoed_chronological_splits(tmp_path):
    input_path = tmp_path / "outcomes.parquet"
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    start = datetime(2026, 1, 1)
    rows = []
    for hour in range(96):
        for region_index in range(4):
            positive = region_index == 0
            complete = hour < 90
            articles = 18 if positive else 2 + region_index
            domains = 15 if positive else 1 + region_index
            rows.append(
                {
                    "window_start": start + timedelta(hours=hour),
                    "region_id": f"TEST:{region_index}",
                    "disaster_type": "flood",
                    "observed_feature_row": True,
                    "article_count": articles,
                    "estimated_unique_story_count": articles,
                    "high_confidence_story_count": articles,
                    "unique_domain_count": domains,
                    "baseline_median": 1.0,
                    "baseline_mad": 1.0,
                    "robust_z_score": float(domains),
                    "is_candidate_anomaly": hour >= 90 and region_index == 0,
                    "outcome_complete": complete,
                    "label_media_spread_6h": positive if complete else None,
                }
            )
    pl.DataFrame(rows).write_parquet(input_path)

    stats = train_media_spread_model(input_path, model_path, report_path)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert stats.training_rows > stats.validation_rows > 0
    assert stats.test_rows > 0
    assert stats.pending_predictions_scored == 6
    assert model["features"] == list(FEATURE_NAMES)
    assert len(model["coefficients"]) == len(FEATURE_NAMES)
    assert 0.0 < model["threshold"] <= 1.0
    assert report["splits"]["embargo_hours"] == 6
    assert (
        report["splits"]["training"]["prediction_end"]
        < report["splits"]["validation"]["prediction_start"]
        < report["splits"]["test"]["prediction_start"]
    )
    assert report["test_metrics"]["average_precision"] > 0.9
    assert report["model"]["scores_are_calibrated_probabilities"] is False
    assert "probability" not in report["pending_predictions"][0]
    assert 0.0 <= report["pending_predictions"][0]["model_score"] <= 1.0
    assert isinstance(
        report["pending_predictions"][0]["clears_alert_threshold"], bool
    )


def test_media_spread_model_is_safely_unavailable_with_short_history(tmp_path):
    input_path = tmp_path / "short-outcomes.parquet"
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    rows = []
    start = datetime(2026, 1, 1)
    for hour in range(8):
        rows.append(
            {
                "window_start": start + timedelta(hours=hour),
                "region_id": "TEST:1",
                "disaster_type": "flood",
                "observed_feature_row": True,
                "article_count": 1,
                "estimated_unique_story_count": 1,
                "high_confidence_story_count": 1,
                "unique_domain_count": 1,
                "baseline_median": None,
                "baseline_mad": None,
                "robust_z_score": None,
                "is_candidate_anomaly": False,
                "outcome_complete": hour < 2,
                "label_media_spread_6h": False if hour < 2 else None,
            }
        )
    pl.DataFrame(rows).write_parquet(input_path)

    stats = train_media_spread_model(input_path, model_path, report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert stats.training_rows == 0
    assert report["status"] == "unavailable"
    assert "48 completed hourly windows" in report["reason"]
    assert report["model"]["decision_threshold"] is None
