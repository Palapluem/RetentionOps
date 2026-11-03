"""Credential-free synthetic vertical slice, with immutable replayable artifacts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import platform
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import joblib

from .data import (
    DEFAULT_AS_OF,
    FEATURES,
    SEED,
    canonical_hash,
    generate_snapshots,
    ingest_snapshots,
    sha256_file,
)
from .runs import tracked_run
from .storage import publish
from .training import train_baseline


def implementation_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_pipeline(
    root: Path, customers: int = 650, seed: int = SEED, as_of: date = DEFAULT_AS_OF
) -> dict:
    root = root.resolve()
    staging_root = root / "data" / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        source = Path(staging) / "snapshots.csv"
        generate_snapshots(source, customers, seed)
        records, source_manifest = ingest_snapshots(source, root, as_of)
    return fit_and_publish(root, records, source_manifest, seed, as_of)


def run_event_pipeline(
    root: Path, customers: int = 650, seed: int = SEED, as_of: date = DEFAULT_AS_OF
) -> dict:
    from .events import prepare_event_dataset

    root = root.resolve()
    with tracked_run(root, "events") as run_id:
        records, source = prepare_event_dataset(root, customers, seed, as_of)
        return fit_and_publish(root, records, source, seed, as_of, run_id=run_id)


def fit_and_publish(
    root: Path, records: list, source_manifest: dict, seed: int, as_of: date, run_id=None
):
    packages = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "scikit-learn", "joblib", "pydantic", "fastapi", "polars")
    }
    identity = {
        "dataset_sha256": source_manifest["dataset_sha256"],
        "source_manifest_sha256": canonical_hash(source_manifest),
        "implementation_sha256": implementation_hash(),
        "feature_schema_sha256": canonical_hash({"features": FEATURES, "schema": 1}),
        "packages": packages,
        "python": platform.python_version(),
        "runtime": {"system": platform.system(), "machine": platform.machine()},
        "evaluation_freeze": str(as_of),
        "config": {"seed": seed, "C": 1.0, "max_iter": 500, "protocol": "temporal-v1"},
    }
    version = "synthetic-logreg-" + canonical_hash(identity)
    model, protocol, test, probabilities = train_baseline(records, seed)
    model_root = root / "artifacts" / "models"
    model_root.mkdir(parents=True, exist_ok=True)
    release = model_root / version
    if release.exists():
        manifest = json.loads((release / "manifest.json").read_text())
        reproduced = io.BytesIO()
        joblib.dump(model, reproduced)
        if (
            manifest["identity"] != identity
            or sha256_file(release / "model.joblib") != manifest["model_sha256"]
            or hashlib.sha256(reproduced.getvalue()).hexdigest() != manifest["model_sha256"]
        ):
            raise ValueError("Corrupt immutable model release or non-reproducible training")
    else:
        with tempfile.TemporaryDirectory(dir=model_root, prefix=".staging-") as staging:
            staged = Path(staging) / "release"
            staged.mkdir()
            joblib.dump(model, staged / "model.joblib")
            manifest = {
                "model_version": version,
                "identity": identity,
                "source": source_manifest,
                "model_sha256": sha256_file(staged / "model.joblib"),
                "source_type": "SYNTHETIC",
                "not_real_world_performance": True,
                "feature_origin": source_manifest.get(
                    "feature_origin", "Simulated snapshots; not event-derived aggregates"
                ),
                "features": list(FEATURES),
                "label_horizon_days": 30,
                "trained_at": datetime.now(UTC).isoformat(),
                "evaluation_freeze": str(as_of),
                "limitations": [
                    "Synthetic historical holdout, not prospective live inference",
                    "Simulated labels are not the KKBox subscription-renewal definition",
                    "Repeated customers across cohorts; not unseen-customer evaluation",
                    "Predictive probabilities do not measure campaign uplift",
                ],
                **protocol,
            }
            (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            staged.rename(release)
    scores = [
        (version, r.customer_id, str(r.as_of_date), float(p))
        for r, p in zip(test, probabilities, strict=True)
    ]
    publish(root, manifest, scores, snapshots=records, run_id=run_id)
    return manifest
