from __future__ import annotations

import atexit
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "production" / "backup.sh"
RESTORE_SCRIPT = ROOT / "production" / "restore.sh"
MAINTENANCE_IMAGE = f"crisispulse-maintenance-test:{uuid.uuid4().hex[:12]}"
_maintenance_image_built = False


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _remove_maintenance_image() -> None:
    if not _maintenance_image_built:
        return
    subprocess.run(
        ["docker", "image", "rm", "--force", MAINTENANCE_IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


atexit.register(_remove_maintenance_image)


def _ensure_maintenance_image() -> None:
    global _maintenance_image_built
    if _maintenance_image_built:
        return
    if not _docker_available():
        pytest.skip("Docker is required for production script tests")
    result = subprocess.run(
        [
            "docker",
            "build",
            "--file",
            str(ROOT / "Dockerfile.maintenance"),
            "--tag",
            MAINTENANCE_IMAGE,
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    _maintenance_image_built = True


def _normalized_script(source: Path, destination: Path) -> Path:
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return destination


def _mount(source: Path, target: str, *, read_only: bool = False) -> str:
    suffix = ":ro" if read_only else ""
    return f"{source.resolve()}:{target}{suffix}"


def _run_alpine(
    script: Path,
    state: Path,
    work: Path,
    backups: Path,
    *,
    environment: dict[str, str] | None = None,
    network: str = "none",
) -> subprocess.CompletedProcess[str]:
    _ensure_maintenance_image()
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "--volume",
        _mount(state, "/state"),
        "--volume",
        _mount(work, "/work"),
        "--volume",
        _mount(backups, "/backups"),
        "--volume",
        _mount(script, "/opt/crisispulse/script.sh", read_only=True),
    ]
    for key, value in (environment or {}).items():
        command.extend(["--env", f"{key}={value}"])
    command.extend([MAINTENANCE_IMAGE, "/bin/sh", "/opt/crisispulse/script.sh"])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _hold_exclusive_refresh_lock(state: Path, seconds: int = 3) -> subprocess.Popen[str]:
    _ensure_maintenance_image()
    name = f"crisispulse-lock-test-{uuid.uuid4().hex[:12]}"
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--volume",
        _mount(state, "/state"),
        "alpine:3.23",
        "/bin/sh",
        "-c",
        f"exec 9<>/state/refresh-status.lock; flock -x 9; touch /state/lock-held; sleep {seconds}",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    marker = state / "lock-held"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if marker.exists():
            return process
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"lock holder failed: {stdout}\n{stderr}")
        time.sleep(0.05)
    process.terminate()
    raise AssertionError("lock holder did not acquire the refresh lock")


def _source_tree(root: Path) -> tuple[Path, Path, Path]:
    state = root / "state"
    work = root / "work"
    backups = root / "backups"
    (state / "raw").mkdir(parents=True)
    (work / "history").mkdir(parents=True)
    backups.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    (state / "dashboard.json").write_text(
        json.dumps(
            {
                "snapshot": {"updated_label": "Aug 24, 5:00 PM EDT"},
                "signals": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    refreshed_at = datetime.now(UTC).isoformat()
    (state / "refresh-status.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "status": "success",
                "started_at": refreshed_at,
                "finished_at": refreshed_at,
                "last_success_at": refreshed_at,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    window_start = "2026-08-24T21:00:00"
    reviewed_at = "2026-08-24T21:05:00Z"
    (state / "reviews.jsonl").write_text(
        json.dumps(
            {
                "signal_id": f"US:USNJ|{window_start}",
                "region_code": "US:USNJ",
                "window_start": window_start,
                "decision": "confirmed_event",
                "reviewed_at": reviewed_at,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (state / "article-reviews.jsonl").write_text(
        json.dumps(
            {
                "article_id": "a" * 64,
                "title": "Flooding closes a county road",
                "url": "https://example.test/flood",
                "source_domain": "example.test",
                "match_strength": "high",
                "review_bucket": "high_match",
                "decision": "relevant",
                "reviewed_at": reviewed_at,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (state / "raw" / "redownloadable.zip").write_bytes(b"raw")
    naive_now = datetime.now(UTC).replace(tzinfo=None)
    pl.DataFrame(
        {
            "window_start": [naive_now],
            "region_id": ["US:USNJ"],
            "article_count": [1],
            "estimated_unique_story_count": [1],
        }
    ).write_parquet(work / "history" / "hourly_region_features.parquet")
    pl.DataFrame(
        {
            "article_id": ["article-1"],
            "seen_at": [naive_now],
            "canonical_url": ["https://example.test/flood"],
            "source_domain": ["example.test"],
            "disaster_type": ["flood"],
        }
    ).write_parquet(work / "history" / "flood_articles_archive.parquet")
    return state, work, backups


def _create_verified_backup(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    state, work, backups = _source_tree(tmp_path)
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")
    result = _run_alpine(script, state, work, backups)
    assert result.returncode == 0, result.stderr
    archives = list(backups.glob("crisispulse-*.tar.gz"))
    assert len(archives) == 1
    assert archives[0].with_suffix(archives[0].suffix + ".sha256").is_file()
    return state, work, backups, archives[0]


def test_backup_is_verified_atomic_and_preserves_reviews(tmp_path: Path) -> None:
    state, _, backups, archive = _create_verified_backup(tmp_path)

    names: set[str]
    with tarfile.open(archive, "r:gz") as opened:
        names = set(opened.getnames())
    assert "state/reviews.jsonl" in names
    assert "state/article-reviews.jsonl" in names
    assert "state/raw" not in names
    assert "state/raw/redownloadable.zip" not in names
    assert "state/refresh-status.lock" not in names
    assert (state / "raw" / "redownloadable.zip").exists()

    status = json.loads((backups / "backup-status.json").read_text(encoding="utf-8"))
    assert set(status) == {
        "schema_version",
        "status",
        "application_data_verified",
        "verified_at",
        "archive_name",
        "archive_bytes",
        "checksum",
    }
    assert status["schema_version"] == 2
    assert status["status"] == "verified"
    assert status["application_data_verified"] is True
    assert status["archive_name"] == archive.name
    assert status["archive_bytes"] == archive.stat().st_size
    assert status["checksum"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert status["verified_at"].endswith("Z")
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    assert sidecar.read_text(encoding="utf-8") == f'{status["checksum"]}  {archive.name}\n'
    assert not list(backups.glob("*partial*"))


def test_backup_accepts_mixed_legacy_and_detailed_article_labels(
    tmp_path: Path,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    base_record = json.loads(
        (state / "article-reviews.jsonl").read_text(encoding="utf-8")
    )
    records: list[dict[str, object]] = []
    decisions = [
        (1, "relevant"),
        (1, "not_relevant"),
        (1, "uncertain"),
        (2, "reported_flooding"),
        (2, "flood_risk_warning"),
        (2, "heavy_rain_only"),
        (2, "not_flood_related"),
        (2, "uncertain"),
    ]
    for index, (version, decision) in enumerate(decisions):
        record = dict(base_record)
        record["article_id"] = format(index, "x") * 64
        record["decision"] = decision
        if version == 2:
            record["decision_schema_version"] = 2
            if decision == "reported_flooding":
                record["tags"] = ["fatality", "heavy-rain", "daño"]
        records.append(record)
    (state / "article-reviews.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode == 0, result.stderr
    assert len(list(backups.glob("crisispulse-*.tar.gz"))) == 1


def test_backup_accepts_null_as_an_empty_v2_article_tag_list(
    tmp_path: Path,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["decision_schema_version"] = 2
    record["decision"] = "heavy_rain_only"
    record["tags"] = None
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode == 0, result.stderr
    assert len(list(backups.glob("crisispulse-*.tar.gz"))) == 1


def test_backup_accepts_protocol_v1_article_review(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record.update(
        decision_schema_version=2,
        decision="reported_flooding",
        review_protocol_version=1,
        review_basis="full_article",
        headline_support="sufficient",
        impact_flags=["fatality", "transport_disruption"],
        context_flags=["aftermath_recovery"],
    )
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode == 0, result.stderr
    assert len(list(backups.glob("crisispulse-*.tar.gz"))) == 1


def test_backup_rejects_invalid_protocol_v1_flags(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record.update(
        decision_schema_version=2,
        decision="reported_flooding",
        review_protocol_version=1,
        review_basis="full_article",
        headline_support="sufficient",
        impact_flags=["fatality", "fatality"],
    )
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "impact_flags" in result.stderr
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_accepts_optional_publisher_title_provenance(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["decision_schema_version"] = 2
    record["decision"] = "reported_flooding"
    record["title_source"] = "publisher_metadata"
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode == 0, result.stderr
    assert len(list(backups.glob("crisispulse-*.tar.gz"))) == 1


@pytest.mark.parametrize("title_source", [None, 7, "review_display_text"])
def test_backup_rejects_invalid_article_title_provenance(
    tmp_path: Path,
    title_source: object,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["decision_schema_version"] = 2
    record["decision"] = "reported_flooding"
    record["title_source"] = title_source
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "invalid title_source" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_rejects_article_label_from_the_wrong_schema_version(
    tmp_path: Path,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["decision_schema_version"] = 2
    record["decision"] = "relevant"
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "invalid decision" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize(
    ("version", "tags"),
    [
        (2, ["Flood Damage"]),
        (2, ["x" * 33]),
        (2, ["fatality", "fatality"]),
        (2, [f"tag-{index}" for index in range(9)]),
        (1, ["fatality"]),
    ],
)
def test_backup_rejects_invalid_article_tags(
    tmp_path: Path,
    version: int,
    tags: list[str],
) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "article-reviews.jsonl"
    record = json.loads(review_path.read_text(encoding="utf-8"))
    record["decision_schema_version"] = version
    record["decision"] = "relevant" if version == 1 else "reported_flooding"
    record["tags"] = tags
    review_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "article tags" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_cleans_stale_partial_files(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    stale = backups / "crisispulse-old.tar.gz.partial"
    stale.write_bytes(b"partial")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode == 0, result.stderr
    assert not stale.exists()


def test_backup_refuses_missing_core_data_and_records_safe_failure(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    (state / "dashboard.json").unlink()
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    status = json.loads((backups / "backup-status.json").read_text(encoding="utf-8"))
    assert status == {
        "schema_version": 2,
        "status": "failed",
        "application_data_verified": False,
        "verified_at": None,
        "archive_name": "",
        "archive_bytes": 0,
        "checksum": "",
    }
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize(
    ("relative_path", "corrupt_bytes"),
    [
        (Path("state/dashboard.json"), b'{"snapshot":'),
        (Path("state/refresh-status.json"), b'{"schema_version":3,"status":"running"}\n'),
    ],
)
def test_backup_rejects_invalid_application_json(
    tmp_path: Path,
    relative_path: Path,
    corrupt_bytes: bytes,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    target = tmp_path / relative_path
    target.write_bytes(corrupt_bytes)
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "application data validation failed" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))
    status = json.loads((backups / "backup-status.json").read_text(encoding="utf-8"))
    assert status["application_data_verified"] is False


@pytest.mark.parametrize("invalid_case", ["mismatched_success", "future_times"])
def test_backup_rejects_refresh_timestamps_the_api_would_reject(
    tmp_path: Path,
    invalid_case: str,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    status_path = state / "refresh-status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if invalid_case == "mismatched_success":
        payload["last_success_at"] = "2026-08-24T21:04:59Z"
    else:
        future = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
        payload["started_at"] = future
        payload["finished_at"] = future
        payload["last_success_at"] = future
    status_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "refresh-status.json" in result.stderr
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize(
    ("json_name", "maximum_bytes"),
    [("dashboard.json", 2 << 20), ("refresh-status.json", 256 << 10)],
)
def test_backup_rejects_json_larger_than_api_caps(
    tmp_path: Path,
    json_name: str,
    maximum_bytes: int,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    path = state / json_name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["padding"] = "x" * maximum_bytes
    path.write_text(json.dumps(payload), encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "size limit" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("work/history/hourly_region_features.parquet"),
        Path("work/history/flood_articles_archive.parquet"),
    ],
)
def test_backup_rejects_corrupt_parquet(
    tmp_path: Path,
    relative_path: Path,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    (tmp_path / relative_path).write_bytes(b"not parquet")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "readable parquet" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_rejects_invalid_review_json_object(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    (state / "reviews.jsonl").write_text(
        (state / "reviews.jsonl").read_text(encoding="utf-8")
        + '["not", "an", "object"]\n',
        encoding="utf-8",
    )
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "must be a json object" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize("review_name", ["reviews.jsonl", "article-reviews.jsonl"])
def test_backup_rejects_empty_stored_review_shapes(
    tmp_path: Path,
    review_name: str,
) -> None:
    state, work, backups = _source_tree(tmp_path)
    (state / review_name).write_text("{}\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert review_name in result.stderr
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_rejects_review_line_larger_than_api_cap(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    review_path = state / "reviews.jsonl"
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    payload["ignored_by_go_but_scanner_limited"] = "x" * (17 << 10)
    review_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "line size limit" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_rejects_review_log_larger_than_api_cap(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    (state / "reviews.jsonl").write_bytes(b"\n" * ((4 << 20) + 1))
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "review log size limit" in result.stderr.lower()
    assert not list(backups.glob("crisispulse-*.tar.gz"))


@pytest.mark.parametrize(
    "article_ids",
    [["article-1", ""], ["article-1", "article-1"]],
)
def test_backup_rejects_empty_or_duplicate_article_ids(
    tmp_path: Path,
    article_ids: list[str],
) -> None:
    state, work, backups = _source_tree(tmp_path)
    count = len(article_ids)
    pl.DataFrame(
        {
            "article_id": article_ids,
            "seen_at": [datetime.now(UTC).replace(tzinfo=None)] * count,
            "canonical_url": ["https://example.test/flood"] * count,
            "source_domain": ["example.test"] * count,
            "disaster_type": ["flood"] * count,
        }
    ).write_parquet(work / "history" / "flood_articles_archive.parquet")
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")

    result = _run_alpine(script, state, work, backups)

    assert result.returncode != 0
    assert "article_id" in result.stderr
    assert not list(backups.glob("crisispulse-*.tar.gz"))


def test_backup_reads_uid_owned_mode_0600_review_logs_with_minimal_capability(
    tmp_path: Path,
) -> None:
    _ensure_maintenance_image()
    fixture_state, fixture_work, backups = _source_tree(tmp_path)
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")
    identifier = uuid.uuid4().hex[:12]
    state_volume = f"crisispulse-mode600-state-{identifier}"
    work_volume = f"crisispulse-mode600-work-{identifier}"
    backup_volume = f"crisispulse-unprivileged-backup-{identifier}"
    subprocess.run(["docker", "volume", "create", state_volume], check=True, capture_output=True)
    subprocess.run(["docker", "volume", "create", work_volume], check=True, capture_output=True)
    subprocess.run(["docker", "volume", "create", backup_volume], check=True, capture_output=True)
    try:
        prepared = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--volume",
                f"{state_volume}:/state",
                "--volume",
                f"{work_volume}:/work",
                "--volume",
                _mount(fixture_state, "/fixtures-state", read_only=True),
                "--volume",
                _mount(fixture_work, "/fixtures-work", read_only=True),
                MAINTENANCE_IMAGE,
                "/bin/sh",
                "-c",
                "cp -a /fixtures-state/. /state/ && cp -a /fixtures-work/. /work/ && "
                "chown -R 10001:10001 /state /work && "
                "chmod 0600 /state/reviews.jsonl /state/article-reviews.jsonl && "
                "chmod 0644 /state/refresh-status.lock && "
                "test \"$(stat -c '%u:%g %a' /state/reviews.jsonl)\" = '10001:10001 600'",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert prepared.returncode == 0, prepared.stderr
        initialized = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--volume",
                f"{backup_volume}:/backups",
                "alpine:3.23",
                "/bin/sh",
                "-c",
                "chown 10001:10001 /backups && chmod 0755 /backups",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert initialized.returncode == 0, initialized.stderr
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--cap-drop",
                "ALL",
                "--user",
                "10001:10001",
                "--volume",
                f"{state_volume}:/state:ro",
                "--volume",
                f"{work_volume}:/work:ro",
                "--volume",
                f"{backup_volume}:/backups",
                "--volume",
                _mount(script, "/opt/crisispulse/backup.sh", read_only=True),
                MAINTENANCE_IMAGE,
                "/bin/sh",
                "/opt/crisispulse/backup.sh",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        published = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--volume",
                f"{backup_volume}:/backups:ro",
                "alpine:3.23",
                "/bin/sh",
                "-c",
                "set -- /backups/crisispulse-*.tar.gz; "
                "test \"$#\" -eq 1 && test -f \"$1\"",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert published.returncode == 0, published.stderr
    finally:
        subprocess.run(
            [
                "docker",
                "volume",
                "rm",
                "--force",
                state_volume,
                work_volume,
                backup_volume,
            ],
            check=False,
            capture_output=True,
        )


def test_backup_waits_for_the_refresh_exclusive_lock(tmp_path: Path) -> None:
    state, work, backups = _source_tree(tmp_path)
    script = _normalized_script(BACKUP_SCRIPT, tmp_path / "backup.sh")
    holder = _hold_exclusive_refresh_lock(state)

    started = time.monotonic()
    result = _run_alpine(script, state, work, backups)
    elapsed = time.monotonic() - started
    holder.wait(timeout=10)

    assert result.returncode == 0, result.stderr
    assert elapsed >= 2


@pytest.mark.parametrize(
    ("archive_value", "expected_message"),
    [
        (
            "/backups/nested/crisispulse-20260824T000000Z.tar.gz",
            "directory must be exactly /backups",
        ),
        (
            "/backups/../backups/crisispulse-20260824T000000Z.tar.gz",
            "directory must be exactly /backups",
        ),
        ("/backups/crisispulse-latest.tar.gz", "archive name is invalid"),
    ],
)
def test_restore_requires_exact_backup_directory_and_strict_basename(
    tmp_path: Path,
    archive_value: str,
    expected_message: str,
) -> None:
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    backups = tmp_path / "backups"
    state.mkdir()
    work.mkdir()
    backups.mkdir()
    lock = state / "refresh-status.lock"
    lock.write_text("unchanged-lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": archive_value},
    )

    assert result.returncode != 0
    assert expected_message in result.stderr
    assert lock.read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []


def test_restore_rejects_corrupt_archive_before_target_mutation(tmp_path: Path) -> None:
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    backups = tmp_path / "backups"
    state.mkdir()
    work.mkdir()
    backups.mkdir()
    lock = state / "refresh-status.lock"
    lock.write_text("unchanged-lock\n", encoding="utf-8")
    archive = backups / "crisispulse-20260824T000001Z.tar.gz"
    archive.write_bytes(b"not a tar archive")
    archive.with_suffix(archive.suffix + ".sha256").write_bytes(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n".encode()
    )
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert lock.read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []
    assert "integrity check failed" in result.stderr


def test_restore_rejects_archive_that_does_not_match_its_sidecar(tmp_path: Path) -> None:
    _, _, backups, archive = _create_verified_backup(tmp_path / "source")
    archive.write_bytes(archive.read_bytes() + b"tampered")
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    lock = state / "refresh-status.lock"
    lock.write_text("unchanged-lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert lock.read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []
    assert "checksum verification failed" in result.stderr


def test_restore_rejects_unsafe_archive_before_target_mutation(tmp_path: Path) -> None:
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    backups = tmp_path / "backups"
    state.mkdir()
    work.mkdir()
    backups.mkdir()
    lock = state / "refresh-status.lock"
    lock.write_text("unchanged-lock\n", encoding="utf-8")
    archive = backups / "crisispulse-20260824T000002Z.tar.gz"
    with tarfile.open(archive, "w:gz") as opened:
        entry = tarfile.TarInfo("state/../../escape")
        payload = b"unsafe"
        entry.size = len(payload)
        opened.addfile(entry, io.BytesIO(payload))
    archive.with_suffix(archive.suffix + ".sha256").write_bytes(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n".encode()
    )
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert lock.read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []
    assert "unsafe path" in result.stderr or "unexpected entry" in result.stderr


def test_restore_rejects_non_file_archive_members(tmp_path: Path) -> None:
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    backups = tmp_path / "backups"
    state.mkdir()
    work.mkdir()
    backups.mkdir()
    lock = state / "refresh-status.lock"
    lock.write_text("unchanged-lock\n", encoding="utf-8")
    archive = backups / "crisispulse-20260824T000003Z.tar.gz"
    with tarfile.open(archive, "w:gz") as opened:
        for name in (
            "state/dashboard.json",
            "state/refresh-status.json",
            "work/history/hourly_region_features.parquet",
            "work/history/flood_articles_archive.parquet",
        ):
            payload = b"required"
            entry = tarfile.TarInfo(name)
            entry.size = len(payload)
            opened.addfile(entry, io.BytesIO(payload))
        special = tarfile.TarInfo("state/unsupported-fifo")
        special.type = tarfile.FIFOTYPE
        opened.addfile(special)
    archive.with_suffix(archive.suffix + ".sha256").write_bytes(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n".encode()
    )
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert lock.read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []
    assert "non-file entry" in result.stderr


def test_restore_revalidates_application_data_after_extraction(tmp_path: Path) -> None:
    source_state, source_work, backups = _source_tree(tmp_path / "source")
    (source_state / "dashboard.json").write_text(
        '{"snapshot":',
        encoding="utf-8",
    )
    archive = backups / "crisispulse-20260824T000004Z.tar.gz"
    members = [
        source_state / "dashboard.json",
        source_state / "refresh-status.json",
        source_state / "reviews.jsonl",
        source_state / "article-reviews.jsonl",
        source_work / "history" / "hourly_region_features.parquet",
        source_work / "history" / "flood_articles_archive.parquet",
    ]
    with tarfile.open(archive, "w:gz") as opened:
        for member in members:
            if member.is_relative_to(source_state):
                archive_name = Path("state") / member.relative_to(source_state)
            else:
                archive_name = Path("work") / member.relative_to(source_work)
            opened.add(member, arcname=archive_name.as_posix())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_bytes(
        f"{checksum}  {archive.name}\n".encode("utf-8")
    )

    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert "semantic validation" in result.stderr.lower()
    assert (state / "dashboard.json").is_file()
    assert (work / "history" / "flood_articles_archive.parquet").is_file()


def test_restore_uses_fresh_targets_and_preserves_review_logs(tmp_path: Path) -> None:
    _, _, backups, archive = _create_verified_backup(tmp_path / "source")
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode == 0, result.stderr
    assert (state / "dashboard.json").is_file()
    assert (state / "reviews.jsonl").is_file()
    assert (state / "article-reviews.jsonl").is_file()
    assert (work / "history" / "hourly_region_features.parquet").is_file()
    assert (work / "history" / "flood_articles_archive.parquet").is_file()


def test_restore_normalizes_untrusted_zero_modes(tmp_path: Path) -> None:
    source_state, source_work, backups = _source_tree(tmp_path / "source")
    archive = backups / "crisispulse-20260824T000005Z.tar.gz"
    members = [
        (source_state / "dashboard.json", "state/dashboard.json"),
        (source_state / "refresh-status.json", "state/refresh-status.json"),
        (source_state / "reviews.jsonl", "state/reviews.jsonl"),
        (source_state / "article-reviews.jsonl", "state/article-reviews.jsonl"),
        (
            source_work / "history" / "hourly_region_features.parquet",
            "work/history/hourly_region_features.parquet",
        ),
        (
            source_work / "history" / "flood_articles_archive.parquet",
            "work/history/flood_articles_archive.parquet",
        ),
    ]
    with tarfile.open(archive, "w:gz") as opened:
        for directory_name in ("state", "work", "work/history"):
            directory = tarfile.TarInfo(directory_name)
            directory.type = tarfile.DIRTYPE
            directory.mode = 0
            opened.addfile(directory)
        for source, archive_name in members:
            info = opened.gettarinfo(source, arcname=archive_name)
            info.mode = 0
            with source.open("rb") as payload:
                opened.addfile(info, payload)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_bytes(
        f"{checksum}  {archive.name}\n".encode("utf-8")
    )

    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode == 0, result.stderr
    permissions = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--volume",
            _mount(state, "/state", read_only=True),
            "--volume",
            _mount(work, "/work", read_only=True),
            MAINTENANCE_IMAGE,
            "/bin/sh",
            "-c",
            "stat -c '%a' /state /work /work/history /state/dashboard.json "
            "/work/history/hourly_region_features.parquet /state/refresh-status.lock",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert permissions.stdout.splitlines() == ["750", "750", "750", "640", "640", "644"]


def test_restore_refuses_nonempty_target_without_deleting_it(tmp_path: Path) -> None:
    _, _, backups, archive = _create_verified_backup(tmp_path / "source")
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    sentinel = state / "do-not-delete.txt"
    sentinel.write_text("preserve me\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )

    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
    assert "target state volume is not empty" in result.stderr


def test_restore_refuses_while_api_is_reachable(tmp_path: Path) -> None:
    _, _, backups, archive = _create_verified_backup(tmp_path / "source")
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    web = tmp_path / "www" / "api" / "v1"
    state.mkdir()
    work.mkdir()
    web.mkdir(parents=True)
    (state / "refresh-status.lock").write_text("unchanged-lock\n", encoding="utf-8")
    (web / "health").write_text('{"status":"ok"}\n', encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")
    identifier = uuid.uuid4().hex[:12]
    network = f"crisispulse-restore-test-{identifier}"
    server = f"crisispulse-api-test-{identifier}"
    subprocess.run(["docker", "network", "create", network], check=True, capture_output=True)
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                server,
                "--network",
                network,
                "--network-alias",
                "api",
                "--volume",
                _mount(tmp_path / "www", "/www", read_only=True),
                "caddy:2.10-alpine",
                "caddy",
                "file-server",
                "--listen",
                ":8080",
                "--root",
                "/www",
            ],
            check=True,
            capture_output=True,
        )
        for _ in range(30):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    server,
                    "wget",
                    "-q",
                    "-O",
                    "/dev/null",
                    "http://127.0.0.1:8080/api/v1/health",
                ],
                check=False,
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("temporary API did not become reachable")
        result = _run_alpine(
            script,
            state,
            work,
            backups,
            environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
            network=network,
        )
    finally:
        subprocess.run(["docker", "rm", "--force", server], check=False, capture_output=True)
        subprocess.run(["docker", "network", "rm", network], check=False, capture_output=True)

    assert result.returncode != 0
    assert (state / "refresh-status.lock").read_text(encoding="utf-8") == "unchanged-lock\n"
    assert list(work.iterdir()) == []
    assert "API is still reachable" in result.stderr


def test_restore_refuses_a_busy_target_lock_without_waiting(tmp_path: Path) -> None:
    _, _, backups, archive = _create_verified_backup(tmp_path / "source")
    state = tmp_path / "fresh-state"
    work = tmp_path / "fresh-work"
    state.mkdir()
    work.mkdir()
    (state / "refresh-status.lock").write_text("lock\n", encoding="utf-8")
    script = _normalized_script(RESTORE_SCRIPT, tmp_path / "restore.sh")
    holder = _hold_exclusive_refresh_lock(state, seconds=8)

    result = _run_alpine(
        script,
        state,
        work,
        backups,
        environment={"CONFIRM_RESTORE": "YES", "RESTORE_ARCHIVE": f"/backups/{archive.name}"},
    )
    holder_was_still_running = holder.poll() is None
    holder.wait(timeout=10)

    assert result.returncode != 0
    assert holder_was_still_running
    assert "target volume is in use" in result.stderr


def test_tracked_shell_and_systemd_files_use_lf_line_endings() -> None:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--",
            ":(glob)**/*.sh",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_paths = [ROOT / line for line in result.stdout.splitlines() if line]
    assert tracked_paths
    for path in tracked_paths:
        contents = path.read_bytes()
        assert b"\r" not in contents, f"{path.relative_to(ROOT)} must use LF endings"

    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes
    assert "*.service text eol=lf" in attributes
    assert "*.timer text eol=lf" in attributes
