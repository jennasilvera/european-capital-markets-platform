"""Canonical parties that may participate in capital-markets transactions."""

from dataclasses import dataclass

from european_capital_markets.domain.entities import IssuerRecord
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.taxonomy import EntityType, PartyType


@dataclass(frozen=True, slots=True)
class PartyRecord:
    """Canonical participant identity used by transaction-role relationships."""

    party_id: str
    party_type: PartyType
    linked_issuer_id: str | None = None
    canonical_name: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.party_id, EntityType.PARTY)

        if not isinstance(self.party_type, PartyType):
            raise TypeError("party_type must be a PartyType.")

        if self.linked_issuer_id is not None:
            validate_identifier(self.linked_issuer_id, EntityType.ISSUER)

            if self.canonical_name is not None:
                raise ValueError(
                    "An issuer-linked party must derive its name from IssuerRecord."
                )
            return

        if self.canonical_name is None:
            raise ValueError(
                "A party without linked_issuer_id requires canonical_name."
            )

        _require_non_blank(self.canonical_name, "canonical_name")


def validate_party_bundle(
    issuers: tuple[IssuerRecord, ...],
    parties: tuple[PartyRecord, ...],
) -> None:
    """Validate party uniqueness and optional issuer bridges."""

    issuer_ids = _unique_ids(issuers, "issuer_id")
    _unique_ids(parties, "party_id")

    issuer_to_party: dict[str, str] = {}

    for party in parties:
        if party.linked_issuer_id is None:
            continue

        if party.linked_issuer_id not in issuer_ids:
            raise ValueError(
                f"Unknown linked issuer reference: {party.linked_issuer_id!r}"
            )

        existing_party_id = issuer_to_party.get(party.linked_issuer_id)
        if existing_party_id is not None:
            raise ValueError(
                f"Issuer {party.linked_issuer_id!r} is already linked to "
                f"party {existing_party_id!r}."
            )

        issuer_to_party[party.linked_issuer_id] = party.party_id


def party_display_name(
    party: PartyRecord,
    issuers: tuple[IssuerRecord, ...],
) -> str:
    """Resolve the display name without duplicating issuer naming data."""

    if party.linked_issuer_id is None:
        if party.canonical_name is None:
            raise ValueError("Unlinked party is missing canonical_name.")
        return party.canonical_name

    issuer_by_id = {issuer.issuer_id: issuer for issuer in issuers}

    try:
        issuer = issuer_by_id[party.linked_issuer_id]
    except KeyError as exc:
        raise ValueError(
            f"Unknown linked issuer reference: {party.linked_issuer_id!r}"
        ) from exc

    return issuer.canonical_name


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")


def _unique_ids[T](records: tuple[T, ...], id_field: str) -> set[str]:
    identifiers: set[str] = set()

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in identifiers:
            raise ValueError(f"Duplicate identifier: {identifier!r}")

        identifiers.add(identifier)

    return identifiers
