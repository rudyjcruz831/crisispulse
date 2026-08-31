# Clean Parquet data dictionary

The starter writes one row per unique canonical article URL. GDELT processing timestamps are UTC even though `seen_at` is stored without a timezone marker.

| Column | Type | Meaning |
|---|---|---|
| `source_file` | string | GKG filename that supplied the first retained copy of the article. |
| `record_id` | string | Original GKG record ID, when available. |
| `article_id` | string | SHA-256 hash of the canonical URL (or raw URL when invalid). |
| `seen_at` | datetime | Time GDELT processed the record, interpreted as UTC. |
| `canonical_url` | string/null | Normalized HTTP(S) article URL with common tracking fields removed. |
| `source_domain` | string/null | Hostname from the canonical URL, falling back to GDELT's source name. |
| `location_name` | string/null | Primary location selected from `V2ENHANCEDLOCATIONS`. |
| `country_code` | string/null | GDELT country code for the primary location. |
| `adm1_code` | string/null | First-level administrative code supplied by GDELT. |
| `adm2_code` | string/null | Second-level administrative code supplied by GDELT. |
| `latitude` | float/null | Extracted latitude; may be invalid when a quality flag is present. |
| `longitude` | float/null | Extracted longitude; may be invalid when a quality flag is present. |
| `distinct_location_count` | integer | Number of distinct places mentioned in the article. |
| `location_selection_status` | string | `single_region`, `dominant_region`, `ambiguous_region`, `unresolved_region`, or `missing`. |
| `location_candidate_regions` | list[string] | Mentioned region keys ordered by mention count, then key. |
| `disaster_type` | string | Disaster filter used for this run, currently `flood` or `wildfire`. |
| `disaster_match_strength` | string | `high` for explicit event themes or `weak` for ambiguous theme-only evidence. |
| `matched_disaster_themes` | list[string] | Theme tokens that caused the disaster classification. |
| `url_topic_relevance` | string | `supporting`, `mismatch`, or `unknown` comparison between a readable URL headline and the selected disaster topic. A mismatch downgrades a high GDELT theme to weak. |
| `publisher_title` | string/null | Bounded title read from permitted publisher metadata or HTML, or supplied by an audited manual override when automated reading is prohibited; null when unavailable. |
| `publisher_title_relevance` | string | `supporting`, `mismatch`, or `unknown` comparison between the publisher title and the selected disaster topic. A mismatch downgrades a high match to weak. |
| `themes` | list[string] | Unique normalized GKG theme tokens found on the record. |
| `tone` | float/null | First value from GDELT's tone field. It is weak evidence, not a severity measurement. |
| `geo_confidence` | string | `coordinates_valid`, `location_only`, or `missing`. |
| `quality_flags` | list[string] | Non-destructive warnings such as `invalid_coordinates` or `multiple_locations`. |
| `duplicate_group_id` | string | Stable first-pass group for likely copies within a six-hour window. |
| `duplicate_group_method` | string | `url_slug_6h` or the conservative `canonical_url` fallback. |
| `duplicate_group_size` | integer | Number of clean article URLs assigned to the group. |

Current quality flags are `invalid_url`, `invalid_seen_at`, `missing_location`, `invalid_coordinates`, `multiple_locations`, `ambiguous_region`, and `unresolved_region`.

## Permanent article archive

`flood_articles_archive.parquet` uses the same columns above and is keyed by `article_id`. Each production refresh upserts the current cleaned batch, preferring the latest checked version of a repeated article. The file uses zstd compression and is atomically replaced only after a read-back check proves that every current article ID is present. It is retained independently of the 10 GB raw ZIP cache and included in production backups.

## Daily article-quality sample

`quality-review-sample.json` is regenerated after permanent archival. Version 2 is a deterministic Smart Review Queue with up to 24 recent, distinct story groups. It removes completed version-2 decisions, keeps unfinished cards stable during the same UTC day, and replenishes completed vacancies on a later refresh. Coarse legacy decisions are returned first for detailed labeling; unseen articles are then sampled around the current local CPU smoke-test gaps. If authoritative readiness cannot be computed, selection fails closed to the deterministic balanced `high_match`, `headline_conflict`, and `ambiguous_match` order.

Top-level `selection_intent` records the active smoke-test thresholds, current class and chronological-split counts, date and publisher diversity, inference-text coverage, and the production thresholds for context. Each card has a deterministic `rank`, an optional estimated chronological `sampling_split`, and bounded neutral selection reasons. The internal class-balancing lane is deliberately not serialized, preventing a guessed class from anchoring the reviewer. A candidate's final split can change as more labels are added.

Each item carries only bounded review evidence: stable article ID, timestamp, title, title source (`manual_override`, `publisher_metadata`, `url_path`, or `unavailable`), safe publisher URL/domain, location, match strength, review reason, matched themes, and quality flags. Publisher metadata is preferred; the URL-path parser removes common dates, IDs, UUIDs, file extensions, and generic route segments. `manual_override` means the exact publisher page was human-verified and recorded in the checked-in audit file because normal automated reading was prohibited. When no trustworthy source yields a headline, the sample explicitly reports that the title is unavailable rather than displaying a domain or opaque identifier as a headline.

Human decisions are stored separately in append-only `article-reviews.jsonl`. The primary decision schema remains version 2: `reported_flooding`, `flood_risk_warning`, `heavy_rain_only`, `not_flood_related`, or `uncertain`. New reviews also use `review_protocol_version: 1` to record the evidence basis, headline sufficiency, controlled reasons, and closed-vocabulary flags described below. The browser cannot submit or override server-side article identity or `title_source` provenance. The API collapses corrections to the latest decision per `article_id` while retaining earlier audit entries on disk. Historical records without a schema-version, protocol-version, or title-source field remain valid; coarse version 1 decisions still require a detailed version 2 answer before entering version 2 measurements or training data.

The detailed decision order is: reported physical flooding; otherwise explicit flood risk/watch/warning; otherwise heavy rain or severe weather without flood evidence; otherwise no actionable signal. Apply that precedence only to the main article's central claim, not to navigation, sidebars, recommendations, or incidental historical mentions. Use `uncertain` only when the publisher evidence cannot support a decision. See [the article review protocol](article-review-protocol.md) for the normative human criteria.

### Article review protocol fields

| Field | Type | Meaning |
|---|---|---|
| `review_protocol_version` | integer/null | `1` for the structured evidence protocol. Missing on older readable records. It does not change `decision_schema_version: 2`. |
| `review_basis` | string/null | Required on protocol-1 reviews: `full_article`, `publisher_summary`, `headline_only`, or `unavailable`. `unavailable` is restricted to `uncertain`. |
| `headline_support` | string/null | Required on resolved protocol-1 decisions and forbidden on `uncertain`: `sufficient`, `body_required`, or `conflicts_with_body`. A resolved `headline_only` review must be `sufficient`. |
| `no_signal_reason` | string/null | Required only for `not_flood_related`: `flood_context_analysis`, `other_weather_non_flood`, or `unrelated_false_match`. |
| `uncertainty_reason` | string/null | Required only for `uncertain`: `access_blocked`, `page_unavailable`, `wrong_or_junk_page`, `multi_story_page`, `language_barrier`, or `insufficient_or_conflicting`. |
| `impact_flags` | list[string]/null | Unique controlled values: `fatality`, `injury`, `evacuation_displacement`, `rescue_search`, `property_crop_damage`, `transport_disruption`, and `utility_disruption`. Forbidden on `uncertain`. |
| `context_flags` | list[string]/null | Unique controlled values: `aftermath_recovery`, `climate_background`, `historical_background`, and `policy_preparedness`. Forbidden on `uncertain`. |
| `tags` | list[string]/null | Historical free-form tags from pre-protocol records. They remain readable and exportable but protocol-1 requests reject them; they are never silently converted to flags. |

Missing or unselected flags mean unrecorded, not confirmed absent. Protocol
fields and flags support audit and evaluation slices; they are not current model
features.

## Training Data Lab derived fields

The Training Data Lab API and its audit CSV derive these fields from the latest valid review record for each `article_id`. They are not stored as new fields in the append-only review log.

| Field | Type | Meaning |
|---|---|---|
| `training_eligible` | boolean | `true` only when the latest decision uses schema version 2, is one of the four resolved targets, and passes the current inference-text evidence gate. It does not assert that the overall dataset is large or balanced enough for model training. |
| `exclusion_reason` | string | Empty for eligible rows, `uncertain` for a version 2 uncertain label, `legacy_schema` for a version 1 label, or `headline_not_sufficient` for a resolved protocol-1 review marked `body_required` or `conflicts_with_body`. Historical records with no stored schema version are read as version 1. |

Corrections remain append-only on disk, but the Training Data Lab exposes only the newest decision per article. Consequently, an earlier eligible label can become excluded after an uncertain correction, and a corrected version 2 label can replace a legacy label in the derived view without deleting either audit entry.

## Regional/hourly feature Parquet

| Column | Type | Meaning |
|---|---|---|
| `window_start` | datetime | Start of the UTC hourly window. |
| `region_id` | string | `country_code:adm1_code`, country fallback, or `UNKNOWN`. |
| `country_code` | string/null | GDELT/FIPS-style country code. |
| `adm1_code` | string/null | GDELT first-level administrative code. |
| `disaster_type` | string | Disaster category. |
| `article_count` | integer | Retained article URLs in the region/hour. |
| `high_confidence_article_count` | integer | Articles with a high-strength theme match. |
| `weak_article_count` | integer | Articles retained for auditing with weak-only evidence. |
| `unique_domain_count` | integer | Distinct source domains. |
| `estimated_unique_story_count` | integer | Distinct heuristic story groups. |
| `high_confidence_story_count` | integer | Story groups containing high-strength evidence. |
| `average_tone` | float/null | Mean GDELT tone value. |
| `location_confident_article_count` | integer | Articles assigned through a single or mention-dominant region. |
| `location_review_article_count` | integer | Articles with ambiguous, unresolved, or missing regional assignment. |
| `duplicate_ratio` | float | `1 - estimated stories / articles`. |
| `previous_story_count` | integer/null | Estimated story count in the immediately preceding hour. |
| `previous_domain_count` | integer/null | Domain count in the immediately preceding hour. |
| `article_velocity` | integer/null | Current estimated stories minus the previous hour. |
| `domain_velocity` | integer/null | Current domains minus the previous hour. |

## Manual-review CSV

The manual-review CSV copies the article identity, URL, disaster match, location selection, candidate regions, quality flags, and duplicate-group size from the clean data. It adds:

| Column | Meaning |
|---|---|
| `review_bucket` | Sampling stratum combining high/weak theme strength with assigned/questionable location. |
| `label_disaster_relevance` | Blank human label; suggested values are `reported_flooding`, `flood_risk_warning`, `heavy_rain_only`, `not_flood_related`, or `uncertain`. Legacy `relevant` and `not_relevant` remain readable. |
| `label_primary_region` | Blank human label; enter `country:adm1`, `UNKNOWN`, or `uncertain`. |
| `review_notes` | Blank free-text notes for the reviewer. |

The review evaluator accepts the five detailed disaster-relevance labels and the legacy `relevant` or `not_relevant` values. It reports class counts, treats reported flooding and explicit flood risk as flood-related for the compatibility rate, and excludes blank and uncertain rows from calculated rates. Primary-region labels use `country:adm1`, `UNKNOWN`, or `uncertain`.

## Anomaly candidate Parquet

| Column | Type | Meaning |
|---|---|---|
| `window_start` | datetime | UTC hour being scored. |
| `region_id` | string | Region or `UNKNOWN`. |
| `country_code` | string/null | GDELT country code for a confident region. |
| `adm1_code` | string/null | GDELT ADM1 code for a confident region. |
| `disaster_type` | string | Disaster category. |
| `observed_feature_row` | boolean | Whether the source feature table contained this row; false rows are zero-filled hours. |
| `article_count` | integer | Raw retained article count for the hour. |
| `estimated_unique_story_count` | integer | Duplicate-adjusted story count. |
| `high_confidence_story_count` | integer | High-strength story count used as the anomaly signal. |
| `unique_domain_count` | integer | Source-domain support for the candidate gate. |
| `baseline_history_hours` | integer | Prior zero-filled hourly observations available to the baseline. |
| `baseline_median` | float/null | Median high-confidence story count over prior lookback hours. |
| `baseline_mad` | float/null | Median absolute deviation over prior lookback hours. |
| `robust_z_score` | float/null | Robust standardized increase; null when history is insufficient or MAD is zero. |
| `anomaly_status` | string | `insufficient_history`, `below_minimum_support`, `normal`, or `candidate_anomaly`. |
| `is_candidate_anomaly` | boolean | True only after every history, story, domain, increase, and score gate passes. |

## Six-hour outcome Parquet

This table copies prediction-time fields from the anomaly table and adds a future-only media-spread target.

| Column | Type | Meaning |
|---|---|---|
| `window_start` | datetime | Prediction hour; all model features stop here. |
| `region_id` | string | Region or `UNKNOWN`. |
| `disaster_type` | string | Disaster category. |
| `observed_feature_row` | boolean | Whether the prediction hour contained an observed feature row. |
| `article_count` | integer | Prediction-hour article count. |
| `estimated_unique_story_count` | integer | Prediction-hour duplicate-adjusted story count. |
| `high_confidence_story_count` | integer | Prediction-hour high-confidence story count. |
| `unique_domain_count` | integer | Prediction-hour distinct source-domain count. |
| `baseline_history_hours` | integer | Prior hours available to the anomaly baseline. |
| `baseline_median` | float/null | Prior-only rolling median at prediction time. |
| `baseline_mad` | float/null | Prior-only median absolute deviation at prediction time. |
| `robust_z_score` | float/null | Prediction-time anomaly score. |
| `anomaly_status` | string | Prediction-time anomaly status. |
| `is_candidate_anomaly` | boolean | Whether the prediction-time anomaly gates passed. |
| `outcome_matures_at` | datetime | End of the six-hour future observation window. |
| `future_max_domain_count` | integer/null | Maximum domains in any one of future hours 1–6; null until complete. |
| `label_media_spread_6h` | boolean/null | True when `future_max_domain_count >= 20`; null until complete. |
| `outcome_complete` | boolean | Whether all six future hours are available. |

The current hour never contributes to `future_max_domain_count` or the label. This prevents a candidate's triggering evidence from also satisfying its future outcome.

## Dashboard evidence stories

Each `latest_coverage` item and candidate `evidence` item contains a stable `story_id`, UTC `seen_at`, optional `location`, matched `themes`, and bounded publisher `sources`. The optional `title` is read from the primary publisher's Open Graph, social, or HTML metadata. It is `null` when the publisher disallows or prevents the bounded lookup; the dashboard then displays a URL-derived fallback. Titles are display metadata only and do not affect flood classification, anomaly scoring, or forecast labels.
