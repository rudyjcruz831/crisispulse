from datetime import datetime
from pathlib import Path

import polars as pl

from pipelines.merge_feature_history import merge_feature_history


def _write_features(path: Path, rows: list[tuple[datetime, str, int]]) -> None:
    pl.DataFrame(
        {
            "window_start": [row[0] for row in rows],
            "region_id": [row[1] for row in rows],
            "disaster_type": ["flood"] * len(rows),
            "estimated_unique_story_count": [row[2] for row in rows],
        }
    ).write_parquet(path)


def test_merge_creates_history_and_replaces_overlapping_keys(tmp_path: Path) -> None:
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    history_path = tmp_path / "history.parquet"
    first_hour = datetime(2026, 8, 20, 12)
    second_hour = datetime(2026, 8, 20, 13)
    _write_features(first_path, [(first_hour, "US:USHI", 2)])
    _write_features(
        second_path,
        [(first_hour, "US:USHI", 5), (second_hour, "US:USHI", 3)],
    )

    first = merge_feature_history(first_path, history_path)
    second = merge_feature_history(second_path, history_path)
    history = pl.read_parquet(history_path).sort("window_start")

    assert first.existing_rows == 0
    assert first.history_rows == 1
    assert second.existing_rows == 1
    assert second.replaced_rows == 1
    assert second.history_rows == 2
    assert history["estimated_unique_story_count"].to_list() == [5, 3]
    assert not list(tmp_path.glob("*.partial"))
