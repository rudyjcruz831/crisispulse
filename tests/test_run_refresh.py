from pathlib import Path

from pipelines.download_history import GKG_SUFFIX
from pipelines.run_refresh import (
    _prune_raw_files,
    _raw_storage_bytes,
    _select_processing_files,
)


def _touch_window(
    raw_dir: Path,
    timestamps: list[str],
    *,
    sizes: list[int] | None = None,
) -> list[Path]:
    paths = []
    for index, timestamp in enumerate(timestamps):
        path = raw_dir / f"{timestamp}{GKG_SUFFIX}"
        size = sizes[index] if sizes is not None else len(b"fixture")
        path.write_bytes(bytes([index % 256]) * size)
        paths.append(path)
    return paths


def test_processing_window_starts_at_first_complete_hour(tmp_path: Path) -> None:
    timestamps = [
        "20260820191500",
        "20260820193000",
        "20260820194500",
        "20260820200000",
        "20260820201500",
        "20260820203000",
        "20260820204500",
        "20260820210000",
    ]
    _touch_window(tmp_path, timestamps)

    selected = _select_processing_files(tmp_path, window_intervals=8)

    assert [path.name for path in selected] == [
        f"{timestamp}{GKG_SUFFIX}" for timestamp in timestamps[3:]
    ]


def test_raw_retention_keeps_newest_files_under_byte_budget(tmp_path: Path) -> None:
    timestamps = [
        "20260820190000",
        "20260820191500",
        "20260820193000",
        "20260820194500",
    ]
    _touch_window(tmp_path, timestamps, sizes=[6, 7, 8, 9])

    pruned = _prune_raw_files(
        tmp_path,
        retention_bytes=17,
        minimum_files=2,
    )

    assert pruned == 2
    assert _raw_storage_bytes(tmp_path) == 17
    assert sorted(path.name for path in tmp_path.glob(f"*{GKG_SUFFIX}")) == [
        f"{timestamp}{GKG_SUFFIX}" for timestamp in timestamps[-2:]
    ]


def test_raw_retention_never_removes_minimum_processing_window(
    tmp_path: Path,
) -> None:
    timestamps = [
        "20260820190000",
        "20260820191500",
        "20260820193000",
        "20260820194500",
    ]
    _touch_window(tmp_path, timestamps, sizes=[10, 10, 10, 10])

    pruned = _prune_raw_files(
        tmp_path,
        retention_bytes=5,
        minimum_files=2,
    )

    assert pruned == 2
    assert _raw_storage_bytes(tmp_path) == 20
    assert sorted(path.name for path in tmp_path.glob(f"*{GKG_SUFFIX}")) == [
        f"{timestamp}{GKG_SUFFIX}" for timestamp in timestamps[-2:]
    ]
