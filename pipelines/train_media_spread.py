"""Train and evaluate a chronological logistic model for six-hour media spread."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler


FEATURE_NAMES = (
    "log_article_count",
    "log_story_count",
    "log_domain_count",
    "syndication_ratio",
    "baseline_median",
    "baseline_mad",
    "robust_z_score",
    "hour_sin",
    "hour_cos",
    "observed_feature_row",
)

REQUIRED_COLUMNS = {
    "window_start",
    "region_id",
    "disaster_type",
    "observed_feature_row",
    "article_count",
    "estimated_unique_story_count",
    "high_confidence_story_count",
    "unique_domain_count",
    "baseline_median",
    "baseline_mad",
    "robust_z_score",
    "is_candidate_anomaly",
    "outcome_complete",
    "label_media_spread_6h",
}


@dataclass
class ModelStats:
    training_rows: int
    validation_rows: int
    test_rows: int
    training_positives: int
    validation_positives: int
    test_positives: int
    pending_predictions_scored: int


def _numeric(frame: pl.DataFrame, column: str) -> np.ndarray:
    return np.asarray(
        [0.0 if value is None else float(value) for value in frame[column]],
        dtype=np.float64,
    )


def _feature_matrix(frame: pl.DataFrame) -> np.ndarray:
    articles = _numeric(frame, "article_count")
    stories = _numeric(frame, "high_confidence_story_count")
    domains = _numeric(frame, "unique_domain_count")
    duplicate_adjusted = _numeric(frame, "estimated_unique_story_count")
    denominator = np.maximum(articles, 1.0)
    syndication_ratio = np.clip(1.0 - duplicate_adjusted / denominator, 0.0, 1.0)
    robust_z = np.clip(_numeric(frame, "robust_z_score"), -20.0, 20.0)
    hours = np.asarray([value.hour for value in frame["window_start"]], dtype=np.float64)
    hour_angle = 2.0 * math.pi * hours / 24.0
    observed = np.asarray(
        [1.0 if value else 0.0 for value in frame["observed_feature_row"]],
        dtype=np.float64,
    )
    return np.column_stack(
        [
            np.log1p(articles),
            np.log1p(stories),
            np.log1p(domains),
            syndication_ratio,
            _numeric(frame, "baseline_median"),
            _numeric(frame, "baseline_mad"),
            robust_z,
            np.sin(hour_angle),
            np.cos(hour_angle),
            observed,
        ]
    )


def _labels(frame: pl.DataFrame) -> np.ndarray:
    return np.asarray(frame["label_media_spread_6h"].to_list(), dtype=np.int64)


def _split_frame(
    eligible: pl.DataFrame, horizon_hours: int
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    hours = sorted(eligible["window_start"].unique().to_list())
    if len(hours) < max(48, horizon_hours * 4):
        raise ValueError("at least 48 completed hourly windows are required")
    validation_start_index = int(len(hours) * 0.70)
    test_start_index = int(len(hours) * 0.85)
    train_hours = hours[: max(1, validation_start_index - horizon_hours)]
    validation_hours = hours[
        validation_start_index : max(validation_start_index + 1, test_start_index - horizon_hours)
    ]
    test_hours = hours[test_start_index:]
    if not train_hours or not validation_hours or not test_hours:
        raise ValueError("chronological split is too short after the outcome embargo")

    train = eligible.filter(pl.col("window_start").is_in(train_hours))
    validation = eligible.filter(pl.col("window_start").is_in(validation_hours))
    test = eligible.filter(pl.col("window_start").is_in(test_hours))
    for name, split in (("training", train), ("validation", validation), ("test", test)):
        positives = int(split["label_media_spread_6h"].sum())
        if positives == 0 or positives == split.height:
            raise ValueError(f"{name} split must contain positive and negative outcomes")
    metadata = {
        "embargo_hours": horizon_hours,
        "training": {
            "prediction_start": train_hours[0].isoformat(),
            "prediction_end": train_hours[-1].isoformat(),
        },
        "validation": {
            "prediction_start": validation_hours[0].isoformat(),
            "prediction_end": validation_hours[-1].isoformat(),
        },
        "test": {
            "prediction_start": test_hours[0].isoformat(),
            "prediction_end": test_hours[-1].isoformat(),
        },
    }
    return train, validation, test, metadata


def _classification_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    prediction_hours: int,
) -> dict[str, float | int]:
    predicted = probabilities >= threshold
    true_positives = int(np.sum(predicted & (labels == 1)))
    false_positives = int(np.sum(predicted & (labels == 0)))
    false_negatives = int(np.sum(~predicted & (labels == 1)))
    days = max(prediction_hours / 24.0, 1.0 / 24.0)
    return {
        "average_precision": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "predicted_alerts": int(predicted.sum()),
        "false_alerts_per_day": float(false_positives / days),
    }


def _select_threshold(
    labels: np.ndarray,
    probabilities: np.ndarray,
    prediction_hours: int,
    maximum_false_alerts_per_day: float,
) -> tuple[float, dict[str, float | int]]:
    candidates = np.unique(
        np.concatenate(
            (
                np.linspace(0.05, 0.99, 95),
                np.linspace(0.9901, 0.9999, 99),
                np.asarray([1.0]),
            )
        )
    )
    scored = []
    for threshold in candidates:
        metrics = _classification_metrics(
            labels, probabilities, float(threshold), prediction_hours
        )
        if metrics["false_alerts_per_day"] <= maximum_false_alerts_per_day:
            scored.append((float(threshold), metrics))
    if not scored:
        threshold = 1.0
        return threshold, _classification_metrics(
            labels, probabilities, threshold, prediction_hours
        )
    return max(
        scored,
        key=lambda item: (
            item[1]["f1"],
            item[1]["recall"],
            item[1]["precision"],
            -item[0],
        ),
    )


def _rounded_metrics(metrics: dict[str, float | int]) -> dict[str, float | int]:
    return {
        key: round(value, 6) if isinstance(value, float) else value
        for key, value in metrics.items()
    }


def _write_unavailable_model(
    model_path: Path,
    report_path: Path,
    *,
    reason: str,
    horizon_hours: int,
) -> ModelStats:
    stats = ModelStats(0, 0, 0, 0, 0, 0, 0)
    model_artifact = {
        "model_type": "unavailable",
        "target": "media_spread_6h",
        "features": list(FEATURE_NAMES),
        "reason": reason,
    }
    report = {
        "status": "unavailable",
        "reason": reason,
        "target": {
            "name": "media_spread_6h",
            "horizon_hours": horizon_hours,
            "leakage_rule": "Features stop at prediction hour; labels use only hours 1–6.",
        },
        "model": {
            "type": "logistic_regression",
            "decision_threshold": None,
            "scores_are_calibrated_probabilities": False,
        },
        "splits": {},
        **asdict(stats),
        "validation_metrics": {},
        "test_metrics": {},
        "validation_hours": 0,
        "test_hours": 0,
        "pending_predictions": [],
        "guardrails": [
            "The model stays unavailable until enough corrected chronological history exists."
        ],
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps(model_artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return stats


def train_media_spread_model(
    input_path: Path,
    model_path: Path,
    report_path: Path,
    *,
    horizon_hours: int = 6,
    maximum_false_alerts_per_day: float = 5.0,
) -> ModelStats:
    if horizon_hours < 1:
        raise ValueError("model horizon must be at least one hour")
    if maximum_false_alerts_per_day <= 0:
        raise ValueError("false-alert budget must be positive")
    frame = pl.read_parquet(input_path).sort(
        ["window_start", "region_id", "disaster_type"]
    )
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"outcome dataset is missing columns: {sorted(missing)}")
    eligible = frame.filter(pl.col("outcome_complete"))
    try:
        train, validation, test, split_metadata = _split_frame(
            eligible, horizon_hours
        )
    except ValueError as error:
        return _write_unavailable_model(
            model_path,
            report_path,
            reason=str(error),
            horizon_hours=horizon_hours,
        )

    scaler = StandardScaler()
    train_matrix = scaler.fit_transform(_feature_matrix(train))
    validation_matrix = scaler.transform(_feature_matrix(validation))
    test_matrix = scaler.transform(_feature_matrix(test))
    train_labels = _labels(train)
    validation_labels = _labels(validation)
    test_labels = _labels(test)
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=2000,
        random_state=42,
        solver="lbfgs",
    )
    model.fit(train_matrix, train_labels)

    validation_probabilities = model.predict_proba(validation_matrix)[:, 1]
    validation_hours = validation["window_start"].n_unique()
    threshold, validation_metrics = _select_threshold(
        validation_labels,
        validation_probabilities,
        validation_hours,
        maximum_false_alerts_per_day,
    )
    test_probabilities = model.predict_proba(test_matrix)[:, 1]
    test_hours = test["window_start"].n_unique()
    test_metrics = _classification_metrics(
        test_labels, test_probabilities, threshold, test_hours
    )

    pending = frame.filter(
        pl.col("is_candidate_anomaly") & ~pl.col("outcome_complete")
    )
    pending_predictions = []
    if pending.height:
        probabilities = model.predict_proba(
            scaler.transform(_feature_matrix(pending))
        )[:, 1]
        for row, probability in zip(pending.to_dicts(), probabilities, strict=True):
            pending_predictions.append(
                {
                    "region_code": row["region_id"],
                    "window_start": row["window_start"].isoformat(),
                    "model_score": round(float(probability), 6),
                    "clears_alert_threshold": bool(probability >= threshold),
                }
            )

    stats = ModelStats(
        training_rows=train.height,
        validation_rows=validation.height,
        test_rows=test.height,
        training_positives=int(train_labels.sum()),
        validation_positives=int(validation_labels.sum()),
        test_positives=int(test_labels.sum()),
        pending_predictions_scored=len(pending_predictions),
    )
    latest_training_window = train["window_start"].max()
    model_artifact = {
        "model_type": "logistic_regression",
        "target": "media_spread_6h",
        "features": list(FEATURE_NAMES),
        "threshold": round(threshold, 6),
        "trained_through": (
            latest_training_window.isoformat()
            if isinstance(latest_training_window, datetime)
            else None
        ),
        "scaler_mean": [round(float(value), 12) for value in scaler.mean_],
        "scaler_scale": [round(float(value), 12) for value in scaler.scale_],
        "coefficients": [round(float(value), 12) for value in model.coef_[0]],
        "intercept": round(float(model.intercept_[0]), 12),
        "scikit_learn_version": sklearn.__version__,
    }
    report = {
        "input": str(input_path),
        "model_output": str(model_path),
        "target": {
            "name": "media_spread_6h",
            "horizon_hours": horizon_hours,
            "leakage_rule": "Features stop at prediction hour; labels use only hours 1–6.",
        },
        "model": {
            "type": "logistic_regression",
            "class_weight": "balanced",
            "decision_threshold": round(threshold, 6),
            "maximum_validation_false_alerts_per_day": maximum_false_alerts_per_day,
            "scores_are_calibrated_probabilities": False,
        },
        "splits": split_metadata,
        **asdict(stats),
        "validation_metrics": _rounded_metrics(validation_metrics),
        "test_metrics": _rounded_metrics(test_metrics),
        "validation_hours": validation_hours,
        "test_hours": test_hours,
        "pending_predictions": pending_predictions,
        "guardrails": [
            "This model forecasts news-domain spread, not physical disaster severity.",
            "Chronological splits include a six-hour embargo between datasets.",
            "Later test hours are not used to fit the model or select its alert threshold.",
            "Class-balanced logistic scores are ranking values, not calibrated probabilities.",
        ],
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        json.dumps(model_artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--horizon-hours", type=int, default=6)
    parser.add_argument("--maximum-false-alerts-per-day", type=float, default=5.0)
    args = parser.parse_args()
    stats = train_media_spread_model(
        args.input,
        args.model,
        args.report,
        horizon_hours=args.horizon_hours,
        maximum_false_alerts_per_day=args.maximum_false_alerts_per_day,
    )
    print(json.dumps({**asdict(stats), "model": str(args.model)}, indent=2))


if __name__ == "__main__":
    main()
