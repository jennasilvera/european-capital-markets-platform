"""Canonical PostgreSQL persistence adapters."""

from european_capital_markets.persistence.id_allocation import (
    allocate_market_lineage_ids,
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
    "MarketObservationAppendConflictError",
    "MarketObservationAppendStatus",
    "allocate_market_lineage_ids",
    "load_canonical_dataset",
    "persist_canonical_dataset",
    "persist_market_observation_batch",
]
