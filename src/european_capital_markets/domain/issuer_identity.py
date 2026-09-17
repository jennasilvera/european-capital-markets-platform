"""Issuer external identifiers and deterministic identity resolution."""

from dataclasses import dataclass
from datetime import date
from re import fullmatch

from european_capital_markets.domain.entities import IssuerRecord
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    SourceRecord,
    validate_lineage_bundle,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
)

_EXPECTED_SCOPE_BY_IDENTIFIER_TYPE = {
    IssuerIdentifierType.LEI: IdentifierScopeType.GLOBAL,
    IssuerIdentifierType.TICKER: IdentifierScopeType.TRADING_VENUE,
    IssuerIdentifierType.COMPANY_REGISTRATION_NUMBER: IdentifierScopeType.REGISTRY,
    IssuerIdentifierType.VENDOR_IDENTIFIER: IdentifierScopeType.VENDOR,
    IssuerIdentifierType.OTHER: IdentifierScopeType.OTHER,
}


@dataclass(frozen=True, slots=True)
class IssuerIdentifierRecord:
    """Source-backed external identifier associated with a canonical issuer."""

    issuer_id: str
    identifier_type: IssuerIdentifierType
    identifier_value: str
    scope_type: IdentifierScopeType
    evidence_ids: tuple[str, ...]
    scope_value: str | None = None
    assignment_valid_from: date | None = None
    assignment_valid_to: date | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.issuer_id, EntityType.ISSUER)

        _validate_identifier_components(
            identifier_type=self.identifier_type,
            identifier_value=self.identifier_value,
            scope_type=self.scope_type,
            scope_value=self.scope_value,
        )

        if (
            self.assignment_valid_from is not None
            and self.assignment_valid_to is not None
            and self.assignment_valid_from >= self.assignment_valid_to
        ):
            raise ValueError(
                "assignment_valid_from must be earlier than assignment_valid_to."
            )

        if not self.evidence_ids:
            raise ValueError("Issuer identifier records require source evidence.")

        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must not contain duplicates.")

        for evidence_id in self.evidence_ids:
            validate_identifier(evidence_id, EntityType.EVIDENCE)

        if self.notes is not None:
            _require_canonical_text(self.notes, "notes")


def validate_issuer_identity_bundle(
    issuers: tuple[IssuerRecord, ...],
    identifiers: tuple[IssuerIdentifierRecord, ...],
    sources: tuple[SourceRecord, ...],
    evidence: tuple[EvidenceRecord, ...],
) -> None:
    """Validate identity references, evidence lineage, and identifier collisions."""

    validate_lineage_bundle(
        sources=sources,
        evidence=evidence,
        observations=(),
    )

    issuer_ids = _unique_ids(issuers, "issuer_id")
    evidence_ids = {record.evidence_id for record in evidence}

    for identifier in identifiers:
        if identifier.issuer_id not in issuer_ids:
            raise ValueError(
                f"Unknown issuer reference: {identifier.issuer_id!r}"
            )

        for evidence_id in identifier.evidence_ids:
            if evidence_id not in evidence_ids:
                raise ValueError(
                    f"Unknown evidence reference: {evidence_id!r}"
                )

    _validate_identifier_collisions(identifiers)


def resolve_issuer_identifier(
    identifiers: tuple[IssuerIdentifierRecord, ...],
    *,
    identifier_type: IssuerIdentifierType,
    identifier_value: str,
    scope_type: IdentifierScopeType,
    scope_value: str | None,
    as_of_date: date,
) -> str | None:
    """Resolve an external identifier to one canonical issuer at a point in time."""

    _validate_identifier_components(
        identifier_type=identifier_type,
        identifier_value=identifier_value,
        scope_type=scope_type,
        scope_value=scope_value,
    )

    matches = {
        record.issuer_id
        for record in identifiers
        if record.identifier_type is identifier_type
        and record.identifier_value == identifier_value
        and record.scope_type is scope_type
        and record.scope_value == scope_value
        and _contains_date(record, as_of_date)
    }

    if not matches:
        return None

    if len(matches) > 1:
        raise ValueError(
            "Identifier resolution is ambiguous for the requested date."
        )

    return next(iter(matches))


def _validate_identifier_components(
    *,
    identifier_type: IssuerIdentifierType,
    identifier_value: str,
    scope_type: IdentifierScopeType,
    scope_value: str | None,
) -> None:
    if not isinstance(identifier_type, IssuerIdentifierType):
        raise TypeError("identifier_type must be an IssuerIdentifierType.")

    if not isinstance(scope_type, IdentifierScopeType):
        raise TypeError("scope_type must be an IdentifierScopeType.")

    _require_canonical_text(identifier_value, "identifier_value")

    expected_scope = _EXPECTED_SCOPE_BY_IDENTIFIER_TYPE[identifier_type]
    if scope_type is not expected_scope:
        raise ValueError(
            f"{identifier_type.value} requires {expected_scope.value} scope."
        )

    if scope_type is IdentifierScopeType.GLOBAL:
        if scope_value is not None:
            raise ValueError("GLOBAL identifiers must not define scope_value.")
    else:
        if scope_value is None:
            raise ValueError(
                f"{scope_type.value} identifiers require scope_value."
            )

        _require_canonical_text(scope_value, "scope_value")

    if identifier_type is IssuerIdentifierType.LEI:
        _validate_lei(identifier_value)

    if (
        identifier_type is IssuerIdentifierType.TICKER
        and identifier_value != identifier_value.upper()
    ):
        raise ValueError("Ticker identifiers must use canonical upper case.")


def _validate_lei(value: str) -> None:
    if fullmatch(r"[A-Z0-9]{18}[0-9]{2}", value) is None:
        raise ValueError(
            "LEI must contain 18 upper-case alphanumeric characters "
            "followed by 2 numeric check digits."
        )

    numeric_value = "".join(
        character
        if character.isdigit()
        else str(ord(character) - ord("A") + 10)
        for character in value
    )

    remainder = 0
    for digit in numeric_value:
        remainder = ((remainder * 10) + int(digit)) % 97

    if remainder != 1:
        raise ValueError("LEI check digits are invalid.")


def _require_canonical_text(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be blank.")

    if value != value.strip():
        raise ValueError(
            f"{field_name} must not contain leading or trailing whitespace."
        )


def _unique_ids[T](records: tuple[T, ...], id_field: str) -> set[str]:
    identifiers: set[str] = set()

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in identifiers:
            raise ValueError(f"Duplicate identifier: {identifier!r}")

        identifiers.add(identifier)

    return identifiers


def _identity_key(
    record: IssuerIdentifierRecord,
) -> tuple[
    IssuerIdentifierType,
    str,
    IdentifierScopeType,
    str | None,
]:
    return (
        record.identifier_type,
        record.identifier_value,
        record.scope_type,
        record.scope_value,
    )


def _validate_identifier_collisions(
    identifiers: tuple[IssuerIdentifierRecord, ...],
) -> None:
    for index, first in enumerate(identifiers):
        for second in identifiers[index + 1 :]:
            if _identity_key(first) != _identity_key(second):
                continue

            if first.identifier_type is IssuerIdentifierType.LEI:
                if first.issuer_id != second.issuer_id:
                    raise ValueError(
                        "The same LEI cannot map to multiple canonical issuers."
                    )

                raise ValueError(
                    "Duplicate LEI mapping for the same issuer; "
                    "consolidate supporting evidence."
                )

            if not _intervals_overlap(first, second):
                continue

            if first.issuer_id == second.issuer_id:
                raise ValueError(
                    "Overlapping duplicate identifier mapping for the same issuer; "
                    "consolidate supporting evidence."
                )

            raise ValueError(
                "External identifier validity intervals overlap for the "
                "same identifier namespace."
            )


def _intervals_overlap(
    first: IssuerIdentifierRecord,
    second: IssuerIdentifierRecord,
) -> bool:
    first_start = first.assignment_valid_from or date.min
    first_end = first.assignment_valid_to or date.max
    second_start = second.assignment_valid_from or date.min
    second_end = second.assignment_valid_to or date.max

    return first_start < second_end and second_start < first_end


def _contains_date(
    record: IssuerIdentifierRecord,
    as_of_date: date,
) -> bool:
    if (
        record.assignment_valid_from is not None
        and as_of_date < record.assignment_valid_from
    ):
        return False

    return record.assignment_valid_to is None or as_of_date < record.assignment_valid_to
