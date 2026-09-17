from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
    validate_lineage_bundle,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)

VERIFIED_AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _source() -> SourceRecord:
    return SourceRecord(
        source_id="SRC000000001",
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.ISSUER_ANNOUNCEMENT,
        publisher="Example Issuer plc",
        title="Pricing Announcement",
        publication_date=date(2026, 9, 16),
        access_date=date(2026, 9, 16),
        url="https://example.invalid/pricing",
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="EVD000000001",
        source_id="SRC000000001",
        locator="Pricing terms / Offer price",
    )


def _disclosed_price() -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="ecm.offer_price",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PRIMARY_VERIFIED,
        verified_at=VERIFIED_AT,
        value=Decimal("25.00"),
        value_class=ValueClass.DISCLOSED,
        unit="price_per_share",
        currency="EUR",
        evidence_ids=("EVD000000001",),
    )


def test_valid_source_record() -> None:
    source = _source()

    assert source.source_type is SourceType.ISSUER_ANNOUNCEMENT
    assert source.tier is SourceTier.PRIMARY_TRANSACTION_OR_ISSUER


def test_valid_disclosed_observation() -> None:
    observation = _disclosed_price()

    assert observation.value == Decimal("25.00")
    assert observation.value_class is ValueClass.DISCLOSED
    assert observation.verified_at == VERIFIED_AT


def test_disclosed_value_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires supporting evidence"):
        ObservationRecord(
            observation_id="OBS000000001",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="transaction.size",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            verified_at=VERIFIED_AT,
            value=Decimal("500000000"),
            value_class=ValueClass.DISCLOSED,
            currency="EUR",
        )


def test_calculated_value_requires_inputs_and_methodology() -> None:
    with pytest.raises(ValueError, match="requires input observations"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.discount",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PENDING,
            value=Decimal("0.05"),
            value_class=ValueClass.CALCULATED,
        )


def test_missing_state_and_value_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.book_coverage",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.UNAVAILABLE,
            value=Decimal("2.0"),
            missing_state=MissingDataState.UNAVAILABLE,
        )


def test_not_disclosed_requires_evidence() -> None:
    with pytest.raises(ValueError, match="NOT_DISCLOSED requires evidence"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.book_coverage",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            verified_at=VERIFIED_AT,
            missing_state=MissingDataState.NOT_DISCLOSED,
        )


def test_unavailable_requires_unavailable_verification() -> None:
    with pytest.raises(ValueError, match="UNAVAILABLE verification"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.book_coverage",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PENDING,
            missing_state=MissingDataState.UNAVAILABLE,
        )


def test_pending_missing_state_requires_pending_verification() -> None:
    with pytest.raises(ValueError, match="requires PENDING"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.book_coverage",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.UNAVAILABLE,
            missing_state=MissingDataState.PENDING_VERIFICATION,
        )


def test_subject_identifier_must_match_subject_type() -> None:
    with pytest.raises(ValueError, match="not ISSUER"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.ISSUER,
            subject_id="TXN000000001",
            field_name="issuer.country",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PENDING,
            missing_state=MissingDataState.PENDING_VERIFICATION,
        )


def test_governance_record_cannot_be_observation_subject() -> None:
    with pytest.raises(ValueError, match="not an observable business subject"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.SOURCE,
            subject_id="SRC000000001",
            field_name="source.quality",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PENDING,
            missing_state=MissingDataState.PENDING_VERIFICATION,
        )


def test_currency_must_be_upper_case_three_letter_code() -> None:
    with pytest.raises(ValueError, match="three-letter"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="transaction.size",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            verified_at=VERIFIED_AT,
            value=Decimal("100"),
            value_class=ValueClass.DISCLOSED,
            currency="eur",
            evidence_ids=("EVD000000001",),
        )


def test_verified_observation_requires_timestamp() -> None:
    with pytest.raises(ValueError, match="verified_at"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="transaction.size",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            value=Decimal("100"),
            value_class=ValueClass.DISCLOSED,
            evidence_ids=("EVD000000001",),
        )


def test_verified_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="transaction.size",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            verified_at=datetime(2026, 9, 16, 12, 0),
            value=Decimal("100"),
            value_class=ValueClass.DISCLOSED,
            evidence_ids=("EVD000000001",),
        )


def test_calculated_value_cannot_claim_primary_source_verification() -> None:
    with pytest.raises(ValueError, match="source-verification"):
        ObservationRecord(
            observation_id="OBS000000002",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="ecm.discount",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PRIMARY_VERIFIED,
            verified_at=VERIFIED_AT,
            value=Decimal("0.05"),
            value_class=ValueClass.CALCULATED,
            input_observation_ids=("OBS000000001",),
            derivation_ref="methodology/ecm-discount-v1",
        )


def test_valid_lineage_bundle() -> None:
    calculated = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="ecm.offer_price_eur",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.CROSS_VERIFIED,
        verified_at=VERIFIED_AT,
        value=Decimal("25.00"),
        value_class=ValueClass.CALCULATED,
        currency="EUR",
        input_observation_ids=("OBS000000001",),
        derivation_ref="methodology/currency-normalization-v1",
    )

    validate_lineage_bundle(
        sources=(_source(),),
        evidence=(_evidence(),),
        observations=(_disclosed_price(), calculated),
    )


def test_bundle_rejects_unknown_source() -> None:
    evidence = EvidenceRecord(
        evidence_id="EVD000000001",
        source_id="SRC000000002",
        locator="Pricing terms / Offer price",
    )

    with pytest.raises(ValueError, match="Unknown source"):
        validate_lineage_bundle(
            sources=(_source(),),
            evidence=(evidence,),
            observations=(),
        )


def test_bundle_rejects_unknown_evidence() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="ecm.offer_price",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PRIMARY_VERIFIED,
        verified_at=VERIFIED_AT,
        value=Decimal("25.00"),
        value_class=ValueClass.DISCLOSED,
        currency="EUR",
        evidence_ids=("EVD000000002",),
    )

    with pytest.raises(ValueError, match="Unknown evidence"):
        validate_lineage_bundle(
            sources=(_source(),),
            evidence=(_evidence(),),
            observations=(observation,),
        )


def test_bundle_rejects_unknown_input_observation() -> None:
    calculated = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="ecm.discount",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.05"),
        value_class=ValueClass.CALCULATED,
        input_observation_ids=("OBS000000999",),
        derivation_ref="methodology/ecm-discount-v1",
    )

    with pytest.raises(ValueError, match="Unknown input observation"):
        validate_lineage_bundle(
            sources=(),
            evidence=(),
            observations=(calculated,),
        )


def test_bundle_rejects_duplicate_identifiers() -> None:
    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_lineage_bundle(
            sources=(_source(), _source()),
            evidence=(),
            observations=(),
        )


def test_bundle_rejects_calculation_cycles() -> None:
    first = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="metric.one",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        value=Decimal("1"),
        value_class=ValueClass.CALCULATED,
        input_observation_ids=("OBS000000002",),
        derivation_ref="methodology/test",
    )
    second = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="metric.two",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        value=Decimal("2"),
        value_class=ValueClass.CALCULATED,
        input_observation_ids=("OBS000000001",),
        derivation_ref="methodology/test",
    )

    with pytest.raises(ValueError, match="Cycle detected"):
        validate_lineage_bundle(
            sources=(),
            evidence=(),
            observations=(first, second),
        )


def test_unverified_observation_cannot_have_verified_timestamp() -> None:
    with pytest.raises(ValueError, match="unverified observation"):
        ObservationRecord(
            observation_id="OBS000000003",
            subject_type=EntityType.TRANSACTION,
            subject_id="TXN000000001",
            field_name="transaction.size",
            as_of_date=date(2026, 9, 16),
            verification_state=VerificationState.PENDING,
            verified_at=VERIFIED_AT,
            missing_state=MissingDataState.PENDING_VERIFICATION,
        )


def test_party_is_valid_observation_subject() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000010",
        subject_type=EntityType.PARTY,
        subject_id="PTY000000001",
        field_name="party.country",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    assert observation.subject_type is EntityType.PARTY
    assert observation.subject_id == "PTY000000001"


def test_party_subject_requires_party_identifier() -> None:
    with pytest.raises(ValueError, match="not PARTY"):
        ObservationRecord(
            observation_id="OBS000000011",
            subject_type=EntityType.PARTY,
            subject_id="ISS000000001",
            field_name="party.country",
            as_of_date=date(2026, 9, 17),
            verification_state=VerificationState.PENDING,
            missing_state=MissingDataState.PENDING_VERIFICATION,
        )
