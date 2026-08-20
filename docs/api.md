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

The default address is `http://127.0.0.1:8080`, and the default allowed dashboard origin is `http://localhost:3000`. The API reads `%USERPROFILE%\.crisispulse\dashboard.json`, which the refresh runner replaces after each successful cycle, and appends decisions to `%USERPROFILE%\.crisispulse\reviews.jsonl`. Override these locations with `scripts\run-api.ps1 -DataPath <path> -ReviewPath <path>` when needed.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Confirm the API process is available. |
| `GET` | `/api/v1/snapshot` | Return the complete dashboard snapshot. |
| `GET` | `/api/v1/signals` | Return the update time, candidate count, and supported signal rows. |
| `GET` | `/api/v1/reviews` | Return the latest saved decision for each reviewed signal. |
| `POST` | `/api/v1/reviews` | Append a validated review decision to the local audit log. |

### Health response

```json
{
  "service": "crisispulse-api",
  "status": "ok"
}
```

### Save a review decision

```json
{
  "region_code": "US:USMN",
  "window_start": "2026-08-20T21:00:00",
  "decision": "confirmed_event"
}
```

`decision` must be `confirmed_event`, `irrelevant_news`, or `uncertain`. Posting another decision for the same region and hour preserves the earlier audit entry while making the latest value current.

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
- Snapshot responses use `Cache-Control: no-store` and are capped at 2 MiB.
- Review requests are capped at 16 KiB, the append-only review log is capped at 4 MiB, and untrusted browser origins are rejected before writes.
- Internal file paths and parser errors are logged locally but not returned to callers.
- The API writes only the local review log. It has no remote accounts, paid services, or public network listener.
- A `confirmed_event` review is a human label for model evaluation; it is not an emergency warning.
- The dashboard falls back to its bundled verified snapshot if the API cannot be reached.
