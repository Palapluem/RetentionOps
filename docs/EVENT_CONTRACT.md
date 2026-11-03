# Synthetic subscription event and analyst contract

Decision owner: Palapluem / Codex. Status: implementation contract, 2026-11-03.
Resolves: Define temporal event, renewal-label, and analyst-serving contracts.

## Observation and label

Observation grain is synthetic customer × scheduled expiry, with prediction cutoff equal
to the scheduled expiry date. A subscription opportunity must already be known before
that cutoff. Churn means no renewal event for that opportunity in the inclusive interval
`[expiry, expiry + 30 days]`. Source completeness and evaluation freeze must cover that
interval. Labels use the latest revisions available at freeze; a late outcome correction
that adds, removes or changes a qualifying renewal advances label availability. It cannot
silently enter an earlier training cohort.
This is a project-defined simulation, not the unverified KKBox competition definition.
Repeated monthly opportunities can represent reactivation; it is not a survival cohort.

## Local source intake and replay

The first local pipeline stage accepts newline-delimited JSON only when each row conforms to
`subscription-events-v1`. It currently requires synthetic event/customer identifiers and
`source_type: SYNTHETIC`; it does not accept raw KKBox files or claim a general source mapping.
`retentionops ingest-events` requires an explicit source ID and completeness watermark. It
copies the source into staging, validates payloads, duplicate/revision continuity, logical
identity, availability watermark and row reconciliation, then atomically publishes an
immutable release at `data/events/{source_id}-{release_identity_sha256}/`. The identity
includes source ID, raw-byte hash, schema, source type and completeness watermark, so a later
completeness assertion is a new version. The deterministic manifest records source identity,
raw hash, schema, watermark, row/logical-event/customer counts, quality checks and rights
boundary. Exact replays reuse the release; corruption and invalid sources fail closed without
publishing.

`retentionops run-events --source-release ...` verifies the release and manifest, derives
point-in-time features and labels, writes an immutable typed Parquet feature release keyed by
source, dataset, freeze, feature implementation and Polars version, then runs the established
temporal model evaluation and atomic serving publication.
`retentionops events` uses the same stages after generating a synthetic source. Local files
and generated data stay under ignored `data/`; do not place the Execution Kit or licensed data
in the repository.

GCS object generations, BigQuery bronze tables, cloud IAM, Cloud Run jobs and scheduling are
not implemented in this local adapter. They remain blocked on verified source rights and the
owner's GCP project, region, budget and access setup.

## Bitemporal feature rules

Event key is `(event_id, revision)`; a logical ID retains customer and event kind across
revisions. `occurred_at <= available_at`. A source retains contiguous revision history
starting at 1; missing earlier revisions fail because snapshots could silently lose events.
Latest revision known by cutoff wins, including tombstones. Choose the revision **before**
filtering event time, so corrected/deleted
events cannot resurrect an obsolete value. Unknown future revisions have no effect.

Feature event windows are right-exclusive: `[cutoff - 30 days, cutoff)` for distinct active
days and `[cutoff - 90 days, cutoff)` for failed payments. Availability is inclusive at
day-grain cutoff. Plan/fee/auto-renew/start date come from the known subscription record.
Tenure is completed 30-day months, at least one. Cancellation is not a feature; future
cancellation flags and all renewal outcomes are excluded from the model feature allowlist.
Provenance includes latest contributing event/availability, source release and derived hash.

Duplicate revision keys, changing logical identities, invalid date/range/payload, ambiguous
subscription opportunities and incomplete label horizons fail closed. Missing known
subscription opportunities are explicitly excluded and counted. Corrections form a new
immutable source release. Single local writer per root remains the operating constraint.

## Analyst-serving contract

Default risk view is the active model's scored historical test cohort. Support bounded
pagination, customer search, risk band and auto-renew filters, descending probability order,
customer detail with actual feature values, cohort summaries and model/data/job status.
Every view carries model/source/cutoff lineage. Cohort observed churn uses mature eligible
rows as its denominator; predicted risk belongs only to the scored test cohort.

The Next.js product has Overview, Risk explorer, Cohorts, and Data & model views. Errors,
loading, empty results and stale historical cutoffs are explicit. UI feature values describe
observations; do not invent causal explanations, saved customers or proven campaign ROI.
The local app binds to loopback; cloud authentication/deployment is a separate gated task.
