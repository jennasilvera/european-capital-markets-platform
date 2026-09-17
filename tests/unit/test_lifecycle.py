from datetime import date

import pytest

from european_capital_markets.domain.entities import TransactionRecord
from european_capital_markets.domain.lifecycle import (
    TransactionLifecycleEventRecord,
    derive_transaction_status,
    validate_lifecycle_bundle,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    SourceRecord,
)
from european_capital_markets.domain.taxonomy import (
    ProductFamily,
    SourceTier,
    SourceType,
    TransactionStatus,
)


def _transaction(
    transaction_id: str = "TXN000000001",
) -> TransactionRecord:
    return TransactionRecord(
        transaction_id=transaction_id,
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.IG_DCM,
    )


def _source() -> SourceRecord:
    return SourceRecord(
        source_id="SRC000000001",
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.ISSUER_ANNOUNCEMENT,
        publisher="Example Issuer plc",
        title="Transaction Announcement",
        access_date=date(2026, 9, 17),
        url="https://example.invalid/announcement",
    )


def _evidence(
    evidence_id: str = "EVD000000001",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_id="SRC000000001",
        locator="Transaction status announcement",
    )


def _event(
    *,
    event_id: str = "TLE000000001",
    transaction_id: str = "TXN000000001",
    status: TransactionStatus = TransactionStatus.ANNOUNCED,
    effective_date: date = date(2026, 9, 1),
    event_order: int = 1,
    evidence_ids: tuple[str, ...] = ("EVD000000001",),
    notes: str | None = None,
) -> TransactionLifecycleEventRecord:
    return TransactionLifecycleEventRecord(
        event_id=event_id,
        transaction_id=transaction_id,
        status=status,
        effective_date=effective_date,
        event_order=event_order,
        evidence_ids=evidence_ids,
        notes=notes,
    )


def _validate(
    events: tuple[TransactionLifecycleEventRecord, ...],
    *,
    transactions: tuple[TransactionRecord, ...] | None = None,
    evidence: tuple[EvidenceRecord, ...] | None = None,
) -> None:
    validate_lifecycle_bundle(
        transactions=transactions or (_transaction(),),
        events=events,
        sources=(_source(),),
        evidence=evidence or (_evidence(),),
    )


def test_valid_lifecycle_event() -> None:
    _validate((_event(),))


def test_multiple_statuses_may_occur_on_same_date_in_known_order() -> None:
    launched = _event(
        event_id="TLE000000001",
        status=TransactionStatus.LAUNCHED,
        event_order=1,
    )
    priced = _event(
        event_id="TLE000000002",
        status=TransactionStatus.PRICED,
        event_order=2,
    )

    _validate((launched, priced))


def test_event_requires_lifecycle_identifier() -> None:
    with pytest.raises(ValueError, match="not TRANSACTION_LIFECYCLE_EVENT"):
        _event(event_id="TXN000000001")


def test_event_requires_transaction_identifier() -> None:
    with pytest.raises(ValueError, match="not TRANSACTION"):
        _event(transaction_id="ISS000000001")


def test_status_must_be_controlled() -> None:
    with pytest.raises(TypeError, match="TransactionStatus"):
        _event(
            status="PRICED",  # type: ignore[arg-type]
        )


def test_event_order_must_be_integer() -> None:
    with pytest.raises(TypeError, match="integer"):
        _event(
            event_order=1.5,  # type: ignore[arg-type]
        )


def test_event_order_rejects_boolean() -> None:
    with pytest.raises(TypeError, match="integer"):
        _event(
            event_order=True,
        )


def test_event_order_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        _event(event_order=0)


def test_event_requires_evidence() -> None:
    with pytest.raises(ValueError, match="require source evidence"):
        _event(evidence_ids=())


def test_event_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        _event(
            evidence_ids=(
                "EVD000000001",
                "EVD000000001",
            )
        )


def test_event_rejects_blank_notes() -> None:
    with pytest.raises(ValueError, match="notes"):
        _event(notes="   ")


def test_bundle_rejects_unknown_transaction() -> None:
    event = _event(
        transaction_id="TXN000000002",
    )

    with pytest.raises(ValueError, match="Unknown transaction"):
        _validate((event,))


def test_bundle_rejects_unknown_evidence() -> None:
    event = _event(
        evidence_ids=("EVD000000002",),
    )

    with pytest.raises(ValueError, match="Unknown evidence"):
        _validate((event,))


def test_bundle_rejects_duplicate_event_ids() -> None:
    first = _event()
    second = _event(
        status=TransactionStatus.MARKETING,
    )

    with pytest.raises(ValueError, match="Duplicate identifier"):
        _validate((first, second))


def test_bundle_rejects_duplicate_date_order_slot() -> None:
    first = _event(
        status=TransactionStatus.LAUNCHED,
    )
    second = _event(
        event_id="TLE000000002",
        status=TransactionStatus.PRICED,
    )

    with pytest.raises(ValueError, match="ordering slot"):
        _validate((first, second))


def test_same_status_may_recur_on_same_date_when_ordered() -> None:
    initial_launch = _event(
        event_id="TLE000000001",
        status=TransactionStatus.LAUNCHED,
        event_order=1,
    )
    postponed = _event(
        event_id="TLE000000002",
        status=TransactionStatus.POSTPONED,
        event_order=2,
    )
    relaunch = _event(
        event_id="TLE000000003",
        status=TransactionStatus.LAUNCHED,
        event_order=3,
    )

    events = (
        initial_launch,
        postponed,
        relaunch,
    )

    _validate(events)

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
        )
        is TransactionStatus.LAUNCHED
    )


def test_same_status_may_recur_on_later_date() -> None:
    initial_launch = _event(
        event_id="TLE000000001",
        status=TransactionStatus.LAUNCHED,
        effective_date=date(2026, 9, 1),
    )
    relaunch = _event(
        event_id="TLE000000002",
        status=TransactionStatus.LAUNCHED,
        effective_date=date(2026, 9, 5),
    )

    _validate((initial_launch, relaunch))


def test_latest_status_is_derived_from_date_and_order() -> None:
    events = (
        _event(
            event_id="TLE000000001",
            status=TransactionStatus.ANNOUNCED,
            effective_date=date(2026, 9, 1),
        ),
        _event(
            event_id="TLE000000002",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 3),
            event_order=1,
        ),
        _event(
            event_id="TLE000000003",
            status=TransactionStatus.PRICED,
            effective_date=date(2026, 9, 3),
            event_order=2,
        ),
    )

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
        )
        is TransactionStatus.PRICED
    )


def test_historical_status_respects_as_of_date() -> None:
    events = (
        _event(
            event_id="TLE000000001",
            status=TransactionStatus.ANNOUNCED,
            effective_date=date(2026, 9, 1),
        ),
        _event(
            event_id="TLE000000002",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 5),
        ),
        _event(
            event_id="TLE000000003",
            status=TransactionStatus.PRICED,
            effective_date=date(2026, 9, 6),
        ),
    )

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
            as_of_date=date(2026, 9, 5),
        )
        is TransactionStatus.LAUNCHED
    )


def test_status_is_unknown_before_first_event() -> None:
    event = _event(
        effective_date=date(2026, 9, 5),
    )

    assert (
        derive_transaction_status(
            "TXN000000001",
            (event,),
            as_of_date=date(2026, 9, 4),
        )
        is None
    )


def test_status_derivation_ignores_other_transactions() -> None:
    target = _event(
        event_id="TLE000000001",
        transaction_id="TXN000000001",
        status=TransactionStatus.LAUNCHED,
    )
    other = _event(
        event_id="TLE000000002",
        transaction_id="TXN000000002",
        status=TransactionStatus.PRICED,
        effective_date=date(2026, 9, 10),
    )

    assert (
        derive_transaction_status(
            "TXN000000001",
            (target, other),
        )
        is TransactionStatus.LAUNCHED
    )


def test_postponement_then_relaunch_preserves_both_states() -> None:
    events = (
        _event(
            event_id="TLE000000001",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 1),
        ),
        _event(
            event_id="TLE000000002",
            status=TransactionStatus.POSTPONED,
            effective_date=date(2026, 9, 2),
        ),
        _event(
            event_id="TLE000000003",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 5),
        ),
    )

    _validate(events)

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
            as_of_date=date(2026, 9, 2),
        )
        is TransactionStatus.POSTPONED
    )

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
        )
        is TransactionStatus.LAUNCHED
    )


def test_withdrawn_transaction_remains_in_lifecycle_history() -> None:
    events = (
        _event(
            event_id="TLE000000001",
            status=TransactionStatus.ANNOUNCED,
            effective_date=date(2026, 9, 1),
        ),
        _event(
            event_id="TLE000000002",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 3),
        ),
        _event(
            event_id="TLE000000003",
            status=TransactionStatus.WITHDRAWN,
            effective_date=date(2026, 9, 4),
        ),
    )

    _validate(events)

    assert len(events) == 3
    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
        )
        is TransactionStatus.WITHDRAWN
    )


def test_as_of_date_uses_latest_event_order_within_that_date() -> None:
    events = (
        _event(
            event_id="TLE000000001",
            status=TransactionStatus.LAUNCHED,
            effective_date=date(2026, 9, 3),
            event_order=1,
        ),
        _event(
            event_id="TLE000000002",
            status=TransactionStatus.PRICED,
            effective_date=date(2026, 9, 3),
            event_order=2,
        ),
    )

    _validate(events)

    assert (
        derive_transaction_status(
            "TXN000000001",
            events,
            as_of_date=date(2026, 9, 3),
        )
        is TransactionStatus.PRICED
    )
