"""Provider-neutral contracts for controlled market-data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from re import fullmatch

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.reference_data.market_series_catalog import (
    MarketSeriesCatalogEntry,
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")


@dataclass(frozen=True, slots=True)
class RetrievalSource:
    """Actual source used for one retrieval, independent of catalog selection."""

    publisher: str
    source_tier: SourceTier
    source_type: SourceType
    title: str
    url: str | None = None
    retrieval_identifier: str | None = None
    document_date: date | None = None
    publication_date: date | None = None
    document_version: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.publisher, "publisher")
        _require_non_blank(self.title, "title")

        for field_name in (
            "url",
            "retrieval_identifier",
            "document_version",
            "notes",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_non_blank(value, field_name)


@dataclass(frozen=True, slots=True)
class RawRetrievalArtifact:
    """Integrity metadata for source bytes preserved exactly as retrieved."""

    market_series_id: str
    source: RetrievalSource
    retrieved_at: datetime
    archived_location: str
    content_sha256: str
    byte_length: int
    media_type: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )

        if self.retrieved_at.utcoffset() is None:
            raise ValueError(
                "retrieved_at must be timezone-aware."
            )

        _require_non_blank(
            self.archived_location,
            "archived_location",
        )

        if (
            fullmatch(
                r"[0-9a-f]{64}",
                self.content_sha256,
            )
            is None
        ):
            raise ValueError(
                "content_sha256 must be a lower-case SHA-256 hex digest."
            )

        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
        ):
            raise TypeError(
                "byte_length must be an integer."
            )

        if self.byte_length < 0:
            raise ValueError(
                "byte_length must not be negative."
            )

        if self.media_type is not None:
            _require_non_blank(
                self.media_type,
                "media_type",
            )


@dataclass(frozen=True, slots=True)
class NormalizedMarketDatum:
    """One provider-neutral datum ready for canonical lineage construction."""

    market_series_id: str
    field_name: str
    as_of_date: date
    evidence_locator: str
    value: Decimal | None = None
    missing_state: MissingDataState | None = None
    unit: str | None = None
    currency: str | None = None
    evidence_label: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )

        if (
            fullmatch(
                r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*",
                self.field_name,
            )
            is None
        ):
            raise ValueError(
                "field_name must use canonical lower-case "
                "snake_case segments."
            )

        _require_non_blank(
            self.evidence_locator,
            "evidence_locator",
        )

        has_value = self.value is not None
        has_missing_state = self.missing_state is not None

        if has_value == has_missing_state:
            raise ValueError(
                "Exactly one of value or missing_state must be populated."
            )

        if has_value and not isinstance(
            self.value,
            Decimal,
        ):
            raise TypeError(
                "Normalized market values require Decimal."
            )

        if self.unit is not None:
            _require_non_blank(
                self.unit,
                "unit",
            )

        if (
            self.currency is not None
            and fullmatch(
                r"[A-Z]{3}",
                self.currency,
            )
            is None
        ):
            raise ValueError(
                "currency must be a three-letter upper-case code."
            )

        if self.evidence_label is not None:
            _require_non_blank(
                self.evidence_label,
                "evidence_label",
            )

        if self.notes is not None:
            _require_non_blank(
                self.notes,
                "notes",
            )


@dataclass(frozen=True, slots=True)
class AllocatedLineageIds:
    """Canonical IDs allocated outside ingestion transformation logic."""

    source_id: str
    evidence_id: str
    observation_id: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.source_id,
            EntityType.SOURCE,
        )
        validate_identifier(
            self.evidence_id,
            EntityType.EVIDENCE,
        )
        validate_identifier(
            self.observation_id,
            EntityType.OBSERVATION,
        )


@dataclass(frozen=True, slots=True)
class MarketLineageRecords:
    """Canonical lineage records produced from one normalized market datum."""

    source: SourceRecord
    evidence: EvidenceRecord
    observation: ObservationRecord


def compute_sha256(content: bytes) -> str:
    """Return the canonical lower-case SHA-256 digest for raw source bytes."""

    if not isinstance(content, bytes):
        raise TypeError(
            "Raw artifact content must be bytes."
        )

    return sha256(content).hexdigest()


def validate_raw_artifact_content(
    artifact: RawRetrievalArtifact,
    content: bytes,
) -> None:
    """Verify that raw bytes match the artifact's frozen integrity metadata."""

    if not isinstance(content, bytes):
        raise TypeError(
            "Raw artifact content must be bytes."
        )

    if len(content) != artifact.byte_length:
        raise ValueError(
            "Raw artifact byte length does not match metadata."
        )

    digest = compute_sha256(content)

    if digest != artifact.content_sha256:
        raise ValueError(
            "Raw artifact SHA-256 does not match metadata."
        )


def build_pending_market_lineage(
    catalog_entry: MarketSeriesCatalogEntry,
    artifact: RawRetrievalArtifact,
    datum: NormalizedMarketDatum,
    ids: AllocatedLineageIds,
) -> MarketLineageRecords:
    """Construct non-auto-verified canonical lineage from normalized input.

    The catalog entry selects the canonical economic series. The raw artifact
    identifies the actual source used for this retrieval. Those concepts are
    intentionally separate because an ingestion distributor or endpoint may
    differ from the administrator identifier retained by controlled reference
    data.

    This function never promotes a populated observation to a verified state.
    Verification remains a separate governance action.
    """

    expected_series_id = (
        catalog_entry.market_series.market_series_id
    )

    if artifact.market_series_id != expected_series_id:
        raise ValueError(
            "Raw artifact market_series_id does not match "
            "the selected catalog entry."
        )

    if datum.market_series_id != expected_series_id:
        raise ValueError(
            "Normalized datum market_series_id does not match "
            "the selected catalog entry."
        )

    source = SourceRecord(
        source_id=ids.source_id,
        tier=artifact.source.source_tier,
        source_type=artifact.source.source_type,
        publisher=artifact.source.publisher,
        title=artifact.source.title,
        access_date=artifact.retrieved_at.date(),
        document_date=artifact.source.document_date,
        publication_date=artifact.source.publication_date,
        url=artifact.source.url,
        archived_location=artifact.archived_location,
        document_version=artifact.source.document_version,
        notes=artifact.source.notes,
    )

    evidence = EvidenceRecord(
        evidence_id=ids.evidence_id,
        source_id=ids.source_id,
        locator=datum.evidence_locator,
        label=datum.evidence_label,
    )

    verification_state = VerificationState.PENDING

    if datum.missing_state is MissingDataState.UNAVAILABLE:
        verification_state = VerificationState.UNAVAILABLE

    observation = ObservationRecord(
        observation_id=ids.observation_id,
        subject_type=EntityType.MARKET_SERIES,
        subject_id=expected_series_id,
        field_name=datum.field_name,
        as_of_date=datum.as_of_date,
        verification_state=verification_state,
        value=datum.value,
        value_class=(
            ValueClass.DISCLOSED
            if datum.value is not None
            else None
        ),
        missing_state=datum.missing_state,
        unit=datum.unit,
        currency=datum.currency,
        evidence_ids=(ids.evidence_id,),
        notes=datum.notes,
    )

    return MarketLineageRecords(
        source=source,
        evidence=evidence,
        observation=observation,
    )
