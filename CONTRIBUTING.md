# Contributing

Use a feature branch linked to a scoped issue. Keep commits reviewable and use conventional
commit messages. A PR must describe the trigger, resulting behavior, actual validation,
data/operational impact and limitations. A human reviews and merges; no direct main work.

Install with the README's Python 3.11/hash-locked steps. Run local_smoke.sh, pip-audit and
tracked-file checks before pushing. Cloud changes require a separate reviewed resource
plan and explicit owner approval for billable/IAM/public-exposure actions.

The original Execution Kit is a local reference and must never be staged. Add actual reviewed
implementation to project paths instead. Do not commit generated raw sources, models,
databases, credentials or private cloud inventories.

To intentionally refresh the lock, use a dedicated tooling environment with uv 0.13.7:

```bash
uv pip compile pyproject.toml --extra dev --python-version 3.11 --generate-hashes --output-file requirements.lock
```

Review changed package versions/hashes and rerun checks in a fresh environment. The lock
includes dev/build tools so both clean editable installs and container builds can avoid
unlocked build isolation. Only Python 3.11 is verified; other permitted Python versions need
their own compatibility run. Do not change model parameters to optimize the final holdout.
