# Day 2 checkpoint: local data platform and cloud adapter boundary

Date: 2026-11-04 (Asia/Bangkok)
Work item: [Add optional GCS and BigQuery adapters for synthetic releases](https://github.com/Palapluem/RetentionOps/issues/12)
Branch: `feat/rop-009-gcp-ingestion-adapters`

## Implemented

- Added an optional, separately hash-locked Google Cloud SDK dependency set. The default local path remains credential-free.
- Added explicit `retentionops publish-gcp` orchestration for locally validated synthetic event releases.
- GCS upload preserves exact raw bytes and the manifest, plus a typed bronze NDJSON artifact. It checks bucket location, Object Versioning, uniform bucket-level access, Public Access Prevention, explicit total upload size, generation preconditions and existing-object checksums.
- BigQuery load requires an existing native table with the declared schema, `complete_through` partition and `source_release_id,event_id` clustering. It uses `CREATE_NEVER`, `WRITE_APPEND`, deterministic bounded job attempts, `maximum_bytes_billed`, and streamed field/hash/key/lineage reconciliation against the validated local events.
- Hardened the handoff against local source changes between validation and upload by staging and rechecking source SHA-256. The BigQuery URI is restricted to the expected bronze object path for that exact release.
- Added fake-client tests for replay, conflicting metadata, row/key/hash/lineage mismatches, altered fields with a preserved hash, missing targets, failed/unknown jobs, plus a no-credential test using the installed BigQuery SDK to validate request configuration.

## Verification

- `bash scripts/local_smoke.sh`: **103 passed**, Ruff checks and repository hygiene passed. One existing Starlette/httpx deprecation warning was reported by FastAPI's test client.
- Synthetic event E2E: 69,748 input event revisions → 2,600 eligible feature rows → train 1,300 / validation 650 / test 650. This is generated data only.
- `python -m pip install --require-hashes -r requirements-cloud.lock`: succeeded with `google-cloud-storage 3.17.1` and `google-cloud-bigquery 3.47.0`.
- `pip-audit` for both `requirements.lock` and `requirements-cloud.lock`: no known vulnerabilities found.
- SDK signatures were inspected locally; tests confirm the BigQuery job configuration objects construct successfully without credentials.

## Cloud evidence boundary

`python scripts/cloud_preflight.py` reports `gcloud=false`, `bq=false`, account/project/region/billing/IAM as `NOT_VERIFIED`. The owner has not created a GCP account. No API calls, bucket/table writes, resource creation, billing changes or IAM changes were made. The adapter tests use fakes and are not evidence of a real Google Cloud integration. Real GCS generations, BigQuery job IDs, permissions, query costs and recovery remain pending issue #2 and explicit approval.

The local Execution Kit remains ignored and was not staged or uploaded. A separate untracked `apps/` directory was preserved and excluded from this work.
