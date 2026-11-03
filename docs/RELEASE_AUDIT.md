# v0.1.0 release gates

Target: 2026-11-13, Asia/Bangkok. Current status: **not a release**. Mark a gate only with
direct evidence; local synthetic evidence does not satisfy a cloud/real-data gate.

- [ ] Approved source rights, data classification, eligible population and label definition.
- [ ] Private cloud resources, regional alignment, budget alerts and least-privilege IAM verified.
- [ ] GCS/BigQuery ingestion, lineage, schema checks and retry reconciliation verified.
- [ ] Raw-event point-in-time features, late corrections and mature cohort labels verified.
- [ ] Fixed time-aware training/validation/test, baseline comparison and model card complete.
- [ ] Versioned artifacts and reproducible model/data/environment hashes verified.
- [ ] Idempotent cloud scoring and source/target count reconciliation verified.
- [ ] Authenticated API, bounded queries, public-data boundary and denial tests pass.
- [ ] Next.js dashboard shows real API values, cohort denominators, source and freshness.
- [ ] PR CI and human code review pass; main governance limitations documented.
- [ ] Dependency/secret/privacy review and actual cost exposure reviewed.
- [ ] Recovery/replay/rollback and monitoring/schedule behavior tested.
- [ ] Clean-checkout demo and cloud run IDs/revisions captured.
- [ ] Known limits and measured performance boundaries documented.

Day 1 evidence: [local engineering report](evidence/DAY1_2026-11-03.md). Synthetic-only
results are suitable for development demonstrations, not proof of real churn performance,
production readiness or campaign value. If cloud/source dependencies remain incomplete,
describe the result as a local preview and list those gates; do not create a release tag.
