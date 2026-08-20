"""Create a deterministic, human-labelable review CSV from clean GDELT rows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl


REVIEW_LOCATION_STATUSES = {"missing", "ambiguous_region", "unresolved_region"}
SOURCE_COLUMNS = [
    "article_id",
    "seen_at",
    "canonical_url",
    "source_domain",
    "disaster_type",
    "disaster_match_strength",
    "matched_disaster_themes",
    "location_name",
    "country_code",
    "adm1_code",
    "distinct_location_count",
    "location_selection_status",
    "location_candidate_regions",
    "quality_flags",
    "duplicate_group_size",
]
OUTPUT_COLUMNS = [
    "review_bucket",
    *SOURCE_COLUMNS,
    "label_disaster_relevance",
    "label_primary_region",
    "review_notes",
]
LIST_COLUMNS = {
    "matched_disaster_themes",
    "location_candidate_regions",
    "quality_flags",
}


@dataclass
class ReviewStats:
    input_rows: int
    review_rows: int
    high_strength_rows: int
    weak_strength_rows: int
    location_review_rows: int


def _bucket(row: dict[str, object]) -> str:
    strength = str(row["disaster_match_strength"])
    location_group = (
        "needs_location_review"
        if row["location_selection_status"] in REVIEW_LOCATION_STATUSES
        else "assigned_location"
    )
    return f"{strength}:{location_group}"


def _location_priority(row: dict[str, object]) -> int:
    return {
        "ambiguous_region": 0,
        "unresolved_region": 1,
        "missing": 2,
        "dominant_region": 3,
        "single_region": 4,
    }.get(str(row["location_selection_status"]), 5)


def _round_robin(rows: list[dict[str, object]], size: int) -> list[dict[str, object]]:
    buckets: dict[str, deque[dict[str, object]]] = defaultdict(deque)
    for row in sorted(
        rows, key=lambda item: (_location_priority(item), str(item["article_id"]))
    ):
        row["review_bucket"] = _bucket(row)
        buckets[row["review_bucket"]].append(row)

    selected: list[dict[str, object]] = []
    while len(selected) < size and any(buckets.values()):
        for bucket_name in sorted(buckets):
            if buckets[bucket_name] and len(selected) < size:
                selected.append(buckets[bucket_name].popleft())
    return selected


def build_review_set(
    input_path: Path, output_path: Path, size: int = 40
) -> ReviewStats:
    if size < 1:
        raise ValueError("review size must be at least 1")
    frame = pl.read_parquet(input_path)
    missing = set(SOURCE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"clean dataset is missing columns: {sorted(missing)}")

    selected = _round_robin(frame.select(SOURCE_COLUMNS).to_dicts(), min(size, frame.height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in selected:
            rendered = dict(row)
            for column in LIST_COLUMNS:
                rendered[column] = json.dumps(rendered[column] or [], ensure_ascii=False)
            rendered["seen_at"] = str(rendered["seen_at"] or "")
            rendered["label_disaster_relevance"] = ""
            rendered["label_primary_region"] = ""
            rendered["review_notes"] = ""
            writer.writerow(rendered)

    return ReviewStats(
        input_rows=frame.height,
        review_rows=len(selected),
        high_strength_rows=sum(
            row["disaster_match_strength"] == "high" for row in selected
        ),
        weak_strength_rows=sum(
            row["disaster_match_strength"] == "weak" for row in selected
        ),
        location_review_rows=sum(
            row["location_selection_status"] in REVIEW_LOCATION_STATUSES
            for row in selected
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=40)
    args = parser.parse_args()
    stats = build_review_set(args.input, args.output, args.size)
    print(json.dumps({**asdict(stats), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
