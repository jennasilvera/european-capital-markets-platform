"""Add Phase 1 market-series definition persistence tables.

Revision ID: 0002_market_series_defs
Revises: 0001_canonical_schema
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_market_series_defs"
down_revision: str | None = "0001_canonical_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID_LENGTH = 12

MARKET_SERIES_TYPES = (
    "FX_REFERENCE_RATE",
    "POLICY_RATE",
    "GOVERNMENT_YIELD",
    "SWAP_RATE",
    "CREDIT_SPREAD",
    "EQUITY_INDEX",
    "VOLATILITY_INDEX",
)

DEFINITION_TABLES = (
    "fx_reference_rate_definitions",
    "policy_rate_definitions",
    "government_yield_definitions",
    "swap_rate_definitions",
    "credit_spread_definitions",
    "equity_index_definitions",
    "volatility_index_definitions",
)

def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _market_series_fk() -> sa.ForeignKey:
    return sa.ForeignKey(
        "market_series.market_series_id",
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def _nonblank(column_name: str) -> str:
    return f"btrim({column_name}) <> ''"


def upgrade() -> None:
    """Add the six Phase 1 type-specific market definition families."""

    # Schema 0001 permitted an FX market-series row without its extension row.
    # Before introducing exact-one-definition database enforcement, refuse to
    # migrate a database containing such incomplete historical state.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM market_series AS ms
                LEFT JOIN fx_reference_rate_definitions AS fx
                  ON fx.market_series_id = ms.market_series_id
                WHERE fx.market_series_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot migrate incomplete market-series definitions'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$;
        """
    )

    op.drop_constraint(
        "ck_market_series_type",
        "market_series",
        type_="check",
    )
    op.create_check_constraint(
        "ck_market_series_type",
        "market_series",
        f"series_type IN ({_sql_values(MARKET_SERIES_TYPES)})",
    )

    op.create_table(
        "policy_rate_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("authority", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_name", sa.Text(), nullable=False),
        sa.Column("convention_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_policy_rate_definitions",
        ),
        sa.UniqueConstraint(
            "authority",
            "jurisdiction",
            "currency",
            "rate_name",
            "convention_ref",
            name="uq_policy_rate_identity",
        ),
        sa.CheckConstraint(
            _nonblank("authority"),
            name="ck_policy_rate_authority_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("jurisdiction"),
            name="ck_policy_rate_jurisdiction_nonblank",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_policy_rate_currency",
        ),
        sa.CheckConstraint(
            _nonblank("rate_name"),
            name="ck_policy_rate_name_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("convention_ref"),
            name="ck_policy_rate_convention_nonblank",
        ),
    )

    op.create_table(
        "government_yield_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("sovereign", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tenor_months", sa.Integer(), nullable=False),
        sa.Column("benchmark_ref", sa.Text(), nullable=False),
        sa.Column("convention_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_government_yield_definitions",
        ),
        sa.UniqueConstraint(
            "sovereign",
            "jurisdiction",
            "currency",
            "tenor_months",
            "benchmark_ref",
            "convention_ref",
            name="uq_government_yield_identity",
        ),
        sa.CheckConstraint(
            _nonblank("sovereign"),
            name="ck_government_yield_sovereign_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("jurisdiction"),
            name="ck_government_yield_jurisdiction_nonblank",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_government_yield_currency",
        ),
        sa.CheckConstraint(
            "tenor_months > 0",
            name="ck_government_yield_tenor_positive",
        ),
        sa.CheckConstraint(
            _nonblank("benchmark_ref"),
            name="ck_government_yield_benchmark_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("convention_ref"),
            name="ck_government_yield_convention_nonblank",
        ),
    )

    op.create_table(
        "swap_rate_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tenor_months", sa.Integer(), nullable=False),
        sa.Column("floating_rate_ref", sa.Text(), nullable=False),
        sa.Column(
            "fixed_leg_convention_ref",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("convention_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_swap_rate_definitions",
        ),
        sa.UniqueConstraint(
            "currency",
            "tenor_months",
            "floating_rate_ref",
            "fixed_leg_convention_ref",
            "convention_ref",
            name="uq_swap_rate_identity",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_swap_rate_currency",
        ),
        sa.CheckConstraint(
            "tenor_months > 0",
            name="ck_swap_rate_tenor_positive",
        ),
        sa.CheckConstraint(
            _nonblank("floating_rate_ref"),
            name="ck_swap_rate_floating_ref_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("fixed_leg_convention_ref"),
            name="ck_swap_rate_fixed_leg_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("convention_ref"),
            name="ck_swap_rate_convention_nonblank",
        ),
    )

    op.create_table(
        "credit_spread_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("benchmark_family", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("credit_universe", sa.Text(), nullable=False),
        sa.Column("rating_segment", sa.Text(), nullable=True),
        sa.Column("sector_segment", sa.Text(), nullable=True),
        sa.Column("spread_measure", sa.Text(), nullable=False),
        sa.Column("convention_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_credit_spread_definitions",
        ),
        sa.CheckConstraint(
            _nonblank("benchmark_family"),
            name="ck_credit_spread_benchmark_nonblank",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_credit_spread_currency",
        ),
        sa.CheckConstraint(
            _nonblank("credit_universe"),
            name="ck_credit_spread_universe_nonblank",
        ),
        sa.CheckConstraint(
            """
            rating_segment IS NULL
            OR btrim(rating_segment) <> ''
            """,
            name="ck_credit_spread_rating_nonblank",
        ),
        sa.CheckConstraint(
            """
            sector_segment IS NULL
            OR btrim(sector_segment) <> ''
            """,
            name="ck_credit_spread_sector_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("spread_measure"),
            name="ck_credit_spread_measure_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("convention_ref"),
            name="ck_credit_spread_convention_nonblank",
        ),
    )

    # Domain semantic identity treats None as an ordinary identity value.
    # PostgreSQL ordinary UNIQUE treats NULLs as distinct, so use PostgreSQL's
    # NULLS NOT DISTINCT semantics to preserve the domain tuple exactly.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_credit_spread_identity
        ON credit_spread_definitions (
            benchmark_family,
            currency,
            credit_universe,
            rating_segment,
            sector_segment,
            spread_measure,
            convention_ref
        )
        NULLS NOT DISTINCT
        """
    )

    op.create_table(
        "equity_index_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("index_name", sa.Text(), nullable=False),
        sa.Column("universe", sa.Text(), nullable=False),
        sa.Column("index_variant_ref", sa.Text(), nullable=False),
        sa.Column("methodology_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_equity_index_definitions",
        ),
        sa.UniqueConstraint(
            "index_name",
            "universe",
            "index_variant_ref",
            "methodology_ref",
            name="uq_equity_index_identity",
        ),
        sa.CheckConstraint(
            _nonblank("index_name"),
            name="ck_equity_index_name_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("universe"),
            name="ck_equity_index_universe_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("index_variant_ref"),
            name="ck_equity_index_variant_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("methodology_ref"),
            name="ck_equity_index_methodology_nonblank",
        ),
    )

    op.create_table(
        "volatility_index_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _market_series_fk(),
            nullable=False,
        ),
        sa.Column("index_name", sa.Text(), nullable=False),
        sa.Column("underlying_ref", sa.Text(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("methodology_ref", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_volatility_index_definitions",
        ),
        sa.CheckConstraint(
            _nonblank("index_name"),
            name="ck_volatility_index_name_nonblank",
        ),
        sa.CheckConstraint(
            _nonblank("underlying_ref"),
            name="ck_volatility_index_underlying_nonblank",
        ),
        sa.CheckConstraint(
            """
            horizon_days IS NULL
            OR horizon_days > 0
            """,
            name="ck_volatility_index_horizon_positive",
        ),
        sa.CheckConstraint(
            _nonblank("methodology_ref"),
            name="ck_volatility_index_methodology_nonblank",
        ),
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_volatility_index_identity
        ON volatility_index_definitions (
            index_name,
            underlying_ref,
            horizon_days,
            methodology_ref
        )
        NULLS NOT DISTINCT
        """
    )

    # Exact-one-definition and parent-type compatibility are cross-table
    # invariants. They are deferred so one logical parent+extension unit can be
    # inserted atomically in either order within a transaction.
    op.execute(
        """
        CREATE FUNCTION ecm_validate_market_series_definition()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_market_series_id text;
            v_series_type text;
            v_definition_count integer;
            v_type_matches boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_market_series_id := OLD.market_series_id;
            ELSE
                v_market_series_id := NEW.market_series_id;
            END IF;

            SELECT series_type
            INTO v_series_type
            FROM market_series
            WHERE market_series_id = v_market_series_id;

            IF NOT FOUND THEN
                RETURN NULL;
            END IF;

            SELECT
                (
                    SELECT count(*)
                    FROM fx_reference_rate_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM policy_rate_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM government_yield_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM swap_rate_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM credit_spread_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM equity_index_definitions
                    WHERE market_series_id = v_market_series_id
                )
                +
                (
                    SELECT count(*)
                    FROM volatility_index_definitions
                    WHERE market_series_id = v_market_series_id
                )
            INTO v_definition_count;

            IF v_definition_count <> 1 THEN
                RAISE EXCEPTION
                    'Market series % requires exactly one type-specific definition',
                    v_market_series_id
                    USING ERRCODE = '23514';
            END IF;

            v_type_matches :=
                (
                    v_series_type = 'FX_REFERENCE_RATE'
                    AND EXISTS (
                        SELECT 1
                        FROM fx_reference_rate_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'POLICY_RATE'
                    AND EXISTS (
                        SELECT 1
                        FROM policy_rate_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'GOVERNMENT_YIELD'
                    AND EXISTS (
                        SELECT 1
                        FROM government_yield_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'SWAP_RATE'
                    AND EXISTS (
                        SELECT 1
                        FROM swap_rate_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'CREDIT_SPREAD'
                    AND EXISTS (
                        SELECT 1
                        FROM credit_spread_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'EQUITY_INDEX'
                    AND EXISTS (
                        SELECT 1
                        FROM equity_index_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                )
                OR
                (
                    v_series_type = 'VOLATILITY_INDEX'
                    AND EXISTS (
                        SELECT 1
                        FROM volatility_index_definitions
                        WHERE market_series_id = v_market_series_id
                    )
                );

            IF NOT v_type_matches THEN
                RAISE EXCEPTION
                    'Market-series definition family does not match series type for %',
                    v_market_series_id
                    USING ERRCODE = '23514';
            END IF;

            RETURN NULL;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            ct_market_series_definition_integrity
        AFTER INSERT OR UPDATE OR DELETE
        ON market_series
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION ecm_validate_market_series_definition();
        """
    )

    for table_name in DEFINITION_TABLES:
        op.execute(
            f"""
            CREATE CONSTRAINT TRIGGER
                ct_{table_name}_integrity
            AFTER INSERT OR UPDATE OR DELETE
            ON {table_name}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION ecm_validate_market_series_definition();
            """
        )

        op.execute(
            f"""
            CREATE TRIGGER
                tr_{table_name}_immutable_market_series_id
            BEFORE UPDATE OF market_series_id
            ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION ecm_reject_canonical_id_update(
                'market_series_id'
            );
            """
        )


def downgrade() -> None:
    """Remove Phase 1 market-series definition persistence."""

    # Downgrading with Phase 1 records would destroy governed canonical data.
    # Refuse rather than silently deleting those records.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM market_series
                WHERE series_type <> 'FX_REFERENCE_RATE'
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while Phase 1 market-series records exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            ct_market_series_definition_integrity
        ON market_series
        """
    )

    for table_name in DEFINITION_TABLES:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS
                ct_{table_name}_integrity
            ON {table_name}
            """
        )
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS
                tr_{table_name}_immutable_market_series_id
            ON {table_name}
            """
        )

    op.drop_index(
        "uq_volatility_index_identity",
        table_name="volatility_index_definitions",
    )
    op.drop_index(
        "uq_credit_spread_identity",
        table_name="credit_spread_definitions",
    )

    op.drop_table("volatility_index_definitions")
    op.drop_table("equity_index_definitions")
    op.drop_table("credit_spread_definitions")
    op.drop_table("swap_rate_definitions")
    op.drop_table("government_yield_definitions")
    op.drop_table("policy_rate_definitions")

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_validate_market_series_definition()
        """
    )

    op.drop_constraint(
        "ck_market_series_type",
        "market_series",
        type_="check",
    )
    op.create_check_constraint(
        "ck_market_series_type",
        "market_series",
        "series_type IN ('FX_REFERENCE_RATE')",
    )
