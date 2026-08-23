"""Build leakage-safe six-hour media-spread outcomes from scored signal history."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl


REQUIRED_COLUMNS = {
    "window_start",
    "region_id",
    "disaster_type",
    "observed_feature_row",
    "article_count",
    "estimated_unique_story_count",
    "high_confidence_story_count",
    "unique_domain_count",
    "baseline_history_hours",
    "baseline_median",
    "baseline_mad",
    "robust_z_score",
    "anomaly_status",
    "is_candidate_anomaly",
}

OUTPUT_SCHEMA = {
    "window_start": pl.Datetime(time_unit="us"),
    "region_id": pl.String,
    "disaster_type": pl.String,
    "observed_feature_row": pl.Boolean,
    "article_count": pl.Int64,
    "estimated_unique_story_count": pl.Int64,
    "high_confidence_story_count": pl.Int64,
    "unique_domain_count": pl.Int64,
    "baseline_history_hours": pl.Int64,
    "baseline_median": pl.Float64,
    "baseline_mad": pl.Float64,
    "robust_z_score": pl.Float64,
    "anomaly_status": pl.String,
    "is_candidate_anomaly": pl.Boolean,
    "outcome_matures_at": pl.Datetime(time_unit="us"),
    "future_max_domain_count": pl.Int64,
    "label_media_spread_6h": pl.Boolean,
    "outcome_complete": pl.Boolean,
}


@dataclass
class OutcomeStats:
    input_rows: int
    outcome_rows: int
    eligible_rows: int
    pending_rows: int
    positive_outcomes: int
    evaluation_ready_rows: int
    evaluation_positive_outcomes: int
    candidate_predictions: int
    evaluated_candidate_predictions: int
    pending_candidate_predictions: int
    true_positives: int
    false_positives: int
    false_negatives: int


def build_outcomes(
    input_path: Path,
    output_path: Path,
    report_path: Path | None = None,
    *,
    horizon_hours: int = 6,
    domain_threshold: int = 20,
) -> OutcomeStats:
    if horizon_hours < 1:
        raise ValueError("outcome horizon must be at least one hour")
    if domain_threshold < 1:
        raise ValueError("domain threshold must be at least one")

    frame = pl.read_parquet(input_path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"scored dataset is missing columns: {sorted(missing)}")
    if frame.is_empty():
        outcomes = pl.DataFrame(schema=OUTPUT_SCHEMA)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        outcomes.write_parquet(output_path, compression="zstd")
        stats = OutcomeStats(*(0 for _ in range(13)))
        if report_path:
            _write_report(
                report_path,
                input_path,
                output_path,
                outcomes,
                stats,
                horizon_hours,
                domain_threshold,
            )
        return stats

    keys = ["region_id", "disaster_type", "window_start"]
    if frame.select(keys).unique().height != frame.height:
        raise ValueError("scored dataset contains duplicate region/disaster/hour rows")

    selected_columns = [
        "window_start",
        "region_id",
        "disaster_type",
        "observed_feature_row",
        "article_count",
        "estimated_unique_story_count",
        "high_confidence_story_count",
        "unique_domain_count",
        "baseline_history_hours",
        "baseline_median",
        "baseline_mad",
        "robust_z_score",
        "anomaly_status",
        "is_candidate_anomaly",
    ]
    outcomes = frame.select(selected_columns)
    future_columns = []
    for offset in range(1, horizon_hours + 1):
        future_column = f"_future_domains_{offset}"
        future_columns.append(future_column)
        shifted = frame.select(
            "region_id",
            "disaster_type",
            (pl.col("window_start") - pl.duration(hours=offset)).alias("window_start"),
            pl.col("unique_domain_count").alias(future_column),
        )
        outcomes = outcomes.join(shifted, on=keys, how="left")

    complete = pl.all_horizontal(
        [pl.col(column).is_not_null() for column in future_columns]
    )
    outcomes = (
        outcomes.with_columns(
            (pl.col("window_start") + pl.duration(hours=horizon_hours)).alias(
                "outcome_matures_at"
            ),
            complete.alias("outcome_complete"),
        )
        .with_columns(
            pl.when(pl.col("outcome_complete"))
            .then(pl.max_horizontal(future_columns))
            .otherwise(None)
            .cast(pl.Int64)
            .alias("future_max_domain_count")
        )
        .with_columns(
            pl.when(pl.col("outcome_complete"))
            .then(pl.col("future_max_domain_count") >= domain_threshold)
            .otherwise(None)
            .cast(pl.Boolean)
            .alias("label_media_spread_6h")
        )
        .select(*OUTPUT_SCHEMA)
        .sort(keys)
    )

    eligible = outcomes.filter(pl.col("outcome_complete"))
    evaluation_ready = eligible.filter(
        pl.col("anomaly_status") != "insufficient_history"
    )
    evaluated_candidates = evaluation_ready.filter(pl.col("is_candidate_anomaly"))
    positives = eligible.filter(pl.col("label_media_spread_6h"))
    evaluation_positives = evaluation_ready.filter(pl.col("label_media_spread_6h"))
    stats = OutcomeStats(
        input_rows=frame.height,
        outcome_rows=outcomes.height,
        eligible_rows=eligible.height,
        pending_rows=outcomes.height - eligible.height,
        positive_outcomes=positives.height,
        evaluation_ready_rows=evaluation_ready.height,
        evaluation_positive_outcomes=evaluation_positives.height,
        candidate_predictions=int(outcomes["is_candidate_anomaly"].sum()),
        evaluated_candidate_predictions=evaluated_candidates.height,
        pending_candidate_predictions=outcomes.filter(
            pl.col("is_candidate_anomaly") & ~pl.col("outcome_complete")
        ).height,
        true_positives=evaluated_candidates.filter(
            pl.col("label_media_spread_6h")
        ).height,
        false_positives=evaluated_candidates.filter(
            ~pl.col("label_media_spread_6h")
        ).height,
        false_negatives=evaluation_ready.filter(
            ~pl.col("is_candidate_anomaly") & pl.col("label_media_spread_6h")
        ).height,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    outcomes.write_parquet(output_path, compression="zstd")
    if report_path:
        _write_report(
            report_path,
            input_path,
            output_path,
            outcomes,
            stats,
            horizon_hours,
            domain_threshold,
        )
    return stats


def _write_report(
    report_path: Path,
    input_path: Path,
    output_path: Path,
    outcomes: pl.DataFrame,
    stats: OutcomeStats,
    horizon_hours: int,
    domain_threshold: int,
) -> None:
    precision = (
        stats.true_positives / stats.evaluated_candidate_predictions
        if stats.evaluated_candidate_predictions
        else None
    )
    recall = (
        stats.true_positives / stats.evaluation_positive_outcomes
        if stats.evaluation_positive_outcomes
        else None
    )
    latest_window = outcomes["window_start"].max() if outcomes.height else None
    pending = []
    if isinstance(latest_window, datetime):
        for row in (
            outcomes.filter(
                pl.col("is_candidate_anomaly") & ~pl.col("outcome_complete")
            )
            .sort("window_start", descending=True)
            .select(
                "region_id",
                "window_start",
                "outcome_matures_at",
                "high_confidence_story_count",
                "unique_domain_count",
            )
            .to_dicts()
        ):
            matures_at = row["outcome_matures_at"]
            remaining = max(
                0,
                int((matures_at - latest_window).total_seconds() // 3600),
            )
            pending.append(
                {
                    "region_code": row["region_id"],
                    "window_start": row["window_start"].isoformat(),
                    "matures_at": matures_at.isoformat(),
                    "hours_remaining": remaining,
                    "stories_at_detection": int(row["high_confidence_story_count"]),
                    "domains_at_detection": int(row["unique_domain_count"]),
                }
            )

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "target": {
            "name": "media_spread_6h",
            "horizon_hours": horizon_hours,
            "domain_threshold": domain_threshold,
            "definition": (
                f"At least {domain_threshold} independent source domains in any "
                f"single hour during the next {horizon_hours} completed hours."
            ),
        },
        **asdict(stats),
        "precision": precision,
        "recall": recall,
        "latest_window": latest_window.isoformat() if isinstance(latest_window, datetime) else None,
        "pending_predictions": pending,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--horizon-hours", type=int, default=6)
    parser.add_argument("--domain-threshold", type=int, default=20)
    args = parser.parse_args()
    stats = build_outcomes(
        args.input,
        args.output,
        args.report,
        horizon_hours=args.horizon_hours,
        domain_threshold=args.domain_threshold,
    )
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
