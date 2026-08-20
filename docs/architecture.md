# CrisisPulse starter architecture

## Goal

This local MVP ingests GDELT GKG records, isolates flood reporting, builds explainable regional/hourly features, scores history-gated anomaly candidates, and presents the evidence in a read-only dashboard. It deliberately excludes cloud infrastructure and machine learning.

## Data flow

```text
Included sample TSV                         Optional live GDELT index
        |                                             |
        |                                      Go ingestor
        |                                  1–672 consecutive files
        |                                             |
        |                                  immutable ZIP + manifest
        |                                             |
        +--------------------+------------------------+
                             |
                    Python batch cleaner
         theme filter | URL cleanup | location parser
             exact deduplication | story grouping
                             |
                             v
                 data/clean/*.parquet
                             |
                  +----------+-----------+----------------+
                  |                      |                |
                  v                      v                v
          DuckDB hourly counts    manual-review CSV  ADM1/hour features
                                                           |
                                              +------------+------------+
                                              |                         |
                                              v                         v
                                    JSON inspection report    history-gated MAD scorer
                                                                      |
                                                                      v
                                                            dashboard JSON export
                                                                      |
                                                                      v
                                                               local Go API
                                                                      |
                                                                      v
                                                            local React dashboard
```

## Components

### Go ingestor

The ingestor reads GDELT's `lastupdate.txt`, selects the newest GKG ZIP, and can derive up to 672 consecutive 15-minute URLs ending at that file (seven days). Downloads use a temporary file followed by an atomic rename. Every new file receives a SHA-256 checksum and an entry in `manifest.jsonl`. Existing destinations report `already_present` and are not downloaded again.

When Docker or Go is unavailable, the Python standard-library downloader applies the same seven-day limit, checksum manifest, atomic rename, and idempotency rules. Its Windows runner defaults to `%USERPROFILE%\.crisispulse\raw` so multi-gigabyte raw history is not synchronized through OneDrive and every local runtime sees the same physical folder, including Microsoft Store Python.

After each history run, the compact feature merger atomically updates a local Parquet history keyed by hour, region, and disaster type. Overlapping batches replace the same keys instead of double-counting. The anomaly scorer reads this accumulated history, allowing raw ZIP retention to follow the user's storage policy independently of baseline continuity.

### Python cleaner

The cleaner accepts one or more official headerless GKG ZIP/TSV files or compact headered fixtures. Batch mode keeps one article-identity set across the entire window. It:

1. Classifies explicit disaster themes as high-confidence and ambiguous theme-only matches as weak.
2. Canonicalizes HTTP(S) URLs and removes common tracking parameters.
3. Hashes the canonical URL to form a stable article ID.
4. Removes exact canonical-URL duplicates and groups likely cross-domain copies using a conservative URL-slug and six-hour heuristic.
5. Parses all nine GDELT enhanced-location fields, records every candidate region, and classifies the selection as single, dominant, ambiguous, unresolved, or missing.
6. Preserves questionable records with quality flags.
7. Writes a compressed Parquet file.

### DuckDB analysis

The first analysis groups cleaned records by GDELT processing hour, disaster type, and primary location. It reports article counts and unique source-domain counts without requiring a database server.

### Gold feature builder

The first gold layer uses `country_code:adm1_code` as the region key, falling back to country and then `UNKNOWN`. Single-region and mention-dominant assignments may enter a named region. Tied, unresolved, and missing assignments go to `UNKNOWN` instead of creating a misleading regional signal. For every region, disaster type, and UTC hour it stores raw and high/weak article counts, location-confidence counts, unique domains, estimated unique stories, duplicate ratio, average tone, and story/domain velocity when the immediately preceding hour exists.

### Manual review set

The review builder writes a deterministic CSV sampled in round-robin order across high/weak theme strength and assigned/questionable location groups. It includes the article URL, matched themes, selected location, candidate regions, and blank human-label columns. The labels remain local and are not used as ground truth until a person fills them in. A separate evaluator then reports relevance rate by match strength and primary-region accuracy while excluding blank and uncertain labels.

### Anomaly candidate scorer

The scorer densifies each observed region/disaster series to hourly rows, filling absent reporting with zero. For every hour it computes a rolling median and median absolute deviation from prior hours only. The default gate requires 168 prior hours, at least three high-confidence story groups, at least three source domains, a story increase of at least three, and a robust-z score of at least `6.0`. When historical MAD is zero, the same history and support gates still apply before a positive jump can become a candidate.

Statuses make readiness explicit: `insufficient_history`, `below_minimum_support`, `normal`, or `candidate_anomaly`. The output is an unusual-reporting candidate list, never a claim that a physical disaster occurred.

### Evidence dashboard

The exporter combines coverage totals from compact feature history, anomaly parameters, status totals, and the latest supported rows into one small JSON snapshot. Using the same feature history for coverage and scoring prevents an incremental clean batch from being presented as the full retained reporting window. A history run refreshes the snapshot automatically.

The standard-library Go API reads that file on every request, so a completed history run becomes visible without restarting the service. It exposes a health check, the complete snapshot, a smaller signals projection, and a local review endpoint. Snapshot responses are read-only, size-limited, and no-store. Review writes accept only three validated decisions from the configured local dashboard origin.

Review decisions use a bounded append-only JSON Lines audit log. Re-labeling a region/hour adds a new record; reads collapse the log to the latest decision per stable signal ID. This keeps the data inspectable and preserves corrections without adding a database. The React dashboard uses the API when it is reachable and falls back to its bundled verified snapshot when it is not. Review buttons remain disabled without the local API.

The first dashboard remains local and has no authentication, map service, remote database, or paid API.

### Incremental refresh

The refresh runner downloads the latest eight 15-minute files into a persistent cache outside OneDrive. It starts processing at the first hour boundary within that overlap, then merges the resulting region/hour features into compact history. A refreshed hour replaces its prior region rows as one partition rather than double-counting or leaving stale rows. The overlap allows an initially partial current hour to be replaced as later quarter-hour files arrive without treating the cut-off leading hour as complete.

An exclusive local lock skips overlapping runs. After a successful refresh, raw retention removes only ZIP files beyond the newest 672, keeping disk usage bounded to approximately seven days. A local JSON status file records start, completion, last success, download counts, retained files, pruned files, and failure messages. The optional Windows Scheduled Task invokes this runner every 15 minutes and can be removed independently of project data.

## Key decisions and limits

- `seen_at` is the GDELT processing timestamp and is stored as a timezone-naive UTC value for cross-platform compatibility.
- The default flood filter keeps explicit flood/flooding/floods themes and excludes weak-only matches such as metaphorical `FLOODED` or World Bank policy themes. Weak matches remain available through `--minimum-strength weak` for recall studies.
- Exact canonical URL duplicates are removed. A conservative URL-slug heuristic groups obvious cross-domain copies but does not delete them; embeddings or MinHash remain a later improvement.
- The primary-location heuristic prefers valid coordinates, geographic specificity, repeated mentions, and then the earliest mention. Repeated mentions of the same region can create a dominant assignment. Equal top region counts are explicitly ambiguous and cannot enter a named regional aggregate. Questionable coordinates remain visible through quality flags.
- Raw downloads are immutable. Reprocessing should create a new cleaned output instead of altering the source file.
- Anomaly baselines include zero-filled hours and exclude the current observation to avoid survivorship bias and future leakage.
- Every component runs locally with free software. No credentials, cloud accounts, or paid APIs are used.
