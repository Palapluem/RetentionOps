"""Day-grain subscription events, bitemporal corrections and point-in-time aggregates."""

from __future__ import annotations

import csv
import json
import math
import random
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .data import CUTOFFS, LABEL_HORIZON_DAYS, SEED, Snapshot, sha256_file


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    event_id: Annotated[str, Field(pattern=r"^SYN-[A-Za-z0-9-]+$")]
    revision: Annotated[int, Field(ge=1)] = 1
    customer_id: Annotated[str, Field(pattern=r"^SYN-[0-9]{5,7}$")]
    kind: Literal["subscription", "activity", "payment_failed", "renewal", "cancellation"]
    occurred_at: date
    available_at: date
    deleted: bool = False
    expiry_date: date | None = None
    started_at: date | None = None
    monthly_fee: Annotated[float, Field(gt=0, le=10000)] | None = None
    auto_renew: Literal[0, 1] | None = None
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"

    @model_validator(mode="after")
    def payload(self) -> Event:
        if self.occurred_at > self.available_at:
            raise ValueError("Event cannot be available before occurrence")
        if self.kind == "subscription":
            if None in (self.expiry_date, self.started_at, self.monthly_fee, self.auto_renew):
                raise ValueError("Subscription requires expiry/start/fee/renewal status")
            if not self.started_at <= self.occurred_at < self.expiry_date:
                raise ValueError("Invalid subscription date order")
        elif self.kind in ("renewal", "cancellation"):
            if self.expiry_date is None:
                raise ValueError("Outcome must identify its subscription expiry")
            if any(v is not None for v in (self.started_at, self.monthly_fee, self.auto_renew)):
                raise ValueError("Outcome cannot carry plan feature fields")
        elif any(
            v is not None
            for v in (self.expiry_date, self.started_at, self.monthly_fee, self.auto_renew)
        ):
            raise ValueError("Activity/payment event cannot carry subscription fields")
        return self


def validate_events(events: list[Event], complete_through: date) -> None:
    if not events:
        raise ValueError("Empty event source")
    versions = defaultdict(list)
    for event in events:
        if event.available_at > complete_through:
            raise ValueError("Event availability exceeds source completeness watermark")
        versions[event.event_id].append(event)
    for rows in versions.values():
        rows.sort(key=lambda e: e.revision)
        if len({e.revision for e in rows}) != len(rows):
            raise ValueError("Duplicate event revision")
        if len({(e.customer_id, e.kind) for e in rows}) != 1:
            raise ValueError("Logical event identity changed across revisions")
        if any(a.available_at > b.available_at for a, b in pairwise(rows)):
            raise ValueError("Revision availability must be monotonic")


def visible_versions(events: list[Event], cutoff: date) -> list[Event]:
    latest = {}
    for event in events:
        prior = latest.get(event.event_id)
        if event.available_at <= cutoff and (prior is None or event.revision > prior.revision):
            latest[event.event_id] = event
    return list(latest.values())


def build_features(
    events: list[Event],
    freeze: date,
    complete_through: date,
    cutoffs: tuple[date, ...] = CUTOFFS,
) -> tuple[list[Snapshot], dict]:
    validate_events(events, complete_through)
    if max(cutoffs) + timedelta(days=LABEL_HORIZON_DAYS) > min(freeze, complete_through):
        raise ValueError("Immature label horizon or incomplete source coverage")
    by_customer = defaultdict(list)
    for event in events:
        by_customer[event.customer_id].append(event)
    records, excluded = [], 0
    for customer, history in sorted(by_customer.items()):
        outcomes = visible_versions(history, freeze)
        for cutoff in cutoffs:
            known = visible_versions(history, cutoff)
            plans = [
                e
                for e in known
                if (
                    e.kind == "subscription"
                    and e.expiry_date == cutoff
                    and e.occurred_at < cutoff
                    and not e.deleted
                )
            ]
            if not plans:
                excluded += 1
                continue
            if len(plans) != 1:
                raise ValueError("Ambiguous subscription opportunity at cutoff")
            plan = plans[0]
            activity = [
                e
                for e in known
                if e.kind == "activity"
                and (max(plan.started_at, cutoff - timedelta(days=30)) <= e.occurred_at < cutoff)
            ]
            payments = [
                e
                for e in known
                if e.kind == "payment_failed"
                and (max(plan.started_at, cutoff - timedelta(days=90)) <= e.occurred_at < cutoff)
            ]
            contributing = [plan, *activity, *payments]
            horizon = cutoff + timedelta(days=30)
            renewals = [
                e
                for e in outcomes
                if (
                    e.kind == "renewal"
                    and e.expiry_date == cutoff
                    and cutoff <= e.occurred_at <= horizon
                )
            ]
            label_available = max([horizon, *(e.available_at for e in renewals)])
            records.append(
                Snapshot(
                    customer_id=customer,
                    as_of_date=cutoff,
                    active_days_30d=len({e.occurred_at for e in activity if not e.deleted}),
                    payment_failures_90d=sum(not e.deleted for e in payments),
                    tenure_months=max(1, (cutoff - plan.started_at).days // 30),
                    monthly_fee=plan.monthly_fee,
                    auto_renew=plan.auto_renew,
                    feature_max_event_at=max(e.occurred_at for e in contributing),
                    source_max_available_at=max(e.available_at for e in contributing),
                    churn_30d=int(not any(not e.deleted for e in renewals)),
                    label_available_at=label_available,
                    source_type="SYNTHETIC",
                )
            )
    if not records:
        raise ValueError("No eligible known subscription opportunities")
    return records, {
        "input_event_revisions": len(events),
        "logical_events": len({e.event_id for e in events}),
        "customers": len(by_customer),
        "candidate_opportunities": len(by_customer) * len(cutoffs),
        "eligible_rows": len(records),
        "excluded_no_known_subscription": excluded,
        "complete_through": str(complete_through),
        "freeze": str(freeze),
        "feature_windows": "[cutoff-lookback, cutoff); available_at <= cutoff",
        "label": "No renewal in [scheduled expiry, expiry+30d]; source complete and mature",
    }


def generate_events(path: Path, customers: int = 650, seed: int = SEED) -> int:
    if not 50 <= customers <= 100000:
        raise ValueError("customers must be between 50 and 100000")
    rng = random.Random(seed)
    events = []
    for n in range(customers):
        customer = f"SYN-{n:05d}"
        auto = int(rng.random() < 0.65)
        fee = rng.choice([99, 149, 199, 249, 299])
        started = CUTOFFS[0] - timedelta(days=rng.randint(2, 48) * 30)
        engagement = rng.uniform(0.12, 0.95)
        payment_propensity = rng.uniform(0, 0.03)
        for day_offset in range((CUTOFFS[-1] - date(2026, 4, 1)).days):
            day = date(2026, 4, 1) + timedelta(days=day_offset)
            if day < started:
                continue
            if rng.random() < engagement:
                events.append(
                    Event(
                        event_id=f"{customer}-activity-{day}",
                        customer_id=customer,
                        kind="activity",
                        occurred_at=day,
                        available_at=day,
                    )
                )
            if rng.random() < payment_propensity:
                events.append(
                    Event(
                        event_id=f"{customer}-payment-{day}",
                        customer_id=customer,
                        kind="payment_failed",
                        occurred_at=day,
                        available_at=day,
                    )
                )
        for cutoff in CUTOFFS:
            events.append(
                Event(
                    event_id=f"{customer}-plan-{cutoff}",
                    customer_id=customer,
                    kind="subscription",
                    occurred_at=cutoff - timedelta(days=10),
                    available_at=cutoff - timedelta(days=9),
                    expiry_date=cutoff,
                    started_at=started,
                    monthly_fee=fee,
                    auto_renew=auto,
                )
            )
            logit = -0.5 - 2.8 * engagement + 35 * payment_propensity - 0.7 * auto
            if rng.random() >= 1 / (1 + math.exp(-logit)):
                renewed = cutoff + timedelta(days=rng.randint(1, 25))
                events.append(
                    Event(
                        event_id=f"{customer}-renewal-{cutoff}",
                        customer_id=customer,
                        kind="renewal",
                        occurred_at=renewed,
                        available_at=renewed + timedelta(days=1),
                        expiry_date=cutoff,
                    )
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in sorted(events, key=lambda e: (e.customer_id, e.occurred_at, e.event_id)):
            handle.write(event.model_dump_json() + "\n")
    return len(events)


def prepare_event_dataset(root: Path, customers: int, seed: int, freeze: date):
    """Publish immutable event source and derived CSV/Parquet, returning validated snapshots."""
    from .data import DEFAULT_AS_OF, ingest_snapshots

    if freeze > DEFAULT_AS_OF:
        raise ValueError("Synthetic source completeness ends on 2026-11-03")
    staging_root = root / "data/staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        staged = Path(staging)
        source = staged / "events.jsonl"
        generate_events(source, customers, seed)
        events = [Event.model_validate_json(line) for line in source.read_text().splitlines()]
        snapshots, quality = build_features(events, freeze, DEFAULT_AS_OF)
        checksum = sha256_file(source)
        event_release = root / "data/events" / checksum
        manifest = {
            "source_release_id": f"synthetic-events-{checksum}",
            "sha256": checksum,
            "source_type": "SYNTHETIC",
            "schema_version": "subscription-events-v1",
            "complete_through": str(DEFAULT_AS_OF),
            "rows": len(events),
            "rights": "Project-generated synthetic subscription events",
        }
        event_release.parent.mkdir(parents=True, exist_ok=True)
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if event_release.exists():
            if (
                sha256_file(event_release / "events.jsonl") != checksum
                or json.loads((event_release / "manifest.json").read_text()) != manifest
            ):
                raise ValueError("Corrupt immutable event source")
        else:
            with tempfile.TemporaryDirectory(dir=event_release.parent) as tmp:
                target = Path(tmp) / "release"
                target.mkdir()
                (target / "events.jsonl").write_bytes(source.read_bytes())
                (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                target.rename(event_release)
        csv_path = staged / "snapshots.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(Snapshot.model_fields))
            writer.writeheader()
            writer.writerows(r.model_dump(mode="json") for r in snapshots)
        records, source_manifest = ingest_snapshots(csv_path, root, freeze)
        feature_release = root / "data/features" / source_manifest["dataset_sha256"]
        feature_release.mkdir(parents=True, exist_ok=True)
        parquet = staged / "features.parquet"
        pl.DataFrame([r.model_dump() for r in records]).write_parquet(parquet)
        destination = feature_release / "features.parquet"
        if destination.exists() and sha256_file(destination) != sha256_file(parquet):
            raise ValueError("Corrupt or non-reproducible feature Parquet")
        if not destination.exists():
            parquet.rename(destination)
        source_manifest = {
            **source_manifest,
            "events": manifest,
            "quality": quality,
            "feature_parquet_sha256": sha256_file(destination),
            "feature_origin": "Event-derived point-in-time subscription aggregates",
        }
        return records, source_manifest
