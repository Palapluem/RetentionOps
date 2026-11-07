# Deliver an event-backed analyst workspace with reproducible delivery

Canonical map: https://github.com/Palapluem/RetentionOps/issues/5

## Destination

Receive a versioned synthetic event source, validate and replay it through point-in-time
features, evaluated models and versioned scores into an analyst workspace, with tested
local/container/CI delivery.

## Notes

The owner authorized execution after decisions on 2026-11-03. Continue local implementation
while source rights and paid cloud approval remain external gates. Preserve the original
local Execution Kit outside Git and Docker contexts. The existing stack begins with
[Establish engineering foundation and verified synthetic vertical slice](https://github.com/Palapluem/RetentionOps/pull/4)
and [Derive synthetic features from subscription events with point-in-time tests](https://github.com/Palapluem/RetentionOps/pull/8).
[Build an API-backed Next.js retention analyst workspace](https://github.com/Palapluem/RetentionOps/pull/9)
and [Add replayable local event-source ingestion](https://github.com/Palapluem/RetentionOps/pull/11)
build on the event layer. Review their combined API, pipeline and storage behavior before
retargeting or merging; existing branch checks apply to their current bases. Current
implementation status is recorded in `docs/BACKLOG.md`.

The local intake is synthetic-only; a real-data adapter and live GCS/BigQuery execution
require separate rights and cloud readiness decisions.

## Decisions so far

[Define temporal event, renewal-label, and analyst-serving contracts](https://github.com/Palapluem/RetentionOps/issues/6)
resolved the day-grain event/revision rules, label maturity and analyst views; the source
contract and implementation limits are recorded in `docs/EVENT_CONTRACT.md`.

## Not yet specified

The owner confirms no GCP account exists. KKBox access/terms and a supported prospective
label; account/project/region/budget; deployment identity, final authentication and production
release approval remain open gates. [Verify cloud readiness and review a bounded GCP
resource plan](https://github.com/Palapluem/RetentionOps/issues/2) has a resource plan and Thai
onboarding guide, with live readiness pending account setup.

## Out of scope

Unapproved cloud creation/IAM/public exposure; restricted raw redistribution; campaign
uplift/ROI claims; Kafka/Kubernetes/Feast; production-ready or release claims without gates.
