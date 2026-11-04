"""Transactional publication and read-only serving of a single active model release."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
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
"""


def publish(root: Path, manifest: dict, scores: list[tuple]) -> None:
    """Atomically publish a release; allow exact replays and reject conflicting score keys."""
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

        if prior is not None:
            stored_scores = [
                tuple(row)
                for row in conn.execute(
                    "SELECT customer_id, as_of_date, churn_probability FROM predictions "
                    "WHERE model_version=? ORDER BY customer_id, as_of_date",
                    (version,),
                )
            ]
            incoming_scores = sorted(
                [(score[1], score[2], float(score[3])) for score in scores],
                key=lambda score: (score[0], score[1]),
            )
            if not stored_scores or stored_scores != incoming_scores:
                raise ValueError("Refusing to mutate scores for an immutable model release")

        conn.execute("INSERT OR IGNORE INTO releases VALUES (?, ?)", (version, encoded))
        if prior is None:
            conn.executemany("INSERT INTO predictions VALUES (?, ?, ?, ?)", scores)
        conn.execute(
            "INSERT INTO active_release VALUES (1, ?) "
            "ON CONFLICT(slot) DO UPDATE SET model_version=excluded.model_version",
            (version,),
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
