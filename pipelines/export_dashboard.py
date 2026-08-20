"""Export the current CrisisPulse outputs as a small dashboard snapshot."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


STATUS_KEYS = (
    "insufficient_history",
    "below_minimum_support",
    "normal",
    "candidate_anomaly",
)

REGION_LABELS = {
    "UNKNOWN": "Unknown region",
    "US:USHI": "Hawaii, United States",
}


def _time_label(value: datetime) -> str:
    return f"{value:%b} {value.day}, {value:%H:%M} UTC"


def _window_label(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start:%b} {start.day}–{end.day}, {end.year}"
    return f"{start:%b} {start.day}, {start.year}–{end:%b} {end.day}, {end.year}"


def _rounded(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def build_dashboard_snapshot(
    clean_path: Path,
    feature_path: Path,
    anomaly_path: Path,
    anomaly_report_path: Path,
) -> dict[str, Any]:
    clean = pl.read_parquet(clean_path)
    features = pl.read_parquet(feature_path)
    anomalies = pl.read_parquet(anomaly_path)
    report = json.loads(anomaly_report_path.read_text(encoding="utf-8"))

    if features.is_empty() or anomalies.is_empty():
        raise ValueError("feature and anomaly outputs must not be empty")
    if "duplicate_group_id" not in clean.columns:
        raise ValueError("clean output must contain duplicate_group_id")

    window_start = features["window_start"].min()
    window_end = features["window_start"].max()
    if not isinstance(window_start, datetime) or not isinstance(window_end, datetime):
        raise ValueError("window_start must contain datetimes")

    status_counts = {key: 0 for key in STATUS_KEYS}
    for item in report.get("status_counts", []):
        key = item.get("anomaly_status")
        if key in status_counts:
            status_counts[key] = int(item.get("row_count", 0))
    status_counts["candidate_anomaly"] = int(report.get("candidate_anomalies", 0))

    candidate_rows = anomalies.filter(pl.col("is_candidate_anomaly"))
    if candidate_rows.height:
        signal_rows = candidate_rows.sort(
            ["robust_z_score", "window_start"], descending=[True, True]
        )
    else:
        normal_rows = anomalies.filter(pl.col("anomaly_status") == "normal")
        if normal_rows.height:
            latest_supported = normal_rows["window_start"].max()
            signal_rows = normal_rows.filter(
                pl.col("window_start") == latest_supported
            ).sort("robust_z_score", descending=True)
        else:
            signal_rows = normal_rows

    signals = []
    for row in signal_rows.head(8).to_dicts():
        region_id = str(row["region_id"])
        signals.append(
            {
                "region": REGION_LABELS.get(region_id, region_id),
                "code": region_id,
                "window_start": row["window_start"].isoformat(),
                "stories": int(row["high_confidence_story_count"]),
                "domains": int(row["unique_domain_count"]),
                "baseline": _rounded(row["baseline_median"]),
                "score": _rounded(row["robust_z_score"]),
                "status": str(row["anomaly_status"]),
                "status_label": (
                    "Candidate" if row["is_candidate_anomaly"] else "Normal"
                ),
            }
        )

    return {
        "snapshot": {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "window_label": _window_label(window_start, window_end),
            "updated_label": _time_label(window_end),
            "clean_articles": clean.height,
            "regions": int(report["regions"]),
            "hours": int(report["hourly_windows"]),
            "story_groups": int(clean["duplicate_group_id"].n_unique()),
            "candidates": int(report["candidate_anomalies"]),
            "scored_rows": int(report["scored_rows"]),
        },
        "parameters": report["parameters"],
        "status_counts": status_counts,
        "signals": signals,
    }


def write_dashboard_snapshot(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f"{output_path.name}.",
            suffix=".partial",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(snapshot, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--anomalies", type=Path, required=True)
    parser.add_argument("--anomaly-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    snapshot = build_dashboard_snapshot(
        args.clean, args.features, args.anomalies, args.anomaly_report
    )
    write_dashboard_snapshot(snapshot, args.output)
    print(json.dumps({"output": str(args.output), **snapshot["snapshot"]}, indent=2))


if __name__ == "__main__":
    main()
