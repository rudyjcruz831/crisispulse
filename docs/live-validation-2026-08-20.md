# Live GDELT validation — 2026-08-20

This validation exercised the local CrisisPulse pipeline against one real 15-minute GDELT GKG 2.1 update. The source ZIP and generated Parquet file remain local and are excluded from Git.

## Source

| Item | Value |
|---|---|
| GKG timestamp | `20260820144500` |
| Compressed size | `6,236,676` bytes |
| GDELT index MD5 | `9ded6d2e364fcdc5ce93dd45611f29ea` |
| Local SHA-256 | `838317cdff3637343661012f8ebf91a88b043b621f3fb257ea8d057ee9866ef6` |

The downloaded size and MD5 matched the values published in GDELT's update index. A second ingestor run returned `already_present`, demonstrating file-level idempotency.

## Results

| Measurement | Result |
|---|---:|
| Input GKG rows | 1,467 |
| Broad flood-theme matches | 28 |
| Weak-only rows skipped | 13 |
| High-confidence output rows | 15 |
| Unique source domains | 14 |
| GDELT country codes | 6 |
| Estimated unique stories | 13 |
| Articles in syndicated groups | 3 |
| Missing primary locations | 3 |
| Invalid coordinate flags | 0 |
| Multiple-location articles | 11 |

These figures describe one small time window and are engineering-validation results, not estimates of disaster frequency or model accuracy.

## Findings and changes

1. Live `V2ENHANCEDLOCATIONS` entries contain nine fields, including ADM2 before latitude and longitude. The original sample omitted ADM2, shifting live coordinates. The parser, fixture, data dictionary, and regression tests now use the nine-field layout.
2. `NATURAL_DISASTER_FLOODED` often appeared in metaphorical reporting. The cleaner now labels theme matches as `high` or `weak` and defaults to high-confidence rows. Broad recall studies can use `--minimum-strength weak`.
3. Obvious syndicated copies shared long URL title slugs across domains. The cleaner now assigns a conservative six-hour story group while preserving every source article.
4. GDELT's data host currently serves the working update feed over HTTP; the Go ingestor uses that published endpoint, stores files immutably, and records a local SHA-256 checksum. This protects reproducibility but is not transport authenticity.

## Reproduce locally

```powershell
docker compose --profile live run --rm ingestor

.\.venv\Scripts\python.exe -m pipelines.clean_gkg `
  --input data/raw/20260820144500.gkg.csv.zip `
  --output data/clean/20260820144500_flood_articles.parquet `
  --disaster flood `
  --minimum-strength high

.\.venv\Scripts\python.exe -m pipelines.inspect_clean `
  --input data/clean/20260820144500_flood_articles.parquet
```

## Next validation

Process several consecutive updates, manually label a small sample of high and weak matches, and calculate duplicate-adjusted regional/hourly features. A single update is insufficient for anomaly thresholds or precision estimates.
