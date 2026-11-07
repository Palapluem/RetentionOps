"""Typed read-only synthetic analytics; bind to loopback until cloud auth is approved."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse

from . import __version__, serving
from .serving import Contract, CustomerDetail, ModelStatus, Overview, RiskPage, Workspace
from .storage import active_manifest, read_connection
from .system_status import SystemStatus, inspect_system


class Health(Contract):
    status: Literal["ok"] = "ok"
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"


class Ready(Health):
    model_version: str


def risk_filters(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    search: Annotated[str, Query(max_length=32, pattern=r"^[A-Za-z0-9-]*$")] = "",
    band: Literal["all", "high", "watch", "low"] = "all",
    auto_renew: Annotated[int | None, Query(ge=0, le=1)] = None,
) -> dict:
    return dict(limit=limit, offset=offset, search=search, band=band, auto_renew=auto_renew)


def create_app(root: Path | None = None) -> FastAPI:
    data_root = (root or Path(os.getenv("RETENTIONOPS_ROOT", "."))).resolve()
    application = FastAPI(title="RetentionOps Synthetic Analytics API", version=__version__)

    def read(function, *args, **kwargs):
        try:
            with read_connection(data_root) as conn:
                return function(conn, *args, **kwargs)
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            logging.warning("Publication read unavailable: %s", type(exc).__name__)
            raise HTTPException(
                503, "No valid publication. Inspect pipeline status and retry."
            ) from exc

    @application.get("/health", response_model=Health)
    def health():
        return Health()

    @application.get("/ready", response_model=Ready)
    def ready():
        state = read(serving.workspace, limit=1)
        return Ready(model_version=state.overview.model_version)

    @application.get("/api/v1/overview", response_model=Overview)
    def overview():
        return read(lambda conn: serving.overview(conn, active_manifest(conn)))

    @application.get("/api/v1/risk", response_model=RiskPage)
    def risk(criteria: Annotated[dict, Depends(risk_filters)]):
        return read(lambda conn: serving.risk(conn, active_manifest(conn), **criteria))

    @application.get("/api/v1/cohorts", response_model=serving.CohortPage)
    def cohorts():
        return read(lambda conn: serving.cohorts(conn, active_manifest(conn)))

    @application.get("/api/v1/model-status", response_model=ModelStatus)
    def model_status():
        return read(lambda conn: serving.model_status(conn, active_manifest(conn)))

    @application.get("/api/v1/workspace", response_model=Workspace)
    def workspace(criteria: Annotated[dict, Depends(risk_filters)]):
        return read(serving.workspace, **criteria)

    @application.get("/api/v1/jobs", response_model=serving.JobPage)
    def jobs():
        if not (data_root / "artifacts/serving.sqlite").exists():
            return serving.JobPage(publication_present=False, items=[])
        return read(serving.jobs)

    @application.get("/api/v1/system-status", response_model=SystemStatus)
    def system_status():
        return inspect_system(data_root)

    @application.get("/api/v1/customers/{customer_id}", response_model=CustomerDetail)
    def customer(
        customer_id: Annotated[str, PathParam(pattern=r"^SYN-[0-9]{5,7}$")],
        model_version: Annotated[
            str | None, Query(pattern=r"^synthetic-(?:logreg|lightgbm)-[a-f0-9]{64}$")
        ] = None,
    ):
        return read(serving.customer, customer_id, model_version)

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard():
        return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")

    return application


app = create_app()
