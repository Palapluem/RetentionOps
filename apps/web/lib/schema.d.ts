// Generated from FastAPI OpenAPI by scripts/export_contracts.py; do not edit.
// Schema types only; unsupported schema constructs fail generation.
export interface components { schemas: {
"Cohort": { "as_of_date": string; "partition": "train" | "validation" | "test"; "eligible": number; "churned": number; "churn_rate": number; "mean_active_days": number; "auto_renew_share": number; };
"CohortPage": { "data_mode"?: "SYNTHETIC"; "model_version": string; "label_freeze": string; "items": Array<components["schemas"]["Cohort"]>; };
"CustomerDetail": { "customer_id": string; "model_version": string; "as_of_date": string; "churn_probability": number; "risk_band": "high" | "watch" | "low"; "features": Record<string, number>; "feature_max_event_at": string; "source_max_available_at": string; "source_release_id": string; };
"HTTPValidationError": { "detail"?: Array<components["schemas"]["ValidationError"]>; };
"Health": { "status"?: "ok"; "data_mode"?: "SYNTHETIC"; };
"ModelStatus": { "data_mode"?: "SYNTHETIC"; "model_version": string; "source_release_id": string; "event_release_id": string | null; "feature_origin": string; "dataset_sha256": string; "model_sha256": string; "feature_schema_sha256": string; "trained_at": string; "evaluation_freeze": string; "source_complete_through": string | null; "quality": Record<string, number | string>; "features": Array<string>; "limitations": Array<string>; "runs": Array<components["schemas"]["RunInfo"]>; };
"Overview": { "data_mode"?: "SYNTHETIC"; "not_real_world_performance"?: true; "model_version": string; "score_cutoff": string; "trained_at": string; "customers": number; "average_precision": number; "baseline_average_precision": number; "roc_auc": number; "brier": number; "recall_at_10pct": number; "log_loss": number; "observed_churn_rate": number; "mean_predicted_risk": number; "high_risk_customers": number; "review_capacity": number; "limitations": Array<string>; };
"Ready": { "status"?: "ok"; "data_mode"?: "SYNTHETIC"; "model_version": string; };
"RiskItem": { "customer_id": string; "as_of_date": string; "churn_probability": number; "risk_band": "high" | "watch" | "low"; "active_days_30d": number; "payment_failures_90d": number; "tenure_months": number; "monthly_fee": number; "auto_renew": number; };
"RiskPage": { "data_mode"?: "SYNTHETIC"; "model_version": string; "total": number; "limit": number; "offset": number; "items": Array<components["schemas"]["RiskItem"]>; };
"RunInfo": { "run_id": string; "mode": string; "state": "running" | "succeeded" | "failed"; "started_at": string; "finished_at": string | null; "model_version": string | null; "output_rows": number | null; "elapsed_seconds": number | null; "error_type": string | null; };
"ValidationError": { "loc": Array<string | number>; "msg": string; "type": string; "input"?: unknown; "ctx"?: Record<string, unknown>; };
"Workspace": { "overview": components["schemas"]["Overview"]; "risk": components["schemas"]["RiskPage"]; "cohorts": components["schemas"]["CohortPage"]; "status": components["schemas"]["ModelStatus"]; };
}; }
