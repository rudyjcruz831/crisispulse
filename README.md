# CrisisPulse

CrisisPulse is a portfolio project for detecting emerging disaster signals in GDELT news reporting. This starter implements the first local, explainable pipeline for flood-related GKG records. It does **not** claim to predict physical disasters before they occur.

The current version costs **$0** to run: it uses local Python, DuckDB, Parquet, Docker, Go, and public GDELT data. It has no cloud resources, paid APIs, credentials, or background services.

## What works now

- A Go ingestor that discovers and safely downloads the newest GDELT GKG file.
- An immutable raw-file layout with SHA-256 checksums and a JSON Lines manifest.
- A Python cleaner for official GKG ZIP/TSV files and compact headered samples.
- Flood and wildfire theme filtering (the sample run uses floods).
- URL canonicalization, source-domain extraction, exact deduplication, and location parsing.
- Quality flags that preserve questionable records instead of silently deleting them.
- Compressed Parquet output and DuckDB hourly counts.
- Seven Python tests and two Go tests.

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
- The first flood rule matches GKG themes containing `FLOOD`; it needs evaluation on real data.
- Exact URL deduplication does not yet identify syndicated copies across different domains.
- `seen_at` is when GDELT processed a record, not necessarily when the source article was published.
- Location selection is a transparent starter heuristic, not a full geocoder.

These constraints are deliberate. The next milestone should validate the flood filter on a small real GKG file, then improve multi-location handling and cross-domain story deduplication before adding anomaly scores.

## Design reference

See [the architecture](docs/architecture.md) for component details and [the data dictionary](docs/data-dictionary.md) for the Parquet schema.
