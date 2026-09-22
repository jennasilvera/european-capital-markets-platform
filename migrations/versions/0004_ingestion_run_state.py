"""Add durable market-ingestion run state and retained lineage allocation.

Revision ID: 0004_ingestion_run_state
Revises: 0003_lineage_id_sequences
Create Date: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ingestion_run_state"
down_revision: str | None = "0003_lineage_id_sequences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID_LENGTH = 12

INGESTION_RUN_CHECKPOINTS = (
    "STARTED",
    "RAW_LANDED",
    "LINEAGE_ALLOCATED",
    "PERSISTED",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _canonical_id_check(column_name: str, prefix: str) -> str:
    return (
        f"{column_name} ~ '^{prefix}[0-9]{{9}}$' "
        f"AND {column_name} <> '{prefix}000000000'"
    )


def _restrict_fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(
        target,
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def upgrade() -> None:
    """Add durable checkpoints for same-logical-attempt ingestion recovery."""

    op.create_table(
        "market_ingestion_runs",
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("market_series.market_series_id"),
            nullable=False,
        ),
        sa.Column(
            "checkpoint",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "storage_token",
            sa.Uuid(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "archived_location",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "raw_content_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "raw_byte_length",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "raw_retrieved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "raw_media_type",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_publisher",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_tier_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_type_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_title",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_retrieval_identifier",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_document_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "source_publication_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "source_document_version",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "source_notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "normalized_batch_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "normalized_datum_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "source_id",
            sa.String(length=ID_LENGTH),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "run_id",
            name="pk_market_ingestion_runs",
        ),
        sa.UniqueConstraint(
            "source_id",
            name="uq_market_ingestion_runs_source_id",
        ),
        sa.CheckConstraint(
            f"checkpoint IN ({_sql_values(INGESTION_RUN_CHECKPOINTS)})",
            name="ck_market_ingestion_runs_checkpoint",
        ),
        sa.CheckConstraint(
            """
            raw_content_sha256 IS NULL
            OR raw_content_sha256 ~ '^[0-9a-f]{64}$'
            """,
            name="ck_market_ingestion_runs_raw_sha256",
        ),
        sa.CheckConstraint(
            """
            normalized_batch_sha256 IS NULL
            OR normalized_batch_sha256 ~ '^[0-9a-f]{64}$'
            """,
            name="ck_market_ingestion_runs_normalized_sha256",
        ),
        sa.CheckConstraint(
            """
            raw_byte_length IS NULL
            OR raw_byte_length >= 0
            """,
            name="ck_market_ingestion_runs_raw_byte_length",
        ),
        sa.CheckConstraint(
            """
            normalized_datum_count IS NULL
            OR normalized_datum_count > 0
            """,
            name="ck_market_ingestion_runs_datum_count",
        ),
        sa.CheckConstraint(
            f"""
            source_id IS NULL
            OR ({_canonical_id_check("source_id", "SRC")})
            """,
            name="ck_market_ingestion_runs_source_id_shape",
        ),
        sa.CheckConstraint(
            """
            archived_location IS NULL
            OR btrim(archived_location) <> ''
            """,
            name="ck_market_ingestion_runs_archive_nonblank",
        ),
        sa.CheckConstraint(
            """
            raw_media_type IS NULL
            OR btrim(raw_media_type) <> ''
            """,
            name="ck_market_ingestion_runs_media_type_nonblank",
        ),
        sa.CheckConstraint(
            """
            checkpoint = 'STARTED'
            OR (
                storage_token IS NOT NULL
                AND archived_location IS NOT NULL
                AND raw_content_sha256 IS NOT NULL
                AND raw_byte_length IS NOT NULL
                AND raw_retrieved_at IS NOT NULL
                AND source_publisher IS NOT NULL
                AND btrim(source_publisher) <> ''
                AND source_tier_name IS NOT NULL
                AND btrim(source_tier_name) <> ''
                AND source_type_name IS NOT NULL
                AND btrim(source_type_name) <> ''
                AND source_title IS NOT NULL
                AND btrim(source_title) <> ''
            )
            """,
            name="ck_market_ingestion_runs_raw_checkpoint_complete",
        ),
        sa.CheckConstraint(
            """
            checkpoint IN ('STARTED', 'RAW_LANDED')
            OR (
                normalized_batch_sha256 IS NOT NULL
                AND normalized_datum_count IS NOT NULL
                AND source_id IS NOT NULL
            )
            """,
            name="ck_market_ingestion_runs_lineage_checkpoint_complete",
        ),
        sa.CheckConstraint(
            """
            (
                checkpoint = 'STARTED'
                AND storage_token IS NULL
                AND archived_location IS NULL
                AND raw_content_sha256 IS NULL
                AND raw_byte_length IS NULL
                AND raw_retrieved_at IS NULL
                AND raw_media_type IS NULL
                AND source_publisher IS NULL
                AND source_tier_name IS NULL
                AND source_type_name IS NULL
                AND source_title IS NULL
                AND source_url IS NULL
                AND source_retrieval_identifier IS NULL
                AND source_document_date IS NULL
                AND source_publication_date IS NULL
                AND source_document_version IS NULL
                AND source_notes IS NULL
                AND normalized_batch_sha256 IS NULL
                AND normalized_datum_count IS NULL
                AND source_id IS NULL
                AND persisted_at IS NULL
            )
            OR (
                checkpoint = 'RAW_LANDED'
                AND normalized_batch_sha256 IS NULL
                AND normalized_datum_count IS NULL
                AND source_id IS NULL
                AND persisted_at IS NULL
            )
            OR (
                checkpoint = 'LINEAGE_ALLOCATED'
                AND persisted_at IS NULL
            )
            OR (
                checkpoint = 'PERSISTED'
                AND persisted_at IS NOT NULL
            )
            """,
            name="ck_market_ingestion_runs_checkpoint_shape",
        ),
    )

    op.create_table(
        "market_ingestion_run_lineage",
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            _restrict_fk("market_ingestion_runs.run_id"),
            nullable=False,
        ),
        sa.Column(
            "ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "observation_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "run_id",
            "ordinal",
            name="pk_market_ingestion_run_lineage",
        ),
        sa.UniqueConstraint(
            "evidence_id",
            name="uq_market_ingestion_run_lineage_evidence_id",
        ),
        sa.UniqueConstraint(
            "observation_id",
            name="uq_market_ingestion_run_lineage_observation_id",
        ),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_market_ingestion_run_lineage_ordinal",
        ),
        sa.CheckConstraint(
            _canonical_id_check("evidence_id", "EVD"),
            name="ck_market_ingestion_run_lineage_evidence_id_shape",
        ),
        sa.CheckConstraint(
            _canonical_id_check("observation_id", "OBS"),
            name="ck_market_ingestion_run_lineage_observation_id_shape",
        ),
    )


def downgrade() -> None:
    """Remove run state only when no recoverable in-flight context is lost."""

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM market_ingestion_runs
                WHERE checkpoint IN (
                    'RAW_LANDED',
                    'LINEAGE_ALLOCATED'
                )
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade ingestion-run state while recoverable '
                    'in-flight runs exist'
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$;
        """
    )

    op.drop_table("market_ingestion_run_lineage")
    op.drop_table("market_ingestion_runs")
