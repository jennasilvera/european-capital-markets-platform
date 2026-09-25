"""PostgreSQL integration coverage for durable ingestion crash recovery."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

import european_capital_markets.ingestion.orchestration as orchestration
from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.ingestion.providers.ecb import (
    create_ecb_client,
)
from european_capital_markets.ingestion.raw_storage import (
    ImmutableRawArtifactStore,
)
from european_capital_markets.ingestion.run_state import (
    IngestionRunCheckpoint,
)
from european_capital_markets.persistence import (
    MarketObservationAppendStatus,
    persist_canonical_dataset,
    persist_market_observation_batch,
)
from european_capital_markets.persistence.ingestion_runs import (
    allocate_market_ingestion_run_lineage,
    create_market_ingestion_run,
    load_market_ingestion_run,
    record_market_ingestion_raw_landing,
)
from european_capital_markets.reference_data import (
    load_market_series_catalog,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)

_MARKET_SERIES_ID = "MKS000000001"

_STORAGE_TOKEN = UUID(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
)

_IGNORED_RECOVERY_TOKEN = UUID(
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
)

_SYNTHETIC_CSV = (
    b"KEY,FREQ,CURRENCY,PROVIDER_FM_ID,"
    b"DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,UNIT,TITLE\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-18,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-19,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-20,2.5,PCPA,Deposit facility\n"
)

_TABLES_TO_RESET = (
    "market_ingestion_run_lineage",
    "market_ingestion_runs",
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
def engine() -> Iterator[Engine]:
    if DATABASE_URL is None:
        pytest.skip(
            "DATABASE_URL is required."
        )

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


def _truncate(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                f"""
                TRUNCATE TABLE
                    {", ".join(_TABLES_TO_RESET)}
                RESTART IDENTITY CASCADE
                """
            )
        )


def _catalog_entry():
    catalog = load_market_series_catalog(
        "data/reference/market_series_catalog.json"
    )

    return next(
        entry
        for entry in catalog.entries
        if (
            entry.market_series.market_series_id
            == _MARKET_SERIES_ID
        )
    )


def _store(
    tmp_path: Path,
) -> ImmutableRawArtifactStore:
    root = tmp_path / "raw"
    root.mkdir()

    return ImmutableRawArtifactStore(
        root=root,
        archive_location_prefix="data/raw",
    )


def _client() -> httpx.Client:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "Content-Type": "text/csv",
            },
            content=_SYNTHETIC_CSV,
        )

    return create_ecb_client(
        transport=httpx.MockTransport(
            handler
        )
    )


def _seed_controlled_series(
    engine: Engine,
    catalog_entry,
) -> None:
    persist_canonical_dataset(
        engine,
        CanonicalDataset(
            market_series=(
                catalog_entry.market_series,
            ),
            policy_rates=(
                catalog_entry.definition,
            ),
        ),
    )


def _canonical_counts(
    engine: Engine,
) -> tuple[int, int, int, int]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                sa.text(
                    f"SELECT count(*) FROM {table_name}"
                )
            ).scalar_one()
            for table_name in (
                "sources",
                "evidence",
                "observations",
                "observation_evidence",
            )
        )


def test_recovers_after_canonical_commit_before_persisted_checkpoint(
    engine: Engine,
    tmp_path: Path,
) -> None:
    """Replay committed canonical rows, then durably finish the run."""

    catalog_entry = _catalog_entry()
    raw_store = _store(
        tmp_path
    )
    run_id = uuid4()

    _seed_controlled_series(
        engine,
        catalog_entry,
    )

    with _client() as client:
        raw_ingestion = (
            orchestration
            .retrieve_land_normalize_ecb_dfr(
                client,
                catalog_entry,
                raw_store,
                storage_token=_STORAGE_TOKEN,
            )
        )

    started = create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=_MARKET_SERIES_ID,
    )

    assert (
        started.checkpoint
        is IngestionRunCheckpoint.STARTED
    )

    raw_landed = record_market_ingestion_raw_landing(
        engine,
        run_id=run_id,
        raw_landing=raw_ingestion.raw_landing,
    )

    assert (
        raw_landed.checkpoint
        is IngestionRunCheckpoint.RAW_LANDED
    )

    allocated_ids = (
        allocate_market_ingestion_run_lineage(
            engine,
            run_id=run_id,
            datums=raw_ingestion.datums,
        )
    )

    allocated_run = load_market_ingestion_run(
        engine,
        run_id,
    )

    assert allocated_run is not None
    assert (
        allocated_run.checkpoint
        is IngestionRunCheckpoint.LINEAGE_ALLOCATED
    )
    assert (
        allocated_run.allocated_ids
        == allocated_ids
    )

    handoff = (
        orchestration
        .build_canonical_market_ingestion_handoff(
            catalog_entry,
            raw_ingestion.raw_landing.artifact,
            raw_ingestion.datums,
            allocated_ids,
        )
    )

    first_status = persist_market_observation_batch(
        engine,
        handoff.dataset,
    )

    assert (
        first_status
        is MarketObservationAppendStatus.INSERTED
    )

    # Simulate process death after the canonical transaction commits but
    # before mark_market_ingestion_run_persisted() can execute.
    crashed_run = load_market_ingestion_run(
        engine,
        run_id,
    )

    assert crashed_run is not None
    assert (
        crashed_run.checkpoint
        is IngestionRunCheckpoint.LINEAGE_ALLOCATED
    )
    assert (
        crashed_run.allocated_ids
        == allocated_ids
    )

    counts_after_first_commit = _canonical_counts(
        engine
    )

    assert counts_after_first_commit == (
        1,
        3,
        3,
        3,
    )

    # A non-client sentinel proves recovery cannot retrieve from the provider.
    # A different caller token proves the retained run token is authoritative.
    recovery = (
        orchestration
        .ingest_ecb_dfr_to_durable_canonical_persistence(
            object(),
            catalog_entry,
            raw_store,
            engine,
            run_id=run_id,
            last_n_observations=999,
            storage_token=_IGNORED_RECOVERY_TOKEN,
        )
    )

    assert (
        recovery.persistence_status
        is MarketObservationAppendStatus.ALREADY_PERSISTED
    )
    assert (
        recovery.run.checkpoint
        is IngestionRunCheckpoint.PERSISTED
    )
    assert (
        recovery.run.allocated_ids
        == allocated_ids
    )

    reloaded = load_market_ingestion_run(
        engine,
        run_id,
    )

    assert reloaded is not None
    assert (
        reloaded.checkpoint
        is IngestionRunCheckpoint.PERSISTED
    )
    assert reloaded.persisted_at is not None
    assert (
        reloaded.allocated_ids
        == allocated_ids
    )

    assert (
        _canonical_counts(engine)
        == counts_after_first_commit
    )
