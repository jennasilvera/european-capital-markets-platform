"""Real PostgreSQL writer -> snapshot reader -> selection -> calculation seams."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Event, get_ident

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError

from european_capital_markets.analytics import (
    RateChangeBlockReason,
    RateChangeRequest,
    RateChangeStatus,
    SelectionBlockReason,
    calculate_rate_change,
)
from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MarketSeriesType,
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence import (
    MarketObservationAppendStatus,
    calculate_rate_change_from_database,
    load_canonical_dataset,
    persist_canonical_dataset,
    persist_market_observation_batch,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL is required for PostgreSQL integration tests.",
)
SERIES_ID = "MKS999999998"
PRIOR = date(2026, 10, 15)
CURRENT = date(2026, 10, 16)
REQUEST = RateChangeRequest(SERIES_ID, "market_series.rate_percent", PRIOR, CURRENT)
# Only these synthetic test source IDs are ever removed; no global truncation.
SOURCE_IDS = [f"SRC{999990000 + n:09d}" for n in range(1, 9)]


def _subject() -> CanonicalDataset:
    return CanonicalDataset(
        market_series=(MarketSeriesRecord(SERIES_ID, MarketSeriesType.POLICY_RATE),),
        policy_rates=(
            PolicyRateDefinitionRecord(
                SERIES_ID,
                "Synthetic snapshot authority",
                "Test jurisdiction",
                "EUR",
                "Snapshot test rate",
                "test/rate-change-snapshot-v1",
            ),
        ),
    )


def _batch(number: int, rows: tuple[tuple[date, str | None, VerificationState], ...]):
    source_id = SOURCE_IDS[number - 1]
    subject = _subject()
    evidence = []
    observations = []
    for ordinal, (day, value, state) in enumerate(rows):
        suffix = 999990000 + number * 10 + ordinal
        evidence_id = f"EVD{suffix:09d}"
        evidence.append(EvidenceRecord(evidence_id, source_id, f"row/{ordinal}"))
        observations.append(
            ObservationRecord(
                observation_id=f"OBS{suffix:09d}",
                subject_type=EntityType.MARKET_SERIES,
                subject_id=SERIES_ID,
                field_name=REQUEST.field_name,
                as_of_date=day,
                verification_state=state,
                verified_at=(
                    None
                    if state
                    in {VerificationState.PENDING, VerificationState.UNAVAILABLE}
                    else datetime(2026, 10, 16, 20, tzinfo=UTC)
                ),
                value=Decimal(value) if value is not None else None,
                value_class=ValueClass.DISCLOSED if value is not None else None,
                missing_state=MissingDataState.UNAVAILABLE if value is None else None,
                unit="PERCENT" if value is not None else None,
                evidence_ids=(evidence_id,),
            )
        )
    return replace(
        subject,
        sources=(
            SourceRecord(
                source_id,
                SourceTier.OFFICIAL_INSTITUTION,
                SourceType.CENTRAL_BANK_PUBLICATION,
                "Synthetic snapshot authority",
                f"Snapshot test retrieval {number}",
                CURRENT,
                url=f"https://example.invalid/snapshot/{number}",
                document_version="fixture-v1",
            ),
        ),
        evidence=tuple(evidence),
        observations=tuple(observations),
    )


def _seed(engine: Engine, prior="2.400", current="2.5500") -> CanonicalDataset:
    dataset = _batch(
        1,
        (
            (PRIOR, prior, VerificationState.SECONDARY_VERIFIED),
            (CURRENT, current, VerificationState.CROSS_VERIFIED),
        ),
    )
    # Shared evidence and non-ID evidence order must survive relational ordinals.
    first, second = dataset.observations
    dataset = replace(
        dataset,
        observations=(
            replace(
                first, evidence_ids=(second.evidence_ids[0], first.evidence_ids[0])
            ),
            second,
        ),
    )
    persist_canonical_dataset(engine, dataset)
    return dataset


@pytest.fixture
def engine() -> Iterator[Engine]:
    assert DATABASE_URL is not None
    database_engine = sa.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    _cleanup(database_engine)
    try:
        yield database_engine
    finally:
        _cleanup(database_engine)
        database_engine.dispose()


def _cleanup(engine: Engine) -> None:
    with engine.begin() as connection:
        for statement in (
            "DELETE FROM observation_evidence WHERE observation_id IN "
            "(SELECT observation_id FROM observations WHERE subject_id = :series_id)",
            "DELETE FROM observations WHERE subject_id = :series_id",
            "DELETE FROM evidence WHERE source_id = ANY(:source_ids)",
            "DELETE FROM sources WHERE source_id = ANY(:source_ids)",
            "DELETE FROM policy_rate_definitions WHERE market_series_id = :series_id",
            "DELETE FROM market_series WHERE market_series_id = :series_id",
            "DELETE FROM observation_subjects WHERE subject_id = :series_id",
        ):
            connection.execute(
                sa.text(statement), {"series_id": SERIES_ID, "source_ids": SOURCE_IDS}
            )


@pytest.mark.parametrize(
    "prior,current",
    [
        ("2.400", "2.5500"),
        (
            "123456789012345678901234567890123456789.01",
            "123456789012345678901234567890123456789.02",
        ),
    ],
)
def test_persisted_decimal_lineage_and_calculation_round_trip(engine, prior, current):
    dataset = _seed(engine, prior, current)
    expected = calculate_rate_change(dataset, REQUEST)
    stored_before = load_canonical_dataset(engine)
    result = calculate_rate_change_from_database(engine, REQUEST)
    assert result == expected
    assert result.status is RateChangeStatus.CALCULATED
    # Preserve any other valid canonical records already in the test database.
    assert load_canonical_dataset(engine) == stored_before
    for original, endpoint in zip(
        dataset.observations, (result.prior, result.current), strict=True
    ):
        retained = endpoint.lineage_observations[0]
        assert retained.value.as_tuple() == original.value.as_tuple()
        assert retained.evidence_ids == original.evidence_ids
        assert retained.verification_state is original.verification_state
        assert retained.verified_at == original.verified_at


def test_database_missing_and_conflicting_states_produce_explicit_block(engine):
    dataset = _batch(
        1,
        (
            (PRIOR, None, VerificationState.UNAVAILABLE),
            (CURRENT, "2.55", VerificationState.PRIMARY_VERIFIED),
            (CURRENT, "2.65", VerificationState.PENDING),
        ),
    )
    persist_canonical_dataset(engine, dataset)
    result = calculate_rate_change_from_database(engine, REQUEST)
    assert result == calculate_rate_change(dataset, REQUEST)
    assert result.value is None
    assert result.block_reasons == (
        RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,
        RateChangeBlockReason.PRIOR_SELECTION_BLOCKED,
    )
    assert (
        result.prior.lineage_observations[0].missing_state
        is MissingDataState.UNAVAILABLE
    )
    assert result.current.block_reasons == (SelectionBlockReason.CONFLICTING_VALUES,)


def _read_during(
    engine: Engine,
    action: Callable[[dict], None],
):
    """Pause a real reconstruction after a relation read, with bounded events.

    SQLAlchemy hooks coordinate timing only: no reader, SQL result, connection,
    transaction, writer, or analytical component is replaced or mocked.
    """

    paused, resume = Event(), Event()
    reader_ident = None
    details = {"transactions": 0}

    def begin(connection):
        if get_ident() == reader_ident:
            details["transactions"] += 1

    def after_execute(connection, cursor, statement, parameters, context, executemany):
        if get_ident() != reader_ident or paused.is_set():
            return
        if "FROM observation_evidence" not in statement:
            return
        details["isolation"] = connection.exec_driver_sql(
            "SHOW transaction_isolation"
        ).scalar_one()
        details["read_only"] = connection.exec_driver_sql(
            "SHOW transaction_read_only"
        ).scalar_one()
        details["pid"] = connection.exec_driver_sql(
            "SELECT pg_backend_pid()"
        ).scalar_one()
        paused.set()
        if not resume.wait(10):
            raise TimeoutError("Reader was not released after snapshot boundary.")

    def read():
        nonlocal reader_ident
        reader_ident = get_ident()
        return calculate_rate_change_from_database(engine, REQUEST)

    sa.event.listen(engine, "begin", begin)
    sa.event.listen(engine, "after_cursor_execute", after_execute)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(read)
            try:
                if not paused.wait(10):
                    if future.done():
                        future.result()  # Surface acquisition/reconstruction errors.
                    pytest.fail("Reader did not reach the evidence snapshot boundary.")
                assert details["isolation"] == "repeatable read"
                assert details["read_only"] == "on"
                action(details)
            finally:
                resume.set()
            result = future.result(timeout=15)
        assert details["transactions"] == 1
        return result
    finally:
        sa.event.remove(engine, "begin", begin)
        sa.event.remove(engine, "after_cursor_execute", after_execute)


@pytest.mark.parametrize("new_value", ["2.55000", "2.65"])
def test_concurrent_committed_append_cannot_tear_an_in_flight_snapshot(
    engine, new_value
):
    dataset = _seed(engine)
    before = calculate_rate_change(dataset, REQUEST)
    appended = _batch(2, ((CURRENT, new_value, VerificationState.PRIMARY_VERIFIED),))

    def append(details):
        assert (
            persist_market_observation_batch(engine, appended)
            is MarketObservationAppendStatus.INSERTED
        )
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                != details["pid"]
            )
            assert (
                connection.execute(
                    sa.text(
                        "SELECT count(*) FROM observations "
                        "WHERE subject_id = :series_id"
                    ),
                    {"series_id": SERIES_ID},
                ).scalar_one()
                == 3
            )

    during = _read_during(engine, append)
    assert during == before  # Old coherent graph, although append has committed.
    after = calculate_rate_change_from_database(engine, REQUEST)
    assert len(after.current.candidate_observation_ids) == 2
    if new_value == "2.55000":
        assert after.status is RateChangeStatus.CALCULATED
        assert after.value == before.value
        assert len(after.current.supporting_observation_ids) == 2
    else:
        assert after.block_reasons == (RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,)
        assert after.current.block_reasons == (SelectionBlockReason.CONFLICTING_VALUES,)
    assert during == before  # A later acquisition cannot rewrite the old result.


def test_real_connection_loss_fails_acquisition_then_new_invocation_can_recover(engine):
    dataset = _seed(engine)

    def disconnect(details):
        # Terminate only this test's paused reader backend; wait for termination
        # before releasing it. No timing sleeps or unrelated sessions are used.
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT pg_terminate_backend(:pid, 5000)"),
                {"pid": details["pid"]},
            ).scalar_one()

    with pytest.raises(DBAPIError):
        _read_during(engine, disconnect)
    assert calculate_rate_change_from_database(
        engine, REQUEST
    ) == calculate_rate_change(dataset, REQUEST)


def test_structurally_storable_but_invalid_unit_fails_reconstruction_validation(engine):
    dataset = _seed(engine)
    observation_id = dataset.observations[1].observation_id
    with engine.begin() as connection:
        # Deliberate synthetic corruption outside the canonical writer: the
        # schema permits this unit, but it is wrong for a policy-rate field.
        connection.execute(
            sa.text(
                "UPDATE observations SET unit = 'INDEX_POINTS' "
                "WHERE observation_id = :id"
            ),
            {"id": observation_id},
        )
    with pytest.raises(ValueError, match="unit"):
        calculate_rate_change_from_database(engine, REQUEST)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE observations SET unit = 'PERCENT' WHERE observation_id = :id"
            ),
            {"id": observation_id},
        )
    assert calculate_rate_change_from_database(
        engine, REQUEST
    ) == calculate_rate_change(dataset, REQUEST)
