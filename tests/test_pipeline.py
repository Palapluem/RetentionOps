import json
import sqlite3
from datetime import date

import joblib
import numpy as np
import pytest

from retentionops.data import FEATURES, read_snapshots
from retentionops.pipeline import run_pipeline
from retentionops.storage import active_manifest, publish, read_connection
from retentionops.training import evaluate, matrix, temporal_split


def test_split_chronology_and_missing_cohort(csv_path):
    rows = read_snapshots(csv_path)
    split = temporal_split(rows)
    assert [len(split[k]) for k in ("train", "validation", "test")] == [200, 100, 100]
    for older, newer in (("train", "validation"), ("validation", "test")):
        assert max(r.label_available_at for r in split[older]) <= min(
            r.as_of_date for r in split[newer]
        )
    with pytest.raises(ValueError, match="four documented"):
        temporal_split([r for r in rows if r.as_of_date.month != 9])


def test_split_rejects_unavailable_training_labels(csv_path):
    rows = read_snapshots(csv_path)
    # model_copy intentionally bypasses field validation to exercise the split gate independently.
    rows[1] = rows[1].model_copy(update={"label_available_at": date(2026, 9, 1)})
    with pytest.raises(ValueError, match="embargo"):
        temporal_split(rows)


def test_one_class_is_explained(csv_path):
    rows = [r.model_copy(update={"churn_30d": 0}) for r in read_snapshots(csv_path)]
    with pytest.raises(ValueError, match="Both target classes"):
        temporal_split(rows)


def test_known_ranking_and_calibration():
    labels = np.array([1, 0, 1, 0])
    metrics = evaluate(labels, np.array([0.9, 0.1, 0.8, 0.2]))
    assert metrics["average_precision"] == 1
    assert metrics["recall_at_10pct"] == 0.5
    assert metrics["precision_at_10pct"] == 1
    assert sum(bin_["count"] for bin_ in metrics["calibration"]) == 4


def test_e2e_replay_and_artifact_predictions(publication):
    root, first = publication
    second = run_pipeline(root, customers=150)
    assert first == second
    assert first["cohorts"]["train"]["rows"] == 300
    assert first["cohorts"]["validation"]["rows"] == 150
    assert first["customer_overlap_train_test"] == 150
    release = root / "artifacts/models" / first["model_version"]
    # Load only a model created by this test in a private temporary directory.
    model = joblib.load(release / "model.joblib")
    source = next((root / "data/raw").glob("*/snapshots.csv"))
    rows = temporal_split(read_snapshots(source))
    train_x, _ = matrix(rows["train"])
    test_x, _ = matrix(rows["test"])
    np.testing.assert_allclose(model.named_steps["standardize"].mean_, train_x.mean(axis=0))
    expected = model.predict_proba(test_x)[:, 1]
    with read_connection(root) as conn:
        actual = conn.execute(
            "SELECT churn_probability FROM predictions ORDER BY customer_id"
        ).fetchall()
    np.testing.assert_allclose([r[0] for r in actual], expected, rtol=1e-12)
    assert len(actual) == 150
    assert model.n_features_in_ == len(FEATURES)


def test_different_sources_are_isolated(publication):
    root, first = publication
    second = run_pipeline(root, customers=200)
    assert first["model_version"] != second["model_version"]
    with read_connection(root) as conn:
        assert active_manifest(conn)["model_version"] == second["model_version"]
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 350
    assert len(list((root / "data/raw").iterdir())) == 2


def test_invalid_pipeline_preserves_active_release(publication):
    root, first = publication
    with pytest.raises(ValueError, match="Immature label"):
        run_pipeline(root, customers=200, as_of=date(2026, 10, 1))
    with read_connection(root) as conn:
        assert active_manifest(conn) == first


def test_failed_transaction_rolls_back(publication):
    root, first = publication
    invalid = dict(first, model_version="invalid-test-release")
    scores = [(invalid["model_version"], f"SYN-{i:05d}", "2026-09-30", 0.2) for i in range(150)]
    scores[-1] = (*scores[-1][:3], 2.0)
    with pytest.raises(sqlite3.IntegrityError):
        publish(root, invalid, scores)
    with read_connection(root) as conn:
        assert active_manifest(conn) == first
        assert conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 150


def test_model_corruption_preserves_active_release(publication):
    root, first = publication
    model = root / "artifacts/models" / first["model_version"] / "model.joblib"
    model.write_bytes(b"broken")
    with pytest.raises(ValueError, match="Corrupt immutable model"):
        run_pipeline(root, customers=150)
    with read_connection(root) as conn:
        assert active_manifest(conn) == first


def test_manifest_has_reproducibility_identity(publication):
    root, manifest = publication
    assert manifest["identity"]["packages"]["scikit-learn"]
    assert len(manifest["model_sha256"]) == 64
    assert manifest["source"]["rights"].startswith("Project-generated")
    assert manifest["not_real_world_performance"] is True
    json.dumps(manifest, allow_nan=False)


def test_reproducible_independent_roots(tmp_path):
    first = run_pipeline(tmp_path / "a", customers=150)
    second = run_pipeline(tmp_path / "b", customers=150)
    assert first["model_version"] == second["model_version"]
    assert first["model_sha256"] == second["model_sha256"]
    assert first["metrics"] == second["metrics"]


def test_replay_can_restore_previous_active_release(publication):
    root, first = publication
    run_pipeline(root, customers=200)
    restored = run_pipeline(root, customers=150)
    assert restored == first
    with read_connection(root) as conn:
        assert active_manifest(conn)["model_version"] == first["model_version"]


def test_source_count_mismatch_preserves_active_release(publication):
    root, first = publication
    with pytest.raises(ValueError, match="reconciliation"):
        publish(root, first, [])
    with read_connection(root) as conn:
        assert active_manifest(conn) == first
