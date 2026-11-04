import sqlite3

import joblib
import numpy as np

from retentionops.data import CUTOFFS, generate_snapshots, read_snapshots
from retentionops.pipeline import run_pipeline
from retentionops.training import matrix, temporal_split, train_selected


def test_holdout_labels_do_not_change_validation_selected_model(tmp_path):
    csv_path = tmp_path / "snapshots.csv"
    generate_snapshots(csv_path, customers=650, seed=342)
    records = read_snapshots(csv_path)
    changed_test_labels = [
        row.model_copy(update={"churn_30d": 1 - row.churn_30d})
        if row.as_of_date == CUTOFFS[3]
        else row
        for row in records
    ]

    _, first_protocol, _, first_scores = train_selected(records, seed=342)
    _, second_protocol, _, second_scores = train_selected(changed_test_labels, seed=342)

    candidates = first_protocol["selection"]["candidates"]
    best_validation_ap = max(row["average_precision"] for row in candidates)
    first_best_candidate = next(
        row["candidate"] for row in candidates if row["average_precision"] == best_validation_ap
    )
    assert first_protocol["selection"]["selected_candidate"] == first_best_candidate
    assert first_protocol["selection"]["selected_model_family"] == "logistic_regression"
    assert set(first_protocol["metrics"]["test"]) == {"constant_prior", "selected_model"}
    assert first_protocol["selection"] == second_protocol["selection"]
    assert first_protocol["metrics"]["validation"] == second_protocol["metrics"]["validation"]
    np.testing.assert_array_equal(first_scores, second_scores)


def test_selected_model_scores_are_immutable_replayable_and_match_artifact(tmp_path):
    first = run_pipeline(tmp_path, customers=100, seed=2)
    replay = run_pipeline(tmp_path, customers=100, seed=2)

    assert replay == first
    assert first["selection"]["selected_model_family"] == "lightgbm"
    assert set(first["metrics"]["test"]) == {
        "constant_prior",
        "logistic_regression",
        "selected_model",
    }
    assert first["identity"]["packages"]["lightgbm"]
    assert (
        first["identity"]["config"]["selected_parameters"]
        == first["selection"]["selected_parameters"]
    )
    release = tmp_path / "artifacts/models" / first["model_version"]
    model = joblib.load(release / "model.joblib")
    source = next((tmp_path / "data/raw").glob("*/snapshots.csv"))
    rows = temporal_split(read_snapshots(source))
    test_x, _ = matrix(rows["test"])
    expected = model.predict_proba(test_x)[:, 1]

    with sqlite3.connect(tmp_path / "artifacts/serving.sqlite") as conn:
        scores = conn.execute(
            "SELECT churn_probability FROM predictions WHERE model_version=? "
            "ORDER BY customer_id, as_of_date",
            (first["model_version"],),
        ).fetchall()
        count, distinct_keys = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT customer_id || '/' || as_of_date) "
            "FROM predictions WHERE model_version=?",
            (first["model_version"],),
        ).fetchone()

    assert count == distinct_keys == first["cohorts"]["test"]["rows"]
    np.testing.assert_allclose([row[0] for row in scores], expected, rtol=1e-12)
