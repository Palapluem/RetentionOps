# Deliver an event-backed analyst workspace with reproducible delivery

Canonical map: https://github.com/Palapluem/RetentionOps/issues/5

## Destination

Run synthetic subscription events through point-in-time features, evaluated models and
versioned scores into an analyst workspace, with tested local/container/CI delivery.

## Notes

The owner authorized execution after decisions on 2026-11-03. Local synthetic delivery now
covers event-derived features, evaluated scoring and an analyst workspace. Implementation is
in stacked review: foundation PR #4, event PR #8, analyst workspace PR #9. Preserve the
original local Execution Kit outside Git and Docker contexts.

## Decisions so far

- [Define temporal event, renewal-label, and analyst-serving contracts](https://github.com/Palapluem/RetentionOps/issues/6): resolved discrete-day revision/window/renewal semantics and four analyst journeys; see docs/EVENT_CONTRACT.md.

## Not yet specified

The owner confirms no GCP account exists. KKBox access/terms and a supported prospective
label; account/project/region/budget; deployment identity, final authentication and production
release approval remain open gates. Issue #2, [Verify cloud readiness and review a bounded
GCP resource plan](https://github.com/Palapluem/RetentionOps/issues/2), has a plan and Thai
onboarding guide but requires owner account setup before live readiness can be verified.

## Out of scope

Unapproved cloud creation/IAM/public exposure; restricted raw redistribution; campaign
uplift/ROI claims; Kafka/Kubernetes/Feast; production-ready or release claims without gates.
