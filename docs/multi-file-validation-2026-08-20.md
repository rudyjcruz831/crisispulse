# Multi-file aggregation validation — 2026-08-20

This validation covers eight consecutive 15-minute GDELT GKG 2.1 updates from 16:00 through 17:45 UTC. Raw ZIPs, clean Parquet data, feature Parquet data, and generated JSON reports remain local and are excluded from Git.

## Pipeline run

```text
8 GKG ZIP files
      ↓
12,886 raw rows
      ↓ flood-theme classification
200 broad matches (152 high, 48 weak)
      ↓ canonical URL deduplication + story grouping
156 estimated stories from 155 source domains
      ↓ ADM1/hour aggregation
98 region/hour feature rows across 2 hours and 81 regions
```

## Clean-data results

| Measurement | Result |
|---|---:|
| Input files | 8 |
| Input rows | 12,886 |
| Broad flood matches | 200 |
| High-confidence matches | 152 |
| Weak matches | 48 |
| Unique source domains | 155 |
| Estimated unique stories | 156 |
| Articles in syndicated groups | 55 |
| Missing primary locations | 24 |
| Invalid coordinate flags | 0 |
| Multiple-location articles | 161 |

## Gold feature results

| Measurement | Result |
|---|---:|
| Hourly windows | 2 |
| Regions | 81 |
| Region/hour rows | 98 |
| Minimum observed story velocity | -10 |
| Maximum observed story velocity | +2 |

The initial region key is GDELT country plus ADM1 code, falling back to country and then `UNKNOWN`. These are GDELT/FIPS-style codes, not guaranteed ISO codes.

## What the report revealed

- A 28-domain syndicated story was reduced to one estimated story group, showing why raw article count alone is misleading.
- One region/hour had 30 articles but only three estimated stories and a duplicate ratio of `0.90`.
- The highest positive duplicate-adjusted velocities were `+2`, far smaller than the largest raw volumes.
- `UNKNOWN` remained a leading bucket because 24 articles had no usable primary location.
- A Hawaii-related syndicated story was associated with `US:USNH`, showing that a single primary-location heuristic can select a misleading place when an article mentions several locations.
- The first feature report exposed unsigned-integer underflow in negative velocity. Counts are now cast to signed integers, and a regression test requires a real `-1` velocity.

These results validate the mechanics, not signal accuracy. Two hours are not enough for an anomaly baseline.

## Location-quality follow-up

The next milestone reran the same eight files with conservative regional selection. A named region is now allowed only when all usable mentions agree or the leading region has at least twice as many mentions as the runner-up.

| Measurement | Result |
|---|---:|
| Single-region assignments | 29 |
| Mention-dominant assignments | 92 |
| Ambiguous regional assignments | 55 |
| Missing regional assignments | 24 |
| Articles routed to location review | 79 |
| Named/unknown feature rows | 67 |
| Feature regions including `UNKNOWN` | 56 |

The questionable Hawaii story still retains `Big Island, New Hampshire` as the selected audit value in clean data, but its tied candidate regions make the assignment ambiguous. It is now aggregated into `UNKNOWN`; the feature output contains zero `US:USNH` rows. This preserves the evidence without allowing a questionable primary-location choice to create a regional signal.

The generated 40-row review CSV contains ten rows from each of four buckets: high/assigned, high/location-review, weak/assigned, and weak/location-review. Its relevance, primary-region, and notes columns are intentionally blank for human labels.

## Reproduce locally

Download the most recent two-hour window:

```powershell
docker compose --profile live run --rm ingestor --intervals 8 --output-dir /app/data/raw
```

Run a chosen consecutive filename window through silver and gold layers:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-batch.ps1 `
  -Pattern '202608201[67]*.gkg.csv.zip'
```

Generated outputs:

```text
data/clean/flood_articles_batch.parquet
data/features/hourly_region_features.parquet
data/features/hourly_region_report.json
data/review/flood_manual_review.csv
```

## Next validation

Label the 40-row review CSV, measure disaster-match and regional-assignment quality by bucket, and use the results to tune the theme and location rules. Then collect enough hourly windows for a robust median/MAD baseline. No anomaly threshold should be presented as meaningful from this two-hour sample.
