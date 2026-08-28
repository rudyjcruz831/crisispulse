from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_task_installers_use_the_quiet_launcher() -> None:
    for relative_path in (
        "scripts/install-refresh-task.ps1",
        "scripts/install-production-refresh-task.ps1",
        "scripts/install-production-soak-task.ps1",
        "scripts/install-production-backup-task.ps1",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "run-hidden.vbs" in source
        assert "//B //NoLogo" in source
        assert "-Execute \"powershell.exe\"" not in source


def test_quiet_launcher_hides_powershell_and_preserves_its_result() -> None:
    source = (ROOT / "scripts/run-hidden.vbs").read_text(encoding="utf-8")
    assert "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" in source
    assert "-NoProfile -NonInteractive" in source
    assert "-WindowStyle Hidden" in source
    assert "shell.Run(command, 0, True)" in source
    assert "WScript.Quit exitCode" in source


def test_production_backup_task_runs_daily_at_a_fixed_utc_time() -> None:
    installer = (ROOT / "scripts/install-production-backup-task.ps1").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "scripts/run-production-backup.ps1").read_text(encoding="utf-8")

    assert '"CrisisPulse Production Backup"' in installer
    assert "[int]$UtcHour = 7" in installer
    assert "[int]$UtcMinute = 10" in installer
    assert 'FindSystemTimeZoneById("Eastern Standard Time")' in installer
    assert "$StartUtc = [DateTime]::SpecifyKind(" in installer
    assert "$StartAt = $StartUtc.ToLocalTime()" in installer
    assert "New-ScheduledTaskTrigger -Daily" in installer
    assert "-StartWhenAvailable" in installer
    assert "-MultipleInstances IgnoreNew" in installer
    assert "New-TimeSpan -Minutes 90" in installer
    assert "run --rm backup" in runner
    assert "Start-Process -FilePath $DockerDesktop -WindowStyle Hidden" in runner
    assert "$ExitCode = $LASTEXITCODE" in runner
    assert "exit $ExitCode" in runner
    assert '"run-encrypted-offsite-backup.ps1"' in runner
    assert "if (Test-Path -LiteralPath $EncryptionConfigPath)" in runner


def test_encrypted_backup_secrets_stay_outside_the_repository() -> None:
    setup = (ROOT / "scripts/setup-encrypted-offsite-backup.ps1").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "scripts/run-encrypted-offsite-backup.ps1").read_text(
        encoding="utf-8"
    )
    common = (ROOT / "scripts/backup-encryption-common.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Join-Path $env:LOCALAPPDATA "CrisisPulse\\backup-encryption\\config.json"' in common
    assert '"SAVE-THIS-RECOVERY-CODE.txt"' in setup
    assert 'Join-Path $OneDriveRoot "CrisisPulse Encrypted Backups"' in setup
    assert "Export-PfxCertificate" in setup
    assert "Protect-CmsMessage" in common
    assert "HMACSHA256" in common
    assert "DataProtectionScope]::CurrentUser" in common
    assert "$EncryptedFile.Length -gt 134217728" in common
    assert "$DeclaredArchiveBytes -gt 67108864" in common
    assert "max_archive_bytes = 67108864" in setup
    assert "Test-CrisisPulseEncryptedBackup" in setup
    assert setup.index('Write-CrisisPulseUtf8Atomic -Path $RecoveryCodePath') < setup.index(
        '-Path $ConfigPath `'
    )
    assert "$EnvironmentOriginalBytes" in setup
    assert "$EnvironmentRollback" in setup
    assert "cloud_visibility_confirmed = $false" in runner
    assert "RecoveryPasswordText" not in runner
