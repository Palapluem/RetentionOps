# RetentionOps engineering instructions

Communicate with the owner primarily in Thai. Code, API names and commits use English.
Read README, docs/DECISIONS.md and the relevant contract before changing behavior.

## Scope and evidence

- Current implementation is a synthetic-only local foundation. Do not claim KKBox results,
  event-derived features, cloud deployment, production auth or completed release gates.
- Keep `RetentionOps_Execution_Kit_2026-11-04/` and its archive local and untracked. Treat
  starter files as reference material; integrate only reviewed, relevant content.
- Never commit credentials, .env, private data, generated models, SQLite databases or raw
  sources. Run `python scripts/check_repository.py` before committing/pushing.
- Work on a feature branch, link an issue, run relevant tests, record actual evidence and
  open a PR. Preserve user files and Git history; no force pushes or destructive resets.
- No automatic cloud provisioning, billing, significant IAM changes or public exposure.
  These require explicit owner approval after a concrete plan, budget and cleanup review.
- Use Wayfinder for a requested large planning exercise; the current Day 1 task is execution.

## Contracts

- Snapshot grain is customer × cutoff. Labels and identifiers never enter the feature matrix.
- Source event time ≤ source availability ≤ cutoff. Mature labels only; older-cohort labels
  must be available by the next cohort cutoff. Preprocessing fits on train only.
- Public/local demo accepts generated synthetic identifiers and fixed numeric fields only.
- The snapshot validator checks supplied provenance dates; raw-event feature derivation is
  separate work. Do not describe metadata checks as proof of event-level correctness.
- Model identity includes data, implementation, configuration and dependency versions.
- Publish scores and active-release pointer in one transaction. Failure preserves the prior
  active release; API queries must filter that release and use read-only connections.

## Development

Use Python 3.11. Install requirements.lock with hashes, then install the project with
`pip install --no-deps --no-build-isolation -e .`. See scripts/local_smoke.sh.
Run Ruff check/format, Pytest, synthetic CLI smoke, pip-audit and repository checks.
Tests must verify behavior and failure boundaries. Keep code shared in src/retentionops
until separate jobs/services require a wider monorepo structure. No empty scaffolding.
Update docs/LEARNING_LOG_TH.md and docs/evidence for meaningful checkpoints.
