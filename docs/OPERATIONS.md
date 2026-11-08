# Local operations, incidents and cloud readiness

## Normal operation

Activate the venv; run `retentionops events` for the generated event demo or run the staged
source workflow below; start Uvicorn bound to `127.0.0.1`. `/health` is process liveness.
`/ready` is HTTP 200 only when the serving database contains an active manifest and
reconciled score/feature keys and cohort counts. Overview reports `trained_at` and
`score_cutoff`; the fixed historical cutoff is visible separately from service readiness.
Only one pipeline writer per root.

### Inspect System state

The Next.js root `/` and `/system` show the System dashboard. `/overview`, `/risk`,
`/cohorts` and `/status` provide the retention and data/model views. Read-only
`GET /api/v1/system-status` returns a status document even before a successful publication;
it does not create or migrate a database. Inspect `publication_state` in its response:

- `ready`: the active release reconciles with materialized scores, features and cohorts.
- `empty`: no active publication exists; readable failed/running attempts are still shown.
- `unavailable`: storage or publication verification failed; inspect the local root and retry.

`model_artifact_state` reports checksum verification separately from publication readiness.
The API hashes model bytes without deserializing them. A missing or mismatched artifact needs
investigation even when existing materialized scores remain readable. Source truth identifies
the simulated snapshot or renewal label. Infrastructure reports local SQLite, cloud not
connected and authentication not configured; these fields do not verify GCP readiness.
Expand Source & artifact evidence for the active source/event release IDs and dataset/model
checksums when tracing the displayed publication.

### Ingest and replay an event source

The local intake is synthetic-only. Generate a sample source or provide a file already
conforming to the versioned event contract. Declare the source identity and latest complete
availability date explicitly:

```bash
retentionops generate-events --output data/incoming/demo-events.jsonl --customers 650
retentionops ingest-events --input data/incoming/demo-events.jsonl \
  --source-id demo-feed --complete-through 2026-11-03
```

Review the returned `source_release_id` and quality counts, then replay that immutable source:

```bash
retentionops run-events --source-release 'PASTE_SOURCE_RELEASE_ID'
```

The replay verifies the source and manifest before deriving features or training. Identical
source bytes with the same source ID and watermark are idempotent. Failed validation leaves
no new event release and does not alter the serving publication. This path does not connect
to GCS or BigQuery; cloud ingestion remains a separate gated implementation.

The CLI records `generate-events` as `source-generation` and `ingest-events` as `source-intake`.
Source-stage success is recorded after file output or intake validation/publication finishes.
Filesystem output and the run-history database have separate commit boundaries; an existing
source output does not prove that its attempt status was persisted. Source stages leave the
active model release unchanged.
Generation creates an output without replacing an existing file: exact-byte replay of an
ordinary file is accepted, while different bytes, symlinks and managed release locations are
rejected. Choose a new incoming filename for a different generated source.

To avoid overwriting an earlier experiment, pass `--root` and matching `RETENTIONOPS_ROOT`.
Do not load joblib files from an untrusted source; they are executable serialization. The
API never deserializes a model and has no write or arbitrary SQL endpoint.

## Failed source/training/publication

1. Stop the writer and inspect its error. Validation/training failures do not change the
   active publication; SQLite rolls back invalid score batches.
2. Inspect System state or `/api/v1/jobs`, including before the first publication, then confirm
   `/ready` and the active model version. A failed attempt retains the prior valid release.
3. Correct the synthetic input/generator/config in a reviewed branch, run focused tests,
   then re-ingest and replay. The raw source hash prevents duplicate releases; do not edit a
   published release in place.
4. Verify row reconciliation, model checksum and risk version before using results.

Corrupt source/model directories fail closed and are never silently overwritten. Preserve
the damaged root for diagnosis. Restore a verified backup or run a separate clean root.
The prior score publication can continue serving, but training should not ignore corruption.

## Local rollback / replay

The pipeline's `publish` function can reactivate an existing immutable release in the same
transaction as verifying its features and scores. Exact feature/score replay is accepted;
conflicting content for an existing key rejects the transaction and preserves the active
release. The operational path for this slice is replaying an earlier
documented `--customers`, `--seed`, `--as-of` configuration **on the same code/dependency
revision**. This retains the original manifest and reactivates that model. Across code
changes, use the earlier reviewed commit and locked environment in a separate root; verify
its model/data hashes before switching the API root and restarting. Do not update an active
pointer alone or claim a cloud rollback drill has passed.
The synthetic integration test `tests/test_recovery_drill.py` exercises event releases A → B,
a failed source run that preserves B, and replay of A, checking API results, scores,
features, artifact verification and run history in a temporary local root.

## Docker

`docker compose up --build --wait api web` can start against an empty `demo` volume.
The API healthcheck uses `/health`, and the web healthcheck uses the same-origin
`/api/retention/system-status`; both allow System to show empty/first-failed state.
`/ready` separately requires a reconciled score publication. Run
`docker compose run --rm pipeline` to populate the volume; the API serves it read-only.
The image uses an unprivileged user. Stop with `docker compose down`;
that retains the local demo volume. `docker compose down --volumes` deliberately removes
that generated demo state, so use it only when the owner intends to discard it. No host
source directory is mounted into the container.

## Cloud readiness and approval gate

Run `python scripts/cloud_preflight.py`. It reads installed tool status and, if available,
whether account/project are configured; it does not print their identifiers or modify cloud
state. A CLI is not proof of billing/IAM readiness. Review privately:

- Verified account, dedicated project and co-located GCS/BigQuery/Cloud Run region.
- Budget owner and spending allowance; alerts are notifications, not a hard cost cap.
- Required APIs, least-privilege ingest/train/score/API identities and separate CI identity.
- Private bucket access, bounded BigQuery bytes, Cloud Run scale/timeouts and retention.
- OIDC/Workload Identity Federation restricted by repository/ref, no persistent SA keys.
- Exact billable resource plan, cleanup sequence and explicit owner approval.

After approval, record redacted resource inventory and actual job/revision IDs. Cleanup
starts by disabling schedules, then removes approved services/jobs/images and reviews
retained storage, warehouse tables/logs and billing. No bootstrap/apply script is included
until its resource plan and safety conditions are verified.

## System and analyst workspace operation

A named local environment can be started with
`docker compose -p retentionops-day1 up --build --wait api web`, followed by
`docker compose -p retentionops-day1 run --rm pipeline` when ready to publish.
Product: http://127.0.0.1:3000; API: http://127.0.0.1:8000/docs.
Run the event pipeline after upgrading; it creates the new feature/run tables during the
writer step. API startup never migrates or writes storage. `/ready` reconciles scored keys
with feature rows and all cohort counts, not only database existence.

Source and model stages record actual attempts. Model modes are `snapshots` from `all`,
generated `events` from `events`, and ingested `event-source` from `run-events`.
Model success commits with features, scores and the active pointer; failed attempts retain
the last valid result. The run table's Output rows counts event revisions for source stages
and scored customers for model stages.
Process termination can leave a running attempt: inspect the actual process and
replay manually; automatic stale-job reconciliation/cloud orchestration is not implemented.
A replay records a new attempt but retains the immutable model training timestamp.

Data & model status reports the selected family, candidate, parameters and recorded validation AP,
including LightGBM-selected releases. Overview and customer details use that selected release.
Risk filters and pagination are encoded in the URL; links can be reloaded or shared.

Web uses a fixed server-side API URL, allowlisted read routes and no-store responses.
It has no production authentication and remains loopback-only. TypeScript contracts must
be regenerated from OpenAPI when backend contracts change. `npm run start` loads the
production standalone server after `npm run build` copies static assets; it is not a dev server.
See docs/CLOUD_ONBOARDING_TH.md before any cloud account/resource or identity work.
