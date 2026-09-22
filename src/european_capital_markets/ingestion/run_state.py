"""Provider-neutral durable state for recoverable market-ingestion runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from uuid import UUID

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.taxonomy import EntityType
from european_capital_markets.ingestion.contracts import (
    AllocatedLineageIds,
    NormalizedMarketDatum,
    RawRetrievalArtifact,
)


class IngestionRunCheckpoint(StrEnum):
    """Highest durable recovery boundary completed by one logical ingestion run."""

    STARTED = "STARTED"
    RAW_LANDED = "RAW_LANDED"
    LINEAGE_ALLOCATED = "LINEAGE_ALLOCATED"
    PERSISTED = "PERSISTED"


@dataclass(frozen=True, slots=True)
class MarketIngestionRun:
    """Durable same-logical-attempt recovery context."""

    run_id: UUID
    market_series_id: str
    checkpoint: IngestionRunCheckpoint
    raw_artifact: RawRetrievalArtifact | None = None
    storage_token: UUID | None = None
    normalized_batch_sha256: str | None = None
    normalized_datum_count: int | None = None
    allocated_ids: tuple[AllocatedLineageIds, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None
    persisted_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")

        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )

        for field_name in (
            "created_at",
            "updated_at",
            "persisted_at",
        ):
            value = getattr(self, field_name)

            if (
                value is not None
                and value.utcoffset() is None
            ):
                raise ValueError(
                    f"{field_name} must be timezone-aware."
                )

        if (
            self.raw_artifact is not None
            and self.raw_artifact.market_series_id
            != self.market_series_id
        ):
            raise ValueError(
                "raw_artifact market_series_id must match the run."
            )

        if (
            self.raw_artifact is None
        ) != (
            self.storage_token is None
        ):
            raise ValueError(
                "raw_artifact and storage_token must be populated together."
            )

        has_raw = (
            self.raw_artifact is not None
            and self.storage_token is not None
        )

        if (
            self.normalized_batch_sha256 is not None
            and fullmatch(
                r"[0-9a-f]{64}",
                self.normalized_batch_sha256,
            )
            is None
        ):
            raise ValueError(
                "normalized_batch_sha256 must be a lower-case SHA-256 "
                "hex digest."
            )

        if self.normalized_datum_count is not None:
            if (
                isinstance(self.normalized_datum_count, bool)
                or not isinstance(self.normalized_datum_count, int)
            ):
                raise TypeError(
                    "normalized_datum_count must be an integer."
                )

            if self.normalized_datum_count < 1:
                raise ValueError(
                    "normalized_datum_count must be positive."
                )

        populated_lineage_components = (
            self.normalized_batch_sha256 is not None,
            self.normalized_datum_count is not None,
            bool(self.allocated_ids),
        )

        if (
            any(populated_lineage_components)
            and not all(populated_lineage_components)
        ):
            raise ValueError(
                "Normalized fingerprint, datum count, and allocated IDs "
                "must be populated together."
            )

        has_lineage = all(
            populated_lineage_components
        )

        if has_lineage:
            assert self.normalized_datum_count is not None

            if len(self.allocated_ids) != self.normalized_datum_count:
                raise ValueError(
                    "allocated_ids must contain exactly one bundle per "
                    "normalized datum."
                )

            source_ids = {
                ids.source_id
                for ids in self.allocated_ids
            }

            if len(source_ids) != 1:
                raise ValueError(
                    "All retained allocation bundles must share one source_id."
                )

        if self.checkpoint is IngestionRunCheckpoint.STARTED:
            if has_raw or has_lineage or self.persisted_at is not None:
                raise ValueError(
                    "STARTED runs must not contain downstream checkpoint state."
                )

        elif self.checkpoint is IngestionRunCheckpoint.RAW_LANDED:
            if not has_raw:
                raise ValueError(
                    "RAW_LANDED runs require immutable raw-artifact state."
                )

            if has_lineage or self.persisted_at is not None:
                raise ValueError(
                    "RAW_LANDED runs must not contain lineage or persisted state."
                )

        elif self.checkpoint is IngestionRunCheckpoint.LINEAGE_ALLOCATED:
            if not has_raw or not has_lineage:
                raise ValueError(
                    "LINEAGE_ALLOCATED runs require raw and lineage state."
                )

            if self.persisted_at is not None:
                raise ValueError(
                    "LINEAGE_ALLOCATED runs must not have persisted_at."
                )

        elif self.checkpoint is IngestionRunCheckpoint.PERSISTED:
            if not has_raw or not has_lineage:
                raise ValueError(
                    "PERSISTED runs require raw and lineage state."
                )

            if self.persisted_at is None:
                raise ValueError(
                    "PERSISTED runs require persisted_at."
                )

        else:
            raise ValueError(
                f"Unsupported ingestion-run checkpoint: {self.checkpoint!r}."
            )


def compute_normalized_market_batch_sha256(
    datums: tuple[NormalizedMarketDatum, ...],
) -> str:
    """Fingerprint the exact ordered normalized batch bound to lineage IDs."""

    if not isinstance(datums, tuple):
        raise TypeError(
            "datums must be a tuple."
        )

    if not datums:
        raise ValueError(
            "Normalized batch fingerprinting requires at least one datum."
        )

    payload = {
        "schema": "normalized_market_datum_v1",
        "datums": [
            {
                "market_series_id": datum.market_series_id,
                "field_name": datum.field_name,
                "as_of_date": datum.as_of_date.isoformat(),
                "evidence_locator": datum.evidence_locator,
                "value": (
                    str(datum.value)
                    if datum.value is not None
                    else None
                ),
                "missing_state": (
                    datum.missing_state.value
                    if datum.missing_state is not None
                    else None
                ),
                "unit": datum.unit,
                "currency": datum.currency,
                "evidence_label": datum.evidence_label,
                "notes": datum.notes,
            }
            for datum in datums
        ],
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    return sha256(encoded).hexdigest()
