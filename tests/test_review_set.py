import csv
import json
from datetime import datetime
from pathlib import Path

import polars as pl

from pipelines.build_review_set import build_review_set


def test_review_set_balances_buckets_and_adds_blank_labels(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.parquet"
    review_path = tmp_path / "review.csv"
    pl.DataFrame(
        {
            "article_id": ["article-a", "article-b"],
            "seen_at": [datetime(2026, 8, 20, 12, 0)] * 2,
            "canonical_url": ["https://one.test/a", "https://two.test/b"],
            "source_domain": ["one.test", "two.test"],
            "disaster_type": ["flood", "flood"],
            "disaster_match_strength": ["high", "weak"],
            "matched_disaster_themes": [["FLOOD"], ["ENV_FLOOD"]],
            "location_name": ["Hawaii", "Big Island"],
            "country_code": ["US", "US"],
            "adm1_code": ["USHI", "USNH"],
            "distinct_location_count": [1, 2],
            "location_selection_status": ["single_region", "ambiguous_region"],
            "location_candidate_regions": [["US:USHI"], ["US:USHI", "US:USNH"]],
            "quality_flags": [[], ["multiple_locations", "ambiguous_region"]],
            "duplicate_group_size": [1, 2],
        }
    ).write_parquet(clean_path)

    stats = build_review_set(clean_path, review_path, size=2)
    with review_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert stats.review_rows == 2
    assert stats.high_strength_rows == 1
    assert stats.weak_strength_rows == 1
    assert stats.location_review_rows == 1
    assert {row["review_bucket"] for row in rows} == {
        "high:assigned_location",
        "weak:needs_location_review",
    }
    assert all(row["label_disaster_relevance"] == "" for row in rows)
    assert all(row["label_primary_region"] == "" for row in rows)
    ambiguous = next(row for row in rows if row["disaster_match_strength"] == "weak")
    assert json.loads(ambiguous["location_candidate_regions"]) == [
        "US:USHI",
        "US:USNH",
    ]
