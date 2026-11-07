"""Read local operational facts without creating state or loading an executable model."""

import re
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from . import serving
from .data import sha256_file
from .serving import Contract, ModelStatus, RunInfo
from .storage import read_connection


class SourceTruth(Contract):
    status: Literal["simulated"] = "simulated"
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    label_definition: str
    external_source_connected: Literal[False] = False


class LocalInfrastructure(Contract):
    score_store: Literal["SQLite"] = "SQLite"
    cloud_connection: Literal["not_connected"] = "not_connected"
    authentication: Literal["not_configured"] = "not_configured"


class SystemStatus(Contract):
    data_mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    environment: Literal["local"] = "local"
    observed_at: datetime
    publication_state: Literal["ready", "empty", "unavailable"]
    message: str
    scored_customers: int | None
    score_cutoff: date | None
    active_release: ModelStatus | None
    model_artifact_state: Literal["not_published", "verified", "missing", "mismatch", "unavailable"]
    source_truth: SourceTruth
    infrastructure: LocalInfrastructure
    runs: list[RunInfo]


def _artifact_state(root: Path, release: ModelStatus) -> str:
    if not re.fullmatch(r"synthetic-(?:logreg|lightgbm)-[a-f0-9]{64}", release.model_version):
        return "unavailable"
    path = root / "artifacts" / "models" / release.model_version / "model.joblib"
    try:
        if not path.is_file():
            return "missing"
        return "verified" if sha256_file(path) == release.model_sha256 else "mismatch"
    except OSError:
        return "unavailable"


def inspect_system(root: Path) -> SystemStatus:
    """Keep attempts observable even before the first successful publication or on corruption."""
    state = "empty"
    active = None
    overview = None
    runs = []
    path = root / "artifacts" / "serving.sqlite"
    if path.exists():
        try:
            with read_connection(root) as conn:
                history = serving.jobs(conn)
                runs = history.items
                if history.publication_present:
                    state = "unavailable"
                    workspace = serving.workspace(conn, limit=1)
                    active, overview = workspace.status, workspace.overview
                    state = "ready"
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
            state = "unavailable"

    if active is None:
        label = (
            "No model publication identifies a scored source yet. "
            "The accepted source contract uses generated synthetic data."
        )
    elif active.event_release_id:
        label = (
            "No renewal in [scheduled expiry, expiry + 30 days] for a simulated subscription, "
            "with a complete source watermark and mature outcome window."
        )
    else:
        label = "A seeded simulated Bernoulli outcome at each historical snapshot cutoff."

    messages = {
        "ready": "The active release reconciles with its materialized scores and features.",
        "empty": "Run the synthetic event pipeline to publish the first release.",
        "unavailable": "The publication could not be verified. Inspect the local pipeline and retry.",
    }
    return SystemStatus(
        observed_at=datetime.now(UTC),
        publication_state=state,
        message=messages[state],
        scored_customers=overview.customers if overview else None,
        score_cutoff=overview.score_cutoff if overview else None,
        active_release=active,
        model_artifact_state=(
            _artifact_state(root, active)
            if active
            else "unavailable"
            if state == "unavailable"
            else "not_published"
        ),
        source_truth=SourceTruth(label_definition=label),
        infrastructure=LocalInfrastructure(),
        runs=runs,
    )
