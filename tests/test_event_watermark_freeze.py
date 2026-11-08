"""Independent examples for source coverage through the label evaluation freeze."""

from datetime import date, timedelta

import pytest

from retentionops.data import DEFAULT_AS_OF
from retentionops.events import Event, build_features, generate_events, read_event_jsonl

CUTOFF = date(2026, 6, 30)
WATERMARK = date(2026, 8, 1)
CORRECTION_AVAILABLE = date(2026, 8, 5)
FREEZE = date(2026, 8, 10)


def source_revisions():
    plan = Event(
        event_id="SYN-plan-watermark",
        customer_id="SYN-00001",
        kind="subscription",
        occurred_at=date(2026, 6, 1),
        available_at=date(2026, 6, 1),
        expiry_date=CUTOFF,
        started_at=date(2026, 1, 1),
        monthly_fee=149.0,
        auto_renew=1,
    )
    renewal = Event(
        event_id="SYN-renew-watermark",
        customer_id="SYN-00001",
        kind="renewal",
        occurred_at=date(2026, 7, 20),
        available_at=date(2026, 7, 21),
        expiry_date=CUTOFF,
    )
    tombstone = Event(
        event_id="SYN-renew-watermark",
        revision=2,
        customer_id="SYN-00001",
        kind="renewal",
        occurred_at=date(2026, 7, 20),
        available_at=CORRECTION_AVAILABLE,
        expiry_date=CUTOFF,
        deleted=True,
    )
    return [plan, renewal], tombstone


def test_mature_horizon_does_not_prove_coverage_through_freeze():
    early_source, _ = source_revisions()
    assert CUTOFF + timedelta(days=30) < WATERMARK < CORRECTION_AVAILABLE < FREEZE

    # The source may legitimately omit a later correction; it cannot support
    # claiming that the label reflects the requested later evaluation freeze.
    with pytest.raises(ValueError):
        build_features(early_source, FREEZE, WATERMARK, (CUTOFF,))


def test_watermark_equal_to_freeze_accepts_mature_uncorrected_label():
    early_source, _ = source_revisions()
    records, quality = build_features(early_source, WATERMARK, WATERMARK, (CUTOFF,))

    assert len(records) == 1
    assert records[0].churn_30d == 0
    assert records[0].label_available_at == date(2026, 7, 30)
    assert quality["freeze"] == quality["complete_through"] == WATERMARK.isoformat()


def test_complete_source_correction_changes_label_only_when_known_at_freeze():
    early_source, tombstone = source_revisions()
    full_source = [*early_source, tombstone]

    before, _ = build_features(full_source, WATERMARK, FREEZE, (CUTOFF,))
    after, _ = build_features(full_source, FREEZE, FREEZE, (CUTOFF,))

    assert before[0].churn_30d == 0
    assert before[0].label_available_at == date(2026, 7, 30)
    assert after[0].churn_30d == 1
    assert after[0].label_available_at == CORRECTION_AVAILABLE
    assert before[0].feature_max_event_at == after[0].feature_max_event_at
    assert before[0].source_max_available_at == after[0].source_max_available_at


def test_default_generated_event_source_remains_accepted_at_equal_watermark(tmp_path):
    source = tmp_path / "events.jsonl"
    generate_events(source, customers=50)

    records, quality = build_features(read_event_jsonl(source), DEFAULT_AS_OF, DEFAULT_AS_OF)

    assert len(records) == 200
    assert quality["eligible_rows"] == 200
    assert all(record.label_available_at <= DEFAULT_AS_OF for record in records)
