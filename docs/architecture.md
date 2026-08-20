# CrisisPulse starter architecture

## Goal

This starter proves the first local data path for CrisisPulse: ingest or load GDELT GKG records, isolate flood reporting, clean the useful fields, and create a queryable Parquet dataset. It deliberately excludes cloud infrastructure, dashboards, anomaly detection, and machine learning.

## Data flow

```text
Included sample TSV                         Optional live GDELT index
        |                                             |
        |                                      Go ingestor
        |                                  1–96 consecutive files
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
                  +----------+-----------+
                  |                      |
                  v                      v
          DuckDB hourly counts    ADM1/hour gold features
                                         |
                                         v
                               JSON inspection report
```

## Components

### Go ingestor

The ingestor reads GDELT's `lastupdate.txt`, selects the newest GKG ZIP, and can derive up to 96 consecutive 15-minute URLs ending at that file. Downloads use a temporary file followed by an atomic rename. Every new file receives a SHA-256 checksum and an entry in `manifest.jsonl`. Existing destinations report `already_present` and are not downloaded again.

### Python cleaner

The cleaner accepts one or more official headerless GKG ZIP/TSV files or compact headered fixtures. Batch mode keeps one article-identity set across the entire window. It:

1. Classifies explicit disaster themes as high-confidence and ambiguous theme-only matches as weak.
2. Canonicalizes HTTP(S) URLs and removes common tracking parameters.
3. Hashes the canonical URL to form a stable article ID.
4. Removes exact canonical-URL duplicates and groups likely cross-domain copies using a conservative URL-slug and six-hour heuristic.
5. Parses all nine GDELT enhanced-location fields and chooses a primary location.
6. Preserves questionable records with quality flags.
7. Writes a compressed Parquet file.

### DuckDB analysis

The first analysis groups cleaned records by GDELT processing hour, disaster type, and primary location. It reports article counts and unique source-domain counts without requiring a database server.

### Gold feature builder

The first gold layer uses `country_code:adm1_code` as the region key, falling back to country and then `UNKNOWN`. For every region, disaster type, and UTC hour it stores raw and high/weak article counts, unique domains, estimated unique stories, duplicate ratio, average tone, and story/domain velocity when the immediately preceding hour exists.

## Key decisions and limits

- `seen_at` is the GDELT processing timestamp and is stored as a timezone-naive UTC value for cross-platform compatibility.
- The default flood filter keeps explicit flood/flooding/floods themes and excludes weak-only matches such as metaphorical `FLOODED` or World Bank policy themes. Weak matches remain available through `--minimum-strength weak` for recall studies.
- Exact canonical URL duplicates are removed. A conservative URL-slug heuristic groups obvious cross-domain copies but does not delete them; embeddings or MinHash remain a later improvement.
- The primary-location heuristic prefers valid coordinates, geographic specificity, repeated mentions, and then the earliest mention. Repeated mentions of the same place count as one distinct location; questionable coordinates remain visible through quality flags.
- Raw downloads are immutable. Reprocessing should create a new cleaned output instead of altering the source file.
- Every component runs locally with free software. No credentials, cloud accounts, or paid APIs are used.
