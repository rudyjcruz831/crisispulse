# Seven-day history validation — 2026-08-20

This validation processed 672 consecutive 15-minute GDELT GKG 2.1 updates from 2026-08-13 19:15 through 2026-08-20 19:00 UTC. Docker was unavailable, so the standard-library Python downloader fetched the same window and passed it through the normal batch pipeline.

## Pipeline run

```text
672 GKG ZIP files
       ↓
671,346 raw GKG rows
       ↓ flood-theme classification
13,231 broad matches
       ↓ exact URL deduplication
13,196 clean article rows
       ↓ story grouping + conservative regional assignment
4,020 observed region/hour feature rows
       ↓ compact history merge + zero-filled anomaly scoring
67,600 scored region/hour rows
```

## Clean-data results

| Measurement | Result |
|---|---:|
| Input files | 672 |
| Input rows | 671,346 |
| Broad flood matches | 13,231 |
| Exact duplicates removed | 35 |
| Clean output rows | 13,196 |
| Unique source domains | 2,790 |
| Estimated unique stories | 9,112 |
| Articles in syndicated groups | 4,649 |
| Multiple-location articles | 10,554 |

## Location-quality results

| Assignment status | Rows |
|---|---:|
| Single-region | 3,757 |
| Mention-dominant | 5,175 |
| Ambiguous | 2,830 |
| Missing | 1,434 |
| Routed to location review | 4,264 |

The generated 40-row review file contains 20 high-confidence and 20 weak theme matches, including 20 rows that require location review. These rows still need human labels before disaster relevance or regional assignment accuracy can be claimed.

## Feature and anomaly results

| Measurement | Result |
|---|---:|
| Observed feature rows | 4,020 |
| Hourly windows | 169 |
| Regions | 400 |
| Zero-filled scored rows | 67,600 |
| Insufficient-history rows | 67,200 |
| Below-minimum-support rows | 398 |
| Normal rows | 2 |
| Candidate anomalies | 0 |

Exactly seven days of quarter-hour inputs spans 169 hourly buckets at these boundaries. Consequently, only the final hour had the required 168 prior observations. The two supported rows in that hour were classified as normal:

| Region | High-confidence stories | Domains | Historical median | Historical MAD | Robust z-score |
|---|---:|---:|---:|---:|---:|
| `UNKNOWN` | 6 | 6 | 15.5 | 3.5 | -1.83 |
| `US:USHI` | 5 | 5 | 4.0 | 3.0 | 0.22 |

Zero candidates is a useful result: the seven-day gate opened without turning ordinary reporting into an alert. It does not mean that no floods occurred, because CrisisPulse measures unusual news reporting rather than physical hazards.

## Storage outcome

The multi-gigabyte raw ZIP cache was not retained after this validation run. Generated clean data, review data, and anomaly outputs remain local and ignored by Git. The compact 69 KB feature history is retained at `data/history/hourly_region_features.parquet`; future overlapping runs replace identical hour/region keys and add new hours without double-counting.

## Verification and next step

The Python suite passes 28 tests, including downloader ordering and idempotency, atomic history merging, anomaly history gating, regional ambiguity handling, and the end-to-end batch path. The Go seven-day limit has a unit test, but it could not be executed in this environment because Docker failed to start and a local Go runtime was unavailable.

The next useful validation is to run the history command regularly so the baseline contains many fully eligible hours, then inspect candidate stability and label the 40-row review set before tuning the theme, location, or alert thresholds.
