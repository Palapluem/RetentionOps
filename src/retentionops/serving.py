"""One consistent analytical read transaction for each analyst workspace response."""

import json
import math
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .data import CUTOFFS, FEATURES
from .storage import active_manifest

Probability = Annotated[float, Field(ge=0, le=1)]
Band = Literal["high", "watch", "low"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Overview(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    not_real_world_performance: Literal[True] = True
    model_version: str
    score_cutoff: date
    trained_at: datetime
    customers: Annotated[int, Field(ge=1)]
    average_precision: Probability
    baseline_average_precision: Probability
    roc_auc: Probability
    brier: Probability
    recall_at_10pct: Probability
    log_loss: Annotated[float, Field(ge=0)]
    observed_churn_rate: Probability
    mean_predicted_risk: Probability
    high_risk_customers: int
    review_capacity: int
    limitations: list[str]


class RiskItem(Contract):
    customer_id: Annotated[str, Field(pattern=r"^SYN-[0-9]{5,7}$")]
    as_of_date: date
    churn_probability: Probability
    risk_band: Band
    active_days_30d: int
    payment_failures_90d: int
    tenure_months: int
    monthly_fee: float
    auto_renew: int


class RiskPage(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    model_version: str
    total: int
    limit: int
    offset: int
    items: list[RiskItem]


class Cohort(Contract):
    as_of_date: date
    partition: Literal["train", "validation", "test"]
    eligible: int
    churned: int
    churn_rate: Probability
    mean_active_days: float
    auto_renew_share: Probability


class CohortPage(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    model_version: str
    label_freeze: date
    items: list[Cohort]


class DataQualitySummary(Contract):
    """Aggregate-only source, maturity, reconciliation, and holdout facts."""

    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    source_release_id: str
    model_version: str
    source_kind: Literal["event_derived", "snapshot"]
    score_cutoff: date
    evaluation_freeze: date
    source_complete_through: date | None
    source_coverage_status: Literal["verified", "not_declared"]
    source_rows: int
    source_event_revisions: int | None
    candidate_opportunities: int | None
    eligible_rows: int
    excluded_rows: int | None
    feature_rows: int
    scored_rows: int
    reconciliation_status: Literal["verified"]
    label_maturity_status: Literal["verified"]
    cohorts: list[Cohort]
    test_cohort_rows: int
    test_churned: int
    test_churn_rate: Probability
    test_average_precision: Probability
    baseline_average_precision: Probability
    test_brier: Probability
    recall_at_10pct: Probability


def data_quality(conn, manifest):
    """Reconcile one immutable publication and expose only cohort-level facts."""
    result = overview(conn, manifest)
    cohort_page = cohorts(conn, manifest)
    source = manifest["source"]
    quality = source.get("quality", {})
    events = source.get("events")
    if events:
        source_kind = "event_derived"
        source_rows = events["rows"]
        complete_through = date.fromisoformat(events["complete_through"])
        evaluation_freeze = date.fromisoformat(manifest["evaluation_freeze"])
        latest_label_cutoff = max(item.as_of_date for item in cohort_page.items)
        if (
            complete_through < evaluation_freeze
            or evaluation_freeze < latest_label_cutoff + timedelta(days=30)
        ):
            raise ValueError(
                "Published source does not cover its evaluation freeze and mature labels"
            )
        coverage_status = "verified"
        source_event_revisions = events["rows"]
        candidate_opportunities = quality.get("candidate_opportunities")
        eligible_rows = quality.get("eligible_rows", source["rows"])
        excluded_rows = quality.get("excluded_no_known_subscription", 0)
        if (
            eligible_rows != source["rows"]
            or candidate_opportunities != eligible_rows + excluded_rows
            or quality.get("freeze") != str(evaluation_freeze)
            or quality.get("complete_through") != complete_through.isoformat()
        ):
            raise ValueError("Published source quality counts or temporal lineage do not reconcile")
    else:
        source_kind = "snapshot"
        source_rows = source["rows"]
        complete_through = None
        evaluation_freeze = date.fromisoformat(manifest["evaluation_freeze"])
        coverage_status = "not_declared"
        source_event_revisions = None
        candidate_opportunities = None
        eligible_rows = source["rows"]
        excluded_rows = None

    test_cohort = next((item for item in cohort_page.items if item.partition == "test"), None)
    if test_cohort is None:
        raise ValueError("Published release has no mature test cohort")
    test_metrics = manifest["metrics"]["test"]
    selected_metrics = test_metrics.get("selected_model", test_metrics.get("logistic_regression"))
    if selected_metrics is None:
        raise ValueError("Published release has no selected-model test metrics")
    return DataQualitySummary(
        source_release_id=source["source_release_id"],
        model_version=manifest["model_version"],
        source_kind=source_kind,
        score_cutoff=result.score_cutoff,
        evaluation_freeze=evaluation_freeze,
        source_complete_through=complete_through,
        source_coverage_status=coverage_status,
        source_rows=source_rows,
        source_event_revisions=source_event_revisions,
        candidate_opportunities=candidate_opportunities,
        eligible_rows=eligible_rows,
        excluded_rows=excluded_rows,
        feature_rows=sum(item.eligible for item in cohort_page.items),
        scored_rows=result.customers,
        reconciliation_status="verified",
        label_maturity_status="verified",
        cohorts=cohort_page.items,
        test_cohort_rows=test_cohort.eligible,
        test_churned=test_cohort.churned,
        test_churn_rate=test_cohort.churn_rate,
        test_average_precision=selected_metrics["average_precision"],
        baseline_average_precision=test_metrics["constant_prior"]["average_precision"],
        test_brier=selected_metrics["brier"],
        recall_at_10pct=selected_metrics["recall_at_10pct"],
    )


class RunInfo(Contract):
    run_id: str
    mode: str
    state: Literal["running", "succeeded", "failed"]
    started_at: datetime
    finished_at: datetime | None
    model_version: str | None
    output_rows: int | None
    elapsed_seconds: float | None
    error_type: str | None


class JobPage(Contract):
    publication_present: bool
    items: list[RunInfo]


class ModelStatus(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    model_version: str
    model_family: Literal["logistic_regression", "lightgbm"]
    selected_candidate: str
    selection_metric: str | None
    validation_average_precision: Probability | None
    selected_parameters: dict[str, int | float | str | bool]
    source_release_id: str
    event_release_id: str | None
    feature_origin: str
    dataset_sha256: str
    model_sha256: str
    feature_schema_sha256: str
    trained_at: datetime
    evaluation_freeze: date
    source_complete_through: date | None
    quality: dict[str, int | str]
    features: list[str]
    limitations: list[str]
    runs: list[RunInfo]


class CustomerDetail(Contract):
    customer_id: str
    model_version: str
    as_of_date: date
    churn_probability: Probability
    risk_band: Band
    features: dict[str, float]
    feature_max_event_at: date
    source_max_available_at: date
    source_release_id: str


class Workspace(Contract):
    overview: Overview
    risk: RiskPage
    cohorts: CohortPage
    status: ModelStatus


def risk_band(probability):
    return "high" if probability >= 0.4 else "watch" if probability >= 0.2 else "low"


def validate_score_cutoff(conn, manifest):
    """Reject a release if any persisted score belongs to another cutoff."""
    mismatch = conn.execute(
        "SELECT 1 FROM predictions WHERE model_version=? AND as_of_date<>? LIMIT 1",
        (manifest["model_version"], manifest["score_cutoff"]),
    ).fetchone()
    if mismatch is not None:
        raise ValueError("Score release/cutoff mismatch")


def overview(conn, manifest):
    validate_score_cutoff(conn, manifest)
    metrics = manifest["metrics"]["test"]
    values = (
        metrics["selected_model"] if "selected_model" in metrics else metrics["logistic_regression"]
    )
    aggregate = conn.execute(
        "SELECT COUNT(*), AVG(churn_probability), SUM(churn_probability >= 0.4) "
        "FROM predictions JOIN feature_snapshots USING(model_version,customer_id,as_of_date) "
        "WHERE model_version=? AND as_of_date=?",
        (manifest["model_version"], manifest["score_cutoff"]),
    ).fetchone()
    if aggregate[0] != values["rows"]:
        raise ValueError("Publication reconciliation failed")
    return Overview(
        model_version=manifest["model_version"],
        score_cutoff=manifest["score_cutoff"],
        trained_at=manifest["trained_at"],
        customers=values["rows"],
        baseline_average_precision=metrics["constant_prior"]["average_precision"],
        observed_churn_rate=values["positive_rate"],
        mean_predicted_risk=aggregate[1],
        high_risk_customers=aggregate[2],
        review_capacity=math.ceil(values["rows"] * 0.1),
        limitations=manifest["limitations"],
        **{
            key: values[key]
            for key in ("average_precision", "roc_auc", "brier", "recall_at_10pct", "log_loss")
        },
    )


def risk(conn, manifest, limit=20, offset=0, search="", band="all", auto_renew=None):
    validate_score_cutoff(conn, manifest)
    clauses = ["p.model_version=?", "p.as_of_date=?"]
    params = [manifest["model_version"], manifest["score_cutoff"]]
    if search:
        clauses.append("p.customer_id LIKE ?")
        params.append(f"%{search}%")
    if band == "high":
        clauses.append("p.churn_probability >= 0.4")
    elif band == "watch":
        clauses.append("p.churn_probability >= 0.2 AND p.churn_probability < 0.4")
    elif band == "low":
        clauses.append("p.churn_probability < 0.2")
    if auto_renew is not None:
        clauses.append("json_extract(f.snapshot,'$.auto_renew')=?")
        params.append(auto_renew)
    table = (
        "predictions p JOIN feature_snapshots f ON p.model_version=f.model_version "
        "AND p.customer_id=f.customer_id AND p.as_of_date=f.as_of_date"
    )
    where = " AND ".join(clauses)
    count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT p.*,f.snapshot FROM {table} WHERE {where} "
        "ORDER BY p.churn_probability DESC,p.customer_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = []
    for row in rows:
        snapshot = json.loads(row["snapshot"])
        items.append(
            RiskItem(
                customer_id=row["customer_id"],
                as_of_date=row["as_of_date"],
                churn_probability=row["churn_probability"],
                risk_band=risk_band(row["churn_probability"]),
                **{feature: snapshot[feature] for feature in FEATURES},
            )
        )
    return RiskPage(
        model_version=manifest["model_version"],
        total=count,
        limit=limit,
        offset=offset,
        items=items,
    )


def cohorts(conn, manifest):
    rows = conn.execute(
        "SELECT as_of_date, COUNT(*) AS eligible, SUM(json_extract(snapshot,'$.churn_30d')) "
        "AS churned, AVG(json_extract(snapshot,'$.active_days_30d')) AS activity, "
        "AVG(json_extract(snapshot,'$.auto_renew')) AS auto_renew FROM feature_snapshots "
        "WHERE model_version=? GROUP BY as_of_date ORDER BY as_of_date",
        (manifest["model_version"],),
    ).fetchall()
    items = [
        Cohort(
            as_of_date=r["as_of_date"],
            eligible=r["eligible"],
            churned=r["churned"],
            churn_rate=r["churned"] / r["eligible"],
            mean_active_days=r["activity"],
            auto_renew_share=r["auto_renew"],
            partition="test"
            if r["as_of_date"] == str(CUTOFFS[3])
            else "validation"
            if r["as_of_date"] == str(CUTOFFS[2])
            else "train",
        )
        for r in rows
    ]
    if sum(r.eligible for r in items) != manifest["source"]["rows"]:
        raise ValueError("Feature/source reconciliation failed")
    return CohortPage(
        model_version=manifest["model_version"],
        label_freeze=manifest["evaluation_freeze"],
        items=items,
    )


def model_status(conn, manifest):
    runs = conn.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 10").fetchall()
    events = manifest["source"].get("events", {})
    selection = manifest.get("selection", {})
    candidate = selection.get("selected_candidate", "logistic_regression")
    selected_result = next(
        (row for row in selection.get("candidates", []) if row["candidate"] == candidate),
        {},
    )
    return ModelStatus(
        model_version=manifest["model_version"],
        model_family=selection.get("selected_model_family", "logistic_regression"),
        selected_candidate=candidate,
        selection_metric=selection.get("metric"),
        validation_average_precision=selected_result.get("average_precision"),
        selected_parameters=selection.get("selected_parameters", {}),
        source_release_id=manifest["source"]["source_release_id"],
        event_release_id=events.get("source_release_id"),
        feature_origin=manifest["feature_origin"],
        dataset_sha256=manifest["identity"]["dataset_sha256"],
        model_sha256=manifest["model_sha256"],
        feature_schema_sha256=manifest["identity"]["feature_schema_sha256"],
        trained_at=manifest["trained_at"],
        evaluation_freeze=manifest["evaluation_freeze"],
        source_complete_through=events.get("complete_through"),
        quality=manifest["source"].get("quality", {}),
        features=manifest["features"],
        limitations=manifest["limitations"],
        runs=[RunInfo(**dict(r)) for r in runs],
    )


def jobs(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    runs = (
        conn.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 10").fetchall()
        if "pipeline_runs" in tables
        else []
    )
    publication = (
        bool(conn.execute("SELECT 1 FROM active_release WHERE slot=1").fetchone())
        if "active_release" in tables
        else False
    )
    return JobPage(publication_present=publication, items=[RunInfo(**dict(row)) for row in runs])


def customer(conn, customer_id, version=None):
    manifest = active_manifest(conn)
    if version and version != manifest["model_version"]:
        prior = conn.execute(
            "SELECT manifest FROM releases WHERE model_version=?", (version,)
        ).fetchone()
        if prior is None:
            raise HTTPException(404, "Model release not found")
        manifest = json.loads(prior[0])
    validate_score_cutoff(conn, manifest)
    row = conn.execute(
        "SELECT p.*,f.snapshot FROM predictions p JOIN feature_snapshots f "
        "ON p.model_version=f.model_version AND p.customer_id=f.customer_id "
        "AND p.as_of_date=f.as_of_date WHERE p.model_version=? AND p.customer_id=? "
        "AND p.as_of_date=?",
        (manifest["model_version"], customer_id, manifest["score_cutoff"]),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Customer not in this scored cohort")
    snapshot = json.loads(row["snapshot"])
    return CustomerDetail(
        customer_id=customer_id,
        model_version=manifest["model_version"],
        as_of_date=row["as_of_date"],
        churn_probability=row["churn_probability"],
        risk_band=risk_band(row["churn_probability"]),
        features={f: snapshot[f] for f in FEATURES},
        feature_max_event_at=snapshot["feature_max_event_at"],
        source_max_available_at=snapshot["source_max_available_at"],
        source_release_id=manifest["source"]["source_release_id"],
    )


def workspace(conn, **filters):
    manifest = active_manifest(conn)
    return Workspace(
        overview=overview(conn, manifest),
        risk=risk(conn, manifest, **filters),
        cohorts=cohorts(conn, manifest),
        status=model_status(conn, manifest),
    )
