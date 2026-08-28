$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentPath = Join-Path $RepositoryRoot ".env.production"
$EncryptedBackupRunner = Join-Path $PSScriptRoot "run-encrypted-offsite-backup.ps1"
$EncryptionConfigPath = Join-Path $env:LOCALAPPDATA "CrisisPulse\backup-encryption\config.json"
if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
    throw "The local production environment file is missing."
}

& cmd.exe /d /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    $DockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $DockerDesktop)) {
        throw "Docker Desktop is not installed at the expected location."
    }
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $DockerDesktop -WindowStyle Hidden
    }
    $DockerReady = $false
    for ($Attempt = 0; $Attempt -lt 24; $Attempt++) {
        Start-Sleep -Seconds 5
        & cmd.exe /d /c "docker info >nul 2>&1"
        if ($LASTEXITCODE -eq 0) {
            $DockerReady = $true
            break
        }
    }
    if (-not $DockerReady) {
        throw "Docker Desktop did not become ready within two minutes."
    }
}

Push-Location $RepositoryRoot
try {
    & docker compose `
        --env-file .env.production `
        -f compose.production.yml `
        --profile maintenance `
        run --rm backup
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($ExitCode -ne 0) {
    exit $ExitCode
}

# Off-device encryption is optional on hosts that have not run the setup yet.
# Once configured, a failed encrypted copy makes the scheduled task fail loudly
# while preserving the already verified local archive.
if (Test-Path -LiteralPath $EncryptionConfigPath) {
    if (-not (Test-Path -LiteralPath $EncryptedBackupRunner)) {
        throw "Encrypted backup is configured, but its runner is missing."
    }
    & $EncryptedBackupRunner -ConfigPath $EncryptionConfigPath
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
exit 0
