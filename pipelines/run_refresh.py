"""Run one cross-platform production refresh with locking and status output."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, TextIO
from urllib.parse import urlparse

from pipelines.backfill_article_titles import (
    DEFAULT_BATCH_SIZE as DEFAULT_TITLE_BACKFILL_BATCH,
    backfill_article_titles,
)
from pipelines.build_features import build_features
from pipelines.build_outcomes import build_outcomes
from pipelines.build_quality_sample import build_quality_sample
from pipelines.build_review_set import build_review_set
from pipelines.clean_gkg import clean_files
from pipelines.download_history import (
    GKG_SUFFIX,
    MAX_INTERVALS,
    download_window,
    gkg_window_urls,
    latest_available_gkg_url,
    latest_gkg_url,
)
from pipelines.export_dashboard import (
    build_dashboard_snapshot,
    write_dashboard_snapshot,
)
from pipelines.inspect_features import build_feature_report
from pipelines.merge_article_archive import merge_article_archive
from pipelines.merge_feature_history import merge_feature_history
from pipelines.score_anomalies import score_anomalies
from pipelines.train_media_spread import train_media_spread_model


DEFAULT_RAW_RETENTION_BYTES = 10_000_000_000
REFRESH_STATUS_VERSION = 3
MAX_RECENT_RUNS = 256
SOAK_TARGET_HOURS = 48
SOAK_INTERVAL_MINUTES = 15
SOAK_MAX_GAP_MINUTES = 30
SOAK_MINIMUM_COVERAGE_PERCENT = 95.0
TERMINAL_REFRESH_STATUSES = frozenset({"success", "failed", "interrupted"})
SOAK_RESET_REASONS = frozenset(
    {"none", "failed_refresh", "interrupted_refresh", "refresh_gap"}
)


class RefreshAlreadyRunning(RuntimeError):
    """Raised when another Linux production refresh owns the state lock."""


@contextmanager
def _refresh_lock(lock_path: Path) -> Iterator[TextIO]:
    """Acquire a non-blocking advisory lock (the production image runs on Linux)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+", encoding="utf-8")
    if os.name == "nt":
        stream.close()
        raise RuntimeError("production refresh locking requires Linux")
    import fcntl

    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        stream.close()
        raise RefreshAlreadyRunning("another refresh is already running") from error
    try:
        stream.seek(0)
        stream.truncate()
        stream.write(f"{os.getpid()}\n")
        stream.flush()
        yield stream
    finally:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_status_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _status_time(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _read_status(status_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _nonnegative_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _bounded_percent(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return round(min(100.0, max(0.0, number)), 2)


def _normalized_status_time(value: object) -> str:
    parsed = _parse_status_time(value)
    return _status_time(parsed) if parsed is not None else ""


def _empty_soak() -> dict[str, object]:
    return {
        "status": "not_started",
        "started_at": "",
        "last_observed_at": "",
        "completed_at": "",
        "target_hours": SOAK_TARGET_HOURS,
        "interval_minutes": SOAK_INTERVAL_MINUTES,
        "observed_minutes": 0,
        "remaining_minutes": SOAK_TARGET_HOURS * 60,
        "successful_runs": 0,
        "expected_runs": 0,
        "last_covered_slot": -1,
        "failed_runs": 0,
        "missed_runs": 0,
        "interrupted_runs": 0,
        "reset_count": 0,
        "coverage_percent": 0.0,
        "progress_percent": 0.0,
        "last_failure_at": "",
        "last_reset_at": "",
        "reset_reason": "none",
    }


def _sanitized_soak(value: object) -> dict[str, object]:
    soak = _empty_soak()
    if not isinstance(value, dict):
        return soak

    status = value.get("status")
    if status in {"not_started", "in_progress", "passed"}:
        soak["status"] = status
    for field in (
        "started_at",
        "last_observed_at",
        "completed_at",
        "last_failure_at",
        "last_reset_at",
    ):
        soak[field] = _normalized_status_time(value.get(field))
    for field in (
        "observed_minutes",
        "remaining_minutes",
        "successful_runs",
        "expected_runs",
        "failed_runs",
        "missed_runs",
        "interrupted_runs",
        "reset_count",
    ):
        soak[field] = _nonnegative_int(value.get(field), int(soak[field]))
    try:
        last_covered_slot = int(value.get("last_covered_slot", -1))
    except (TypeError, ValueError, OverflowError):
        last_covered_slot = -1
    soak["last_covered_slot"] = max(-1, last_covered_slot)
    soak["coverage_percent"] = _bounded_percent(value.get("coverage_percent"))
    soak["progress_percent"] = _bounded_percent(value.get("progress_percent"))
    reset_reason = value.get("reset_reason")
    if reset_reason in SOAK_RESET_REASONS:
        soak["reset_reason"] = reset_reason

    # These are policy constants, not caller-controlled status values.
    soak["target_hours"] = SOAK_TARGET_HOURS
    soak["interval_minutes"] = SOAK_INTERVAL_MINUTES
    return soak


def _sanitized_run(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or value.get("status") not in TERMINAL_REFRESH_STATUSES:
        return None
    started_at = _parse_status_time(value.get("started_at"))
    finished_at = _parse_status_time(value.get("finished_at"))
    if started_at is None or finished_at is None or finished_at < started_at:
        return None
    return {
        "status": value["status"],
        "started_at": _status_time(started_at),
        "finished_at": _status_time(finished_at),
        "duration_seconds": max(
            0, int((finished_at - started_at).total_seconds())
        ),
    }


def _recent_runs(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    sanitized = [run for item in value if (run := _sanitized_run(item))]
    return sanitized[-MAX_RECENT_RUNS:]


def _terminal_run(
    status: str,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, object]:
    normalized_start = _as_utc(started_at)
    normalized_finish = max(normalized_start, _as_utc(finished_at))
    return {
        "status": status,
        "started_at": _status_time(normalized_start),
        "finished_at": _status_time(normalized_finish),
        "duration_seconds": max(
            0, int((normalized_finish - normalized_start).total_seconds())
        ),
    }


def _legacy_terminal_run(payload: dict[str, object]) -> dict[str, object] | None:
    if payload.get("status") not in {"success", "failed"}:
        return None
    return _sanitized_run(
        {
            "status": payload.get("status"),
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
        }
    )


def _reset_active_soak(
    soak: dict[str, object],
    *,
    reset_at: datetime,
    reason: str,
) -> None:
    if reason not in SOAK_RESET_REASONS or reason == "none":
        raise ValueError("invalid soak reset reason")
    soak.update(
        {
            "status": "not_started",
            "started_at": "",
            "last_observed_at": _status_time(reset_at),
            "completed_at": "",
            "observed_minutes": 0,
            "remaining_minutes": SOAK_TARGET_HOURS * 60,
            "successful_runs": 0,
            "expected_runs": 0,
            "last_covered_slot": -1,
            "coverage_percent": 0.0,
            "progress_percent": 0.0,
            "reset_count": _nonnegative_int(soak.get("reset_count")) + 1,
            "last_reset_at": _status_time(reset_at),
            "reset_reason": reason,
        }
    )


def _advance_soak(
    soak_value: object,
    prior_runs: list[dict[str, object]],
    run: dict[str, object],
) -> dict[str, object]:
    soak = _sanitized_soak(soak_value)
    status = str(run["status"])
    started_at = _parse_status_time(run["started_at"])
    finished_at = _parse_status_time(run["finished_at"])
    if started_at is None or finished_at is None:
        return soak

    if status in {"failed", "interrupted"}:
        if status == "failed":
            soak["failed_runs"] = _nonnegative_int(soak.get("failed_runs")) + 1
            reset_reason = "failed_refresh"
        else:
            soak["interrupted_runs"] = (
                _nonnegative_int(soak.get("interrupted_runs")) + 1
            )
            reset_reason = "interrupted_refresh"
        soak["last_failure_at"] = _status_time(finished_at)
        _reset_active_soak(soak, reset_at=finished_at, reason=reset_reason)
        return soak

    previous_run = prior_runs[-1] if prior_runs else None
    gap_reset = False
    if previous_run is not None and previous_run.get("status") == "success":
        previous_finished = _parse_status_time(previous_run.get("finished_at"))
        if previous_finished is not None:
            gap_seconds = (finished_at - previous_finished).total_seconds()
            interval_seconds = SOAK_INTERVAL_MINUTES * 60
            if gap_seconds < 0 or gap_seconds > SOAK_MAX_GAP_MINUTES * 60:
                if gap_seconds > 0:
                    missed = max(0, int(gap_seconds // interval_seconds) - 1)
                    soak["missed_runs"] = (
                        _nonnegative_int(soak.get("missed_runs")) + missed
                    )
                _reset_active_soak(
                    soak,
                    reset_at=finished_at,
                    reason="refresh_gap",
                )
                gap_reset = True

    proof_started = _parse_status_time(soak.get("started_at"))
    if proof_started is None or gap_reset:
        proof_started = finished_at
        successful_runs = 1
        current_slot = 0
    else:
        observed_seconds = max(0.0, (finished_at - proof_started).total_seconds())
        interval_seconds = SOAK_INTERVAL_MINUTES * 60
        current_slot = int(observed_seconds // interval_seconds)
        previous_slot = max(-1, int(soak.get("last_covered_slot", -1)))
        successful_runs = min(
            _nonnegative_int(soak.get("successful_runs")),
            previous_slot + 1,
        )
        if current_slot > previous_slot:
            successful_runs += 1
            missed = max(0, current_slot - previous_slot - 1)
            soak["missed_runs"] = (
                _nonnegative_int(soak.get("missed_runs")) + missed
            )

    observed_seconds = max(0.0, (finished_at - proof_started).total_seconds())
    target_seconds = SOAK_TARGET_HOURS * 60 * 60
    expected_runs = int(observed_seconds // (SOAK_INTERVAL_MINUTES * 60)) + 1
    coverage_percent = min(100.0, successful_runs / expected_runs * 100.0)
    passed = (
        observed_seconds >= target_seconds
        and coverage_percent >= SOAK_MINIMUM_COVERAGE_PERCENT
    )
    previous_completed = _normalized_status_time(soak.get("completed_at"))
    soak.update(
        {
            "status": "passed" if passed else "in_progress",
            "started_at": _status_time(proof_started),
            "last_observed_at": _status_time(finished_at),
            "completed_at": (
                previous_completed
                if passed and previous_completed
                else _status_time(finished_at) if passed else ""
            ),
            "observed_minutes": int(observed_seconds // 60),
            "remaining_minutes": max(
                0, math.ceil((target_seconds - observed_seconds) / 60)
            ),
            "successful_runs": successful_runs,
            "expected_runs": expected_runs,
            "last_covered_slot": current_slot,
            "coverage_percent": round(coverage_percent, 2),
            "progress_percent": round(
                min(100.0, observed_seconds / target_seconds * 100.0), 2
            ),
        }
    )
    return soak


def _write_status(
    status_path: Path,
    *,
    status: str,
    started_at: datetime,
    message: str,
    details: dict[str, object] | None = None,
    previous_success: str | None = None,
    observed_at: datetime | None = None,
) -> None:
    if status not in {"running", "success", "failed"}:
        raise ValueError("invalid refresh status")

    observed = _as_utc(observed_at or datetime.now(UTC))
    previous = _read_status(status_path)
    upgrading = previous.get("schema_version") != REFRESH_STATUS_VERSION
    runs = [] if upgrading else _recent_runs(previous.get("recent_runs"))
    soak = _empty_soak() if upgrading else _sanitized_soak(previous.get("soak"))

    if upgrading:
        legacy_run = _legacy_terminal_run(previous)
        if legacy_run is not None:
            soak = _advance_soak(soak, runs, legacy_run)
            runs.append(legacy_run)

    normalized_start = _as_utc(started_at)
    prior_started_at = _parse_status_time(previous.get("started_at"))
    if status == "running" and previous.get("status") == "running":
        interrupted_start = prior_started_at or normalized_start
        interrupted = _terminal_run(
            "interrupted",
            interrupted_start,
            max(interrupted_start, normalized_start),
        )
        soak = _advance_soak(soak, runs, interrupted)
        runs.append(interrupted)

    terminal_finished: datetime | None = None
    if status in {"success", "failed"}:
        # A failure handler runs outside run_refresh. The current status is the
        # durable source of the real start time for the failed attempt.
        if previous.get("status") == "running" and prior_started_at is not None:
            normalized_start = prior_started_at
        terminal_finished = max(normalized_start, observed)
        terminal = _terminal_run(status, normalized_start, terminal_finished)
        soak = _advance_soak(soak, runs, terminal)
        runs.append(terminal)

    runs = runs[-MAX_RECENT_RUNS:]
    stored_previous_success = _normalized_status_time(
        previous.get("last_success_at")
    )
    fallback_previous_success = _normalized_status_time(previous_success)
    last_success_at = stored_previous_success or fallback_previous_success
    if status == "success" and terminal_finished is not None:
        last_success_at = _status_time(terminal_finished)

    prior_details = previous.get("details")
    if not isinstance(prior_details, dict):
        prior_details = {}
    payload = {
        "schema_version": REFRESH_STATUS_VERSION,
        "status": status,
        "started_at": _status_time(normalized_start),
        "finished_at": (
            _status_time(terminal_finished) if terminal_finished is not None else None
        ),
        "last_success_at": last_success_at,
        "message": message[:500],
        "details": details if details is not None else prior_details,
        "soak": soak,
        "recent_runs": runs,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=status_path.parent,
            prefix=f"{status_path.name}.",
            suffix=".partial",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
        os.replace(temporary_path, status_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _previous_success(status_path: Path) -> str | None:
    value = _read_status(status_path).get("last_success_at")
    normalized = _normalized_status_time(value)
    return normalized or None


def _select_processing_files(raw_dir: Path, window_intervals: int) -> list[Path]:
    available = sorted(raw_dir.glob(f"*{GKG_SUFFIX}"))
    selected = available[-window_intervals:]
    if len(selected) < window_intervals:
        raise ValueError(
            f"only {len(selected)} raw files are available; {window_intervals} are required"
        )
    for index, path in enumerate(selected):
        timestamp = datetime.strptime(path.name.removesuffix(GKG_SUFFIX), "%Y%m%d%H%M%S")
        if timestamp.minute == 0:
            return selected[index:]
    raise ValueError("the downloaded window does not contain an hour boundary")


def _raw_storage_bytes(raw_dir: Path) -> int:
    return sum(path.stat().st_size for path in raw_dir.glob(f"*{GKG_SUFFIX}"))


def _refresh_download_plan(
    raw_dir: Path,
    latest_url: str,
    window_intervals: int,
) -> tuple[list[str], list[str], dict[str, object]]:
    """Plan the normal window plus missing retained-history intervals.

    The normal processing window is always retained.  When local raw history
    exists, audit at most the latest seven days and add only absent intervals
    older than that normal window.  This repairs both a direct resume gap and
    older holes left by a refresh that ran before catch-up support existed.
    """
    normal_urls = gkg_window_urls(latest_url, window_intervals)
    remote_name = Path(urlparse(latest_url).path).name
    remote_timestamp = datetime.strptime(
        remote_name.removesuffix(GKG_SUFFIX), "%Y%m%d%H%M%S"
    )
    retained_names: set[str] = set()
    retained_timestamps: list[datetime] = []
    for path in raw_dir.glob(f"*{GKG_SUFFIX}"):
        try:
            timestamp = datetime.strptime(
                path.name.removesuffix(GKG_SUFFIX), "%Y%m%d%H%M%S"
            )
        except ValueError:
            continue
        if timestamp <= remote_timestamp:
            retained_names.add(path.name)
            retained_timestamps.append(timestamp)

    metrics: dict[str, object] = {
        "catch_up_audited_intervals": 0,
        "catch_up_requested_files": 0,
        "catch_up_audit_capped": False,
        "automatic_catch_up": False,
    }
    if not retained_timestamps:
        return normal_urls, [], metrics

    bounded_urls = gkg_window_urls(latest_url, MAX_INTERVALS)
    bounded_start_name = Path(urlparse(bounded_urls[0]).path).name
    bounded_start = datetime.strptime(
        bounded_start_name.removesuffix(GKG_SUFFIX), "%Y%m%d%H%M%S"
    )
    oldest_retained = min(retained_timestamps)
    audit_start = max(oldest_retained, bounded_start)
    audited_urls = [
        url
        for url in bounded_urls
        if datetime.strptime(
            Path(urlparse(url).path).name.removesuffix(GKG_SUFFIX),
            "%Y%m%d%H%M%S",
        )
        >= audit_start
    ]
    normal_names = {Path(urlparse(url).path).name for url in normal_urls}
    catch_up_urls = [
        url
        for url in audited_urls
        if (name := Path(urlparse(url).path).name) not in retained_names
        and name not in normal_names
    ]
    metrics.update(
        {
            "catch_up_audited_intervals": len(audited_urls),
            "catch_up_requested_files": len(catch_up_urls),
            "catch_up_audit_capped": oldest_retained < bounded_start,
            "automatic_catch_up": bool(catch_up_urls),
        }
    )
    return catch_up_urls + normal_urls, catch_up_urls, metrics


def _prune_raw_files(
    raw_dir: Path,
    retention_bytes: int,
    *,
    minimum_files: int = 1,
) -> int:
    """Remove oldest raw ZIPs until the archive fits the byte budget.

    The newest ``minimum_files`` are always preserved so a refresh cannot prune
    away its own processing window when a custom budget is unusually small.
    """
    if retention_bytes < 1:
        raise ValueError("retention bytes must be positive")
    if minimum_files < 1:
        raise ValueError("minimum files must be positive")

    available = sorted(raw_dir.glob(f"*{GKG_SUFFIX}"))
    retained_bytes = sum(path.stat().st_size for path in available)
    pruned = 0
    for path in available:
        if retained_bytes <= retention_bytes:
            break
        if len(available) - pruned <= minimum_files:
            break
        file_size = path.stat().st_size
        path.unlink()
        retained_bytes -= file_size
        pruned += 1
    return pruned


def run_refresh(
    *,
    raw_dir: Path,
    work_dir: Path,
    dashboard_output: Path,
    status_path: Path,
    window_intervals: int = 8,
    retention_bytes: int = DEFAULT_RAW_RETENTION_BYTES,
    workers: int = 8,
    title_backfill_batch: int = DEFAULT_TITLE_BACKFILL_BATCH,
) -> dict[str, object]:
    if retention_bytes < 1:
        raise ValueError("retention bytes must be positive")
    if title_backfill_batch < 1:
        raise ValueError("title backfill batch must be positive")
    started_at = datetime.now(UTC)
    previous_success = _previous_success(status_path)
    _write_status(
        status_path,
        status="running",
        started_at=started_at,
        message="refresh started",
        previous_success=previous_success,
    )

    clean_dir = work_dir / "clean"
    feature_dir = work_dir / "features"
    review_dir = work_dir / "review"
    history_dir = work_dir / "history"
    clean_path = clean_dir / "flood_articles_batch.parquet"
    article_archive_path = history_dir / "flood_articles_archive.parquet"
    quality_sample_path = dashboard_output.with_name("quality-review-sample.json")
    feature_path = feature_dir / "hourly_region_features.parquet"
    feature_report_path = feature_dir / "hourly_region_report.json"
    history_path = history_dir / "hourly_region_features.parquet"
    anomaly_path = feature_dir / "hourly_region_anomalies.parquet"
    anomaly_report_path = feature_dir / "hourly_region_anomaly_report.json"
    outcome_path = feature_dir / "six_hour_outcomes.parquet"
    outcome_report_path = feature_dir / "six_hour_outcome_report.json"
    model_path = feature_dir / "media_spread_logistic.json"
    model_report_path = feature_dir / "media_spread_model_report.json"

    advertised_url = latest_gkg_url(
        "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
    )
    latest_url = latest_available_gkg_url(advertised_url)
    source_urls, catch_up_urls, catch_up_metrics = _refresh_download_plan(
        raw_dir,
        latest_url,
        window_intervals,
    )
    download_stats = download_window(
        source_urls,
        raw_dir,
        workers=workers,
        progress_every=0,
    )
    catch_up_paths = [
        raw_dir / Path(urlparse(url).path).name for url in catch_up_urls
    ]
    catch_up_remaining = sum(not path.is_file() for path in catch_up_paths)
    catch_up_metrics.update(
        {
            "catch_up_recovered_files": len(catch_up_paths) - catch_up_remaining,
            "catch_up_remaining_files": catch_up_remaining,
        }
    )
    processing_files = _select_processing_files(raw_dir, window_intervals)
    clean_stats = clean_files(
        processing_files,
        clean_path,
        disaster_type="flood",
        minimum_strength="weak",
        title_cache_path=dashboard_output.with_name("publisher-title-cache.json"),
    )
    # Archival happens before any raw ZIP can be pruned. A failed merge or
    # verification aborts the refresh and leaves every retained raw file intact.
    catch_up_archive_stats = None
    if catch_up_paths:
        catch_up_clean_path = clean_dir / "flood_articles_catch_up.parquet"
        clean_files(
            catch_up_paths,
            catch_up_clean_path,
            disaster_type="flood",
            minimum_strength="weak",
            title_cache_path=dashboard_output.with_name(
                "publisher-title-cache.json"
            ),
        )
        catch_up_archive_stats = merge_article_archive(
            catch_up_clean_path,
            article_archive_path,
        )
    article_archive_stats = merge_article_archive(clean_path, article_archive_path)
    title_backfill_stats = backfill_article_titles(
        article_archive_path,
        dashboard_output.with_name("publisher-title-cache.json"),
        history_dir / "article-title-backfill-state.json",
        batch_size=title_backfill_batch,
    )
    quality_sample_stats = build_quality_sample(
        article_archive_path,
        quality_sample_path,
        title_cache_path=dashboard_output.with_name("publisher-title-cache.json"),
    )
    build_review_set(clean_path, review_dir / "flood_manual_review.csv", size=40)
    build_features(clean_path, feature_path)
    feature_report = build_feature_report(feature_path)
    feature_report_path.parent.mkdir(parents=True, exist_ok=True)
    feature_report_path.write_text(
        json.dumps(feature_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    history_stats = merge_feature_history(feature_path, history_path)
    anomaly_stats = score_anomalies(
        history_path, anomaly_path, anomaly_report_path
    )
    build_outcomes(anomaly_path, outcome_path, outcome_report_path)
    train_media_spread_model(
        outcome_path, model_path, model_report_path
    )

    previous_snapshot = None
    if dashboard_output.exists():
        try:
            previous_snapshot = json.loads(
                dashboard_output.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            previous_snapshot = None
    snapshot = build_dashboard_snapshot(
        clean_path,
        history_path,
        anomaly_path,
        anomaly_report_path,
        previous_snapshot,
        outcome_report_path,
        model_report_path,
        dashboard_output.with_name("publisher-title-cache.json"),
    )
    write_dashboard_snapshot(snapshot, dashboard_output)

    pruned = _prune_raw_files(
        raw_dir,
        retention_bytes,
        minimum_files=window_intervals,
    )
    retained = len(list(raw_dir.glob(f"*{GKG_SUFFIX}")))
    retained_bytes = _raw_storage_bytes(raw_dir)
    details = {
        **download_stats,
        **catch_up_metrics,
        "first_file": processing_files[0].name,
        "last_file": processing_files[-1].name,
        "processed_files": len(processing_files),
        "retained_raw_files": retained,
        "retained_raw_bytes": retained_bytes,
        "raw_storage_limit_bytes": retention_bytes,
        "raw_storage_used_percent": round(
            retained_bytes / retention_bytes * 100,
            2,
        ),
        "pruned_raw_files": pruned,
        "archived_articles": article_archive_stats.archive_rows,
        "new_archived_articles": article_archive_stats.new_rows
        + (catch_up_archive_stats.new_rows if catch_up_archive_stats else 0),
        "updated_archived_articles": article_archive_stats.updated_rows
        + (catch_up_archive_stats.updated_rows if catch_up_archive_stats else 0),
        "article_archive_bytes": title_backfill_stats.archive_bytes,
        "title_backfill_attempted_articles": title_backfill_stats.attempted_articles,
        "title_backfill_updated_articles": title_backfill_stats.updated_articles,
        "title_backfill_invalidated_titles": title_backfill_stats.invalidated_titles,
        "title_backfill_downgraded_articles": title_backfill_stats.downgraded_articles,
        "title_backfill_promoted_articles": title_backfill_stats.promoted_articles,
        "title_backfill_remaining_articles": title_backfill_stats.remaining_without_titles,
        "quality_sample_articles": quality_sample_stats.sample_articles,
        "quality_sample_date": quality_sample_stats.sample_date,
        "high_confidence_archived_articles": (
            title_backfill_stats.high_confidence_articles
        ),
        "weak_confidence_archived_articles": (
            title_backfill_stats.weak_confidence_articles
        ),
        "url_topic_mismatch_rows": clean_stats.url_topic_mismatch_rows,
        "publisher_title_checked_rows": clean_stats.publisher_title_checked_rows,
        "publisher_title_mismatch_rows": clean_stats.publisher_title_mismatch_rows,
        "history_hours": history_stats.hourly_windows,
        "candidate_anomalies": anomaly_stats.candidate_anomalies,
        "publisher_titles": sum(
            1 for story in snapshot["latest_coverage"] if story.get("title")
        ),
    }
    _write_status(
        status_path,
        status="success",
        started_at=started_at,
        message="refresh completed",
        details=details,
        previous_success=previous_success,
    )
    return details


def _run_refresh_with_lock(args: argparse.Namespace) -> dict[str, object]:
    with _refresh_lock(args.status_path.with_suffix(".lock")):
        try:
            return run_refresh(
                raw_dir=args.raw_dir,
                work_dir=args.work_dir,
                dashboard_output=args.dashboard_output,
                status_path=args.status_path,
                window_intervals=args.window_intervals,
                retention_bytes=args.retention_bytes,
                workers=args.workers,
                title_backfill_batch=args.title_backfill_batch,
            )
        except Exception as error:
            # The terminal status belongs to the same critical section as the
            # refresh. Otherwise a new run could start and have its running
            # status clobbered by this failure record.
            _write_status(
                args.status_path,
                status="failed",
                started_at=datetime.now(UTC),
                message=str(error),
                previous_success=_previous_success(args.status_path),
            )
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--dashboard-output", type=Path, required=True)
    parser.add_argument("--status-path", type=Path, required=True)
    parser.add_argument("--window-intervals", type=int, default=8)
    parser.add_argument(
        "--retention-bytes",
        type=int,
        default=DEFAULT_RAW_RETENTION_BYTES,
        help="maximum raw GDELT ZIP storage in bytes (default: 10 GB)",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--title-backfill-batch",
        type=int,
        default=DEFAULT_TITLE_BACKFILL_BATCH,
        help="maximum archived article titles checked per refresh",
    )
    args = parser.parse_args()
    try:
        details = _run_refresh_with_lock(args)
    except RefreshAlreadyRunning as error:
        print(json.dumps({"status": "skipped", "message": str(error)}))
        return
    print(json.dumps({"status": "success", "details": details}, indent=2))


if __name__ == "__main__":
    main()
