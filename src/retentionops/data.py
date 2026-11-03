"""Synthetic snapshot generation and strict, point-in-time intake contracts.

Snapshots are simulated features, not aggregates proven against raw events.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

FEATURES = ("active_days_30d", "payment_failures_90d", "tenure_months", "monthly_fee", "auto_renew")
CUTOFFS = (date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30))
LABEL_HORIZON_DAYS = 30
DEFAULT_AS_OF = date(2026, 11, 3)
SEED = 342


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    customer_id: Annotated[str, Field(pattern=r"^SYN-[0-9]{5,7}$")]
    as_of_date: date
    active_days_30d: Annotated[int, Field(ge=0, le=30)]
    payment_failures_90d: Annotated[int, Field(ge=0)]
    tenure_months: Annotated[int, Field(ge=1, le=1200)]
    monthly_fee: Annotated[float, Field(gt=0, le=10000)]
    auto_renew: Literal[0, 1]
    feature_max_event_at: date
    source_max_available_at: date
    churn_30d: Literal[0, 1]
    label_available_at: date
    source_type: Literal["SYNTHETIC"]

    @model_validator(mode="after")
    def temporal_contract(self) -> Snapshot:
        if not self.feature_max_event_at <= self.source_max_available_at <= self.as_of_date:
            raise ValueError("Future feature event or availability beyond cutoff")
        if (self.label_available_at - self.as_of_date).days < LABEL_HORIZON_DAYS:
            raise ValueError("Invalid label horizon")
        return self


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def generate_snapshots(path: Path, customers: int = 650, seed: int = SEED) -> int:
    if not 50 <= customers <= 100000:
        raise ValueError("customers must be between 50 and 100000")
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Snapshot.model_fields))
        writer.writeheader()
        for n in range(customers):
            auto_renew = int(rng.random() < 0.65)
            fee = rng.choice([99, 149, 199, 249, 299])
            base_tenure = rng.randint(1, 48)
            bias = rng.uniform(-0.6, 0.6)
            for j, cutoff in enumerate(CUTOFFS):
                activity = max(0, min(30, int(rng.gauss(15 + 5 * auto_renew, 7))))
                failures = rng.choices([0, 1, 2, 3], weights=[75, 17, 6, 2])[0]
                tenure = base_tenure + j
                logit = (
                    0.1
                    - 0.11 * activity
                    + 0.85 * failures
                    - 0.018 * tenure
                    - 0.8 * auto_renew
                    + bias
                )
                writer.writerow(
                    {
                        "customer_id": f"SYN-{n:05d}",
                        "as_of_date": cutoff,
                        "active_days_30d": activity,
                        "payment_failures_90d": failures,
                        "tenure_months": tenure,
                        "monthly_fee": fee,
                        "auto_renew": auto_renew,
                        "feature_max_event_at": cutoff - timedelta(days=1),
                        "source_max_available_at": cutoff,
                        "churn_30d": int(rng.random() < 1 / (1 + math.exp(-logit))),
                        "label_available_at": cutoff + timedelta(days=LABEL_HORIZON_DAYS),
                        "source_type": "SYNTHETIC",
                    }
                )
    return customers * len(CUTOFFS)


def read_snapshots(path: Path, as_of: date = DEFAULT_AS_OF) -> list[Snapshot]:
    records = []
    keys = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or set(headers) != set(Snapshot.model_fields):
            raise ValueError("CSV schema must exactly match snapshot contract")
        for line, row in enumerate(reader, start=2):
            # CSV has string fields; binary values are parsed explicitly before Literal validation.
            try:
                for field in ("churn_30d", "auto_renew"):
                    if row[field] not in ("0", "1"):
                        raise ValueError(f"Invalid binary field: {field}")
                    row[field] = int(row[field])
                record = Snapshot.model_validate(row)
            except (ValidationError, ValueError, TypeError) as exc:
                raise ValueError(f"Invalid snapshot at CSV line {line}: {exc}") from exc
            key = (record.customer_id, record.as_of_date)
            if key in keys:
                raise ValueError(f"Duplicate grain at CSV line {line}")
            if record.label_available_at > as_of:
                raise ValueError(f"Immature label at CSV line {line}")
            keys.add(key)
            records.append(record)
    if not records:
        raise ValueError("Empty snapshot file")
    return records


def ingest_snapshots(source: Path, root: Path, as_of: date) -> tuple[list[Snapshot], dict]:
    """Validate first, then publish one immutable content-addressed local source release."""
    records = read_snapshots(source, as_of)
    checksum = sha256_file(source)
    manifest = {
        "source_release_id": f"synthetic-{checksum}",
        "dataset_sha256": checksum,
        "schema_version": "synthetic-snapshot-v1",
        "source_type": "SYNTHETIC",
        "rights": "Project-generated synthetic snapshots; no external customer dataset",
        "rows": len(records),
        "cutoffs": sorted({str(r.as_of_date) for r in records}),
    }
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    release = raw / manifest["source_release_id"]
    if release.exists():
        if (
            sha256_file(release / "snapshots.csv") != checksum
            or json.loads((release / "manifest.json").read_text()) != manifest
        ):
            raise ValueError("Corrupt immutable source release; restore from original source")
    else:
        with tempfile.TemporaryDirectory(dir=raw, prefix=".staging-") as staging:
            staged = Path(staging) / "release"
            staged.mkdir()
            (staged / "snapshots.csv").write_bytes(source.read_bytes())
            (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            staged.rename(release)
    return records, manifest
