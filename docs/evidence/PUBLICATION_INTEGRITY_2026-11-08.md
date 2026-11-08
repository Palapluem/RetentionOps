# Local publication integrity and recovery — 2026-11-08

Scope: synthetic data, local filesystem and SQLite only, on the ROP-013 integration stack.
This is not a cloud, real-customer, or production release assessment.

Independent regression fixtures reproduced unsafe source-output overwrites and incomplete
coverage of the evaluation freeze. Generation now stages output beside its destination and
publishes without replacement; a matching regular file can be replayed, while conflicting
files, symlinks and managed release paths fail. The source completeness watermark must
cover the evaluation freeze, including any corrections known at that date. Score-serving
reads verify that the entire release matches its manifest cutoff and filter by that cutoff.
Corrupt active releases fail closed; a corrupt pinned historical release does not invalidate
an otherwise sound active release.

The recovery integration fixture publishes event release A, publishes B, injects an invalid
source run and confirms B remains active, then replays A on the same implementation and
checks readiness, system status, artifact checksum, risk, customer features, cohorts, run
history and unchanged persisted scores/features for both releases. This is a local replay
drill, not a cloud failover or cross-version rollback test.

Verification performed in a temporary copy with isolated generated data: Ruff check and
format, 134 Python tests, snapshot and event CLI smoke, and repository hygiene passed.
Python dependency audit and npm audit found no known vulnerabilities. Frontend lint,
typecheck and production build passed, as did 20 Chromium E2E tests. The existing
Starlette/httpx deprecation warning remains. CI results are recorded in the PR.
The initial temporary web build using a symlink to external dependencies failed because
Turbopack excludes files outside its workspace; a fresh local dependency install was used
for the subsequent verification.

Source rights and real ground truth remain unresolved. Process termination may leave a run
marked running; automatic heartbeat/reconciliation is not implemented. The Execution Kit,
generated data and model/database artifacts remain outside tracked files.
