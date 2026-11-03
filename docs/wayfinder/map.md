# Deliver an event-backed analyst workspace with reproducible delivery

Canonical map: https://github.com/Palapluem/RetentionOps/issues/5

## Destination

Run synthetic subscription events through point-in-time features, evaluated models and
versioned scores into an analyst workspace, with tested local/container/CI delivery.

## Notes

The owner authorized execution after decisions on 2026-11-03. Use Wayfinder,
codebase-design, find-docs, frontend-design and React/Next.js best practices. Continue safe
local implementation while source rights and paid cloud approval remain external gates.
Stack feature PRs on the reviewed foundation; preserve the original local Execution Kit.

## Decisions so far

- [Define temporal event, renewal-label, and analyst-serving contracts](https://github.com/Palapluem/RetentionOps/issues/6): resolved discrete-day revision/window/renewal semantics and four analyst journeys; see docs/EVENT_CONTRACT.md.

## Not yet specified

The owner confirms no GCP account exists. KKBox access/terms and supported prospective
label; GCP account/project/region/budget;
approved deployment identities, final authentication and production release approval.

## Out of scope

Unapproved cloud creation/IAM/public exposure; restricted raw redistribution; campaign
uplift/ROI claims; Kafka/Kubernetes/Feast; production-ready or release claims without gates.
