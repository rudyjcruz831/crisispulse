"""Summarize regional/hourly CrisisPulse features as readable JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl


DISPLAY_COLUMNS = [
    "window_start",
    "region_id",
    "disaster_type",
    "article_count",
    "high_confidence_article_count",
    "weak_article_count",
    "unique_domain_count",
    "estimated_unique_story_count",
    "location_confident_article_count",
    "location_review_article_count",
    "duplicate_ratio",
    "article_velocity",
]


def _display_rows(frame: pl.DataFrame) -> list[dict[str, object]]:
    if frame.is_empty():
        return []
    return (
        frame.select(DISPLAY_COLUMNS)
        .with_columns(pl.col("window_start").dt.strftime("%Y-%m-%dT%H:%M:%S"))
        .to_dicts()
    )


def build_feature_report(feature_path: Path, top: int = 10) -> dict[str, object]:
    frame = pl.read_parquet(feature_path)
    top_signals = frame.sort(
        [
            "high_confidence_story_count",
            "unique_domain_count",
            "estimated_unique_story_count",
        ],
        descending=True,
    ).head(top)
    rising = (
        frame.filter(pl.col("article_velocity") > 0)
        .sort(["article_velocity", "unique_domain_count"], descending=True)
        .head(top)
    )
    return {
        "input": str(feature_path),
        "feature_rows": frame.height,
        "hourly_windows": frame["window_start"].n_unique() if frame.height else 0,
        "regions": frame["region_id"].n_unique() if frame.height else 0,
        "top_signals": _display_rows(top_signals),
        "largest_positive_velocities": _display_rows(rising),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_feature_report(args.input, max(args.top, 1))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
