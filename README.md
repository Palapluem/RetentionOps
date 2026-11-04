# RetentionOps

Customer churn intelligence with traceable data, temporal model evaluation and bounded
read-only risk serving. **Current status: verified-local scope under development; synthetic
data only. No GCP deployment, KKBox training, production authentication or v0.1.0 release.**

Day 1: [implementation PR](https://github.com/Palapluem/RetentionOps/pull/4) with passing
[implementation CI](https://github.com/Palapluem/RetentionOps/actions/runs/41618586106),
local/clean-checkout evidence and human review pending.

The first vertical slice runs without cloud credentials:

```text
Synthetic CSV → strict data contract → immutable source release
  → train-only Logistic Regression / LightGBM candidates → validation-only selection
  → frozen test evaluation + constant-prior comparison
  → immutable model + manifest → transactional SQLite scores → FastAPI → smoke dashboard
```

The event-backed path is now implemented and tested locally:

```text
Synthetic subscription/activity/payment/renewal events → latest known revisions
  → point-in-time features + mature renewal labels → immutable CSV/typed Parquet
  → the same evaluated model and atomic serving publication
```

Run `retentionops events --customers 650` for the one-command synthetic demo; `retentionops all`
preserves the earlier snapshot smoke path. To exercise the first pipeline as separate,
replayable stages:

```bash
retentionops generate-events --output data/incoming/demo-events.jsonl --customers 650
retentionops ingest-events --input data/incoming/demo-events.jsonl \
  --source-id demo-feed --complete-through 2026-11-03
# Copy source_release_id from the intake report:
retentionops run-events --source-release 'PASTE_SOURCE_RELEASE_ID'
```

Intake validates the staged bytes and atomically publishes a content-addressed release under
`data/events/`. Replay verifies its checksum and quality manifest before features, training,
temporal evaluation and publication. Identical input is idempotent; failed intake publishes no
release. The adapter accepts the synthetic event contract only, not KKBox or real customer
data. See [event and renewal semantics](docs/EVENT_CONTRACT.md). These are simulated
subscription opportunities, not a real-world accuracy result.

## Run locally

Python 3.11 is the supported baseline. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
bash scripts/local_smoke.sh
python -m uvicorn retentionops.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> or <http://127.0.0.1:8000/docs>. The dashboard displays actual
locally published synthetic predictions. Training is an explicit CLI step, never an API
startup side effect. Docker is optional; it is not needed for the Python workflow.

```bash
retentionops all --customers 650
retentionops all --root /tmp/retentionops-demo --customers 200 --as-of 2026-11-03
RETENTIONOPS_ROOT=/tmp/retentionops-demo python -m uvicorn retentionops.api:app --host 127.0.0.1
curl --fail http://127.0.0.1:8000/ready
curl --fail 'http://127.0.0.1:8000/api/v1/risk?limit=5&offset=0'
```

The default freeze date is fixed at 2026-11-03 for reproducibility. Generated files stay in
ignored `data/` and `artifacts/`. Run one writer at a time for a given root. The demo binds
to loopback and has no authentication; cloud exposure is a separate gated task.

## Verify

```bash
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -q
python -m pip_audit -r requirements.lock --require-hashes --disable-pip
python scripts/check_repository.py
python scripts/cloud_preflight.py
```

Cloud preflight is read-only. Missing CLI/account/project checks mean cloud readiness is
unverified, not that the project has been deployed. See [observed evidence](docs/evidence/DAY1_2026-11-03.md).

## Container workflow

```bash
docker compose run --rm pipeline
docker compose up api
```

The services share a local named volume; API readiness follows pipeline publication.
Host port 8000 binds to `127.0.0.1`. See [operations](docs/OPERATIONS.md) for recovery and
volume lifecycle. A Dockerfile is not deployment evidence.

## Understand and extend

- [Product scope and implementation status](docs/PRD.md)
- [Implemented and target architecture](docs/ARCHITECTURE.md)
- [Data, label and license contracts](docs/DATA_CONTRACT.md)
- [ML evaluation protocol](docs/ML_EVALUATION.md)
- [Synthetic model card](docs/MODEL_CARD.md) and [ROP-011 run evidence](docs/evidence/ML_LIGHTGBM_2026-11-04.md)
- [Decisions and alternatives](docs/DECISIONS.md)
- [Thai learning log](docs/LEARNING_LOG_TH.md)
- [Testing strategy](docs/TESTING.md), [risk register](docs/RISK_REGISTER.md)
- [Release gates](docs/RELEASE_AUDIT.md), [backlog](docs/BACKLOG.md)
- [Local source-intake and replay evidence](docs/evidence/source_intake_2026-11-03.json)

The original Execution Kit is intentionally excluded from Git and Docker context. This repo
contains reviewed implementation and project documentation, not the kit directory.
