# CrisisPulse dashboard

This local React dashboard turns the latest CrisisPulse Parquet and JSON outputs into a readable evidence screen. It shows candidate counts, scoring readiness, supported regional signals, data coverage, and a human-review queue with the guardrails behind every decision.

When the local Go API is running on port 8080, the development server forwards same-origin `/api/*` requests to it. The header reports `Live API connected` and the screen uses `%USERPROFILE%\.crisispulse\dashboard.json`, refreshed by the automatic pipeline. If the service is stopped or unavailable, it reports `Verified local snapshot` and continues to show the last versioned result instead of failing blank.

The committed `data/dashboard.json` snapshot comes from the real seven-day validation. Refresh it after a history run with:

```powershell
.\.venv\Scripts\python.exe -m pipelines.export_dashboard `
  --clean data/clean/flood_articles_batch.parquet `
  --features data/history/hourly_region_features.parquet `
  --anomalies data/features/hourly_region_anomalies.parquet `
  --anomaly-report data/features/hourly_region_anomaly_report.json `
  --output dashboard/data/dashboard.json
```

From this directory, run `npm install` once and `npm run dev` to open the local dashboard. From the repository root, `scripts\run-api.ps1` starts the API. Candidate labels are stored in `%USERPROFILE%\.crisispulse\reviews.jsonl`; the dashboard never writes into the repository. `npm test` builds the production bundle and verifies the server-rendered fallback screen.

The dashboard requires no paid API. A candidate represents unusual news reporting that needs human review; even a saved `Real event` label is evaluation data, not a public warning or proof issued by CrisisPulse.
