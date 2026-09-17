from dataclasses import FrozenInstanceError

import pytest

from european_capital_markets.domain.entities import (
    InstrumentRecord,
    IssuerRecord,
    TransactionRecord,
    validate_entity_bundle,
)
from european_capital_markets.domain.taxonomy import ProductFamily


def _issuer() -> IssuerRecord:
    return IssuerRecord(
        issuer_id="ISS000000001",
        canonical_name="Example Issuer plc",
    )


def _transaction() -> TransactionRecord:
    return TransactionRecord(
        transaction_id="TXN000000001",
        primary_issuer_id="ISS000000001",
        product_family=ProductFamily.IG_DCM,
        transaction_label="Example 2026 Bond Financing",
    )


def _instrument() -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id="INS000000001",
        transaction_id="TXN000000001",
        instrument_label="5Y Senior Notes",
    )


def test_valid_entity_hierarchy() -> None:
    validate_entity_bundle(
        issuers=(_issuer(),),
        transactions=(_transaction(),),
        instruments=(_instrument(),),
    )


def test_issuer_requires_issuer_identifier() -> None:
    with pytest.raises(ValueError, match="not ISSUER"):
        IssuerRecord(
            issuer_id="TXN000000001",
            canonical_name="Example Issuer plc",
        )


def test_issuer_name_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="canonical_name"):
        IssuerRecord(
            issuer_id="ISS000000001",
            canonical_name="   ",
        )


def test_transaction_requires_controlled_product_family() -> None:
    with pytest.raises(TypeError, match="ProductFamily"):
        TransactionRecord(
            transaction_id="TXN000000001",
            primary_issuer_id="ISS000000001",
            product_family="IG_DCM",  # type: ignore[arg-type]
        )


def test_optional_transaction_label_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="transaction_label"):
        TransactionRecord(
            transaction_id="TXN000000001",
            primary_issuer_id="ISS000000001",
            product_family=ProductFamily.ECM,
            transaction_label=" ",
        )


def test_optional_instrument_label_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="instrument_label"):
        InstrumentRecord(
            instrument_id="INS000000001",
            transaction_id="TXN000000001",
            instrument_label=" ",
        )


def test_bundle_rejects_unknown_issuer_reference() -> None:
    transaction = TransactionRecord(
        transaction_id="TXN000000001",
        primary_issuer_id="ISS000000002",
        product_family=ProductFamily.ECM,
    )

    with pytest.raises(ValueError, match="Unknown primary issuer"):
        validate_entity_bundle(
            issuers=(_issuer(),),
            transactions=(transaction,),
            instruments=(),
        )


def test_bundle_rejects_unknown_transaction_reference() -> None:
    instrument = InstrumentRecord(
        instrument_id="INS000000001",
        transaction_id="TXN000000002",
    )

    with pytest.raises(ValueError, match="Unknown transaction"):
        validate_entity_bundle(
            issuers=(_issuer(),),
            transactions=(_transaction(),),
            instruments=(instrument,),
        )


def test_bundle_rejects_duplicate_entity_identifiers() -> None:
    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_entity_bundle(
            issuers=(_issuer(), _issuer()),
            transactions=(),
            instruments=(),
        )


def test_instrument_does_not_duplicate_issuer_relationship() -> None:
    instrument = _instrument()

    assert not hasattr(instrument, "primary_issuer_id")


def test_entities_are_immutable() -> None:
    issuer = _issuer()

    with pytest.raises(FrozenInstanceError):
        issuer.canonical_name = "Changed Name"  # type: ignore[misc]


def test_transaction_requires_transaction_identifier() -> None:
    with pytest.raises(ValueError, match="not TRANSACTION"):
        TransactionRecord(
            transaction_id="ISS000000001",
            primary_issuer_id="ISS000000001",
            product_family=ProductFamily.ECM,
        )


def test_transaction_requires_issuer_identifier_for_primary_anchor() -> None:
    with pytest.raises(ValueError, match="not ISSUER"):
        TransactionRecord(
            transaction_id="TXN000000001",
            primary_issuer_id="TXN000000002",
            product_family=ProductFamily.ECM,
        )


def test_instrument_requires_instrument_identifier() -> None:
    with pytest.raises(ValueError, match="not INSTRUMENT"):
        InstrumentRecord(
            instrument_id="TXN000000001",
            transaction_id="TXN000000001",
        )


def test_instrument_requires_transaction_identifier_for_parent() -> None:
    with pytest.raises(ValueError, match="not TRANSACTION"):
        InstrumentRecord(
            instrument_id="INS000000001",
            transaction_id="ISS000000001",
        )


def test_bundle_rejects_duplicate_transaction_identifiers() -> None:
    transaction = _transaction()

    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_entity_bundle(
            issuers=(_issuer(),),
            transactions=(transaction, transaction),
            instruments=(),
        )


def test_bundle_rejects_duplicate_instrument_identifiers() -> None:
    instrument = _instrument()

    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_entity_bundle(
            issuers=(_issuer(),),
            transactions=(_transaction(),),
            instruments=(instrument, instrument),
        )


def test_multi_instrument_transaction_is_valid() -> None:
    second_instrument = InstrumentRecord(
        instrument_id="INS000000002",
        transaction_id="TXN000000001",
        instrument_label="10Y Senior Notes",
    )

    validate_entity_bundle(
        issuers=(_issuer(),),
        transactions=(_transaction(),),
        instruments=(_instrument(), second_instrument),
    )
