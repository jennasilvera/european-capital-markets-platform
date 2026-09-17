"""Canonical party participation relationships for financing events."""

from dataclasses import dataclass

from european_capital_markets.domain.entities import (
    InstrumentRecord,
    TransactionRecord,
)
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    SourceRecord,
    validate_lineage_bundle,
)
from european_capital_markets.domain.parties import PartyRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    ParticipantRole,
)


@dataclass(frozen=True, slots=True)
class ParticipationRecord:
    """Canonical party role in a transaction or specific instrument."""

    participation_id: str
    party_id: str
    transaction_id: str
    role: ParticipantRole
    evidence_ids: tuple[str, ...]
    instrument_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.participation_id,
            EntityType.PARTICIPATION,
        )
        validate_identifier(self.party_id, EntityType.PARTY)
        validate_identifier(
            self.transaction_id,
            EntityType.TRANSACTION,
        )

        if self.instrument_id is not None:
            validate_identifier(
                self.instrument_id,
                EntityType.INSTRUMENT,
            )

        if not isinstance(self.role, ParticipantRole):
            raise TypeError("role must be a ParticipantRole.")

        if not self.evidence_ids:
            raise ValueError(
                "Participation records require source evidence."
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

        if self.notes is not None:
            _require_non_blank(self.notes, "notes")


def validate_participation_bundle(
    parties: tuple[PartyRecord, ...],
    transactions: tuple[TransactionRecord, ...],
    instruments: tuple[InstrumentRecord, ...],
    participations: tuple[ParticipationRecord, ...],
    sources: tuple[SourceRecord, ...],
    evidence: tuple[EvidenceRecord, ...],
) -> None:
    """Validate relationship references, evidence, and semantic uniqueness."""

    validate_lineage_bundle(
        sources=sources,
        evidence=evidence,
        observations=(),
    )

    party_ids = _unique_ids(parties, "party_id")
    transaction_by_id = _index_unique(
        transactions,
        "transaction_id",
    )
    instrument_by_id = _index_unique(
        instruments,
        "instrument_id",
    )
    _unique_ids(participations, "participation_id")
    evidence_ids = {
        evidence_record.evidence_id
        for evidence_record in evidence
    }

    semantic_keys: set[
        tuple[
            str,
            str,
            str | None,
            ParticipantRole,
        ]
    ] = set()

    for participation in participations:
        if participation.party_id not in party_ids:
            raise ValueError(
                f"Unknown party reference: {participation.party_id!r}"
            )

        if participation.transaction_id not in transaction_by_id:
            raise ValueError(
                "Unknown transaction reference: "
                f"{participation.transaction_id!r}"
            )

        if participation.instrument_id is not None:
            instrument = instrument_by_id.get(
                participation.instrument_id
            )

            if instrument is None:
                raise ValueError(
                    "Unknown instrument reference: "
                    f"{participation.instrument_id!r}"
                )

            if (
                instrument.transaction_id
                != participation.transaction_id
            ):
                raise ValueError(
                    "Instrument participation transaction does not "
                    "match the instrument's canonical parent transaction."
                )

        for evidence_id in participation.evidence_ids:
            if evidence_id not in evidence_ids:
                raise ValueError(
                    f"Unknown evidence reference: {evidence_id!r}"
                )

        semantic_key = (
            participation.party_id,
            participation.transaction_id,
            participation.instrument_id,
            participation.role,
        )

        if semantic_key in semantic_keys:
            raise ValueError(
                "Duplicate participation relationship; "
                "consolidate supporting evidence."
            )

        semantic_keys.add(semantic_key)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")


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


def _index_unique[T](
    records: tuple[T, ...],
    id_field: str,
) -> dict[str, T]:
    index: dict[str, T] = {}

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in index:
            raise ValueError(
                f"Duplicate identifier: {identifier!r}"
            )

        index[identifier] = record

    return index
