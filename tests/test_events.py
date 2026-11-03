import hashlib
import json
from datetime import date, timedelta

import polars as pl
import pytest

from retentionops.data import DEFAULT_AS_OF
from retentionops.events import (
    Event,
    build_features,
    generate_events,
    ingest_event_source,
    load_event_source,
    validate_events,
)
from retentionops.pipeline import run_event_pipeline, run_event_source_pipeline
from retentionops.training import temporal_split

CUTOFF = date(2026, 6, 30)


def event(kind, name, occurred, available=None, **fields):
    return Event(
        event_id=f"SYN-{name}",
        customer_id="SYN-00001",
        kind=kind,
        occurred_at=date.fromisoformat(occurred),
        available_at=date.fromisoformat(available or occurred),
        **fields,
    )


def history():
    return [
        event(
            "subscription",
            "plan",
            "2026-06-01",
            expiry_date=CUTOFF,
            started_at=date(2026, 1, 1),
            monthly_fee=149,
            auto_renew=1,
        ),
        event("activity", "start", "2026-05-31"),
        event("activity", "last", "2026-06-29"),
        event("payment_failed", "pay", "2026-04-01"),
        event("renewal", "renew", "2026-07-30", expiry_date=CUTOFF),
    ]


def build(rows):
    return build_features(rows, DEFAULT_AS_OF, DEFAULT_AS_OF, (CUTOFF,))[0][0]


def test_independent_window_and_label_boundaries():
    rows = history() + [
        event("activity", "outside", "2026-05-30"),
        event("activity", "cutoff", "2026-06-30"),
        event("activity", "same-day", "2026-06-29"),
        event("payment_failed", "too-old", "2026-03-31"),
        event("payment_failed", "pay-cutoff", "2026-06-30"),
    ]
    snapshot = build(rows)
    assert snapshot.active_days_30d == 2
    assert snapshot.payment_failures_90d == 1
    assert snapshot.tenure_months == 6
    assert snapshot.monthly_fee == 149 and snapshot.auto_renew == 1
    assert snapshot.churn_30d == 0  # Renewal exactly at +30 days counts.
    assert snapshot.label_available_at == date(2026, 7, 30)


def test_future_events_late_arrivals_and_cancellations_do_not_change_prior_snapshot():
    base = history()
    added = [
        event("activity", "future", "2026-07-01"),
        event("activity", "late", "2026-06-28", "2026-07-01"),
        event("payment_failed", "late-pay", "2026-06-20", "2026-07-02"),
        event("cancellation", "cancel", "2026-07-01", expiry_date=CUTOFF),
        base[3].model_copy(
            update={"revision": 2, "deleted": True, "available_at": date(2026, 7, 1)}
        ),
    ]
    assert build(base + added) == build(base)


def test_latest_known_correction_before_time_filter_prevents_resurrection():
    rows = history()
    # Correction is known by cutoff and moves the historical payment outside its window.
    corrected = rows[3].model_copy(
        update={"revision": 2, "occurred_at": date(2026, 3, 31), "available_at": date(2026, 6, 30)}
    )
    assert build(rows + [corrected]).payment_failures_90d == 0
    tombstone = rows[1].model_copy(
        update={"revision": 2, "deleted": True, "available_at": date(2026, 6, 30)}
    )
    assert build(rows + [tombstone]).active_days_30d == 1


def test_no_renewal_and_late_renewal_are_churn():
    rows = history()[:-1]
    assert build(rows).churn_30d == 1
    assert (
        build(
            rows + [event("renewal", "outside-renew", "2026-07-31", expiry_date=CUTOFF)]
        ).churn_30d
        == 1
    )


def test_late_outcome_advances_label_availability():
    rows = history()
    rows[-1] = rows[-1].model_copy(update={"available_at": date(2026, 9, 1)})
    assert build(rows).label_available_at == date(2026, 9, 1)


@pytest.mark.parametrize("correction", ["outside-window", "changed-expiry", "deleted"])
def test_removing_renewal_eligibility_retains_late_revision_availability(correction):
    rows = history()
    update = {"revision": 2, "available_at": date(2026, 9, 1)}
    if correction == "outside-window":
        update["occurred_at"] = date(2026, 7, 31)
    elif correction == "changed-expiry":
        update["expiry_date"] = date(2026, 7, 31)
    else:
        update["deleted"] = True
    rows.append(rows[-1].model_copy(update=update))
    snapshot = build(rows)
    assert snapshot.churn_30d == 1
    assert snapshot.label_available_at == date(2026, 9, 1)


def test_removed_renewal_late_correction_cannot_enter_earlier_training():
    from retentionops.data import CUTOFFS

    rows = []
    for n in range(2):
        customer = f"SYN-{n:05d}"
        for cutoff in CUTOFFS:
            rows.append(
                Event(
                    event_id=f"{customer}-plan-{cutoff}",
                    customer_id=customer,
                    kind="subscription",
                    occurred_at=cutoff - timedelta(days=10),
                    available_at=cutoff - timedelta(days=9),
                    started_at=date(2026, 1, 1),
                    expiry_date=cutoff,
                    monthly_fee=149,
                    auto_renew=1,
                )
            )
            if n == 1:
                rows.append(
                    Event(
                        event_id=f"{customer}-renew-{cutoff}",
                        customer_id=customer,
                        kind="renewal",
                        occurred_at=cutoff + timedelta(days=10),
                        available_at=cutoff + timedelta(days=11),
                        expiry_date=cutoff,
                    )
                )
    original, _ = build_features(rows, DEFAULT_AS_OF, DEFAULT_AS_OF)
    temporal_split(original)
    renewal = next(e for e in rows if e.kind == "renewal" and e.expiry_date == CUTOFF)
    rows.append(
        renewal.model_copy(
            update={
                "revision": 2,
                "occurred_at": date(2026, 7, 31),
                "available_at": date(2026, 9, 1),
            }
        )
    )
    corrected, _ = build_features(rows, DEFAULT_AS_OF, DEFAULT_AS_OF)
    with pytest.raises(ValueError, match="embargo"):
        temporal_split(corrected)


def test_missing_revision_history_is_not_silently_excluded():
    rows = history()
    rows[3] = rows[3].model_copy(update={"revision": 2})
    with pytest.raises(ValueError, match="revision history"):
        build(rows)


def test_payment_count_is_not_capped_by_number_of_days():
    rows = history() + [event("payment_failed", f"attempt-{i}", "2026-06-20") for i in range(100)]
    assert build(rows).payment_failures_90d == 101


@pytest.mark.parametrize("change", ["duplicate", "identity", "watermark", "revision-order"])
def test_quality_gate_failure(change):
    rows = history()
    if change == "duplicate":
        rows.append(rows[0])
    elif change == "identity":
        rows.append(rows[0].model_copy(update={"revision": 2, "customer_id": "SYN-00002"}))
    elif change == "watermark":
        rows.append(event("activity", "beyond", "2026-11-04"))
    else:
        rows.append(rows[0].model_copy(update={"revision": 2, "available_at": date(2026, 5, 31)}))
    with pytest.raises(ValueError):
        validate_events(rows, DEFAULT_AS_OF)


def test_coverage_and_eligibility():
    with pytest.raises(ValueError, match="Immature"):
        build_features(history(), date(2026, 7, 29), DEFAULT_AS_OF, (CUTOFF,))
    rows, report = build_features(
        history(), DEFAULT_AS_OF, DEFAULT_AS_OF, (CUTOFF, CUTOFF + timedelta(days=31))
    )
    assert len(rows) == 1 and report["excluded_no_known_subscription"] == 1
    with pytest.raises(ValueError, match="Ambiguous"):
        build(history() + [history()[0].model_copy(update={"event_id": "SYN-second-plan"})])


def test_event_bytes_and_pipeline_replay(tmp_path):
    path = tmp_path / "events.jsonl"
    generate_events(path, 100)
    first = path.read_bytes()
    generate_events(path, 100)
    assert path.read_bytes() == first
    manifest = run_event_pipeline(tmp_path, customers=150)
    assert run_event_pipeline(tmp_path, customers=150) == manifest
    assert manifest["feature_origin"].startswith("Event-derived")
    assert manifest["source"]["quality"]["eligible_rows"] == 600
    assert manifest["source"]["quality"]["excluded_no_known_subscription"] == 0
    parquet = next((tmp_path / "data/features").glob("*/features.parquet"))
    assert pl.read_parquet(parquet).height == 600
    assert pl.read_parquet_schema(parquet)["as_of_date"] == pl.Date


def test_local_source_intake_is_content_addressed_and_reconciled(tmp_path):
    source = tmp_path / "incoming.jsonl"
    generate_events(source, 100)
    first_event = Event.model_validate_json(source.read_text().splitlines()[0])
    correction = first_event.model_copy(
        update={
            "revision": 2,
            "available_at": first_event.available_at + timedelta(days=1),
        }
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(correction.model_dump_json() + "\n")
    payload = source.read_bytes()

    first = ingest_event_source(source, tmp_path / "workspace", "sample-feed", DEFAULT_AS_OF)
    second = ingest_event_source(source, tmp_path / "workspace", "sample-feed", DEFAULT_AS_OF)
    events, manifest = load_event_source(tmp_path / "workspace", first["source_release_id"])

    release = tmp_path / "workspace/data/events" / first["source_release_id"]
    assert first == second == manifest
    assert first["source_type"] == "SYNTHETIC"
    assert first["sha256"] == hashlib.sha256(payload).hexdigest()
    assert first["quality"]["rows"] == len(events) == first["rows"]
    assert first["quality"]["logical_events"] < first["rows"]
    assert first["quality"]["watermark_passed"] is True
    assert (release / "events.jsonl").read_bytes() == payload


@pytest.mark.parametrize(
    "invalid_source", ["malformed", "blank", "duplicate", "watermark", "extra-field"]
)
def test_failed_local_intake_publishes_no_release(tmp_path, invalid_source):
    source = tmp_path / "incoming.jsonl"
    generate_events(source, 50)
    rows = source.read_text().splitlines()
    if invalid_source == "malformed":
        rows.append("not-json")
    elif invalid_source == "blank":
        rows.append("")
    elif invalid_source == "duplicate":
        rows.append(rows[0])
    elif invalid_source == "extra-field":
        invalid_event = json.loads(rows[0])
        invalid_event["private_marker"] = "synthetic-private-marker"
        rows.append(json.dumps(invalid_event))
    else:
        rows.append(
            Event(
                event_id="SYN-outside-watermark",
                customer_id="SYN-00000",
                kind="activity",
                occurred_at=date(2026, 11, 4),
                available_at=date(2026, 11, 4),
            ).model_dump_json()
        )
    source.write_text("\n".join(rows) + "\n")

    with pytest.raises(ValueError) as caught:
        ingest_event_source(source, tmp_path / "workspace", "sample-feed", DEFAULT_AS_OF)
    if invalid_source == "extra-field":
        assert "synthetic-private-marker" not in str(caught.value)
    event_root = tmp_path / "workspace/data/events"
    assert not [path for path in event_root.iterdir() if path.is_dir()]


def test_corrupt_published_event_release_fails_closed(tmp_path):
    source = tmp_path / "incoming.jsonl"
    generate_events(source, 50)
    manifest = ingest_event_source(source, tmp_path / "workspace", "sample-feed", DEFAULT_AS_OF)
    published_source = (
        tmp_path / "workspace/data/events" / manifest["source_release_id"] / "events.jsonl"
    )
    published_source.write_bytes(published_source.read_bytes() + b"corruption\n")

    with pytest.raises(ValueError, match="Corrupt immutable event source"):
        ingest_event_source(source, tmp_path / "workspace", "sample-feed", DEFAULT_AS_OF)
    with pytest.raises(ValueError, match="checksum"):
        load_event_source(tmp_path / "workspace", manifest["source_release_id"])


def test_event_pipeline_replays_an_ingested_source_without_regeneration(tmp_path):
    source = tmp_path / "incoming.jsonl"
    generate_events(source, 150, seed=71)
    event_release = ingest_event_source(source, tmp_path, "owner-upload", DEFAULT_AS_OF)

    first = run_event_source_pipeline(tmp_path, event_release["source_release_id"])
    second = run_event_source_pipeline(tmp_path, event_release["source_release_id"])

    assert first == second
    assert first["source"]["events"]["source_release_id"] == event_release["source_release_id"]
    assert first["source"]["events"]["sha256"] == event_release["sha256"]
    assert first["source"]["quality"]["eligible_rows"] == 600
    feature_release = tmp_path / "data/features" / first["source"]["feature_release_id"]
    feature_manifest = json.loads((feature_release / "manifest.json").read_text())
    assert feature_manifest["source_release_id"] == event_release["source_release_id"]
    assert feature_manifest["rows"] == 600


def test_late_labels_cannot_silently_enter_train(csv_path):
    from retentionops.data import read_snapshots

    rows = read_snapshots(csv_path)
    rows[1] = rows[1].model_copy(update={"label_available_at": date(2026, 9, 1)})
    with pytest.raises(ValueError, match="embargo"):
        temporal_split(rows)
