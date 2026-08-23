# CrisisPulse dashboard

This local React dashboard turns the latest CrisisPulse Parquet and JSON outputs into a readable evidence screen. It shows candidate counts, scoring readiness, supported regional signals, data coverage, a human-review queue with direct publisher evidence, guarded review-quality metrics, and a six-hour Forecast Lab. A separate read-only operations console is available at `/admin`.

When the local Go API is running on port 8080, the development server forwards same-origin `/api/*` requests to it. The header reports `Live API connected` and the screen uses `%USERPROFILE%\.crisispulse\dashboard.json`, refreshed by the automatic pipeline. If the service is stopped or unavailable, it reports `Verified local snapshot` and continues to show the last versioned result instead of failing blank.

The committed `data/dashboard.json` snapshot comes from the real seven-day validation. Refresh it after a history run with:

```powershell
.\.venv\Scripts\python.exe -m pipelines.export_dashboard `
  --clean data/clean/flood_articles_batch.parquet `
  --features data/history/hourly_region_features.parquet `
  --anomalies data/features/hourly_region_anomalies.parquet `
  --anomaly-report data/features/hourly_region_anomaly_report.json `
  --outcome-report data/features/six_hour_outcome_report.json `
  --model-report data/features/media_spread_model_report.json `
  --output dashboard/data/dashboard.json
```

From this directory, run `npm install` once and `npm run dev` to open the local dashboard. From the repository root, `scripts\run-api.ps1` starts the API. Candidate labels are stored in `%USERPROFILE%\.crisispulse\reviews.jsonl`; the dashboard never writes into the repository. The review-quality section withholds rates until 20 resolved labels exist and offers the latest label per signal as a CSV download. `npm test` builds the production bundle and verifies the server-rendered fallback screen.

The admin page combines live refresh health, expected refresh time, retained-file counts, forecast clocks, model holdout metrics, review-sample progress, and paid-pilot readiness. It automatically checks the local API once per minute and presents all operational times in U.S. Eastern Time. It deliberately exposes no restart, deletion, billing, or access-management controls. Before deployment, `/admin` must be protected by private authentication.

The dashboard requires no paid API. Evidence is grouped by duplicate-adjusted story ID and links directly to retained publisher URLs. For the bounded set of visible stories, the refresh prefers a cached publisher-provided Open Graph, social, or HTML title. If the publisher blocks automated reading or the request is unsafe, slow, or unavailable, the interface derives a readable fallback from the URL while skipping trailing numeric IDs. Clear conflicts between that URL-derived wording and the GDELT flood tag are downgraded before scoring and cannot create an alert. A candidate represents unusual news reporting that needs human review; even a saved `Real event` label is evaluation data, not a public warning or proof issued by CrisisPulse.

Forecast Lab defines success as at least 20 source domains in any one of the next six completed hours. It keeps future data out of the prediction row, shows open outcome clocks, and displays the first model's performance on a later chronological holdout. The class-balanced model score is a ranking value, not a calibrated probability, and the target is media spread—not disaster occurrence or severity. See the [model card](../docs/model-card-media-spread.md) for the current evaluation and limitations.
