# CrisisPulse starter architecture

## Goal

This local MVP ingests GDELT GKG records, isolates flood reporting, builds explainable regional/hourly features, scores history-gated anomaly candidates, measures future news-domain spread, and presents the evidence in a local review dashboard. An optional, not-yet-activated single-server package runs the same components behind HTTPS and a shared paid-pilot login.

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
                                                          +-----------+-----------+
                                                          |                       |
                                                          v                       v
                                                six-hour outcome table    anomaly candidates
                                                          |
                                                          v
                                               chronological model + report
                                                          |
                                                          +-----------+-----------+
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

After each history run, the compact feature merger atomically updates a local Parquet history keyed by hour, region, and disaster type. Overlapping batches replace the same keys instead of double-counting. The production refresh also maintains a permanent zstd-compressed article archive keyed by stable article ID. Current rows can improve cached titles and quality fields without duplicating the article. The archive is written to a temporary file, read back, and checked for every current article ID before it replaces the prior archive. The anomaly scorer reads accumulated feature history, allowing raw ZIP retention to follow the user's storage policy independently of baseline continuity or article preservation.

### Python cleaner

The cleaner accepts one or more official headerless GKG ZIP/TSV files or compact headered fixtures. Batch mode keeps one article-identity set across the entire window. It:

1. Classifies explicit disaster themes as high-confidence and ambiguous theme-only matches as weak. When a readable URL headline clearly conflicts with the selected disaster topic, the row is downgraded to weak and cannot create an alert.
2. Canonicalizes HTTP(S) URLs and removes common tracking parameters.
3. Hashes the canonical URL to form a stable article ID.
4. Removes exact canonical-URL duplicates and groups likely cross-domain copies using a conservative URL-title and six-hour heuristic. Trailing numeric article IDs are skipped so syndicated copies group on their readable title segment.
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

### Six-hour outcome and supervised benchmark

The outcome builder creates one time-locked label per region/hour. A positive `media_spread_6h` outcome means that at least 20 source domains appear in any single hour during future hours 1–6. The prediction hour is explicitly excluded. Outcomes remain pending until all six future hours exist, so an in-progress forecast cannot leak partial future results into evaluation.

Model evaluation uses only completed outcome rows and prediction-time features. Prediction hours are split chronologically into training, validation, and final test periods, with a six-hour embargo between them so label windows do not overlap. A class-balanced logistic regression selects its alert threshold on validation data and reports exploratory metrics on the later test period, which is not used for fitting or threshold selection. The portable artifact stores feature order, scaler values, coefficients, and intercept as JSON.

Because class balancing changes the score scale, model scores are treated as ranking values rather than calibrated probabilities. The modeled target is future publisher-domain spread, not a physical event or its severity. See the model card for the current short-holdout results and usage limits.

### Evidence dashboard

The exporter combines coverage totals from compact feature history, anomaly parameters, status totals, future-outcome counts, the chronological model report, and the latest supported rows into one small JSON snapshot. Using the same feature history for coverage and scoring prevents an incremental clean batch from being presented as the full retained reporting window. A history run refreshes the snapshot automatically.

The standard-library Go API reads that file on every request, so a completed history run becomes visible without restarting the service. It exposes a health check, the complete snapshot, a smaller signals projection, and a local review endpoint. Snapshot responses are read-only, size-limited, and no-store. Review writes accept only validated decisions from the exact configured dashboard origins; the local package permits its protected address and loopback-only preview while rejecting every other browser origin.

Review decisions use a bounded append-only JSON Lines audit log. Re-labeling a region/hour adds a new record; reads collapse the log to the latest decision per stable signal ID. This keeps the data inspectable and preserves corrections without adding a database. The React dashboard uses the API when it is reachable and falls back to its bundled verified snapshot when it is not. Review buttons remain disabled without the local API.

The API derives review-quality counts from those latest decisions and exports the same records as CSV. Rate fields remain `null` until 20 labels are resolved as real event or irrelevant news; uncertain labels are retained but excluded from the denominator. This prevents a tiny or ambiguous sample from being presented as product accuracy, and the dashboard explicitly distinguishes human-review outcomes from external disaster verification.

The admin operations route combines the dashboard snapshot with a sanitized refresh-status projection. It reports whether the 15-minute pipeline is current, the expected next run, permanent article count and compressed size, bounded raw-storage counts, open forecast clocks, holdout metrics, human-review progress, and paid-pilot readiness. All times are rendered in U.S. Eastern Time. The API never returns the local paths or raw filenames stored in the refresh log, and the interface exposes no destructive controls; its only write is an append-only article review decision. Private authentication remains a deployment gate before `/admin` can be published.

The admin quality lab is intentionally separate from anomaly review. Every refresh derives a stable 24-item daily sample from recent permanent article history, round-robining strong matches, weak headline conflicts, and other ambiguous matches. This keeps evaluation available during quiet periods with zero anomaly candidates. Article decisions are append-only, rates are separated by stratum, and measurement stays locked until 20 resolved decisions include at least five strong and five blocked examples. The balanced sample measures filter behavior; its combined label share is not a prevalence estimate.

The dashboard exporter also attaches a bounded evidence bundle to each displayed signal. Clean rows are matched by region and UTC hour, grouped by duplicate-adjusted story ID, and limited to eight stories with eight publisher URLs per story. When an older candidate is still displayed but its clean hour is no longer in the incremental batch, the exporter carries forward its previously captured evidence. GDELT publisher URLs are retained as direct links. A bounded title reader checks `robots.txt`, rejects credentials, nonstandard ports, private or local network destinations, caps redirects and response bytes, and reads only the small set of pages eligible for display. It considers Open Graph, Twitter, JSON-LD, headline metadata, article headings, and HTML titles, then stores accepted results in a compact persistent cache. A rotating 12-article batch gradually writes successful titles into permanent history; its cursor advances even after blocked or missing pages so the archive cannot stall on the oldest failures. A failed lookup never fails the refresh, and the interface explicitly distinguishes publisher metadata, conservative URL-derived titles, and unavailable titles.

The default dashboard remains local and has no authentication, map service, remote database, or paid API. The optional single-server package protects the entire pilot with Caddy basic authentication; managed per-user identity remains a later milestone.

### Optional single-server package

The production package uses Caddy as the only public entry point. It terminates HTTPS, protects the dashboard and API with a shared pilot login, and routes same-origin API requests to the Go service. The dashboard and API restart automatically. A Linux-native one-shot refresh container writes to persistent state and work volumes; a systemd timer starts it every 15 minutes and prevents overlapping service runs. A separate monitor checks refresh freshness, and a daily timer creates compressed backups without copying re-downloadable raw GDELT ZIP files.

The design deliberately keeps one server and local files for the first pilot. Its trade-off is a single failure domain and no per-user access control. Off-server encrypted backups, managed identity, and redundant service instances should be revisited when revenue or customer requirements justify the added cost.

### Incremental refresh

The refresh runner downloads the latest eight 15-minute files into a persistent cache outside OneDrive. It starts processing at the first hour boundary within that overlap, then merges the resulting region/hour features into compact history. A refreshed hour replaces its prior region rows as one partition rather than double-counting or leaving stale rows. The overlap allows an initially partial current hour to be replaced as later quarter-hour files arrive without treating the cut-off leading hour as complete.

An exclusive local lock skips overlapping runs. Before raw retention runs, every cleaned article is upserted into the permanent compressed archive and the newly written file is verified. An archive or later processing failure aborts the cycle without pruning raw data. Only after the complete refresh succeeds does raw retention total the compressed GDELT ZIP sizes and remove the oldest files until the cache fits the configured 10 GB budget. The newest processing window is always preserved even if a custom budget is too small. A local JSON status file records start, completion, last success, article-archive rows and bytes, download counts, retained raw files and bytes, the storage limit, pruned files, and failure messages. The Windows Scheduled Task invokes this runner every 15 minutes indefinitely and can be removed independently of project data.

## Key decisions and limits

- `seen_at` is the GDELT processing timestamp and is stored as a timezone-naive UTC value for cross-platform compatibility.
- The default flood filter keeps explicit flood/flooding/floods themes and excludes weak-only matches such as metaphorical `FLOODED` or World Bank policy themes. Weak matches remain available through `--minimum-strength weak` for recall studies.
- Exact canonical URL duplicates are removed. A conservative URL-slug heuristic groups obvious cross-domain copies but does not delete them; embeddings or MinHash remain a later improvement.
- The primary-location heuristic prefers valid coordinates, geographic specificity, repeated mentions, and then the earliest mention. Repeated mentions of the same region can create a dominant assignment. Equal top region counts are explicitly ambiguous and cannot enter a named regional aggregate. Questionable coordinates remain visible through quality flags.
- Raw downloads are immutable. Reprocessing should create a new cleaned output instead of altering the source file.
- Anomaly baselines include zero-filled hours and exclude the current observation to avoid survivorship bias and future leakage.
- Every component runs locally with free software. No credentials, cloud accounts, or paid APIs are used.
