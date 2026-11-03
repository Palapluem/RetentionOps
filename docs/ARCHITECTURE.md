# Architecture

## Implemented local slice

```mermaid
flowchart LR
  G[Synthetic subscription events] --> K[Latest known revisions / point-in-time features]
  K --> V[Strict schema + temporal validation]
  V --> R[(Immutable event / CSV / Parquet release)]
  R --> T[Train-only scaling + Logistic Regression]
  T --> E[Validation/test and constant-prior comparison]
  T --> M[(Immutable model + manifest)]
  E --> P[Atomic publication]
  M --> P
  P --> S[(SQLite active release + scores)]
  S --> A[Typed read-only FastAPI]
  A --> U[Next.js analyst workspace]
```

`events.py` owns bitemporal event features; `data.py` owns snapshot schema/intake; `training.py` owns the fixed evaluation protocol;
`pipeline.py` coordinates artifacts and lineage; `storage.py` owns publication transactions;
`serving.py` reads consistent workspace views; `runs.py` records actual attempts;
`api.py` serves bounded results and `apps/web/` provides Next.js/TypeScript. Shared Python is in
`src/retentionops/`; separate cloud job entrypoints when those adapters are built.

Data is generated at customer × cutoff grain. The entire source is validated before a raw
release becomes visible. Models are written through a staging directory then renamed.
SQLite commits manifest, features, predictions, active pointer and successful run state together. A request reads the
active manifest and scores within one read transaction, preventing mixed model releases.

Local constraints: one pipeline writer per root; CSV materializes in memory; SQLite serves
small demos; no public authentication; no cloud scheduler; features are
computed from simulated events on the `events` path. The legacy `all` path still simulates
feature values directly. Source completeness is defined by the synthetic generator; an
external source needs independent rights/schema/watermark verification.

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
