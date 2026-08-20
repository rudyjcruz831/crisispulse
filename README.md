# CrisisPulse

CrisisPulse is a portfolio project for detecting emerging disaster signals in GDELT news reporting. This starter implements the first local, explainable pipeline for flood-related GKG records. It does **not** claim to predict physical disasters before they occur.

The current version costs **$0** to run: it uses local Python, DuckDB, Parquet, Docker, Go, and public GDELT data. It has no cloud resources, paid APIs, or credentials; the optional background refresh is a local Windows task.

## What works now

- A Go ingestor that discovers and safely downloads the newest GDELT GKG file.
- Consecutive-window ingestion for up to 672 fifteen-minute files (seven days).
- An immutable raw-file layout with SHA-256 checksums and a JSON Lines manifest.
- A Python cleaner for official GKG ZIP/TSV files and compact headered samples.
- High/weak flood and wildfire theme classification (the sample run uses high-confidence floods).
- URL canonicalization, source-domain extraction, exact deduplication, and location parsing.
- Explicit `single`, `dominant`, `ambiguous`, `unresolved`, or `missing` regional selection status.
- Quality flags that preserve questionable records instead of silently deleting them.
- Compressed Parquet output and DuckDB hourly counts.
- Conservative cross-domain syndicated-story grouping using URL slugs and six-hour windows.
- A repeatable JSON quality report for evaluating real GKG files.
- Duplicate-adjusted ADM1/hour features with source diversity and velocity.
- A readable JSON feature report for inspecting the strongest regional signals.
- A balanced manual-review CSV with blank relevance and primary-region label fields.
- A local scorecard for completed relevance and primary-region labels.
- Conservative rolling median/MAD anomaly candidates with a seven-day history gate.
- A local React evidence dashboard generated from the latest pipeline outputs.
- A local Go API for health, complete snapshot, and supported-signal responses.
- A safe local 15-minute refresh workflow with locking, seven-day raw retention, and run status.
- A local human-review queue with persistent real-event, irrelevant-news, and uncertain labels.
- Twenty-nine Python tests, twelve Go tests, and two dashboard rendering tests.

## Quick start on Windows

From PowerShell in this repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-sample.ps1
```

The first command creates an isolated `.venv` and installs the free Python packages. The second cleans the five included GDELT-format sample rows and prints hourly location counts.

Expected cleaning summary:

```text
input rows:       5
flood rows:       4
duplicates:       1
clean rows:       3
```

The result is written to `data/clean/flood_articles.parquet`.

Run the tests:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

## Docker alternative

Docker can run the sample cleaner without a local Python setup:

```powershell
docker compose run --rm pipeline
docker compose run --rm pipeline python -m pipelines.hourly_counts --input data/clean/flood_articles.parquet
```

The Dockerized Go build runs its unit tests before producing the ingestor binary, so Go does not need to be installed on the host.

## Optional live GDELT download

This step accesses the public internet and stores the newest GKG ZIP locally. GDELT does not charge for the file, but it uses your normal internet bandwidth and disk space.

```powershell
docker compose --profile live run --rm ingestor
```

Downloaded files go to `data/raw`, and metadata goes to `data/raw/manifest.jsonl`. Running the same file again returns `already_present` rather than downloading a duplicate.

Download the latest two hours as eight consecutive files:

```powershell
docker compose --profile live run --rm ingestor --intervals 8 --output-dir /app/data/raw
```

Download the latest seven days as 672 files. A current window is roughly 4 GB, depending on GDELT file sizes:

```powershell
docker compose --profile live run --rm ingestor --intervals 672 --output-dir /app/data/raw
```

If Docker is unavailable, the local fallback stores the large raw archive outside OneDrive by default and then runs the same batch pipeline:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-history.ps1
```

The history runner merges each compact feature batch into `data/history/hourly_region_features.parquet`, replacing overlapping region/hour keys. Future runs can therefore extend the baseline without retaining every multi-gigabyte raw window in the repository.

To clean a downloaded ZIP, replace the filename below with the one in `data/raw`:

```powershell
.\.venv\Scripts\python.exe -m pipelines.clean_gkg --input data/raw/20260819120000.gkg.csv.zip --output data/clean/live_floods.parquet --disaster flood
.\.venv\Scripts\python.exe -m pipelines.hourly_counts --input data/clean/live_floods.parquet
.\.venv\Scripts\python.exe -m pipelines.inspect_clean --input data/clean/live_floods.parquet
```

## Multi-file aggregation

After downloading a window, clean it as one batch and build regional/hourly features. The pattern should select only the consecutive files you want to analyze:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-batch.ps1
```

If `data/raw` also contains older windows, pass `-Pattern` to select only the consecutive filenames you want.

The batch cleaner preserves both high and weak matches for auditing, deduplicates exact URLs across all selected files, and recalculates syndicated group sizes across the full window. It produces:

```text
data/clean/flood_articles_batch.parquet
data/features/hourly_region_features.parquet
data/features/hourly_region_report.json
data/features/hourly_region_anomalies.parquet
data/features/hourly_region_anomaly_report.json
data/review/flood_manual_review.csv
```

The review CSV is deterministic and round-robins across high/weak matches and assigned/questionable locations. Fill in `label_disaster_relevance`, `label_primary_region`, and `review_notes`; generated review files remain local and are ignored by Git.

After labeling, calculate the review scorecard:

```powershell
.\.venv\Scripts\python.exe -m pipelines.evaluate_review `
  --input data/review/flood_manual_review.csv `
  --output data/review/flood_review_report.json
```

## Anomaly readiness

The batch command also creates a conservative anomaly-scoring table. It fills missing region-hours with zero and uses only prior observations in a rolling median/MAD baseline. A row cannot become a candidate until it has at least 168 prior hourly observations, three high-confidence stories, three source domains, and an increase of at least three stories. The default robust-z threshold is `6.0`.

The seven-day validation produced the first fully eligible hour: two rows were classified as normal and zero alert candidates were created. This confirms the history gate opens without manufacturing alerts; it does not mean no floods occurred.

## Local API and dashboard

Install the verified portable Go toolchain once, then start the API:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-go.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-api.ps1
```

The history runner refreshes the runtime dashboard snapshot from the real clean, feature, and anomaly outputs. Start the dashboard locally with:

```powershell
cd dashboard
npm install
npm run dev
```

The dashboard shows current candidate counts, supported regional evidence, scoring readiness, alert guardrails, and a human-review queue. Candidate decisions are appended to `%USERPROFILE%\.crisispulse\reviews.jsonl` and can be changed without losing the earlier audit entries. It connects to the Go API when available and visibly falls back to the last verified snapshot when the API is stopped. It requires no paid API and never presents an unusual news pattern as a verified disaster.

Run the complete Python, Go, and dashboard test suite with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

## Automatic local refresh

Run one incremental refresh manually before scheduling it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-refresh.ps1
```

The refresh downloads the newest two-hour overlap, processes from the first safe hour boundary, merges it into compact history, refreshes anomaly scores, and writes the live API snapshot to `%USERPROFILE%\.crisispulse\dashboard.json`. Raw ZIP retention is capped at 672 files (seven days) outside OneDrive. Concurrent runs are skipped, and the latest outcome is recorded at `%USERPROFILE%\.crisispulse\refresh-status.json`.

After a successful manual run, the optional Windows task can run it every 15 minutes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-refresh-task.ps1
```

Remove the task at any time with `scripts\uninstall-refresh-task.ps1`. See [the automation guide](docs/automation.md) before enabling it.

## Repository map

```text
cmd/ingestor/              Go live-file downloader
cmd/api/                   Go signals API
pipelines/                 Python cleaning, batch aggregation, features, and reports
data/sample/               Tiny, versioned GKG-format fixture
data/raw/                  Immutable downloads (ignored by Git)
%USERPROFILE%/.crisispulse/raw/  Default seven-day cache outside OneDrive
data/clean/                Generated Parquet files (ignored by Git)
data/review/               Generated human-labeling CSV files (ignored by Git)
data/history/              Compact accumulated feature history (ignored by Git)
dashboard/                 Local React evidence dashboard
tests/                     Python unit and pipeline tests
scripts/                   Windows setup, run, and test commands
docs/architecture.md       Design decisions and data flow
docs/data-dictionary.md    Clean Parquet field definitions
```

## Important limitations

- GDELT measures news reporting, not physical hazard sensors.
- The high-confidence flood rule removes the weakest theme matches, but GDELT themes can still reflect metaphorical or background references.
- The URL-slug grouping catches obvious syndicated copies but is only an estimate, not content-level deduplication.
- `seen_at` is when GDELT processed a record, not necessarily when the source article was published.
- Location selection is a transparent starter heuristic, not a full geocoder. Tied multi-region articles are routed to `UNKNOWN` until reviewed.
- ADM1 region IDs use GDELT/FIPS-style country and administrative codes, not guaranteed ISO codes.
- Seven days opens the first eligible scoring hour but is not yet enough to evaluate candidate stability over time.
- An anomaly candidate measures unusual news reporting, not proof of a physical disaster.

### First live validation

The cleaner has been exercised against a current 15-minute GKG update. That run exposed and fixed the live nine-field `V2ENHANCEDLOCATIONS` layout (including ADM2), and showed that `NATURAL_DISASTER_FLOODED` often describes metaphorical flooding. Both cases are now covered by regression tests. Live ZIPs and generated Parquet files remain local and are excluded from Git.

These constraints are deliberate. The next milestone is to label the generated review set and keep extending the compact hourly history so candidate stability can be measured across many eligible hours.

## Design reference

See [the architecture](docs/architecture.md) for component details, [the automation guide](docs/automation.md), [the API reference](docs/api.md), [the data dictionary](docs/data-dictionary.md) for the Parquet schemas, [the first live validation](docs/live-validation-2026-08-20.md), [the multi-file validation](docs/multi-file-validation-2026-08-20.md), and [the seven-day validation](docs/seven-day-validation-2026-08-20.md).
