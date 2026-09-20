"""Controlled ingestion orchestration boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from european_capital_markets.ingestion.contracts import (
    NormalizedMarketDatum,
    RetrievalSource,
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
