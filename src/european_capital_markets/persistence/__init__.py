"""Canonical PostgreSQL persistence adapters."""

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
    "load_canonical_dataset",
    "persist_canonical_dataset",
    "persist_market_observation_batch",
]
