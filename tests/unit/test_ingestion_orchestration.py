"""Tests for retrieve-land-normalize ingestion ordering."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest

import european_capital_markets.ingestion.orchestration as orchestration
from european_capital_markets.ingestion.providers.ecb import (
    create_ecb_client,
)
from european_capital_markets.ingestion.raw_storage import (
    ImmutableRawArtifactStore,
)
from european_capital_markets.reference_data import (
    load_market_series_catalog,
)

_PROVIDER_ID = (
    "FM.D.U2.EUR.4F.KR.DFR.LEV"
)

_TOKEN = UUID(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
)

_SYNTHETIC_CSV = (
    b"KEY,FREQ,CURRENCY,PROVIDER_FM_ID,"
    b"DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,UNIT,TITLE\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-18,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-19,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-20,2.5,PCPA,Deposit facility\n"
)


def _catalog_entry():
    catalog = load_market_series_catalog(
        "data/reference/market_series_catalog.json"
    )

    return next(
        entry
        for entry in catalog.entries
        if (
            entry.market_series.market_series_id
            == "MKS000000001"
        )
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


def _client(
    content: bytes = _SYNTHETIC_CSV,
) -> httpx.Client:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "Content-Type": "text/csv",
            },
            content=content,
        )

    return create_ecb_client(
        transport=httpx.MockTransport(
            handler
        )
    )


def test_ecb_orchestration_retrieves_lands_then_normalizes(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    with _client() as client:
        result = (
            orchestration.retrieve_land_normalize_ecb_dfr(
                client,
                _catalog_entry(),
                store,
                last_n_observations=3,
                storage_token=_TOKEN,
            )
        )

    assert (
        result.raw_landing.filesystem_path.read_bytes()
        == _SYNTHETIC_CSV
    )

    assert len(
        result.datums
    ) == 3

    assert (
        result.datums[-1].as_of_date
        == date(
            2026,
            9,
            20,
        )
    )

    assert (
        result.datums[-1].value
        == Decimal("2.5")
    )


def test_raw_artifact_exists_before_parser_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(
        tmp_path
    )

    original_parser = (
        orchestration.parse_ecb_dfr_csv
    )

    def asserting_parser(
        content: bytes,
        *,
        market_series_id: str,
        expected_provider_series_id: str,
    ):
        landed = list(
            store.root.rglob(
                "*.csv"
            )
        )

        assert len(
            landed
        ) == 1

        assert (
            landed[0].read_bytes()
            == content
        )

        return original_parser(
            content,
            market_series_id=(
                market_series_id
            ),
            expected_provider_series_id=(
                expected_provider_series_id
            ),
        )

    monkeypatch.setattr(
        orchestration,
        "parse_ecb_dfr_csv",
        asserting_parser,
    )

    with _client() as client:
        orchestration.retrieve_land_normalize_ecb_dfr(
            client,
            _catalog_entry(),
            store,
            storage_token=_TOKEN,
        )


def test_parser_failure_preserves_raw_provider_bytes(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    malformed = (
        b"KEY,TIME_PERIOD\n"
        + _PROVIDER_ID.encode()
        + b",2026-09-20\n"
    )

    with (
        _client(
            malformed
        ) as client,
        pytest.raises(
            ValueError,
            match="missing required columns",
        ),
    ):
        orchestration.retrieve_land_normalize_ecb_dfr(
            client,
            _catalog_entry(),
            store,
            storage_token=_TOKEN,
        )

    landed = list(
        store.root.rglob(
            "*.csv"
        )
    )

    assert len(
        landed
    ) == 1

    assert (
        landed[0].read_bytes()
        == malformed
    )


def test_orchestration_builds_actual_retrieval_provenance(
    tmp_path: Path,
) -> None:
    store = _store(
        tmp_path
    )

    with _client() as client:
        result = (
            orchestration.retrieve_land_normalize_ecb_dfr(
                client,
                _catalog_entry(),
                store,
                storage_token=_TOKEN,
            )
        )

    source = (
        result.raw_landing.artifact.source
    )

    assert (
        source.publisher
        == "European Central Bank"
    )

    assert (
        source.retrieval_identifier
        == _PROVIDER_ID
    )

    assert (
        source.url
        == result.retrieval.response_url
    )

    assert (
        source.title
        == "ECB Data Portal: Deposit Facility Rate"
    )


def test_end_to_end_canonical_persistence_composes_reviewed_boundaries(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    calls = []

    client = object()
    catalog_entry = object()
    raw_store = object()
    engine = object()
    storage_token = object()

    artifact = object()

    datums = (
        object(),
        object(),
    )

    raw_ingestion = (
        orchestration.EcbDfrRawIngestionResult(
            retrieval=object(),
            raw_landing=SimpleNamespace(
                artifact=artifact,
            ),
            datums=datums,
        )
    )

    allocated_ids = (
        object(),
        object(),
    )

    dataset = object()

    handoff = SimpleNamespace(
        dataset=dataset,
    )

    status = (
        orchestration
        .MarketObservationAppendStatus
        .INSERTED
    )

    def fake_retrieve(
        actual_client,
        actual_catalog_entry,
        actual_raw_store,
        *,
        last_n_observations,
        storage_token,
    ):
        calls.append(
            (
                "retrieve",
                actual_client,
                actual_catalog_entry,
                actual_raw_store,
                last_n_observations,
                storage_token,
            )
        )

        return raw_ingestion

    def fake_allocate(
        actual_engine,
        datum_count,
    ):
        calls.append(
            (
                "allocate",
                actual_engine,
                datum_count,
            )
        )

        return allocated_ids

    def fake_handoff(
        actual_catalog_entry,
        actual_artifact,
        actual_datums,
        actual_allocated_ids,
    ):
        calls.append(
            (
                "handoff",
                actual_catalog_entry,
                actual_artifact,
                actual_datums,
                actual_allocated_ids,
            )
        )

        return handoff

    def fake_persist(
        actual_engine,
        actual_dataset,
    ):
        calls.append(
            (
                "persist",
                actual_engine,
                actual_dataset,
            )
        )

        return status

    monkeypatch.setattr(
        orchestration,
        "retrieve_land_normalize_ecb_dfr",
        fake_retrieve,
    )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_lineage_ids",
        fake_allocate,
    )

    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        fake_handoff,
    )

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        fake_persist,
    )

    result = (
        orchestration
        .ingest_ecb_dfr_to_canonical_persistence(
            client,
            catalog_entry,
            raw_store,
            engine,
            last_n_observations=5,
            storage_token=storage_token,
        )
    )

    assert calls == [
        (
            "retrieve",
            client,
            catalog_entry,
            raw_store,
            5,
            storage_token,
        ),
        (
            "allocate",
            engine,
            2,
        ),
        (
            "handoff",
            catalog_entry,
            artifact,
            datums,
            allocated_ids,
        ),
        (
            "persist",
            engine,
            dataset,
        ),
    ]

    assert (
        result.raw_ingestion
        is raw_ingestion
    )

    assert (
        result.allocated_ids
        is allocated_ids
    )

    assert (
        result.handoff
        is handoff
    )

    assert (
        result.persistence_status
        is status
    )


def test_end_to_end_orchestration_stops_if_retrieval_fails(
    monkeypatch,
) -> None:
    import pytest

    def fail_retrieval(
        *_args,
        **_kwargs,
    ):
        raise RuntimeError(
            "retrieval failed"
        )

    def forbidden(
        *_args,
        **_kwargs,
    ):
        raise AssertionError(
            "downstream boundary must not run"
        )

    monkeypatch.setattr(
        orchestration,
        "retrieve_land_normalize_ecb_dfr",
        fail_retrieval,
    )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_lineage_ids",
        forbidden,
    )

    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        forbidden,
    )

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        forbidden,
    )

    with pytest.raises(
        RuntimeError,
        match="retrieval failed",
    ):
        (
            orchestration
            .ingest_ecb_dfr_to_canonical_persistence(
                object(),
                object(),
                object(),
                object(),
            )
        )


def test_end_to_end_orchestration_stops_if_allocation_fails(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    import pytest

    raw_ingestion = (
        orchestration.EcbDfrRawIngestionResult(
            retrieval=object(),
            raw_landing=SimpleNamespace(
                artifact=object(),
            ),
            datums=(
                object(),
            ),
        )
    )

    monkeypatch.setattr(
        orchestration,
        "retrieve_land_normalize_ecb_dfr",
        lambda *_args, **_kwargs: (
            raw_ingestion
        ),
    )

    def fail_allocation(
        *_args,
        **_kwargs,
    ):
        raise RuntimeError(
            "allocation failed"
        )

    def forbidden(
        *_args,
        **_kwargs,
    ):
        raise AssertionError(
            "downstream boundary must not run"
        )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_lineage_ids",
        fail_allocation,
    )

    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        forbidden,
    )

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        forbidden,
    )

    with pytest.raises(
        RuntimeError,
        match="allocation failed",
    ):
        (
            orchestration
            .ingest_ecb_dfr_to_canonical_persistence(
                object(),
                object(),
                object(),
                object(),
            )
        )


def test_end_to_end_orchestration_stops_if_handoff_fails(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    import pytest

    raw_ingestion = (
        orchestration.EcbDfrRawIngestionResult(
            retrieval=object(),
            raw_landing=SimpleNamespace(
                artifact=object(),
            ),
            datums=(
                object(),
            ),
        )
    )

    monkeypatch.setattr(
        orchestration,
        "retrieve_land_normalize_ecb_dfr",
        lambda *_args, **_kwargs: (
            raw_ingestion
        ),
    )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_lineage_ids",
        lambda *_args, **_kwargs: (
            object(),
        ),
    )

    def fail_handoff(
        *_args,
        **_kwargs,
    ):
        raise RuntimeError(
            "handoff failed"
        )

    def forbidden(
        *_args,
        **_kwargs,
    ):
        raise AssertionError(
            "persistence must not run"
        )

    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        fail_handoff,
    )

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        forbidden,
    )

    with pytest.raises(
        RuntimeError,
        match="handoff failed",
    ):
        (
            orchestration
            .ingest_ecb_dfr_to_canonical_persistence(
                object(),
                object(),
                object(),
                object(),
            )
        )


def test_end_to_end_orchestration_does_not_retry_persistence(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    import pytest

    calls = {
        "retrieve": 0,
        "allocate": 0,
        "handoff": 0,
        "persist": 0,
    }

    raw_ingestion = (
        orchestration.EcbDfrRawIngestionResult(
            retrieval=object(),
            raw_landing=SimpleNamespace(
                artifact=object(),
            ),
            datums=(
                object(),
            ),
        )
    )

    handoff = SimpleNamespace(
        dataset=object(),
    )

    def fake_retrieve(
        *_args,
        **_kwargs,
    ):
        calls["retrieve"] += 1
        return raw_ingestion

    def fake_allocate(
        *_args,
        **_kwargs,
    ):
        calls["allocate"] += 1
        return (
            object(),
        )

    def fake_handoff(
        *_args,
        **_kwargs,
    ):
        calls["handoff"] += 1
        return handoff

    def fail_persistence(
        *_args,
        **_kwargs,
    ):
        calls["persist"] += 1
        raise RuntimeError(
            "persistence failed"
        )

    monkeypatch.setattr(
        orchestration,
        "retrieve_land_normalize_ecb_dfr",
        fake_retrieve,
    )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_lineage_ids",
        fake_allocate,
    )

    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        fake_handoff,
    )

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        fail_persistence,
    )

    with pytest.raises(
        RuntimeError,
        match="persistence failed",
    ):
        (
            orchestration
            .ingest_ecb_dfr_to_canonical_persistence(
                object(),
                object(),
                object(),
                object(),
            )
        )

    assert calls == {
        "retrieve": 1,
        "allocate": 1,
        "handoff": 1,
        "persist": 1,
    }
