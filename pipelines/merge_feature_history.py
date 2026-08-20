"""Merge a feature batch into compact, deduplicated regional/hourly history."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl


KEY_COLUMNS = ["window_start", "region_id", "disaster_type"]
PARTITION_COLUMNS = ["window_start", "disaster_type"]
VELOCITY_COLUMNS = {
    "estimated_unique_story_count",
    "unique_domain_count",
    "article_velocity",
    "domain_velocity",
}


@dataclass
class MergeStats:
    existing_rows: int
    input_rows: int
    replaced_rows: int
    history_rows: int
    hourly_windows: int
    regions: int


def merge_feature_history(input_path: Path, history_path: Path) -> MergeStats:
    current = pl.read_parquet(input_path)
    missing = set(KEY_COLUMNS).difference(current.columns)
    if missing:
        raise ValueError(f"feature dataset is missing columns: {sorted(missing)}")

    if history_path.exists():
        existing = pl.read_parquet(history_path)
        if set(existing.columns) != set(current.columns):
            raise ValueError("existing history schema does not match the feature batch")
        existing = existing.select(current.columns)
    else:
        existing = pl.DataFrame(schema=current.schema)

    observed_partitions = current.select(PARTITION_COLUMNS).unique()
    retained = existing.join(
        observed_partitions,
        on=PARTITION_COLUMNS,
        how="anti",
    )
    replaced_rows = existing.height - retained.height
    combined = pl.concat([retained, current], how="vertical_relaxed")
    history = combined.unique(subset=KEY_COLUMNS, keep="last").sort(KEY_COLUMNS)
    if VELOCITY_COLUMNS.issubset(history.columns):
        base = history.drop(
            "previous_story_count",
            "previous_domain_count",
            "article_velocity",
            "domain_velocity",
            strict=False,
        )
        previous = base.select(
            "region_id",
            "disaster_type",
            (pl.col("window_start") + pl.duration(hours=1)).alias("window_start"),
            pl.col("estimated_unique_story_count").alias("previous_story_count"),
            pl.col("unique_domain_count").alias("previous_domain_count"),
        )
        history = (
            base.join(
                previous,
                on=["region_id", "disaster_type", "window_start"],
                how="left",
            )
            .with_columns(
                (
                    pl.col("estimated_unique_story_count")
                    - pl.col("previous_story_count")
                ).alias("article_velocity"),
                (
                    pl.col("unique_domain_count") - pl.col("previous_domain_count")
                ).alias("domain_velocity"),
            )
            .select(current.columns)
            .sort(KEY_COLUMNS)
        )

    history_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=history_path.parent,
            prefix=f"{history_path.name}.",
            suffix=".partial",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        history.write_parquet(temporary_path, compression="zstd")
        os.replace(temporary_path, history_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return MergeStats(
        existing_rows=existing.height,
        input_rows=current.height,
        replaced_rows=replaced_rows,
        history_rows=history.height,
        hourly_windows=history["window_start"].n_unique() if history.height else 0,
        regions=history["region_id"].n_unique() if history.height else 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    args = parser.parse_args()
    stats = merge_feature_history(args.input, args.history)
    print(json.dumps({**asdict(stats), "history": str(args.history)}, indent=2))


if __name__ == "__main__":
    main()
