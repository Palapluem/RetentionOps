# Local operations, incidents and cloud readiness

## Normal operation

Activate the venv; run `retentionops events` for the generated event demo or run the staged
source workflow below; start Uvicorn bound to `127.0.0.1`. `/health` is process liveness.
`/ready` is HTTP 200 only when the serving database contains an active manifest and
reconciled score count; it does not mean that historical data is fresh today. Overview reports
both `trained_at` and `score_cutoff`. Only one pipeline writer per root.

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

To avoid overwriting an earlier experiment, pass `--root` and matching `RETENTIONOPS_ROOT`.
Do not load joblib files from an untrusted source; they are executable serialization. The
API never deserializes a model and has no write or arbitrary SQL endpoint.

## Failed source/training/publication

1. Stop the writer and inspect its error. Validation/training failures do not change the
   active publication; SQLite rolls back invalid score batches.
2. Confirm `/ready` and the overview model version. A failed run is not a successful refresh.
3. Correct the synthetic input/generator/config in a reviewed branch, run focused tests,
   then re-ingest and replay. The raw source hash prevents duplicate releases; do not edit a
   published release in place.
4. Verify row reconciliation, model checksum and risk version before using results.

Corrupt source/model directories fail closed and are never silently overwritten. Preserve
the damaged root for diagnosis. Restore a verified backup or run a separate clean root.
The prior score publication can continue serving, but training should not ignore corruption.

## Local rollback / replay

The pipeline's `publish` function can activate an existing release in the same transaction
as restoring its scores. The tested operational path for this slice is replaying an earlier
documented `--customers`, `--seed`, `--as-of` configuration **on the same code/dependency
revision**. This retains the original manifest and reactivates that model. Across code
changes, use the earlier reviewed commit and locked environment in a separate root; verify
its model/data hashes before switching the API root and restarting. Do not update an active
pointer alone or claim a cloud rollback drill has passed.

## Docker

`docker compose run --rm pipeline` populates the `demo` volume; `docker compose up api`
serves it read-only. The image uses an unprivileged user. Stop with `docker compose down`;
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
