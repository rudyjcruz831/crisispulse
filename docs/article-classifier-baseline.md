# Local article-classifier baseline

## What this runner does

`pipelines.train_article_classifier` is the guarded first step between human
labels and model training. Its default operation is a **readiness audit**: it
checks the data and writes a JSON report without fitting a model.

The runner is deliberately limited to the native CrisisPulse article-review
log. It does not accept arbitrary external datasets. Before Groundsource, a
research dataset, or another source can enter training, a separate importer
must document its license, schema, text availability, provenance, and an
explicit mapping to the four CrisisPulse classes.

The four supported training labels are:

- `reported_flooding`
- `flood_risk_warning`
- `heavy_rain_only`
- `not_flood_related`

Version-1 labels, version-2 `uncertain` decisions, unsupported labels, missing
archive rows, and rows without collection-time metadata or inference-safe text
are excluded and counted in the report. They are never silently fitted.

## Why the archive is required

`article-reviews.jsonl` is an append-only decision log. It does not duplicate
all collection metadata. The runner joins its latest decision per article to
`flood_articles_archive.parquet` to obtain:

- `seen_at`, used for chronological splitting instead of review time;
- `duplicate_group_id`, used to keep likely copies of one story together;
- `source_domain`, normalized into a publisher group; and
- text that is available through the same path at live inference.

An archive publisher title is used only when the archive records
`publisher_metadata` provenance. A review title can also be used when the API
recorded `title_source: publisher_metadata`, the review URL exactly equals the
archive URL, and the normalized review and archive publishers match. Otherwise
the runner uses the existing conservative URL-headline parser. It never
silently uses a manual title override, stored URL-path display text, or a
publisher title with unknown provenance.

Older reviews can be audited against the local publisher-title cache without
rewriting history. The following command is dry-run by default and reports how
many exact, live-path matches can receive a new append-only provenance record:

```powershell
.\.venv\Scripts\python.exe -m pipelines.backfill_review_title_sources `
  --reviews <path-to-article-reviews.jsonl> `
  --archive <path-to-flood_articles_archive.parquet> `
  --title-cache <path-to-publisher-title-cache.json>
```

After reviewing that count, repeat with `--apply`. The tool never accesses the
network or changes a label. It appends only when the cached publisher title,
review title, URL, and normalized publisher all match exactly; a second run is
idempotent.

## Run a readiness audit

```powershell
.\.venv\Scripts\python.exe -m pipelines.train_article_classifier `
  --reviews <path-to-article-reviews.jsonl> `
  --archive <path-to-flood_articles_archive.parquet> `
  --report outputs/article-baseline-readiness.json
```

This is safe to run at any dataset size. It does not train. The report lists
every gate and its actual and required values.

Report schema version 2 also records the newest review timestamp, a SHA-256
fingerprint of the exact prepared rows, and an aggregate geography summary.
The geography data contains only trusted single-region or dominant-region
coordinates from the permanent archive, grouped into at most 250 locations.
It deliberately excludes article IDs, titles, URLs, and publisher details.
These points describe places mentioned by articles; they are not verified
physical flood events. Version-1 reports remain readable but do not contain
the geography or newest-review fields.

For a preliminary CPU evaluation, add `--train` and retain the required raw
test predictions:

```powershell
.\.venv\Scripts\python.exe -m pipelines.train_article_classifier `
  --reviews <path-to-article-reviews.jsonl> `
  --archive <path-to-flood_articles_archive.parquet> `
  --report outputs/article-baseline-report.json `
  --predictions-output outputs/article-baseline-predictions.parquet `
  --train
```

The command exits without fitting if any production gate fails. The gate
values follow `docs/local-article-training.md`: at least 500 usable labels, at
least 100 in each class, sufficient time and publisher diversity, at least 95%
inference-text coverage, and minimum per-class counts after leakage purging.

## Optional smoke test

For development only, `--train --smoke-test` enables smaller split gates. A
successful result is stamped `NON_EVALUATIVE_SMOKE_TEST` throughout the report.
It proves that vectorization, fitting, prediction, and artifact writing work;
its scores must not be used to describe model quality or readiness.

The smoke path still enforces all label, text-provenance, chronological,
publisher, and story-group safeguards. It also requires at least one example
of every class in validation and test after purging. It is not a shortcut for
training on incompatible or unlicensed data.

## Evaluation design

The CPU model combines word TF-IDF 1–2 grams and character TF-IDF 3–5 grams
with class-balanced logistic regression. It is compared with a prior-only
dummy classifier and frozen keyword rules. The report includes macro-F1,
per-class precision/recall/F1, a fixed-order confusion matrix, and fixed
confidence-threshold abstention behavior.

Rows begin in an approximately 70/15/15 `seen_at` split. If one story group
crosses a boundary, every member is assigned to its newest split. Publishers
present in the final period are then purged from training and validation. The
runner refuses to continue if a story overlaps any split or a final-period
publisher remains in an earlier split.

This is local CPU baseline training, not pretraining a language model from
scratch. It does not call OpenAI or consume API credits. No offline score from
this runner alone makes the classifier production-ready.
