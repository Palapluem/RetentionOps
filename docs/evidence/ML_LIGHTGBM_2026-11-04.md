# ROP-011 synthetic model comparison evidence

Run date: 2026-11-04 (Asia/Bangkok)
Evaluation freeze: 2026-11-03
Runtime: Python 3.11.18, macOS arm64; LightGBM 4.7.0
Input: 650 project-generated synthetic customers, seed 342
Storage: temporary local directories; no generated datasets or model files are committed

## Event-derived run

The run used the event-derived feature path and the fixed June/July train, August validation,
September test cohorts. Cohort counts were 1,300 train rows, 650 validation rows and 650 test
rows. Maximum label availability was 2026-08-30 for train, 2026-09-30 for validation and
2026-10-30 for test; the next-cutoff embargo passed.

Selection used validation average precision only:

| Candidate | Validation average precision |
|---|---:|
| Logistic Regression | 0.309339 |
| LightGBM 001 | 0.298362 |
| LightGBM 002 | 0.294825 |
| LightGBM 003 | 0.302218 |

Logistic Regression was selected. After freezing that choice, test results were:

| Metric | Selected model | Constant-prior reference |
|---|---:|---:|
| Average precision | 0.251506 | 0.160000 |
| ROC-AUC | 0.677999 | 0.500000 |
| Brier | 0.131704 | 0.134405 |
| Log loss | 0.421662 | 0.439690 |
| Precision at top 10% (65 rows) | 0.292308 | 0.138462 |
| Recall at top 10% | 0.182692 | 0.086538 |

The test cohort had 104 positives out of 650 (16%). Metrics are calculated on generated
labels and are not evidence of real customer or campaign performance.

## Artifact and replay

- Model version: `synthetic-logreg-48bfbca21fb3c631b255643d03124e79508d78f3c0717537fdd56072de34aaa3`
- Feature dataset SHA-256: `cb701245a13536fc6892de34e84d094c4e034a11e43f5f6d28777169c81628be`
- Serialized model SHA-256: `c339287fc0a017cdc1a579bb971eb2b7185f1e772a6f24047780dab61ee8dca5`
- Same-root replay returned an identical manifest, model version and model checksum.
- SQLite held 650 unique model/customer/cutoff scores for the selected test cohort.

## Snapshot-path cross-check

The independent generated-snapshot path also selected Logistic Regression. Validation AP was
0.439844 for Logistic Regression and 0.424532, 0.406156 and 0.422050 for LightGBM 001–003.
Its selected-model test AP was 0.462184. This is a separate synthetic input path, not a second
real-world validation source.

## Reproduction

Run each command with a fresh temporary `--root` directory:

```sh
retentionops events --root /tmp/retentionops-events --customers 650 --seed 342 --as-of 2026-11-03
retentionops all --root /tmp/retentionops-snapshots --customers 650 --seed 342 --as-of 2026-11-03
```

Repeat each command against its original root to check immutable replay. Both commands are
local and synthetic; they do not contact GCP or validate Cloud Run/BigQuery integration.

## Implementation verification

- `bash scripts/local_smoke.sh`: Ruff check/format, 80 tests, snapshot and event CLI smoke,
  and repository hygiene all passed. Pytest emitted one existing Starlette/httpx deprecation
  warning.
- `python -m pip_audit -r requirements.lock --require-hashes --disable-pip`: no known
  vulnerabilities. `python -m pip check`: no broken requirements.
- Docker's first pipeline run exposed the LightGBM wheel's `libgomp.so.1` runtime dependency.
  The image now installs `libgomp1`; a clean ARM64 image build and
  `docker compose -p retentionops-rop011 run --rm --build pipeline` then completed the
  synthetic event pipeline successfully.
- The container API used the same volume on port 8011 because the Day 1 API already occupied
  port 8000. `/ready` and `/api/v1/overview` returned HTTP 200; the overview showed the
  selected-model AP 0.251506 and constant-prior AP 0.160000. The temporary container,
  project network and volume were removed afterward.
