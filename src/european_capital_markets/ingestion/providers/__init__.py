"""Controlled provider-specific ingestion adapters."""

from european_capital_markets.ingestion.providers.ecb import (
    ECB_DATA_API_BASE_URL,
    EcbDfrFetchResult,
    build_ecb_data_url,
    create_ecb_client,
    fetch_ecb_csv,
    fetch_ecb_dfr,
    parse_ecb_dfr_csv,
    validate_ecb_dfr_catalog_entry,
)

__all__ = [
    "ECB_DATA_API_BASE_URL",
    "EcbDfrFetchResult",
    "build_ecb_data_url",
    "create_ecb_client",
    "fetch_ecb_csv",
    "fetch_ecb_dfr",
    "parse_ecb_dfr_csv",
    "validate_ecb_dfr_catalog_entry",
]
