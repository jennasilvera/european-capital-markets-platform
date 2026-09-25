"""Tests for durable checkpoint-driven ECB DFR orchestration."""

from types import SimpleNamespace
from uuid import UUID

import pytest

import european_capital_markets.ingestion.orchestration as orchestration
from european_capital_markets.persistence.ingestion_runs import (
    IngestionRunConflictError,
)

_RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
_INITIAL_TOKEN = UUID("22222222-2222-2222-2222-222222222222")
_RETAINED_TOKEN = UUID("33333333-3333-3333-3333-333333333333")
_SERIES_ID = "MKS000000001"
_PROVIDER_ID = "FM.D.U2.EUR.4F.KR.DFR.LEV"


def _catalog_entry():
    return SimpleNamespace(
        market_series=SimpleNamespace(
            market_series_id=_SERIES_ID,
        ),
    )


def _artifact(
    provider_series_id: str = _PROVIDER_ID,
):
    return SimpleNamespace(
        source=SimpleNamespace(
            retrieval_identifier=provider_series_id,
        ),
    )


def _run(checkpoint, *, artifact=None, storage_token=None):
    return SimpleNamespace(
        run_id=_RUN_ID,
        market_series_id=_SERIES_ID,
        checkpoint=checkpoint,
        raw_artifact=artifact,
        storage_token=storage_token,
    )


class _RawStore:
    def __init__(self, calls, *, content=b"retained raw bytes"):
        self.calls = calls
        self.content = content

    def load_verified_content(self, artifact, *, storage_token):
        self.calls.append(("reload", artifact, storage_token))
        return self.content


def _install_catalog_validation(monkeypatch, calls):
    def validate(catalog_entry):
        calls.append(("validate", catalog_entry))
        return _PROVIDER_ID

    monkeypatch.setattr(
        orchestration,
        "validate_ecb_dfr_catalog_entry",
        validate,
    )


def test_durable_started_records_raw_before_normalizing(monkeypatch) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    raw_store = _RawStore(calls)
    engine = object()
    client = object()
    artifact = _artifact()
    raw_landing = SimpleNamespace(
        artifact=artifact,
        storage_token=_INITIAL_TOKEN,
    )

    started = _run(orchestration.IngestionRunCheckpoint.STARTED)
    raw_landed = _run(
        orchestration.IngestionRunCheckpoint.RAW_LANDED,
        artifact=artifact,
        storage_token=_INITIAL_TOKEN,
    )
    persisted = _run(
        orchestration.IngestionRunCheckpoint.PERSISTED,
        artifact=artifact,
        storage_token=_INITIAL_TOKEN,
    )

    datums = (object(), object())
    allocated_ids = (object(), object())
    dataset = object()
    handoff = SimpleNamespace(dataset=dataset)

    _install_catalog_validation(monkeypatch, calls)

    def create(actual_engine, *, run_id, market_series_id):
        calls.append(("create", actual_engine, run_id, market_series_id))
        return started

    def retrieve_land(
        actual_client,
        actual_catalog_entry,
        actual_raw_store,
        *,
        provider_series_id,
        last_n_observations,
        storage_token,
    ):
        calls.append(
            (
                "retrieve_land",
                actual_client,
                actual_catalog_entry,
                actual_raw_store,
                provider_series_id,
                last_n_observations,
                storage_token,
            )
        )
        return object(), raw_landing

    def record(actual_engine, *, run_id, raw_landing):
        calls.append(("record_raw", actual_engine, run_id, raw_landing))
        return raw_landed

    def parse(content, *, market_series_id, expected_provider_series_id):
        calls.append(
            (
                "parse",
                content,
                market_series_id,
                expected_provider_series_id,
            )
        )
        return datums

    def allocate(actual_engine, *, run_id, datums):
        calls.append(("allocate_or_replay", actual_engine, run_id, datums))
        return allocated_ids

    def build_handoff(
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

    def persist(actual_engine, actual_dataset):
        calls.append(("persist", actual_engine, actual_dataset))
        return orchestration.MarketObservationAppendStatus.INSERTED

    def mark(actual_engine, *, run_id):
        calls.append(("mark_persisted", actual_engine, run_id))
        return persisted

    monkeypatch.setattr(orchestration, "create_market_ingestion_run", create)
    monkeypatch.setattr(orchestration, "_retrieve_land_ecb_dfr", retrieve_land)
    monkeypatch.setattr(
        orchestration,
        "record_market_ingestion_raw_landing",
        record,
    )
    monkeypatch.setattr(orchestration, "parse_ecb_dfr_csv", parse)
    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        allocate,
    )
    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        build_handoff,
    )
    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        persist,
    )
    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        mark,
    )

    result = orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
        client,
        catalog_entry,
        raw_store,
        engine,
        run_id=_RUN_ID,
        last_n_observations=5,
        storage_token=_INITIAL_TOKEN,
    )

    assert [call[0] for call in calls] == [
        "create",
        "validate",
        "retrieve_land",
        "record_raw",
        "reload",
        "parse",
        "allocate_or_replay",
        "handoff",
        "persist",
        "mark_persisted",
    ]
    assert result.run is persisted
    assert (
        result.persistence_status
        is orchestration.MarketObservationAppendStatus.INSERTED
    )


def test_durable_raw_landed_recovery_never_retrieves(monkeypatch) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    engine = object()
    artifact = _artifact()
    raw_landed = _run(
        orchestration.IngestionRunCheckpoint.RAW_LANDED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )
    persisted = _run(
        orchestration.IngestionRunCheckpoint.PERSISTED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )
    raw_store = _RawStore(calls)

    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: raw_landed,
    )

    def forbidden_validation(*_args, **_kwargs):
        raise AssertionError(
            "RAW_LANDED recovery must use retained provider provenance."
        )

    monkeypatch.setattr(
        orchestration,
        "validate_ecb_dfr_catalog_entry",
        forbidden_validation,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "RAW_LANDED recovery must not retrieve or record raw bytes."
        )

    monkeypatch.setattr(orchestration, "_retrieve_land_ecb_dfr", forbidden)
    monkeypatch.setattr(
        orchestration,
        "record_market_ingestion_raw_landing",
        forbidden,
    )
    def parse_retained(
        _content,
        *,
        market_series_id,
        expected_provider_series_id,
    ):
        assert market_series_id == _SERIES_ID
        assert expected_provider_series_id == _PROVIDER_ID

        return (object(),)

    monkeypatch.setattr(
        orchestration,
        "parse_ecb_dfr_csv",
        parse_retained,
    )
    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        lambda *_args, **_kwargs: SimpleNamespace(dataset=object()),
    )
    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        lambda *_args, **_kwargs: (
            orchestration.MarketObservationAppendStatus.INSERTED
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        lambda *_args, **_kwargs: persisted,
    )

    result = orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
        object(),
        catalog_entry,
        raw_store,
        engine,
        run_id=_RUN_ID,
        last_n_observations=99,
        storage_token=_INITIAL_TOKEN,
    )

    assert ("reload", artifact, _RETAINED_TOKEN) in calls
    assert result.run is persisted


def test_durable_lineage_allocated_replay_accepts_already_persisted(
    monkeypatch,
) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    engine = object()
    artifact = _artifact()
    allocated = _run(
        orchestration.IngestionRunCheckpoint.LINEAGE_ALLOCATED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )
    persisted = _run(
        orchestration.IngestionRunCheckpoint.PERSISTED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )
    raw_store = _RawStore(calls)
    datums = (object(),)
    retained_ids = (object(),)

    _install_catalog_validation(monkeypatch, calls)
    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: allocated,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "LINEAGE_ALLOCATED recovery must not retrieve or reland raw bytes."
        )

    monkeypatch.setattr(orchestration, "_retrieve_land_ecb_dfr", forbidden)
    monkeypatch.setattr(
        orchestration,
        "record_market_ingestion_raw_landing",
        forbidden,
    )
    monkeypatch.setattr(
        orchestration,
        "parse_ecb_dfr_csv",
        lambda *_args, **_kwargs: datums,
    )

    def replay(actual_engine, *, run_id, datums):
        calls.append(("allocation_replay", actual_engine, run_id, datums))
        return retained_ids

    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        replay,
    )
    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        lambda *_args, **_kwargs: SimpleNamespace(dataset=object()),
    )

    def persist(*_args, **_kwargs):
        calls.append(("persist",))
        return orchestration.MarketObservationAppendStatus.ALREADY_PERSISTED

    def mark(*_args, **_kwargs):
        calls.append(("mark",))
        return persisted

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        persist,
    )
    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        mark,
    )

    result = orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
        object(),
        catalog_entry,
        raw_store,
        engine,
        run_id=_RUN_ID,
    )

    assert ("allocation_replay", engine, _RUN_ID, datums) in calls
    assert calls.index(("persist",)) < calls.index(("mark",))
    assert (
        result.persistence_status
        is orchestration.MarketObservationAppendStatus.ALREADY_PERSISTED
    )
    assert result.run is persisted


def test_durable_persisted_run_is_terminal_noop(monkeypatch) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    artifact = _artifact()
    persisted = _run(
        orchestration.IngestionRunCheckpoint.PERSISTED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )

    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: persisted,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "PERSISTED replay must not execute downstream work."
        )

    for name in (
        "validate_ecb_dfr_catalog_entry",
        "_retrieve_land_ecb_dfr",
        "record_market_ingestion_raw_landing",
        "parse_ecb_dfr_csv",
        "allocate_market_ingestion_run_lineage",
        "build_canonical_market_ingestion_handoff",
        "persist_market_observation_batch",
        "mark_market_ingestion_run_persisted",
    ):
        monkeypatch.setattr(orchestration, name, forbidden)

    result = orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
        object(),
        catalog_entry,
        _RawStore(calls),
        object(),
        run_id=_RUN_ID,
    )

    assert result.run is persisted
    assert result.persistence_status is None


def test_durable_parser_failure_occurs_after_raw_checkpoint(monkeypatch) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    artifact = _artifact()
    started = _run(orchestration.IngestionRunCheckpoint.STARTED)
    raw_landed = _run(
        orchestration.IngestionRunCheckpoint.RAW_LANDED,
        artifact=artifact,
        storage_token=_INITIAL_TOKEN,
    )

    _install_catalog_validation(monkeypatch, calls)
    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: started,
    )
    raw_landing = SimpleNamespace(
        artifact=artifact,
        storage_token=_INITIAL_TOKEN,
    )
    monkeypatch.setattr(
        orchestration,
        "_retrieve_land_ecb_dfr",
        lambda *_args, **_kwargs: (object(), raw_landing),
    )

    def record(*_args, **_kwargs):
        calls.append(("record_raw",))
        return raw_landed

    monkeypatch.setattr(
        orchestration,
        "record_market_ingestion_raw_landing",
        record,
    )
    raw_store = _RawStore(calls)

    def fail_parse(*_args, **_kwargs):
        calls.append(("parse",))
        raise ValueError("normalization failed")

    monkeypatch.setattr(orchestration, "parse_ecb_dfr_csv", fail_parse)

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "downstream work must not run after parser failure."
        )

    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        forbidden,
    )
    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        forbidden,
    )
    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        forbidden,
    )

    with pytest.raises(ValueError, match="normalization failed"):
        orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
            object(),
            catalog_entry,
            raw_store,
            object(),
            run_id=_RUN_ID,
            storage_token=_INITIAL_TOKEN,
        )

    assert calls.index(("record_raw",)) < calls.index(("parse",))


def test_durable_normalized_replay_conflict_stops_before_persistence(
    monkeypatch,
) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    artifact = _artifact()
    allocated = _run(
        orchestration.IngestionRunCheckpoint.LINEAGE_ALLOCATED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )

    _install_catalog_validation(monkeypatch, calls)
    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: allocated,
    )
    monkeypatch.setattr(
        orchestration,
        "parse_ecb_dfr_csv",
        lambda *_args, **_kwargs: (object(),),
    )

    def conflict(*_args, **_kwargs):
        raise IngestionRunConflictError("normalized replay conflict")

    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        conflict,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "conflicting replay must stop before canonical persistence."
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
    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        forbidden,
    )

    with pytest.raises(
        IngestionRunConflictError,
        match="normalized replay conflict",
    ):
        orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
            object(),
            catalog_entry,
            _RawStore(calls),
            object(),
            run_id=_RUN_ID,
        )


def test_durable_persistence_failure_does_not_mark_persisted(
    monkeypatch,
) -> None:
    calls = []
    catalog_entry = _catalog_entry()
    artifact = _artifact()
    allocated = _run(
        orchestration.IngestionRunCheckpoint.LINEAGE_ALLOCATED,
        artifact=artifact,
        storage_token=_RETAINED_TOKEN,
    )

    _install_catalog_validation(monkeypatch, calls)
    monkeypatch.setattr(
        orchestration,
        "create_market_ingestion_run",
        lambda *_args, **_kwargs: allocated,
    )
    monkeypatch.setattr(
        orchestration,
        "parse_ecb_dfr_csv",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setattr(
        orchestration,
        "allocate_market_ingestion_run_lineage",
        lambda *_args, **_kwargs: (object(),),
    )
    monkeypatch.setattr(
        orchestration,
        "build_canonical_market_ingestion_handoff",
        lambda *_args, **_kwargs: SimpleNamespace(dataset=object()),
    )

    def fail_persist(*_args, **_kwargs):
        raise RuntimeError("canonical persistence failed")

    monkeypatch.setattr(
        orchestration,
        "persist_market_observation_batch",
        fail_persist,
    )

    def forbidden_mark(*_args, **_kwargs):
        raise AssertionError(
            "run must not be marked PERSISTED after writer failure."
        )

    monkeypatch.setattr(
        orchestration,
        "mark_market_ingestion_run_persisted",
        forbidden_mark,
    )

    with pytest.raises(RuntimeError, match="canonical persistence failed"):
        orchestration.ingest_ecb_dfr_to_durable_canonical_persistence(
            object(),
            catalog_entry,
            _RawStore(calls),
            object(),
            run_id=_RUN_ID,
        )
