# Architecture

## Implemented local slice

```mermaid
flowchart LR
  G[Synthetic snapshot generator] --> V[Strict schema + temporal validation]
  V --> R[(Content-addressed local raw release)]
  R --> T[Train-only scaling + Logistic Regression]
  T --> E[Validation/test and constant-prior comparison]
  T --> M[(Immutable model + manifest)]
  E --> P[Atomic publication]
  M --> P
  P --> S[(SQLite active release + scores)]
  S --> A[Typed read-only FastAPI]
  A --> U[Local smoke dashboard]
```

`data.py` owns source schema/intake; `training.py` owns the fixed evaluation protocol;
`pipeline.py` coordinates artifacts and lineage; `storage.py` owns publication transactions;
`api.py` serves bounded results; `cli.py` explicitly runs work. Shared code is in
`src/retentionops/`; introduce `apps/web/` and separate job entrypoints as those are built.

Data is generated at customer × cutoff grain. The entire source is validated before a raw
release becomes visible. Models are written through a staging directory then renamed.
SQLite commits manifest, predictions and the active pointer together. A request reads the
active manifest and scores within one read transaction, preventing mixed model releases.

Local constraints: one pipeline writer per root; CSV materializes in memory; SQLite serves
small demos; no public authentication; no cloud scheduler; feature values are simulated,
not computed from raw subscription/activity events. Provenance fields are checked but
cannot independently prove that an external aggregate was generated correctly.

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
