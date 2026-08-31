# Article review protocol

This document defines how a person labels CrisisPulse article candidates. It is
the normative annotation guide for `review_protocol_version: 1`. The stored
article decision schema remains version 2, and the four resolved model targets
remain unchanged:

- `reported_flooding`
- `flood_risk_warning`
- `heavy_rain_only`
- `not_flood_related`

`uncertain` is a retained review outcome, not a fifth training target. The
protocol adds evidence, uncertainty, and controlled context fields without
rewriting earlier append-only decisions.

## Objective

The immediate classifier answers an operational question: what actionable
flood or heavy-rain state is central to this article? It is not a general topic
classifier and it does not determine whether a publisher is trustworthy.

The reviewer should identify the main publisher article before considering a
label. Use its headline, publisher-authored summary or lead, and main body.
Ignore navigation, advertisements, comments, recommended-story cards, footer
headlines, and other unrelated text on the page. A GDELT theme, queue bucket,
heuristic match strength, parser guess, or model prediction is never evidence
for the human answer.

Review is blind: do not show the reviewer an internal guessed class or a model
prediction before the decision is saved. Neutral sampling reasons may explain
why an article entered the queue, but must not recommend an answer.

## Review sequence

1. Open the publisher story and identify the page's main article.
2. Record what evidence was actually available in `review_basis`.
3. Record whether the headline alone supports the answer in
   `headline_support`.
4. Choose exactly one primary decision using the centrality and precedence
   rules below.
5. Supply the required controlled reason for `not_flood_related` or
   `uncertain`.
6. Add only supported controlled impact and context flags. Unselected flags
   mean unrecorded, not proven absent.
7. Save the answer. A correction appends a new record; it never changes or
   deletes the earlier audit entry.

A reviewer who is tired or wants to return later should skip the card without
saving a decision. `uncertain` is reserved for an actual evidence limitation,
not for time pressure.

## Evidence fields

### `review_basis`

| Value | Use when |
|---|---|
| `full_article` | The reviewer read enough of the publisher's main article body to identify its central claim. |
| `publisher_summary` | A publisher-authored standfirst, lead, or summary supplied enough evidence without relying on unrelated page text. |
| `headline_only` | A trustworthy publisher headline was the only evidence used and was explicit enough to support the answer. |
| `unavailable` | No reliable publisher evidence was available. Use an uncertainty reason rather than guessing from GDELT metadata. |

An access block does not automatically force `uncertain` when a trustworthy
headline is explicit—for example, “Flash flooding closes three county roads.”
A vague headline such as “Hurricane Lala approaches” is not enough to infer a
flood class.

### `headline_support`

| Value | Meaning for the current headline model |
|---|---|
| `sufficient` | The trustworthy headline alone supports the primary decision. |
| `body_required` | The headline is usable but the publisher summary or article body was required to choose the decision. |
| `conflicts_with_body` | The headline and main article support different decisions, or the displayed headline belongs to a different story. |

`review_basis` says what the reviewer read. `headline_support` separately says
whether the text available to the current classifier contains enough evidence.
The fields are intentionally not interchangeable.

### Protocol validation matrix

- `review_basis` is required on every protocol-1 review, including
  `uncertain`.
- `review_basis: unavailable` is allowed only with `uncertain`.
- `headline_support` is required on every resolved decision and forbidden on
  `uncertain`.
- A resolved `headline_only` review must use `headline_support: sufficient`.
- `no_signal_reason` is required if and only if the decision is
  `not_flood_related`.
- `uncertainty_reason` is required if and only if the decision is `uncertain`.
- `impact_flags` and `context_flags` are forbidden on `uncertain`.
- The historical `tags` field is rejected on protocol-1 requests.

## Primary decision rules

Apply these rules to the article's central claim, not to every hazard word that
appears anywhere on the page.

| Decision | Include | Exclude |
|---|---|---|
| `reported_flooding` | Physical floodwater is occurring or occurred, including inundated normally dry land, buildings or roads; river overflow; flash or urban flooding; coastal surge; or direct deaths, rescues, damage, disruption, or immediate recovery attributed to a specific flood. | A forecast or warning with no central confirmed flooding; rain alone; an incidental historical flood mention. |
| `flood_risk_warning` | An explicit, credible flood watch, warning, forecast, or near-term risk for a real place or time, before central flooding is confirmed. | Generic statements that climate change can increase future flood risk; severe rain with no explicit flood risk. |
| `heavy_rain_only` | Heavy, torrential, excessive, or otherwise operationally significant rain is central, but the article gives no observed flooding, flood warning, or explicit flood-risk evidence. | Ordinary rain; wind-, hail-, or tornado-only stories; any article whose central claim already supports a flood class. |
| `not_flood_related` | No actionable flood or heavy-rain state above is central. A controlled `no_signal_reason` must distinguish flood context, other weather, and an unrelated false match. | A supported observed flood, explicit near-term risk, or central heavy-rain report. |
| `uncertain` | The source cannot support a defensible semantic decision because access, page identity, language, article structure, or evidence is insufficient or conflicting. | Reviewer fatigue, a difficult but answerable story, or disagreement with a GDELT tag. |

### Centrality and precedence

First identify the headline, lead, and dominant subject of the main article.
An incidental sentence does not control the label. If a prior flood is merely
background for a new storm forecast, label the new central condition. A true
multi-story roundup is uncertain unless CrisisPulse can isolate the specific
story segment.

When two operational states are genuinely co-central, apply this precedence:

1. `reported_flooding`
2. `flood_risk_warning`
3. `heavy_rain_only`
4. `not_flood_related`

Precedence resolves co-central evidence; it must not promote an incidental
historical mention over the article's actual subject.

## Required controlled reasons

### `no_signal_reason`

This field is required when `decision` is `not_flood_related`:

| Value | Meaning |
|---|---|
| `flood_context_analysis` | Flooding, climate, research, insurance, policy, preparedness, or historical analysis is central, but there is no actionable current event or near-term risk. |
| `other_weather_non_flood` | Another weather hazard is central without supported heavy rain or flooding, such as a wind-, hail-, tornado-, or snow-focused story. |
| `unrelated_false_match` | The page is outside the monitoring scope or a GDELT/parser false match, including procurement, astronomy, metaphorical flooding, or unrelated content. |

These remain one negative model target. CrisisPulse does not add a fifth
`flood_context_analysis` training class while the labeled dataset is small.

### `uncertainty_reason`

This field is required when `decision` is `uncertain`:

| Value | Meaning |
|---|---|
| `access_blocked` | A paywall, login, robots rule, or other access control prevents enough review. |
| `page_unavailable` | The publisher page is broken, removed, or cannot be reached. |
| `wrong_or_junk_page` | The destination is not the claimed article or contains no trustworthy primary story. |
| `multi_story_page` | Several independent stories share the page and no single article unit can be isolated. |
| `language_barrier` | No reliable supported-language text or translation is available to the reviewer. |
| `insufficient_or_conflicting` | Available trustworthy evidence is too vague or internally conflicting for a defensible decision. |

## Controlled flags

Protocol-v1 reviews do not accept free-form tags. Flags are closed-vocabulary
audit attributes, not primary labels.

### `impact_flags`

- `fatality`
- `injury`
- `evacuation_displacement`
- `rescue_search`
- `property_crop_damage`
- `transport_disruption`
- `utility_disruption`

### `context_flags`

- `aftermath_recovery`
- `climate_background`
- `historical_background`
- `policy_preparedness`

Record a flag only when the reviewed publisher evidence supports it. An absent
flag means “not recorded by this review,” not “confirmed absent.” The arrays
must contain unique values from the lists above. They are available for audit,
quality slices, and future multi-label experiments, but the current classifier
does not receive them as features.

## Examples

| Evidence | Primary decision | Additional protocol fields |
|---|---|---|
| “Flash flooding entered homes and closed Interstate 95.” | `reported_flooding` | `impact_flags: [property_crop_damage, transport_disruption]` |
| “The weather service issued a flash-flood warning through 8 PM.” | `flood_risk_warning` | `context_flags: []` |
| “Up to five inches of heavy rain is expected,” with no flood language. | `heavy_rain_only` | No impact inferred from rainfall alone. |
| “Study projects climate-driven flood losses by 2050.” | `not_flood_related` | `no_signal_reason: flood_context_analysis`; `context_flags: [climate_background]` |
| A hurricane article focused only on damaging winds. | `not_flood_related` | `no_signal_reason: other_weather_non_flood` |
| A procurement page carrying an erroneous flood theme. | `not_flood_related` | `no_signal_reason: unrelated_false_match` |
| A generic paywalled headline with no explicit flood or rain evidence. | `uncertain` | `review_basis: unavailable`; `uncertainty_reason: access_blocked` |
| A page intentionally combining several independent local stories. | `uncertain` | `uncertainty_reason: multi_story_page` |

## Training eligibility and model boundary

A resolved version-2 decision is necessary but not sufficient for the current
headline-only classifier. For protocol-v1 reviews:

- `headline_support: sufficient` may enter the existing eligibility pipeline,
  subject to title provenance, archive joins, leakage controls, and all other
  readiness gates.
- `headline_support: body_required` or `conflicts_with_body` is excluded from
  the current headline model with `exclusion_reason: headline_not_sufficient`.
- `uncertain` remains preserved for audit and abstention evaluation, but never
  becomes a semantic training target.

The evidence fields, reasons, impact flags, and context flags are audit,
selection, and evaluation-slice data. They are not current model features and
must not be used as post-review shortcuts. A later model that can legally and
reliably obtain publisher summaries or article text may define a new feature
contract and reconsider `body_required` examples without changing their human
labels.

## Legacy records and corrections

Earlier version-1 and version-2 records remain readable and append-only.
Existing `tags` arrays remain visible as historical evidence, but they are not
protocol-v1 fields and are not silently converted to controlled flags. Missing
protocol fields in an older record mean “not collected,” not a default value.

The API and training views collapse each article to its latest decision without
deleting earlier lines. Re-reviewing an older article appends a protocol-v1
record. Older resolved rows continue through the existing provenance and
inference-text safeguards until they are re-reviewed; they are not rewritten
merely to satisfy the new protocol.

## Annotation quality control

- Keep button definitions and order fixed across reviewers and languages.
- Hide system guesses and model outputs until after the answer is saved.
- Independently double-review a stratified 10–20% sample across classes, dates,
  publishers, and evidence bases.
- Adjudicate disagreements rather than letting one answer silently overwrite
  another reviewer's evidence.
- Report agreement by class and target an adjudicated Cohen's kappa of at least
  0.75 before a GPU experiment.
- Version future semantic rule changes explicitly; do not reinterpret stored
  decisions in place.
