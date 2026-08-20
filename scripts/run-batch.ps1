param(
    [string]$InputDir = "data/raw",
    [string]$Pattern = "*.gkg.csv.zip"
)

$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

& $Python -m pipelines.batch_clean `
    --input-dir $InputDir `
    --pattern $Pattern `
    --output data/clean/flood_articles_batch.parquet `
    --disaster flood `
    --minimum-strength weak
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pipelines.inspect_clean `
    --input data/clean/flood_articles_batch.parquet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pipelines.build_review_set `
    --input data/clean/flood_articles_batch.parquet `
    --output data/review/flood_manual_review.csv `
    --size 40
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pipelines.build_features `
    --input data/clean/flood_articles_batch.parquet `
    --output data/features/hourly_region_features.parquet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pipelines.inspect_features `
    --input data/features/hourly_region_features.parquet `
    --output data/features/hourly_region_report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
