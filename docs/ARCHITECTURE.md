# Architecture

## Implemented local slice

```mermaid
flowchart LR
  G[Synthetic generator or synthetic JSONL file] --> I[Staged intake: schema, identity, revision, watermark]
  I --> R[(Immutable event release + quality manifest)]
  R --> F[Point-in-time features + mature renewal labels]
  F --> Q[(Immutable CSV / typed Parquet feature release)]
  Q --> T[Train-only Logistic Regression + bounded LightGBM candidates]
  T --> E[Validation-only selection, then frozen test evaluation]
  T --> M[(Immutable model + source lineage)]
  E --> P[Atomic publication]
  M --> P
  P --> S[(SQLite active release + scores)]
  S --> A[Typed read-only FastAPI]
  A --> U[Local analyst dashboard]
```

`events.py` owns event schema, local intake, immutable raw source releases, quality reports and
point-in-time feature derivation. `data.py` owns the earlier snapshot schema/intake;
`training.py` owns train-only model fitting and validation-only candidate selection;
`pipeline.py` coordinates model selection, artifacts and lineage; `storage.py` owns
publication transactions; `api.py` serves bounded results; `cli.py` exposes generation,
ingestion, replay, and the one-command demo. Shared code is in `src/retentionops/`.

Synthetic event intake copies the input into staging, validates all rows and revisions against
the declared completeness watermark, writes deterministic provenance, then renames the
release directory atomically. Replay verifies the raw hash and quality evidence before
derivation. Feature Parquet and model artifacts are immutable and content-addressed. SQLite
commits manifest, predictions and the active pointer together. A request reads the active
manifest and scores within one read transaction, preventing mixed model releases.

Local constraints: the event adapter accepts only the synthetic event schema and IDs; it is
not a real-data/KKBox source adapter. One pipeline writer per root; CSV intake materializes in
memory; SQLite serves small demos; no cloud scheduler or GCS/BigQuery integration exists. The
legacy `all` command still uses simulated snapshot features. Model family and LightGBM grid
selection use validation average precision; test is evaluated after freeze. The local
manifest carries candidate results, selected parameters and dependency/source/model hashes.
Cloud resources remain planned, not provisioned.

## Target cloud architecture (planned)

```mermaid
flowchart TB
  D[Authorized historical / synthetic sources] --> G[(Private GCS versioned raw)]
  G --> I[Cloud Run ingestion job]
  I --> B[(BigQuery bronze)]
  B --> F[Polars/PyArrow + SQL normalization and PIT features]
  F --> Q[(BigQuery silver/gold/analytics/features)]
  Q --> T[Cloud Run training job: Logistic / LightGBM]
  T --> M[(GCS model + experiment manifests)]
  M --> P[Cloud Run scoring job]
  Q --> P
  P --> S[(BigQuery governed risk mart)]
  S --> A[Private FastAPI Cloud Run service]
  A --> U[Next.js TypeScript dashboard]
  C[Cloud Scheduler] -.-> I
  C -.-> P
  O[GitHub OIDC delivery] -.-> A
  L[Cloud Logging / Monitoring] -.-> I
  L -.-> T
  L -.-> P
```

No resources in this diagram are claimed to exist. Region, account/project, billing alerts,
IAM, API enablement and teardown need a verified plan and owner approval before creation.
Batch-first serving decouples analyst requests from expensive model execution. BigQuery
queries must use governed views, partition predicates and maximum bytes billed.
