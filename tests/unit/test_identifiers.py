import pytest

from european_capital_markets.domain.identifiers import (
    format_identifier,
    parse_identifier,
    validate_identifier,
)
from european_capital_markets.domain.taxonomy import EntityType


@pytest.mark.parametrize(
    ("entity_type", "expected"),
    [
        (EntityType.ISSUER, "ISS000000001"),
        (EntityType.PARTY, "PTY000000001"),
        (EntityType.TRANSACTION, "TXN000000001"),
        (EntityType.INSTRUMENT, "INS000000001"),
        (EntityType.OBSERVATION, "OBS000000001"),
        (EntityType.SOURCE, "SRC000000001"),
        (EntityType.EVIDENCE, "EVD000000001"),
        (EntityType.ASSUMPTION, "ASM000000001"),
        (EntityType.RELEASE, "REL000000001"),
    ],
)
def test_identifier_namespaces(
    entity_type: EntityType,
    expected: str,
) -> None:
    assert format_identifier(entity_type, 1) == expected


def test_identifier_round_trip() -> None:
    identifier = format_identifier(EntityType.TRANSACTION, 42)
    parsed = parse_identifier(identifier)

    assert parsed.entity_type is EntityType.TRANSACTION
    assert parsed.sequence == 42


def test_identifier_namespace_upper_bound() -> None:
    assert (
        format_identifier(EntityType.OBSERVATION, 999_999_999)
        == "OBS999999999"
    )


def test_identifier_namespace_overflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        format_identifier(EntityType.OBSERVATION, 1_000_000_000)


@pytest.mark.parametrize(
    "identifier",
    [
        "TXN000000000",
        "TXN1",
        "txn000000001",
        "ABC000000001",
        "TXN000000001EXTRA",
        "TXN000001",
    ],
)
def test_invalid_identifiers_are_rejected(identifier: str) -> None:
    with pytest.raises(ValueError):
        parse_identifier(identifier)


def test_identifier_type_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="not ISSUER"):
        validate_identifier("TXN000000001", EntityType.ISSUER)


def test_identifier_sequence_must_be_positive_integer() -> None:
    with pytest.raises(ValueError):
        format_identifier(EntityType.ISSUER, 0)

    with pytest.raises(TypeError):
        format_identifier(EntityType.ISSUER, True)
