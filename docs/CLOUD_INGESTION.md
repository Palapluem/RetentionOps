# Optional GCS and BigQuery ingestion

## Status

The repository contains an explicit adapter for publishing a **validated synthetic event
release** to Google Cloud Storage and loading its bronze rows into BigQuery. It is covered by
offline fake-client tests. No GCP account, project, bucket, dataset, table, IAM change, billing
setup or real cloud job has been used or verified. A fake-client pass is not GCP integration
evidence.

## Data path

```text
local immutable event release
  ├─ exact events.jsonl ─┐
  ├─ manifest.json ──────┼─> existing private, versioned GCS bucket
  └─ bronze/events.ndjson┘            │
                                      └─> existing partitioned BigQuery bronze table
```

The raw JSONL bytes are preserved as received. A separate bronze JSONL file adds release
lineage, source completeness, validated event fields and a per-event SHA-256. The object key
contains the source release ID, while object metadata records the byte checksum and artifact
kind. Re-upload uses the Cloud Storage generation precondition `if_generation_match=0`;
an existing object is accepted only when its metadata and downloaded bytes match. The returned
generation is included in the CLI report.

The BigQuery destination must already exist as a native table. The adapter checks its exact
bronze schema, location, `complete_through` partition, and clustering by
`source_release_id, event_id`. Loads
use an explicit schema, `CREATE_NEVER`, `WRITE_APPEND`, deterministic job IDs, and at most
three deterministic attempts after a confirmed failed job. An unknown job outcome stops for
manual reconciliation. Before and after a load, the adapter streams the release rows back and
compares every typed event field, event hash, revision key and source-lineage field with the
validated local release. Replays with a fully reconciled release are no-ops; partial or
inconsistent prior rows fail closed. Reconciliation queries require a positive
`maximum_bytes_billed` value.

Google documents that `if_generation_match=0` means an object can be created only when no live
version exists, and that GCS-to-BigQuery loads should use colocated locations. BigQuery load
jobs support `CREATE_NEVER` and atomic `WRITE_APPEND`; custom job IDs are needed to avoid
duplicate appends when retrying an uncertain submission. See [GCS generation preconditions](https://docs.cloud.google.com/python/docs/reference/storage/latest/generation_metageneration),
[GCS bucket security settings](https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.bucket.IAMConfiguration),
[BigQuery load job configuration](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job),
[BigQuery reliability and job IDs](https://docs.cloud.google.com/bigquery/docs/reliability-intro),
and [BigQuery locations](https://docs.cloud.google.com/bigquery/docs/locations).

## Resource contract

The adapter does not create or change cloud resources. Before use, the owner must complete the
account/project, source-rights, region, billing/budget, IAM and cleanup review in
[issue #2](https://github.com/Palapluem/RetentionOps/issues/2) and obtain explicit approval
for cloud writes. The following resources must already be prepared:

- A private Cloud Storage bucket with Object Versioning enabled, uniform bucket-level access,
  and Public Access Prevention explicitly enforced.
- A BigQuery dataset and native bronze table in the exact same selected location as the bucket.
- An ADC identity with only the required object and load/query permissions. No service-account
  key is supported or stored by this code.
- A maximum total upload size and a maximum billed query size chosen by the owner.

The table contract is [bigquery_bronze_events.json](../contracts/bigquery_bronze_events.json).
This SQL is a setup template only; it has not been run:

```sql
CREATE TABLE `YOUR_PROJECT.analytics.bronze_events` (
  source_release_id STRING NOT NULL,
  source_id STRING NOT NULL,
  source_sha256 STRING NOT NULL,
  schema_version STRING NOT NULL,
  complete_through DATE NOT NULL,
  event_id STRING NOT NULL,
  revision INT64 NOT NULL,
  customer_id STRING NOT NULL,
  kind STRING NOT NULL,
  occurred_at DATE NOT NULL,
  available_at DATE NOT NULL,
  deleted BOOL NOT NULL,
  expiry_date DATE,
  started_at DATE,
  monthly_fee FLOAT64,
  auto_renew INT64,
  source_type STRING NOT NULL,
  event_sha256 STRING NOT NULL
)
PARTITION BY complete_through
CLUSTER BY source_release_id, event_id;
```

Object versioning can add storage cost for retained noncurrent versions. Choose retention and
lifecycle settings as part of the reviewed resource plan; this adapter does not delete data.
The exact-location requirement is intentionally conservative and avoids transfer charges from
misplaced bucket/dataset pairs.

## Install and run after approval

The default local path remains free of Google SDK dependencies. To install the optional SDKs,
use the separate hash-locked dependency file:

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install --require-hashes -r requirements-cloud.lock
python -m pip install --no-deps --no-build-isolation -e .
```

After setting up Application Default Credentials and approving the concrete GCP plan, first
ingest a local synthetic source and inspect its report. Then run the cloud write explicitly:

```bash
retentionops publish-gcp \
  --root . \
  --source-release 'PASTE_SOURCE_RELEASE_ID' \
  --bucket 'YOUR_PRIVATE_BUCKET' \
  --table 'YOUR_PROJECT.analytics.bronze_events' \
  --location 'YOUR_SELECTED_LOCATION' \
  --max-upload-bytes 50000000 \
  --max-query-bytes 50000000
```

The byte limits above are examples, not a budget recommendation. Pick bounds that match the
owner-approved source and spending plan. The command never runs as part of `retentionops
events`, model training, API startup or container startup. If a BigQuery step fails after the
GCS uploads, the immutable GCS artifacts remain; re-running the same release verifies and
reuses them. Do not delete or overwrite them to recover.

## Limits of current evidence

- The intake contract accepts `SYNTHETIC` IDs/events only. It does not authorize or map KKBox
  or customer data.
- Tests exercise protocol behavior with fake clients; they do not test IAM, credentials,
  bucket/dataset location compatibility, quotas, real retries, cloud cost or cloud logs.
- No Cloud Run, Scheduler, BigQuery production mart, authentication or public endpoint is
  implemented by this adapter.
- Cloud execution remains blocked until the owner has a GCP account/project and approves the
  concrete resource/budget/cleanup plan. Record actual object generations and BigQuery job IDs
  only after a real run.
