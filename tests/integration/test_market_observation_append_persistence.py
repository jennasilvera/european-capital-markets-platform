from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MarketSeriesType,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence import (
    MarketObservationAppendConflictError,
    MarketObservationAppendStatus,
    persist_canonical_dataset,
    persist_market_observation_batch,
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


@pytest.fixture
def engine() -> Engine:
    if DATABASE_URL is None:
        pytest.skip("DATABASE_URL is required.")

    database_engine = sa.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    _truncate(database_engine)

    try:
        yield database_engine
    finally:
        _truncate(database_engine)
        database_engine.dispose()


def _truncate(engine: Engine) -> None:
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


def _series_dataset(
    *,
    convention_ref: str = "market-data/fx/reference-rate-v1",
) -> CanonicalDataset:
    return CanonicalDataset(
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
                convention_ref=convention_ref,
            ),
        ),
    )


def _batch(
    sequence: int,
    *,
    value: str = "0.8650",
) -> CanonicalDataset:
    source_id = f"SRC{sequence:09d}"
    evidence_id = f"EVD{sequence:09d}"
    observation_id = f"OBS{sequence:09d}"

    subject = _series_dataset()

    return CanonicalDataset(
        market_series=subject.market_series,
        fx_reference_rates=subject.fx_reference_rates,
        sources=(
            SourceRecord(
                source_id=source_id,
                tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
                source_type=SourceType.MARKET_DATA,
                publisher="Example market-data provider",
                title="EUR/GBP daily reference rate",
                access_date=date(2026, 9, 20),
                url=(
                    "https://example.invalid/"
                    f"retrieval/{sequence}"
                ),
                archived_location=(
                    "data/raw/test/MKS000000001/"
                    f"2026/09/20/{sequence}.csv"
                ),
            ),
        ),
        evidence=(
            EvidenceRecord(
                evidence_id=evidence_id,
                source_id=source_id,
                locator="TIME_PERIOD=2026-09-19",
            ),
        ),
        observations=(
            ObservationRecord(
                observation_id=observation_id,
                subject_type=EntityType.MARKET_SERIES,
                subject_id="MKS000000001",
                field_name="market_series.fx_rate",
                as_of_date=date(2026, 9, 19),
                verification_state=VerificationState.PENDING,
                value=Decimal(value),
                value_class=ValueClass.DISCLOSED,
                evidence_ids=(evidence_id,),
            ),
        ),
    )


def _count(
    engine: Engine,
    table_name: str,
) -> int:
    if table_name not in CANONICAL_TABLES:
        raise ValueError(
            f"Unknown canonical table: {table_name!r}"
        )

    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                f"SELECT count(*) FROM {table_name}"
            )
        ).scalar_one()


def test_append_inserts_lineage_against_existing_series(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(),
    )

    result = persist_market_observation_batch(
        engine,
        _batch(1),
    )

    assert (
        result
        is MarketObservationAppendStatus.INSERTED
    )
    assert _count(engine, "market_series") == 1
    assert _count(
        engine,
        "fx_reference_rate_definitions",
    ) == 1
    assert _count(engine, "sources") == 1
    assert _count(engine, "evidence") == 1
    assert _count(engine, "observations") == 1
    assert _count(
        engine,
        "observation_evidence",
    ) == 1


def test_exact_canonical_id_replay_is_noop(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(),
    )

    batch = _batch(1)

    first = persist_market_observation_batch(
        engine,
        batch,
    )
    second = persist_market_observation_batch(
        engine,
        batch,
    )

    assert (
        first
        is MarketObservationAppendStatus.INSERTED
    )
    assert (
        second
        is MarketObservationAppendStatus.ALREADY_PERSISTED
    )

    assert _count(engine, "sources") == 1
    assert _count(engine, "evidence") == 1
    assert _count(engine, "observations") == 1


def test_same_series_date_with_new_ids_is_new_append(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(),
    )

    first = persist_market_observation_batch(
        engine,
        _batch(1),
    )
    second = persist_market_observation_batch(
        engine,
        _batch(2),
    )

    assert (
        first
        is MarketObservationAppendStatus.INSERTED
    )
    assert (
        second
        is MarketObservationAppendStatus.INSERTED
    )

    assert _count(engine, "market_series") == 1
    assert _count(engine, "sources") == 2
    assert _count(engine, "evidence") == 2
    assert _count(engine, "observations") == 2


def test_same_ids_with_changed_content_fail_closed(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(),
    )

    batch = _batch(1)

    persist_market_observation_batch(
        engine,
        batch,
    )

    changed = replace(
        batch,
        observations=(
            replace(
                batch.observations[0],
                value=Decimal("0.9999"),
            ),
        ),
    )

    with pytest.raises(
        MarketObservationAppendConflictError,
        match="observation content",
    ):
        persist_market_observation_batch(
            engine,
            changed,
        )

    assert _count(engine, "sources") == 1
    assert _count(engine, "evidence") == 1
    assert _count(engine, "observations") == 1


def test_partial_canonical_id_replay_fails_closed(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(),
    )

    batch = _batch(1)
    source = batch.sources[0]

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
                    document_date,
                    publication_date,
                    url,
                    archived_location,
                    document_version,
                    notes
                )
                VALUES (
                    :source_id,
                    :source_tier,
                    :source_type,
                    :publisher,
                    :title,
                    :access_date,
                    :document_date,
                    :publication_date,
                    :url,
                    :archived_location,
                    :document_version,
                    :notes
                )
                """
            ),
            {
                "source_id": source.source_id,
                "source_tier": int(source.tier),
                "source_type": source.source_type.value,
                "publisher": source.publisher,
                "title": source.title,
                "access_date": source.access_date,
                "document_date": source.document_date,
                "publication_date": source.publication_date,
                "url": source.url,
                "archived_location": source.archived_location,
                "document_version": source.document_version,
                "notes": source.notes,
            },
        )

    with pytest.raises(
        MarketObservationAppendConflictError,
        match="Partial canonical-ID replay",
    ):
        persist_market_observation_batch(
            engine,
            batch,
        )

    assert _count(engine, "sources") == 1
    assert _count(engine, "evidence") == 0
    assert _count(engine, "observations") == 0


def test_missing_controlled_market_series_fails_before_lineage_write(
    engine: Engine,
) -> None:
    with pytest.raises(
        MarketObservationAppendConflictError,
        match="already-persisted market series",
    ):
        persist_market_observation_batch(
            engine,
            _batch(1),
        )

    assert _count(engine, "sources") == 0
    assert _count(engine, "evidence") == 0
    assert _count(engine, "observations") == 0


def test_mismatched_persisted_definition_fails_before_lineage_write(
    engine: Engine,
) -> None:
    persist_canonical_dataset(
        engine,
        _series_dataset(
            convention_ref="different-convention",
        ),
    )

    with pytest.raises(
        MarketObservationAppendConflictError,
        match="definition does not match",
    ):
        persist_market_observation_batch(
            engine,
            _batch(1),
        )

    assert _count(engine, "sources") == 0
    assert _count(engine, "evidence") == 0
    assert _count(engine, "observations") == 0
