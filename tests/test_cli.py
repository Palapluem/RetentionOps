import json
import sys
from datetime import date

from retentionops.cli import main
from retentionops.data import DEFAULT_AS_OF


def test_cli_ingests_then_runs_a_published_event_source(tmp_path, monkeypatch, capsys):
    source = tmp_path / "incoming.jsonl"
    root = tmp_path / "workspace"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retentionops",
            "generate-events",
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
