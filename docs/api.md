# CrisisPulse local API

The first API is a read-only Go service that exposes the latest versioned dashboard snapshot. It uses only the Go standard library and reads `dashboard/data/dashboard.json` on each request, so the history pipeline can refresh data without restarting the service.

## Start locally

Install the pinned portable Go toolchain once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-go.ps1
```

Start the API from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-api.ps1
```

The default address is `http://127.0.0.1:8080`, and the default allowed dashboard origin is `http://localhost:3000`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Confirm the API process is available. |
| `GET` | `/api/v1/snapshot` | Return the complete dashboard snapshot. |
| `GET` | `/api/v1/signals` | Return the update time, candidate count, and supported signal rows. |

### Health response

```json
{
  "service": "crisispulse-api",
  "status": "ok"
}
```

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

- The service accepts only `GET`, `HEAD`, and local CORS preflight requests.
- Snapshot responses use `Cache-Control: no-store` and are capped at 2 MiB.
- Internal file paths and parser errors are logged locally but not returned to callers.
- The API does not write data, authenticate users, call paid services, or claim that a candidate is a verified physical disaster.
- The dashboard falls back to its bundled verified snapshot if the API cannot be reached.
