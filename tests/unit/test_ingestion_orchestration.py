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
