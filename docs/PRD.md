# RetentionOps product requirements

Owner: Palapluem. Target release: 2026-11-13, Asia/Bangkok; deadline before 2026-11-14.
Planned work: eight working days / approximately 64 hours, with November 7–8 as optional
buffer. Implementation began early on 2026-11-03; dates do not waive quality gates.

## Product question

A retention analyst needs a reliable ranked view of subscriber churn risk, cohort outcomes,
data freshness and model provenance. An engineer must be able to reproduce each score,
explain the label and recover safely from a failed run.

The intended cloud product uses authorized subscription history, batch scoring, FastAPI
and Next.js. Public demonstrations use generated synthetic accounts exclusively.

## Acceptance and current scope

| Capability | Current implementation | Release requirement |
|---|---|---|
| Source intake | Synthetic CSV and JSONL event intake, source identity, immutable hash/quality manifests, idempotent replay | Authorized source-specific GCS/BigQuery ingestion and reconciliation |
| Features | Event-derived point-in-time features and mature synthetic renewal labels; legacy snapshot smoke path retained | Real-source event mapping, independent label/correction policy and production warehouse transforms |
| Training | Fixed Logistic Regression, constant prior, 3 temporal splits | Baseline/candidate comparison, tracked promotion |
| Model lineage | Data/code/config/dependencies/model hashes | GCS versioned artifacts, reproducible cloud training |
| Scores | Transactional local SQLite, active-release isolation | Idempotent BigQuery batch scoring |
| API | Typed local read-only overview/risk and readiness | Access-controlled Cloud Run service and governed views |
| UI | API-backed smoke dashboard | Next.js cohort/risk/freshness views and E2E |
| Delivery | Feature branch, issue, PR and credential-free CI | Reviewed changes, OIDC delivery, operations/recovery evidence |

## P0 release outcomes

Source rights and label semantics are documented; temporal leakage gates pass; data and
scores reconcile with unique keys; train/validation/test chronology is recorded; model
metrics are compared fairly; API access and query costs are bounded; UI shows provenance;
tests, logs and recovery evidence exist; clean checkout reproduces the demo.

Measure average precision, recall at top 10%, calibration/Brier, log loss and ROC-AUC.
Observed churn rates need an eligible, mature denominator. Predicted risk is neither a
causal campaign effect nor measured retention ROI.

## Exclusions

No Kafka, Kubernetes, Spark cluster, online feature store, counterfactual uplift claim,
multi-tenant billing or high-availability guarantee. MLflow, LightGBM and Polars/PyArrow
enter when their concrete data/training tasks are implemented; no duplicate tools by default.
