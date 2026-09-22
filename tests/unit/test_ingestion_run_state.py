from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.ingestion.contracts import NormalizedMarketDatum
from european_capital_markets.ingestion.run_state import (
    compute_normalized_market_batch_sha256,
)


def _datum(
    *,
    as_of_date: date,
    value: str,
    locator: str,
) -> NormalizedMarketDatum:
    return NormalizedMarketDatum(
        market_series_id="MKS000000001",
        field_name="market.policy_rate",
        as_of_date=as_of_date,
        evidence_locator=locator,
        value=Decimal(value),
        unit="PERCENT",
        currency="EUR",
    )


def test_normalized_batch_fingerprint_is_deterministic() -> None:
    datums = (
        _datum(
            as_of_date=date(2026, 9, 18),
            value="2.00",
            locator="row=1",
        ),
        _datum(
            as_of_date=date(2026, 9, 19),
            value="2.10",
            locator="row=2",
        ),
    )

    first = compute_normalized_market_batch_sha256(
        datums
    )
    second = compute_normalized_market_batch_sha256(
        datums
    )

    assert first == second
    assert len(first) == 64


def test_normalized_batch_fingerprint_is_order_sensitive() -> None:
    first = _datum(
        as_of_date=date(2026, 9, 18),
        value="2.00",
        locator="row=1",
    )
    second = _datum(
        as_of_date=date(2026, 9, 19),
        value="2.10",
        locator="row=2",
    )

    assert (
        compute_normalized_market_batch_sha256(
            (first, second)
        )
        != compute_normalized_market_batch_sha256(
            (second, first)
        )
    )


def test_normalized_batch_fingerprint_changes_with_content() -> None:
    baseline = (
        _datum(
            as_of_date=date(2026, 9, 18),
            value="2.00",
            locator="row=1",
        ),
    )
    changed = (
        _datum(
            as_of_date=date(2026, 9, 18),
            value="2.01",
            locator="row=1",
        ),
    )

    assert (
        compute_normalized_market_batch_sha256(
            baseline
        )
        != compute_normalized_market_batch_sha256(
            changed
        )
    )


def test_normalized_batch_fingerprint_requires_tuple() -> None:
    with pytest.raises(
        TypeError,
        match="tuple",
    ):
        compute_normalized_market_batch_sha256(  # type: ignore[arg-type]
            []
        )


def test_normalized_batch_fingerprint_rejects_empty_batch() -> None:
    with pytest.raises(
        ValueError,
        match="at least one",
    ):
        compute_normalized_market_batch_sha256(
            ()
        )
