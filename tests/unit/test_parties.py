from dataclasses import FrozenInstanceError

import pytest

from european_capital_markets.domain.entities import IssuerRecord
from european_capital_markets.domain.parties import (
    PartyRecord,
    party_display_name,
    validate_party_bundle,
)
from european_capital_markets.domain.taxonomy import PartyType


def _issuer(
    issuer_id: str = "ISS000000001",
    name: str = "Example Issuer plc",
) -> IssuerRecord:
    return IssuerRecord(
        issuer_id=issuer_id,
        canonical_name=name,
    )


def _linked_party() -> PartyRecord:
    return PartyRecord(
        party_id="PTY000000001",
        party_type=PartyType.CORPORATE,
        linked_issuer_id="ISS000000001",
    )


def test_valid_issuer_linked_party() -> None:
    party = _linked_party()

    assert party.linked_issuer_id == "ISS000000001"
    assert party.canonical_name is None


def test_valid_nonissuer_party() -> None:
    party = PartyRecord(
        party_id="PTY000000002",
        party_type=PartyType.FUND,
        canonical_name="Example Sponsor Fund",
    )

    assert party.canonical_name == "Example Sponsor Fund"


def test_party_requires_party_identifier() -> None:
    with pytest.raises(ValueError, match="not PARTY"):
        PartyRecord(
            party_id="ISS000000001",
            party_type=PartyType.CORPORATE,
            canonical_name="Example Party",
        )


def test_party_type_must_be_controlled() -> None:
    with pytest.raises(TypeError, match="PartyType"):
        PartyRecord(
            party_id="PTY000000001",
            party_type="FUND",  # type: ignore[arg-type]
            canonical_name="Example Fund",
        )


def test_unlinked_party_requires_name() -> None:
    with pytest.raises(ValueError, match="requires canonical_name"):
        PartyRecord(
            party_id="PTY000000001",
            party_type=PartyType.FUND,
        )


def test_unlinked_party_name_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="canonical_name"):
        PartyRecord(
            party_id="PTY000000001",
            party_type=PartyType.FUND,
            canonical_name="   ",
        )


def test_linked_party_must_not_duplicate_name() -> None:
    with pytest.raises(ValueError, match="derive its name"):
        PartyRecord(
            party_id="PTY000000001",
            party_type=PartyType.CORPORATE,
            linked_issuer_id="ISS000000001",
            canonical_name="Duplicate Name",
        )


def test_bundle_rejects_unknown_linked_issuer() -> None:
    party = PartyRecord(
        party_id="PTY000000001",
        party_type=PartyType.CORPORATE,
        linked_issuer_id="ISS000000002",
    )

    with pytest.raises(ValueError, match="Unknown linked issuer"):
        validate_party_bundle(
            issuers=(_issuer(),),
            parties=(party,),
        )


def test_bundle_rejects_duplicate_party_ids() -> None:
    party = _linked_party()

    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_party_bundle(
            issuers=(_issuer(),),
            parties=(party, party),
        )


def test_issuer_may_link_to_only_one_party() -> None:
    first = _linked_party()
    second = PartyRecord(
        party_id="PTY000000002",
        party_type=PartyType.CORPORATE,
        linked_issuer_id="ISS000000001",
    )

    with pytest.raises(ValueError, match="already linked"):
        validate_party_bundle(
            issuers=(_issuer(),),
            parties=(first, second),
        )


def test_linked_party_display_name_comes_from_issuer() -> None:
    assert (
        party_display_name(
            _linked_party(),
            issuers=(_issuer(),),
        )
        == "Example Issuer plc"
    )


def test_nonissuer_party_uses_own_display_name() -> None:
    party = PartyRecord(
        party_id="PTY000000002",
        party_type=PartyType.FUND,
        canonical_name="Example Sponsor Fund",
    )

    assert party_display_name(party, issuers=()) == "Example Sponsor Fund"


def test_parties_are_immutable() -> None:
    party = _linked_party()

    with pytest.raises(FrozenInstanceError):
        party.party_type = PartyType.FUND  # type: ignore[misc]
