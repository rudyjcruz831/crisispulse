"""Build duplicate-adjusted regional/hourly features from clean GDELT records."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl


REQUIRED_COLUMNS = {
    "seen_at",
    "country_code",
    "adm1_code",
    "disaster_type",
    "source_domain",
    "duplicate_group_id",
    "disaster_match_strength",
    "tone",
}
CONFIDENT_LOCATION_STATUSES = {"single_region", "dominant_region", "legacy"}
REVIEW_LOCATION_STATUSES = {"missing", "ambiguous_region", "unresolved_region"}


@dataclass
class FeatureStats:
    input_rows: int
    feature_rows: int
    hourly_windows: int
    regions: int


def build_features(input_path: Path, output_path: Path) -> FeatureStats:
    frame = pl.read_parquet(input_path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"clean dataset is missing columns: {sorted(missing)}")

    location_status = (
        pl.col("location_selection_status")
        if "location_selection_status" in frame.columns
        else pl.lit("legacy")
    )
    prepared = frame.filter(pl.col("seen_at").is_not_null()).with_columns(
        pl.col("seen_at").dt.truncate("1h").alias("window_start"),
        location_status.alias("_location_selection_status"),
    )
    location_is_confident = pl.col("_location_selection_status").is_in(
        CONFIDENT_LOCATION_STATUSES
    )
    prepared = prepared.with_columns(
        pl.when(location_is_confident)
        .then(pl.col("country_code"))
        .otherwise(None)
        .alias("_region_country_code"),
        pl.when(location_is_confident)
        .then(pl.col("adm1_code"))
        .otherwise(None)
        .alias("_region_adm1_code"),
    ).with_columns(
        pl.when(pl.col("_region_country_code").is_not_null())
        .then(
            pl.when(pl.col("_region_adm1_code").is_not_null())
            .then(
                pl.concat_str(
                    ["_region_country_code", "_region_adm1_code"], separator=":"
                )
            )
            .otherwise(pl.col("_region_country_code"))
        )
        .otherwise(pl.lit("UNKNOWN"))
        .alias("region_id")
    )
    features = (
        prepared.group_by(
            "window_start",
            "region_id",
            "_region_country_code",
            "_region_adm1_code",
            "disaster_type",
        )
        .agg(
            pl.len().cast(pl.Int64).alias("article_count"),
            (pl.col("disaster_match_strength") == "high")
            .sum()
            .cast(pl.Int64)
            .alias("high_confidence_article_count"),
            (pl.col("disaster_match_strength") == "weak")
            .sum()
            .cast(pl.Int64)
            .alias("weak_article_count"),
            pl.col("source_domain")
            .drop_nulls()
            .n_unique()
            .cast(pl.Int64)
            .alias("unique_domain_count"),
            pl.col("duplicate_group_id")
            .n_unique()
            .cast(pl.Int64)
            .alias("estimated_unique_story_count"),
            pl.col("duplicate_group_id")
            .filter(pl.col("disaster_match_strength") == "high")
            .n_unique()
            .cast(pl.Int64)
            .alias("high_confidence_story_count"),
            pl.col("tone").mean().alias("average_tone"),
            pl.col("_location_selection_status")
            .is_in(CONFIDENT_LOCATION_STATUSES)
            .sum()
            .cast(pl.Int64)
            .alias("location_confident_article_count"),
            pl.col("_location_selection_status")
            .is_in(REVIEW_LOCATION_STATUSES)
            .sum()
            .cast(pl.Int64)
            .alias("location_review_article_count"),
        )
        .rename(
            {
                "_region_country_code": "country_code",
                "_region_adm1_code": "adm1_code",
            }
        )
        .with_columns(
            (
                1
                - pl.col("estimated_unique_story_count").cast(pl.Float64)
                / pl.col("article_count")
            ).alias("duplicate_ratio")
        )
        .sort(["region_id", "disaster_type", "window_start"])
    )

    previous = features.select(
        "region_id",
        "disaster_type",
        (pl.col("window_start") + pl.duration(hours=1)).alias("window_start"),
        pl.col("estimated_unique_story_count").alias("previous_story_count"),
        pl.col("unique_domain_count").alias("previous_domain_count"),
    )
    features = (
        features.join(
            previous,
            on=["region_id", "disaster_type", "window_start"],
            how="left",
        )
        .with_columns(
            (
                pl.col("estimated_unique_story_count") - pl.col("previous_story_count")
            ).alias("article_velocity"),
            (pl.col("unique_domain_count") - pl.col("previous_domain_count")).alias(
                "domain_velocity"
            ),
        )
        .sort(["window_start", "region_id", "disaster_type"])
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.write_parquet(output_path, compression="zstd")
    return FeatureStats(
        input_rows=frame.height,
        feature_rows=features.height,
        hourly_windows=features["window_start"].n_unique() if features.height else 0,
        regions=features["region_id"].n_unique() if features.height else 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stats = build_features(args.input, args.output)
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
