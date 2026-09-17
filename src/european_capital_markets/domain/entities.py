"""Canonical issuer, transaction, and instrument entities."""

from dataclasses import dataclass

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.taxonomy import EntityType, ProductFamily


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")


@dataclass(frozen=True, slots=True)
class IssuerRecord:
    """Stable canonical identity for an issuer."""

    issuer_id: str
    canonical_name: str

    def __post_init__(self) -> None:
        validate_identifier(self.issuer_id, EntityType.ISSUER)
        _require_non_blank(self.canonical_name, "canonical_name")


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    """Canonical financing event anchored to one primary analytical issuer."""

    transaction_id: str
    primary_issuer_id: str
    product_family: ProductFamily
    transaction_label: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.transaction_id, EntityType.TRANSACTION)
        validate_identifier(self.primary_issuer_id, EntityType.ISSUER)

        if not isinstance(self.product_family, ProductFamily):
            raise TypeError("product_family must be a ProductFamily.")

        if self.transaction_label is not None:
            _require_non_blank(self.transaction_label, "transaction_label")


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    """Canonical instrument or tranche belonging to one transaction."""

    instrument_id: str
    transaction_id: str
    instrument_label: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.instrument_id, EntityType.INSTRUMENT)
        validate_identifier(self.transaction_id, EntityType.TRANSACTION)

        if self.instrument_label is not None:
            _require_non_blank(self.instrument_label, "instrument_label")


def validate_entity_bundle(
    issuers: tuple[IssuerRecord, ...],
    transactions: tuple[TransactionRecord, ...],
    instruments: tuple[InstrumentRecord, ...],
) -> None:
    """Validate uniqueness and canonical parent-child relationships."""

    issuer_by_id = _index_unique(issuers, "issuer_id")
    transaction_by_id = _index_unique(transactions, "transaction_id")
    _index_unique(instruments, "instrument_id")

    for transaction in transactions:
        if transaction.primary_issuer_id not in issuer_by_id:
            raise ValueError(
                "Unknown primary issuer reference: "
                f"{transaction.primary_issuer_id!r}"
            )

    for instrument in instruments:
        if instrument.transaction_id not in transaction_by_id:
            raise ValueError(
                f"Unknown transaction reference: {instrument.transaction_id!r}"
            )


def _index_unique[T](
    records: tuple[T, ...],
    id_field: str,
) -> dict[str, T]:
    index: dict[str, T] = {}

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in index:
            raise ValueError(f"Duplicate identifier: {identifier!r}")

        index[identifier] = record

    return index
