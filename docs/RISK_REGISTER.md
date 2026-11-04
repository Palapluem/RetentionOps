# Active risk register

| Risk | Current evidence/status | Mitigation / next action |
|---|---|---|
| KKBox access/cloud-use rights unknown | Blocked; official rule text not readable in unauthenticated inspection | Manual authenticated terms review; synthetic-only in the meantime |
| Cloud account/project/budget/IAM unknown | No GCP account; gcloud/bq absent. Optional adapter has fake-client tests only | Complete issue #2, review resource/budget/cleanup plan and approve before any real GCP execution |
| Feature/label leakage | Strict snapshot metadata and temporal negative tests implemented | Add event-derived features with independent cutoff/correction fixtures |
| Snapshot realism | Synthetic feature values and labels only | Do not report real-world/KKBox accuracy or prospective production quality |
| Mixed stale model results | Active-release query and transaction boundaries implemented | Test multiple runs and rollback; cloud version needs equivalent transaction semantics |
| Duplicate replay/source correction | Local content-addressed releases; cloud code uses generation preconditions and deterministic load IDs | Preserve previous versions; reconcile source rows/hashes and validate correction lineage before cloud ingestion |
| Public exposure/PII | Local loopback demo and fixed synthetic schema | Access-controlled production API; no external raw data/public IDs |
| Cost growth | No cloud resources created; adapter requires explicit GCS upload/query byte caps | Budget alerts, query bounds, instance/job limits and reviewed cleanup plan before use |
| Repo governance | Admin permission verified; main initially unprotected | PR/CI workflow first; human review and branch-rule/board follow-up |
| Local scale | In-memory CSV and single writer | Introduce Polars/PyArrow/warehouse jobs at measured need; no throughput claims |
| Release overclaim | Cloud/UI/real-data gates incomplete | No v0.1.0 tag until release checklist has direct evidence |
