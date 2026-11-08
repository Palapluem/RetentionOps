"""Exercise recovery through the event pipeline and read-only serving interfaces."""

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.pipeline import run_event_pipeline, run_event_source_pipeline
from retentionops.storage import read_connection


def test_protected_output_rejection_is_recorded_and_preserves_publication(tmp_path):
    manifest = run_event_pipeline(tmp_path, customers=100)
    client = TestClient(create_app(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "retentionops.cli",
            "generate-events",
            "--root",
            str(tmp_path),
            "--output",
            str(tmp_path / "artifacts/serving.sqlite"),
            "--customers",
            "50",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert client.get("/ready").status_code == 200
    status = client.get("/api/v1/system-status").json()
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert status["runs"][0]["mode"] == "source-generation"
    assert status["runs"][0]["state"] == "failed"


def test_event_release_replay_restores_service_after_a_failed_run(tmp_path):
    first = run_event_pipeline(tmp_path, customers=100)
    client = TestClient(create_app(tmp_path))
    first_risk = client.get("/api/v1/risk?limit=100").json()
    first_cohorts = client.get("/api/v1/cohorts").json()
    customer_id = first_risk["items"][0]["customer_id"]
    first_detail = client.get(f"/api/v1/customers/{customer_id}").json()
    assert len(first_risk["items"]) == first_risk["total"] == 100
    assert first_detail["model_version"] == first["model_version"]
    assert first_detail["features"]

    second = run_event_pipeline(tmp_path, customers=120)
    assert second["model_version"] != first["model_version"]
    second_risk = client.get("/api/v1/risk?limit=100").json()
    second_detail = client.get(f"/api/v1/customers/{customer_id}").json()
    assert second_risk["model_version"] == second["model_version"]
    assert second_risk["total"] == 120
    assert second_detail["model_version"] == second["model_version"]
    with read_connection(tmp_path) as conn:
        before = {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3")]
            for table in ("predictions", "feature_snapshots")
        }

    with pytest.raises(ValueError):
        run_event_source_pipeline(tmp_path, "invalid-release")
    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == second["model_version"]
    assert status["runs"][0]["state"] == "failed"
    assert client.get("/api/v1/risk?limit=100").json() == second_risk
    assert client.get(f"/api/v1/customers/{customer_id}").json() == second_detail

    restored = run_event_pipeline(tmp_path, customers=100)
    assert restored == first
    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == first["model_version"]
    assert status["model_artifact_state"] == "verified"
    assert [run["state"] for run in status["runs"][:4]] == [
        "succeeded",
        "failed",
        "succeeded",
        "succeeded",
    ]
    assert [status["runs"][i]["model_version"] for i in (0, 2, 3)] == [
        first["model_version"],
        second["model_version"],
        first["model_version"],
    ]
    assert client.get("/api/v1/risk?limit=100").json() == first_risk
    assert client.get("/api/v1/cohorts").json() == first_cohorts
    assert client.get(f"/api/v1/customers/{customer_id}").json() == first_detail
    assert (
        client.get(
            f"/api/v1/customers/{customer_id}?model_version={second['model_version']}"
        ).json()
        == second_detail
    )
    with read_connection(tmp_path) as conn:
        after = {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3")]
            for table in ("predictions", "feature_snapshots")
        }
    assert before == after
