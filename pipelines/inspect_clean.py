"""Build a compact quality report for a CrisisPulse clean Parquet file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl


def _flag_count(frame: pl.DataFrame, flag: str) -> int:
    if frame.is_empty():
        return 0
    return int(frame.select(pl.col("quality_flags").list.contains(flag).sum()).item())


def build_report(parquet_path: Path, top: int = 10) -> dict[str, object]:
    frame = pl.read_parquet(parquet_path)
    location_status_counts = (
        frame.group_by("location_selection_status")
        .len(name="article_count")
        .sort("location_selection_status")
        .to_dicts()
        if "location_selection_status" in frame.columns
        else []
    )
    top_locations = (
        frame.with_columns(
            pl.col("location_name").fill_null("Unknown"),
            pl.col("country_code").fill_null("Unknown"),
        )
        .group_by("location_name", "country_code")
        .agg(
            pl.len().alias("article_count"),
            pl.col("source_domain").n_unique().alias("unique_domain_count"),
        )
        .sort(["article_count", "unique_domain_count", "location_name"], descending=[True, True, False])
        .head(top)
        .to_dicts()
    )
    matching_themes = (
        frame.select("matched_disaster_themes")
        .explode("matched_disaster_themes", empty_as_null=True)
        .group_by("matched_disaster_themes")
        .len(name="article_count")
        .sort(["article_count", "matched_disaster_themes"], descending=[True, False])
        .to_dicts()
    )
    top_story_groups = (
        frame.filter(pl.col("duplicate_group_size") > 1)
        .group_by("duplicate_group_id")
        .agg(
            pl.len().alias("article_count"),
            pl.col("source_domain").n_unique().alias("unique_domain_count"),
            pl.col("canonical_url").first().alias("example_url"),
            pl.col("location_name").first(),
            pl.col("duplicate_group_method").first().alias("method"),
        )
        .sort(["article_count", "unique_domain_count"], descending=True)
        .head(top)
        .to_dicts()
    )

    return {
        "input": str(parquet_path),
        "row_count": frame.height,
        "unique_domain_count": frame["source_domain"].drop_nulls().n_unique(),
        "unique_country_count": frame["country_code"].drop_nulls().n_unique(),
        "estimated_unique_story_count": frame["duplicate_group_id"].n_unique(),
        "syndicated_article_count": int(
            frame.select((pl.col("duplicate_group_size") > 1).sum()).item()
        ),
        "missing_location_count": int(frame["location_name"].null_count()),
        "invalid_coordinate_count": _flag_count(frame, "invalid_coordinates"),
        "multiple_location_count": _flag_count(frame, "multiple_locations"),
        "ambiguous_region_count": _flag_count(frame, "ambiguous_region"),
        "location_review_count": sum(
            item["article_count"]
            for item in location_status_counts
            if item["location_selection_status"]
            in {"missing", "ambiguous_region", "unresolved_region"}
        ),
        "location_selection_statuses": location_status_counts,
        "top_locations": top_locations,
        "matching_themes": matching_themes,
        "top_story_groups": top_story_groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="clean Parquet input")
    parser.add_argument("--top", type=int, default=10, help="number of top locations")
    parser.add_argument("--output", type=Path, help="optional JSON report destination")
    args = parser.parse_args()

    report = build_report(args.input, max(args.top, 1))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
