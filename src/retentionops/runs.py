"""Record stage attempts; model success commits with the score publication."""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from .storage import SCHEMA


def complete_source_stage(root, run_id, output_rows):
    """Record successful generation/intake after its output is complete and validated."""
    with sqlite3.connect(root / "artifacts/serving.sqlite", timeout=30) as conn:
        started = conn.execute(
            "SELECT started_at FROM pipeline_runs WHERE run_id=? AND state='running'",
            (run_id,),
        ).fetchone()
        if started is None:
            raise ValueError("Source completion requires a running stage")
        finished = datetime.now(UTC)
        conn.execute(
            "UPDATE pipeline_runs SET state='succeeded',finished_at=?,output_rows=?, "
            "elapsed_seconds=? WHERE run_id=?",
            (
                finished.isoformat(),
                output_rows,
                max(0, (finished - datetime.fromisoformat(started[0])).total_seconds()),
                run_id,
            ),
        )


@contextmanager
def tracked_run(root, mode):
    path = root / "artifacts/serving.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid4())
    started = datetime.now(UTC)
    with sqlite3.connect(path, timeout=30) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO pipeline_runs(run_id,mode,state,started_at) VALUES(?,?,'running',?)",
            (run_id, mode, started.isoformat()),
        )
    try:
        yield run_id
    except Exception as exc:
        finished = datetime.now(UTC)
        try:
            with sqlite3.connect(path, timeout=30) as conn:
                conn.execute(
                    "UPDATE pipeline_runs SET state='failed',finished_at=?,error_type=?, "
                    "elapsed_seconds=? WHERE run_id=? AND state='running'",
                    (
                        finished.isoformat(),
                        type(exc).__name__,
                        max(0, (finished - started).total_seconds()),
                        run_id,
                    ),
                )
        except sqlite3.Error:
            logging.exception("Could not persist failed job status")
        raise
