# CrisisPulse local API

The local Go service exposes the latest dashboard snapshot and stores human review decisions. It uses only the Go standard library and reads the runtime JSON file on each request, so the history pipeline can refresh data without restarting the service.

## Start locally

Install the pinned portable Go toolchain once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-go.ps1
```

Start the API from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-api.ps1
```

The default address is `http://127.0.0.1:8080`, and the default allowed dashboard origin is `http://localhost:3000`. The `--allowed-origin` flag also accepts an exact, comma-separated origin list, which lets the protected `http://localhost:8088` address and the loopback-only `http://localhost:3000` preview submit reviews without allowing arbitrary browser origins. The API reads `%USERPROFILE%\.crisispulse\dashboard.json`, which the refresh runner replaces after each successful cycle, and appends decisions to `%USERPROFILE%\.crisispulse\reviews.jsonl`. Override these locations with `scripts\run-api.ps1 -DataPath <path> -ReviewPath <path>` when needed.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` or `/api/v1/health` | Confirm the API process is available. |
| `GET` | `/api/v1/admin/status` | Return sanitized refresh health, permanent-article counts, and raw-storage usage for the local admin page. |
| `GET` | `/api/v1/snapshot` | Return the complete dashboard snapshot, including bounded source evidence for displayed signals. |
| `GET` | `/api/v1/signals` | Return the update time, candidate count, and supported signal rows. |
| `GET` | `/api/v1/reviews` | Return the latest saved decision for each reviewed signal. |
| `POST` | `/api/v1/reviews` | Append a validated review decision to the local audit log. |
| `GET` | `/api/v1/reviews/summary` | Return label counts and sample-readiness metrics. |
| `GET` | `/api/v1/reviews/export.csv` | Download the latest decision for each reviewed signal as CSV. |
| `GET` | `/api/v1/quality/articles` | Return the current balanced daily article sample with any saved decisions. |
| `POST` | `/api/v1/quality/articles` | Append a validated relevance decision for an article in the current sample. |
| `GET` | `/api/v1/quality/articles/summary` | Return guarded article-filter quality measurements and review progress. |
| `GET` | `/api/v1/quality/articles/export.csv` | Download the latest article relevance decision per article as CSV. |

### Health response

```json
{
  "service": "crisispulse-api",
  "status": "ok"
}
```

### Admin status

The read-only admin response reports API availability, refresh health, the last successful refresh, the next expected 15-minute refresh, permanent archived-article count and compressed size, bounded raw-file counts, verified-backup freshness, and a server-calculated 48-hour reliability check. A normal `running` refresh remains healthy while its prior success is current and the run is younger than 15 minutes; a failed, stalled, or more-than-30-minute-old refresh is degraded. Raw pipeline errors are replaced with fixed safe messages, so local paths, filenames, credentials, source URLs, and parser details are never returned.

`refresh.soak` advances only when a refresh finishes. It passes after 48 observed hours with at least 95% of expected 15-minute runs. A failed or interrupted attempt or a gap longer than 30 minutes restarts the active proof, while lifetime failure/missed/interrupted counters remain visible. Time while the computer is asleep does not count. `pilot_readiness.status` can become `ready_for_pilot_setup` only when that proof is current and the latest integrity-checked backup is less than 26 hours old. This means setup may begin; it is not a customer-readiness or public-launch claim.

Readiness is fail-closed: the API enforces the versioned 48-hour/15-minute policy, requires the reliability record to end at the same recent success used for current refresh health, rejects future or inconsistent timestamps, and accepts only a current backup whose application data passed JSON, JSONL, and Parquet validation.

### Save a review decision

```json
{
  "region_code": "US:USMN",
  "window_start": "2026-08-20T21:00:00",
  "decision": "confirmed_event"
}
```

`decision` must be `confirmed_event`, `irrelevant_news`, or `uncertain`. Posting another decision for the same region and hour preserves the earlier audit entry while making the latest value current.

### Review-quality summary

The summary counts only the latest decision for each stable signal ID. `confirmed_event_rate` and `irrelevant_news_rate` remain `null` until at least 20 reviews are resolved as either `confirmed_event` or `irrelevant_news`; `uncertain` labels remain in the dataset but do not count toward that minimum. These rates describe human review outcomes, not externally verified disaster accuracy.

### Article-filter quality

The daily sample contains 24 safe publisher links drawn deterministically from recent permanent history: eight strong matches, eight weak headline conflicts, and eight other ambiguous matches when each group has enough rows. Version 2 article-review `POST` requests accept exactly `reported_flooding`, `flood_risk_warning`, `heavy_rain_only`, `not_flood_related`, or `uncertain` for an article in the current sample. They may also carry up to eight optional custom context tags. The server normalizes each tag to a distinct lowercase Unicode letter/digit slug of at most 32 characters, writes `decision_schema_version: 2`, and copies the system classification from the server-side sample rather than trusting browser-supplied metadata.

The labels follow a fixed precedence: reported physical flooding first; otherwise an explicit flood forecast, watch, warning, or risk; otherwise heavy rain or severe weather without explicit flood evidence; otherwise not flood-related. `uncertain` is reserved for unavailable, contradictory, or insufficient evidence. The first four labels are resolved training classes. `uncertain` is retained but excluded from rate denominators.

Historical records with no schema-version field are version 1 and may contain `relevant`, `not_relevant`, or `uncertain`. They remain in the append-only audit log and are not silently converted into detailed classes. The CSV contains the latest decision per article, so an unsuperseded version 1 answer remains visible there while a corrected article exports its current version 2 answer. The current sample presents version 1 answers for re-review. A new version 2 answer appends a correction and becomes the latest decision without deleting the older audit record.

Strong-match and blocked-match flood-related rates count `reported_flooding` plus `flood_risk_warning` in the numerator. They remain `null` until at least 20 version 2 decisions are resolved and both the strong and blocked strata contain at least five resolved reviews. The sample is deliberately balanced, so its combined class share is not an estimate of production prevalence or overall accuracy. Custom tags are secondary context rather than measurement classes and do not change alerts or rate calculations. The CSV is a versioned, training-ready latest-label export and includes pipe-separated tags; it is not yet consumed by an automatic model-training job.

### Signals response

```json
{
  "updated_label": "Aug 20, 19:00 UTC",
  "candidate_anomalies": 0,
  "signals": [
    {
      "region": "Hawaii, United States",
      "code": "US:USHI",
      "window_start": "2026-08-20T19:00:00",
      "stories": 5,
      "domains": 5,
      "baseline": 4.0,
      "score": 0.22,
      "status": "normal",
      "status_label": "Normal"
    }
  ]
}
```

## Safety and scope

- Snapshot and signal routes remain read-only. The review route accepts only `GET`, `HEAD`, and validated JSON `POST` requests.
- The admin-status source is read-only, capped at 256 KiB, and exposes only a fixed allowlist of operational fields. The persisted run ledger itself is capped at 256 terminal records.
- Snapshot responses use `Cache-Control: no-store` and are capped at 2 MiB.
- Signal evidence is limited to eight distinct story groups and eight validated HTTP(S) publisher links per story.
- Review requests are capped at 16 KiB, the append-only review log is capped at 4 MiB, and untrusted browser origins are rejected before writes.
- The CSV export is generated from validated local records and contains only the latest decision per signal.
- Internal file paths and parser errors are logged locally but not returned to callers.
- By default the API writes only the local review log and has no public network listener. In the optional single-server package it remains private on the container network; Caddy is the only public listener and requires the shared pilot login for every route except health checks.
- A `confirmed_event` review is a human label for model evaluation; it is not an emergency warning.
- The dashboard falls back to its bundled verified snapshot if the API cannot be reached.
