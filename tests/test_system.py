import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.data import Snapshot
from retentionops.pipeline import run_event_source_pipeline, run_pipeline
from retentionops.storage import active_manifest, publish, read_connection


def test_empty_system_status_does_not_create_a_database(tmp_path):
    response = TestClient(create_app(tmp_path)).get("/api/v1/system-status")

    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "empty"
    assert status["active_release"] is None
    assert status["scored_customers"] is None
    assert status["model_artifact_state"] == "not_published"
    assert status["runs"] == []
    assert status["source_truth"]["status"] == "simulated"
    assert status["source_truth"]["source_type"] == "SYNTHETIC"
    assert status["source_truth"]["external_source_connected"] is False
    assert status["infrastructure"] == {
        "score_store": "SQLite",
        "cloud_connection": "not_connected",
        "authentication": "not_configured",
    }
    assert not (tmp_path / "artifacts/serving.sqlite").exists()


@pytest.mark.parametrize("mode", ["snapshots", "event-source"])
def test_first_failed_pipeline_is_visible_without_a_publication(tmp_path, mode):
    with pytest.raises(ValueError):
        if mode == "snapshots":
            run_pipeline(tmp_path, customers=100, as_of=date(2026, 10, 1))
        else:
            run_event_source_pipeline(tmp_path, "invalid-release")

    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/system-status")

    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "empty"
    assert status["active_release"] is None
    assert status["model_artifact_state"] == "not_published"
    assert len(status["runs"]) == 1
    run = status["runs"][0]
    assert run["mode"] == mode
    assert run["state"] == "failed"
    assert run["error_type"] == "ValueError"
    assert run["finished_at"] is not None
    assert run["model_version"] is None
    assert run["output_rows"] is None
    assert client.get("/ready").status_code == 503


@pytest.mark.parametrize("mode", ["snapshots", "event-source"])
def test_failed_pipeline_retains_the_verified_active_publication(publication, mode):
    root, manifest = publication
    client = TestClient(create_app(root))
    before = client.get("/api/v1/system-status").json()

    with pytest.raises(ValueError):
        if mode == "snapshots":
            run_pipeline(root, customers=200, as_of=date(2026, 10, 1))
        else:
            run_event_source_pipeline(root, "invalid-release")

    response = client.get("/api/v1/system-status")

    assert response.status_code == 200
    after = response.json()
    assert after["publication_state"] == "ready"
    assert after["active_release"]["model_version"] == manifest["model_version"]
    assert after["scored_customers"] == before["scored_customers"] == 150
    assert after["score_cutoff"] == before["score_cutoff"] == manifest["score_cutoff"]
    assert after["model_artifact_state"] == "verified"
    assert after["runs"][0]["mode"] == mode
    assert after["runs"][0]["state"] == "failed"
    assert after["runs"][1]["state"] == "succeeded"
    assert after["runs"][1]["model_version"] == manifest["model_version"]
    assert client.get("/ready").status_code == 200
    with read_connection(root) as conn:
        assert active_manifest(conn) == manifest


def test_selected_lightgbm_release_agrees_across_api_views_and_pinned_detail(tmp_path):
    manifest = run_pipeline(tmp_path, customers=100, seed=2)
    selection = manifest["selection"]
    assert selection["selected_model_family"] == "lightgbm"
    client = TestClient(create_app(tmp_path))
    system_response = client.get("/api/v1/system-status")
    workspace_response = client.get("/api/v1/workspace?limit=5")
    model_response = client.get("/api/v1/model-status")
    overview_response = client.get("/api/v1/overview")
    assert all(
        response.status_code == 200
        for response in (
            system_response,
            workspace_response,
            model_response,
            overview_response,
        )
    )
    system = system_response.json()
    workspace = workspace_response.json()
    model = model_response.json()
    overview = overview_response.json()
    assert {section["model_version"] for section in workspace.values()} == {
        manifest["model_version"]
    }
    assert workspace["overview"] == overview
    assert system["active_release"] == workspace["status"] == model
    assert system["publication_state"] == "ready"
    assert system["model_artifact_state"] == "verified"
    assert system["scored_customers"] == 100
    assert system["score_cutoff"] == manifest["score_cutoff"]
    assert system["source_truth"]["status"] == "simulated"
    assert system["source_truth"]["external_source_connected"] is False
    assert model["model_family"] == "lightgbm"
    assert model["selected_candidate"] == selection["selected_candidate"]
    assert model["selected_parameters"] == selection["selected_parameters"]
    assert model["selection_metric"] == selection["metric"]
    selected_validation = next(
        row
        for row in selection["candidates"]
        if row["candidate"] == selection["selected_candidate"]
    )
    assert model["validation_average_precision"] == selected_validation["average_precision"]
    for metric in ("average_precision", "roc_auc", "brier", "log_loss", "recall_at_10pct"):
        assert overview[metric] == manifest["metrics"]["test"]["selected_model"][metric]

    selected_row = workspace["risk"]["items"][0]
    second = run_pipeline(tmp_path, customers=150)
    assert second["model_version"] != manifest["model_version"]
    pinned = client.get(
        f"/api/v1/customers/{selected_row['customer_id']}?model_version={manifest['model_version']}"
    )
    assert pinned.status_code == 200
    assert pinned.json()["model_version"] == manifest["model_version"]
    assert pinned.json()["churn_probability"] == selected_row["churn_probability"]
    assert client.get("/api/v1/overview").json()["model_version"] == second["model_version"]


def test_model_checksum_mismatch_keeps_materialized_serving_available(publication):
    root, manifest = publication
    client = TestClient(create_app(root))
    before = client.get("/api/v1/risk?limit=5").json()
    model_path = root / "artifacts/models" / manifest["model_version"] / "model.joblib"
    model_path.write_bytes(b"invalid model bytes")

    response = client.get("/api/v1/system-status")

    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "ready"
    assert status["model_artifact_state"] == "mismatch"
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/risk?limit=5").json() == before


def test_corrupt_database_reports_unavailable_without_echoing_local_content(tmp_path):
    database = tmp_path / "artifacts/serving.sqlite"
    database.parent.mkdir()
    database.write_bytes(b"private-source-marker: not a SQLite database")

    response = TestClient(create_app(tmp_path)).get("/api/v1/system-status")

    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "unavailable"
    assert status["active_release"] is None
    assert status["runs"] == []
    assert "private-source-marker" not in response.text
    assert str(tmp_path) not in response.text


def test_broken_feature_reconciliation_is_observable_with_run_history(publication):
    root, _ = publication
    with sqlite3.connect(root / "artifacts/serving.sqlite") as conn:
        conn.execute(
            "DELETE FROM feature_snapshots WHERE customer_id='SYN-00001' "
            "AND as_of_date='2026-09-30'"
        )
    client = TestClient(create_app(root))

    response = client.get("/api/v1/system-status")

    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "unavailable"
    assert status["active_release"] is None
    assert status["runs"][0]["state"] == "succeeded"
    assert client.get("/ready").status_code == 503


def test_conflicting_feature_replay_preserves_scores_and_active_release(publication):
    root, first = publication
    version = first["model_version"]
    with read_connection(root) as conn:
        scores = [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM predictions WHERE model_version=? ORDER BY customer_id,as_of_date",
                (version,),
            )
        ]
        original_features = [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM feature_snapshots WHERE model_version=? "
                "ORDER BY customer_id,as_of_date",
                (version,),
            )
        ]
    snapshots = [Snapshot.model_validate_json(row[3]) for row in original_features]
    changed = snapshots[0].model_dump()
    changed["monthly_fee"] += 1
    snapshots[0] = Snapshot.model_validate(changed)
    second = run_pipeline(root, customers=200)

    with pytest.raises(ValueError, match="immutable model release"):
        publish(root, first, scores, snapshots=snapshots)

    with read_connection(root) as conn:
        assert active_manifest(conn) == second
        assert [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM predictions WHERE model_version=? ORDER BY customer_id,as_of_date",
                (version,),
            )
        ] == scores
        assert [
            tuple(row)
            for row in conn.execute(
                "SELECT * FROM feature_snapshots WHERE model_version=? "
                "ORDER BY customer_id,as_of_date",
                (version,),
            )
        ] == original_features
    assert TestClient(create_app(root)).get("/ready").status_code == 200
