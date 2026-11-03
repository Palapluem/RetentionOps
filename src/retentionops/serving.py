"""One consistent analytical read transaction for each analyst workspace response."""

import json
import math
from datetime import date, datetime
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


def overview(conn, manifest):
    metrics = manifest["metrics"]["test"]
    values = metrics["logistic_regression"]
    aggregate = conn.execute(
        "SELECT COUNT(*), AVG(churn_probability), SUM(churn_probability >= 0.4) "
        "FROM predictions JOIN feature_snapshots USING(model_version,customer_id,as_of_date) "
        "WHERE model_version=?",
        (manifest["model_version"],),
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
    clauses = ["p.model_version=?"]
    params = [manifest["model_version"]]
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
    return ModelStatus(
        model_version=manifest["model_version"],
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
    row = conn.execute(
        "SELECT p.*,f.snapshot FROM predictions p JOIN feature_snapshots f "
        "ON p.model_version=f.model_version AND p.customer_id=f.customer_id "
        "AND p.as_of_date=f.as_of_date WHERE p.model_version=? AND p.customer_id=?",
        (manifest["model_version"], customer_id),
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
