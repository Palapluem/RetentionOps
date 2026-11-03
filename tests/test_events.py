from datetime import date, timedelta

import polars as pl
import pytest

from retentionops.data import DEFAULT_AS_OF
from retentionops.events import Event, build_features, generate_events, validate_events
from retentionops.pipeline import run_event_pipeline
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


def test_late_labels_cannot_silently_enter_train(csv_path):
    from retentionops.data import read_snapshots

    rows = read_snapshots(csv_path)
    rows[1] = rows[1].model_copy(update={"label_available_at": date(2026, 9, 1)})
    with pytest.raises(ValueError, match="embargo"):
        temporal_split(rows)
