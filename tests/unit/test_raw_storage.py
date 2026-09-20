"""Tests for immutable raw-artifact filesystem landing."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from european_capital_markets.domain.taxonomy import (
    SourceTier,
    SourceType,
)
from european_capital_markets.ingestion.contracts import (
    RetrievalSource,
    compute_sha256,
)
from european_capital_markets.ingestion.raw_storage import (
    ImmutableRawArtifactStore,
)
from european_capital_markets.ingestion.transport import (
    HttpRetrievedPayload,
)

_URL = (
    "https://example.test/market-data"
)

_TOKEN_1 = UUID(
    "11111111-1111-1111-1111-111111111111"
)

_TOKEN_2 = UUID(
    "22222222-2222-2222-2222-222222222222"
)


def _source() -> RetrievalSource:
    return RetrievalSource(
        publisher="Test Provider",
        source_tier=(
            SourceTier.OFFICIAL_INSTITUTION
        ),
        source_type=(
            SourceType.CENTRAL_BANK_PUBLICATION
        ),
        title="Synthetic market-data response",
        url=_URL,
        retrieval_identifier="TEST.SERIES",
    )


def _retrieval(
    *,
    content: bytes = b"raw-provider-bytes",
    status_code: int = 200,
    retrieved_at: datetime | None = None,
) -> HttpRetrievedPayload:
    return HttpRetrievedPayload(
        request_url=_URL,
        response_url=_URL,
        retrieved_at=(
            retrieved_at
            or datetime(
                2026,
                9,
                20,
                3,
                45,
                12,
                123456,
                tzinfo=UTC,
            )
        ),
        status_code=status_code,
        content=content,
        media_type="text/csv",
        last_modified=(
            "Sat, 19 Sep 2026 23:35:54 GMT"
        ),
    )


def _store(
    tmp_path: Path,
) -> ImmutableRawArtifactStore:
    root = tmp_path / "raw"
    root.mkdir()

    return ImmutableRawArtifactStore(
        root=root,
        archive_location_prefix="data/raw",
    )


def test_land_http_retrieval_writes_exact_bytes_and_metadata(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    retrieval = _retrieval()

    landing = store.land_http_retrieval(
        market_series_id="MKS000000001",
        source=_source(),
        retrieval=retrieval,
        namespace="test-provider",
        suffix=".csv",
        storage_token=_TOKEN_1,
    )

    assert (
        landing.filesystem_path.read_bytes()
        == retrieval.content
    )

    assert (
        landing.artifact.content_sha256
        == compute_sha256(
            retrieval.content
        )
    )

    assert (
        landing.artifact.byte_length
        == len(retrieval.content)
    )

    assert (
        landing.artifact.archived_location
        == (
            "data/raw/test-provider/"
            "MKS000000001/2026/09/20/"
            "20260920T034512.123456Z_"
            "11111111111111111111111111111111.csv"
        )
    )

    assert (
        landing.storage_token
        == _TOKEN_1
    )


def test_identical_bytes_remain_distinct_retrieval_events(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    retrieval = _retrieval(
        content=b"identical"
    )

    first = store.land_http_retrieval(
        market_series_id="MKS000000001",
        source=_source(),
        retrieval=retrieval,
        namespace="test-provider",
        suffix=".csv",
        storage_token=_TOKEN_1,
    )

    second = store.land_http_retrieval(
        market_series_id="MKS000000001",
        source=_source(),
        retrieval=retrieval,
        namespace="test-provider",
        suffix=".csv",
        storage_token=_TOKEN_2,
    )

    assert (
        first.filesystem_path
        != second.filesystem_path
    )

    assert (
        first.artifact.content_sha256
        == second.artifact.content_sha256
    )

    assert (
        first.filesystem_path.read_bytes()
        == second.filesystem_path.read_bytes()
        == b"identical"
    )


def test_collision_never_overwrites_existing_artifact(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    first = store.land_http_retrieval(
        market_series_id="MKS000000001",
        source=_source(),
        retrieval=_retrieval(
            content=b"first"
        ),
        namespace="test-provider",
        suffix=".csv",
        storage_token=_TOKEN_1,
    )

    with pytest.raises(
        FileExistsError
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=_source(),
            retrieval=_retrieval(
                content=b"second"
            ),
            namespace="test-provider",
            suffix=".csv",
            storage_token=_TOKEN_1,
        )

    assert (
        first.filesystem_path.read_bytes()
        == b"first"
    )


def test_non_success_http_response_is_rejected_before_write(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="successful HTTP",
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=_source(),
            retrieval=_retrieval(
                status_code=503
            ),
            namespace="test-provider",
            suffix=".csv",
            storage_token=_TOKEN_1,
        )

    assert not any(
        store.root.iterdir()
    )


def test_source_url_must_match_actual_response_url(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    source = RetrievalSource(
        publisher="Test Provider",
        source_tier=(
            SourceTier.OFFICIAL_INSTITUTION
        ),
        source_type=(
            SourceType.CENTRAL_BANK_PUBLICATION
        ),
        title="Synthetic response",
        url="https://example.test/wrong",
    )

    with pytest.raises(
        ValueError,
        match="actual HTTP response URL",
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=source,
            retrieval=_retrieval(),
            namespace="test-provider",
            suffix=".csv",
            storage_token=_TOKEN_1,
        )

    assert not any(
        store.root.iterdir()
    )


def test_namespace_rejects_path_traversal_before_write(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=_source(),
            retrieval=_retrieval(),
            namespace="../escape",
            suffix=".csv",
            storage_token=_TOKEN_1,
        )

    assert not any(
        store.root.iterdir()
    )


def test_suffix_rejects_path_components(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="suffix",
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=_source(),
            retrieval=_retrieval(),
            namespace="test-provider",
            suffix="../csv",
            storage_token=_TOKEN_1,
        )

    assert not any(
        store.root.iterdir()
    )


def test_existing_symlink_archive_component_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    outside = tmp_path / "outside"

    root.mkdir()
    outside.mkdir()

    (root / "ecb").symlink_to(
        outside,
        target_is_directory=True,
    )

    store = ImmutableRawArtifactStore(
        root=root,
        archive_location_prefix="data/raw",
    )

    with pytest.raises(
        OSError
    ):
        store.land_http_retrieval(
            market_series_id="MKS000000001",
            source=_source(),
            retrieval=_retrieval(),
            namespace="ecb",
            suffix=".csv",
            storage_token=_TOKEN_1,
        )

    assert not any(
        outside.iterdir()
    )


def test_filename_timestamp_is_normalized_to_utc(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    local_zone = timezone(
        timedelta(
            hours=2
        )
    )

    retrieval = _retrieval(
        retrieved_at=datetime(
            2026,
            9,
            20,
            5,
            45,
            12,
            123456,
            tzinfo=local_zone,
        )
    )

    landing = store.land_http_retrieval(
        market_series_id="MKS000000001",
        source=_source(),
        retrieval=retrieval,
        namespace="test-provider",
        suffix=".csv",
        storage_token=_TOKEN_1,
    )

    assert (
        landing.filesystem_path.name
        == (
            "20260920T034512.123456Z_"
            "11111111111111111111111111111111.csv"
        )
    )

    assert (
        landing.artifact.retrieved_at
        == retrieval.retrieved_at
    )
