import json

import pytest
from fastapi.testclient import TestClient

from retentionops import local_ai
from retentionops.api import create_app
from retentionops.pipeline import run_event_pipeline
from retentionops.serving import data_quality
from retentionops.storage import active_manifest, read_connection

INSIGHT_HEADERS = {"X-RetentionOps-Local-Insight": "generate"}


@pytest.fixture(autouse=True)
def reset_insight_cooldown(monkeypatch):
    monkeypatch.setattr(local_ai, "_LAST_INFERENCE_AT", 0.0)


def _event_publication(tmp_path):
    return run_event_pipeline(tmp_path, customers=50)


def test_event_quality_summary_reconciles_counts_and_maturity(tmp_path):
    manifest = _event_publication(tmp_path)
    with read_connection(tmp_path) as conn:
        summary = data_quality(conn, active_manifest(conn))

    assert summary.source_kind == "event_derived"
    assert summary.source_event_revisions == manifest["source"]["events"]["rows"]
    assert summary.eligible_rows == manifest["source"]["quality"]["eligible_rows"]
    assert summary.excluded_rows == manifest["source"]["quality"]["excluded_no_known_subscription"]
    assert summary.candidate_opportunities == summary.eligible_rows + summary.excluded_rows
    assert summary.feature_rows == summary.eligible_rows
    assert summary.scored_rows == summary.test_cohort_rows
    assert summary.source_coverage_status == "verified"
    assert summary.source_complete_through >= summary.evaluation_freeze
    assert summary.label_maturity_status == "verified"
    assert sum(cohort.eligible for cohort in summary.cohorts) == summary.feature_rows


def test_snapshot_quality_summary_does_not_invent_source_watermark(publication):
    root, _ = publication
    with read_connection(root) as conn:
        summary = data_quality(conn, active_manifest(conn))

    assert summary.source_kind == "snapshot"
    assert summary.source_coverage_status == "not_declared"
    assert summary.source_complete_through is None
    assert summary.excluded_rows is None
    assert summary.eligible_rows == summary.feature_rows


def test_local_ai_payload_contains_only_allowlisted_aggregate_facts(publication, monkeypatch):
    root, _ = publication
    captured = {}

    def choose(**kwargs):
        captured.update(kwargs)
        return {
            "observation_ids": ["publication_reconciled", "test_cohort_mature"],
            "next_step": "review_cohort_denominators",
        }

    monkeypatch.setattr(local_ai, "_request_model", choose)
    response = TestClient(create_app(root)).post(
        "/api/v1/insights",
        json={"customer_id": "SYN-00001", "prompt": "private"},
        headers=INSIGHT_HEADERS,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ready"
    assert result["advisory_only"] is True
    assert result["model_version"] is not None
    assert result["source_release_id"] is not None
    assert "customer_id" not in json.dumps(captured["facts"])
    assert "SYN-" not in json.dumps(captured["facts"])
    assert "private" not in json.dumps(captured["facts"])
    assert "model_version" not in captured["facts"]
    assert "source_release_id" not in captured["facts"]
    assert set(captured["facts"]) == {
        "data_mode",
        "source_kind",
        "source_coverage_status",
        "source_complete_through",
        "evaluation_freeze",
        "score_cutoff",
        "source_rows",
        "eligible_rows",
        "excluded_rows",
        "feature_rows",
        "scored_rows",
        "reconciliation_status",
        "label_maturity_status",
        "test_cohort_rows",
        "test_churned",
        "test_churn_rate",
        "test_average_precision",
        "baseline_average_precision",
        "test_brier",
        "recall_at_10pct",
    }


@pytest.mark.parametrize("runtime_url", ["https://example.com:11434", "http://ollama:11434"])
def test_local_ai_requires_no_publication_or_external_runtime(
    publication, monkeypatch, runtime_url
):
    root, _ = publication
    called = False

    def unexpected(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("Unsafe runtime must not be called")

    monkeypatch.setattr(local_ai, "_request_model", unexpected)
    monkeypatch.setenv("RETENTIONOPS_OLLAMA_URL", runtime_url)
    response = TestClient(create_app(root)).post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "unsafe_runtime_url"
    assert called is False


def test_insight_api_requires_the_fixed_same_origin_action_header(publication, monkeypatch):
    root, _ = publication
    called = False

    def unexpected(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("Missing action header must not invoke the model")

    monkeypatch.setattr(local_ai, "_request_model", unexpected)
    response = TestClient(create_app(root)).post("/api/v1/insights")

    assert response.status_code == 403
    assert called is False


def test_local_inference_cooldown_limits_repeated_calls(publication, monkeypatch):
    root, _ = publication
    calls = 0

    def choose(**kwargs):
        nonlocal calls
        calls += 1
        return {
            "observation_ids": ["publication_reconciled"],
            "next_step": "review_cohort_denominators",
        }

    monkeypatch.setattr(local_ai, "_request_model", choose)
    client = TestClient(create_app(root))
    first = client.post("/api/v1/insights", headers=INSIGHT_HEADERS)
    second = client.post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert first.json()["status"] == "ready"
    assert second.json()["reason"] == "rate_limited"
    assert calls == 1


def test_insight_without_release_does_not_create_database(tmp_path, monkeypatch):
    called = False

    def unexpected(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("No model call is allowed before publication")

    monkeypatch.setattr(local_ai, "_request_model", unexpected)
    response = TestClient(create_app(tmp_path)).post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert response.status_code == 200
    assert response.json()["reason"] == "no_publication"
    assert called is False
    assert not (tmp_path / "artifacts/serving.sqlite").exists()


def test_corrupt_publication_does_not_look_like_an_empty_release(tmp_path, monkeypatch):
    database = tmp_path / "artifacts/serving.sqlite"
    database.parent.mkdir()
    database.write_bytes(b"not a database")

    def unexpected(**kwargs):
        raise AssertionError("Model call must not run")

    monkeypatch.setattr(local_ai, "_request_model", unexpected)

    response = TestClient(create_app(tmp_path)).post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert response.status_code == 200
    assert response.json()["reason"] == "publication_unavailable"


def test_local_model_response_is_schema_and_allowlist_validated(publication, monkeypatch):
    root, _ = publication

    def unsupported(**kwargs):
        return {"observation_ids": ["invented_claim"], "next_step": "review_cohort_denominators"}

    monkeypatch.setattr(local_ai, "_request_model", unsupported)
    response = TestClient(create_app(root)).post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "invalid_response"


def test_verified_event_coverage_observation_uses_release_dates(tmp_path, monkeypatch):
    manifest = _event_publication(tmp_path)

    def choose(**kwargs):
        assert "event_coverage_verified" in kwargs["observations"]
        return {
            "observation_ids": ["event_coverage_verified"],
            "next_step": "review_cohort_denominators",
        }

    monkeypatch.setattr(local_ai, "_request_model", choose)
    response = TestClient(create_app(tmp_path)).post("/api/v1/insights", headers=INSIGHT_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert manifest["source"]["events"]["complete_through"] in body["observations"][0]["text"]
    assert manifest["evaluation_freeze"] in body["observations"][0]["text"]
