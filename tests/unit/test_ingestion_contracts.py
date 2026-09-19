"""Unit tests for provider-neutral market-data ingestion contracts."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from european_capital_markets.domain.taxonomy import (
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.ingestion import (
    AllocatedLineageIds,
    NormalizedMarketDatum,
    RawRetrievalArtifact,
    RetrievalSource,
    build_pending_market_lineage,
    compute_sha256,
    validate_raw_artifact_content,
)
from european_capital_markets.reference_data import (
    load_market_series_catalog,
)


def _catalog_entry(series_id: str):
    catalog = load_market_series_catalog(
        Path("data/reference/market_series_catalog.json")
    )

    return next(
        entry
        for entry in catalog.entries
        if entry.market_series.market_series_id == series_id
    )


def _retrieval_source() -> RetrievalSource:
    return RetrievalSource(
        publisher="Controlled Test Provider",
        source_tier=SourceTier.ESTABLISHED_MARKET_DATA,
        source_type=SourceType.MARKET_DATA,
        title="Synthetic policy-rate response",
        url="https://example.test/market-data",
        retrieval_identifier="TEST-SERIES-001",
    )


def _artifact(
    content: bytes = b'{"value":"2.00"}',
) -> RawRetrievalArtifact:
    return RawRetrievalArtifact(
        market_series_id="MKS000000001",
        source=_retrieval_source(),
        retrieved_at=datetime(
            2026,
            9,
            19,
            14,
            30,
            tzinfo=UTC,
        ),
        archived_location=(
            "data/raw/test-provider/"
            "2026-09-19/MKS000000001.json"
        ),
        content_sha256=compute_sha256(content),
        byte_length=len(content),
        media_type="application/json",
    )


def _datum() -> NormalizedMarketDatum:
    return NormalizedMarketDatum(
        market_series_id="MKS000000001",
        field_name="market_series.rate_percent",
        as_of_date=date(2026, 9, 19),
        evidence_locator="$.value",
        value=Decimal("2.00"),
        unit="PERCENT",
        evidence_label="Synthetic policy-rate field",
    )


def _ids() -> AllocatedLineageIds:
    return AllocatedLineageIds(
        source_id="SRC000000001",
        evidence_id="EVD000000001",
        observation_id="OBS000000001",
    )


def test_compute_sha256_is_deterministic() -> None:
    content = b"canonical raw bytes"

    assert (
        compute_sha256(content)
        == (
            "365c6337d95e8238168f9a40eaf19230"
            "765aefeda50994b8cefcaf1459662282"
        )
    )


def test_raw_artifact_content_round_trip_validates() -> None:
    content = b'{"value":"2.00"}'
    artifact = _artifact(content)

    validate_raw_artifact_content(
        artifact,
        content,
    )


def test_raw_artifact_content_rejects_hash_mismatch() -> None:
    artifact = _artifact()

    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        validate_raw_artifact_content(
            artifact,
            b'{"value":"3.00"}',
        )


def test_raw_artifact_requires_timezone_aware_retrieval() -> None:
    content = b"payload"

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        RawRetrievalArtifact(
            market_series_id="MKS000000001",
            source=_retrieval_source(),
            retrieved_at=datetime(
                2026,
                9,
                19,
                14,
                30,
            ),
            archived_location="data/raw/example.bin",
            content_sha256=compute_sha256(content),
            byte_length=len(content),
        )


def test_normalized_market_datum_requires_exactly_one_state() -> None:
    with pytest.raises(
        ValueError,
        match="Exactly one",
    ):
        NormalizedMarketDatum(
            market_series_id="MKS000000001",
            field_name="market_series.rate_percent",
            as_of_date=date(2026, 9, 19),
            evidence_locator="$.value",
        )


def test_build_pending_market_lineage_preserves_boundaries() -> None:
    records = build_pending_market_lineage(
        _catalog_entry("MKS000000001"),
        _artifact(),
        _datum(),
        _ids(),
    )

    assert records.source.publisher == "Controlled Test Provider"
    assert records.source.access_date == date(2026, 9, 19)
    assert (
        records.source.archived_location
        == (
            "data/raw/test-provider/"
            "2026-09-19/MKS000000001.json"
        )
    )

    assert records.evidence.source_id == "SRC000000001"
    assert records.evidence.locator == "$.value"

    assert (
        records.observation.verification_state
        is VerificationState.PENDING
    )
    assert records.observation.verified_at is None
    assert (
        records.observation.value_class
        is ValueClass.DISCLOSED
    )
    assert records.observation.value == Decimal("2.00")
    assert records.observation.evidence_ids == (
        "EVD000000001",
    )


def test_unavailable_datum_remains_unverified() -> None:
    datum = NormalizedMarketDatum(
        market_series_id="MKS000000001",
        field_name="market_series.rate_percent",
        as_of_date=date(2026, 9, 19),
        evidence_locator="$.value",
        missing_state=MissingDataState.UNAVAILABLE,
        unit="PERCENT",
    )

    records = build_pending_market_lineage(
        _catalog_entry("MKS000000001"),
        _artifact(),
        datum,
        _ids(),
    )

    assert (
        records.observation.verification_state
        is VerificationState.UNAVAILABLE
    )
    assert records.observation.verified_at is None
    assert records.observation.value is None
    assert records.observation.value_class is None
    assert (
        records.observation.missing_state
        is MissingDataState.UNAVAILABLE
    )


def test_lineage_builder_rejects_series_mismatch() -> None:
    artifact = RawRetrievalArtifact(
        market_series_id="MKS000000002",
        source=_retrieval_source(),
        retrieved_at=datetime(
            2026,
            9,
            19,
            14,
            30,
            tzinfo=UTC,
        ),
        archived_location="data/raw/example.json",
        content_sha256=compute_sha256(b"payload"),
        byte_length=len(b"payload"),
    )

    with pytest.raises(
        ValueError,
        match="Raw artifact market_series_id",
    ):
        build_pending_market_lineage(
            _catalog_entry("MKS000000001"),
            artifact,
            _datum(),
            _ids(),
        )
