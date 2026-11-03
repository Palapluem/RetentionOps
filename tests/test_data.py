import csv
import json
from datetime import date

import pytest

from retentionops.data import (
    FEATURES,
    generate_snapshots,
    ingest_snapshots,
    read_snapshots,
)


def rewrite(path, mutate):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    mutate(rows)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_deterministic_source(csv_path):
    before = csv_path.read_bytes()
    generate_snapshots(csv_path, customers=100)
    assert csv_path.read_bytes() == before
    assert len(read_snapshots(csv_path)) == 400


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_type", "PRIVATE"),
        ("customer_id", "person@example.com"),
        ("active_days_30d", "31"),
        ("active_days_30d", "1.5"),
        ("payment_failures_90d", "-1"),
        ("tenure_months", "0"),
        ("monthly_fee", "NaN"),
        ("monthly_fee", "inf"),
        ("monthly_fee", "-10"),
        ("auto_renew", "2"),
        ("churn_30d", "-1"),
        ("monthly_fee", ""),
        ("as_of_date", "invalid"),
        ("feature_max_event_at", "2026-07-01"),
        ("source_max_available_at", "2026-07-01"),
        ("label_available_at", "2026-06-29"),
    ],
)
def test_invalid_input_rejected(csv_path, field, value):
    rewrite(csv_path, lambda rows: rows[0].update({field: value}))
    with pytest.raises(ValueError, match="Invalid snapshot"):
        read_snapshots(csv_path)


def test_maturity_is_runtime_freeze(csv_path):
    with pytest.raises(ValueError, match="Immature label"):
        read_snapshots(csv_path, as_of=date(2026, 10, 1))
    assert len(read_snapshots(csv_path, as_of=date(2026, 10, 30))) == 400


def test_duplicate_grain_rejected(csv_path):
    rewrite(csv_path, lambda rows: rows.append(rows[0].copy()))
    with pytest.raises(ValueError, match="Duplicate grain"):
        read_snapshots(csv_path)


@pytest.mark.parametrize("content", ["", "customer_id,as_of_date\n", "a,a\n1,1\n"])
def test_schema_rejected(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(ValueError, match="schema"):
        read_snapshots(path)


def test_empty_body_rejected(csv_path):
    csv_path.write_text(csv_path.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="Empty"):
        read_snapshots(csv_path)


def test_future_column_rejected(csv_path):
    rewrite(csv_path, lambda rows: [row.update({"future_cancellation": "1"}) for row in rows])
    with pytest.raises(ValueError, match="schema"):
        read_snapshots(csv_path)


def test_allowlist_excludes_targets_and_identifiers():
    assert not {"churn_30d", "label_available_at", "customer_id", "as_of_date"} & set(FEATURES)


def test_source_replay_and_corruption_detection(csv_path, tmp_path):
    _, first = ingest_snapshots(csv_path, tmp_path, date(2026, 11, 3))
    _, second = ingest_snapshots(csv_path, tmp_path, date(2026, 11, 3))
    assert first == second
    releases = list((tmp_path / "data/raw").iterdir())
    assert len(releases) == 1
    assert json.loads((releases[0] / "manifest.json").read_text())["rows"] == 400
    (releases[0] / "snapshots.csv").write_text("corruption")
    with pytest.raises(ValueError, match="Corrupt immutable source"):
        ingest_snapshots(csv_path, tmp_path, date(2026, 11, 3))
