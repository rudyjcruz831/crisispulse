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
| `GET` | `/api/v1/quality/articles` | Return the current review-aware Smart Review Queue, sampling intent, and any saved decisions. |
| `POST` | `/api/v1/quality/articles` | Append a validated relevance decision for an article in the current sample. |
| `GET` | `/api/v1/quality/articles/summary` | Return guarded article-filter quality measurements and review progress. |
| `GET` | `/api/v1/quality/articles/export.csv` | Download the latest article relevance decision per article as CSV. |
| `GET` | `/api/v1/training/articles` | Return the latest article label per article with deterministic training eligibility and class counts. |
| `GET` | `/api/v1/training/articles/export.csv` | Download the latest eligible and excluded article labels as an Excel-compatible audit CSV. |
| `GET` | `/api/v1/training/status` | Return a bounded, sanitized summary of the latest local article-baseline report. |
| `GET` | `/api/v1/training/external-datasets` | Return the fail-closed external dataset audit registry. |

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

The Smart Review Queue contains up to 24 safe publisher links from distinct story groups, drawn deterministically from recent permanent history. It preserves unfinished cards during the UTC day, removes completed version-2 decisions, replenishes open positions after a refresh, and prioritizes legacy re-labeling plus the class, chronological-split, date, publisher, and inference-text gaps blocking the first local CPU smoke test. When authoritative readiness is unavailable it falls back to the earlier balanced strong-match, headline-conflict, and ambiguous-match order.

The response's top-level `selection_intent` describes the current dataset and active thresholds. Each article can include a ranked `selection_intent` with an estimated `sampling_split` and neutral selection reasons. Internal class-balancing guesses are intentionally omitted so the API and dashboard cannot anchor the human reviewer. Version 1 sample files remain readable during deployment rollover, while version 2 metadata is strictly validated before the API returns it. A valid version 2 response may contain an empty `articles` array when the current queue is complete.

Version 2 article-review `POST` requests accept exactly `reported_flooding`, `flood_risk_warning`, `heavy_rain_only`, `not_flood_related`, or `uncertain` for an article in the current sample. Every new request must send `review_protocol_version: 1`; this does not change `decision_schema_version: 2` or add a fifth resolved target. The server copies article identity, evidence, and `title_source` provenance from the server-side sample rather than trusting browser-supplied metadata. Older records without protocol or title provenance remain readable.

A resolved protocol-1 request is shaped like:

```json
{
  "article_id": "0000000000000000000000000000000000000000000000000000000000000000",
  "decision": "reported_flooding",
  "review_protocol_version": 1,
  "review_basis": "full_article",
  "headline_support": "sufficient",
  "impact_flags": ["transport_disruption"],
  "context_flags": ["aftermath_recovery"]
}
```

`review_basis` is required on every protocol-1 review and must be `full_article`, `publisher_summary`, `headline_only`, or `unavailable`. `unavailable` is restricted to `uncertain`. `headline_support` is required on each resolved decision and must be `sufficient`, `body_required`, or `conflicts_with_body`; it is forbidden on `uncertain`, and a resolved `headline_only` review must be `sufficient`.

`not_flood_related` additionally requires exactly one `no_signal_reason`: `flood_context_analysis`, `other_weather_non_flood`, or `unrelated_false_match`. `uncertain` instead requires exactly one `uncertainty_reason`: `access_blocked`, `page_unavailable`, `wrong_or_junk_page`, `multi_story_page`, `language_barrier`, or `insufficient_or_conflicting`. Each reason field is forbidden on every other decision.

Resolved requests may include unique closed-vocabulary arrays. `impact_flags` accepts `fatality`, `injury`, `evacuation_displacement`, `rescue_search`, `property_crop_damage`, `transport_disruption`, and `utility_disruption`. `context_flags` accepts `aftermath_recovery`, `climate_background`, `historical_background`, and `policy_preparedness`. Both arrays are forbidden on `uncertain`; an omitted flag is unrecorded, not confirmed absent. Protocol-1 requests reject the historical free-form `tags` field. Existing records with tags remain readable and exportable but are not silently converted to controlled flags.

The labels follow a fixed precedence for the main article's central claim: reported physical flooding first; otherwise an explicit flood forecast, watch, warning, or risk; otherwise heavy rain or severe weather without explicit flood evidence; otherwise no actionable flood/rain signal. Incidental historical mentions and surrounding page cards do not invoke precedence. `uncertain` is reserved for a recorded access, page, language, structure, or evidence limitation. The first four labels are resolved classes. `uncertain` is retained but excluded from rate denominators. Human review is blind to internal guessed classes and model predictions; see [the article review protocol](article-review-protocol.md).

Historical records with no schema-version field are version 1 and may contain `relevant`, `not_relevant`, or `uncertain`. They remain in the append-only audit log and are not silently converted into detailed classes. The CSV contains the latest decision per article, so an unsuperseded version 1 answer remains visible there while a corrected article exports its current version 2 answer. The current sample presents version 1 answers for re-review. A new version 2 answer appends a correction and becomes the latest decision without deleting the older audit record.

Strong-match and blocked-match flood-related rates count `reported_flooding` plus `flood_risk_warning` in the numerator. They remain `null` until at least 20 version 2 decisions are resolved and both the strong and blocked strata contain at least five resolved reviews. The sample is deliberately balanced, so its combined class share is not an estimate of production prevalence or overall accuracy. Protocol fields and controlled flags are secondary audit/slice data; they do not change alerts or enter rate calculations. The quality CSV is a versioned latest-label audit export; the separate Training Data Lab view below adds explicit training eligibility. Neither export is consumed by an automatic model-training job.

### Training Data Lab

`GET /api/v1/training/articles` is a read-only, schema-versioned view of the article-review audit log. It returns one row per `article_id`, using only that article's latest appended decision. Correcting a label does not rewrite or delete the earlier JSONL record; the correction is appended to `article-reviews.jsonl` and becomes the row exposed by this endpoint.

```json
{
  "schema_version": 1,
  "summary": {
    "total_articles": 3,
    "training_eligible": 1,
    "excluded": 2,
    "class_counts": {
      "reported_flooding": 1,
      "flood_risk_warning": 0,
      "heavy_rain_only": 0,
      "not_flood_related": 0
    },
    "exclusion_reason_counts": {
      "legacy_schema": 1,
      "uncertain": 1
    }
  },
  "articles": [
    {
      "article_id": "0000000000000000000000000000000000000000000000000000000000000000",
      "title": "Flood closes local road",
      "title_source": "publisher_metadata",
      "url": "https://news.example/flood-closes-road",
      "source_domain": "news.example",
      "match_strength": "high",
      "review_bucket": "high_match",
      "decision": "reported_flooding",
      "decision_schema_version": 2,
      "review_protocol_version": 1,
      "review_basis": "full_article",
      "headline_support": "sufficient",
      "impact_flags": ["transport_disruption"],
      "context_flags": [],
      "reviewed_at": "2026-08-24T12:00:00Z",
      "training_eligible": true,
      "exclusion_reason": ""
    }
  ]
}
```

Eligibility is deterministic and does not imply that the sample is large enough to train a useful model:

- Version 2 `reported_flooding`, `flood_risk_warning`, `heavy_rain_only`, and `not_flood_related` decisions are eligible. `class_counts` counts only these eligible latest labels and always includes all four class keys, including zero counts.
- A version 2 `uncertain` decision is excluded with `exclusion_reason: "uncertain"`.
- A version 1 decision is excluded with `exclusion_reason: "legacy_schema"`, including historical records that originally omitted the schema-version field.
- A resolved protocol-1 decision with `headline_support: "body_required"` or `"conflicts_with_body"` is excluded from the current headline-only model with `exclusion_reason: "headline_not_sufficient"`.
- Every article row includes `training_eligible` and `exclusion_reason`. Eligible rows use an empty exclusion reason. `summary.total_articles` includes eligible and excluded rows.

`GET /api/v1/training/articles/export.csv` exports the same latest-label audit population, including excluded rows. To preserve spreadsheet compatibility, its original 13 columns keep their positions and the protocol columns are appended. The exact order is `article_id`, `title`, `title_source`, `url`, `source_domain`, `match_strength`, `review_bucket`, `decision`, `decision_schema_version`, `reviewed_at`, `tags`, `training_eligible`, `exclusion_reason`, `review_protocol_version`, `review_basis`, `headline_support`, `no_signal_reason`, `uncertainty_reason`, `impact_flags`, and `context_flags`.

The article-quality CSV follows the same append-only evolution. Its exact order is `article_id`, `title`, `title_source`, `url`, `source_domain`, `match_strength`, `review_bucket`, `decision`, `decision_schema_version`, `reviewed_at`, `tags`, `review_protocol_version`, `review_basis`, `headline_support`, `no_signal_reason`, `uncertainty_reason`, `impact_flags`, and `context_flags`. Array values are pipe-separated. Historical tags remain present only for backward-compatible audit.

CSV files use a UTF-8 byte-order mark and CRLF rows for Excel compatibility. Cells derived from publisher or reviewer data are protected against spreadsheet formula execution: dangerous leading `=`, `+`, `-`, `@`, tab, or carriage-return characters are prefixed with an apostrophe. Both training endpoints use `Cache-Control: no-store`; the CSV export does not modify review history.

### Training status

`GET /api/v1/training/status` reads the fixed `article-baseline-report.json` file beside the configured review log and returns only fields needed by the Training Data Lab. The response includes the report status and creation time, whether fitting actually happened, an evaluation tier when applicable, the dataset fingerprint, review/resolved/usable counts, exclusions, four-class counts before and after inference-text filtering, sanitized chronological split metadata and class counts, and the production and non-evaluative smoke-test gates. A validated trained report also includes an optional `results` object containing the fixed model type and feature count, bounded CPU/runtime metadata, validation and test evaluation summaries, dummy and frozen-rule baselines, abstention counts, and at most eight aggregate off-diagonal confusion pairs under `representative_mistakes`. Private input and prediction paths, test slices, article text, article identifiers, URLs, and arbitrary report fields are not returned.

The report is capped at 512 KiB and must use a supported report schema (currently 1 or 2) and the native CrisisPulse article-review contract. Counts, class keys, exclusion reasons, split boundaries and leakage flags, fixed gate names/minimums, gate outcomes, readiness states, and training status must agree with one another. For trained reports, every published score and support count must also agree with the fixed-order confusion matrices and split counts; runtime and abstention metadata are similarly bounded and cross-checked. A missing report returns `404` with `training status report not found`. Empty, oversized, malformed, unsupported, or internally inconsistent reports fail closed with `503` and the fixed public message `training status report unavailable`; details remain only in private API logs. The endpoint accepts only `GET` and `HEAD` and uses `Cache-Control: no-store`.

A readiness-only report with too little data returns a summary shaped like:

```json
{
  "report_schema_version": 1,
  "status": "not_ready",
  "training_performed": false,
  "created_at": "2026-08-25T12:00:00+00:00",
  "latest_review_count": 46,
  "resolved_schema_v2_count": 20,
  "usable_training_rows": 19,
  "exclusion_counts": {"missing_inference_text": 1, "legacy_schema": 26},
  "class_counts_before_text_filter": {
    "reported_flooding": 5,
    "flood_risk_warning": 5,
    "heavy_rain_only": 2,
    "not_flood_related": 8
  },
  "class_counts_after_text_filter": {
    "reported_flooding": 5,
    "flood_risk_warning": 5,
    "heavy_rain_only": 2,
    "not_flood_related": 7
  },
  "split": {
    "computable": false,
    "reason": "insufficient_data_for_leakage_safe_split",
    "story_rows_promoted_to_newer_split": 0,
    "earlier_rows_purged_for_final_publishers": 0,
    "story_overlap_after_purge": false,
    "final_publisher_overlap_after_purge": false,
    "training_rows": 0,
    "validation_rows": 0,
    "test_rows": 0,
    "class_counts": {}
  },
  "production_readiness": {
    "ready": false,
    "gates": [
      {"name": "total_usable_rows", "actual": 19, "minimum": 500, "passed": false},
      {"name": "minimum_rows_in_each_class", "actual": 2, "minimum": 100, "passed": false},
      {"name": "distinct_article_dates", "actual": 4, "minimum": 30, "passed": false},
      {"name": "publisher_groups", "actual": 12, "minimum": 100, "passed": false},
      {"name": "inference_text_coverage", "actual": 0.95, "minimum": 0.95, "passed": true},
      {"name": "leakage_safe_split_computable", "actual": false, "minimum": true, "passed": false}
    ]
  },
  "smoke_test_readiness": {
    "ready": false,
    "gates": [
      {"name": "total_usable_rows", "actual": 19, "minimum": 16, "passed": true},
      {"name": "minimum_rows_in_each_class", "actual": 2, "minimum": 4, "passed": false},
      {"name": "distinct_article_dates", "actual": 4, "minimum": 3, "passed": true},
      {"name": "publisher_groups", "actual": 12, "minimum": 12, "passed": true},
      {"name": "inference_text_coverage", "actual": 0.95, "minimum": 1.0, "passed": false},
      {"name": "leakage_safe_split_computable", "actual": false, "minimum": true, "passed": false}
    ]
  },
  "blocked_reason": "readiness_gates_not_met"
}
```

### External dataset audit

`GET /api/v1/training/external-datasets` returns the versioned, read-only audit registry for candidate third-party training datasets. Each entry records its source URL or DOI, current access and license state, whether article text is actually available, the source label type, an explicit mapping to CrisisPulse labels, import and training decisions, supporting evidence, notes, and the date those facts were last checked.

The registry is fail-closed. A public download does not count as training permission, `license_training_approved` remains false when `license_state` is `unknown`, and every unknown license must use the `blocked` training decision. Training approval additionally requires a verified permissive license, available article text, and labels with more than low compatibility. External labels retain provenance and cannot silently become native CrisisPulse ground truth; a separate native holdout remains required.

The version-controlled source is `cmd/api/data/external-dataset-audit.v1.json`. Unknown JSON fields, unrecognized audit states, duplicate dataset IDs, malformed evidence links, and unsafe license/training combinations make the registry unavailable rather than weakening these rules. The endpoint accepts only `GET` and `HEAD` and uses `Cache-Control: no-store`.

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
