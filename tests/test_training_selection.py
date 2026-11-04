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
    changed_validation_labels = [
        row.model_copy(update={"churn_30d": 1 - row.churn_30d})
        if row.as_of_date == CUTOFFS[2]
        else row
        for row in records
    ]

    _, first_protocol, _, first_scores = train_selected(records, seed=342)
    _, second_protocol, _, second_scores = train_selected(changed_test_labels, seed=342)
    _, changed_validation_protocol, _, _ = train_selected(changed_validation_labels, seed=342)

    candidates = first_protocol["selection"]["candidates"]
    best_validation_ap = max(row["average_precision"] for row in candidates)
    first_best_candidate = next(
        row["candidate"] for row in candidates if row["average_precision"] == best_validation_ap
    )
    assert first_protocol["selection"]["selected_candidate"] == first_best_candidate
    assert first_protocol["selection"]["selected_parameters"] == next(
        row["parameters"] for row in candidates if row["candidate"] == first_best_candidate
    )
    assert set(first_protocol["metrics"]["test"]) == {"constant_prior", "selected_model"}
    assert first_protocol["selection"] == second_protocol["selection"]
    assert (
        first_protocol["selection"]["selected_parameters"]
        == second_protocol["selection"]["selected_parameters"]
    )
    assert first_protocol["metrics"]["validation"] == second_protocol["metrics"]["validation"]
    assert first_protocol["selection"] != changed_validation_protocol["selection"]
    changed_candidates = changed_validation_protocol["selection"]["candidates"]
    changed_best = max(changed_candidates, key=lambda row: row["average_precision"])
    assert (
        changed_validation_protocol["selection"]["selected_candidate"] == changed_best["candidate"]
    )
    assert (
        changed_validation_protocol["selection"]["selected_parameters"]
        == changed_best["parameters"]
    )
    np.testing.assert_array_equal(first_scores, second_scores)
    assert (
        first_protocol["metrics"]["test"]["selected_model"]
        != second_protocol["metrics"]["test"]["selected_model"]
    )


def test_selected_model_scores_are_immutable_replayable_and_match_artifact(tmp_path):
    first = run_pipeline(tmp_path, customers=100, seed=2)
    database = tmp_path / "artifacts/serving.sqlite"
    with sqlite3.connect(database) as conn:
        before_replay = conn.execute(
            "SELECT model_version, as_of_date, customer_id, churn_probability "
            "FROM predictions WHERE model_version=? ORDER BY as_of_date, customer_id",
            (first["model_version"],),
        ).fetchall()

    replay = run_pipeline(tmp_path, customers=100, seed=2)
    with sqlite3.connect(database) as conn:
        after_replay = conn.execute(
            "SELECT model_version, as_of_date, customer_id, churn_probability "
            "FROM predictions WHERE model_version=? ORDER BY as_of_date, customer_id",
            (first["model_version"],),
        ).fetchall()

    assert replay == first
    assert after_replay == before_replay
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
    score_keys = [tuple(row[:3]) for row in after_replay]
    assert len(score_keys) == len(set(score_keys)) == first["cohorts"]["test"]["rows"]
    assert {row[0] for row in score_keys} == {first["model_version"]}
    assert {row[1] for row in score_keys} == {first["score_cutoff"]}
    np.testing.assert_allclose([row[0] for row in scores], expected, rtol=1e-12)
