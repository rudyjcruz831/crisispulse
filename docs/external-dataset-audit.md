# External dataset audit

## Purpose

An external dataset is not admitted to CrisisPulse merely because it is public or free to download. Before import or training, the project records four separate answers:

1. **Rights:** does the dataset's own license permit the planned use?
2. **Content:** does the release contain text available to the live classifier, rather than only maps, event dates, or social posts?
3. **Labels:** can each source label be mapped without guessing to the CrisisPulse article taxonomy?
4. **Evaluation:** can provenance be retained while a newer native CrisisPulse holdout stays untouched?

```text
Public description + license + documented schema
                         |
                         v
               Versioned audit record
                  /             \
          approved support     blocked
          (keeps provenance)   (no import/training)
                  |
                  v
       native-label calibration + isolated holdout
```

Unknown rights fail closed. External labels are never rewritten as native human reviews, and weak labels never enter the final native holdout.

## Current decisions

Checked on 2026-08-25. No large external dataset was downloaded during this audit.

| Source | Rights | Released material | Label compatibility | Current CrisisPulse decision |
| --- | --- | --- | --- | --- |
| [Groundsource](https://zenodo.org/records/18647054) | CC BY 4.0 verified in the [official DOI metadata](https://api.datacite.org/dois/10.5281/zenodo.18647054) | 2,646,302 event rows; `uuid`, `area_km2`, `start_date`, `end_date`, and `geometry`; no article text, URL, title, publisher, or class label | Partial positive-event signal only | Approved later for time/location event validation with attribution; not recommended for direct article-classifier training |
| [Bangladesh flood-news study](https://arxiv.org/abs/2312.14943) | Dataset and underlying news-text rights not verified | Paper reports 39,777 English articles and 1,380 expert binary labels; public files and exact schema not verified | `flood` roughly matches reported flooding; `not flood` mixes several CrisisPulse classes | Blocked pending files, explicit rights, schema inspection, and manual negative-label remapping |
| [HumAID](https://crisisnlp.qcri.org/humaid_dataset.html) | [Official terms](https://crisisnlp.qcri.org/terms-of-use.html) restrict use to humanitarian-computing research and add confidentiality/deletion duties | Human-labeled social posts, not publisher articles | Humanitarian categories do not map to the four article classes | Blocked from commercial product training under the current terms |
| [CrisisMMD](https://crisisnlp.qcri.org/crisismmd) | Not verified for this use | Social posts and images | Low compatibility | Not recommended for the current article classifier |
| [Natural-disaster news study](https://doi.org/10.1109/BigData.2017.8258374) | Corpus access and dataset license not verified | Publication describes human-annotated agency news | Flood class is promising, but other classes do not provide the needed warning/rain/unrelated separation | Blocked pending a public corpus, rights, schema, and mapping audit |
| [TREC Incident Streams](https://www.nist.gov/publications/incident-streams-2021-deep-end-deeper-annotations-and-evaluations-twitter) | Dataset/platform content terms not fully audited | Crisis social posts with information-type and priority annotations | Suitable only for possible future urgency research | Not recommended for the current article classifier |

## Why Groundsource does not train the article classifier

Groundsource is valuable and reusable with attribution, but its public Parquet file is an event inventory. A row can say that flooding was evidenced within a particular geometry and date range. It cannot teach the classifier which words distinguish reported flooding from a warning or heavy rain because the released row contains no article words.

Its safe role is a separate weak evidence layer:

```text
CrisisPulse article (time + place)
                 |
                 v
        Groundsource event match
                 |
                 v
  event-validation feature for audit only
```

The match must retain `source_dataset=groundsource`, its dataset version/DOI, the match method, and a weak-label marker. It must not set `human_reviewed=true`.

## Training-data admission contract

An external row may enter a supervised experiment only when all of the following are recorded:

- dataset name, version, stable source URL or DOI, and file checksum;
- exact license identifier and attribution requirements;
- original label and documented conversion rule;
- text field used by training and proof that the same kind of text exists at live inference;
- source publication time, publisher group, and duplicate/story group needed for leakage-safe splitting;
- import code version and audit date;
- explicit exclusion from the native final holdout.

If any required item is unknown, the importer must stop with a blocked decision rather than guess.

## Revisit as the product grows

- Contact the Bangladesh dataset authors for the promised corpus, schema, and explicit data/news-text rights.
- Add a provenance-aware Groundsource event matcher only after the article model baseline is reproducible.
- Re-audit third-party licenses before a commercial launch or material change in use.
- Consider separate urgency, severity, or humanitarian-impact models only after the four-class article classifier is reliable.
