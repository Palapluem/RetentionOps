# Synthetic model selection and evaluation protocol

Observation: one generated customer at one monthly cutoff. Feature allowlist contains only
the five numeric behavioral/plan fields in `data.FEATURES`. IDs, cutoff, label and label
availability never enter the feature matrix. `all` uses simulated snapshots; `events`
derives values from simulated raw events under docs/EVENT_CONTRACT.md. Neither is real
customer evidence. Late renewal corrections advance label availability and are subject
to the same cross-cohort label embargo; a label is available no earlier than cutoff +30d.

| Partition | Cutoffs | Latest label maturity | Role |
|---|---|---|---|
| Train | 2026-06-30, 2026-07-31 | 2026-08-30 | Fit Logistic Regression, LightGBM candidates and constant prior |
| Validation | 2026-08-31 | 2026-09-30 | Select model family and LightGBM configuration by average precision |
| Test | 2026-09-30 | 2026-10-30 | Evaluate the frozen selection and reference baselines once |

An older partition's labels must be available by the next cutoff (equality is allowed at
day granularity). Freeze defaults to 2026-11-03 and can be set explicitly. Each cohort must
contain both classes; fail with a clear error otherwise. Repeated customer overlap is recorded;
this is an out-of-time test, not a cold-start/unseen-customer evaluation.

Logistic Regression uses train-only StandardScaler, fixed C=1, max_iter=500 and the run seed.
LightGBM uses a bounded, predeclared three-row grid (leaves/depth 3/2 and 7/3, learning
rates 0.05 and 0.03, 80–160 estimators and minimum child sizes 20–40). It runs on one CPU
thread with a fixed seed, `deterministic=True` and `force_col_wise=True`. Preprocessing and
all candidate fits use the train cohort only; validation average precision selects both the
model family and, when applicable, the LightGBM row. Exact ties keep Logistic Regression,
then the earlier grid row. There is no test-based selection and no train+validation refit.
`DummyClassifier(strategy="prior")` predicts the train positive rate as a constant reference.
Do not interpret its top-k ties as evidence of useful ranking.

Validation records average precision for Logistic Regression, each LightGBM candidate and
the constant-prior reference; full validation diagnostics are also retained. After selection
is frozen, test reports the selected model plus Logistic Regression and constant-prior
references. Unselected LightGBM candidates are not evaluated on test. Metrics are average
precision, ROC-AUC, log loss, Brier, precision/recall at top 10%, positive count/rate and five
calibration bins. Top-k uses `ceil(0.1 × n)` and stable source-order ties. Empty calibration
bins are omitted; counts must reconcile to cohort size.
Average precision is the non-interpolated precision–recall summary defined by
[scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html),
not trapezoidal PR area. Temporal ordering follows the principle described in the
[time-series validation reference](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html);
we split explicit calendar cohorts instead of applying row-wise TimeSeriesSplit.

Model identity hashes dataset, implementation source, feature schema, all candidate and
selected configurations, Python and relevant package versions (including LightGBM), seed and
freeze date. The immutable manifest records each validation candidate/AP, the selected family
and parameters, selected-model test metrics, model checksum, training timestamp, cohort counts,
overlap, source rights and limitations. The existing transactional SQLite publisher stores
only the selected model's test-cohort scores. Training timestamp is retained on replay; a
changed identity creates another immutable version. The manifest is the local experiment
record for this bounded workflow; MLflow is not part of this slice.

These metrics are synthetic smoke measurements. They do not establish prospective quality,
production calibration, KKBox performance or campaign uplift. Cloud batch scoring, BigQuery
MERGE, Cloud Run jobs, remote artifact registry, calibration tuning and real-data promotion
remain gated by source rights and cloud readiness in issue #2. See [model card](MODEL_CARD.md)
and [the recorded synthetic run](evidence/ML_LIGHTGBM_2026-11-04.md).
