# Critical path and tracked work

[Engineering foundation and verified synthetic vertical slice](https://github.com/Palapluem/RetentionOps/issues/1)
tracks the Day 1 implementation. The 24 Execution Kit tickets were reviewed as planning
input; they have not been mass-created or marked done. This list groups their deliverables
into reviewable follow-up slices. Each slice needs an issue, acceptance criteria, tests,
evidence, branch and PR before implementation.

## Local implementation and integration

- [Establish engineering foundation and verified synthetic vertical slice](https://github.com/Palapluem/RetentionOps/issues/1) — [foundation PR](https://github.com/Palapluem/RetentionOps/pull/4).
- [Derive synthetic features from subscription events with point-in-time tests](https://github.com/Palapluem/RetentionOps/issues/3) — [event-features PR](https://github.com/Palapluem/RetentionOps/pull/8), including label corrections and maturity tests.
- [Build an API-backed Next.js retention analyst workspace](https://github.com/Palapluem/RetentionOps/issues/7) — [workspace PR](https://github.com/Palapluem/RetentionOps/pull/9), with local browser/container evidence.
- [Add replayable local event-source ingestion](https://github.com/Palapluem/RetentionOps/issues/10) — [intake PR](https://github.com/Palapluem/RetentionOps/pull/11), separating generation, quality-gated intake and replay.
- [Add LightGBM candidate comparison and experiment manifest](https://github.com/Palapluem/RetentionOps/issues/14) — [model PR](https://github.com/Palapluem/RetentionOps/pull/15), with validation-only selection and immutable selected-model scores.
- [Integrate the selected-model API and local system dashboard](https://github.com/Palapluem/RetentionOps/issues/16) — current integration of workspace, source intake and model-publication behavior; combined verification is required.

The dependency chain starts with foundation → event features → local intake → model selection.
The workspace branches from event features. Review the combined API, pipeline and storage
changes when integrating these branches; a green check against one PR's current base does
not prove the combined stack. Keep review diffs focused and retest after each base change.

## External readiness and schedule

The owner has not created a GCP account. The resource plan and Thai onboarding guide are
available, while account/project/region/budget and cost/IAM approvals remain open. Source
rights, approved eligibility and the business label definition are unresolved.

Cloud readiness remains tracked in
[Verify cloud readiness and review a bounded GCP resource plan](https://github.com/Palapluem/RetentionOps/issues/2).

| Planned period | Next deliverable | Dependency / acceptance |
|---|---|---|
| Nov 4 foundation | Review Day 1 PR, establish governance and source rights gate | Local evidence + CI; confirm branch rules/board support; record approved data rights |
| Nov 5 data platform | Local event-source intake is implemented; GCS versioned intake and BigQuery bronze remain | Cloud project, source rights, budget and IAM approval; source hashes/counts; idempotent replay |
| Nov 6 features | Subscription events, normalization, PIT feature snapshots | Actual source contract; independent event/correction cutoff fixtures |
| Nov 9 ML | [ROP-011](https://github.com/Palapluem/RetentionOps/issues/14): bounded LightGBM comparison, immutable local experiment manifest and selected-model batch scoring | Validation-only selection, artifact provenance, SQLite model/cutoff/customer unique keys; Cloud Run and BigQuery batch scoring remain gated by ROP-002 |
| Nov 10 backend | Integrate the selected-model workspace API; prepare governed cloud reads | Consistent model/source identity and bounded queries; cloud identity, auth denial and query-cost bounds remain gated |
| Nov 11 frontend | Integrate Next.js risk/cohort/freshness/model views | Typed API, desktop/mobile/error/loading/empty E2E and provenance |
| Nov 12 reliability | OIDC deployment, schedule/monitoring, recovery/cost drills | Actual run/revision IDs and failure/recovery evidence |
| Nov 13 release | Clean checkout, human audit, model card, demo | All P0 gates pass before v0.1.0 |

Independent work while cloud is unavailable: event-based synthetic generator, replayable
local intake, feature-window and late-arrival tests, local Parquet/source contracts and cloud
adapter tests using an explicit fake boundary. Fakes must never be labeled as Google Cloud
integration evidence.
Do not let the calendar bypass correctness, rights, privacy or release gates.

November 7–8 are optional buffer days. [The Day 1–4 re-audit](evidence/DAYS1_4_REAUDIT_2026-11-07.md)
records the local evidence and the remaining cloud/real-source gates.
