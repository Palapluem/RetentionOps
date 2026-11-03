# Critical path and tracked work

The 24 Execution Kit tickets were reviewed as planning input; they have not been mass-created
or marked done. The slices below are tracked with acceptance criteria, tests and evidence.
Implementation PRs remain unmerged until owner review of their GitHub diffs and checks.

## Implemented locally; awaiting review and merge

- [ROP-001 — Engineering foundation and verified synthetic vertical slice](https://github.com/Palapluem/RetentionOps/issues/1)
  — PR #4, ready for review.
- [ROP-003 — Derive synthetic features from subscription events with point-in-time tests](https://github.com/Palapluem/RetentionOps/issues/3)
  — PR #8, ready for review; includes label-correction maturity and multi-attempt count fixes.
- [ROP-007 — Build an API-backed Next.js retention analyst workspace](https://github.com/Palapluem/RetentionOps/issues/7)
  — PR #9, stacked on the event PR; local browser and container evidence is recorded.

The branches are ordered foundation → event features → analyst workspace. Review each PR on
its own base; merge the foundation before the event PR and the event PR before the workspace.

## Open external readiness gate

[ROP-002 — Verify cloud readiness and review a bounded GCP resource plan](https://github.com/Palapluem/RetentionOps/issues/2)
remains open. The owner has not created a GCP account. A plan and Thai onboarding guide are
ready, but account/project/region/budget and cost/IAM approvals are not available. Continue
local work; do not provision resources or claim cloud integration.

| Planned period | Next deliverable | Dependency / acceptance |
|---|---|---|
| Current review | Merge the foundation, event and analyst workspace in dependency order | Owner reviews each diff; branch CI passes; no kit/raw data in repository |
| Cloud onboarding | Verify account, project, region and monthly budget | Owner sign-up and concrete cost/IAM approval; no resource creation before authorization |
| Source readiness | Establish legal access and a defensible renewal label | Approved source contract, point-in-time mapping and independently tested corrections |
| Cloud data platform | Versioned GCS intake and BigQuery bronze/features | Idempotent replay, reconciliation, access denial and bounded query cost |
| Production model | Compare candidates and promote by validation only | Reproducible training, calibration and independent customer/time evaluation |
| Production service | Governed views, authenticated API/UI and scheduled jobs | Least privilege, recovery/cost drills and actual deployed revision IDs |
| Release | Clean checkout, human audit, model card and demo | All P0 gates pass before v0.1.0 |

Independent work while cloud is unavailable: maintain the event contract and synthetic test
fixtures, improve the local workspace, and prepare cloud integration tasks. Fakes must never
be labeled as Google Cloud integration evidence. Do not let the calendar bypass correctness,
rights, privacy or release gates.
