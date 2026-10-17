"""Adapter error routing only; real transaction guarantees live in integration tests."""

import hashlib
import platform
from datetime import date

import pytest
from sqlalchemy.exc import OperationalError

import european_capital_markets.persistence.analytics as adapter
from european_capital_markets.analytics import RateChangeRequest
from european_capital_markets.analytics.bundles import BundleError, ExecutionIdentity

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


def _execution():
    return ExecutionIdentity(
        "a" * 40,
        hashlib.sha256(b"source").hexdigest(),
        hashlib.sha256(b"lock").hexdigest(),
        platform.python_implementation(),
        platform.python_version(),
        True,
    )


@pytest.mark.parametrize("bad_request", [True, False])
def test_bundle_capture_rejects_invalid_arguments_before_acquisition(
    monkeypatch, bad_request
):
    def forbidden(*args):
        pytest.fail("Invalid capture arguments must not acquire a snapshot.")

    monkeypatch.setattr(adapter, "load_canonical_dataset", forbidden)
    with pytest.raises(
        TypeError, match="RateChangeRequest" if bad_request else "ExecutionIdentity"
    ):
        adapter.create_rate_change_bundle_from_database(
            object(),
            object() if bad_request else REQUEST,
            _execution() if bad_request else object(),
        )


@pytest.mark.parametrize(
    "error",
    [
        OperationalError(None, None, RuntimeError("synthetic connection failure")),
        ValueError("synthetic reconstructed invalid state"),
    ],
)
def test_bundle_capture_reader_failure_never_enters_pure_creation(monkeypatch, error):
    calls = []

    def fail(engine):
        calls.append(engine)
        raise error

    def forbidden(*args):
        pytest.fail("Failed acquisition cannot produce a bundle.")

    monkeypatch.setattr(adapter, "load_canonical_dataset", fail)
    monkeypatch.setattr(adapter, "create_rate_change_bundle", forbidden)
    engine = object()
    with pytest.raises(type(error)) as caught:
        adapter.create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    assert caught.value is error
    assert calls == [engine]


def test_bundle_capture_pure_failure_propagates_without_retry_or_reacquisition(
    monkeypatch,
):
    engine, snapshot = object(), object()
    execution = _execution()
    calls = []
    error = BundleError("synthetic codec rejection")

    def load(actual_engine):
        assert actual_engine is engine
        calls.append("load")
        return snapshot

    def fail(dataset, request, identity):
        assert dataset is snapshot and request is REQUEST and identity is execution
        calls.append("create")
        raise error

    monkeypatch.setattr(adapter, "load_canonical_dataset", load)
    monkeypatch.setattr(adapter, "create_rate_change_bundle", fail)
    with pytest.raises(BundleError) as caught:
        adapter.create_rate_change_bundle_from_database(engine, REQUEST, execution)
    assert caught.value is error
    assert calls == ["load", "create"]
