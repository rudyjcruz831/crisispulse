import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import pipelines.run_refresh as refresh_module

from pipelines.download_history import GKG_SUFFIX
from pipelines.run_refresh import (
    MAX_RECENT_RUNS,
    _prune_raw_files,
    _raw_storage_bytes,
    _refresh_download_plan,
    _select_processing_files,
    _write_status,
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


def test_refresh_download_plan_recovers_a_shutdown_gap(
    tmp_path: Path,
) -> None:
    _touch_window(tmp_path, ["20260826070000"])
    latest_url = (
        "https://data.gdeltproject.org/gdeltv2/"
        f"20260826114500{GKG_SUFFIX}"
    )

    source_urls, catch_up_urls, metrics = _refresh_download_plan(
        tmp_path,
        latest_url,
        window_intervals=8,
    )

    assert len(source_urls) == 19
    assert len(catch_up_urls) == 11
    assert catch_up_urls[0].endswith(f"20260826071500{GKG_SUFFIX}")
    assert catch_up_urls[-1].endswith(f"20260826094500{GKG_SUFFIX}")
    assert source_urls[-1].endswith(f"20260826114500{GKG_SUFFIX}")
    assert metrics == {
        "catch_up_audited_intervals": 20,
        "catch_up_requested_files": 11,
        "catch_up_audit_capped": False,
        "automatic_catch_up": True,
    }


def test_refresh_download_plan_recovers_internal_holes_without_duplicates(
    tmp_path: Path,
) -> None:
    timestamps = [
        f"20260826{hour:02d}{minute:02d}00"
        for hour in range(7, 12)
        for minute in (0, 15, 30, 45)
        if (hour, minute) not in {(8, 15), (9, 30)}
    ]
    _touch_window(tmp_path, timestamps)
    latest_url = (
        "https://data.gdeltproject.org/gdeltv2/"
        f"20260826114500{GKG_SUFFIX}"
    )

    source_urls, catch_up_urls, metrics = _refresh_download_plan(
        tmp_path,
        latest_url,
        window_intervals=8,
    )

    assert len(source_urls) == 10
    assert [Path(urlparse(url).path).name for url in catch_up_urls] == [
        f"20260826081500{GKG_SUFFIX}",
        f"20260826093000{GKG_SUFFIX}",
    ]
    assert len({Path(urlparse(url).path).name for url in source_urls}) == 10
    assert metrics["catch_up_requested_files"] == 2
    assert metrics["automatic_catch_up"] is True


def test_refresh_download_plan_stays_normal_for_a_fresh_install(
    tmp_path: Path,
) -> None:
    latest_url = (
        "https://data.gdeltproject.org/gdeltv2/"
        f"20260826114500{GKG_SUFFIX}"
    )

    source_urls, catch_up_urls, metrics = _refresh_download_plan(
        tmp_path,
        latest_url,
        window_intervals=8,
    )

    assert len(source_urls) == 8
    assert catch_up_urls == []
    assert metrics == {
        "catch_up_audited_intervals": 0,
        "catch_up_requested_files": 0,
        "catch_up_audit_capped": False,
        "automatic_catch_up": False,
    }


def test_refresh_download_plan_caps_a_long_outage_at_seven_days(
    tmp_path: Path,
) -> None:
    _touch_window(tmp_path, ["20260815000000"])
    latest_url = (
        "https://data.gdeltproject.org/gdeltv2/"
        f"20260826114500{GKG_SUFFIX}"
    )

    source_urls, catch_up_urls, metrics = _refresh_download_plan(
        tmp_path,
        latest_url,
        window_intervals=8,
    )

    assert len(source_urls) == 7 * 24 * 4
    assert len(catch_up_urls) == (7 * 24 * 4) - 8
    assert metrics["catch_up_audit_capped"] is True
    assert len({Path(urlparse(url).path).name for url in source_urls}) == len(source_urls)


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


def _write_run(
    status_path: Path,
    started_at: datetime,
    *,
    status: str = "success",
    duration: timedelta = timedelta(minutes=1),
) -> None:
    _write_status(
        status_path,
        status="running",
        started_at=started_at,
        message="refresh started",
        observed_at=started_at,
    )
    _write_status(
        status_path,
        status=status,
        # Deliberately wrong for failed runs: the durable running record must win.
        started_at=started_at + timedelta(seconds=30),
        message=f"refresh {status}",
        observed_at=started_at + duration,
    )


def _status(status_path: Path) -> dict[str, object]:
    return json.loads(status_path.read_text(encoding="utf-8"))


def test_status_upgrade_seeds_one_terminal_run_and_preserves_details(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "refresh-status.json"
    finished_at = datetime(2026, 8, 24, 12, 1, tzinfo=UTC)
    status_path.write_text(
        json.dumps(
            {
                "status": "success",
                "started_at": (finished_at - timedelta(minutes=1)).isoformat(),
                "finished_at": finished_at.isoformat(),
                "last_success_at": finished_at.isoformat(),
                "message": "refresh completed",
                "details": {"processed_files": 5, "archived_articles": 100},
            }
        ),
        encoding="utf-8",
    )

    next_start = finished_at + timedelta(minutes=14)
    _write_status(
        status_path,
        status="running",
        started_at=next_start,
        message="refresh started",
        observed_at=next_start,
    )
    payload = _status(status_path)

    assert payload["schema_version"] == 3
    assert payload["details"] == {"processed_files": 5, "archived_articles": 100}
    assert len(payload["recent_runs"]) == 1
    assert payload["recent_runs"][0]["status"] == "success"
    assert payload["soak"]["status"] == "in_progress"
    assert payload["soak"]["successful_runs"] == 1
    assert payload["soak"]["observed_minutes"] == 0

    # Rewriting the same running state represents a prior interrupted process,
    # not another opportunity to seed the legacy terminal record.
    restarted_at = next_start + timedelta(minutes=5)
    _write_status(
        status_path,
        status="running",
        started_at=restarted_at,
        message="refresh restarted",
        observed_at=restarted_at,
    )
    restarted = _status(status_path)
    assert [run["status"] for run in restarted["recent_runs"]] == [
        "success",
        "interrupted",
    ]
    assert restarted["soak"]["interrupted_runs"] == 1
    assert restarted["soak"]["reset_count"] == 1
    assert restarted["soak"]["reset_reason"] == "interrupted_refresh"


def test_failed_status_uses_durable_start_and_preserves_prior_details(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "refresh-status.json"
    started_at = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
    _write_status(
        status_path,
        status="running",
        started_at=started_at,
        message="refresh started",
        details={"processed_files": 5},
        observed_at=started_at,
    )
    _write_status(
        status_path,
        status="failed",
        started_at=started_at + timedelta(minutes=10),
        message="private path must stay only in the current status",
        observed_at=started_at + timedelta(minutes=2),
    )
    payload = _status(status_path)

    assert payload["started_at"] == started_at.isoformat()
    assert payload["details"] == {"processed_files": 5}
    assert payload["recent_runs"][-1]["status"] == "failed"
    assert payload["recent_runs"][-1]["duration_seconds"] == 120
    assert payload["soak"]["status"] == "not_started"
    assert payload["soak"]["failed_runs"] == 1
    assert payload["soak"]["reset_count"] == 1
    assert payload["soak"]["reset_reason"] == "failed_refresh"


def test_status_sanitizes_an_unrecognized_reset_reason(tmp_path: Path) -> None:
    status_path = tmp_path / "refresh-status.json"
    started_at = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)
    status_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "success",
                "started_at": started_at.isoformat(),
                "finished_at": started_at.isoformat(),
                "last_success_at": started_at.isoformat(),
                "details": {},
                "soak": {"reset_reason": "C:\\private\\refresh-error.log"},
                "recent_runs": [],
            }
        ),
        encoding="utf-8",
    )

    next_start = started_at + timedelta(minutes=15)
    _write_status(
        status_path,
        status="running",
        started_at=next_start,
        message="refresh started",
        observed_at=next_start,
    )

    assert _status(status_path)["soak"]["reset_reason"] == "none"


def test_soak_passes_after_48_observed_hours_with_expected_coverage(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "refresh-status.json"
    first_start = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    for interval in range(193):
        _write_run(status_path, first_start + timedelta(minutes=15 * interval))

    payload = _status(status_path)
    soak = payload["soak"]
    assert soak["status"] == "passed"
    assert soak["observed_minutes"] == 48 * 60
    assert soak["remaining_minutes"] == 0
    assert soak["successful_runs"] == 193
    assert soak["expected_runs"] == 193
    assert soak["coverage_percent"] == 100.0
    assert soak["progress_percent"] == 100.0
    assert soak["completed_at"] == soak["last_observed_at"]


def test_soak_does_not_advance_during_a_long_running_or_sleep_gap(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "refresh-status.json"
    first_start = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    _write_run(status_path, first_start)
    much_later = first_start + timedelta(hours=40)
    _write_status(
        status_path,
        status="running",
        started_at=much_later,
        message="refresh started after sleep",
        observed_at=much_later,
    )

    payload = _status(status_path)
    assert payload["soak"]["observed_minutes"] == 0
    assert payload["soak"]["remaining_minutes"] == 48 * 60
    assert payload["soak"]["progress_percent"] == 0.0

    _write_status(
        status_path,
        status="success",
        started_at=much_later,
        message="refresh completed",
        observed_at=much_later + timedelta(minutes=1),
    )
    after_success = _status(status_path)["soak"]
    assert after_success["status"] == "in_progress"
    assert after_success["successful_runs"] == 1
    assert after_success["observed_minutes"] == 0
    assert after_success["missed_runs"] >= 1
    assert after_success["reset_count"] == 1
    assert after_success["reset_reason"] == "refresh_gap"


def test_soak_with_48_hours_but_low_coverage_does_not_pass(tmp_path: Path) -> None:
    status_path = tmp_path / "refresh-status.json"
    first_start = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    # Thirty-minute gaps do not reset the proof, but their missing cycles keep
    # coverage below the explicit 95% gate.
    for interval in range(97):
        _write_run(status_path, first_start + timedelta(minutes=30 * interval))

    soak = _status(status_path)["soak"]
    assert soak["observed_minutes"] == 48 * 60
    assert soak["status"] == "in_progress"
    assert soak["remaining_minutes"] == 0
    assert soak["successful_runs"] == 97
    assert soak["expected_runs"] == 193
    assert soak["coverage_percent"] < 95.0
    assert soak["missed_runs"] == 96


def test_duplicate_refreshes_cannot_hide_missed_intervals(tmp_path: Path) -> None:
    status_path = tmp_path / "refresh-status.json"
    first_start = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    for interval in range(97):
        slot_start = first_start + timedelta(minutes=30 * interval)
        _write_run(status_path, slot_start)
        _write_run(status_path, slot_start + timedelta(minutes=2))

    soak = _status(status_path)["soak"]
    assert soak["observed_minutes"] >= 48 * 60
    assert soak["status"] == "in_progress"
    assert soak["successful_runs"] == 97
    assert soak["expected_runs"] == 193
    assert soak["coverage_percent"] < 95.0
    assert soak["missed_runs"] == 96


def test_recent_run_evidence_is_capped_without_losing_total_counters(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "refresh-status.json"
    first_start = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    for interval in range(MAX_RECENT_RUNS + 8):
        _write_run(status_path, first_start + timedelta(minutes=15 * interval))

    failure_start = first_start + timedelta(
        minutes=15 * (MAX_RECENT_RUNS + 8)
    )
    _write_run(status_path, failure_start, status="failed")
    payload = _status(status_path)

    assert len(payload["recent_runs"]) == MAX_RECENT_RUNS
    assert payload["recent_runs"][-1]["status"] == "failed"
    assert payload["soak"]["failed_runs"] == 1
    assert payload["soak"]["reset_count"] == 1
    assert status_path.stat().st_size < 64 << 10


def test_failure_status_is_recorded_before_refresh_lock_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_owned = False
    events: list[str] = []

    @contextmanager
    def fake_lock(_path: Path):
        nonlocal lock_owned
        lock_owned = True
        events.append("lock acquired")
        try:
            yield
        finally:
            events.append("lock released")
            lock_owned = False

    def failing_refresh(**_kwargs: object) -> dict[str, object]:
        events.append("refresh failed")
        raise RuntimeError("fixture failure")

    def record_status(*_args: object, **kwargs: object) -> None:
        assert lock_owned
        assert kwargs["status"] == "failed"
        events.append("failure recorded")

    monkeypatch.setattr(refresh_module, "_refresh_lock", fake_lock)
    monkeypatch.setattr(refresh_module, "run_refresh", failing_refresh)
    monkeypatch.setattr(refresh_module, "_write_status", record_status)
    args = SimpleNamespace(
        raw_dir=tmp_path / "raw",
        work_dir=tmp_path / "work",
        dashboard_output=tmp_path / "dashboard.json",
        status_path=tmp_path / "refresh-status.json",
        window_intervals=8,
        retention_bytes=10_000,
        workers=1,
        title_backfill_batch=1,
    )

    with pytest.raises(RuntimeError, match="fixture failure"):
        refresh_module._run_refresh_with_lock(args)

    assert events == [
        "lock acquired",
        "refresh failed",
        "failure recorded",
        "lock released",
    ]
