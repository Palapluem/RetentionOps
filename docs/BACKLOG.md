# Critical path and tracked work

[Engineering foundation and verified synthetic vertical slice](https://github.com/Palapluem/RetentionOps/issues/1)
tracks the Day 1 implementation. The 24 Execution Kit tickets were reviewed as planning
input; they have not been mass-created or marked done. This list groups their deliverables
into reviewable follow-up slices. Each slice needs an issue, acceptance criteria, tests,
evidence, branch and PR before implementation.

Created follow-ups:
[Verify cloud readiness and review a bounded GCP resource plan](https://github.com/Palapluem/RetentionOps/issues/2)
and [Derive synthetic features from subscription events with point-in-time tests](https://github.com/Palapluem/RetentionOps/issues/3).
The local intake follow-up [Add replayable local event-source ingestion](https://github.com/Palapluem/RetentionOps/issues/10)
now separates source generation, quality-gated intake, and replayable feature/model execution;
it is under review in [PR #11](https://github.com/Palapluem/RetentionOps/pull/11).

| Planned period | Next deliverable | Dependency / acceptance |
|---|---|---|
| Nov 4 foundation | Review Day 1 PR, establish governance and source rights gate | Local evidence + CI; confirm branch rules/board support; record approved data rights |
| Nov 5 data platform | Local event-source intake is implemented; GCS versioned intake and BigQuery bronze remain | Cloud project, source rights, budget and IAM approval; source hashes/counts; idempotent replay |
| Nov 6 features | Subscription events, normalization, PIT feature snapshots | Actual source contract; independent event/correction cutoff fixtures |
| Nov 9 ML | LightGBM comparison, experiment tracking and batch scoring | Validation-only selection, artifact provenance, warehouse unique keys |
| Nov 10 backend | Governed warehouse views, access controls, Cloud Run API | Least-privilege identity, auth denial and query-cost bounds |
| Nov 11 frontend | Next.js risk/cohort/freshness/model views | Typed API, desktop/mobile/error/loading/empty E2E |
| Nov 12 reliability | OIDC deployment, schedule/monitoring, recovery/cost drills | Actual run/revision IDs and failure/recovery evidence |
| Nov 13 release | Clean checkout, human audit, model card, demo | All P0 gates pass before v0.1.0 |

Independent work while cloud is unavailable: event-based synthetic generator, replayable
local intake, feature-window and late-arrival tests, local Parquet/source contracts and cloud
adapter tests using an explicit fake boundary. Fakes must never be labeled as Google Cloud
integration evidence.
Do not let the calendar bypass correctness, rights, privacy or release gates.
