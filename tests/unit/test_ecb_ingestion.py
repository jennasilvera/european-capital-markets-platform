"""Tests for the controlled ECB Data Portal ingestion adapter."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from european_capital_markets.domain.taxonomy import (
    MarketSeriesType,
)
from european_capital_markets.ingestion.providers.ecb import (
    ECB_DATA_API_BASE_URL,
    build_ecb_data_url,
    create_ecb_client,
    fetch_ecb_csv,
    fetch_ecb_dfr,
    parse_ecb_dfr_csv,
)
from european_capital_markets.reference_data import (
    load_market_series_catalog,
)

_PROVIDER_ID = (
    "FM.D.U2.EUR.4F.KR.DFR.LEV"
)

_SYNTHETIC_CSV = (
    b"KEY,FREQ,CURRENCY,PROVIDER_FM_ID,"
    b"DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,UNIT,TITLE\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-17,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-18,2.5,PCPA,Deposit facility\n"
    b"FM.D.U2.EUR.4F.KR.DFR.LEV,D,EUR,DFR,"
    b"LEV,2026-09-19,2.5,PCPA,Deposit facility\n"
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


def test_build_ecb_data_url_from_catalog_identifier() -> None:
    assert build_ecb_data_url(
        _PROVIDER_ID
    ) == (
        f"{ECB_DATA_API_BASE_URL}/"
        "FM/D.U2.EUR.4F.KR.DFR.LEV"
    )


def test_fetch_ecb_csv_builds_bounded_request() -> None:
    captured: dict[
        str,
        httpx.Request,
    ] = {}

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        captured["request"] = request

        return httpx.Response(
            200,
            headers={
                "Content-Type": (
                    "text/csv; charset=utf-8"
                ),
                "Last-Modified": (
                    "Fri, 18 Sep 2026 23:35:54 GMT"
                ),
                "Cache-Control": "max-age=30",
            },
            content=_SYNTHETIC_CSV,
        )

    transport = httpx.MockTransport(
        handler
    )

    with create_ecb_client(
        transport=transport
    ) as client:
        result = fetch_ecb_csv(
            client,
            _PROVIDER_ID,
            last_n_observations=3,
        )

    request = captured["request"]

    assert request.method == "GET"
    assert (
        request.url.path
        == (
            "/service/data/"
            "FM/D.U2.EUR.4F.KR.DFR.LEV"
        )
    )
    assert (
        request.url.params["format"]
        == "csvdata"
    )
    assert (
        request.url.params[
            "lastNObservations"
        ]
        == "3"
    )
    assert (
        request.headers["accept"]
        == "text/csv"
    )
    assert "authorization" not in (
        request.headers
    )

    assert result.status_code == 200
    assert result.media_type == "text/csv"
    assert (
        result.content
        == _SYNTHETIC_CSV
    )
    assert (
        result.last_modified
        == "Fri, 18 Sep 2026 23:35:54 GMT"
    )
    assert (
        result.cache_control
        == "max-age=30"
    )
    assert (
        result.retrieved_at.utcoffset()
        is not None
    )


def test_fetch_ecb_csv_raises_for_http_error() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            503,
            request=request,
            text="unavailable",
        )

    with create_ecb_client(
        transport=httpx.MockTransport(
            handler
        )
    ) as client, pytest.raises(
        httpx.HTTPStatusError
    ):
        fetch_ecb_csv(
            client,
            _PROVIDER_ID,
            last_n_observations=3,
        )


def test_fetch_ecb_csv_rejects_wrong_media_type() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "Content-Type": (
                    "text/html"
                ),
            },
            content=b"<html></html>",
        )

    with create_ecb_client(
        transport=httpx.MockTransport(
            handler
        )
    ) as client, pytest.raises(
        ValueError,
        match="text/csv",
    ):
        fetch_ecb_csv(
            client,
            _PROVIDER_ID,
            last_n_observations=3,
        )


def test_parse_ecb_dfr_csv_maps_observations() -> None:
    datums = parse_ecb_dfr_csv(
        _SYNTHETIC_CSV,
        market_series_id=(
            "MKS000000001"
        ),
        expected_provider_series_id=(
            _PROVIDER_ID
        ),
    )

    assert len(datums) == 3

    assert [
        datum.as_of_date
        for datum in datums
    ] == [
        date(2026, 9, 17),
        date(2026, 9, 18),
        date(2026, 9, 19),
    ]

    assert all(
        datum.value
        == Decimal("2.5")
        for datum in datums
    )

    assert all(
        datum.field_name
        == "market_series.rate_percent"
        for datum in datums
    )

    assert all(
        datum.unit == "PERCENT"
        for datum in datums
    )


def test_parse_ecb_dfr_csv_rejects_missing_columns() -> None:
    content = (
        "KEY,TIME_PERIOD\n"
        f"{_PROVIDER_ID},2026-09-19\n"
    ).encode()

    with pytest.raises(
        ValueError,
        match="missing required columns",
    ):
        parse_ecb_dfr_csv(
            content,
            market_series_id=(
                "MKS000000001"
            ),
            expected_provider_series_id=(
                _PROVIDER_ID
            ),
        )


def test_parse_ecb_dfr_csv_rejects_key_mismatch() -> None:
    bad = _SYNTHETIC_CSV.replace(
        _PROVIDER_ID.encode(),
        b"FM.D.U2.EUR.4F.KR.OTHER.LEV",
        1,
    )

    with pytest.raises(
        ValueError,
        match="KEY does not match",
    ):
        parse_ecb_dfr_csv(
            bad,
            market_series_id=(
                "MKS000000001"
            ),
            expected_provider_series_id=(
                _PROVIDER_ID
            ),
        )


def test_parse_ecb_dfr_csv_rejects_semantic_metadata_mismatch() -> None:
    bad = _SYNTHETIC_CSV.replace(
        b",PCPA,Deposit facility",
        b",INDEX,Deposit facility",
        1,
    )

    with pytest.raises(
        ValueError,
        match="metadata mismatch",
    ):
        parse_ecb_dfr_csv(
            bad,
            market_series_id=(
                "MKS000000001"
            ),
            expected_provider_series_id=(
                _PROVIDER_ID
            ),
        )


def test_fetch_ecb_dfr_uses_controlled_catalog_entry() -> None:
    entry = _catalog_entry()

    assert (
        entry.market_series.series_type
        is MarketSeriesType.POLICY_RATE
    )

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "Content-Type": "text/csv",
            },
            content=_SYNTHETIC_CSV,
        )

    with create_ecb_client(
        transport=httpx.MockTransport(
            handler
        )
    ) as client:
        result = fetch_ecb_dfr(
            client,
            entry,
            last_n_observations=3,
        )

    assert (
        result.retrieval.status_code
        == 200
    )
    assert len(result.datums) == 3
    assert (
        result.datums[-1].as_of_date
        == date(2026, 9, 19)
    )
    assert (
        result.datums[-1].value
        == Decimal("2.5")
    )


def test_fetch_ecb_csv_rejects_non_positive_bound() -> None:
    with create_ecb_client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={
                    "Content-Type": "text/csv",
                },
                content=_SYNTHETIC_CSV,
            )
        )
    ) as client, pytest.raises(
        ValueError,
        match="positive",
    ):
        fetch_ecb_csv(
            client,
            _PROVIDER_ID,
            last_n_observations=0,
        )
