# Specification review — 2026-11-03

## Scope

The code-review skill's Spec axis reviewed the continuation from foundation commit
`6ce3335999fd34300f6d5b65b675d1b595409d3e` through analyst workspace commit `ee8d05a`, then
independently checked both findings against the event hardening in commit `d9072c2` and the
current analyst workspace changes. The reviewer did not edit source files.

## Finding 1 — late renewal corrections and cohort embargo

A correction that removes a prior renewal from the qualifying window could change the churn
label without advancing its availability. The source now carries availability from the
latest freeze-visible revision of every logical renewal that qualified at any point by the
freeze. Tests cover an occurrence moved outside the window, a changed expiry, a tombstone,
and a full temporal split that rejects an embargo violation. Independent review confirmed
the prior P1 is fixed. This correction is in event PR #8.

## Finding 2 — first failed run without a publication

Previously the analyst workspace could not read run history until a successful publication
existed, hiding the first failed pipeline attempt. `/api/v1/jobs` now reads job attempts
independently of an active release; the same-origin proxy exposes that bounded read. The UI
loads it after the workspace request fails and reports whether a publication exists. A real
Python integration test records an initial `ValueError` failure while `/ready` stays 503 and
the jobs endpoint returns HTTP 200 with the failed attempt. A production Chromium test checks
the no-publication error and visible failed attempt. Independent review confirmed both the
API and UI fix.

The follow-up reviewer found no additional Spec findings or scope expansion. Final local
validation passed 79 Python tests and 12 production-browser tests, including the new failure
state test.

## Specification-axis summary

The renewal maturity and initial-run visibility findings are fixed; all specified analyst
views remain synthetic, lineage-backed and bounded, with cloud provisioning outside scope.
