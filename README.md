# RetentionOps

Customer churn intelligence with traceable events, point-in-time features, temporal model
validation and a Next.js analyst workspace. **Implemented and tested locally with synthetic
subscription events. GCP deployment, KKBox access, production authentication and v0.1.0
release gates remain open.**

```text
Synthetic events → immutable source → known-at-cutoff revisions → CSV / typed Parquet
  → temporal model evaluation → atomic features / scores / successful run publication
  → typed FastAPI workspace → same-origin Next.js proxy → analyst decisions
```

The workspace provides Overview, Risk explorer, Cohort analytics and Data & model views.
Filter by subscriber/risk/auto-renew, paginate, inspect actual customer features, compare
mature cohort denominators, and trace model/source identifiers and actual job attempts.
These are synthetic historical scores, not live customer performance or campaign uplift.

## Run with Docker

```bash
docker compose -p retentionops-day1 run --rm --build pipeline
docker compose -p retentionops-day1 up --build --wait api web
```

Open the product at <http://127.0.0.1:3000/> and API reference at
<http://127.0.0.1:8000/docs>. API and web ports bind to loopback; the API volume is read-only.
The named project retains the local verification volume from the first session.
`docker compose -p retentionops-day1 down` stops the containers and preserves demo data.

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

The server-only `RETENTIONOPS_API_URL` defaults to `http://127.0.0.1:8000`; no backend
credentials are sent to the browser. `RETENTIONOPS_ROOT` selects the API's data root.
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

Browser tests launch a real production web server and API against a generated 150-customer
fixture. They cover API-backed values, filters/pagination, pinned details, error/retry,
loading, proxy bounds, desktop/mobile accessibility and keyboard scrolling. CI also tests
the complete Compose web → API → published event-data path without cloud credentials.
OpenAPI/TypeScript schemas are generated and checked for drift; unsupported schema
constructs fail generation. Biome supplies frontend lint/format; Ruff and Pytest cover Python.

## Project evidence and guides

- [Event and renewal contract](docs/EVENT_CONTRACT.md), [analyst UX](docs/ANALYST_UX.md)
- [Product scope](docs/PRD.md), [architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md)
- [Thai learning log](docs/LEARNING_LOG_TH.md), [operations](docs/OPERATIONS.md)
- [Cloud onboarding and concrete resource plan](docs/CLOUD_ONBOARDING_TH.md)
- [Wayfinder map](https://github.com/Palapluem/RetentionOps/issues/5), [backlog](docs/BACKLOG.md)
- [Day 1 evidence](docs/evidence/DAY1_2026-11-03.md), [event-run evidence](docs/evidence/events_run.json)
- [Testing](docs/TESTING.md), [risks](docs/RISK_REGISTER.md), [release gates](docs/RELEASE_AUDIT.md)

The owner has not created a GCP account. No cloud resources, billing, IAM or public
exposure were changed. The current SQLite serving and private Cloud Run identity integration
must be adapted and tested before cloud deployment. Real-data access needs a verified rights
and label review. The original Execution Kit, raw data, model binaries, databases and secrets
are excluded from Git; Docker build contexts exclude the kit and generated data.
