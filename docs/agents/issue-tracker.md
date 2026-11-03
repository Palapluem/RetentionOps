# Issue tracker

GitHub repository: Palapluem/RetentionOps. Canonical Wayfinder map:
[Deliver an event-backed analyst workspace with reproducible delivery](https://github.com/Palapluem/RetentionOps/issues/5).

Prefer the connected GitHub tools for issue/PR reads, creation, metadata and CI checks.
The GitHub CLI is the fallback for labels, native sub-issues/dependencies and issue resolution
notes not covered by the connector. Never print tokens or private account/project metadata.

Review base for the full continuation is foundation commit
`6ce3335999fd34300f6d5b65b675d1b595409d3e`. Spec sources are docs/EVENT_CONTRACT.md,
docs/ANALYST_UX.md and docs/PRD.md. PR #8's event branch now contains the temporal maturity
and feature-domain corrections. PR #9's analyst branch is stacked on that updated event head.
After merging each predecessor to `main`, retarget the next PR base to `main` before merging
so the review diff stays isolated. Human review/merge remains separate from implementation
and verified local evidence.
