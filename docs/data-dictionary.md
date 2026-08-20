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
| `themes` | list[string] | Unique normalized GKG theme tokens found on the record. |
| `tone` | float/null | First value from GDELT's tone field. It is weak evidence, not a severity measurement. |
| `geo_confidence` | string | `coordinates_valid`, `location_only`, or `missing`. |
| `quality_flags` | list[string] | Non-destructive warnings such as `invalid_coordinates` or `multiple_locations`. |
| `duplicate_group_id` | string | Stable first-pass group for likely copies within a six-hour window. |
| `duplicate_group_method` | string | `url_slug_6h` or the conservative `canonical_url` fallback. |
| `duplicate_group_size` | integer | Number of clean article URLs assigned to the group. |

Current quality flags are `invalid_url`, `invalid_seen_at`, `missing_location`, `invalid_coordinates`, `multiple_locations`, `ambiguous_region`, and `unresolved_region`.

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
| `label_disaster_relevance` | Blank human label; suggested values are `relevant`, `not_relevant`, or `uncertain`. |
| `label_primary_region` | Blank human label; enter `country:adm1`, `UNKNOWN`, or `uncertain`. |
| `review_notes` | Blank free-text notes for the reviewer. |

The review evaluator accepts `relevant`, `not_relevant`, or `uncertain` for disaster relevance. Primary-region labels use `country:adm1`, `UNKNOWN`, or `uncertain`. Blank and uncertain values are reported separately and excluded from calculated rates.
