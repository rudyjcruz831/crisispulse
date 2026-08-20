param(
    [string]$RawDir = "$env:LOCALAPPDATA\CrisisPulse\raw",
    [int]$Intervals = 672,
    [int]$Workers = 8
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
    --output dashboard/data/dashboard.json
exit $LASTEXITCODE
