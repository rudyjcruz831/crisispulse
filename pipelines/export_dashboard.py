"""Export the current CrisisPulse outputs as a small dashboard snapshot."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

CONFIDENT_LOCATION_STATUSES = {"single_region", "dominant_region", "legacy"}
MAX_EVIDENCE_STORIES = 8
MAX_EVIDENCE_SOURCES = 8
MAX_EVIDENCE_THEMES = 8


def _time_label(value: datetime) -> str:
    return f"{value:%b} {value.day}, {value:%H:%M} UTC"


def _window_label(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start:%b} {start.day}–{end.day}, {end.year}"
    return f"{start:%b} {start.day}, {start.year}–{end:%b} {end.day}, {end.year}"


def _rounded(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _signal_id(region_id: str, window_start: str) -> str:
    return f"{region_id}|{window_start}"


def _safe_source(row: dict[str, Any]) -> dict[str, str] | None:
    url = str(row.get("canonical_url") or "").strip()
    if not url or len(url) > 2048:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    domain = parsed.hostname.strip().lower()
    if not domain or len(domain) > 255:
        return None
    return {"domain": domain, "url": url}


def _evidence_by_signal(
    clean_path: Path, wanted_signal_ids: set[str]
) -> dict[str, list[dict[str, Any]]]:
    clean = pl.read_parquet(clean_path)
    required_columns = {
        "seen_at",
        "country_code",
        "adm1_code",
        "location_selection_status",
        "canonical_url",
        "source_domain",
        "duplicate_group_id",
        "disaster_match_strength",
        "matched_disaster_themes",
        "location_name",
    }
    if required_columns.difference(clean.columns):
        return {}

    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in clean.select(sorted(required_columns)).iter_rows(named=True):
        seen_at = row.get("seen_at")
        if not isinstance(seen_at, datetime):
            continue
        if row.get("disaster_match_strength") != "high":
            continue
        location_status = str(row.get("location_selection_status") or "")
        if location_status in CONFIDENT_LOCATION_STATUSES and row.get("country_code"):
            region_id = str(row["country_code"])
            if row.get("adm1_code"):
                region_id = f"{region_id}:{row['adm1_code']}"
        else:
            region_id = "UNKNOWN"
        window_start = seen_at.replace(minute=0, second=0, microsecond=0).isoformat()
        signal_id = _signal_id(region_id, window_start)
        if signal_id not in wanted_signal_ids:
            continue

        source = _safe_source(row)
        if source is None:
            continue
        story_id = str(row.get("duplicate_group_id") or "").strip()
        if not story_id:
            continue
        story = grouped.setdefault(signal_id, {}).setdefault(
            story_id,
            {
                "story_id": story_id,
                "seen_at": seen_at.isoformat(),
                "locations": set(),
                "themes": set(),
                "sources": {},
            },
        )
        location_name = str(row.get("location_name") or "").strip()
        if location_name:
            story["locations"].add(location_name)
        for theme in row.get("matched_disaster_themes") or []:
            rendered_theme = str(theme).strip()
            if rendered_theme:
                story["themes"].add(rendered_theme)
        story["sources"][source["url"]] = source

    evidence: dict[str, list[dict[str, Any]]] = {}
    for signal_id, stories in grouped.items():
        rendered_stories = []
        for story in sorted(
            stories.values(), key=lambda item: (item["seen_at"], item["story_id"])
        )[:MAX_EVIDENCE_STORIES]:
            sources = sorted(
                story["sources"].values(),
                key=lambda item: (item["domain"], item["url"]),
            )[:MAX_EVIDENCE_SOURCES]
            if not sources:
                continue
            locations = sorted(story["locations"])
            rendered_stories.append(
                {
                    "story_id": story["story_id"],
                    "seen_at": story["seen_at"],
                    "location": locations[0] if locations else None,
                    "themes": sorted(story["themes"])[:MAX_EVIDENCE_THEMES],
                    "sources": sources,
                }
            )
        if rendered_stories:
            evidence[signal_id] = rendered_stories
    return evidence


def _previous_evidence(snapshot: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(snapshot, dict):
        return {}
    previous: dict[str, list[dict[str, Any]]] = {}
    for signal in snapshot.get("signals", []):
        if not isinstance(signal, dict) or not isinstance(signal.get("evidence"), list):
            continue
        code = signal.get("code")
        window_start = signal.get("window_start")
        if not isinstance(code, str) or not isinstance(window_start, str):
            continue
        rendered_stories = []
        for story in signal["evidence"][:MAX_EVIDENCE_STORIES]:
            if not isinstance(story, dict):
                continue
            story_id = str(story.get("story_id") or "").strip()
            seen_at = str(story.get("seen_at") or "").strip()
            if not story_id or len(story_id) > 128 or not seen_at or len(seen_at) > 40:
                continue
            raw_sources = story.get("sources")
            if not isinstance(raw_sources, list):
                continue
            sources = []
            for source_row in raw_sources[:MAX_EVIDENCE_SOURCES]:
                if not isinstance(source_row, dict):
                    continue
                source = _safe_source(
                    {
                        "canonical_url": source_row.get("url"),
                        "source_domain": source_row.get("domain"),
                    }
                )
                if source is not None:
                    sources.append(source)
            if not sources:
                continue
            raw_location = story.get("location")
            location = (
                str(raw_location).strip()[:255]
                if raw_location is not None and str(raw_location).strip()
                else None
            )
            raw_themes = story.get("themes")
            themes = [
                str(theme).strip()[:100]
                for theme in (
                    raw_themes[:MAX_EVIDENCE_THEMES]
                    if isinstance(raw_themes, list)
                    else []
                )
                if str(theme).strip()
            ]
            rendered_stories.append(
                {
                    "story_id": story_id,
                    "seen_at": seen_at,
                    "location": location,
                    "themes": themes,
                    "sources": sources,
                }
            )
        if rendered_stories:
            previous[_signal_id(code, window_start)] = rendered_stories
    return previous


def build_dashboard_snapshot(
    clean_path: Path,
    feature_path: Path,
    anomaly_path: Path,
    anomaly_report_path: Path,
    previous_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Keep accepting the clean path for compatibility with existing commands. Coverage
    # totals come from feature history so an incremental refresh cannot mix a two-hour
    # clean batch with the full accumulated reporting window.
    if not clean_path.exists():
        raise ValueError("clean output does not exist")
    features = pl.read_parquet(feature_path)
    anomalies = pl.read_parquet(anomaly_path)
    report = json.loads(anomaly_report_path.read_text(encoding="utf-8"))

    if features.is_empty() or anomalies.is_empty():
        raise ValueError("feature and anomaly outputs must not be empty")
    required_feature_columns = {"article_count", "estimated_unique_story_count"}
    missing_feature_columns = required_feature_columns.difference(features.columns)
    if missing_feature_columns:
        raise ValueError(
            f"feature output is missing columns: {sorted(missing_feature_columns)}"
        )

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

    selected_rows = signal_rows.head(8).to_dicts()
    wanted_signal_ids = {
        _signal_id(str(row["region_id"]), row["window_start"].isoformat())
        for row in selected_rows
    }
    current_evidence = _evidence_by_signal(clean_path, wanted_signal_ids)
    prior_evidence = _previous_evidence(previous_snapshot)

    signals = []
    for row in selected_rows:
        region_id = str(row["region_id"])
        rendered_window_start = row["window_start"].isoformat()
        signal_id = _signal_id(region_id, rendered_window_start)
        signals.append(
            {
                "region": REGION_LABELS.get(region_id, region_id),
                "code": region_id,
                "window_start": rendered_window_start,
                "stories": int(row["high_confidence_story_count"]),
                "domains": int(row["unique_domain_count"]),
                "baseline": _rounded(row["baseline_median"]),
                "score": _rounded(row["robust_z_score"]),
                "status": str(row["anomaly_status"]),
                "status_label": (
                    "Candidate" if row["is_candidate_anomaly"] else "Normal"
                ),
                "evidence": current_evidence.get(
                    signal_id, prior_evidence.get(signal_id, [])
                ),
            }
        )

    return {
        "snapshot": {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "window_label": _window_label(window_start, window_end),
            "updated_label": _time_label(window_end),
            "clean_articles": int(features["article_count"].sum()),
            "regions": int(report["regions"]),
            "hours": int(report["hourly_windows"]),
            "story_groups": int(features["estimated_unique_story_count"].sum()),
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

    previous_snapshot = None
    if args.output.exists():
        try:
            previous_snapshot = json.loads(args.output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous_snapshot = None
    snapshot = build_dashboard_snapshot(
        args.clean,
        args.features,
        args.anomalies,
        args.anomaly_report,
        previous_snapshot,
    )
    write_dashboard_snapshot(snapshot, args.output)
    print(json.dumps({"output": str(args.output), **snapshot["snapshot"]}, indent=2))


if __name__ == "__main__":
    main()
