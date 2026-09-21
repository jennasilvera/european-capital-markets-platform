"""Add PostgreSQL-backed canonical lineage identifier sequences.

Revision ID: 0003_lineage_id_sequences
Revises: 0002_market_series_defs
Create Date: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_lineage_id_sequences"
down_revision: str | None = "0002_market_series_defs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_IDENTIFIER_SEQUENCE = 999_999_999

_SEQUENCE_SPECS = (
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


def _create_and_seed_sequence(
    sequence_name: str,
    table_name: str,
    column_name: str,
) -> None:
    """Create one bounded sequence above existing canonical identifiers."""

    op.execute(
        f"""
        CREATE SEQUENCE {sequence_name}
            AS bigint
            INCREMENT BY 1
            MINVALUE 1
            MAXVALUE {MAX_IDENTIFIER_SEQUENCE}
            START WITH 1
            CACHE 1
            NO CYCLE
        """
    )

    op.execute(
        f"""
        SELECT setval(
            '{sequence_name}'::regclass,
            CASE
                WHEN maximum_sequence IS NULL THEN 1
                WHEN maximum_sequence >= {MAX_IDENTIFIER_SEQUENCE}
                    THEN {MAX_IDENTIFIER_SEQUENCE}
                ELSE maximum_sequence + 1
            END,
            CASE
                WHEN maximum_sequence >= {MAX_IDENTIFIER_SEQUENCE}
                    THEN true
                ELSE false
            END
        )
        FROM (
            SELECT
                max(
                    substring(
                        {column_name}
                        FROM 4
                    )::bigint
                ) AS maximum_sequence
            FROM {table_name}
        ) AS existing
        """
    )


def _assert_sequence_can_be_dropped(
    sequence_name: str,
    table_name: str,
    column_name: str,
) -> None:
    """Refuse downgrade when issued IDs exist above persisted state."""

    op.execute(
        f"""
        DO $$
        DECLARE
            v_last_value bigint;
            v_is_called boolean;
            v_persisted_max bigint;
        BEGIN
            SELECT
                last_value,
                is_called
            INTO
                v_last_value,
                v_is_called
            FROM {sequence_name};

            SELECT
                max(
                    substring(
                        {column_name}
                        FROM 4
                    )::bigint
                )
            INTO
                v_persisted_max
            FROM {table_name};

            IF (
                v_is_called
                AND v_last_value > COALESCE(
                    v_persisted_max,
                    0
                )
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade canonical lineage allocation: '
                    '{sequence_name} has issued identifiers beyond '
                    'persisted canonical state'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$;
        """
    )


def upgrade() -> None:
    """Add bounded canonical SRC/EVD/OBS allocation sequences."""

    for (
        sequence_name,
        table_name,
        column_name,
    ) in _SEQUENCE_SPECS:
        _create_and_seed_sequence(
            sequence_name,
            table_name,
            column_name,
        )


def downgrade() -> None:
    """Remove canonical lineage sequences only when reuse remains impossible."""

    for (
        sequence_name,
        table_name,
        column_name,
    ) in _SEQUENCE_SPECS:
        _assert_sequence_can_be_dropped(
            sequence_name,
            table_name,
            column_name,
        )

    for (
        sequence_name,
        _table_name,
        _column_name,
    ) in reversed(_SEQUENCE_SPECS):
        op.execute(
            f"DROP SEQUENCE {sequence_name}"
        )
