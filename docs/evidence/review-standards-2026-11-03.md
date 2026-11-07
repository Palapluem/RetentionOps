# Standards review — 2026-11-03

## Scope

The code-review skill's Standards axis reviewed the continuation from foundation commit
`6ce3335999fd34300f6d5b65b675d1b595409d3e` through analyst workspace commit `ee8d05a`, then
independently rechecked the reported finding against the event hardening in commit
`d9072c2` and its regression tests. The reviewer did not edit source files.

## Finding and resolution

The reviewer found one P1 temporal-label defect: when a previously qualifying renewal was
corrected out of the renewal window, its availability date could be lost before calculating
label maturity. A late correction could then enter an earlier training cohort.

`events.py` now retains logical renewal IDs from revisions that qualified by the freeze,
then uses the latest freeze-visible revision to calculate both the outcome and label
availability. This includes revisions that move the occurrence date, change the expiry, or
tombstone the renewal. Independent fixtures assert September 1 label availability; a
multi-customer, four-cohort fixture confirms the August 31 embargo rejects the corrected
label. These changes are included in event PR #8.

Follow-up review confirmed the P1 is fixed and found no remaining severity for that issue or
other actionable Standards findings. Final local validation passed 79 Python tests and the
standalone event PR branch passed 62 tests; the single warning is an upstream
Starlette/httpx deprecation warning.

## Standards-axis summary

The renewal correction leakage is fixed in the event branch; no other actionable Standards
findings remain from this review.
