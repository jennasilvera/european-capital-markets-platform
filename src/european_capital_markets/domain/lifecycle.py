"""Evidence-backed transaction lifecycle history."""

from dataclasses import dataclass
from datetime import date

from european_capital_markets.domain.entities import TransactionRecord
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    SourceRecord,
    validate_lineage_bundle,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    TransactionStatus,
)


@dataclass(frozen=True, slots=True)
class TransactionLifecycleEventRecord:
    """One evidence-backed status event in a transaction lifecycle."""

    event_id: str
    transaction_id: str
    status: TransactionStatus
    effective_date: date
    event_order: int
    evidence_ids: tuple[str, ...]
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.event_id,
            EntityType.TRANSACTION_LIFECYCLE_EVENT,
        )
        validate_identifier(
            self.transaction_id,
            EntityType.TRANSACTION,
        )

        if not isinstance(self.status, TransactionStatus):
            raise TypeError("status must be a TransactionStatus.")

        if (
            not isinstance(self.event_order, int)
            or isinstance(self.event_order, bool)
        ):
            raise TypeError("event_order must be an integer.")

        if self.event_order < 1:
            raise ValueError("event_order must be positive.")

        if not self.evidence_ids:
            raise ValueError(
                "Lifecycle events require source evidence."
            )

        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError(
                "evidence_ids must not contain duplicates."
            )

        for evidence_id in self.evidence_ids:
            validate_identifier(
                evidence_id,
                EntityType.EVIDENCE,
            )

        if self.notes is not None and not self.notes.strip():
            raise ValueError("notes must not be blank.")


def validate_lifecycle_bundle(
    transactions: tuple[TransactionRecord, ...],
    events: tuple[TransactionLifecycleEventRecord, ...],
    sources: tuple[SourceRecord, ...],
    evidence: tuple[EvidenceRecord, ...],
) -> None:
    """Validate lifecycle references, ordering slots, and evidence."""

    validate_lineage_bundle(
        sources=sources,
        evidence=evidence,
        observations=(),
    )

    transaction_ids = _unique_ids(
        transactions,
        "transaction_id",
    )
    _unique_ids(events, "event_id")

    evidence_ids = {
        evidence_record.evidence_id
        for evidence_record in evidence
    }

    ordering_slots: set[
        tuple[str, date, int]
    ] = set()
    for event in events:
        if event.transaction_id not in transaction_ids:
            raise ValueError(
                "Unknown transaction reference: "
                f"{event.transaction_id!r}"
            )

        for evidence_id in event.evidence_ids:
            if evidence_id not in evidence_ids:
                raise ValueError(
                    f"Unknown evidence reference: {evidence_id!r}"
                )

        ordering_slot = (
            event.transaction_id,
            event.effective_date,
            event.event_order,
        )

        if ordering_slot in ordering_slots:
            raise ValueError(
                "Duplicate lifecycle ordering slot for transaction "
                "and effective date."
            )

        ordering_slots.add(ordering_slot)



def derive_transaction_status(
    transaction_id: str,
    events: tuple[TransactionLifecycleEventRecord, ...],
    *,
    as_of_date: date | None = None,
) -> TransactionStatus | None:
    """Derive the latest known status at an optional historical cut-off."""

    validate_identifier(
        transaction_id,
        EntityType.TRANSACTION,
    )

    applicable = [
        event
        for event in events
        if event.transaction_id == transaction_id
        and (
            as_of_date is None
            or event.effective_date <= as_of_date
        )
    ]

    if not applicable:
        return None

    latest = max(
        applicable,
        key=lambda event: (
            event.effective_date,
            event.event_order,
        ),
    )

    return latest.status


def _unique_ids[T](
    records: tuple[T, ...],
    id_field: str,
) -> set[str]:
    identifiers: set[str] = set()

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in identifiers:
            raise ValueError(
                f"Duplicate identifier: {identifier!r}"
            )

        identifiers.add(identifier)

    return identifiers
