param(
    [string]$RawDir = "$env:USERPROFILE\.crisispulse\raw",
    [int]$Intervals = 672,
    [int]$Workers = 8,
    [string]$DashboardOutput = "$env:USERPROFILE\.crisispulse\dashboard.json"
)

$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

& $Python -m pipelines.download_history `
    --output-dir $RawDir `
    --intervals $Intervals `
    --workers $Workers
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& powershell -ExecutionPolicy Bypass -File .\scripts\run-batch.ps1 `
    -InputDir $RawDir `
    -Pattern "*.gkg.csv.zip"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update-history.ps1 `
    -DashboardOutput $DashboardOutput
exit $LASTEXITCODE
