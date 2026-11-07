# RetentionOps

Customer churn intelligence with traceable events, point-in-time features, temporal model
selection and a Next.js analyst workspace. **Local synthetic implementation under development.
GCP deployment, KKBox access, production authentication and v0.1.0 release gates remain open.**

```text
Synthetic JSONL → staged validation → immutable source release
  → known-at-cutoff revisions → point-in-time CSV / typed Parquet features
  → train-only Logistic Regression / bounded LightGBM candidates
  → validation-only selection → frozen test evaluation + constant-prior reference
  → immutable selected model → atomic features / scores / successful run publication
  → typed FastAPI workspace → same-origin Next.js proxy → analyst workspace
```

The product opens on the System dashboard, with publication readiness, model-artifact
checksum state, source/label provenance and actual pipeline attempts. It shows local SQLite
serving, cloud as not connected and authentication as not configured. Expand Source & artifact
evidence for source/event release IDs and dataset/model checksums. Retention views expose
the selected model's metrics, family/configuration, historical scores and mature cohort
denominators. Risk filters and pagination survive refresh and shared links through the URL.

| Web route | View |
|---|---|
| `/` or `/system` | System dashboard |
| `/overview` | Retention Overview |
| `/risk` | Risk explorer and model-pinned customer details |
| `/cohorts` | Cohort analytics |
| `/status` | Data & model lineage and selection details |

All sources and outcomes remain generated synthetic data. Approved real-source access and
a business ground-truth definition are still open gates.

## Run with Docker

```bash
docker compose -p retentionops-day1 up --build --wait api web
docker compose -p retentionops-day1 run --rm pipeline
```

Open the product at <http://127.0.0.1:3000/> and API reference at
<http://127.0.0.1:8000/docs>. API and web ports bind to loopback; the API volume is read-only.
The named project keeps its generated demo state in a local volume.
`docker compose -p retentionops-day1 down` stops the containers and preserves demo data.
API/web healthchecks allow startup on a fresh volume, where System shows an empty publication.
Run the pipeline and refresh to inspect the published release. `/ready` remains the separate
score-readiness check and returns 503 until a valid release exists.

## Receive and replay a source in separate stages

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
Generation and intake appear as separate source-stage attempts; successful source stages
do not activate a model. Their Output rows count event revisions, while model-run rows count
scored customers. See [operation boundaries](docs/OPERATIONS.md).

## Run manually

Python 3.11 and Node.js 24+ are the supported baselines (macOS Node 26 and container/CI
Node 24 are checked). Choose an available port if the Compose environment is running.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
retentionops events --customers 650
python -m uvicorn retentionops.api:app --host 127.0.0.1 --port 8000
```

In a second terminal, activate the same venv and start the web app:

```bash
source .venv/bin/activate
cd apps/web
npm ci
npm run build
npm run start
```

Open <http://127.0.0.1:3000/> for the Next.js workspace. The API root at port 8000 retains
the earlier smoke HTML. The server-only `RETENTIONOPS_API_URL` defaults to
`http://127.0.0.1:8000`; no backend credentials are sent to the browser.
`RETENTIONOPS_ROOT` selects the API's data root. Training is an explicit CLI step and never
runs when an API or UI request starts.
`retentionops all` retains the legacy simulated-snapshot smoke path; `events` derives
features from raw simulated subscription/activity/payment/renewal events. Default cutoffs
and evaluation freeze (2026-11-03) are fixed for reproducibility. Run one writer per root.

## Verify

```bash
source .venv/bin/activate
bash scripts/local_smoke.sh
python scripts/export_contracts.py
python -m pip_audit -r requirements.lock --require-hashes --disable-pip
npm --prefix apps/web ci
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web audit --audit-level=moderate
npm --prefix apps/web run build
cd apps/web
npx playwright install chromium
npm run test:e2e
```

Browser tests launch a production web server and API against generated customer fixtures.
Include System state, API-backed values, URL filters/pagination, pinned details,
error/retry, loading, proxy bounds, desktop/mobile accessibility and keyboard scrolling in
verification, and record observed results in `docs/evidence/`. CI includes the complete
Compose web → API → published event-data path without cloud credentials. Its container job
is configured to check empty startup and failed-intake history with `/ready` at 503 before
running a successful pipeline and requiring `/ready` at 200.
OpenAPI/TypeScript schemas are generated and checked for drift; unsupported schema
constructs fail generation. Biome supplies frontend lint/format; Ruff and Pytest cover Python.

## Project evidence and guides

- [Event and renewal contract](docs/EVENT_CONTRACT.md), [analyst UX](docs/ANALYST_UX.md)
- [Product scope](docs/PRD.md), [architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md)
- [Thai learning log](docs/LEARNING_LOG_TH.md), [operations](docs/OPERATIONS.md)
- [Cloud onboarding and concrete resource plan](docs/CLOUD_ONBOARDING_TH.md)
- [Wayfinder map](https://github.com/Palapluem/RetentionOps/issues/5), [backlog](docs/BACKLOG.md)
- [Day 1 evidence](docs/evidence/DAY1_2026-11-03.md), [event-run evidence](docs/evidence/events_run.json)
- [ML evaluation protocol](docs/ML_EVALUATION.md), [synthetic model card](docs/MODEL_CARD.md)
- [LightGBM candidate evidence](docs/evidence/ML_LIGHTGBM_2026-11-04.md) and [training/publication seam evidence](docs/evidence/ML_TEST_SEAMS_2026-11-04.md)
- [Source-intake evidence](docs/evidence/source_intake_2026-11-03.json), [Day 1–4 re-audit](docs/evidence/DAYS1_4_REAUDIT_2026-11-07.md)
- [Testing](docs/TESTING.md), [risks](docs/RISK_REGISTER.md), [release gates](docs/RELEASE_AUDIT.md)

The owner has not created a GCP account. No cloud resources, billing, IAM or public
exposure were changed. SQLite serving and private service identity must be adapted and
tested before cloud deployment. Real-data access needs a verified rights
and label review. The original Execution Kit, raw data, model binaries, databases and secrets
are excluded from Git; Docker build contexts exclude the kit and generated data.
