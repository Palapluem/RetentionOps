"""Record catchable interruptions without changing the published release."""

import select
import signal
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from retentionops import cli, pipeline, storage
from retentionops.api import create_app


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_interrupted_model_run_preserves_published_release(
    publication, monkeypatch, exception_type
):
    root, manifest = publication
    client = TestClient(create_app(root))
    before = client.get("/api/v1/risk?limit=5").json()
    interruption = exception_type("interrupted test")

    def interrupt_source(*args, **kwargs):
        raise interruption

    monkeypatch.setattr(pipeline, "generate_snapshots", interrupt_source)
    with pytest.raises(exception_type) as raised:
        pipeline.run_pipeline(root, customers=100, seed=2)
    assert raised.value is interruption

    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert client.get("/api/v1/risk?limit=5").json() == before
    attempt = status["runs"][0]
    assert attempt["mode"] == "snapshots"
    assert attempt["state"] == "failed"
    assert attempt["error_type"] == exception_type.__name__
    assert attempt["finished_at"] is not None
    assert attempt["elapsed_seconds"] >= 0
    assert attempt["model_version"] is None


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_interrupted_source_generation_records_failure(publication, monkeypatch, exception_type):
    root, manifest = publication
    output = root / "incoming.jsonl"
    interruption = exception_type("interrupted source")

    def interrupt_generation(*args, **kwargs):
        raise interruption

    monkeypatch.setattr(cli, "generate_events", interrupt_generation)
    monkeypatch.setattr(
        sys,
        "argv",
        ["retentionops", "generate-events", "--root", str(root), "--output", str(output)],
    )
    with pytest.raises(exception_type) as raised:
        cli.main()
    assert raised.value is interruption
    assert not output.exists()

    client = TestClient(create_app(root))
    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert status["runs"][0]["mode"] == "source-generation"
    assert status["runs"][0]["state"] == "failed"
    assert status["runs"][0]["error_type"] == exception_type.__name__


def test_interrupt_during_publication_rolls_back_partial_database_writes(publication, monkeypatch):
    root, manifest = publication
    client = TestClient(create_app(root))
    before_risk = client.get("/api/v1/risk?limit=5").json()
    with storage.read_connection(root) as conn:
        before_counts = tuple(
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("releases", "predictions", "feature_snapshots")
        )
    interruption = KeyboardInterrupt("during publication")
    original_connect = sqlite3.connect
    original_publish = pipeline.publish

    class InterruptedConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith("INSERT INTO active_release"):
                raise interruption
            return result

    def interrupted_connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=InterruptedConnection)

    def publish_with_interruption(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr(storage.sqlite3, "connect", interrupted_connect)
            return original_publish(*args, **kwargs)

    monkeypatch.setattr(pipeline, "publish", publish_with_interruption)
    with pytest.raises(KeyboardInterrupt) as raised:
        pipeline.run_pipeline(root, customers=100, seed=2)
    assert raised.value is interruption

    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert status["runs"][0]["state"] == "failed"
    assert status["runs"][0]["error_type"] == "KeyboardInterrupt"
    assert client.get("/api/v1/risk?limit=5").json() == before_risk
    with storage.read_connection(root) as conn:
        after_counts = tuple(
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("releases", "predictions", "feature_snapshots")
        )
    assert after_counts == before_counts


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_interruption_after_publication_does_not_rewrite_success(
    publication, monkeypatch, exception_type
):
    root, old_manifest = publication
    original_publish = pipeline.fit_and_publish
    published = {}
    interruption = exception_type("after publication")

    def interrupt_after_publish(*args, **kwargs):
        published.update(original_publish(*args, **kwargs))
        raise interruption

    monkeypatch.setattr(pipeline, "fit_and_publish", interrupt_after_publish)
    with pytest.raises(exception_type) as raised:
        pipeline.run_pipeline(root, customers=100, seed=2)
    assert raised.value is interruption
    assert published["model_version"] != old_manifest["model_version"]

    client = TestClient(create_app(root))
    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == published["model_version"]
    assert status["runs"][0]["state"] == "succeeded"
    assert status["runs"][0]["model_version"] == published["model_version"]
    assert status["runs"][0]["error_type"] is None


def test_sigkill_leaves_last_recorded_running_without_losing_active_release(publication):
    root, manifest = publication
    script = """
import sys
import time
from pathlib import Path
from retentionops.runs import tracked_run
with tracked_run(Path(sys.argv[1]), "source-generation") as run_id:
    print(run_id, flush=True)
    time.sleep(120)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root)], stdout=subprocess.PIPE, text=True
    )
    try:
        readable, _, _ = select.select([process.stdout], [], [], 15)
        assert readable, "child did not record its run in time"
        run_id = process.stdout.readline().strip()
        assert run_id
        process.kill()
        assert process.wait(timeout=15) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        process.stdout.close()

    client = TestClient(create_app(root))
    status = client.get("/api/v1/system-status").json()
    assert client.get("/ready").status_code == 200
    assert status["active_release"]["model_version"] == manifest["model_version"]
    assert status["runs"][0]["run_id"] == run_id
    assert status["runs"][0]["state"] == "running"
    assert status["runs"][0]["finished_at"] is None
    assert status["runs"][0]["error_type"] is None
