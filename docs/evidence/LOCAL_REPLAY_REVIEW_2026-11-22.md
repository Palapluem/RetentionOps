# Local replay and dashboard review

Reviewed the initial PR #23 head `957630b` on November 22, 2026, Asia/Bangkok. The drill
ran on macOS arm64 with Python 3.11 and generated synthetic data.

## Staged pipeline drill

Ran `generate-events`, `ingest-events`, and `run-events` using a fresh temporary root and
checked FastAPI responses with TestClient. `/health` returned 200 and `/ready` returned 503
before the first publication. The API read left the empty root without a serving database.

| Release | Input event revisions | Eligible feature rows across cutoffs | Scored test customers |
|---|---:|---:|---:|
| A | 11,271 | 400 | 100 |
| B | 13,595 | 480 | 120 |

Both releases used the 2026-09-30 score cutoff and 2026-11-03 for evaluation freeze and source
completeness. Separate SQLite reads matched the test row and churn counts in the manifest and
System response. Ingesting identical input twice returned the same source manifest, and
replaying A returned its original model manifest and preserved scores. A request to run an
absent source release exited with a recorded `ValueError`. B stayed active and ready. Replaying A then
restored it as active while preserving the stored scores and features of both releases.
The score keys were unique for each model and cutoff.

## Corrections and verification

- Chromium's real click at the documented IPv4 loopback address received 403 before the fix.
  The updated proxy compares the browser Origin with the validated loopback Host. A new
  browser test passes through Next.js to FastAPI with Ollama disabled by the test configuration.
  The cross-origin and non-local Host rejection tests passed.
- A native run exercised Chromium → Next.js on port 3000 → FastAPI → local Ollama with cloud
  mode disabled. `qwen3:4b-instruct` returned two approved observations. The response
  matched the Dashboard's model version, source release, and score cutoff.
- Isolated local smoke passed **172 Python tests**, both synthetic CLI paths, Ruff, and
  repository hygiene. The CLI wrote into the configured temporary root and the SHA-256
  of the checkout's pre-existing serving database stayed the same. The Starlette/httpx
  TestClient deprecation warning remains.
- Web lint, typecheck, Next.js production build, and **26 Playwright tests** passed.
  `pip-audit` and `npm audit` reported zero known vulnerabilities. Docker Compose config
  validation and `git diff --check` passed.

This drill covers replay on one local implementation and dependency set. Cloud recovery,
licensed source rights, and production deployment retain their separate release gates.
