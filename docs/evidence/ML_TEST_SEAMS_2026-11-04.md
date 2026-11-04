# ROP-011 training and publication seam evidence

Run date: 2026-11-04 (Asia/Bangkok)
Scope: local synthetic data only; no cloud resources, KKBox data or customer data

## Training selection seam

`train_selected` is exercised as the public training interface. With identical train data,
reversing the holdout labels leaves the selected candidate, selected parameters, validation
results and predicted holdout probabilities unchanged; the holdout metrics change to reflect
the reversed labels. Reversing validation labels changes the selected candidate/config, and
the resulting selection matches the candidate with the highest validation average precision.
This checks both sides of the boundary: validation can select, while test cannot.

## End-to-end scoring and publication seam

`run_pipeline` was exercised with a deterministic synthetic snapshot source (100 customers,
seed 2); LightGBM was selected. The published SQLite probabilities matched the selected
serialized artifact's `predict_proba` output. Replaying the same pipeline preserved the full
published row set and probabilities. Each row had one unique
`(model_version, as_of_date, customer_id)` key and the selected test cutoff.

A conflicting replay was tested after publishing a second model release: changing one score
for an existing model/customer/cutoff key was rejected. The transaction preserved the prior
score rows and left the second release active. This was first observed failing against the
previous delete-and-reinsert behavior, then passed after the publisher was changed to accept
exact score replays and reject conflicts.

## Verification

- Focused tests: `pytest -q tests/test_training_selection.py tests/test_pipeline.py` — 16 passed.
- `bash scripts/local_smoke.sh` — Ruff check and format passed; 81 tests passed; synthetic
  snapshot and event CLI paths completed; repository hygiene passed with 60 tracked paths.
- `python -m pip_audit -r requirements.lock --require-hashes --disable-pip` — no known
  vulnerabilities.
- One existing Starlette/httpx deprecation warning was reported by Pytest.

The evidence proves local contract behavior only. It does not validate cloud batch scoring,
real subscription outcomes, prospective performance or production release readiness.
