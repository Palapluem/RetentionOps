# Deliver an event-backed analyst workspace with reproducible delivery

Canonical map: https://github.com/Palapluem/RetentionOps/issues/5

## Destination

Receive a versioned synthetic event source, validate and replay it through point-in-time
features, evaluated models and versioned scores into an analyst workspace, with tested
local/container/CI delivery.

## Notes

The owner authorized execution after decisions on 2026-11-03. Use Wayfinder,
codebase-design, find-docs, frontend-design and React/Next.js best practices. Continue safe
local implementation while source rights and paid cloud approval remain external gates.
Stack feature PRs on the reviewed foundation; preserve the original local Execution Kit.
The local source-intake extension is tracked as
[Add replayable local event-source ingestion](https://github.com/Palapluem/RetentionOps/issues/10)
and is under review in [PR #11](https://github.com/Palapluem/RetentionOps/pull/11).
It is synthetic-only; a real-data adapter and GCS/BigQuery execution require separate rights
and cloud readiness decisions.

## Decisions so far

[Define temporal event, renewal-label, and analyst-serving contracts](https://github.com/Palapluem/RetentionOps/issues/6)
resolved the day-grain event/revision rules, label maturity and analyst views; the source
contract and implementation limits are recorded in `docs/EVENT_CONTRACT.md`.

## Not yet specified

KKBox access/terms and supported prospective label; GCP account/project/region/budget;
approved deployment identities, final authentication and production release approval.

## Out of scope

Unapproved cloud creation/IAM/public exposure; restricted raw redistribution; campaign
uplift/ROI claims; Kafka/Kubernetes/Feast; production-ready or release claims without gates.
