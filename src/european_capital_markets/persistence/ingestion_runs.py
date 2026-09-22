"""PostgreSQL persistence for recoverable market-ingestion run state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.taxonomy import (
    EntityType,
    SourceTier,
    SourceType,
)
from european_capital_markets.ingestion.contracts import (
    AllocatedLineageIds,
    NormalizedMarketDatum,
    RawRetrievalArtifact,
    RetrievalSource,
)
from european_capital_markets.ingestion.raw_storage import RawArtifactLanding
from european_capital_markets.ingestion.run_state import (
    IngestionRunCheckpoint,
    MarketIngestionRun,
    compute_normalized_market_batch_sha256,
)
from european_capital_markets.persistence.id_allocation import (
    _allocate_market_lineage_ids,
)


class IngestionRunConflictError(ValueError):
    """Raised when persisted run state conflicts with requested replay state."""


class IngestionRunStateError(ValueError):
    """Raised when a requested transition is invalid for the current checkpoint."""


def create_market_ingestion_run(
    engine: Engine,
    *,
    run_id: UUID,
    market_series_id: str,
) -> MarketIngestionRun:
    """Create one durable logical ingestion attempt at STARTED."""

    _validate_run_id(run_id)

    validate_identifier(
        market_series_id,
        EntityType.MARKET_SERIES,
    )

    with engine.begin() as connection:
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
                    'STARTED'
                )
                ON CONFLICT (run_id) DO NOTHING
                """
            ),
            {
                "run_id": run_id,
                "market_series_id": market_series_id,
            },
        )

        current = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        if current["market_series_id"] != market_series_id:
            raise IngestionRunConflictError(
                "run_id is already bound to a different market series."
            )

        return _row_to_run(
            connection,
            current,
        )


def load_market_ingestion_run(
    engine: Engine,
    run_id: UUID,
) -> MarketIngestionRun | None:
    """Load one durable recovery context without mutating it."""

    _validate_run_id(run_id)

    with engine.connect() as connection:
        row = _select_run(
            connection,
            run_id,
            for_update=False,
        )

        if row is None:
            return None

        return _row_to_run(
            connection,
            row,
        )


def record_market_ingestion_raw_landing(
    engine: Engine,
    *,
    run_id: UUID,
    raw_landing: RawArtifactLanding,
) -> MarketIngestionRun:
    """Bind one immutable landed retrieval to a logical run exactly once."""

    _validate_run_id(run_id)

    if not isinstance(
        raw_landing,
        RawArtifactLanding,
    ):
        raise TypeError(
            "raw_landing must be RawArtifactLanding."
        )

    artifact = raw_landing.artifact
    source = artifact.source

    with engine.begin() as connection:
        current = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        if current["market_series_id"] != artifact.market_series_id:
            raise IngestionRunConflictError(
                "Raw artifact market series does not match the run."
            )

        checkpoint = IngestionRunCheckpoint(
            current["checkpoint"]
        )

        if checkpoint is not IngestionRunCheckpoint.STARTED:
            _require_raw_state_matches(
                current,
                raw_landing,
            )

            return _row_to_run(
                connection,
                current,
            )

        connection.execute(
            sa.text(
                """
                UPDATE market_ingestion_runs
                SET
                    checkpoint = 'RAW_LANDED',
                    storage_token = :storage_token,
                    archived_location = :archived_location,
                    raw_content_sha256 = :raw_content_sha256,
                    raw_byte_length = :raw_byte_length,
                    raw_retrieved_at = :raw_retrieved_at,
                    raw_media_type = :raw_media_type,
                    source_publisher = :source_publisher,
                    source_tier_name = :source_tier_name,
                    source_type_name = :source_type_name,
                    source_title = :source_title,
                    source_url = :source_url,
                    source_retrieval_identifier = :source_retrieval_identifier,
                    source_document_date = :source_document_date,
                    source_publication_date = :source_publication_date,
                    source_document_version = :source_document_version,
                    source_notes = :source_notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "storage_token": raw_landing.storage_token,
                "archived_location": artifact.archived_location,
                "raw_content_sha256": artifact.content_sha256,
                "raw_byte_length": artifact.byte_length,
                "raw_retrieved_at": artifact.retrieved_at,
                "raw_media_type": artifact.media_type,
                "source_publisher": source.publisher,
                "source_tier_name": source.source_tier.name,
                "source_type_name": source.source_type.name,
                "source_title": source.title,
                "source_url": source.url,
                "source_retrieval_identifier": source.retrieval_identifier,
                "source_document_date": source.document_date,
                "source_publication_date": source.publication_date,
                "source_document_version": source.document_version,
                "source_notes": source.notes,
            },
        )

        updated = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        return _row_to_run(
            connection,
            updated,
        )


def allocate_market_ingestion_run_lineage(
    engine: Engine,
    *,
    run_id: UUID,
    datums: tuple[NormalizedMarketDatum, ...],
) -> tuple[AllocatedLineageIds, ...]:
    """Allocate once, then replay the same retained lineage for this run."""

    _validate_run_id(run_id)

    normalized_batch_sha256 = (
        compute_normalized_market_batch_sha256(
            datums
        )
    )

    with engine.begin() as connection:
        current = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        if any(
            datum.market_series_id
            != current["market_series_id"]
            for datum in datums
        ):
            raise IngestionRunConflictError(
                "Normalized datum market series does not match the run."
            )

        checkpoint = IngestionRunCheckpoint(
            current["checkpoint"]
        )

        if checkpoint is IngestionRunCheckpoint.STARTED:
            raise IngestionRunStateError(
                "Lineage cannot be allocated before RAW_LANDED."
            )

        if checkpoint in {
            IngestionRunCheckpoint.LINEAGE_ALLOCATED,
            IngestionRunCheckpoint.PERSISTED,
        }:
            if (
                current["normalized_batch_sha256"]
                != normalized_batch_sha256
                or int(current["normalized_datum_count"])
                != len(datums)
            ):
                raise IngestionRunConflictError(
                    "Normalized replay does not match the batch bound to "
                    "this run's retained lineage allocation."
                )

            return _load_allocated_ids(
                connection,
                current,
            )

        if checkpoint is not IngestionRunCheckpoint.RAW_LANDED:
            raise IngestionRunStateError(
                f"Unsupported allocation checkpoint: {checkpoint.value}."
            )

        allocated_ids = _allocate_market_lineage_ids(
            connection,
            len(datums),
        )

        source_ids = {
            ids.source_id
            for ids in allocated_ids
        }

        if len(source_ids) != 1:
            raise AssertionError(
                "Market-lineage allocator returned inconsistent source IDs."
            )

        source_id = allocated_ids[0].source_id

        for ordinal, ids in enumerate(
            allocated_ids
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO market_ingestion_run_lineage (
                        run_id,
                        ordinal,
                        evidence_id,
                        observation_id
                    )
                    VALUES (
                        :run_id,
                        :ordinal,
                        :evidence_id,
                        :observation_id
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "ordinal": ordinal,
                    "evidence_id": ids.evidence_id,
                    "observation_id": ids.observation_id,
                },
            )

        connection.execute(
            sa.text(
                """
                UPDATE market_ingestion_runs
                SET
                    checkpoint = 'LINEAGE_ALLOCATED',
                    normalized_batch_sha256 = :normalized_batch_sha256,
                    normalized_datum_count = :normalized_datum_count,
                    source_id = :source_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "normalized_batch_sha256": normalized_batch_sha256,
                "normalized_datum_count": len(datums),
                "source_id": source_id,
            },
        )

        return allocated_ids


def mark_market_ingestion_run_persisted(
    engine: Engine,
    *,
    run_id: UUID,
) -> MarketIngestionRun:
    """Advance a retained-lineage run to PERSISTED monotonically."""

    _validate_run_id(run_id)

    with engine.begin() as connection:
        current = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        checkpoint = IngestionRunCheckpoint(
            current["checkpoint"]
        )

        if checkpoint is IngestionRunCheckpoint.PERSISTED:
            return _row_to_run(
                connection,
                current,
            )

        if checkpoint is not IngestionRunCheckpoint.LINEAGE_ALLOCATED:
            raise IngestionRunStateError(
                "Only LINEAGE_ALLOCATED runs may be marked PERSISTED."
            )

        connection.execute(
            sa.text(
                """
                UPDATE market_ingestion_runs
                SET
                    checkpoint = 'PERSISTED',
                    persisted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )

        updated = _require_run_row(
            connection,
            run_id,
            for_update=True,
        )

        return _row_to_run(
            connection,
            updated,
        )


def _validate_run_id(
    run_id: UUID,
) -> None:
    if not isinstance(
        run_id,
        UUID,
    ):
        raise TypeError(
            "run_id must be a UUID."
        )


def _select_run(
    connection: Connection,
    run_id: UUID,
    *,
    for_update: bool,
) -> Mapping[str, Any] | None:
    suffix = (
        " FOR UPDATE"
        if for_update
        else ""
    )

    return connection.execute(
        sa.text(
            f"""
            SELECT
                run_id,
                market_series_id,
                checkpoint,
                storage_token,
                archived_location,
                raw_content_sha256,
                raw_byte_length,
                raw_retrieved_at,
                raw_media_type,
                source_publisher,
                source_tier_name,
                source_type_name,
                source_title,
                source_url,
                source_retrieval_identifier,
                source_document_date,
                source_publication_date,
                source_document_version,
                source_notes,
                normalized_batch_sha256,
                normalized_datum_count,
                source_id,
                created_at,
                updated_at,
                persisted_at
            FROM market_ingestion_runs
            WHERE run_id = :run_id
            {suffix}
            """
        ),
        {"run_id": run_id},
    ).mappings().one_or_none()


def _require_run_row(
    connection: Connection,
    run_id: UUID,
    *,
    for_update: bool,
) -> Mapping[str, Any]:
    row = _select_run(
        connection,
        run_id,
        for_update=for_update,
    )

    if row is None:
        raise KeyError(
            f"Unknown market ingestion run: {run_id}"
        )

    return row


def _require_raw_state_matches(
    row: Mapping[str, Any],
    raw_landing: RawArtifactLanding,
) -> None:
    artifact = raw_landing.artifact
    source = artifact.source

    expected = {
        "storage_token": raw_landing.storage_token,
        "archived_location": artifact.archived_location,
        "raw_content_sha256": artifact.content_sha256,
        "raw_byte_length": artifact.byte_length,
        "raw_retrieved_at": artifact.retrieved_at,
        "raw_media_type": artifact.media_type,
        "source_publisher": source.publisher,
        "source_tier_name": source.source_tier.name,
        "source_type_name": source.source_type.name,
        "source_title": source.title,
        "source_url": source.url,
        "source_retrieval_identifier": source.retrieval_identifier,
        "source_document_date": source.document_date,
        "source_publication_date": source.publication_date,
        "source_document_version": source.document_version,
        "source_notes": source.notes,
    }

    mismatched = [
        field_name
        for field_name, expected_value in expected.items()
        if row[field_name] != expected_value
    ]

    if mismatched:
        raise IngestionRunConflictError(
            "Raw landing replay conflicts with retained run state: "
            + ", ".join(mismatched)
        )


def _load_allocated_ids(
    connection: Connection,
    row: Mapping[str, Any],
) -> tuple[AllocatedLineageIds, ...]:
    source_id = row["source_id"]
    expected_count = row["normalized_datum_count"]

    if source_id is None or expected_count is None:
        raise IngestionRunConflictError(
            "Retained lineage checkpoint is structurally incomplete."
        )

    rows = connection.execute(
        sa.text(
            """
            SELECT
                ordinal,
                evidence_id,
                observation_id
            FROM market_ingestion_run_lineage
            WHERE run_id = :run_id
            ORDER BY ordinal
            """
        ),
        {"run_id": row["run_id"]},
    ).mappings().all()

    if len(rows) != int(expected_count):
        raise IngestionRunConflictError(
            "Retained lineage row count does not match normalized_datum_count."
        )

    for expected_ordinal, lineage_row in enumerate(
        rows
    ):
        if lineage_row["ordinal"] != expected_ordinal:
            raise IngestionRunConflictError(
                "Retained lineage ordinals are not contiguous from zero."
            )

    return tuple(
        AllocatedLineageIds(
            source_id=source_id,
            evidence_id=lineage_row["evidence_id"],
            observation_id=lineage_row["observation_id"],
        )
        for lineage_row in rows
    )


def _row_to_run(
    connection: Connection,
    row: Mapping[str, Any],
) -> MarketIngestionRun:
    checkpoint = IngestionRunCheckpoint(
        row["checkpoint"]
    )

    raw_artifact = None
    storage_token = row["storage_token"]

    if checkpoint is not IngestionRunCheckpoint.STARTED:
        raw_artifact = RawRetrievalArtifact(
            market_series_id=row["market_series_id"],
            source=RetrievalSource(
                publisher=row["source_publisher"],
                source_tier=SourceTier[
                    row["source_tier_name"]
                ],
                source_type=SourceType[
                    row["source_type_name"]
                ],
                title=row["source_title"],
                url=row["source_url"],
                retrieval_identifier=(
                    row["source_retrieval_identifier"]
                ),
                document_date=row["source_document_date"],
                publication_date=row["source_publication_date"],
                document_version=row["source_document_version"],
                notes=row["source_notes"],
            ),
            retrieved_at=row["raw_retrieved_at"],
            archived_location=row["archived_location"],
            content_sha256=row["raw_content_sha256"],
            byte_length=int(
                row["raw_byte_length"]
            ),
            media_type=row["raw_media_type"],
        )

    allocated_ids: tuple[AllocatedLineageIds, ...] = ()

    if checkpoint in {
        IngestionRunCheckpoint.LINEAGE_ALLOCATED,
        IngestionRunCheckpoint.PERSISTED,
    }:
        allocated_ids = _load_allocated_ids(
            connection,
            row,
        )

    return MarketIngestionRun(
        run_id=row["run_id"],
        market_series_id=row["market_series_id"],
        checkpoint=checkpoint,
        raw_artifact=raw_artifact,
        storage_token=storage_token,
        normalized_batch_sha256=row["normalized_batch_sha256"],
        normalized_datum_count=(
            int(row["normalized_datum_count"])
            if row["normalized_datum_count"] is not None
            else None
        ),
        allocated_ids=allocated_ids,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        persisted_at=row["persisted_at"],
    )
