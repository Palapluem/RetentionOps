# Active risk register

| Risk | Current evidence/status | Mitigation / next action |
|---|---|---|
| KKBox access/cloud-use rights unknown | Blocked; official rule text not readable in unauthenticated inspection | Manual authenticated terms review; synthetic-only in the meantime |
| Cloud account/project/budget/IAM unknown | gcloud/bq absent at initial inspection | Install tooling when needed, inspect privately, prepare concrete plan before approval |
| Feature/label leakage | Strict snapshot metadata and temporal negative tests implemented | Add event-derived features with independent cutoff/correction fixtures |
| Snapshot realism | Synthetic feature values and labels only | Do not report real-world/KKBox accuracy or prospective production quality |
| Mixed stale model results | Active-release query and transaction boundaries implemented | Test multiple runs and rollback; cloud version needs equivalent transaction semantics |
| Duplicate replay/source correction | Content-addressed raw and versioned model identity implemented | Preserve previous versions; validate correction lineage before cloud ingestion |
| Public exposure/PII | Local loopback demo and fixed synthetic schema | Access-controlled production API; no external raw data/public IDs |
| Cost growth | No cloud resources created | Budget alerts, query bounds, instance/job limits and reviewed cleanup plan |
| Repo governance | Admin permission verified; main initially unprotected | PR/CI workflow first; human review and branch-rule/board follow-up |
| Local scale | In-memory CSV and single writer | Introduce Polars/PyArrow/warehouse jobs at measured need; no throughput claims |
| Interrupted local job | Uncatchable termination can leave the last recorded state as running | Inspect the process before replay; design and test a lease/heartbeat before automated reconciliation |
| Release overclaim | Cloud/UI/real-data gates incomplete | No v0.1.0 tag until release checklist has direct evidence |
