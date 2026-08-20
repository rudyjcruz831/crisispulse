$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The local environment is missing. Run scripts\setup.ps1 first."
}

& $Python -m pipelines.clean_gkg `
    --input data/sample/gkg_sample.tsv `
    --output data/clean/flood_articles.parquet `
    --disaster flood
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pipelines.hourly_counts `
    --input data/clean/flood_articles.parquet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
