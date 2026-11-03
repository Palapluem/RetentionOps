# Engineering decisions

| Date (Bangkok) | Decision | Reason and trade-off |
|---|---|---|
| 2026-11-03 | Preserve existing GitHub main/history; import by feature branch | Only README tracked upstream; init/fetch safely alongside local kit; no file overwritten |
| 2026-11-03 | Exclude original Execution Kit from Git and Docker | Explicit owner constraint; reviewed content may be rewritten into actual project paths |
| 2026-11-03 | Python 3.11 baseline on macOS arm64 | Installed and compatible; pin dependencies rather than assume other Python versions work |
| 2026-11-03 | Local synthetic snapshots before external data | Works without credentials; cannot prove real subscription label or event-level feature correctness |
| 2026-11-03 | Split June/July, August, September with label embargo | Replaces starter train/test-only protocol; no preprocessing leakage or validation-as-test claim |
| 2026-11-03 | Fixed Logistic Regression and constant-prior baseline | Interpretable and reproducible; LightGBM/MLflow only when comparison workflow is implemented |
| 2026-11-03 | Content-addressed sources and immutable model directories | Replay and audit; code/config/dependency changes create versions; single writer per local root |
| 2026-11-03 | SQLite atomic active-release publication | Small credential-free demo, last good result on failure; unsuitable as the final analytical warehouse |
| 2026-11-03 | Read-only local FastAPI with typed Pydantic contracts | Bounded serving and explicit errors; production auth remains a separate release gate |
| 2026-11-03 | API-backed smoke HTML before Next.js product UI | Verifies the vertical slice early; not a substitute for the planned product frontend |
| 2026-11-03 | Target GCS/BigQuery/Cloud Run/Scheduler with OIDC | Managed batch architecture; no resource creation before account/region/budget/IAM approval |
| 2026-11-03 | Keep shared Python under src until service boundaries exist | Avoid empty monorepo scaffolding; move entrypoints into apps/services when independently operated |


| 2026-11-03 | Latest known contiguous event revisions before right-exclusive windows | Prevent obsolete revisions reappearing after corrections; day-grain synthetic semantics are explicit |
| 2026-11-03 | Atomic features, scores, active pointer and successful job state | Reconcile keys as well as counts; failed attempts are recorded without replacing the prior result |
| 2026-11-03 | One workspace read transaction; model-pinned customer details | Avoid cross-request mixed releases while keeping bounded paginated views |
| 2026-11-03 | Next.js 16 / React 19 / Node 24+ and a server-only fixed proxy | Real analyst workflows without browser backend credentials; cloud service authentication remains a gate |
| 2026-11-03 | Biome plus a small fail-closed OpenAPI schema type exporter | Remove dev-tool dependency chain affected by [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249); 0 known npm advisories after replacement, no unsafe major overrides; supported schema subset is tested |

Revisit a decision when measured evidence changes its assumptions. Record that evidence and
the relevant issue/PR; do not silently expand infrastructure or label semantics.
