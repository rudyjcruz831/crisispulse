param(
    [string]$DashboardOutput = "$env:USERPROFILE\.crisispulse\dashboard.json"
)

$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

Push-Location $RepositoryRoot
try {
    & $Python -m pipelines.merge_feature_history `
        --input data/features/hourly_region_features.parquet `
        --history data/history/hourly_region_features.parquet
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $Python -m pipelines.score_anomalies `
        --input data/history/hourly_region_features.parquet `
        --output data/features/hourly_region_anomalies.parquet `
        --report data/features/hourly_region_anomaly_report.json
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $Python -m pipelines.export_dashboard `
        --clean data/clean/flood_articles_batch.parquet `
        --features data/history/hourly_region_features.parquet `
        --anomalies data/features/hourly_region_anomalies.parquet `
        --anomaly-report data/features/hourly_region_anomaly_report.json `
        --output $DashboardOutput
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
