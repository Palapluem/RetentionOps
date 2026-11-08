"""Day-grain subscription events, bitemporal corrections and point-in-time aggregates."""

from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import shutil
import stat
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .data import CUTOFFS, LABEL_HORIZON_DAYS, SEED, Snapshot, canonical_hash, sha256_file


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

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

    @field_validator("auto_renew", mode="before")
    @classmethod
    def auto_renew_is_integer(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("auto_renew must be the integer 0 or 1")
        return value

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


def read_event_jsonl(path: Path) -> list[Event]:
    """Read one strict JSONL event source and report malformed physical lines."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Cannot read UTF-8 event source: {exc}") from exc
    if not lines:
        raise ValueError("Empty event source")
    events = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"Blank JSONL row at line {line_number}")
        try:
            events.append(Event.model_validate_json(line))
        except ValidationError as exc:
            issues = "; ".join(
                f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
            raise ValueError(f"Invalid event at JSONL line {line_number}: {issues}") from exc
    return events


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
        if any(e.revision != expected for expected, e in enumerate(rows, start=1)):
            raise ValueError("Complete event revision history starting at 1 is required")
        if len({(e.customer_id, e.kind) for e in rows}) != 1:
            raise ValueError("Logical event identity changed across revisions")
        if any(a.available_at > b.available_at for a, b in pairwise(rows)):
            raise ValueError("Revision availability must be monotonic")


def event_quality_report(events: list[Event], complete_through: date) -> dict:
    """Validate a source and return deterministic reconciliation evidence."""
    validate_events(events, complete_through)
    return {
        "rows": len(events),
        "logical_events": len({event.event_id for event in events}),
        "customers": len({event.customer_id for event in events}),
        "max_available_at": str(max(event.available_at for event in events)),
        "revision_history": "contiguous-from-1",
        "duplicate_event_revisions": 0,
        "watermark_passed": True,
    }


def _publish_immutable_release(
    staged_release: Path,
    release: Path,
    manifest: dict,
    artifact_hashes: dict[str, str],
    release_name: str,
) -> None:
    (staged_release / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if release.exists():
        try:
            existing_manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
            artifacts_match = all(
                (release / name).is_file() and sha256_file(release / name) == checksum
                for name, checksum in artifact_hashes.items()
            )
        except (OSError, json.JSONDecodeError):
            artifacts_match = False
            existing_manifest = None
        if existing_manifest != manifest or not artifacts_match:
            raise ValueError(f"Corrupt immutable {release_name} release")
        return
    staged_release.rename(release)


_SOURCE_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_RELEASE_ID = re.compile(r"^(?P<source>[a-z][a-z0-9-]{0,39})-(?P<identity>[0-9a-f]{64})$")


def _source_identity(source_id: str, checksum: str, complete_through: date) -> dict:
    return {
        "source_id": source_id,
        "sha256": checksum,
        "source_type": "SYNTHETIC",
        "schema_version": "subscription-events-v1",
        "complete_through": str(complete_through),
    }


def ingest_event_source(
    source_path: Path, root: Path, source_id: str, complete_through: date
) -> dict:
    """Validate and atomically publish a content-addressed synthetic event release."""
    if not _SOURCE_ID.fullmatch(source_id):
        raise ValueError(
            "source-id must start with a lowercase letter and contain only a-z, 0-9, or hyphen"
        )
    source_path = Path(source_path).expanduser()
    if not source_path.is_file():
        raise ValueError("Event source file does not exist")
    root = Path(root).resolve()
    event_root = root / "data" / "events"
    event_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=event_root, prefix=".staging-") as staging:
        staged_release = Path(staging) / "release"
        staged_release.mkdir()
        staged_source = staged_release / "events.jsonl"
        try:
            shutil.copyfile(source_path, staged_source)
        except OSError as exc:
            raise ValueError(f"Cannot stage event source: {exc}") from exc
        events = read_event_jsonl(staged_source)
        quality = event_quality_report(events, complete_through)
        checksum = sha256_file(staged_source)
        identity = _source_identity(source_id, checksum, complete_through)
        release_id = f"{source_id}-{canonical_hash(identity)}"
        manifest = {
            "source_release_id": release_id,
            "identity": identity,
            **identity,
            "rows": len(events),
            "quality": quality,
            "rights": "Synthetic-only local intake; real customer sources are not approved by this contract",
        }
        release = event_root / release_id
        _publish_immutable_release(
            staged_release, release, manifest, {"events.jsonl": checksum}, "event source"
        )
    return manifest


def load_event_source(root: Path, source_release_id: str) -> tuple[list[Event], dict]:
    """Load a published event release only after verifying its content and manifest."""
    release_match = _RELEASE_ID.fullmatch(source_release_id)
    if not release_match:
        raise ValueError("Invalid source release ID")
    release = Path(root).resolve() / "data" / "events" / source_release_id
    try:
        manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
        source = release / "events.jsonl"
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Event source release is missing or has an invalid manifest") from exc
    if not source.is_file() or sha256_file(source) != manifest.get("sha256"):
        raise ValueError("Event source release checksum does not match its manifest")
    events = read_event_jsonl(source)
    source_id = manifest.get("source_id")
    if (
        manifest.get("source_release_id") != source_release_id
        or source_id != release_match.group("source")
        or manifest.get("source_type") != "SYNTHETIC"
        or manifest.get("schema_version") != "subscription-events-v1"
    ):
        raise ValueError("Event source release identity or contract does not match its manifest")
    try:
        complete_through = date.fromisoformat(manifest["complete_through"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Event source manifest has an invalid completeness watermark") from exc
    identity = _source_identity(source_id, manifest.get("sha256"), complete_through)
    if manifest.get("identity") != identity or canonical_hash(identity) != release_match.group(
        "identity"
    ):
        raise ValueError("Event source release identity or contract does not match its manifest")
    quality = event_quality_report(events, complete_through)
    expected_manifest = {
        "source_release_id": source_release_id,
        "identity": identity,
        **identity,
        "rows": len(events),
        "quality": quality,
        "rights": "Synthetic-only local intake; real customer sources are not approved by this contract",
    }
    if expected_manifest != manifest:
        raise ValueError("Event source release manifest does not match its content and quality")
    return events, manifest


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
    if freeze > complete_through:
        raise ValueError("Source completeness watermark must cover the evaluation freeze")
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
            # Retain the latest availability of revisions that REMOVE a previous renewal
            # from this opportunity/window, as well as revisions that add a renewal.
            relevant_ids = {
                e.event_id
                for e in history
                if e.kind == "renewal"
                and e.available_at <= freeze
                and e.expiry_date == cutoff
                and cutoff <= e.occurred_at <= horizon
            }
            label_revisions = [e for e in outcomes if e.event_id in relevant_ids]
            renewals = [
                e
                for e in label_revisions
                if (
                    e.expiry_date == cutoff and cutoff <= e.occurred_at <= horizon and not e.deleted
                )
            ]
            label_available = max([horizon, *(e.available_at for e in label_revisions)])
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
                    churn_30d=int(not renewals),
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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stage beside the destination, then atomically link without replacing an owner file.
    # Exact replay is allowed only for regular files, never for symlinks.
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".events-staging-") as staging:
        staged = Path(staging) / "events.jsonl"
        with staged.open("w", encoding="utf-8") as handle:
            for event in sorted(events, key=lambda e: (e.customer_id, e.occurred_at, e.event_id)):
                handle.write(event.model_dump_json() + "\n")
        try:
            os.link(staged, path, follow_symlinks=False)
        except FileExistsError:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError as exc:
                raise ValueError("Output already exists or is a symlink") from exc
            with os.fdopen(fd, "rb") as existing, staged.open("rb") as expected:
                if not stat.S_ISREG(os.fstat(existing.fileno()).st_mode):
                    raise ValueError("Output must be a regular file") from None
                while True:
                    existing_chunk = existing.read(1024 * 1024)
                    if existing_chunk != expected.read(1024 * 1024):
                        raise ValueError(
                            "Refusing to overwrite a different existing output"
                        ) from None
                    if not existing_chunk:
                        break
    return len(events)


def prepare_event_dataset(root: Path, customers: int, seed: int, freeze: date):
    """Generate a demo source, then use the same intake and derivation stages as file input."""
    from .data import DEFAULT_AS_OF

    if freeze > DEFAULT_AS_OF:
        raise ValueError("Synthetic source completeness ends on 2026-11-03")
    staging_root = root / "data/staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        source = Path(staging) / "events.jsonl"
        generate_events(source, customers, seed)
        event_manifest = ingest_event_source(source, root, "synthetic-events", DEFAULT_AS_OF)
    return prepare_features_from_release(root, event_manifest["source_release_id"], freeze)


def prepare_features_from_release(root: Path, source_release_id: str, freeze: date):
    """Derive and atomically publish features from a previously ingested event release."""
    from .data import Snapshot, ingest_snapshots

    events, event_manifest = load_event_source(root, source_release_id)
    complete_through = date.fromisoformat(event_manifest["complete_through"])
    snapshots, quality = build_features(events, freeze, complete_through)
    root = Path(root).resolve()
    staging_root = root / "data" / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        staged = Path(staging)
        csv_path = staged / "snapshots.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(Snapshot.model_fields))
            writer.writeheader()
            writer.writerows(r.model_dump(mode="json") for r in snapshots)
        records, source_manifest = ingest_snapshots(csv_path, root, freeze)
        features_root = root / "data" / "features"
        features_root.mkdir(parents=True, exist_ok=True)
        parquet = staged / "features.parquet"
        pl.DataFrame([r.model_dump() for r in records]).write_parquet(parquet)
        parquet_hash = sha256_file(parquet)
        feature_identity = {
            "source_release_id": event_manifest["source_release_id"],
            "dataset_sha256": source_manifest["dataset_sha256"],
            "freeze": str(freeze),
            "schema_version": "event-features-v1",
            "implementation_sha256": sha256_file(Path(__file__)),
            "polars_version": pl.__version__,
        }
        feature_release_id = canonical_hash(feature_identity)
        feature_release = features_root / feature_release_id
        feature_manifest = {
            "feature_release_id": feature_release_id,
            "identity": feature_identity,
            "source_release_id": event_manifest["source_release_id"],
            "source_sha256": event_manifest["sha256"],
            "dataset_sha256": source_manifest["dataset_sha256"],
            "feature_parquet_sha256": parquet_hash,
            "rows": len(records),
            "quality": quality,
            "schema_version": "event-features-v1",
            "source_type": "SYNTHETIC",
        }
        staged_feature_release = staged / "feature-release"
        staged_feature_release.mkdir()
        parquet.rename(staged_feature_release / "features.parquet")
        _publish_immutable_release(
            staged_feature_release,
            feature_release,
            feature_manifest,
            {"features.parquet": parquet_hash},
            "feature",
        )
    source_manifest = {
        **source_manifest,
        "events": event_manifest,
        "quality": quality,
        "feature_release_id": feature_release_id,
        "feature_parquet_sha256": parquet_hash,
        "feature_origin": "Event-derived point-in-time subscription aggregates",
    }
    return records, source_manifest
