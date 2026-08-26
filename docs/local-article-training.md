# Local article-model training plan

## Purpose

The article-review dataset is intended to teach a future model to distinguish reported flooding, explicit flood risk or warnings, heavy rain without flood evidence, and unrelated news. It is separate from the existing media-spread model, which forecasts whether publisher coverage will spread across more domains.

```text
Free GDELT collection
        ↓
Permanent cleaned article archive
        ↓
Human version-2 review + optional context tags
        ↓
Training eligibility and audit export
        ↓
Leakage-safe CPU baseline
        ↓
Optional local GPU experiment
```

## What counts as training data

Only the latest version-2 decision for an article can be eligible. The four resolved decisions are eligible; `uncertain` is retained for audit but excluded. Legacy version-1 decisions remain visible but require a new version-2 review. Corrections stay in the append-only log, while the training view uses only the latest decision per article.

Collected articles are not automatically labels. The permanent archive can contain thousands of articles while the eligible supervised dataset remains small until a person reviews representative examples.

## Readiness gates

These are conservative engineering gates for starting experiments, not guarantees of model quality:

- Preliminary filter measurement: 20 resolved version 2 decisions, with at least five strong and five blocked examples. This unlocks only the two filter-rate estimates; it is not model-training readiness.
- First CPU experiment: at least 500 eligible decisions, at least 100 examples in each resolved class, at least 30 distinct article dates, at least 100 publisher groups, and at least 95% coverage by text that will also exist at live inference.
- Post-split CPU check: after publisher and syndicated-story purging, training retains at least 60 examples per class, validation at least 15 per class, and final test at least 20 per class.
- First local GPU experiment: at least 2,000 eligible decisions, at least 300 examples per class, at least 60 article dates, at least 250 publisher groups, and at least 95% feature parity, after the CPU baseline and holdout pipeline work correctly.
- Label-quality GPU check: at least 200 double-reviewed examples, at least 25 per class, and adjudicated Cohen's kappa of at least 0.75.
- Evidence check: the CPU model improves macro-F1 over the frozen deterministic baseline by at least 0.05, with the publisher/story-cluster bootstrap 95% confidence interval for the gain above zero.

The current review schema cannot yet compute article-date coverage, normalized publisher groups, inference-text coverage, split viability, reviewer agreement, or the evidence check. Those values must remain **not computable** until an audited importer supplies them; label totals alone must never turn the overall readiness status green.

The current development workstation was verified on 2026-08-25 with an NVIDIA GeForce RTX 4070, 12,282 MiB of VRAM, compute capability 8.9, and a CUDA-capable driver. That is sufficient for a modest local text model or parameter-efficient fine-tuning experiment. GPU availability does not compensate for missing or biased labels.

## Evaluation requirements

The first baseline should combine word TF-IDF 1–2 grams and character TF-IDF 3–5 grams with class-balanced multinomial logistic regression. It is fast, interpretable, inexpensive, and should run on CPU. Compare it with a dummy classifier and the frozen deterministic flood rules. A larger neural model is worth testing only if it beats that baseline on untouched data.

Before fitting, the importer must join labels back to permanent article history and prevent duplicate or syndicated stories from crossing splits. Use `seen_at`, not review time, for an approximately 70/15/15 chronological split. Normalize publishers to outlet families, assign any story component that crosses a boundary wholly to the latest split, and keep publishers in the newest final period out of earlier splits. A separate known-publisher chronological diagnostic may be reported, but it must not be blended with the strict holdout.

Do not use `source_domain`, `match_strength`, `review_bucket`, `quality_flags`, context tags, or `reviewed_at` as model inputs. They are audit or split metadata, post-review information, or shortcuts from the current heuristic. Publisher titles added manually or after the human decision are usable only if the identical acquisition path exists before live inference.

The report must show macro-F1, per-class precision and recall, a confusion matrix, abstention behavior, split dates, publisher/language/title-source slices, and the exact dataset version. `uncertain` is an abstention challenge set, not a fifth semantic training class. No result may be described as production-ready from the training rows themselves, and the balanced review queue must not be treated as real-world class prevalence.

If the GPU gates pass, a compact multilingual sequence classifier can be fine-tuned locally with mixed precision and short headline-length sequences. Run at least three fixed seeds and retain raw predictions. The GPU is for the experiment; a future production artifact should remain CPU-capable so hosting does not require a costly GPU server.

## Cost and credits

Scheduled GDELT collection, dataset exports, and local CPU/GPU training run on the user's computer and do not call the OpenAI API or consume ChatGPT credits. Work requested from Codex still uses the user's Codex or ChatGPT allowance. Downloading a third-party open model may require internet bandwidth and acceptance of that model's license, but local inference and training do not require per-request OpenAI fees.
