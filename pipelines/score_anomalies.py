"""Score regional signals with a conservative rolling median/MAD baseline."""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import polars as pl


REQUIRED_COLUMNS = {
    "window_start",
    "region_id",
    "country_code",
    "adm1_code",
    "disaster_type",
    "article_count",
    "estimated_unique_story_count",
    "high_confidence_story_count",
    "unique_domain_count",
}
OUTPUT_SCHEMA = {
    "window_start": pl.Datetime(time_unit="us"),
    "region_id": pl.String,
    "country_code": pl.String,
    "adm1_code": pl.String,
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
}


@dataclass
class AnomalyStats:
    input_feature_rows: int
    scored_rows: int
    observed_feature_rows: int
    hourly_windows: int
    regions: int
    candidate_anomalies: int
    insufficient_history_rows: int


def _hours(start: datetime, end: datetime) -> list[datetime]:
    count = int((end - start).total_seconds() // 3600)
    return [start + timedelta(hours=offset) for offset in range(count + 1)]


def _median_and_mad(values: list[int]) -> tuple[float, float]:
    center = float(median(values))
    deviation = float(median(abs(value - center) for value in values))
    return center, deviation


def _score_status(
    signal: int,
    domains: int,
    history_count: int,
    center: float | None,
    mad: float | None,
    robust_z: float | None,
    *,
    minimum_history_hours: int,
    z_threshold: float,
    minimum_stories: int,
    minimum_domains: int,
    minimum_story_increase: int,
) -> tuple[str, bool]:
    if history_count < minimum_history_hours:
        return "insufficient_history", False
    if signal < minimum_stories or domains < minimum_domains:
        return "below_minimum_support", False
    if center is None or signal - center < minimum_story_increase:
        return "normal", False
    if mad == 0:
        return "candidate_anomaly", True
    if robust_z is not None and robust_z >= z_threshold:
        return "candidate_anomaly", True
    return "normal", False


def score_anomalies(
    input_path: Path,
    output_path: Path,
    report_path: Path | None = None,
    *,
    lookback_hours: int = 720,
    minimum_history_hours: int = 168,
    z_threshold: float = 6.0,
    minimum_stories: int = 3,
    minimum_domains: int = 3,
    minimum_story_increase: int = 3,
) -> AnomalyStats:
    if minimum_history_hours < 1:
        raise ValueError("minimum history must be at least one hour")
    if lookback_hours < minimum_history_hours:
        raise ValueError("lookback hours must be at least the minimum history")
    if z_threshold <= 0:
        raise ValueError("z threshold must be positive")
    if min(minimum_stories, minimum_domains, minimum_story_increase) < 1:
        raise ValueError("minimum support values must be positive")

    frame = pl.read_parquet(input_path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"feature dataset is missing columns: {sorted(missing)}")
    if frame.is_empty():
        scored = pl.DataFrame(schema=OUTPUT_SCHEMA)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        scored.write_parquet(output_path, compression="zstd")
        stats = AnomalyStats(0, 0, 0, 0, 0, 0, 0)
        if report_path:
            _write_report(report_path, input_path, output_path, scored, stats, {})
        return stats

    start = frame["window_start"].min()
    end = frame["window_start"].max()
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("window_start must contain datetimes")
    timeline = _hours(start, end)
    groups = frame.select("region_id", "disaster_type").unique()
    records: list[dict[str, object]] = []

    for group in groups.iter_rows(named=True):
        group_frame = frame.filter(
            (pl.col("region_id") == group["region_id"])
            & (pl.col("disaster_type") == group["disaster_type"])
        )
        if group_frame["window_start"].n_unique() != group_frame.height:
            raise ValueError(
                "feature dataset contains duplicate region/disaster/hour rows"
            )
        if (
            group_frame["country_code"].n_unique() > 1
            or group_frame["adm1_code"].n_unique() > 1
        ):
            raise ValueError("region metadata changes within a feature series")
        country_code = group_frame["country_code"][0]
        adm1_code = group_frame["adm1_code"][0]
        observed = {
            row["window_start"]: row for row in group_frame.iter_rows(named=True)
        }
        history: deque[int] = deque(maxlen=lookback_hours)

        for window_start in timeline:
            current = observed.get(window_start)
            signal = int(current["high_confidence_story_count"]) if current else 0
            domains = int(current["unique_domain_count"]) if current else 0
            history_values = list(history)
            history_count = len(history_values)
            center: float | None = None
            mad: float | None = None
            robust_z: float | None = None
            if history_count >= minimum_history_hours:
                center, mad = _median_and_mad(history_values)
                if mad > 0:
                    robust_z = (signal - center) / (1.4826 * mad)
            status, is_candidate = _score_status(
                signal,
                domains,
                history_count,
                center,
                mad,
                robust_z,
                minimum_history_hours=minimum_history_hours,
                z_threshold=z_threshold,
                minimum_stories=minimum_stories,
                minimum_domains=minimum_domains,
                minimum_story_increase=minimum_story_increase,
            )
            records.append(
                {
                    "window_start": window_start,
                    "region_id": group["region_id"],
                    "country_code": country_code,
                    "adm1_code": adm1_code,
                    "disaster_type": group["disaster_type"],
                    "observed_feature_row": current is not None,
                    "article_count": int(current["article_count"]) if current else 0,
                    "estimated_unique_story_count": (
                        int(current["estimated_unique_story_count"]) if current else 0
                    ),
                    "high_confidence_story_count": signal,
                    "unique_domain_count": domains,
                    "baseline_history_hours": history_count,
                    "baseline_median": center,
                    "baseline_mad": mad,
                    "robust_z_score": robust_z,
                    "anomaly_status": status,
                    "is_candidate_anomaly": is_candidate,
                }
            )
            history.append(signal)

    scored = pl.from_dicts(records, schema=OUTPUT_SCHEMA, strict=False).sort(
        ["window_start", "region_id", "disaster_type"]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored.write_parquet(output_path, compression="zstd")
    stats = AnomalyStats(
        input_feature_rows=frame.height,
        scored_rows=scored.height,
        observed_feature_rows=int(scored["observed_feature_row"].sum()),
        hourly_windows=len(timeline),
        regions=scored["region_id"].n_unique(),
        candidate_anomalies=int(scored["is_candidate_anomaly"].sum()),
        insufficient_history_rows=int(
            scored.select((pl.col("anomaly_status") == "insufficient_history").sum()).item()
        ),
    )
    if report_path:
        parameters = {
            "lookback_hours": lookback_hours,
            "minimum_history_hours": minimum_history_hours,
            "z_threshold": z_threshold,
            "minimum_stories": minimum_stories,
            "minimum_domains": minimum_domains,
            "minimum_story_increase": minimum_story_increase,
        }
        _write_report(report_path, input_path, output_path, scored, stats, parameters)
    return stats


def _write_report(
    report_path: Path,
    input_path: Path,
    output_path: Path,
    scored: pl.DataFrame,
    stats: AnomalyStats,
    parameters: dict[str, int | float],
) -> None:
    status_counts = (
        scored.group_by("anomaly_status")
        .len(name="row_count")
        .sort("anomaly_status")
        .to_dicts()
        if scored.height
        else []
    )
    candidates = (
        scored.filter(pl.col("is_candidate_anomaly"))
        .sort(
            ["robust_z_score", "high_confidence_story_count", "unique_domain_count"],
            descending=True,
            nulls_last=True,
        )
        .head(20)
        .select(
            "window_start",
            "region_id",
            "disaster_type",
            "high_confidence_story_count",
            "unique_domain_count",
            "baseline_median",
            "baseline_mad",
            "robust_z_score",
        )
        .with_columns(pl.col("window_start").dt.strftime("%Y-%m-%dT%H:%M:%S"))
        .to_dicts()
        if scored.height
        else []
    )
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "parameters": parameters,
        **asdict(stats),
        "status_counts": status_counts,
        "top_candidate_anomalies": candidates,
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
    parser.add_argument("--lookback-hours", type=int, default=720)
    parser.add_argument("--minimum-history-hours", type=int, default=168)
    parser.add_argument("--z-threshold", type=float, default=6.0)
    parser.add_argument("--minimum-stories", type=int, default=3)
    parser.add_argument("--minimum-domains", type=int, default=3)
    parser.add_argument("--minimum-story-increase", type=int, default=3)
    args = parser.parse_args()

    stats = score_anomalies(
        args.input,
        args.output,
        args.report,
        lookback_hours=args.lookback_hours,
        minimum_history_hours=args.minimum_history_hours,
        z_threshold=args.z_threshold,
        minimum_stories=args.minimum_stories,
        minimum_domains=args.minimum_domains,
        minimum_story_increase=args.minimum_story_increase,
    )
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
