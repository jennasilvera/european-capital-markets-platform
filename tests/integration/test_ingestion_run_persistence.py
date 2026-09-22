from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from european_capital_markets.domain.taxonomy import SourceTier, SourceType
from european_capital_markets.ingestion.contracts import (
    NormalizedMarketDatum,
    RawRetrievalArtifact,
    RetrievalSource,
)
from european_capital_markets.ingestion.raw_storage import RawArtifactLanding
from european_capital_markets.ingestion.run_state import (
    IngestionRunCheckpoint,
    MarketIngestionRun,
)
from european_capital_markets.persistence.ingestion_runs import (
    IngestionRunConflictError,
    IngestionRunStateError,
    allocate_market_ingestion_run_lineage,
    create_market_ingestion_run,
    load_market_ingestion_run,
    mark_market_ingestion_run_persisted,
    record_market_ingestion_raw_landing,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)

def _alembic_config() -> Config:
    return Config("alembic.ini")


def _current_revision(
    engine: Engine,
) -> str:
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                """
                SELECT version_num
                FROM alembic_version
                """
            )
        ).scalar_one()


MARKET_SERIES_ID = "MKS999999999"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if DATABASE_URL is None:
        pytest.skip(
            "DATABASE_URL is required."
        )

    database_engine = sa.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

    try:
        yield database_engine
    finally:
        database_engine.dispose()


@pytest.fixture(autouse=True)
def controlled_run_state(
    engine: Engine,
) -> Iterator[None]:
    _cleanup(
        engine
    )
    _ensure_market_series(
        engine
    )

    try:
        yield
    finally:
        _cleanup(
            engine
        )


def _ensure_market_series(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        existing = connection.execute(
            sa.text(
                """
                SELECT 1
                FROM market_series
                WHERE market_series_id = :market_series_id
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        ).scalar_one_or_none()

        if existing is None:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO market_series (
                        market_series_id,
                        series_type,
                        series_label
                    )
                    VALUES (
                        :market_series_id,
                        'POLICY_RATE',
                        'Step 13H Integration Test Policy Rate'
                    )
                    """
                ),
                {
                    "market_series_id": MARKET_SERIES_ID,
                },
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO observation_subjects (
                        subject_type,
                        subject_id
                    )
                    VALUES (
                        'MARKET_SERIES',
                        :market_series_id
                    )
                    """
                ),
                {
                    "market_series_id": MARKET_SERIES_ID,
                },
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO policy_rate_definitions (
                        market_series_id,
                        authority,
                        jurisdiction,
                        currency,
                        rate_name,
                        convention_ref
                    )
                    VALUES (
                        :market_series_id,
                        'Integration Test Authority',
                        'EU',
                        'EUR',
                        'Step 13H Test Rate',
                        'TEST_CONVENTION'
                    )
                    """
                ),
                {
                    "market_series_id": MARKET_SERIES_ID,
                },
            )


def _cleanup(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                DELETE FROM market_ingestion_run_lineage
                WHERE run_id IN (
                    SELECT run_id
                    FROM market_ingestion_runs
                    WHERE market_series_id = :market_series_id
                )
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM market_ingestion_runs
                WHERE market_series_id = :market_series_id
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM observation_subjects
                WHERE subject_type = 'MARKET_SERIES'
                  AND subject_id = :market_series_id
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM policy_rate_definitions
                WHERE market_series_id = :market_series_id
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM market_series
                WHERE market_series_id = :market_series_id
                """
            ),
            {
                "market_series_id": MARKET_SERIES_ID,
            },
        )


def _raw_landing(
    *,
    storage_token: UUID | None = None,
    content_sha256: str = "a" * 64,
) -> RawArtifactLanding:
    if storage_token is None:
        storage_token = uuid4()

    source = RetrievalSource(
        publisher="Integration Test Provider",
        source_tier=next(
            iter(SourceTier)
        ),
        source_type=next(
            iter(SourceType)
        ),
        title="Integration Test Retrieval",
        url="https://example.invalid/step-13h",
        retrieval_identifier="step-13h-test",
        document_date=date(2026, 9, 20),
        publication_date=date(2026, 9, 20),
        document_version="v1",
        notes="Integration-test provenance.",
    )

    artifact = RawRetrievalArtifact(
        market_series_id=MARKET_SERIES_ID,
        source=source,
        retrieved_at=datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=UTC,
        ),
        archived_location=(
            "raw/ecb/MKS999999999/2026/09/21/"
            f"20260921T120000.000000Z_{storage_token.hex}.csv"
        ),
        content_sha256=content_sha256,
        byte_length=12,
        media_type="text/csv",
    )

    return RawArtifactLanding(
        artifact=artifact,
        filesystem_path=Path(
            "/tmp/step-13h-test.csv"
        ),
        storage_token=storage_token,
    )


def _datums(
    value: str = "2.00",
) -> tuple[NormalizedMarketDatum, ...]:
    return (
        NormalizedMarketDatum(
            market_series_id=MARKET_SERIES_ID,
            field_name="market.policy_rate",
            as_of_date=date(2026, 9, 19),
            evidence_locator="row=1",
            value=Decimal(value),
            unit="PERCENT",
            currency="EUR",
        ),
        NormalizedMarketDatum(
            market_series_id=MARKET_SERIES_ID,
            field_name="market.policy_rate",
            as_of_date=date(2026, 9, 20),
            evidence_locator="row=2",
            value=Decimal("2.10"),
            unit="PERCENT",
            currency="EUR",
        ),
    )


def _create_raw_landed_run(
    engine: Engine,
    run_id: UUID,
) -> None:
    create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    record_market_ingestion_raw_landing(
        engine,
        run_id=run_id,
        raw_landing=_raw_landing(),
    )


def test_run_progresses_monotonically_through_persisted(
    engine: Engine,
) -> None:
    run_id = uuid4()

    started = create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    assert started.checkpoint is IngestionRunCheckpoint.STARTED

    raw_landing = _raw_landing()

    raw_landed = record_market_ingestion_raw_landing(
        engine,
        run_id=run_id,
        raw_landing=raw_landing,
    )

    assert (
        raw_landed.checkpoint
        is IngestionRunCheckpoint.RAW_LANDED
    )
    assert raw_landed.raw_artifact == raw_landing.artifact
    assert raw_landed.storage_token == raw_landing.storage_token

    allocated = allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=_datums(),
    )

    loaded = load_market_ingestion_run(
        engine,
        run_id,
    )

    assert loaded is not None
    assert (
        loaded.checkpoint
        is IngestionRunCheckpoint.LINEAGE_ALLOCATED
    )
    assert loaded.allocated_ids == allocated
    assert loaded.normalized_datum_count == 2

    persisted = mark_market_ingestion_run_persisted(
        engine,
        run_id=run_id,
    )

    assert (
        persisted.checkpoint
        is IngestionRunCheckpoint.PERSISTED
    )
    assert persisted.persisted_at is not None

    replay = mark_market_ingestion_run_persisted(
        engine,
        run_id=run_id,
    )

    assert replay == persisted


def test_same_normalized_batch_reuses_retained_allocation(
    engine: Engine,
) -> None:
    run_id = uuid4()
    _create_raw_landed_run(
        engine,
        run_id,
    )

    first = allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=_datums(),
    )

    second = allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=_datums(),
    )

    assert second == first


def test_changed_normalized_batch_fails_closed_after_allocation(
    engine: Engine,
) -> None:
    run_id = uuid4()
    _create_raw_landed_run(
        engine,
        run_id,
    )

    allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=_datums(),
    )

    with pytest.raises(
        IngestionRunConflictError,
        match="does not match",
    ):
        allocate_market_ingestion_run_lineage(
            engine,
            run_id=run_id,
            datums=_datums(
                "2.01"
            ),
        )


def test_changed_raw_landing_fails_closed(
    engine: Engine,
) -> None:
    run_id = uuid4()

    create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    first = _raw_landing()

    record_market_ingestion_raw_landing(
        engine,
        run_id=run_id,
        raw_landing=first,
    )

    conflicting = _raw_landing(
        storage_token=first.storage_token,
        content_sha256="b" * 64,
    )

    with pytest.raises(
        IngestionRunConflictError,
        match="conflicts",
    ):
        record_market_ingestion_raw_landing(
            engine,
            run_id=run_id,
            raw_landing=conflicting,
        )


def test_allocation_before_raw_landing_is_rejected(
    engine: Engine,
) -> None:
    run_id = uuid4()

    create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    with pytest.raises(
        IngestionRunStateError,
        match="RAW_LANDED",
    ):
        allocate_market_ingestion_run_lineage(
            engine,
            run_id=run_id,
            datums=_datums(),
        )


def test_concurrent_create_run_converges_on_one_durable_identity(
    engine: Engine,
) -> None:
    run_id = uuid4()
    worker_count = 8
    start_barrier = Barrier(
        worker_count
    )

    def create_run() -> MarketIngestionRun:
        start_barrier.wait(
            timeout=10
        )

        return create_market_ingestion_run(
            engine,
            run_id=run_id,
            market_series_id=MARKET_SERIES_ID,
        )

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        futures = [
            executor.submit(
                create_run
            )
            for _ in range(worker_count)
        ]

        results = [
            future.result(
                timeout=20
            )
            for future in futures
        ]

    assert all(
        result.run_id == run_id
        for result in results
    )

    assert all(
        result.market_series_id
        == MARKET_SERIES_ID
        for result in results
    )

    assert all(
        result.checkpoint
        is IngestionRunCheckpoint.STARTED
        for result in results
    )

    with engine.connect() as connection:
        durable_count = connection.execute(
            sa.text(
                """
                SELECT count(*)
                FROM market_ingestion_runs
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
            },
        ).scalar_one()

    assert durable_count == 1


def test_create_run_replay_requires_same_market_series(
    engine: Engine,
) -> None:
    run_id = uuid4()

    first = create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    second = create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    assert second == first

    with pytest.raises(
        IngestionRunConflictError,
        match="different market series",
    ):
        create_market_ingestion_run(
            engine,
            run_id=run_id,
            market_series_id="MKS000000001",
        )


def test_database_rejects_incomplete_raw_landed_checkpoint(
    engine: Engine,
) -> None:
    run_id = uuid4()

    with pytest.raises(
        IntegrityError,
    ) as exc_info, engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                    INSERT INTO market_ingestion_runs (
                        run_id,
                        market_series_id,
                        checkpoint
                    )
                    VALUES (
                        :run_id,
                        :market_series_id,
                        'RAW_LANDED'
                    )
                    """
            ),
            {
                "run_id": run_id,
                "market_series_id": MARKET_SERIES_ID,
            },
        )

    assert getattr(
        exc_info.value.orig,
        "sqlstate",
        None,
    ) == "23514"


def test_downgrade_refuses_raw_landed_recovery_state(
    engine: Engine,
) -> None:
    run_id = uuid4()

    _create_raw_landed_run(
        engine,
        run_id,
    )

    config = _alembic_config()

    engine.dispose()

    try:
        with pytest.raises(
            DBAPIError,
            match="recoverable",
        ):
            command.downgrade(
                config,
                "0003_lineage_id_sequences",
            )

        assert (
            _current_revision(engine)
            == "0004_ingestion_run_state"
        )
    finally:
        engine.dispose()
        command.upgrade(
            config,
            "head",
        )


def test_downgrade_refuses_lineage_allocated_recovery_state(
    engine: Engine,
) -> None:
    run_id = uuid4()

    _create_raw_landed_run(
        engine,
        run_id,
    )

    allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=_datums(),
    )

    config = _alembic_config()

    engine.dispose()

    try:
        with pytest.raises(
            DBAPIError,
            match="recoverable",
        ):
            command.downgrade(
                config,
                "0003_lineage_id_sequences",
            )

        assert (
            _current_revision(engine)
            == "0004_ingestion_run_state"
        )
    finally:
        engine.dispose()
        command.upgrade(
            config,
            "head",
        )


def test_downgrade_allows_started_only_state(
    engine: Engine,
) -> None:
    run_id = uuid4()

    create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=MARKET_SERIES_ID,
    )

    config = _alembic_config()

    engine.dispose()

    try:
        command.downgrade(
            config,
            "0003_lineage_id_sequences",
        )

        assert (
            _current_revision(engine)
            == "0003_lineage_id_sequences"
        )

        tables = set(
            sa.inspect(engine).get_table_names()
        )

        assert "market_ingestion_runs" not in tables
        assert "market_ingestion_run_lineage" not in tables
    finally:
        engine.dispose()
        command.upgrade(
            config,
            "head",
        )
