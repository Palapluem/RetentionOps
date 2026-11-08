import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from retentionops.api import create_app
from retentionops.data import DEFAULT_AS_OF
from retentionops.events import Event, generate_events, ingest_event_source
from retentionops.pipeline import run_pipeline
from retentionops.storage import active_manifest, read_connection


def cli_generate(root, output, seed=342):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "retentionops.cli",
            "generate-events",
            "--root",
            str(root),
            "--output",
            str(output),
            "--customers",
            "50",
            "--seed",
            str(seed),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generation_cannot_overwrite_the_active_serving_database(tmp_path):
    root = tmp_path / "workspace"
    manifest = run_pipeline(root, customers=100, seed=2)
    client = TestClient(create_app(root))
    with read_connection(root) as conn:
        before = [tuple(row) for row in conn.execute("SELECT * FROM predictions ORDER BY 1,2,3")]
    assert client.get("/ready").status_code == 200

    result = cli_generate(root, root / "artifacts/serving.sqlite")

    assert result.returncode != 0
    assert client.get("/ready").status_code == 200
    with read_connection(root) as conn:
        assert active_manifest(conn) == manifest
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM predictions ORDER BY 1,2,3")
        ] == before


def test_generation_cannot_modify_or_add_files_in_immutable_source_release(tmp_path):
    root = tmp_path / "workspace"
    source = tmp_path / "input.jsonl"
    generate_events(source, customers=50, seed=5)
    manifest = ingest_event_source(source, root, "sample", DEFAULT_AS_OF)
    release = root / "data/events" / manifest["source_release_id"]
    events = release / "events.jsonl"
    manifest_path = release / "manifest.json"
    old_events = events.read_bytes()
    old_manifest = manifest_path.read_bytes()
    extra = release / "unexpected.jsonl"

    assert cli_generate(root, events, seed=6).returncode != 0
    assert cli_generate(root, extra, seed=6).returncode != 0

    assert events.read_bytes() == old_events
    assert manifest_path.read_bytes() == old_manifest
    assert not extra.exists()


def test_conflicting_existing_output_is_not_overwritten(tmp_path):
    output = tmp_path / "owner-file.jsonl"
    original = b"previous source bytes that must be preserved\n"
    output.write_bytes(original)

    result = cli_generate(tmp_path / "workspace", output)

    assert result.returncode != 0
    assert output.read_bytes() == original


@pytest.mark.parametrize("target_exists", [True, False])
def test_generation_does_not_follow_output_symlinks(tmp_path, target_exists):
    target = tmp_path / "owner-target.jsonl"
    if target_exists:
        target.write_bytes(b"owner data\n")
    output = tmp_path / "link.jsonl"
    output.symlink_to(target)

    result = cli_generate(tmp_path / "workspace", output)

    assert result.returncode != 0
    assert output.is_symlink()
    if target_exists:
        assert target.read_bytes() == b"owner data\n"
    else:
        assert not target.exists()


def test_exact_generation_replay_to_ordinary_output_is_idempotent(tmp_path):
    root = tmp_path / "workspace"
    output = tmp_path / "generated.jsonl"

    first = cli_generate(root, output, seed=91)
    assert first.returncode == 0, first.stderr
    original = output.read_bytes()
    second = cli_generate(root, output, seed=91)

    assert second.returncode == 0, second.stderr
    assert output.read_bytes() == original


def test_failed_generation_does_not_leave_partial_output(tmp_path, monkeypatch):
    output = tmp_path / "generated.jsonl"
    original_dump = Event.model_dump_json
    calls = 0

    def fail_after_first_event(event, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected output failure")
        return original_dump(event, *args, **kwargs)

    monkeypatch.setattr(Event, "model_dump_json", fail_after_first_event)

    with pytest.raises((OSError, ValueError, RuntimeError)):
        generate_events(output, customers=50)
    assert calls == 2
    assert not output.exists()
