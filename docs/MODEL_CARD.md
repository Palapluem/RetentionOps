# Model Card — RetentionOps synthetic churn demo

## Status

Experimental local engineering artifact. This card describes the deterministic synthetic
run in [ML evidence for 4 November 2026](evidence/ML_LIGHTGBM_2026-11-04.md), not a model
approved for customer decisions.

## Intended use

- Exercise a reproducible train/validation/test workflow and immutable model manifest.
- Verify local batch scoring, SQLite publication, read-only API behavior and dashboard data.
- Compare a fixed Logistic Regression baseline with a small LightGBM candidate grid.

Do not use the scores to contact, rank, deny service to, or make decisions about real people.
The targets and features are simulated; they do not implement or validate KKBox's renewal
definition. No business threshold or campaign policy is established here.

## Data and prediction task

The task is a simulated binary churn label over a 30-day horizon for one customer at one
monthly cutoff. Each customer can appear at multiple cutoffs. Features are five numeric
behavioral/plan values: active days, payment failures, tenure, monthly fee and auto-renew.
Identifiers, cutoff dates, labels and label availability are excluded from the feature matrix.
Both snapshot and event-derived inputs in the recorded runs are generated locally.

Temporal cohorts are fixed: June and July 2026 for train, August for validation and September
for the final historical test. Label maturity is checked against the next cutoff. Scaling and
model fitting use train only. The final test is used after validation selection is frozen.

## Model selection

Logistic Regression uses a train-only StandardScaler with C=1 and max_iter=500. The positive
rate baseline is `DummyClassifier(strategy="prior")`. LightGBM compares three predeclared
configurations with bounded leaves/depth, learning rate, estimator count and minimum child
size. It uses one CPU thread, a fixed seed, `deterministic=True` and `force_col_wise=True`.

The candidate with the highest validation average precision is selected. Exact ties keep
Logistic Regression, then the earlier LightGBM grid row. The frozen selected model and
reference baselines are evaluated once on test. There is no test tuning or train-plus-validation
refit. Only the selected model's test-cohort scores are published.

## Recorded synthetic event-derived run

With 650 generated customers and seed 342, Logistic Regression was selected: validation AP
was 0.3093 for Logistic Regression versus 0.2984, 0.2948 and 0.3022 for the three LightGBM
configurations. On the held-out synthetic event-derived cohort, selected-model AP was 0.2515,
ROC-AUC 0.6780, Brier 0.1317, log loss 0.4217, precision@10% 0.2923 and recall@10% 0.1827.
The constant-prior AP was 0.1600. Full values, hashes and replay result are in the evidence
record.

These are one-run synthetic measurements. They do not establish live or prospective accuracy,
calibration on a real population, impact on retention, or generalization to unseen customers.

## Provenance and operation

The local manifest binds the source and feature hashes, implementation hash, Python and
dependency versions, candidate grid, selected parameters, seed, freeze date and serialized
model checksum. The SQLite publisher commits the model manifest, selected test scores and
active pointer in one transaction. Replays retain the same identity and checksum. Artifact
loading is limited to files created by this project; the serving API reads published scores
only and does not load the model.

## Known limitations and release gates

- Data and labels are synthetic; there are no customer or KKBox results.
- Repeated customers cross temporal cohorts, so this is not a cold-start evaluation.
- A held-out historical cohort does not establish future performance.
- Calibration bins are descriptive and are not a calibrated production guarantee.
- No campaign uplift or intervention effect is measured.
- Cloud Run/BigQuery batch scoring, production identity/access, source-rights review and real
  data promotion remain unimplemented or gated by [cloud readiness issue #2](https://github.com/Palapluem/RetentionOps/issues/2).
