"""Controlled ingestion orchestration boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy import Engine

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
)
from european_capital_markets.ingestion.contracts import (
    AllocatedLineageIds,
    MarketLineageRecords,
    NormalizedMarketDatum,
    RawRetrievalArtifact,
    RetrievalSource,
    build_pending_market_lineage,
)
from european_capital_markets.ingestion.providers.ecb import (
    fetch_ecb_csv,
    parse_ecb_dfr_csv,
    validate_ecb_dfr_catalog_entry,
)
from european_capital_markets.ingestion.raw_storage import (
    ImmutableRawArtifactStore,
    RawArtifactLanding,
)
from european_capital_markets.ingestion.run_state import (
    IngestionRunCheckpoint,
    MarketIngestionRun,
)
from european_capital_markets.ingestion.transport import (
    HttpRetrievedPayload,
)
from european_capital_markets.persistence.id_allocation import (
    allocate_market_lineage_ids,
)
from european_capital_markets.persistence.ingestion_runs import (
    allocate_market_ingestion_run_lineage,
    create_market_ingestion_run,
    mark_market_ingestion_run_persisted,
    record_market_ingestion_raw_landing,
)
from european_capital_markets.persistence.writer import (
    MarketObservationAppendStatus,
    persist_market_observation_batch,
)
from european_capital_markets.reference_data.market_series_catalog import (
    MarketSeriesCatalogEntry,
)


@dataclass(frozen=True, slots=True)
class EcbDfrRawIngestionResult:
    """Retrieved, durably landed, and normalized ECB DFR data."""

    retrieval: HttpRetrievedPayload
    raw_landing: RawArtifactLanding
    datums: tuple[NormalizedMarketDatum, ...]


def _retrieve_land_ecb_dfr(
    client: httpx.Client,
    catalog_entry: MarketSeriesCatalogEntry,
    raw_store: ImmutableRawArtifactStore,
    *,
    provider_series_id: str,
    last_n_observations: int,
    storage_token: UUID | None,
) -> tuple[HttpRetrievedPayload, RawArtifactLanding]:
    """Retrieve and durably land ECB DFR bytes without normalizing them."""

    retrieval = fetch_ecb_csv(
        client,
        provider_series_id,
        last_n_observations=last_n_observations,
    )

    source_mapping = catalog_entry.source_mapping
    redirect_note = None

    if retrieval.request_url != retrieval.response_url:
        redirect_note = (
            "Requested URL before redirects: "
            f"{retrieval.request_url}"
        )

    source = RetrievalSource(
        publisher=source_mapping.publisher,
        source_tier=source_mapping.source_tier,
        source_type=source_mapping.source_type,
        title=(
            "ECB Data Portal: "
            f"{catalog_entry.definition.rate_name}"
        ),
        url=retrieval.response_url,
        retrieval_identifier=provider_series_id,
        notes=redirect_note,
    )

    raw_landing = raw_store.land_http_retrieval(
        market_series_id=(
            catalog_entry.market_series.market_series_id
        ),
        source=source,
        retrieval=retrieval,
        namespace="ecb",
        suffix=".csv",
        storage_token=storage_token,
    )

    return retrieval, raw_landing


def retrieve_land_normalize_ecb_dfr(
    client: httpx.Client,
    catalog_entry: MarketSeriesCatalogEntry,
    raw_store: ImmutableRawArtifactStore,
    *,
    last_n_observations: int = 3,
    storage_token: UUID | None = None,
) -> EcbDfrRawIngestionResult:
    """Retrieve ECB DFR data, land raw bytes, then normalize them.

    Raw publication intentionally precedes parsing. A normalization failure
    therefore does not destroy or hide the exact provider bytes that caused
    the failure.
    """

    provider_series_id = validate_ecb_dfr_catalog_entry(
        catalog_entry
    )

    retrieval, raw_landing = _retrieve_land_ecb_dfr(
        client,
        catalog_entry,
        raw_store,
        provider_series_id=provider_series_id,
        last_n_observations=last_n_observations,
        storage_token=storage_token,
    )

    # Do not move this parse step above raw landing. The raw artifact is the
    # evidence-preserving boundary for parser or normalization failures.
    datums = parse_ecb_dfr_csv(
        retrieval.content,
        market_series_id=(
            catalog_entry.market_series.market_series_id
        ),
        expected_provider_series_id=provider_series_id,
    )

    return EcbDfrRawIngestionResult(
        retrieval=retrieval,
        raw_landing=raw_landing,
        datums=datums,
    )


@dataclass(frozen=True, slots=True)
class CanonicalMarketIngestionHandoff:
    """Validated canonical representation of one raw retrieval."""

    dataset: CanonicalDataset
    lineage: tuple[MarketLineageRecords, ...]


def _market_definition_buckets(
    catalog_entry: MarketSeriesCatalogEntry,
) -> dict[str, tuple[object, ...]]:
    """Place one controlled definition in its canonical dataset bucket."""

    definition = catalog_entry.definition

    buckets: dict[str, tuple[object, ...]] = {
        "fx_reference_rates": (),
        "policy_rates": (),
        "government_yields": (),
        "swap_rates": (),
        "credit_spreads": (),
        "equity_indices": (),
        "volatility_indices": (),
    }

    if isinstance(
        definition,
        FXReferenceRateDefinitionRecord,
    ):
        buckets["fx_reference_rates"] = (
            definition,
        )
    elif isinstance(
        definition,
        PolicyRateDefinitionRecord,
    ):
        buckets["policy_rates"] = (
            definition,
        )
    elif isinstance(
        definition,
        GovernmentYieldDefinitionRecord,
    ):
        buckets["government_yields"] = (
            definition,
        )
    elif isinstance(
        definition,
        SwapRateDefinitionRecord,
    ):
        buckets["swap_rates"] = (
            definition,
        )
    elif isinstance(
        definition,
        CreditSpreadDefinitionRecord,
    ):
        buckets["credit_spreads"] = (
            definition,
        )
    elif isinstance(
        definition,
        EquityIndexDefinitionRecord,
    ):
        buckets["equity_indices"] = (
            definition,
        )
    elif isinstance(
        definition,
        VolatilityIndexDefinitionRecord,
    ):
        buckets["volatility_indices"] = (
            definition,
        )
    else:
        raise TypeError(
            "Unsupported market-series definition type: "
            f"{type(definition).__name__}."
        )

    return buckets


def build_canonical_market_ingestion_handoff(
    catalog_entry: MarketSeriesCatalogEntry,
    artifact: RawRetrievalArtifact,
    datums: tuple[NormalizedMarketDatum, ...],
    allocated_ids: tuple[AllocatedLineageIds, ...],
) -> CanonicalMarketIngestionHandoff:
    """Build and validate one canonical handoff from a landed retrieval.

    Identifier allocation remains external. One raw retrieval maps to exactly
    one canonical source record, while each normalized datum receives its own
    evidence and observation identifiers.

    This function intentionally does not persist the returned dataset.
    Step 13G composes this validated handoff with the reviewed lineage
    allocator and append writer without changing either boundary's semantics.
    """

    if not datums:
        raise ValueError(
            "Canonical market-ingestion handoff requires "
            "at least one normalized datum."
        )

    if len(datums) != len(
        allocated_ids
    ):
        raise ValueError(
            "allocated_ids must contain exactly one lineage-ID "
            "bundle per normalized datum."
        )

    source_ids = {
        ids.source_id
        for ids in allocated_ids
    }

    if len(source_ids) != 1:
        raise ValueError(
            "All normalized datums from one raw retrieval must "
            "share one externally allocated source_id."
        )

    lineage = tuple(
        build_pending_market_lineage(
            catalog_entry,
            artifact,
            datum,
            ids,
        )
        for datum, ids in zip(
            datums,
            allocated_ids,
            strict=True,
        )
    )

    source = lineage[0].source

    if any(
        records.source != source
        for records in lineage[1:]
    ):
        raise ValueError(
            "One raw retrieval produced inconsistent canonical "
            "source records."
        )

    definition_buckets = (
        _market_definition_buckets(
            catalog_entry
        )
    )

    dataset = CanonicalDataset(
        issuers=(),
        transactions=(),
        instruments=(),
        issuer_identifiers=(),
        parties=(),
        participations=(),
        lifecycle_events=(),
        market_series=(
            catalog_entry.market_series,
        ),
        fx_reference_rates=(
            definition_buckets[
                "fx_reference_rates"
            ]
        ),
        policy_rates=(
            definition_buckets[
                "policy_rates"
            ]
        ),
        government_yields=(
            definition_buckets[
                "government_yields"
            ]
        ),
        swap_rates=(
            definition_buckets[
                "swap_rates"
            ]
        ),
        credit_spreads=(
            definition_buckets[
                "credit_spreads"
            ]
        ),
        equity_indices=(
            definition_buckets[
                "equity_indices"
            ]
        ),
        volatility_indices=(
            definition_buckets[
                "volatility_indices"
            ]
        ),
        sources=(
            source,
        ),
        evidence=tuple(
            records.evidence
            for records in lineage
        ),
        observations=tuple(
            records.observation
            for records in lineage
        ),
    )

    validate_canonical_dataset(
        dataset
    )

    return CanonicalMarketIngestionHandoff(
        dataset=dataset,
        lineage=lineage,
    )

@dataclass(frozen=True, slots=True)
class EcbDfrCanonicalPersistenceResult:
    """Successful ECB DFR ingestion through canonical append persistence."""

    raw_ingestion: EcbDfrRawIngestionResult
    allocated_ids: tuple[AllocatedLineageIds, ...]
    handoff: CanonicalMarketIngestionHandoff
    persistence_status: MarketObservationAppendStatus


def ingest_ecb_dfr_to_canonical_persistence(
    client: httpx.Client,
    catalog_entry: MarketSeriesCatalogEntry,
    raw_store: ImmutableRawArtifactStore,
    engine: Engine,
    *,
    last_n_observations: int = 3,
    storage_token: UUID | None = None,
) -> EcbDfrCanonicalPersistenceResult:
    """Run the reviewed ECB DFR ingestion boundaries in canonical order.

    This function is deliberately a composition layer only:

    retrieve -> immutable raw landing -> normalize -> allocate lineage IDs
    -> canonical handoff -> controlled append persistence

    It does not introduce a transaction spanning those boundaries and does
    not retry failed work. Sequence values consumed before a later failure
    remain consumed under the Step 13F allocation contract.
    """

    raw_ingestion = retrieve_land_normalize_ecb_dfr(
        client,
        catalog_entry,
        raw_store,
        last_n_observations=last_n_observations,
        storage_token=storage_token,
    )

    allocated_ids = allocate_market_lineage_ids(
        engine,
        len(raw_ingestion.datums),
    )

    handoff = build_canonical_market_ingestion_handoff(
        catalog_entry,
        raw_ingestion.raw_landing.artifact,
        raw_ingestion.datums,
        allocated_ids,
    )

    persistence_status = persist_market_observation_batch(
        engine,
        handoff.dataset,
    )

    return EcbDfrCanonicalPersistenceResult(
        raw_ingestion=raw_ingestion,
        allocated_ids=allocated_ids,
        handoff=handoff,
        persistence_status=persistence_status,
    )


@dataclass(frozen=True, slots=True)
class DurableEcbDfrCanonicalPersistenceResult:
    """Outcome of one durable same-logical-attempt ECB DFR ingestion."""

    run: MarketIngestionRun
    persistence_status: MarketObservationAppendStatus | None


def ingest_ecb_dfr_to_durable_canonical_persistence(
    client: httpx.Client,
    catalog_entry: MarketSeriesCatalogEntry,
    raw_store: ImmutableRawArtifactStore,
    engine: Engine,
    *,
    run_id: UUID,
    last_n_observations: int = 3,
    storage_token: UUID | None = None,
) -> DurableEcbDfrCanonicalPersistenceResult:
    """Execute or recover one durable ECB DFR ingestion run.

    STARTED is the only checkpoint that may retrieve provider bytes.
    RAW_LANDED and LINEAGE_ALLOCATED always reload and verify the retained
    immutable raw artifact. Lineage allocation is durable and replay-safe:
    a LINEAGE_ALLOCATED recovery recomputes the normalized batch fingerprint
    and reuses the retained SRC/EVD/OBS identifiers only on an exact match.

    Canonical persistence completes before the run is marked PERSISTED.
    Therefore a crash after canonical commit but before the checkpoint update
    safely replays the same canonical IDs and accepts ALREADY_PERSISTED.

    last_n_observations and storage_token affect only an initial STARTED
    retrieval. Recovery uses the retained raw artifact and storage token.
    """

    market_series_id = (
        catalog_entry.market_series.market_series_id
    )

    run = create_market_ingestion_run(
        engine,
        run_id=run_id,
        market_series_id=market_series_id,
    )

    if run.checkpoint is IngestionRunCheckpoint.PERSISTED:
        return DurableEcbDfrCanonicalPersistenceResult(
            run=run,
            persistence_status=None,
        )

    if run.checkpoint is IngestionRunCheckpoint.STARTED:
        provider_series_id = validate_ecb_dfr_catalog_entry(
            catalog_entry
        )

        _retrieval, raw_landing = _retrieve_land_ecb_dfr(
            client,
            catalog_entry,
            raw_store,
            provider_series_id=provider_series_id,
            last_n_observations=last_n_observations,
            storage_token=storage_token,
        )

        run = record_market_ingestion_raw_landing(
            engine,
            run_id=run_id,
            raw_landing=raw_landing,
        )

    if run.checkpoint not in {
        IngestionRunCheckpoint.RAW_LANDED,
        IngestionRunCheckpoint.LINEAGE_ALLOCATED,
    }:
        raise AssertionError(
            "Durable ECB DFR ingestion reached an unsupported "
            f"checkpoint: {run.checkpoint.value}."
        )

    if run.raw_artifact is None or run.storage_token is None:
        raise AssertionError(
            "Recoverable ingestion checkpoint is missing retained "
            "raw-artifact state."
        )

    provider_series_id = (
        run.raw_artifact.source.retrieval_identifier
    )

    if not provider_series_id:
        raise ValueError(
            "Retained ECB raw artifact is missing its "
            "provider retrieval identifier."
        )

    raw_content = raw_store.load_verified_content(
        run.raw_artifact,
        storage_token=run.storage_token,
    )

    datums = parse_ecb_dfr_csv(
        raw_content,
        market_series_id=market_series_id,
        expected_provider_series_id=provider_series_id,
    )

    allocated_ids = allocate_market_ingestion_run_lineage(
        engine,
        run_id=run_id,
        datums=datums,
    )

    handoff = build_canonical_market_ingestion_handoff(
        catalog_entry,
        run.raw_artifact,
        datums,
        allocated_ids,
    )

    persistence_status = persist_market_observation_batch(
        engine,
        handoff.dataset,
    )

    persisted_run = mark_market_ingestion_run_persisted(
        engine,
        run_id=run_id,
    )

    return DurableEcbDfrCanonicalPersistenceResult(
        run=persisted_run,
        persistence_status=persistence_status,
    )
