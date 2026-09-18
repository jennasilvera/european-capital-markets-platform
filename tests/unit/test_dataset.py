from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.entities import (
    InstrumentRecord,
    IssuerRecord,
    TransactionRecord,
)
from european_capital_markets.domain.issuer_identity import (
    IssuerIdentifierRecord,
)
from european_capital_markets.domain.lifecycle import (
    TransactionLifecycleEventRecord,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
)
from european_capital_markets.domain.participations import (
    ParticipationRecord,
)
from european_capital_markets.domain.parties import PartyRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
    MarketSeriesType,
    ParticipantRole,
    PartyType,
    ProductFamily,
    SourceTier,
    SourceType,
    TransactionStatus,
    ValueClass,
    VerificationState,
)


def _source() -> SourceRecord:
    return SourceRecord(
        source_id="SRC000000001",
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.OFFERING_DOCUMENT,
        publisher="Example Issuer plc",
        title="Canonical transaction source",
        access_date=date(2026, 9, 17),
        url="https://example.invalid/canonical-source",
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="EVD000000001",
        source_id="SRC000000001",
        locator="Canonical transaction evidence",
    )


def _fx_observation() -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.8650"),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://market-data-assumption",
    )


def _dataset() -> CanonicalDataset:
    return CanonicalDataset(
        issuers=(
            IssuerRecord(
                issuer_id="ISS000000001",
                canonical_name="Example Issuer plc",
            ),
        ),
        transactions=(
            TransactionRecord(
                transaction_id="TXN000000001",
                primary_issuer_id="ISS000000001",
                product_family=ProductFamily.IG_DCM,
            ),
        ),
        instruments=(
            InstrumentRecord(
                instrument_id="INS000000001",
                transaction_id="TXN000000001",
            ),
        ),
        issuer_identifiers=(
            IssuerIdentifierRecord(
                issuer_id="ISS000000001",
                identifier_type=IssuerIdentifierType.TICKER,
                identifier_value="EXM",
                scope_type=IdentifierScopeType.TRADING_VENUE,
                scope_value="XLON",
                evidence_ids=("EVD000000001",),
            ),
        ),
        parties=(
            PartyRecord(
                party_id="PTY000000001",
                party_type=PartyType.CORPORATE,
                linked_issuer_id="ISS000000001",
            ),
        ),
        participations=(
            ParticipationRecord(
                participation_id="PAR000000001",
                party_id="PTY000000001",
                transaction_id="TXN000000001",
                role=ParticipantRole.LEGAL_ISSUER,
                evidence_ids=("EVD000000001",),
            ),
        ),
        lifecycle_events=(
            TransactionLifecycleEventRecord(
                event_id="TLE000000001",
                transaction_id="TXN000000001",
                status=TransactionStatus.PRICED,
                effective_date=date(2026, 9, 17),
                event_order=1,
                evidence_ids=("EVD000000001",),
            ),
        ),
        market_series=(
            MarketSeriesRecord(
                market_series_id="MKS000000001",
                series_type=MarketSeriesType.FX_REFERENCE_RATE,
                series_label="EUR/GBP reference rate",
            ),
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000001",
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
        sources=(_source(),),
        evidence=(_evidence(),),
        observations=(_fx_observation(),),
    )


def _assumed_observation(
    subject_type: EntityType,
    subject_id: str,
) -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000001",
        subject_type=subject_type,
        subject_id=subject_id,
        field_name="test.value",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value="test",
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://subject-reference",
    )


def test_empty_canonical_dataset_is_valid() -> None:
    validate_canonical_dataset(CanonicalDataset())


def test_valid_mixed_canonical_dataset() -> None:
    validate_canonical_dataset(_dataset())


@pytest.mark.parametrize(
    ("subject_type", "subject_id"),
    (
        (EntityType.ISSUER, "ISS000000001"),
        (EntityType.PARTY, "PTY000000001"),
        (EntityType.PARTICIPATION, "PAR000000001"),
        (EntityType.TRANSACTION, "TXN000000001"),
        (EntityType.INSTRUMENT, "INS000000001"),
        (EntityType.MARKET_SERIES, "MKS000000001"),
    ),
)
def test_observation_accepts_existing_concrete_subject(
    subject_type: EntityType,
    subject_id: str,
) -> None:
    if subject_type is EntityType.MARKET_SERIES:
        observation = _fx_observation()
    else:
        observation = _assumed_observation(
            subject_type,
            subject_id,
        )

    dataset = replace(
        _dataset(),
        observations=(observation,),
    )

    validate_canonical_dataset(dataset)


@pytest.mark.parametrize(
    ("subject_type", "subject_id"),
    (
        (EntityType.ISSUER, "ISS000000002"),
        (EntityType.PARTY, "PTY000000002"),
        (EntityType.PARTICIPATION, "PAR000000002"),
        (EntityType.TRANSACTION, "TXN000000002"),
        (EntityType.INSTRUMENT, "INS000000002"),
        (EntityType.MARKET_SERIES, "MKS000000002"),
    ),
)
def test_observation_requires_existing_concrete_subject(
    subject_type: EntityType,
    subject_id: str,
) -> None:
    dataset = replace(
        _dataset(),
        observations=(
            _assumed_observation(
                subject_type,
                subject_id,
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match=(
            "Unknown observation subject reference: "
            f"{subject_type.value} {subject_id!r}"
        ),
    ):
        validate_canonical_dataset(dataset)


def test_fx_definition_requires_existing_market_series() -> None:
    dataset = replace(
        _dataset(),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000002",
                base_currency="EUR",
                quote_currency="USD",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="references unknown market series",
    ):
        validate_canonical_dataset(dataset)


def test_participation_requires_existing_party() -> None:
    dataset = replace(
        _dataset(),
        participations=(
            ParticipationRecord(
                participation_id="PAR000000001",
                party_id="PTY000000002",
                transaction_id="TXN000000001",
                role=ParticipantRole.LEGAL_ISSUER,
                evidence_ids=("EVD000000001",),
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown party reference",
    ):
        validate_canonical_dataset(dataset)


def test_lifecycle_event_requires_existing_transaction() -> None:
    dataset = replace(
        _dataset(),
        lifecycle_events=(
            TransactionLifecycleEventRecord(
                event_id="TLE000000001",
                transaction_id="TXN000000002",
                status=TransactionStatus.PRICED,
                effective_date=date(2026, 9, 17),
                event_order=1,
                evidence_ids=("EVD000000001",),
            ),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown transaction reference",
    ):
        validate_canonical_dataset(dataset)
