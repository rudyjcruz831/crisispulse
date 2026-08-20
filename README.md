# CrisisPulse

CrisisPulse is a portfolio project for detecting emerging disaster signals in GDELT news reporting. This starter implements the first local, explainable pipeline for flood-related GKG records. It does **not** claim to predict physical disasters before they occur.

The current version costs **$0** to run: it uses local Python, DuckDB, Parquet, Docker, Go, and public GDELT data. It has no cloud resources, paid APIs, credentials, or background services.

## What works now

- A Go ingestor that discovers and safely downloads the newest GDELT GKG file.
- An immutable raw-file layout with SHA-256 checksums and a JSON Lines manifest.
- A Python cleaner for official GKG ZIP/TSV files and compact headered samples.
- High/weak flood and wildfire theme classification (the sample run uses high-confidence floods).
- URL canonicalization, source-domain extraction, exact deduplication, and location parsing.
- Quality flags that preserve questionable records instead of silently deleting them.
- Compressed Parquet output and DuckDB hourly counts.
- Conservative cross-domain syndicated-story grouping using URL slugs and six-hour windows.
- A repeatable JSON quality report for evaluating real GKG files.
- Fourteen Python tests and two Go tests.

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

To clean a downloaded ZIP, replace the filename below with the one in `data/raw`:

```powershell
.\.venv\Scripts\python.exe -m pipelines.clean_gkg --input data/raw/20260819120000.gkg.csv.zip --output data/clean/live_floods.parquet --disaster flood
.\.venv\Scripts\python.exe -m pipelines.hourly_counts --input data/clean/live_floods.parquet
.\.venv\Scripts\python.exe -m pipelines.inspect_clean --input data/clean/live_floods.parquet
```

## Repository map

```text
cmd/ingestor/              Go live-file downloader
pipelines/                 Python cleaning and DuckDB analysis
data/sample/               Tiny, versioned GKG-format fixture
data/raw/                  Immutable downloads (ignored by Git)
data/clean/                Generated Parquet files (ignored by Git)
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
- Location selection is a transparent starter heuristic, not a full geocoder.

### First live validation

The cleaner has been exercised against a current 15-minute GKG update. That run exposed and fixed the live nine-field `V2ENHANCEDLOCATIONS` layout (including ADM2), and showed that `NATURAL_DISASTER_FLOODED` often describes metaphorical flooding. Both cases are now covered by regression tests. Live ZIPs and generated Parquet files remain local and are excluded from Git.

These constraints are deliberate. The next milestone should process several consecutive GKG updates and build duplicate-adjusted regional/hourly features before adding an anomaly baseline.

## Design reference

See [the architecture](docs/architecture.md) for component details, [the data dictionary](docs/data-dictionary.md) for the Parquet schema, and [the first live validation](docs/live-validation-2026-08-20.md) for evidence from a real GKG update.
