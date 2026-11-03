# Data contract and source rights

## Authorized source boundary

The runnable path uses project-generated synthetic snapshots. No external customer data
was downloaded, no Kaggle agreement accepted and no KKBox use right established here.
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
| `payment_failures_90d` | Simulated payment failures; integer 0–90 |
| `tenure_months` | Integer 1–1200 |
| `monthly_fee` | Finite simulated fee; greater than 0, at most 10000 |
| `auto_renew` | Binary plan flag known at cutoff |
| `feature_max_event_at` | Supplied latest contributing event date |
| `source_max_available_at` | Supplied latest source availability date |
| `churn_30d` | Simulated Bernoulli outcome; binary |
| `label_available_at` | Cutoff + exactly 30 days; inclusive maturity date |
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

`data/raw/synthetic-{full_sha256}/` contains immutable CSV + manifest: source release ID,
dataset hash, schema version, row count, cutoffs, source mode and rights statement. Identical
content reuses one release. Validate before publication. Corrupt existing content fails;
never silently overwrite it. Invalid input creates no new published source release.

Prediction key: `(model_version, customer_id, as_of_date)`. One active release serves the API;
older predictions remain available locally for audit. Reconcile published rows to test rows.
Generated source/model/SQLite files and the original Execution Kit are ignored by Git.

## Future real-data contract

Validate actual licensed source columns rather than assuming their presence. Record event
and correction availability timestamps, immutable source IDs, eligible expiring subscriptions,
grace-period label rules, freeze/watermarks, lookback closure and exclusion reasons. The
proposed seven-days-before-expiry cutoff is not approved until source evidence supports it.
Every join needs an explicit grain and cardinality check. Every feature needs an independent
event-level cutoff test. Mature cohort rate = churned eligible / eligible expiring customers.
