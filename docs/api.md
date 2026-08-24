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

The read-only admin response reports API availability, refresh health, the last successful refresh, the next expected 15-minute refresh, permanent archived-article count and compressed size, and bounded raw-file counts. A refresh is marked `degraded` when the latest recorded run failed or the last success is more than 30 minutes old. Local paths, filenames, credentials, and raw error details are never returned.

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

The daily sample contains 24 safe publisher links drawn deterministically from recent permanent history: eight strong matches, eight weak headline conflicts, and eight other ambiguous matches when each group has enough rows. `POST` accepts only `relevant`, `not_relevant`, or `uncertain` for an article in the current sample. The API copies the system classification from the server-side sample rather than trusting browser-supplied metadata.

Strong-match relevance and weak-match relevance remain `null` until at least 20 decisions are resolved and both the strong and blocked strata contain at least five resolved reviews. The sample is deliberately balanced, so its combined relevant/not-relevant ratio is not an estimate of production prevalence or overall accuracy.

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
- The admin-status route is read-only, capped at 64 KiB, and exposes only a fixed allowlist of operational fields.
- Snapshot responses use `Cache-Control: no-store` and are capped at 2 MiB.
- Signal evidence is limited to eight distinct story groups and eight validated HTTP(S) publisher links per story.
- Review requests are capped at 16 KiB, the append-only review log is capped at 4 MiB, and untrusted browser origins are rejected before writes.
- The CSV export is generated from validated local records and contains only the latest decision per signal.
- Internal file paths and parser errors are logged locally but not returned to callers.
- By default the API writes only the local review log and has no public network listener. In the optional single-server package it remains private on the container network; Caddy is the only public listener and requires the shared pilot login for every route except health checks.
- A `confirmed_event` review is a human label for model evaluation; it is not an emergency warning.
- The dashboard falls back to its bundled verified snapshot if the API cannot be reached.
