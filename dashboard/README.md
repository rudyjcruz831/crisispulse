# CrisisPulse dashboard

This local React dashboard turns the latest CrisisPulse Parquet and JSON outputs into a readable evidence screen. It shows candidate counts, scoring readiness, supported regional signals, data coverage, and the guardrails behind every decision.

The committed `data/dashboard.json` snapshot comes from the real seven-day validation. Refresh it after a history run with:

```powershell
.\.venv\Scripts\python.exe -m pipelines.export_dashboard `
  --clean data/clean/flood_articles_batch.parquet `
  --features data/history/hourly_region_features.parquet `
  --anomalies data/features/hourly_region_anomalies.parquet `
  --anomaly-report data/features/hourly_region_anomaly_report.json `
  --output dashboard/data/dashboard.json
```

From this directory, run `npm install` once and `npm run dev` to open the local dashboard. `npm test` builds the production bundle and verifies the server-rendered evidence screen.

The first version is intentionally read-only and requires no paid API. A candidate represents unusual news reporting that needs human review; it is never presented as proof that a physical disaster occurred.
