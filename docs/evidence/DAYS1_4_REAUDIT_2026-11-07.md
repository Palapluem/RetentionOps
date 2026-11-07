# Day 1–4 re-audit

Audit date: 2026-11-07 (Asia/Bangkok)
Reviewed implementation: `feat/rop-011-lightgbm-candidate` at `d7fa790`
Scope: repository plan, current open PR stack, local synthetic pipeline, tests, source/label contract, and available CI evidence.

## Exit-gate status

| Day | Local result | Still open |
|---|---|---|
| 1 — foundation | Synthetic snapshot pipeline, contracts, local API and evidence are present. | Source rights, GCP account/project/billing/IAM, production authentication and release gates are unverified. |
| 2 — intake | Local synthetic JSONL generation, validation, immutable source release, idempotent intake and replay are implemented. PR #13 adds optional GCS/BigQuery adapters behind explicit resource prerequisites and fake-client tests. | No live GCS or BigQuery call, real source, or cloud row reconciliation has been verified. |
| 3 — feature platform | Synthetic event-time/availability-time features, renewal labels, cutoff windows, maturity embargo, immutable Parquet lineage and correction/late-event tests are present. | No authorized source mapping or real-data/warehouse Silver and Gold transformations have been validated. |
| 4 — modeling and scoring | Validation AP selects the model/config; frozen holdout metrics are reported afterward. Only selected test-cohort scores publish transactionally to local SQLite with replay and conflict protection. | No Cloud Run batch job, BigQuery prediction table/MERGE, or real-data model result. |

The calendar assigns Day 4 to 2026-11-09; 2026-11-07 and 2026-11-08 are optional buffer days. The local Day 4 implementation was completed ahead of that date.

## Source and label truth

`contracts/source_policy.json` records `external_data_accessed: false`, KKBox as `BLOCKED_PENDING_RIGHTS_REVIEW`, terms as not accepted, and cloud processing as not approved. The snapshot label is a seeded synthetic draw. The event label means no renewal event in the inclusive 30-day interval after a simulated scheduled expiry, subject to source completeness and label maturity. These are useful engineering fixtures, not ground truth from real subscribers. Source rights, eligibility, and the business label definition remain unresolved.

## Re-run evidence

- Ruff check passed; Ruff format check reported 17 files already formatted.
- Pytest: 81 passed, with one existing Starlette/httpx deprecation warning.
- Snapshot and event CLI pipelines both completed for 650 generated customers on separate temporary roots; both selected Logistic Regression by validation AP for those runs.
- Staged event intake generated 69,748 synthetic event revisions. Repeating intake returned the same source release; repeating `run-events` returned the same model version and 650 score rows with 650 distinct customer keys.
- In-process API checks returned 200 for health, readiness, overview and two disjoint risk pages. The responses were marked synthetic and `not_real_world_performance=true`. `/api/v1/model-status` returned 404; it belongs to the next API/dashboard integration slice, not the Day 1–4 local model gate.
- Repository hygiene passed before this report with 61 tracked paths. The original Execution Kit is absent from Git; the pre-existing untracked `apps/` directory was preserved.
- Local `pip-audit` could not reach `pypi.org` because DNS/network access is restricted in this environment. The current PR #15 GitHub Actions run completed the hash-locked dependency audit successfully.
- A loopback Uvicorn bind was denied by the local sandbox. The in-process API checks above passed, and PR #15 CI separately passed its HTTP API check and container E2E.

## PR and integration state

As of this audit, PRs #4, #8, #9, #11, #13 and #15 are open, not merged, and individually reported mergeable. Their latest GitHub Actions runs succeeded: #41618897079, #41653498930, #41655491192, #41667113052, #41793785535 and #41860169916 respectively. Passing branch checks do not merge the stacked changes.

PR #9 is the four-view Next.js analyst workspace (overview, risk, cohorts, and data/model lineage) with a successful browser E2E run. Its data/model view and local run history do not show GCP infrastructure telemetry. A trial integration with the current LightGBM branch found conflicts in shared API, pipeline, storage and documentation files; the full stack still needs an ordered rebase/merge review. The risk filters and pagination are also not reflected in the URL, so refresh and shared links lose that state.

## Next planned work

Continue with the Day 5 API integration locally: reconcile the workspace API contract, including model status and run history, with the selected-model manifest and publication behavior. Resolve and retest the PR stack before presenting the Next.js workspace as the active system UI. Keep cloud deployment and real-source processing gated until rights, account, budget, region and IAM are approved.
