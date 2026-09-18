"""Integration tests for the canonical PostgreSQL schema migration."""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)

EXPECTED_TABLES = {
    "issuers",
    "parties",
    "transactions",
    "instruments",
    "participations",
    "market_series",
    "fx_reference_rate_definitions",
    "sources",
    "evidence",
    "issuer_identifiers",
    "transaction_lifecycle_events",
    "observation_subjects",
    "observations",
    "issuer_identifier_evidence",
    "participation_evidence",
    "transaction_lifecycle_event_evidence",
    "observation_evidence",
    "observation_inputs",
}


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


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    """Run each data-level assertion inside a rollback-only transaction."""

    with engine.connect() as database_connection:
        transaction = database_connection.begin()

        try:
            yield database_connection
        finally:
            transaction.rollback()


def _sqlstate(exc: IntegrityError) -> str | None:
    """Return the PostgreSQL SQLSTATE exposed by Psycopg."""

    return getattr(exc.orig, "sqlstate", None)


def _insert_issuer(
    connection: Connection,
    *,
    issuer_id: str,
    canonical_name: str,
) -> None:
    """Insert one observable issuer and its registry row atomically."""

    connection.execute(
        sa.text(
            """
            INSERT INTO issuers (
                issuer_id,
                canonical_name
            )
            VALUES (
                :issuer_id,
                :canonical_name
            )
            """
        ),
        {
            "issuer_id": issuer_id,
            "canonical_name": canonical_name,
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
                'ISSUER',
                :issuer_id
            )
            """
        ),
        {"issuer_id": issuer_id},
    )


def _insert_missing_observation(
    connection: Connection,
    *,
    observation_id: str,
    issuer_id: str,
    as_of_date: str,
    field_name: str,
) -> None:
    """Insert one structurally valid explicit-missing observation."""

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
                :observation_id,
                'ISSUER',
                :issuer_id,
                :field_name,
                CAST(:as_of_date AS date),
                'UNAVAILABLE',
                'UNAVAILABLE'
            )
            """
        ),
        {
            "observation_id": observation_id,
            "issuer_id": issuer_id,
            "field_name": field_name,
            "as_of_date": as_of_date,
        },
    )


def test_postgresql_18_is_selected_backend(
    connection: Connection,
) -> None:
    """The integration suite must execute against PostgreSQL major 18."""

    version_num = int(
        connection.execute(
            sa.text("SHOW server_version_num")
        ).scalar_one()
    )

    assert 180000 <= version_num < 190000


def test_initial_schema_inventory(engine: Engine) -> None:
    """The migration creates every frozen canonical table family."""

    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())

    assert tables >= EXPECTED_TABLES


def test_btree_gist_extension_is_installed(
    connection: Connection,
) -> None:
    """Issuer-identity exclusions have their required GiST operators."""

    extension = connection.execute(
        sa.text(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname = 'btree_gist'
            """
        )
    ).scalar_one()

    assert extension == "btree_gist"


def test_observable_entity_requires_registry_row(
    connection: Connection,
) -> None:
    """An observable canonical entity cannot commit without registry state."""

    connection.execute(
        sa.text(
            """
            INSERT INTO issuers (
                issuer_id,
                canonical_name
            )
            VALUES (
                'ISS000000001',
                'Example Issuer plc'
            )
            """
        )
    )

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )

    assert _sqlstate(exc_info.value) == "23503"


def test_registry_row_requires_concrete_subject(
    connection: Connection,
) -> None:
    """The polymorphic registry cannot contain an orphan subject."""

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

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )

    assert _sqlstate(exc_info.value) == "23503"


def test_entity_and_registry_can_be_written_atomically(
    connection: Connection,
) -> None:
    """A coherent observable entity plus registry unit satisfies both sides."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="Example Issuer plc",
    )

    connection.execute(
        sa.text("SET CONSTRAINTS ALL IMMEDIATE")
    )

    stored_name = connection.execute(
        sa.text(
            """
            SELECT canonical_name
            FROM issuers
            WHERE issuer_id = 'ISS000000001'
            """
        )
    ).scalar_one()

    assert stored_name == "Example Issuer plc"


def test_duplicate_lei_assignment_is_rejected(
    connection: Connection,
) -> None:
    """A LEI cannot have a second canonical assignment."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="First Issuer plc",
    )
    _insert_issuer(
        connection,
        issuer_id="ISS000000002",
        canonical_name="Second Issuer plc",
    )

    for issuer_id in (
        "ISS000000001",
        "ISS000000002",
    ):
        connection.execute(
            sa.text(
                """
                INSERT INTO issuer_identifiers (
                    issuer_id,
                    identifier_type,
                    identifier_value,
                    scope_type
                )
                VALUES (
                    :issuer_id,
                    'LEI',
                    '5493001KJTIIGC8Y1R12',
                    'GLOBAL'
                )
                """
            ),
            {"issuer_id": issuer_id},
        )

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )

    assert _sqlstate(exc_info.value) == "23P01"


def test_overlapping_ticker_assignments_are_rejected(
    connection: Connection,
) -> None:
    """The same scoped non-LEI identity cannot overlap in time."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="First Issuer plc",
    )
    _insert_issuer(
        connection,
        issuer_id="ISS000000002",
        canonical_name="Second Issuer plc",
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO issuer_identifiers (
                issuer_id,
                identifier_type,
                identifier_value,
                scope_type,
                scope_value,
                assignment_valid_from,
                assignment_valid_to
            )
            VALUES (
                'ISS000000001',
                'TICKER',
                'EXM',
                'TRADING_VENUE',
                'XLON',
                DATE '2020-01-01',
                DATE '2025-01-01'
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO issuer_identifiers (
                issuer_id,
                identifier_type,
                identifier_value,
                scope_type,
                scope_value,
                assignment_valid_from,
                assignment_valid_to
            )
            VALUES (
                'ISS000000002',
                'TICKER',
                'EXM',
                'TRADING_VENUE',
                'XLON',
                DATE '2024-01-01',
                DATE '2026-01-01'
            )
            """
        )
    )

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )

    assert _sqlstate(exc_info.value) == "23P01"


def test_adjacent_ticker_assignments_are_allowed(
    connection: Connection,
) -> None:
    """Half-open validity permits reuse exactly at prior expiry."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="First Issuer plc",
    )
    _insert_issuer(
        connection,
        issuer_id="ISS000000002",
        canonical_name="Second Issuer plc",
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO issuer_identifiers (
                issuer_id,
                identifier_type,
                identifier_value,
                scope_type,
                scope_value,
                assignment_valid_from,
                assignment_valid_to
            )
            VALUES
            (
                'ISS000000001',
                'TICKER',
                'EXM',
                'TRADING_VENUE',
                'XLON',
                DATE '2020-01-01',
                DATE '2025-01-01'
            ),
            (
                'ISS000000002',
                'TICKER',
                'EXM',
                'TRADING_VENUE',
                'XLON',
                DATE '2025-01-01',
                NULL
            )
            """
        )
    )

    connection.execute(
        sa.text("SET CONSTRAINTS ALL IMMEDIATE")
    )

    count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM issuer_identifiers
            WHERE identifier_type = 'TICKER'
              AND identifier_value = 'EXM'
              AND scope_type = 'TRADING_VENUE'
              AND scope_value = 'XLON'
            """
        )
    ).scalar_one()

    assert count == 2


def test_decimal_value_round_trips_exactly(
    connection: Connection,
) -> None:
    """Canonical NUMERIC storage must not introduce float precision loss."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="Example Issuer plc",
    )

    value = Decimal(
        "12345678901234567890.123456789012345678901234567890"
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
                scalar_type,
                decimal_value,
                value_class
            )
            VALUES (
                'OBS000000001',
                'ISSUER',
                'ISS000000001',
                'test.decimal',
                DATE '2026-09-18',
                'PENDING',
                'DECIMAL',
                :value,
                'CALCULATED'
            )
            """
        ),
        {"value": value},
    )

    connection.execute(
        sa.text("SET CONSTRAINTS ALL IMMEDIATE")
    )

    stored = connection.execute(
        sa.text(
            """
            SELECT decimal_value
            FROM observations
            WHERE observation_id = 'OBS000000001'
            """
        )
    ).scalar_one()

    assert isinstance(stored, Decimal)
    assert stored == value


def test_explicit_missing_state_round_trips(
    connection: Connection,
) -> None:
    """Missing observations remain semantic rows rather than tombstones."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="Example Issuer plc",
    )

    _insert_missing_observation(
        connection,
        observation_id="OBS000000001",
        issuer_id="ISS000000001",
        as_of_date="2026-09-18",
        field_name="test.missing",
    )

    connection.execute(
        sa.text("SET CONSTRAINTS ALL IMMEDIATE")
    )

    row = connection.execute(
        sa.text(
            """
            SELECT
                missing_state,
                scalar_type,
                text_value,
                integer_value,
                decimal_value,
                boolean_value,
                date_value,
                datetime_value
            FROM observations
            WHERE observation_id = 'OBS000000001'
            """
        )
    ).one()

    assert row.missing_state == "UNAVAILABLE"
    assert row.scalar_type is None
    assert all(value is None for value in row[2:])


def test_future_observation_input_is_rejected(
    connection: Connection,
) -> None:
    """A calculation input cannot post-date its derived observation."""

    _insert_issuer(
        connection,
        issuer_id="ISS000000001",
        canonical_name="Example Issuer plc",
    )

    _insert_missing_observation(
        connection,
        observation_id="OBS000000001",
        issuer_id="ISS000000001",
        as_of_date="2025-01-01",
        field_name="test.derived",
    )
    _insert_missing_observation(
        connection,
        observation_id="OBS000000002",
        issuer_id="ISS000000001",
        as_of_date="2026-01-01",
        field_name="test.input",
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO observation_inputs (
                derived_observation_id,
                input_observation_id,
                input_ordinal
            )
            VALUES (
                'OBS000000001',
                'OBS000000002',
                0
            )
            """
        )
    )

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )

    assert _sqlstate(exc_info.value) == "23514"


def test_restrictive_source_delete_preserves_evidence(
    connection: Connection,
) -> None:
    """Deleting a source must not silently erase dependent evidence."""

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
                'SRC000000001',
                1,
                'ISSUER_ANNOUNCEMENT',
                'Example Issuer plc',
                'Example announcement',
                DATE '2026-09-18',
                'https://example.com/source'
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
                'EVD000000001',
                'SRC000000001',
                'Page 1'
            )
            """
        )
    )

    with pytest.raises(IntegrityError) as exc_info:
        connection.execute(
            sa.text(
                """
                DELETE FROM sources
                WHERE source_id = 'SRC000000001'
                """
            )
        )

    assert _sqlstate(exc_info.value) == "23503"
