"""Integration tests for transactional canonical dataset persistence."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from european_capital_markets.domain.dataset import CanonicalDataset
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
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
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
    MissingDataState,
    ParticipantRole,
    PartyType,
    ProductFamily,
    SourceTier,
    SourceType,
    TransactionStatus,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence import (
    CanonicalRepository,
    load_canonical_dataset,
    persist_canonical_dataset,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)

CANONICAL_TABLES = (
    "observation_inputs",
    "observation_evidence",
    "transaction_lifecycle_event_evidence",
    "participation_evidence",
    "issuer_identifier_evidence",
    "observations",
    "observation_subjects",
    "transaction_lifecycle_events",
    "issuer_identifiers",
    "evidence",
    "sources",
    "fx_reference_rate_definitions",
    "policy_rate_definitions",
    "government_yield_definitions",
    "swap_rate_definitions",
    "credit_spread_definitions",
    "equity_index_definitions",
    "volatility_index_definitions",
    "market_series",
    "participations",
    "instruments",
    "transactions",
    "parties",
    "issuers",
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Return the migrated PostgreSQL integration database engine."""

    if DATABASE_URL is None:
        pytest.skip("DATABASE_URL is required.")

    database_engine = sa.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    """Isolate committed writer tests from every other integration test."""

    _truncate_canonical_tables(engine)

    try:
        yield
    finally:
        _truncate_canonical_tables(engine)


def _truncate_canonical_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                f"""
                TRUNCATE TABLE
                    {", ".join(CANONICAL_TABLES)}
                RESTART IDENTITY CASCADE
                """
            )
        )


def _canonical_id(prefix: str, sequence: int) -> str:
    return f"{prefix}{sequence:09d}"


def _dataset(sequence: int) -> CanonicalDataset:
    issuer_id = _canonical_id("ISS", sequence)
    transaction_id = _canonical_id("TXN", sequence)
    instrument_id = _canonical_id("INS", sequence)
    party_id = _canonical_id("PTY", sequence)
    participation_id = _canonical_id("PAR", sequence)
    event_id = _canonical_id("TLE", sequence)
    market_series_id = _canonical_id("MKS", sequence)
    source_id = _canonical_id("SRC", sequence)

    evidence_one = _canonical_id(
        "EVD",
        sequence * 10 + 1,
    )
    evidence_two = _canonical_id(
        "EVD",
        sequence * 10 + 2,
    )

    disclosed_observation_id = _canonical_id(
        "OBS",
        sequence * 10 + 1,
    )
    calculated_observation_id = _canonical_id(
        "OBS",
        sequence * 10 + 2,
    )
    missing_observation_id = _canonical_id(
        "OBS",
        sequence * 10 + 3,
    )

    return CanonicalDataset(
        issuers=(
            IssuerRecord(
                issuer_id=issuer_id,
                canonical_name=f"Example Issuer {sequence} plc",
            ),
        ),
        transactions=(
            TransactionRecord(
                transaction_id=transaction_id,
                primary_issuer_id=issuer_id,
                product_family=ProductFamily.IG_DCM,
                transaction_label="Canonical financing event",
            ),
        ),
        instruments=(
            InstrumentRecord(
                instrument_id=instrument_id,
                transaction_id=transaction_id,
                instrument_label="Senior notes",
            ),
        ),
        issuer_identifiers=(
            IssuerIdentifierRecord(
                issuer_id=issuer_id,
                identifier_type=IssuerIdentifierType.TICKER,
                identifier_value=f"EXM{sequence}",
                scope_type=IdentifierScopeType.TRADING_VENUE,
                scope_value="XLON",
                evidence_ids=(
                    evidence_one,
                    evidence_two,
                ),
                notes="Canonical ticker assignment",
            ),
        ),
        parties=(
            PartyRecord(
                party_id=party_id,
                party_type=PartyType.CORPORATE,
                linked_issuer_id=issuer_id,
            ),
        ),
        participations=(
            ParticipationRecord(
                participation_id=participation_id,
                party_id=party_id,
                transaction_id=transaction_id,
                role=ParticipantRole.LEGAL_ISSUER,
                evidence_ids=(
                    evidence_two,
                    evidence_one,
                ),
                notes="Legal issuer participation",
            ),
        ),
        lifecycle_events=(
            TransactionLifecycleEventRecord(
                event_id=event_id,
                transaction_id=transaction_id,
                status=TransactionStatus.PRICED,
                effective_date=date(2026, 9, 17),
                event_order=1,
                evidence_ids=(
                    evidence_one,
                    evidence_two,
                ),
                notes="Transaction priced",
            ),
        ),
        market_series=(
            MarketSeriesRecord(
                market_series_id=market_series_id,
                series_type=MarketSeriesType.FX_REFERENCE_RATE,
                series_label="EUR/GBP reference rate",
            ),
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id=market_series_id,
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
        sources=(
            SourceRecord(
                source_id=source_id,
                tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
                source_type=SourceType.OFFERING_DOCUMENT,
                publisher=f"Example Issuer {sequence} plc",
                title="Canonical transaction source",
                access_date=date(2026, 9, 18),
                document_date=date(2026, 9, 17),
                url="https://example.invalid/canonical-source",
                document_version="final",
                notes="Writer integration fixture",
            ),
        ),
        evidence=(
            EvidenceRecord(
                evidence_id=evidence_one,
                source_id=source_id,
                locator="Pricing terms / FX reference",
                label="Primary evidence",
            ),
            EvidenceRecord(
                evidence_id=evidence_two,
                source_id=source_id,
                locator="Transaction parties",
                label="Relationship evidence",
            ),
        ),
        observations=(
            ObservationRecord(
                observation_id=disclosed_observation_id,
                subject_type=EntityType.MARKET_SERIES,
                subject_id=market_series_id,
                field_name="market_series.fx_rate",
                as_of_date=date(2026, 9, 17),
                verification_state=VerificationState.PRIMARY_VERIFIED,
                verified_at=datetime(
                    2026,
                    9,
                    17,
                    12,
                    0,
                    tzinfo=UTC,
                ),
                value=Decimal("0.8650"),
                value_class=ValueClass.DISCLOSED,
                evidence_ids=(
                    evidence_two,
                    evidence_one,
                ),
            ),
            ObservationRecord(
                observation_id=calculated_observation_id,
                subject_type=EntityType.MARKET_SERIES,
                subject_id=market_series_id,
                field_name="market_series.fx_rate",
                as_of_date=date(2026, 9, 18),
                verification_state=VerificationState.PENDING,
                value=Decimal("0.8660"),
                value_class=ValueClass.CALCULATED,
                input_observation_ids=(
                    disclosed_observation_id,
                ),
                derivation_ref="tests/persistence-writer/fx-derived",
            ),
            ObservationRecord(
                observation_id=missing_observation_id,
                subject_type=EntityType.MARKET_SERIES,
                subject_id=market_series_id,
                field_name="market_series.fx_rate",
                as_of_date=date(2026, 9, 19),
                verification_state=VerificationState.PENDING,
                missing_state=MissingDataState.PENDING_VERIFICATION,
                notes="Awaiting next market observation",
            ),
        ),
    )


def _count(engine: Engine, table_name: str) -> int:
    if table_name not in CANONICAL_TABLES:
        raise ValueError(f"Unknown canonical table: {table_name!r}")

    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                f"SELECT count(*) FROM {table_name}"
            )
        ).scalar_one()


def test_complete_dataset_persists_as_one_canonical_unit(
    engine: Engine,
) -> None:
    """Every frozen record and lineage junction reaches PostgreSQL."""

    dataset = _dataset(1)

    persist_canonical_dataset(engine, dataset)

    expected_counts = {
        "issuers": 1,
        "parties": 1,
        "transactions": 1,
        "instruments": 1,
        "participations": 1,
        "market_series": 1,
        "fx_reference_rate_definitions": 1,
        "sources": 1,
        "evidence": 2,
        "issuer_identifiers": 1,
        "transaction_lifecycle_events": 1,
        "observation_subjects": 6,
        "observations": 3,
        "issuer_identifier_evidence": 2,
        "participation_evidence": 2,
        "transaction_lifecycle_event_evidence": 2,
        "observation_evidence": 2,
        "observation_inputs": 1,
    }

    assert {
        table: _count(engine, table)
        for table in expected_counts
    } == expected_counts

    with engine.connect() as connection:
        observation_rows = connection.execute(
            sa.text(
                """
                SELECT
                    observation_id,
                    scalar_type,
                    decimal_value,
                    value_class,
                    missing_state
                FROM observations
                ORDER BY observation_id
                """
            )
        ).mappings().all()

        assert observation_rows == [
            {
                "observation_id": "OBS000000011",
                "scalar_type": "DECIMAL",
                "decimal_value": Decimal("0.8650"),
                "value_class": "DISCLOSED",
                "missing_state": None,
            },
            {
                "observation_id": "OBS000000012",
                "scalar_type": "DECIMAL",
                "decimal_value": Decimal("0.8660"),
                "value_class": "CALCULATED",
                "missing_state": None,
            },
            {
                "observation_id": "OBS000000013",
                "scalar_type": None,
                "decimal_value": None,
                "value_class": None,
                "missing_state": "PENDING_VERIFICATION",
            },
        ]

        observation_evidence = connection.execute(
            sa.text(
                """
                SELECT
                    evidence_id,
                    evidence_ordinal
                FROM observation_evidence
                WHERE observation_id = 'OBS000000011'
                ORDER BY evidence_ordinal
                """
            )
        ).all()

        assert observation_evidence == [
            ("EVD000000012", 0),
            ("EVD000000011", 1),
        ]

        input_lineage = connection.execute(
            sa.text(
                """
                SELECT
                    input_observation_id,
                    input_ordinal
                FROM observation_inputs
                WHERE derived_observation_id = 'OBS000000012'
                ORDER BY input_ordinal
                """
            )
        ).all()

        assert input_lineage == [
            ("OBS000000011", 0),
        ]

        identifier_evidence = connection.execute(
            sa.text(
                """
                SELECT
                    iie.evidence_id,
                    iie.evidence_ordinal
                FROM issuer_identifier_evidence AS iie
                JOIN issuer_identifiers AS ii
                  ON ii.issuer_identifier_row_id
                   = iie.issuer_identifier_row_id
                WHERE ii.issuer_id = 'ISS000000001'
                ORDER BY iie.evidence_ordinal
                """
            )
        ).all()

        assert identifier_evidence == [
            ("EVD000000011", 0),
            ("EVD000000012", 1),
        ]



def test_complete_dataset_round_trips_unchanged(
    engine: Engine,
) -> None:
    """Persisted governed records reconstruct without information loss."""

    dataset = _dataset(3)

    persist_canonical_dataset(engine, dataset)

    reconstructed = load_canonical_dataset(engine)

    assert reconstructed == dataset




def test_repository_returns_canonical_issuer(
    engine: Engine,
) -> None:
    """Permanent issuer IDs resolve to validated frozen issuer records."""

    dataset = _dataset(4)
    persist_canonical_dataset(engine, dataset)

    repository = CanonicalRepository(engine)

    assert repository.get_issuer(
        dataset.issuers[0].issuer_id
    ) == dataset.issuers[0]

    assert repository.get_issuer(
        "ISS999999999"
    ) is None


def test_repository_resolves_identifier_as_of_date(
    engine: Engine,
) -> None:
    """Identifier access preserves half-open assignment validity."""

    dataset = _dataset(5)
    identifier = dataset.issuer_identifiers[0]

    bounded_identifier = IssuerIdentifierRecord(
        issuer_id=identifier.issuer_id,
        identifier_type=identifier.identifier_type,
        identifier_value=identifier.identifier_value,
        scope_type=identifier.scope_type,
        evidence_ids=identifier.evidence_ids,
        scope_value=identifier.scope_value,
        assignment_valid_from=date(2026, 1, 1),
        assignment_valid_to=date(2027, 1, 1),
        notes=identifier.notes,
    )

    dataset = CanonicalDataset(
        issuers=dataset.issuers,
        transactions=dataset.transactions,
        instruments=dataset.instruments,
        issuer_identifiers=(bounded_identifier,),
        parties=dataset.parties,
        participations=dataset.participations,
        lifecycle_events=dataset.lifecycle_events,
        market_series=dataset.market_series,
        fx_reference_rates=dataset.fx_reference_rates,
        sources=dataset.sources,
        evidence=dataset.evidence,
        observations=dataset.observations,
    )

    persist_canonical_dataset(engine, dataset)

    repository = CanonicalRepository(engine)

    query = {
        "identifier_type": bounded_identifier.identifier_type,
        "identifier_value": bounded_identifier.identifier_value,
        "scope_type": bounded_identifier.scope_type,
        "scope_value": bounded_identifier.scope_value,
    }

    assert repository.resolve_issuer_identifier(
        **query,
        as_of_date=date(2025, 12, 31),
    ) is None

    assert repository.resolve_issuer_identifier(
        **query,
        as_of_date=date(2026, 1, 1),
    ) == bounded_identifier.issuer_id

    assert repository.resolve_issuer_identifier(
        **query,
        as_of_date=date(2026, 12, 31),
    ) == bounded_identifier.issuer_id

    assert repository.resolve_issuer_identifier(
        **query,
        as_of_date=date(2027, 1, 1),
    ) is None


def test_repository_derives_transaction_status_as_of_date(
    engine: Engine,
) -> None:
    """Status queries delegate historical interpretation to domain logic."""

    dataset = _dataset(6)
    priced_event = dataset.lifecycle_events[0]

    launched_event = TransactionLifecycleEventRecord(
        event_id="TLE000000061",
        transaction_id=priced_event.transaction_id,
        status=TransactionStatus.LAUNCHED,
        effective_date=date(2026, 9, 16),
        event_order=1,
        evidence_ids=priced_event.evidence_ids,
        notes="Transaction launched",
    )

    dataset = CanonicalDataset(
        issuers=dataset.issuers,
        transactions=dataset.transactions,
        instruments=dataset.instruments,
        issuer_identifiers=dataset.issuer_identifiers,
        parties=dataset.parties,
        participations=dataset.participations,
        lifecycle_events=(
            launched_event,
            priced_event,
        ),
        market_series=dataset.market_series,
        fx_reference_rates=dataset.fx_reference_rates,
        sources=dataset.sources,
        evidence=dataset.evidence,
        observations=dataset.observations,
    )

    persist_canonical_dataset(engine, dataset)

    repository = CanonicalRepository(engine)
    transaction_id = dataset.transactions[0].transaction_id

    assert repository.get_transaction_status(
        transaction_id,
        as_of_date=date(2026, 9, 15),
    ) is None

    assert repository.get_transaction_status(
        transaction_id,
        as_of_date=date(2026, 9, 16),
    ) is TransactionStatus.LAUNCHED

    assert repository.get_transaction_status(
        transaction_id,
        as_of_date=date(2026, 9, 17),
    ) is TransactionStatus.PRICED

    assert repository.get_transaction_status(
        transaction_id
    ) is TransactionStatus.PRICED



def test_database_failure_rolls_back_complete_dataset(
    engine: Engine,
) -> None:
    """A late relational failure cannot leave earlier entities behind."""

    dataset = _dataset(2)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO sources (
                    source_id,
                    source_tier,
                    source_type,
                    publisher,
                    title,
                    access_date,
                    url
                )
                VALUES (
                    'SRC000000002',
                    1,
                    'OFFERING_DOCUMENT',
                    'Pre-existing publisher',
                    'Pre-existing source',
                    DATE '2026-09-18',
                    'https://example.invalid/pre-existing'
                )
                """
            )
        )

    with pytest.raises(IntegrityError):
        persist_canonical_dataset(engine, dataset)

    # The conflicting pre-existing source remains, but every write performed
    # earlier in persist_canonical_dataset() must have rolled back.
    assert _count(engine, "sources") == 1
    assert _count(engine, "issuers") == 0
    assert _count(engine, "parties") == 0
    assert _count(engine, "transactions") == 0
    assert _count(engine, "instruments") == 0
    assert _count(engine, "market_series") == 0
    assert _count(engine, "observation_subjects") == 0
    assert _count(engine, "observations") == 0



def test_phase1_market_definitions_round_trip_losslessly(
    engine: Engine,
) -> None:
    """All seven market definition families persist and reconstruct exactly."""

    dataset = CanonicalDataset(
        market_series=(
            MarketSeriesRecord(
                market_series_id="MKS000000901",
                series_type=MarketSeriesType.FX_REFERENCE_RATE,
                series_label="EUR/GBP reference rate",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000902",
                series_type=MarketSeriesType.POLICY_RATE,
                series_label="ECB Deposit Facility Rate",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000903",
                series_type=MarketSeriesType.GOVERNMENT_YIELD,
                series_label="Germany 10Y benchmark yield",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000904",
                series_type=MarketSeriesType.SWAP_RATE,
                series_label="EUR 5Y swap rate",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000905",
                series_type=MarketSeriesType.CREDIT_SPREAD,
                series_label="European IG corporate OAS",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000906",
                series_type=MarketSeriesType.EQUITY_INDEX,
                series_label="STOXX Europe 600 price index",
            ),
            MarketSeriesRecord(
                market_series_id="MKS000000907",
                series_type=MarketSeriesType.VOLATILITY_INDEX,
                series_label="European equity volatility",
            ),
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000901",
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
        policy_rates=(
            PolicyRateDefinitionRecord(
                market_series_id="MKS000000902",
                authority="European Central Bank",
                jurisdiction="Euro Area",
                currency="EUR",
                rate_name="Deposit Facility Rate",
                convention_ref="market-data/ecb/policy-rate-v1",
            ),
        ),
        government_yields=(
            GovernmentYieldDefinitionRecord(
                market_series_id="MKS000000903",
                sovereign="Federal Republic of Germany",
                jurisdiction="Germany",
                currency="EUR",
                tenor_months=120,
                benchmark_ref="German sovereign 10Y benchmark",
                convention_ref="market-data/government-yield-v1",
            ),
        ),
        swap_rates=(
            SwapRateDefinitionRecord(
                market_series_id="MKS000000904",
                currency="EUR",
                tenor_months=60,
                floating_rate_ref="EURIBOR-6M",
                fixed_leg_convention_ref="EUR-IRS-fixed-leg-v1",
                convention_ref="market-data/swap-rate-v1",
            ),
        ),
        credit_spreads=(
            CreditSpreadDefinitionRecord(
                market_series_id="MKS000000905",
                benchmark_family="European Corporate Credit",
                currency="EUR",
                credit_universe="Investment Grade",
                spread_measure="OAS",
                convention_ref="market-data/credit-spread-v1",
                rating_segment="A",
                sector_segment=None,
            ),
        ),
        equity_indices=(
            EquityIndexDefinitionRecord(
                market_series_id="MKS000000906",
                index_name="STOXX Europe 600",
                universe="Europe",
                index_variant_ref="PRICE",
                methodology_ref="market-data/equity-index-v1",
            ),
        ),
        volatility_indices=(
            VolatilityIndexDefinitionRecord(
                market_series_id="MKS000000907",
                index_name="European Equity Volatility",
                underlying_ref="STOXX Europe 600",
                methodology_ref="market-data/volatility-index-v1",
                horizon_days=None,
            ),
        ),
    )

    persist_canonical_dataset(engine, dataset)

    assert {
        "market_series": _count(engine, "market_series"),
        "fx_reference_rate_definitions": _count(
            engine,
            "fx_reference_rate_definitions",
        ),
        "policy_rate_definitions": _count(
            engine,
            "policy_rate_definitions",
        ),
        "government_yield_definitions": _count(
            engine,
            "government_yield_definitions",
        ),
        "swap_rate_definitions": _count(
            engine,
            "swap_rate_definitions",
        ),
        "credit_spread_definitions": _count(
            engine,
            "credit_spread_definitions",
        ),
        "equity_index_definitions": _count(
            engine,
            "equity_index_definitions",
        ),
        "volatility_index_definitions": _count(
            engine,
            "volatility_index_definitions",
        ),
        "observation_subjects": _count(
            engine,
            "observation_subjects",
        ),
    } == {
        "market_series": 7,
        "fx_reference_rate_definitions": 1,
        "policy_rate_definitions": 1,
        "government_yield_definitions": 1,
        "swap_rate_definitions": 1,
        "credit_spread_definitions": 1,
        "equity_index_definitions": 1,
        "volatility_index_definitions": 1,
        "observation_subjects": 7,
    }

    reconstructed = load_canonical_dataset(engine)

    assert reconstructed == dataset
