# Data contract and source rights

## Authorized source boundary

The runnable paths use project-generated synthetic snapshots/events. The event pipeline can
also accept a file only when every row conforms to the synthetic event contract below. No
external customer data was downloaded, no Kaggle agreement accepted and no KKBox use right established here.
The [official KKBox rules page](https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/rules)
did not expose readable rule text during inspection. An authenticated manual terms review
must establish access, purpose, cloud processing and redistribution restrictions first.
Until recorded, KKBox intake and cloud transfer remain blocked. Do not substitute a static
Telco snapshot and call it prospective 30-day subscription churn.

## Implemented synthetic schema

Machine-readable schema: [synthetic_snapshot.schema.json](../contracts/synthetic_snapshot.schema.json).
Grain: `(customer_id, as_of_date)`. IDs match `SYN-[0-9]{5,7}`. Exact column names are required;
extra/missing/duplicate headers fail. Critical values must be present, finite and in range.

| Field | Meaning / range |
|---|---|
| `active_days_30d` | Simulated active days; integer 0–30 |
| `payment_failures_90d` | Nonnegative count of failed payment events; multiple per day allowed |
| `tenure_months` | Integer 1–1200 |
| `monthly_fee` | Finite simulated fee; greater than 0, at most 10000 |
| `auto_renew` | Binary plan flag known at cutoff |
| `feature_max_event_at` | Supplied latest contributing event date |
| `source_max_available_at` | Supplied latest source availability date |
| `churn_30d` | Simulated Bernoulli outcome; binary |
| `label_available_at` | At least cutoff +30 days; advanced by late outcome revisions |
| `source_type` | Must be `SYNTHETIC` |

Temporal dates are day-grain ISO dates, not intraday timestamps. Enforce event date ≤
availability date ≤ cutoff and label availability ≤ explicit evaluation freeze. They are
metadata on generated snapshots. Raw-event lookback windows and actual late corrections
remain future work; the current feature values do not prove those properties.

Synthetic label: a seeded probabilistic draw from the documented generator, representing
simulated churn within 30 days of cutoff. It is not a KKBox label, a no-activity rule or a
real observed renewal failure. Repeated customers are independent simulated monthly
observations; a prior positive does not remove a customer from later cohorts.

## Lineage and storage

`data/raw/synthetic-{full_sha256}/` contains immutable snapshot CSV + manifest. Event input is
published under `data/events/{source_id}-{full_sha256}/` with the original JSONL bytes and a
deterministic manifest containing source identity, contract version, completeness watermark,
hash, row/logical-event/customer counts, revision and watermark checks, and synthetic-only
rights. The source file is copied to staging and validated before an atomic directory rename.
Identical content and metadata reuse one release. Corrupt existing content fails; invalid
input creates no new published release. Feature Parquet is content-addressed under
`data/features/{dataset_sha256}/`, with its own manifest linking back to the event release.

Prediction key: `(model_version, customer_id, as_of_date)`. One active release serves the API;
older predictions remain available locally for audit. Reconcile published rows to test rows.
Generated source/model/SQLite files and the original Execution Kit are ignored by Git.

## Event-derived implementation

`retentionops generate-events`, `retentionops ingest-events`, and `retentionops run-events`
expose source generation, validated intake, and replay as separate commands. The one-command
`retentionops events` path uses those same stages. Features are derived from versioned
synthetic raw events, written as typed-date Parquet with Polars, and linked by hashes and
quality counts in the model manifest. Tests cover malformed/duplicate/watermark failures,
idempotent intake, replay, feature windows, late revisions, tombstones, renewal boundaries,
completeness and eligibility. See [EVENT_CONTRACT.md](EVENT_CONTRACT.md). This contract is
synthetic-only; real source identity mapping, source-specific schemas, licensing, and
GCS/BigQuery adapters remain open. The metadata-only limitation still applies to legacy
`retentionops all`.

## Future real-data contract

Validate actual licensed source columns rather than assuming their presence. Record event
and correction availability timestamps, immutable source IDs, eligible expiring subscriptions,
grace-period label rules, freeze/watermarks, lookback closure and exclusion reasons. The
proposed seven-days-before-expiry cutoff is not approved until source evidence supports it.
Every join needs an explicit grain and cardinality check. Every feature needs an independent
event-level cutoff test. Mature cohort rate = churned eligible / eligible expiring customers.
