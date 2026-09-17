from datetime import date

import pytest

from european_capital_markets.domain.entities import (
    InstrumentRecord,
    TransactionRecord,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    SourceRecord,
)
from european_capital_markets.domain.participations import (
    ParticipationRecord,
    validate_participation_bundle,
)
from european_capital_markets.domain.parties import PartyRecord
from european_capital_markets.domain.taxonomy import (
    ParticipantRole,
    PartyType,
    ProductFamily,
    SourceTier,
    SourceType,
)


def _party(
    party_id: str = "PTY000000001",
) -> PartyRecord:
    return PartyRecord(
        party_id=party_id,
        party_type=PartyType.CORPORATE,
        canonical_name=f"Party {party_id}",
    )


def _transaction(
    transaction_id: str = "TXN000000001",
) -> TransactionRecord:
    return TransactionRecord(
        transaction_id=transaction_id,
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.IG_DCM,
    )


def _instrument(
    instrument_id: str = "INS000000001",
    transaction_id: str = "TXN000000001",
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=instrument_id,
        transaction_id=transaction_id,
    )


def _source() -> SourceRecord:
    return SourceRecord(
        source_id="SRC000000001",
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.OFFERING_DOCUMENT,
        publisher="Example Issuer plc",
        title="Offering Document",
        access_date=date(2026, 9, 17),
        url="https://example.invalid/offering",
    )


def _evidence(
    evidence_id: str = "EVD000000001",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_id="SRC000000001",
        locator="Transaction parties section",
    )


def _participation(
    *,
    participation_id: str = "PAR000000001",
    party_id: str = "PTY000000001",
    transaction_id: str = "TXN000000001",
    role: ParticipantRole = ParticipantRole.LEGAL_ISSUER,
    instrument_id: str | None = None,
    evidence_ids: tuple[str, ...] = ("EVD000000001",),
) -> ParticipationRecord:
    return ParticipationRecord(
        participation_id=participation_id,
        party_id=party_id,
        transaction_id=transaction_id,
        role=role,
        instrument_id=instrument_id,
        evidence_ids=evidence_ids,
    )


def _validate(
    participations: tuple[ParticipationRecord, ...],
    *,
    parties: tuple[PartyRecord, ...] | None = None,
    transactions: tuple[TransactionRecord, ...] | None = None,
    instruments: tuple[InstrumentRecord, ...] = (),
    evidence: tuple[EvidenceRecord, ...] | None = None,
) -> None:
    validate_participation_bundle(
        parties=parties or (_party(),),
        transactions=transactions or (_transaction(),),
        instruments=instruments,
        participations=participations,
        sources=(_source(),),
        evidence=evidence or (_evidence(),),
    )


def test_valid_transaction_level_participation() -> None:
    _validate((_participation(),))


def test_valid_instrument_level_participation() -> None:
    _validate(
        (
            _participation(
                instrument_id="INS000000001",
            ),
        ),
        instruments=(_instrument(),),
    )


def test_participation_requires_participation_identifier() -> None:
    with pytest.raises(ValueError, match="not PARTICIPATION"):
        _participation(
            participation_id="PTY000000001",
        )


def test_participation_requires_party_identifier() -> None:
    with pytest.raises(ValueError, match="not PARTY"):
        _participation(
            party_id="ISS000000001",
        )


def test_participation_requires_transaction_identifier() -> None:
    with pytest.raises(ValueError, match="not TRANSACTION"):
        _participation(
            transaction_id="ISS000000001",
        )


def test_optional_instrument_requires_instrument_identifier() -> None:
    with pytest.raises(ValueError, match="not INSTRUMENT"):
        _participation(
            instrument_id="TXN000000001",
        )


def test_role_must_be_controlled() -> None:
    with pytest.raises(TypeError, match="ParticipantRole"):
        _participation(
            role="LEGAL_ISSUER",  # type: ignore[arg-type]
        )


def test_participation_requires_evidence() -> None:
    with pytest.raises(ValueError, match="require source evidence"):
        _participation(
            evidence_ids=(),
        )


def test_bundle_rejects_unknown_party() -> None:
    participation = _participation(
        party_id="PTY000000002",
    )

    with pytest.raises(ValueError, match="Unknown party"):
        _validate((participation,))


def test_bundle_rejects_unknown_transaction() -> None:
    participation = _participation(
        transaction_id="TXN000000002",
    )

    with pytest.raises(ValueError, match="Unknown transaction"):
        _validate((participation,))


def test_bundle_rejects_unknown_instrument() -> None:
    participation = _participation(
        instrument_id="INS000000002",
    )

    with pytest.raises(ValueError, match="Unknown instrument"):
        _validate(
            (participation,),
            instruments=(_instrument(),),
        )


def test_instrument_must_belong_to_relationship_transaction() -> None:
    participation = _participation(
        transaction_id="TXN000000002",
        instrument_id="INS000000001",
    )

    with pytest.raises(ValueError, match="canonical parent transaction"):
        _validate(
            (participation,),
            transactions=(
                _transaction(),
                _transaction("TXN000000002"),
            ),
            instruments=(_instrument(),),
        )


def test_bundle_rejects_unknown_evidence() -> None:
    participation = _participation(
        evidence_ids=("EVD000000002",),
    )

    with pytest.raises(ValueError, match="Unknown evidence"):
        _validate((participation,))


def test_duplicate_semantic_relationship_is_rejected() -> None:
    first = _participation()
    second = _participation(
        participation_id="PAR000000002",
    )

    with pytest.raises(ValueError, match="consolidate supporting evidence"):
        _validate((first, second))


def test_same_party_can_hold_multiple_roles() -> None:
    first = _participation(
        role=ParticipantRole.LEGAL_ISSUER,
    )
    second = _participation(
        participation_id="PAR000000002",
        role=ParticipantRole.BORROWER,
    )

    _validate((first, second))


def test_multi_tranche_bond_supports_different_legal_issuers_and_guarantors() -> None:
    issuer_a = PartyRecord(
        party_id="PTY000000001",
        party_type=PartyType.SPECIAL_PURPOSE_VEHICLE,
        canonical_name="Issuer SPV A",
    )
    issuer_b = PartyRecord(
        party_id="PTY000000002",
        party_type=PartyType.SPECIAL_PURPOSE_VEHICLE,
        canonical_name="Issuer SPV B",
    )
    guarantor = PartyRecord(
        party_id="PTY000000003",
        party_type=PartyType.CORPORATE,
        canonical_name="Parent Guarantor plc",
    )

    transaction = TransactionRecord(
        transaction_id="TXN000000001",
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.IG_DCM,
    )
    five_year = InstrumentRecord(
        instrument_id="INS000000001",
        transaction_id="TXN000000001",
        instrument_label="5Y Notes",
    )
    ten_year = InstrumentRecord(
        instrument_id="INS000000002",
        transaction_id="TXN000000001",
        instrument_label="10Y Notes",
    )

    participations = (
        _participation(
            participation_id="PAR000000001",
            party_id="PTY000000001",
            role=ParticipantRole.LEGAL_ISSUER,
            instrument_id="INS000000001",
        ),
        _participation(
            participation_id="PAR000000002",
            party_id="PTY000000002",
            role=ParticipantRole.LEGAL_ISSUER,
            instrument_id="INS000000002",
        ),
        _participation(
            participation_id="PAR000000003",
            party_id="PTY000000003",
            role=ParticipantRole.GUARANTOR,
            instrument_id="INS000000001",
        ),
        _participation(
            participation_id="PAR000000004",
            party_id="PTY000000003",
            role=ParticipantRole.GUARANTOR,
            instrument_id="INS000000002",
        ),
    )

    validate_participation_bundle(
        parties=(issuer_a, issuer_b, guarantor),
        transactions=(transaction,),
        instruments=(five_year, ten_year),
        participations=participations,
        sources=(_source(),),
        evidence=(_evidence(),),
    )


def test_ecm_secondary_block_supports_nonissuer_selling_shareholder() -> None:
    seller = PartyRecord(
        party_id="PTY000000001",
        party_type=PartyType.FUND,
        canonical_name="Example Sponsor Fund",
    )
    transaction = TransactionRecord(
        transaction_id="TXN000000001",
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.ECM,
        transaction_label="Secondary Block Trade",
    )
    participation = _participation(
        party_id="PTY000000001",
        role=ParticipantRole.SELLING_SHAREHOLDER,
    )

    validate_participation_bundle(
        parties=(seller,),
        transactions=(transaction,),
        instruments=(),
        participations=(participation,),
        sources=(_source(),),
        evidence=(_evidence(),),
    )


def test_sponsor_backed_leveraged_financing_supports_distinct_party_roles() -> None:
    sponsor = PartyRecord(
        party_id="PTY000000001",
        party_type=PartyType.FUND,
        canonical_name="Example Sponsor Fund",
    )
    acquisition_vehicle = PartyRecord(
        party_id="PTY000000002",
        party_type=PartyType.SPECIAL_PURPOSE_VEHICLE,
        canonical_name="Acquisition Bidco",
    )
    guarantor = PartyRecord(
        party_id="PTY000000003",
        party_type=PartyType.CORPORATE,
        canonical_name="Operating Company",
    )
    transaction = TransactionRecord(
        transaction_id="TXN000000001",
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.LEVERAGED_FINANCE,
    )

    participations = (
        _participation(
            participation_id="PAR000000001",
            party_id="PTY000000001",
            role=ParticipantRole.SPONSOR,
        ),
        _participation(
            participation_id="PAR000000002",
            party_id="PTY000000002",
            role=ParticipantRole.ACQUISITION_VEHICLE,
        ),
        _participation(
            participation_id="PAR000000003",
            party_id="PTY000000002",
            role=ParticipantRole.BORROWER,
        ),
        _participation(
            participation_id="PAR000000004",
            party_id="PTY000000003",
            role=ParticipantRole.GUARANTOR,
        ),
    )

    validate_participation_bundle(
        parties=(sponsor, acquisition_vehicle, guarantor),
        transactions=(transaction,),
        instruments=(),
        participations=participations,
        sources=(_source(),),
        evidence=(_evidence(),),
    )


def test_multiple_parties_may_hold_same_role() -> None:
    first_borrower = _party("PTY000000001")
    second_borrower = _party("PTY000000002")

    first = _participation(
        participation_id="PAR000000001",
        party_id="PTY000000001",
        role=ParticipantRole.BORROWER,
    )
    second = _participation(
        participation_id="PAR000000002",
        party_id="PTY000000002",
        role=ParticipantRole.BORROWER,
    )

    _validate(
        (first, second),
        parties=(first_borrower, second_borrower),
    )


def test_transaction_and_instrument_level_same_role_are_distinct() -> None:
    transaction_level = _participation(
        participation_id="PAR000000001",
        role=ParticipantRole.GUARANTOR,
    )
    instrument_level = _participation(
        participation_id="PAR000000002",
        role=ParticipantRole.GUARANTOR,
        instrument_id="INS000000001",
    )

    _validate(
        (transaction_level, instrument_level),
        instruments=(_instrument(),),
    )
