"""Permanent non-semantic identifiers used by canonical platform entities."""

from dataclasses import dataclass
from re import fullmatch

from european_capital_markets.domain.taxonomy import EntityType

IDENTIFIER_WIDTH = 9

_PREFIX_BY_ENTITY_TYPE: dict[EntityType, str] = {
    EntityType.ISSUER: "ISS",
    EntityType.PARTY: "PTY",
    EntityType.PARTICIPATION: "PAR",
    EntityType.TRANSACTION: "TXN",
    EntityType.TRANSACTION_LIFECYCLE_EVENT: "TLE",
    EntityType.INSTRUMENT: "INS",
    EntityType.MARKET_SERIES: "MKS",
    EntityType.OBSERVATION: "OBS",
    EntityType.SOURCE: "SRC",
    EntityType.EVIDENCE: "EVD",
    EntityType.ASSUMPTION: "ASM",
    EntityType.RELEASE: "REL",
}

_ENTITY_TYPE_BY_PREFIX = {
    prefix: entity_type for entity_type, prefix in _PREFIX_BY_ENTITY_TYPE.items()
}


@dataclass(frozen=True, slots=True)
class ParsedIdentifier:
    """Parsed representation of a permanent platform identifier."""

    entity_type: EntityType
    sequence: int


def format_identifier(entity_type: EntityType, sequence: int) -> str:
    """Format an explicitly allocated positive sequence as a stable identifier."""

    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise TypeError("Identifier sequence must be an integer.")

    if sequence < 1:
        raise ValueError("Identifier sequence must be positive.")

    maximum = (10**IDENTIFIER_WIDTH) - 1
    if sequence > maximum:
        raise ValueError(
            f"Identifier sequence exceeds the {IDENTIFIER_WIDTH}-digit namespace."
        )

    prefix = _PREFIX_BY_ENTITY_TYPE[entity_type]
    return f"{prefix}{sequence:0{IDENTIFIER_WIDTH}d}"


def parse_identifier(identifier: str) -> ParsedIdentifier:
    """Parse and validate a permanent platform identifier."""

    if not isinstance(identifier, str):
        raise TypeError("Identifier must be a string.")

    match = fullmatch(
        rf"([A-Z]{{3}})([0-9]{{{IDENTIFIER_WIDTH}}})",
        identifier,
    )
    if match is None:
        raise ValueError(f"Invalid identifier format: {identifier!r}")

    prefix, sequence_text = match.groups()

    try:
        entity_type = _ENTITY_TYPE_BY_PREFIX[prefix]
    except KeyError as exc:
        raise ValueError(f"Unknown identifier prefix: {prefix!r}") from exc

    sequence = int(sequence_text)
    if sequence < 1:
        raise ValueError("Identifier sequence must be positive.")

    return ParsedIdentifier(entity_type=entity_type, sequence=sequence)


def validate_identifier(identifier: str, expected_type: EntityType) -> None:
    """Validate identifier format and its expected entity type."""

    parsed = parse_identifier(identifier)

    if parsed.entity_type is not expected_type:
        raise ValueError(
            f"Identifier {identifier!r} represents {parsed.entity_type.value}, "
            f"not {expected_type.value}."
        )
