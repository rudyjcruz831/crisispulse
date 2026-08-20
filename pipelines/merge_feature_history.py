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

    combined = pl.concat([existing, current], how="vertical_relaxed")
    history = combined.unique(subset=KEY_COLUMNS, keep="last").sort(KEY_COLUMNS)
    replaced_rows = existing.height + current.height - history.height

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
