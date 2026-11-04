import sqlite3

from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.pipeline import run_pipeline


def test_not_ready_and_no_implicit_database(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").status_code == 200
    for endpoint in ("/ready", "/api/v1/overview", "/api/v1/risk"):
        assert client.get(endpoint).status_code == 503
    assert not (tmp_path / "artifacts/serving.sqlite").exists()


def test_live_endpoints_and_active_model_isolation(publication):
    root, first = publication
    second = run_pipeline(root, customers=200)
    client = TestClient(create_app(root))
    assert client.get("/ready").json()["model_version"] == second["model_version"]
    summary = client.get("/api/v1/overview").json()
    assert summary["not_real_world_performance"] is True
    assert summary["customers"] == 200
    result = client.get("/api/v1/risk?limit=5").json()
    assert result["model_version"] != first["model_version"]
    assert result["total"] == 200 and len(result["items"]) == 5
    probabilities = [item["churn_probability"] for item in result["items"]]
    assert probabilities == sorted(probabilities, reverse=True)
    page = client.get("/api/v1/risk?limit=5&offset=5").json()
    assert not {r["customer_id"] for r in result["items"]} & {
        r["customer_id"] for r in page["items"]
    }
    assert client.get("/api/v1/risk?offset=200").json()["items"] == []
    assert client.post("/api/v1/risk").status_code == 405


def test_overview_reports_the_selected_lightgbm_candidate(tmp_path):
    manifest = run_pipeline(tmp_path, customers=100, seed=2)
    assert manifest["selection"]["selected_model_family"] == "lightgbm"

    overview = TestClient(create_app(tmp_path)).get("/api/v1/overview").json()

    assert (
        overview["average_precision"]
        == manifest["metrics"]["test"]["selected_model"]["average_precision"]
    )
    assert (
        overview["baseline_average_precision"]
        == manifest["metrics"]["test"]["constant_prior"]["average_precision"]
    )


def test_bounds_and_openapi(tmp_path):
    client = TestClient(create_app(tmp_path))
    for query in ("limit=0", "limit=101", "limit=abc", "offset=-1", "offset=100001"):
        assert client.get(f"/api/v1/risk?{query}").status_code == 422
    schema = client.get("/openapi.json").json()
    assert "Overview" in schema["components"]["schemas"]
    html = client.get("/")
    assert html.status_code == 200
    assert "Synthetic demo" in html.text
    assert "innerHTML" not in html.text


def test_corrupt_database_returns_503(tmp_path):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/serving.sqlite").write_bytes(b"not a database")
    client = TestClient(create_app(tmp_path))
    assert client.get("/ready").status_code == 503
    assert client.get("/api/v1/overview").status_code == 503


def test_invalid_manifest_shape_returns_503(publication):
    root, _ = publication
    with sqlite3.connect(root / "artifacts/serving.sqlite") as conn:
        conn.execute("UPDATE releases SET manifest='[]'")
    client = TestClient(create_app(root))
    for endpoint in ("/ready", "/api/v1/overview", "/api/v1/risk"):
        assert client.get(endpoint).status_code == 503
