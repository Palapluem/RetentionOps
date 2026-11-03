"""Transactional publication and read-only serving of a single active model release."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    model_version TEXT PRIMARY KEY, manifest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    model_version TEXT NOT NULL REFERENCES releases(model_version),
    customer_id TEXT NOT NULL, as_of_date TEXT NOT NULL,
    churn_probability REAL NOT NULL CHECK(churn_probability BETWEEN 0 AND 1),
    PRIMARY KEY(model_version, customer_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS risk_order
    ON predictions(model_version, churn_probability DESC, customer_id);
CREATE TABLE IF NOT EXISTS active_release (
    slot INTEGER PRIMARY KEY CHECK(slot = 1),
    model_version TEXT NOT NULL REFERENCES releases(model_version)
);
CREATE TABLE IF NOT EXISTS feature_snapshots (
    model_version TEXT NOT NULL REFERENCES releases(model_version),
    customer_id TEXT NOT NULL, as_of_date TEXT NOT NULL, snapshot TEXT NOT NULL,
    PRIMARY KEY(model_version, customer_id, as_of_date)
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, state TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT, model_version TEXT,
    output_rows INTEGER, elapsed_seconds REAL, error_type TEXT
);
"""


def publish(root: Path, manifest: dict, scores: list[tuple], snapshots=None, run_id=None) -> None:
    """Make manifest + scores + pointer visible together, or roll everything back."""
    if len(scores) != manifest["cohorts"]["test"]["rows"]:
        raise ValueError("Score/source reconciliation failed")
    if any(s[0] != manifest["model_version"] or s[2] != manifest["score_cutoff"] for s in scores):
        raise ValueError("Score release/cutoff mismatch")
    path = root / "artifacts" / "serving.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        version = manifest["model_version"]
        encoded = json.dumps(manifest, sort_keys=True)
        prior = conn.execute(
            "SELECT manifest FROM releases WHERE model_version = ?", (version,)
        ).fetchone()
        if prior is not None and prior[0] != encoded:
            raise ValueError("Refusing to mutate an immutable model release")
        conn.execute("INSERT OR IGNORE INTO releases VALUES (?, ?)", (version, encoded))
        conn.execute("DELETE FROM predictions WHERE model_version = ?", (version,))
        conn.executemany("INSERT INTO predictions VALUES (?, ?, ?, ?)", scores)
        if snapshots is not None:
            if len(snapshots) != manifest["source"]["rows"]:
                raise ValueError("Feature/source reconciliation failed")
            feature_keys = {(r.customer_id, str(r.as_of_date)) for r in snapshots}
            score_keys = {(row[1], row[2]) for row in scores}
            if len(feature_keys) != len(snapshots) or not score_keys <= feature_keys:
                raise ValueError("Score/feature key reconciliation failed")
            conn.execute("DELETE FROM feature_snapshots WHERE model_version=?", (version,))
            conn.executemany(
                "INSERT INTO feature_snapshots VALUES (?, ?, ?, ?)",
                [
                    (version, r.customer_id, str(r.as_of_date), r.model_dump_json())
                    for r in snapshots
                ],
            )
        conn.execute(
            "INSERT INTO active_release VALUES (1, ?) "
            "ON CONFLICT(slot) DO UPDATE SET model_version=excluded.model_version",
            (version,),
        )
        if run_id is not None:
            started = conn.execute(
                "SELECT started_at FROM pipeline_runs WHERE run_id=? AND state='running'",
                (run_id,),
            ).fetchone()
            if started is None:
                raise ValueError("Publication requires a running job")
            finished = datetime.now(UTC)
            elapsed = max(0, (finished - datetime.fromisoformat(started[0])).total_seconds())
            conn.execute(
                "UPDATE pipeline_runs SET state='succeeded', finished_at=?, model_version=?, "
                "output_rows=?, elapsed_seconds=? WHERE run_id=?",
                (finished.isoformat(), version, len(scores), elapsed, run_id),
            )


@contextmanager
def read_connection(root: Path):
    path = root / "artifacts" / "serving.sqlite"
    # mode=ro prevents accidentally creating an empty serving DB during a read.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")  # One request sees one consistent active release.
        yield conn
    finally:
        conn.close()


def active_manifest(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT r.manifest FROM releases r JOIN active_release a "
        "ON a.model_version = r.model_version WHERE a.slot = 1"
    ).fetchone()
    if row is None:
        raise ValueError("No active release")
    return json.loads(row[0])
