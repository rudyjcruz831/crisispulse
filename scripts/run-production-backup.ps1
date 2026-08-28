$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentPath = Join-Path $RepositoryRoot ".env.production"
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
exit $ExitCode
