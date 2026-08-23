# Media-spread model card

## Purpose

CrisisPulse's first supervised model ranks whether disaster-related news coverage for a region will spread across at least 20 independent source domains in any single hour during the next six completed hours. It is a portfolio benchmark for prioritizing news signals.

It does **not** predict whether a physical disaster will occur, estimate disaster severity, or issue an emergency warning.

## Current status

The model is currently **unavailable by design**. On August 20, 2026, a live review found that GDELT had attached a flood theme to an unrelated astronomy story. CrisisPulse added a URL-headline relevance guard and corrected syndicated grouping for URLs ending in numeric IDs. Because the older raw ZIPs needed to rebuild all seven days were no longer retained, the derived history and model were reset rather than keeping incomparable measurements. The dashboard will show model results again only after enough corrected chronological history has accumulated.

## Data and target

- Data source: public GDELT GKG records processed by the local CrisisPulse pipeline.
- Corrected observation window began August 20, 2026 and is rebuilding automatically.
- Prediction time: the end of hour 0.
- Positive label: `unique_domain_count >= 20` in any one of hours 1–6.
- Leakage control: the current hour is excluded from the label, and future-hour fields are never used as model inputs.
- Completed corrected outcome rows: not yet sufficient for training.

The target measures publisher-domain spread. Source domains are an imperfect proxy for independent attention because syndicated stories and related outlets can still be correlated.

## Model

The benchmark is a class-balanced logistic regression over prediction-time features only:

- log article, high-confidence story, and domain counts;
- duplicate/syndication ratio;
- prior rolling median and median absolute deviation;
- robust anomaly score;
- UTC hour represented as sine and cosine;
- whether an observed feature row existed for the region/hour.

Class balancing makes the score useful for ranking rare outcomes, but it also means the raw score is **not a calibrated probability**. The saved JSON artifact contains the scaler parameters and coefficients rather than an executable pickle.

## Evaluation design

Rows are split chronologically by prediction hour: 70% training, 15% threshold validation, and 15% final testing. A six-hour embargo separates each split so their future label windows cannot overlap. The alert threshold is selected on validation data under a maximum budget of five false alerts per day. The later test period is not used for fitting or threshold selection, but its metrics are exploratory because they are viewed as the local holdout grows.

The pre-reset engineering run exported August 20, 2026 at 23:00 UTC. It is retained here only as historical context and **must not be used as current product performance**, because its input rules differ from the corrected pipeline:

| Split | Rows | Positive outcomes | Hours |
|---|---:|---:|---:|
| Training | 44,110 | 241 | — |
| Validation | 7,619 | 29 | 19 |
| Test | 10,426 | 53 | 26 |

The chosen score threshold is `0.9979`.

## Invalidated historical results

| Metric | Validation | Later test |
|---|---:|---:|
| Average precision | 74.4% | 68.0% |
| Alert precision | 95.0% | 85.7% |
| Outcome recall | 65.5% | 56.6% |
| F1 | 77.6% | 68.2% |
| False alerts per day | 1.3 | 4.6 |

The historical test contained 30 true positives, 5 false positives, and 23 false negatives. These values demonstrate that the training path ran, but they are invalid for current decision-making after the relevance-rule correction. The live dashboard is the source for the next corrected evaluation once it becomes available.

## Intended use

- Rank local review candidates for investigation.
- Track a time-locked outcome after a candidate is created.
- Compare future models against the same chronological benchmark.

## Prohibited or unsafe use

- Do not describe the score as a disaster probability.
- Do not use it for evacuation, emergency response, insurance, lending, or other high-stakes decisions.
- Do not treat publisher agreement as independent confirmation of a physical event.
- Do not market the current holdout results as externally validated accuracy.

## Limitations and next evidence needed

- The current history spans roughly one week and may reflect a narrow news cycle.
- The reference final test spans only 26 hourly windows and 53 positive region/hour outcomes.
- Rows within an hour are region-correlated, so row counts overstate temporal diversity.
- GDELT processing time is not guaranteed to equal article publication time.
- Location assignment, disaster themes, and cross-domain story grouping remain heuristic.
- The class-balanced score needs calibration on a larger, later dataset before it can be presented as a probability.
- Human review and comparison with an external event source are still required before any real-world claim.

The next credible milestone is several weeks of untouched forward collection, followed by a preregistered temporal evaluation and probability calibration on data that was not available during model design.
