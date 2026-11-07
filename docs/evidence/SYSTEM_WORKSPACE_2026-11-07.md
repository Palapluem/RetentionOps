# Integrated local System dashboard evidence

Run date: 2026-11-07 (Asia/Bangkok)
Implementation: `c55f783` on `feat/rop-013-system-workspace-integration`
Tracking: [Integrate the selected-model API and local system dashboard](https://github.com/Palapluem/RetentionOps/issues/16)
Scope: generated synthetic sources and local serving only.

## Delivered behavior

The web entry route `/` (also `/system`) shows the local pipeline, publication readiness,
source/label truth, selected model, artifact checksum and recorded attempts. Expand Source &
artifact evidence for the actual source/event release IDs and dataset/model hashes.
`/overview`, `/risk`, `/cohorts` and `/status` provide the retention analyst views. Their
metrics and model-pinned details support both Logistic Regression and selected LightGBM.
Risk search, band, renewal setting and page are encoded in the URL, including browser history
and stale-response protection.

`/api/v1/system-status` reads state without creating a database. It remains available when
there is no publication or the publication cannot be verified. Model checksum verification
does not deserialize the artifact. A damaged model file is visible independently of already
materialized scores. Source generation and intake attempts are recorded separately; source
completion follows file generation/validation, while model-run success commits with immutable
features, immutable scores and the active pointer in one SQLite transaction.

## Verification

| Check | Observed result |
|---|---|
| `bash scripts/local_smoke.sh` with Python 3.11 venv | Ruff check/format, 111 tests, snapshot/event CLI paths and repository hygiene passed |
| Production Chromium suite | 20 passed; includes API-backed values, System error/empty state, URL reload/history/races, pinned details, proxy bounds, keyboard interaction and mobile layout |
| Axe checks | Zero violations on System, Overview, Risk, Cohorts and Data & model |
| Frontend lint/typecheck/build | Passed; Next.js 16.4.4 / React 19.3.1; macOS Node 26 |
| `pip-audit` and `npm audit --audit-level=moderate` | No known vulnerabilities found |
| Exported OpenAPI/TypeScript | Generated from the implemented API; no uncommitted schema drift |
| Native Python Playwright visual check | All five views loaded; no page errors; document width matched 1440px desktop and 390px mobile viewports |
| Clean local container path | Python 3.11.18 / Node 24.22.2; empty startup, first failed intake and subsequent 650-customer publication verified |

Pytest reported one existing Starlette/httpx deprecation warning. These checks establish
local engineering behavior, not real-world predictive performance or cloud readiness.

## Empty startup, first failure and recovery

An isolated Compose project used a fresh named volume and loopback ports 18013/13013.
API/web healthchecks succeeded before any pipeline ran. System reported `empty`; score
readiness returned 503. A deliberately missing input file caused a source-intake command to
exit 1 and record a failed `ValueError` attempt. The actual Chromium page showed this first
failure without a response mock, while API/web containers remained healthy.

The synthetic event pipeline then published 650 scores. `/ready` returned 200, System
reported `ready` with `model_artifact_state=verified`, all workspace sections agreed on the
active release, and the earlier source-intake failure remained in history. The temporary
containers, network and generated volume were removed after verification. CI now exercises
this bootstrap sequence before its normal published-data checks.

- [Container states, run IDs and image identities](system_container_2026-11-07.json)
- [Browser/source/model evidence](system_browser_2026-11-07.json)
- [Desktop System view](system-desktop.png), [mobile System view](system-mobile.png)
- [Actual first-failed intake view](system-first-failure.png)

## Review and evidence boundary

The standards review identified readiness-gated Compose startup; liveness/System healthchecks
now keep the operational UI accessible before a score publication. The spec review identified
missing home-page source/hash identifiers and source-stage history; both are implemented and
covered by the tests and actual bootstrap checks above.

The source contract accepts synthetic records only. Outcome labels are simulated, external
source rights remain unapproved, and no GCP account, billing, IAM, public endpoint or cloud
telemetry was created. The original Execution Kit, generated models/raw sources/databases and
existing generated web files remain outside Git. Human review and ordered integration of the
open PR stack are still required before merging to `main`.
