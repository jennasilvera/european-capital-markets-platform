"""Read-only composition of canonical PostgreSQL snapshots and pure analytics."""

from sqlalchemy import Engine

from european_capital_markets.analytics.bundles import (
    ExecutionIdentity,
    RateChangeBundle,
    create_rate_change_bundle,
)
from european_capital_markets.analytics.rate_changes import (
    RateChangeRequest,
    RateChangeResult,
    calculate_rate_change,
)
from european_capital_markets.persistence.reader import load_canonical_dataset


def calculate_rate_change_from_database(
    engine: Engine,
    request: RateChangeRequest,
) -> RateChangeResult:
    """Load one coherent canonical snapshot, then calculate without further I/O.

    The existing reader owns the read-only repeatable-read transaction and
    complete reconstruction/validation. Its transaction closes before the pure
    calculation consumes the retained records. Acquisition, reconstruction, and
    validation errors propagate; they are not analytical BLOCKED outcomes.
    This is not historical knowledge-time reconstruction or durable release.
    """

    if not isinstance(request, RateChangeRequest):
        raise TypeError("request must be a RateChangeRequest.")
    dataset = load_canonical_dataset(engine)
    return calculate_rate_change(dataset, request)


def create_rate_change_bundle_from_database(
    engine: Engine,
    request: RateChangeRequest,
    execution: ExecutionIdentity,
) -> RateChangeBundle:
    """Retain the one acquired dataset and calculate/encode over those records.

    The reader closes its transaction before pure bundle creation. No second
    acquisition, archive write, retry, release approval, or deployment attestation
    occurs. V1 codec restrictions apply to the entire dataset, including unrelated
    records. Configure psycopg sessions with TimeZone=UTC for fixed-offset returned
    timestamps; unsupported named-zone objects are rejected without normalization.
    """
    if not isinstance(request, RateChangeRequest):
        raise TypeError("request must be a RateChangeRequest.")
    if not isinstance(execution, ExecutionIdentity):
        raise TypeError("execution must be an ExecutionIdentity.")
    dataset = load_canonical_dataset(engine)
    return create_rate_change_bundle(dataset, request, execution)
