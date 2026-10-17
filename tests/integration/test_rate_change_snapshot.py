"""Real PostgreSQL snapshot -> calculation/bundle -> offline replay seams."""

from __future__ import annotations

import hashlib
import os
import platform
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
from european_capital_markets.analytics.bundles import (
    BundleError,
    ExecutionIdentity,
    create_rate_change_bundle,
    encode_bundle,
    verify_bundle,
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
    create_rate_change_bundle_from_database,
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
        connect_args={
            "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c timezone=UTC"
        },
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
    *,
    acquire: Callable[[], object] | None = None,
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
        return (
            acquire()
            if acquire is not None
            else calculate_rate_change_from_database(engine, REQUEST)
        )

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


SOURCE_ARTIFACT = b"synthetic database-capture source artifact"
LOCK_ARTIFACT = b"synthetic database-capture dependency lock"


def _execution():
    return ExecutionIdentity(
        "a" * 40,
        hashlib.sha256(SOURCE_ARTIFACT).hexdigest(),
        hashlib.sha256(LOCK_ARTIFACT).hexdigest(),
        platform.python_implementation(),
        platform.python_version(),
        True,
    )


def _replay(content):
    return verify_bundle(
        content,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        execution=_execution(),
        source_artifact=SOURCE_ARTIFACT,
        lock_artifact=LOCK_ARTIFACT,
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
def test_database_bundle_retains_full_dataset_and_replays_after_transaction_close(
    engine, prior, current
):
    seeded = _seed(engine, prior, current)
    unrelated = _batch(3, ((date(2026, 10, 14), "2.25", VerificationState.PENDING),))
    persist_market_observation_batch(engine, unrelated)
    snapshot = load_canonical_dataset(engine)
    expected = create_rate_change_bundle(snapshot, REQUEST, _execution())
    connections = set()
    transactions = []

    def begin(connection):
        connections.add(connection)
        transactions.append(connection)

    def end(connection):
        connections.discard(connection)

    sa.event.listen(engine, "begin", begin)
    sa.event.listen(engine, "commit", end)
    sa.event.listen(engine, "rollback", end)
    try:
        captured = create_rate_change_bundle_from_database(
            engine, REQUEST, _execution()
        )
        assert len(transactions) == 1 and not connections
        content = encode_bundle(captured)
        assert content == encode_bundle(expected)
        # All source/evidence/observation records remain, even outside endpoints.
        assert unrelated.observations[0] in captured.dataset.observations
        assert unrelated.sources[0] in captured.dataset.sources
        for original, endpoint in zip(
            seeded.observations,
            (captured.result.prior, captured.result.current),
            strict=True,
        ):
            retained = endpoint.lineage_observations[0]
            assert retained.value.as_tuple() == original.value.as_tuple()
            assert retained.evidence_ids == original.evidence_ids
        assert _replay(content) == captured
        # Encoding and replay must not acquire another transaction.
        assert len(transactions) == 1 and not connections
    finally:
        sa.event.remove(engine, "begin", begin)
        sa.event.remove(engine, "commit", end)
        sa.event.remove(engine, "rollback", end)
    assert load_canonical_dataset(engine) == snapshot  # Capture made no writes.


@pytest.mark.parametrize("new_value", ["2.55000", "2.65"])
def test_database_bundle_snapshot_and_offline_replay_survive_later_append(
    engine, new_value
):
    _seed(engine)
    before = create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    before_bytes = encode_bundle(before)
    appended = _batch(2, ((CURRENT, new_value, VerificationState.PRIMARY_VERIFIED),))

    def append(details):
        assert persist_market_observation_batch(engine, appended) is (
            MarketObservationAppendStatus.INSERTED
        )
        with engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                != (details["pid"])
            )

    during = _read_during(
        engine,
        append,
        acquire=lambda: create_rate_change_bundle_from_database(
            engine, REQUEST, _execution()
        ),
    )
    assert encode_bundle(during) == before_bytes
    after = create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    assert len(after.result.current.candidate_observation_ids) == 2
    assert appended.observations[0] in after.dataset.observations
    assert appended.observations[0] not in during.dataset.observations
    assert len(after.result.current.supporting_observation_ids) == (
        2 if new_value == "2.55000" else 0
    )
    assert after.result.status is (
        RateChangeStatus.CALCULATED
        if new_value == "2.55000"
        else RateChangeStatus.BLOCKED
    )
    assert _replay(encode_bundle(after)) == after
    assert encode_bundle(_replay(before_bytes)) == before_bytes


def test_database_bundle_retains_missing_and_conflicting_diagnostics(engine):
    snapshot = _batch(
        1,
        (
            (PRIOR, None, VerificationState.UNAVAILABLE),
            (CURRENT, "2.55", VerificationState.PRIMARY_VERIFIED),
            (CURRENT, "2.65", VerificationState.PENDING),
        ),
    )
    persist_canonical_dataset(engine, snapshot)
    captured = create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    assert captured.result.block_reasons == (
        RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,
        RateChangeBlockReason.PRIOR_SELECTION_BLOCKED,
    )
    assert captured.result.prior.lineage_observations[0].missing_state is (
        MissingDataState.UNAVAILABLE
    )
    assert captured.result.current.block_reasons == (
        SelectionBlockReason.CONFLICTING_VALUES,
    )
    assert _replay(encode_bundle(captured)) == captured


def test_database_bundle_connection_loss_returns_no_bundle_then_explicit_call_recovers(
    engine,
):
    _seed(engine)
    before = create_rate_change_bundle_from_database(engine, REQUEST, _execution())

    def disconnect(details):
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT pg_terminate_backend(:pid, 5000)"),
                {"pid": details["pid"]},
            ).scalar_one()

    with pytest.raises(DBAPIError):
        _read_during(
            engine,
            disconnect,
            acquire=lambda: create_rate_change_bundle_from_database(
                engine, REQUEST, _execution()
            ),
        )
    after = create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    assert encode_bundle(after) == encode_bundle(before)


def test_database_bundle_codec_failure_leaves_database_unchanged(engine):
    _seed(engine)
    # Valid canonical source metadata exceeding the separately governed wire limit.
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE sources SET notes = :notes WHERE source_id = :id"),
            {"notes": "x" * 262145, "id": SOURCE_IDS[0]},
        )
    snapshot = load_canonical_dataset(engine)
    with pytest.raises(BundleError, match="oversized string"):
        create_rate_change_bundle_from_database(engine, REQUEST, _execution())
    assert load_canonical_dataset(engine) == snapshot
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE sources SET notes = NULL WHERE source_id = :id"),
            {"id": SOURCE_IDS[0]},
        )
    assert (
        _replay(
            encode_bundle(
                create_rate_change_bundle_from_database(engine, REQUEST, _execution())
            )
        ).result.status
        is RateChangeStatus.CALCULATED
    )


def test_database_bundle_rejects_named_zone_without_changing_existing_calculation(
    engine,
):
    _seed(engine)
    zoned_engine = sa.create_engine(
        DATABASE_URL,
        connect_args={
            "options": (
                "-c timezone=Europe/Paris -c statement_timeout=10000 "
                "-c lock_timeout=5000"
            )
        },
    )
    try:
        assert calculate_rate_change_from_database(zoned_engine, REQUEST).status is (
            RateChangeStatus.CALCULATED
        )
        with pytest.raises(BundleError, match="fixed-offset"):
            create_rate_change_bundle_from_database(zoned_engine, REQUEST, _execution())
    finally:
        zoned_engine.dispose()
    # A later explicit acquisition using a supported session still succeeds.
    assert (
        _replay(
            encode_bundle(
                create_rate_change_bundle_from_database(engine, REQUEST, _execution())
            )
        ).result.status
        is RateChangeStatus.CALCULATED
    )
