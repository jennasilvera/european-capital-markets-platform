from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError

from european_capital_markets.domain.identifiers import parse_identifier
from european_capital_markets.persistence import allocate_market_lineage_ids

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)

MAX_IDENTIFIER_SEQUENCE = 999_999_999

SEQUENCE_SPECS = (
    (
        "canonical_source_id_seq",
        "sources",
        "source_id",
    ),
    (
        "canonical_evidence_id_seq",
        "evidence",
        "evidence_id",
    ),
    (
        "canonical_observation_id_seq",
        "observations",
        "observation_id",
    ),
)


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
def controlled_sequence_state(
    engine: Engine,
) -> Iterator[None]:
    _reseed_sequences_to_persisted_state(
        engine
    )

    try:
        yield
    finally:
        _reseed_sequences_to_persisted_state(
            engine
        )


def _alembic_config() -> Config:
    return Config(
        "alembic.ini"
    )


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


def _maximum_persisted_sequence(
    connection: sa.Connection,
    table_name: str,
    column_name: str,
) -> int | None:
    value = connection.execute(
        sa.text(
            f"""
            SELECT
                max(
                    substring(
                        {column_name}
                        FROM 4
                    )::bigint
                )
            FROM {table_name}
            """
        )
    ).scalar_one()

    if value is None:
        return None

    return int(value)


def _reseed_sequences_to_persisted_state(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        for (
            sequence_name,
            table_name,
            column_name,
        ) in SEQUENCE_SPECS:
            maximum = _maximum_persisted_sequence(
                connection,
                table_name,
                column_name,
            )

            if maximum is None:
                next_value = 1
                is_called = False
            elif maximum >= MAX_IDENTIFIER_SEQUENCE:
                next_value = MAX_IDENTIFIER_SEQUENCE
                is_called = True
            else:
                next_value = maximum + 1
                is_called = False

            connection.execute(
                sa.text(
                    """
                    SELECT setval(
                        CAST(
                            :sequence_name
                            AS regclass
                        ),
                        :next_value,
                        :is_called
                    )
                    """
                ),
                {
                    "sequence_name": sequence_name,
                    "next_value": next_value,
                    "is_called": is_called,
                },
            )


def _delete_seed_records(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                DELETE FROM observations
                WHERE observation_id = 'OBS000000987'
                """
            )
        )

        connection.execute(
            sa.text(
                """
                DELETE FROM observation_subjects
                WHERE subject_type = 'ISSUER'
                  AND subject_id = 'ISS000000001'
                """
            )
        )

        connection.execute(
            sa.text(
                """
                DELETE FROM evidence
                WHERE evidence_id = 'EVD000000654'
                """
            )
        )

        connection.execute(
            sa.text(
                """
                DELETE FROM sources
                WHERE source_id = 'SRC000000321'
                """
            )
        )

        connection.execute(
            sa.text(
                """
                DELETE FROM issuers
                WHERE issuer_id = 'ISS000000001'
                """
            )
        )


def test_lineage_sequences_have_frozen_bounds(
    engine: Engine,
) -> None:
    with engine.connect() as connection:
        for (
            sequence_name,
            _table_name,
            _column_name,
        ) in SEQUENCE_SPECS:
            row = connection.execute(
                sa.text(
                    """
                    SELECT
                        data_type,
                        start_value,
                        min_value,
                        max_value,
                        increment_by,
                        cycle,
                        cache_size
                    FROM pg_sequences
                    WHERE schemaname = current_schema()
                      AND sequencename = :sequence_name
                    """
                ),
                {
                    "sequence_name": sequence_name,
                },
            ).mappings().one()

            assert row["data_type"] == "bigint"
            assert row["start_value"] == 1
            assert row["min_value"] == 1
            assert (
                row["max_value"]
                == MAX_IDENTIFIER_SEQUENCE
            )
            assert row["increment_by"] == 1
            assert row["cycle"] is False
            assert row["cache_size"] == 1


def test_allocate_market_lineage_ids_matches_handoff_shape(
    engine: Engine,
) -> None:
    allocated = allocate_market_lineage_ids(
        engine,
        3,
    )

    assert len(allocated) == 3

    assert {
        record.source_id
        for record in allocated
    } == {
        "SRC000000001"
    }

    assert [
        record.evidence_id
        for record in allocated
    ] == [
        "EVD000000001",
        "EVD000000002",
        "EVD000000003",
    ]

    assert [
        record.observation_id
        for record in allocated
    ] == [
        "OBS000000001",
        "OBS000000002",
        "OBS000000003",
    ]


def test_repeated_allocation_is_monotonic_and_unique(
    engine: Engine,
) -> None:
    first = allocate_market_lineage_ids(
        engine,
        1,
    )[0]

    second = allocate_market_lineage_ids(
        engine,
        1,
    )[0]

    assert (
        parse_identifier(
            second.source_id
        ).sequence
        >
        parse_identifier(
            first.source_id
        ).sequence
    )

    assert (
        parse_identifier(
            second.evidence_id
        ).sequence
        >
        parse_identifier(
            first.evidence_id
        ).sequence
    )

    assert (
        parse_identifier(
            second.observation_id
        ).sequence
        >
        parse_identifier(
            first.observation_id
        ).sequence
    )


def test_concurrent_allocations_are_unique(
    engine: Engine,
) -> None:
    def allocate(
        _index: int,
    ) -> tuple[str, str, str]:
        record = allocate_market_lineage_ids(
            engine,
            1,
        )[0]

        return (
            record.source_id,
            record.evidence_id,
            record.observation_id,
        )

    with ThreadPoolExecutor(
        max_workers=8
    ) as executor:
        allocations = tuple(
            executor.map(
                allocate,
                range(24),
            )
        )

    source_ids = {
        source_id
        for (
            source_id,
            _evidence_id,
            _observation_id,
        ) in allocations
    }

    evidence_ids = {
        evidence_id
        for (
            _source_id,
            evidence_id,
            _observation_id,
        ) in allocations
    }

    observation_ids = {
        observation_id
        for (
            _source_id,
            _evidence_id,
            observation_id,
        ) in allocations
    }

    assert len(source_ids) == 24
    assert len(evidence_ids) == 24
    assert len(observation_ids) == 24


def test_sequence_consumption_survives_transaction_rollback(
    engine: Engine,
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()

        burned = int(
            connection.execute(
                sa.text(
                    """
                    SELECT nextval(
                        'canonical_source_id_seq'
                    )
                    """
                )
            ).scalar_one()
        )

        transaction.rollback()

    allocated = allocate_market_lineage_ids(
        engine,
        1,
    )[0]

    assert (
        parse_identifier(
            allocated.source_id
        ).sequence
        == burned + 1
    )


def test_migration_seeds_above_existing_canonical_ids(
    engine: Engine,
) -> None:
    config = _alembic_config()

    engine.dispose()

    command.downgrade(
        config,
        "0002_market_series_defs",
    )

    assert (
        _current_revision(engine)
        == "0002_market_series_defs"
    )

    try:
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
                        'SRC000000321',
                        1,
                        'MARKET_DATA',
                        'Historical Provider',
                        'Historical Source',
                        DATE '2026-09-20',
                        'https://example.invalid/source'
                    )
                    """
                )
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO evidence (
                        evidence_id,
                        source_id,
                        locator
                    )
                    VALUES (
                        'EVD000000654',
                        'SRC000000321',
                        'historical locator'
                    )
                    """
                )
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO issuers (
                        issuer_id,
                        canonical_name
                    )
                    VALUES (
                        'ISS000000001',
                        'Migration Seed Issuer'
                    )
                    """
                )
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO observation_subjects (
                        subject_type,
                        subject_id
                    )
                    VALUES (
                        'ISSUER',
                        'ISS000000001'
                    )
                    """
                )
            )

            connection.execute(
                sa.text(
                    """
                    INSERT INTO observations (
                        observation_id,
                        subject_type,
                        subject_id,
                        field_name,
                        as_of_date,
                        verification_state,
                        missing_state
                    )
                    VALUES (
                        'OBS000000987',
                        'ISSUER',
                        'ISS000000001',
                        'issuer.migration_probe',
                        DATE '2026-09-20',
                        'UNAVAILABLE',
                        'UNAVAILABLE'
                    )
                    """
                )
            )

        engine.dispose()

        command.upgrade(
            config,
            "head",
        )

        assert (
            _current_revision(engine)
            == "0003_lineage_id_sequences"
        )

        allocated = allocate_market_lineage_ids(
            engine,
            1,
        )[0]

        assert (
            allocated.source_id
            == "SRC000000322"
        )

        assert (
            allocated.evidence_id
            == "EVD000000655"
        )

        assert (
            allocated.observation_id
            == "OBS000000988"
        )
    finally:
        engine.dispose()

        command.upgrade(
            config,
            "head",
        )

        _delete_seed_records(
            engine
        )

        _reseed_sequences_to_persisted_state(
            engine
        )


def test_downgrade_refuses_unpersisted_allocations(
    engine: Engine,
) -> None:
    config = _alembic_config()

    allocate_market_lineage_ids(
        engine,
        1,
    )

    engine.dispose()

    try:
        with pytest.raises(
            DBAPIError,
            match="issued identifiers beyond persisted canonical state",
        ):
            command.downgrade(
                config,
                "0002_market_series_defs",
            )

        assert (
            _current_revision(engine)
            == "0003_lineage_id_sequences"
        )
    finally:
        _reseed_sequences_to_persisted_state(
            engine
        )
