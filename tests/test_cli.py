import json
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.cli import main
from retentionops.data import DEFAULT_AS_OF
from retentionops.storage import active_manifest, read_connection


def test_cli_ingests_then_runs_a_published_event_source(tmp_path, monkeypatch, capsys):
    source = tmp_path / "incoming.jsonl"
    root = tmp_path / "workspace"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentionops",
            "generate-events",
            "--root",
            str(root),
            "--output",
            str(source),
            "--customers",
            "150",
            "--seed",
            "98",
        ],
    )
    main()
    generated = json.loads(capsys.readouterr().out)
    assert generated["rows"] > 0

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentionops",
            "ingest-events",
            "--root",
            str(root),
            "--input",
            str(source),
            "--source-id",
            "sample-upload",
            "--complete-through",
            str(DEFAULT_AS_OF),
        ],
    )
    main()
    ingested = json.loads(capsys.readouterr().out)
    assert ingested["source_type"] == "SYNTHETIC"
    client = TestClient(create_app(root))
    assert client.get("/api/v1/system-status").json()["publication_state"] == "empty"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentionops",
            "run-events",
            "--root",
            str(root),
            "--source-release",
            ingested["source_release_id"],
            "--as-of",
            str(date(2026, 11, 3)),
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["source"]["events"]["source_release_id"] == ingested["source_release_id"]
    status = client.get("/api/v1/system-status").json()
    assert status["publication_state"] == "ready"
    assert status["active_release"]["model_version"] == result["model_version"]
    chronological = list(reversed(status["runs"]))
    assert [run["mode"] for run in chronological] == [
        "source-generation",
        "source-intake",
        "event-source",
    ]
    assert all(run["state"] == "succeeded" for run in chronological)
    assert all(run["finished_at"] is not None for run in chronological)
    assert [run["output_rows"] for run in chronological] == [
        generated["rows"],
        ingested["rows"],
        result["cohorts"]["test"]["rows"],
    ]
    assert generated["rows"] == ingested["rows"]
    assert [run["model_version"] for run in chronological] == [
        None,
        None,
        result["model_version"],
    ]


@pytest.mark.parametrize("mode", ["source-generation", "source-intake"])
def test_failed_source_stage_is_observable_without_publication(tmp_path, monkeypatch, capsys, mode):
    root = tmp_path / "workspace"
    source = tmp_path / "incoming.jsonl"
    if mode == "source-generation":
        arguments = ["generate-events", "--output", str(source), "--customers", "0"]
    else:
        source.write_text("private-row-sentinel\n")
        arguments = [
            "ingest-events",
            "--input",
            str(source),
            "--source-id",
            "invalid-feed",
            "--complete-through",
            str(DEFAULT_AS_OF),
        ]
    monkeypatch.setattr(sys, "argv", ["retentionops", *arguments, "--root", str(root)])

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private-row-sentinel" not in captured.err
    response = TestClient(create_app(root)).get("/api/v1/system-status")
    assert response.status_code == 200
    status = response.json()
    assert status["publication_state"] == "empty"
    assert status["active_release"] is None
    assert status["runs"][0]["mode"] == mode
    assert status["runs"][0]["state"] == "failed"
    assert status["runs"][0]["error_type"] == "ValueError"
    assert status["runs"][0]["output_rows"] is None
    assert not list((root / "data/events").glob("*"))
    with read_connection(root) as conn:
        assert conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM active_release").fetchone()[0] == 0


def test_failed_intake_keeps_the_prior_model_and_scores(publication, monkeypatch, capsys):
    root, manifest = publication
    client = TestClient(create_app(root))
    before = client.get("/api/v1/risk?limit=5").json()
    source = root / "invalid-intake.jsonl"
    source.write_text("malformed source row\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentionops",
            "ingest-events",
            "--root",
            str(root),
            "--input",
            str(source),
            "--source-id",
            "invalid-feed",
            "--complete-through",
            str(DEFAULT_AS_OF),
        ],
    )

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    assert capsys.readouterr().out == ""
    status = client.get("/api/v1/system-status").json()
    assert status["publication_state"] == "ready"
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert status["runs"][0]["mode"] == "source-intake"
    assert status["runs"][0]["state"] == "failed"
    assert status["runs"][1]["state"] == "succeeded"
    assert not list((root / "data/events").glob("invalid-feed-*"))
    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/risk?limit=5").json() == before
    with read_connection(root) as conn:
        assert active_manifest(conn) == manifest
