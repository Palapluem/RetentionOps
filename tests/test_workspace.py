import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.data import FEATURES
from retentionops.pipeline import run_event_pipeline, run_pipeline
from retentionops.storage import active_manifest, read_connection


def test_consistent_workspace_and_customer(publication):
    root, manifest = publication
    client = TestClient(create_app(root))
    response = client.get("/api/v1/workspace?limit=12")
    assert response.status_code == 200
    data = response.json()
    assert {section["model_version"] for section in data.values()} == {manifest["model_version"]}
    assert data["overview"]["customers"] == data["risk"]["total"] == 150
    assert sum(c["eligible"] for c in data["cohorts"]["items"]) == 600
    assert len(data["cohorts"]["items"]) == 4
    for cohort in data["cohorts"]["items"]:
        assert cohort["churn_rate"] == cohort["churned"] / cohort["eligible"]
    first = data["risk"]["items"][0]
    detail = client.get(f"/api/v1/customers/{first['customer_id']}").json()
    assert detail["churn_probability"] == first["churn_probability"]
    assert set(detail["features"]) == set(FEATURES)
    assert detail["features"]["active_days_30d"] == first["active_days_30d"]
    assert detail["source_max_available_at"] <= detail["as_of_date"]
    assert "churn_30d" not in detail["features"]


@pytest.mark.parametrize("band", ["all", "high", "watch", "low"])
@pytest.mark.parametrize("renewal", [0, 1])
def test_filters_match_published_rows(publication, band, renewal):
    root, manifest = publication
    client = TestClient(create_app(root))
    data = client.get(f"/api/v1/risk?limit=100&band={band}&auto_renew={renewal}").json()
    with read_connection(root) as conn:
        rows = conn.execute(
            "SELECT p.churn_probability, f.snapshot FROM predictions p JOIN feature_snapshots f "
            "USING(model_version,customer_id,as_of_date) WHERE model_version=?",
            (manifest["model_version"],),
        ).fetchall()
    expected = [
        p
        for p, s in rows
        if json.loads(s)["auto_renew"] == renewal
        and (
            band == "all"
            or band == "high"
            and p >= 0.4
            or band == "watch"
            and 0.2 <= p < 0.4
            or band == "low"
            and p < 0.2
        )
    ]
    assert data["total"] == len(expected)
    assert all(r["auto_renew"] == renewal for r in data["items"])
    assert [r["churn_probability"] for r in data["items"]] == sorted(expected, reverse=True)[:100]


def test_search_bounds_and_pinned_detail(publication):
    root, first = publication
    client = TestClient(create_app(root))
    before = client.get("/api/v1/risk?search=SYN-00001").json()["items"][0]
    run_pipeline(root, customers=200)
    pinned = client.get(f"/api/v1/customers/SYN-00001?model_version={first['model_version']}")
    assert pinned.json()["model_version"] == first["model_version"]
    assert pinned.json()["churn_probability"] == before["churn_probability"]
    assert client.get("/api/v1/customers/SYN-99999").status_code == 404
    assert client.get("/api/v1/risk?search=9999999").json()["total"] == 0
    for query in ("band=invalid", "auto_renew=2", "search=%25", "search=%27"):
        assert client.get(f"/api/v1/workspace?{query}").status_code == 422


def test_job_success_failure_and_publication_are_reconciled(tmp_path):
    first = run_event_pipeline(tmp_path, customers=150)
    client = TestClient(create_app(tmp_path))
    status = client.get("/api/v1/model-status").json()
    assert status["event_release_id"].startswith("synthetic-events-")
    assert status["quality"]["eligible_rows"] == 600
    run = status["runs"][0]
    assert run["state"] == "succeeded" and run["model_version"] == first["model_version"]
    assert run["output_rows"] == 150 and run["elapsed_seconds"] > 0
    with pytest.raises(ValueError, match="Immature"):
        run_event_pipeline(tmp_path, customers=150, as_of=date(2026, 10, 1))
    status = client.get("/api/v1/model-status").json()
    assert status["runs"][0]["state"] == "failed"
    assert status["runs"][0]["error_type"] == "ValueError"
    assert status["model_version"] == first["model_version"]
    with read_connection(tmp_path) as conn:
        assert active_manifest(conn) == first


def test_first_failure_status_is_available_without_publication(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/jobs").json() == {"publication_present": False, "items": []}
    assert not (tmp_path / "artifacts/serving.sqlite").exists()
    with pytest.raises(ValueError, match="Immature"):
        run_event_pipeline(tmp_path, customers=150, as_of=date(2026, 10, 1))
    assert client.get("/ready").status_code == 503
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    status = response.json()
    assert status["publication_present"] is False
    assert status["items"][0]["state"] == "failed"
    assert status["items"][0]["error_type"] == "ValueError"


def test_missing_features_fail_readiness(publication):
    root, _ = publication
    with sqlite3.connect(root / "artifacts/serving.sqlite") as conn:
        conn.execute("DELETE FROM feature_snapshots WHERE customer_id='SYN-00001'")
    client = TestClient(create_app(root))
    assert client.get("/ready").status_code == 503
    assert client.get("/api/v1/workspace").status_code == 503


def test_wrong_feature_keys_fail_even_with_matching_row_counts(publication):
    root, _ = publication
    with sqlite3.connect(root / "artifacts/serving.sqlite") as conn:
        conn.execute(
            "UPDATE feature_snapshots SET customer_id='SYN-99999' "
            "WHERE customer_id='SYN-00001' AND as_of_date='2026-09-30'"
        )
    client = TestClient(create_app(root))
    assert client.get("/ready").status_code == 503


def test_publication_rejects_score_feature_key_mismatch(publication):
    from retentionops.data import read_snapshots
    from retentionops.storage import publish

    root, manifest = publication
    source = next((root / "data/raw").glob("*/snapshots.csv"))
    records = read_snapshots(source)
    records = [
        r.model_copy(update={"customer_id": "SYN-99999"})
        if r.customer_id == "SYN-00001" and r.as_of_date.month == 9
        else r
        for r in records
    ]
    with read_connection(root) as conn:
        scores = [tuple(r) for r in conn.execute("SELECT * FROM predictions").fetchall()]
    with pytest.raises(ValueError, match="key reconciliation"):
        publish(root, manifest, scores, snapshots=records)
    assert TestClient(create_app(root)).get("/ready").status_code == 200
