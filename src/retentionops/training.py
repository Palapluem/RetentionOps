"""Fixed baseline protocol: train-only preprocessing, disjoint temporal cohorts."""

from __future__ import annotations

import math

import numpy as np
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


def train_baseline(records: list[Snapshot], seed: int) -> tuple[Pipeline, dict, list, np.ndarray]:
    cohorts = temporal_split(records)
    x_train, y_train = matrix(cohorts["train"])
    model = Pipeline(
        [
            ("standardize", StandardScaler()),
            ("classifier", LogisticRegression(C=1.0, max_iter=500, random_state=seed)),
        ]
    )
    model.fit(x_train, y_train)
    baseline = DummyClassifier(strategy="prior").fit(x_train, y_train)
    metrics = {}
    for name in ("validation", "test"):
        x, y = matrix(cohorts[name])
        metrics[name] = {
            "logistic_regression": evaluate(y, model.predict_proba(x)[:, 1]),
            "constant_prior": evaluate(y, baseline.predict_proba(x)[:, 1]),
        }
    test_x, _ = matrix(cohorts["test"])
    protocol = {
        "metrics": metrics,
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
        "selection": "Fixed Logistic Regression baseline; no hyperparameter tuning or refit",
        "score_cutoff": str(CUTOFFS[3]),
    }
    return model, protocol, cohorts["test"], model.predict_proba(test_x)[:, 1]
