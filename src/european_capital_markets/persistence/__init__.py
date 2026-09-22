"""Canonical PostgreSQL persistence adapters."""

from european_capital_markets.persistence.id_allocation import (
    allocate_market_lineage_ids,
)
from european_capital_markets.persistence.ingestion_runs import (
    IngestionRunConflictError,
    IngestionRunStateError,
    allocate_market_ingestion_run_lineage,
    create_market_ingestion_run,
    load_market_ingestion_run,
    mark_market_ingestion_run_persisted,
    record_market_ingestion_raw_landing,
)
from european_capital_markets.persistence.reader import load_canonical_dataset
from european_capital_markets.persistence.repository import CanonicalRepository
from european_capital_markets.persistence.writer import (
    MarketObservationAppendConflictError,
    MarketObservationAppendStatus,
    persist_canonical_dataset,
    persist_market_observation_batch,
)

__all__ = [
    "CanonicalRepository",
    "IngestionRunConflictError",
    "IngestionRunStateError",
    "MarketObservationAppendConflictError",
    "MarketObservationAppendStatus",
    "allocate_market_ingestion_run_lineage",
    "allocate_market_lineage_ids",
    "create_market_ingestion_run",
    "load_canonical_dataset",
    "load_market_ingestion_run",
    "mark_market_ingestion_run_persisted",
    "persist_canonical_dataset",
    "persist_market_observation_batch",
    "record_market_ingestion_raw_landing",
]
