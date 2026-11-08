"""Score reads must fail closed when the persisted cutoff disagrees with the release."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.data import CUTOFFS
from retentionops.pipeline import run_event_pipeline, run_pipeline


def move_one_score_to_prior_cohort(root, manifest):
    """Preserve score and joined-row counts while moving a score to an existing feature key."""
    version = manifest["model_version"]
    cutoff = manifest["score_cutoff"]
    prior_cutoff = str(CUTOFFS[-2])
    assert prior_cutoff < cutoff
    with sqlite3.connect(root / "artifacts/serving.sqlite") as conn:
        counts = conn.execute(
            "SELECT COUNT(*), COUNT(f.customer_id) FROM predictions p "
            "LEFT JOIN feature_snapshots f USING(model_version,customer_id,as_of_date) "
            "WHERE p.model_version=?",
            (version,),
        ).fetchone()
        row = conn.execute(
            "SELECT p.customer_id FROM predictions p JOIN feature_snapshots f "
            "ON f.model_version=p.model_version AND f.customer_id=p.customer_id "
            "WHERE p.model_version=? AND p.as_of_date=? AND f.as_of_date=? "
            "ORDER BY p.customer_id LIMIT 1",
            (version, cutoff, prior_cutoff),
        ).fetchone()
        assert row is not None
        customer_id = row[0]
        changed = conn.execute(
            "UPDATE predictions SET as_of_date=? "
            "WHERE model_version=? AND customer_id=? AND as_of_date=?",
            (prior_cutoff, version, customer_id, cutoff),
        )
        assert changed.rowcount == 1
        after = conn.execute(
            "SELECT COUNT(*), COUNT(f.customer_id) FROM predictions p "
            "LEFT JOIN feature_snapshots f USING(model_version,customer_id,as_of_date) "
            "WHERE p.model_version=?",
            (version,),
        ).fetchone()
        assert counts == after == (manifest["cohorts"]["test"]["rows"],) * 2
    return customer_id


@pytest.mark.parametrize(
    "endpoint",
    [
        "/ready",
        "/api/v1/overview",
        "/api/v1/workspace",
        "/api/v1/risk?limit=5",
        "/api/v1/risk?search=SYN-00001",
        "/api/v1/customers/SYN-00000",
        "/api/v1/customers/SYN-00001",
    ],
)
def test_active_release_wrong_score_cutoff_fails_closed(publication, endpoint):
    root, manifest = publication
    moved_customer = move_one_score_to_prior_cohort(root, manifest)
    assert moved_customer == "SYN-00000"
    client = TestClient(create_app(root))

    assert client.get(endpoint).status_code == 503


def test_system_reports_active_cutoff_corruption_unavailable(publication):
    root, manifest = publication
    move_one_score_to_prior_cohort(root, manifest)
    client = TestClient(create_app(root))

    result = client.get("/api/v1/system-status")

    assert result.status_code == 200
    assert result.json()["publication_state"] == "unavailable"
    assert result.json()["active_release"] is None


def test_corrupt_pinned_release_fails_without_disrupting_valid_active_release(tmp_path):
    first = run_pipeline(tmp_path, customers=100, seed=2)
    second = run_pipeline(tmp_path, customers=150)
    moved_customer = move_one_score_to_prior_cohort(tmp_path, first)
    client = TestClient(create_app(tmp_path))

    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/system-status").json()["publication_state"] == "ready"
    active = client.get(f"/api/v1/customers/{moved_customer}")
    assert active.status_code == 200
    assert active.json()["model_version"] == second["model_version"]
    assert active.json()["as_of_date"] == second["score_cutoff"]

    pinned = client.get(
        f"/api/v1/customers/{moved_customer}?model_version={first['model_version']}"
    )
    assert pinned.status_code == 503
    unaffected_customer = client.get(
        f"/api/v1/customers/SYN-00001?model_version={first['model_version']}"
    )
    assert unaffected_customer.status_code == 503
    assert client.get("/ready").status_code == 200


@pytest.mark.parametrize("pipeline", [run_pipeline, run_event_pipeline], ids=["snapshot", "events"])
def test_valid_release_serves_only_its_selected_cutoff(tmp_path, pipeline):
    manifest = pipeline(tmp_path, customers=100)
    client = TestClient(create_app(tmp_path))

    assert client.get("/ready").status_code == 200
    page = client.get("/api/v1/risk?limit=100")
    assert page.status_code == 200
    assert len(page.json()["items"]) == manifest["cohorts"]["test"]["rows"]
    assert {row["as_of_date"] for row in page.json()["items"]} == {manifest["score_cutoff"]}
    customer_id = page.json()["items"][0]["customer_id"]
    detail = client.get(f"/api/v1/customers/{customer_id}")
    assert detail.status_code == 200
    assert detail.json()["as_of_date"] == manifest["score_cutoff"]
