"""Typed read-only API for local synthetic results. Bind to loopback only."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .storage import active_manifest, read_connection


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Overview(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    not_real_world_performance: Literal[True] = True
    model_version: str
    score_cutoff: date
    trained_at: datetime
    customers: Annotated[int, Field(ge=1)]
    average_precision: Annotated[float, Field(ge=0, le=1)]
    baseline_average_precision: Annotated[float, Field(ge=0, le=1)]
    roc_auc: Annotated[float, Field(ge=0, le=1)]
    brier: Annotated[float, Field(ge=0, le=1)]
    recall_at_10pct: Annotated[float, Field(ge=0, le=1)]
    log_loss: Annotated[float, Field(ge=0)]
    limitations: list[str]


class RiskItem(Contract):
    customer_id: Annotated[str, Field(pattern=r"^SYN-[0-9]{5,7}$")]
    as_of_date: date
    churn_probability: Annotated[float, Field(ge=0, le=1)]


class RiskPage(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    model_version: str
    total: int
    limit: int
    offset: int
    items: list[RiskItem]


class Health(Contract):
    status: Literal["ok"] = "ok"
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"


class Ready(Health):
    model_version: str


def create_app(root: Path | None = None) -> FastAPI:
    data_root = (root or Path(os.getenv("RETENTIONOPS_ROOT", "."))).resolve()
    application = FastAPI(title="RetentionOps Synthetic Local API", version=__version__)

    def unavailable(exc: Exception) -> HTTPException:
        return HTTPException(
            503, "No valid publication. Run retentionops all or inspect local logs."
        )

    @application.get("/health", response_model=Health)
    def health():
        return Health()

    @application.get("/ready", response_model=Ready)
    def ready():
        try:
            with read_connection(data_root) as conn:
                manifest = active_manifest(conn)
                count = conn.execute(
                    "SELECT COUNT(*) FROM predictions WHERE model_version=?",
                    (manifest["model_version"],),
                ).fetchone()[0]
                if count != manifest["cohorts"]["test"]["rows"]:
                    raise ValueError("Publication reconciliation failed")
                return Ready(model_version=manifest["model_version"])
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            raise unavailable(exc) from exc

    @application.get("/api/v1/overview", response_model=Overview)
    def overview():
        try:
            with read_connection(data_root) as conn:
                m = active_manifest(conn)
            metrics = m["metrics"]["test"]
            values = (
                metrics["selected_model"]
                if "selected_model" in metrics
                else metrics["logistic_regression"]
            )
            return Overview(
                model_version=m["model_version"],
                score_cutoff=m["score_cutoff"],
                trained_at=m["trained_at"],
                customers=values["rows"],
                baseline_average_precision=metrics["constant_prior"]["average_precision"],
                limitations=m["limitations"],
                **{
                    k: values[k]
                    for k in (
                        "average_precision",
                        "roc_auc",
                        "brier",
                        "recall_at_10pct",
                        "log_loss",
                    )
                },
            )
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            raise unavailable(exc) from exc

    @application.get("/api/v1/risk", response_model=RiskPage)
    def risk(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ):
        try:
            with read_connection(data_root) as conn:
                m = active_manifest(conn)
                rows = conn.execute(
                    "SELECT customer_id, as_of_date, churn_probability FROM predictions "
                    "WHERE model_version=? ORDER BY churn_probability DESC, customer_id "
                    "LIMIT ? OFFSET ?",
                    (m["model_version"], limit, offset),
                ).fetchall()
                return RiskPage(
                    model_version=m["model_version"],
                    total=m["cohorts"]["test"]["rows"],
                    limit=limit,
                    offset=offset,
                    items=[RiskItem(**dict(r)) for r in rows],
                )
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            raise unavailable(exc) from exc

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard():
        return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")

    return application


app = create_app()
