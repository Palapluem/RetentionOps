# Publication audit and local interruption handling — 2026-11-08

Two independent reviews examined PR #19 against issue #18 and repository standards. Both
identified that the output path was expanded for validation but not writing. In a temporary
reproduction, a literal `~` path could write into a managed release via a symlinked parent.
The fix uses the expanded path for generation and checksums, resolving only for the managed
directory check so that a final-component symlink is still rejected. A separate review
noted that overview's aggregate should explicitly filter the selected cutoff; the prior
release-wide validation already rejected mismatches, and the query now also has the filter.

Caught `KeyboardInterrupt` and `SystemExit` now record a failure and error type only while the
attempt is still running, then propagate the original exception. Tests exercise interruptions
before and after committing the initial attempt, before publication, inside a SQLite
publication transaction and after a success commit, including source generation. A real
SIGKILL of a test subprocess confirmed that the last
recorded state remains `running` while the previously active synthetic release remains
readable. The UI labels that state as last recorded and says it does not confirm a live
process. No timeout or PID heuristic changes the state automatically. Failure reporting uses
an existing database only; if startup or failure reporting cannot access it, the original
exception is still propagated.

Verification: an isolated local smoke run passed Ruff, 152 Python tests, synthetic snapshot
and event CLI paths, and repository hygiene. A subsequent failure-report path-error case
passed in the 14-test interruption suite. Frontend lint, typecheck, production build and 21
Chromium tests passed in a temporary copy; the running-state browser
fixture is explicitly mocked. GitHub CI results are recorded in the PR. Existing
Starlette/httpx deprecation warning remains.

This evidence is local and synthetic only. It does not establish cloud monitoring, process
recovery after machine failure, source rights or real-customer ground truth. The Execution
Kit and generated data/models/databases stay outside Git.
