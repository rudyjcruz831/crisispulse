"""Run one cross-platform production refresh with locking and status output."""

from __future__ import annotations

import argparse
import json
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


def _write_status(
    status_path: Path,
    *,
    status: str,
    started_at: datetime,
    message: str,
    details: dict[str, object] | None = None,
    previous_success: str | None = None,
) -> None:
    finished_at = None if status == "running" else datetime.now(UTC).isoformat()
    payload = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "last_success_at": finished_at if status == "success" else previous_success,
        "message": message[:500],
        "details": details or {},
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
    try:
        value = json.loads(status_path.read_text(encoding="utf-8")).get(
            "last_success_at"
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


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
    source_urls = gkg_window_urls(latest_url, window_intervals)
    download_stats = download_window(
        source_urls,
        raw_dir,
        workers=workers,
        progress_every=0,
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
        "first_file": Path(urlparse(source_urls[0]).path).name,
        "last_file": Path(urlparse(source_urls[-1]).path).name,
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
        "new_archived_articles": article_archive_stats.new_rows,
        "updated_archived_articles": article_archive_stats.updated_rows,
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
        with _refresh_lock(args.status_path.with_suffix(".lock")):
            details = run_refresh(
                raw_dir=args.raw_dir,
                work_dir=args.work_dir,
                dashboard_output=args.dashboard_output,
                status_path=args.status_path,
                window_intervals=args.window_intervals,
                retention_bytes=args.retention_bytes,
                workers=args.workers,
                title_backfill_batch=args.title_backfill_batch,
            )
    except RefreshAlreadyRunning as error:
        print(json.dumps({"status": "skipped", "message": str(error)}))
        return
    except Exception as error:
        started_at = datetime.now(UTC)
        _write_status(
            args.status_path,
            status="failed",
            started_at=started_at,
            message=str(error),
            previous_success=_previous_success(args.status_path),
        )
        raise
    print(json.dumps({"status": "success", "details": details}, indent=2))


if __name__ == "__main__":
    main()
