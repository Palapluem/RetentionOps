"""Train-only model fitting and validation-only selection on temporal cohorts."""

from __future__ import annotations

import math

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import CUTOFFS, FEATURES, Snapshot

LIGHTGBM_GRID = (
    {
        "num_leaves": 3,
        "max_depth": 2,
        "learning_rate": 0.05,
        "n_estimators": 80,
        "min_child_samples": 20,
    },
    {
        "num_leaves": 7,
        "max_depth": 3,
        "learning_rate": 0.05,
        "n_estimators": 100,
        "min_child_samples": 20,
    },
    {
        "num_leaves": 7,
        "max_depth": 3,
        "learning_rate": 0.03,
        "n_estimators": 160,
        "min_child_samples": 40,
    },
)


def temporal_split(records: list[Snapshot]) -> dict[str, list[Snapshot]]:
    if {r.as_of_date for r in records} != set(CUTOFFS):
        raise ValueError("Expected exactly the four documented temporal cohorts")
    cohorts = {
        "train": [r for r in records if r.as_of_date in CUTOFFS[:2]],
        "validation": [r for r in records if r.as_of_date == CUTOFFS[2]],
        "test": [r for r in records if r.as_of_date == CUTOFFS[3]],
    }
    for name, rows in cohorts.items():
        if {r.churn_30d for r in rows} != {0, 1}:
            raise ValueError(f"Both target classes required in {name} cohort")
    for older, newer in (("train", "validation"), ("validation", "test")):
        if max(r.label_available_at for r in cohorts[older]) > min(
            r.as_of_date for r in cohorts[newer]
        ):
            raise ValueError("Temporal embargo failed: labels unavailable at next cutoff")
    return cohorts


def matrix(records: list[Snapshot]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array([[getattr(r, f) for f in FEATURES] for r in records], dtype=float),
        np.array([r.churn_30d for r in records], dtype=int),
    )


def evaluate(labels: np.ndarray, probabilities: np.ndarray) -> dict:
    k = max(1, math.ceil(len(labels) * 0.1))
    # Stable tie resolution uses the deterministic source ordering.
    top = np.argsort(-probabilities, kind="stable")[:k]
    positives = int(labels[top].sum())
    calibration = []
    bins = np.minimum((probabilities * 5).astype(int), 4)
    for index in range(5):
        lower, upper = index / 5, (index + 1) / 5
        mask = bins == index
        if mask.any():
            calibration.append(
                {
                    "lower": round(float(lower), 1),
                    "upper": round(float(upper), 1),
                    "count": int(mask.sum()),
                    "mean_predicted": float(probabilities[mask].mean()),
                    "observed_rate": float(labels[mask].mean()),
                }
            )
    return {
        "average_precision": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier": float(brier_score_loss(labels, probabilities)),
        "precision_at_10pct": positives / k,
        "recall_at_10pct": positives / int(labels.sum()),
        "selected_k": k,
        "rows": len(labels),
        "positives": int(labels.sum()),
        "positive_rate": float(labels.mean()),
        "calibration": calibration,
    }


def train_selected(
    records: list[Snapshot], seed: int
) -> tuple[BaseEstimator, dict, list[Snapshot], np.ndarray]:
    cohorts = temporal_split(records)
    x_train, y_train = matrix(cohorts["train"])
    logistic = Pipeline(
        [
            ("standardize", StandardScaler()),
            ("classifier", LogisticRegression(C=1.0, max_iter=500, random_state=seed)),
        ]
    )
    logistic.fit(x_train, y_train)
    baseline = DummyClassifier(strategy="prior").fit(x_train, y_train)

    x_validation, y_validation = matrix(cohorts["validation"])
    validation_metrics = {
        "logistic_regression": evaluate(y_validation, logistic.predict_proba(x_validation)[:, 1]),
        "constant_prior": evaluate(y_validation, baseline.predict_proba(x_validation)[:, 1]),
    }
    candidate_results = [
        {
            "candidate": "logistic_regression",
            "model_family": "logistic_regression",
            "parameters": {"C": 1.0, "max_iter": 500, "seed": seed},
            "average_precision": validation_metrics["logistic_regression"]["average_precision"],
        }
    ]
    fitted_models: dict[str, BaseEstimator] = {"logistic_regression": logistic}
    for index, grid_parameters in enumerate(LIGHTGBM_GRID, start=1):
        candidate_name = f"lightgbm_{index:03d}"
        parameters = {
            **grid_parameters,
            "objective": "binary",
            "random_state": seed,
            "deterministic": True,
            "force_col_wise": True,
            "n_jobs": 1,
            "verbosity": -1,
        }
        model = LGBMClassifier(**parameters)
        model.fit(x_train, y_train)
        candidate_metrics = evaluate(y_validation, model.predict_proba(x_validation)[:, 1])
        validation_metrics[candidate_name] = candidate_metrics
        candidate_results.append(
            {
                "candidate": candidate_name,
                "model_family": "lightgbm",
                "parameters": parameters,
                "average_precision": candidate_metrics["average_precision"],
            }
        )
        fitted_models[candidate_name] = model

    # Select only on validation average precision. A tie retains the simpler LR candidate;
    # subsequent exact ties retain the earlier, smaller LightGBM grid entry.
    winner = max(
        enumerate(candidate_results),
        key=lambda item: (item[1]["average_precision"], -item[0]),
    )[1]
    selected_name = winner["candidate"]
    model = fitted_models[selected_name]
    selection = {
        "metric": "validation_average_precision",
        "selected_candidate": selected_name,
        "selected_model_family": winner["model_family"],
        "selected_parameters": winner["parameters"],
        "reason": "Highest validation average precision; exact ties prefer Logistic Regression, then grid order",
        "candidates": candidate_results,
    }

    test_x, test_y = matrix(cohorts["test"])
    selected_probabilities = model.predict_proba(test_x)[:, 1]
    test_metrics = {"constant_prior": evaluate(test_y, baseline.predict_proba(test_x)[:, 1])}
    if selected_name == "logistic_regression":
        selected_test_metrics = evaluate(test_y, selected_probabilities)
    else:
        test_metrics["logistic_regression"] = evaluate(test_y, logistic.predict_proba(test_x)[:, 1])
        selected_test_metrics = evaluate(test_y, selected_probabilities)
    test_metrics["selected_model"] = selected_test_metrics
    metrics = {
        "validation": validation_metrics,
        "test": test_metrics,
    }
    protocol = {
        "metrics": metrics,
        "selection": selection,
        "cohorts": {
            name: {
                "rows": len(rows),
                "cutoffs": sorted({str(r.as_of_date) for r in rows}),
                "max_label_available_at": str(max(r.label_available_at for r in rows)),
            }
            for name, rows in cohorts.items()
        },
        "customer_overlap_train_test": len(
            {r.customer_id for r in cohorts["train"]} & {r.customer_id for r in cohorts["test"]}
        ),
        "score_cutoff": str(CUTOFFS[3]),
    }
    return model, protocol, cohorts["test"], selected_probabilities
