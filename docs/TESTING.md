# Testing strategy

| Boundary | Evidence required |
|---|---|
| Source generation/intake | Seeded byte determinism; strict JSONL/event contract; identity, hash, revision and watermark checks; idempotent replay; failed intake publishes no release |
| Time | Negative fixtures for future event/availability, immature label, unavailable prior-cohort label |
| Training | Explicit calendar cohorts, both classes, scaler fitted on train, fixed baseline comparison, validation-label changes may change candidate/config while holdout-label changes cannot |
| Artifact/lineage | Model/data/code/config/dependency identity; checksum corruption rejected; serialized model scores reconcile |
| Publication | Row counts, exact score replay idempotence by model/customer/cutoff, conflicting scores for an immutable model rejected, independent versions, failed transaction leaves last good release |
| API | Typed OpenAPI, 503 before publication/corrupt storage, bounds, stable risk sort/pagination, no mixed active version |
| User interface | Browser observes API-backed rows; desktop/mobile; error/retry and empty states; accessibility scan |
| Engineering | Ruff, pinned hashed install, dependency audit, tracked-file hygiene, HTTP smoke, clean checkout |
| Containers | Compose pipeline → shared volume → API readiness; CI records actual result |
| Cloud (planned) | Real job IDs, warehouse reconciliation, auth denial, query budget and rollback evidence |

Run `bash scripts/local_smoke.sh` in the project venv. It is credential-free and generates
synthetic outputs only. `pip-audit` needs network access to its advisory service; a network
failure is not a passed security check. The tracked-file guard detects selected patterns and
forbidden paths; it is not a comprehensive secret/security scanner.

Use tests for behavior and failure boundaries. Do not encode arbitrary target accuracy for
synthetic data. Do not treat metadata validation as an independent raw-event leakage audit.
Use fixed source cohorts for reproducibility and never tune parameters to improve the test
cohort. Test commands and observed timestamps belong in docs/evidence; cloud results remain
unverified until actually executed.
