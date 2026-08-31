from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_backup_utc_schedule_has_expected_eastern_times() -> None:
    edt = timezone(timedelta(hours=-4), "EDT")
    est = timezone(timedelta(hours=-5), "EST")
    summer = datetime(2026, 7, 15, 7, 10, tzinfo=UTC).astimezone(edt)
    winter = datetime(2027, 1, 15, 7, 10, tzinfo=UTC).astimezone(est)

    assert (summer.hour, summer.minute, summer.tzname()) == (3, 10, "EDT")
    assert (winter.hour, winter.minute, winter.tzname()) == (2, 10, "EST")


def test_refresh_service_has_a_hard_cpu_ceiling() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to render the production configuration")

    compose_version = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if compose_version.returncode != 0:
        pytest.skip("Docker Compose is unavailable")

    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env.production.example"),
            "-f",
            str(ROOT / "compose.production.yml"),
            "--profile",
            "maintenance",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads(result.stdout)
    assert config["services"]["refresh"]["cpus"] == 8

    environment = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "CRISISPULSE_REFRESH_CPUS=8.0" in environment


def test_backup_bind_mount_supports_an_explicit_host_path_with_spaces(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to render the production configuration")

    backup_path = (tmp_path / "CrisisPulse local backups").resolve()
    environment = os.environ.copy()
    environment["CRISISPULSE_BACKUP_DIR"] = str(backup_path)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env.production.example"),
            "-f",
            str(ROOT / "compose.production.yml"),
            "--profile",
            "maintenance",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads(result.stdout)
    expected = {
        "init-volumes": ("/backups", False),
        "api": ("/var/lib/crisispulse-backups", True),
        "backup": ("/backups", False),
        "restore": ("/backups", True),
    }
    for service_name, (target, read_only) in expected.items():
        mounts = config["services"][service_name]["volumes"]
        mount = next(item for item in mounts if item["target"] == target)
        assert Path(mount["source"]).resolve() == backup_path
        assert mount.get("read_only", False) is read_only
