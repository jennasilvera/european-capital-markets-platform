"""Adapter error routing only; real transaction guarantees live in integration tests."""

from datetime import date

import pytest
from sqlalchemy.exc import OperationalError

import european_capital_markets.persistence.analytics as adapter
from european_capital_markets.analytics import RateChangeRequest

REQUEST = RateChangeRequest(
    "MKS999999998", "market_series.rate_percent", date(2026, 10, 15), date(2026, 10, 16)
)


def test_invalid_request_cannot_open_the_database(monkeypatch):
    def forbidden(*args):
        pytest.fail("Invalid request must not acquire a snapshot.")

    monkeypatch.setattr(adapter, "load_canonical_dataset", forbidden)
    with pytest.raises(TypeError, match="RateChangeRequest"):
        adapter.calculate_rate_change_from_database(object(), object())


@pytest.mark.parametrize(
    "error",
    [
        OperationalError(None, None, RuntimeError("synthetic unavailable dependency")),
        ValueError("synthetic malformed reconstructed snapshot"),
    ],
)
def test_reader_failure_propagates_without_calculation_or_fallback(monkeypatch, error):
    calls = []

    def fail(engine):
        calls.append(engine)
        raise error

    def forbidden(*args):
        pytest.fail("Failed acquisition must not start calculation.")

    monkeypatch.setattr(adapter, "load_canonical_dataset", fail)
    monkeypatch.setattr(adapter, "calculate_rate_change", forbidden)
    engine = object()
    with pytest.raises(type(error)) as caught:
        adapter.calculate_rate_change_from_database(engine, REQUEST)
    assert caught.value is error
    assert calls == [engine]
