"""Controlled ingestion orchestration boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

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
from european_capital_markets.ingestion.transport import (
    HttpRetrievedPayload,
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

    provider_series_id = (
        validate_ecb_dfr_catalog_entry(
            catalog_entry
        )
    )

    retrieval = fetch_ecb_csv(
        client,
        provider_series_id,
        last_n_observations=(
            last_n_observations
        ),
    )

    source_mapping = (
        catalog_entry.source_mapping
    )

    redirect_note = None

    if (
        retrieval.request_url
        != retrieval.response_url
    ):
        redirect_note = (
            "Requested URL before redirects: "
            f"{retrieval.request_url}"
        )

    source = RetrievalSource(
        publisher=(
            source_mapping.publisher
        ),
        source_tier=(
            source_mapping.source_tier
        ),
        source_type=(
            source_mapping.source_type
        ),
        title=(
            "ECB Data Portal: "
            f"{catalog_entry.definition.rate_name}"
        ),
        url=retrieval.response_url,
        retrieval_identifier=(
            provider_series_id
        ),
        notes=redirect_note,
    )

    raw_landing = (
        raw_store.land_http_retrieval(
            market_series_id=(
                catalog_entry.market_series.market_series_id
            ),
            source=source,
            retrieval=retrieval,
            namespace="ecb",
            suffix=".csv",
            storage_token=storage_token,
        )
    )

    # Do not move this parse step above raw landing. The raw artifact is the
    # evidence-preserving boundary for parser or normalization failures.
    datums = parse_ecb_dfr_csv(
        retrieval.content,
        market_series_id=(
            catalog_entry.market_series.market_series_id
        ),
        expected_provider_series_id=(
            provider_series_id
        ),
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

    This function intentionally does not persist the returned dataset. The
    current canonical writer is insert-oriented; recurring observation
    ingestion needs separately reviewed append/idempotency semantics before
    production persistence orchestration is safe.
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
