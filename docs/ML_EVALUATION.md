# Fixed synthetic evaluation protocol

Observation: one generated customer at one monthly cutoff. Feature allowlist contains only
the five numeric behavioral/plan fields in `data.FEATURES`. IDs, cutoff, label and label
availability never enter the feature matrix. Source values are simulated, not real events.

| Partition | Cutoffs | Latest label maturity | Role |
|---|---|---|---|
| Train | 2026-06-30, 2026-07-31 | 2026-08-30 | Fit scaler, Logistic Regression and constant prior |
| Validation | 2026-08-31 | 2026-09-30 | Diagnostics for a fixed protocol |
| Test | 2026-09-30 | 2026-10-30 | Untuned final historical holdout |

An older partition's labels must be available by the next cutoff (equality is allowed at
day granularity). Freeze defaults to 2026-11-03 and can be set explicitly. Each cohort must
contain both classes; fail with a clear error otherwise. Repeated customer overlap is recorded;
this is an out-of-time test, not a cold-start/unseen-customer evaluation.

Logistic Regression uses train-only StandardScaler, fixed C=1, max_iter=500 and seed 342.
There is no tuning or train+validation refit in this slice. `DummyClassifier(strategy="prior")`
predicts the training positive rate and supplies a constant baseline on the same holdouts.
Do not interpret baseline top-k ties as evidence of useful ranking.

Metrics on validation/test: average precision, ROC-AUC, log loss, Brier, precision/recall at
top 10%, positive count/rate and five calibration bins. Top-k uses `ceil(0.1 × n)` and stable
source-order ties. Empty calibration bins are omitted; counts must reconcile to cohort size.
Average precision is the non-interpolated precision–recall summary defined by
[scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html),
not trapezoidal PR area. Temporal ordering follows the principle described in the
[time-series validation reference](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html);
we split explicit calendar cohorts instead of applying row-wise TimeSeriesSplit.

Model identity hashes dataset, implementation source, feature schema, config, Python and
relevant package versions plus freeze date. Manifest also records model checksum, actual
training timestamp, cohort counts, overlap, metrics, seed, source rights and limitations.
Training timestamp is retained on replay; a changed identity creates another immutable version.

These metrics are synthetic smoke measurements. They do not establish prospective quality,
production calibration, KKBox performance or campaign uplift. Future LightGBM selection
must use validation only; freeze the selected protocol before the final holdout evaluation.
Cloud artifact registry, MLflow, calibration tuning and real-data promotion remain planned.
