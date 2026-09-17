from datetime import date

import pytest

from european_capital_markets.domain.entities import IssuerRecord
from european_capital_markets.domain.issuer_identity import (
    IssuerIdentifierRecord,
    resolve_issuer_identifier,
    validate_issuer_identity_bundle,
)
from european_capital_markets.domain.lineage import EvidenceRecord, SourceRecord
from european_capital_markets.domain.taxonomy import (
    IdentifierScopeType,
    IssuerIdentifierType,
    SourceTier,
    SourceType,
)


def _issuer(
    issuer_id: str = "ISS000000001",
    name: str = "Example Issuer plc",
) -> IssuerRecord:
    return IssuerRecord(
        issuer_id=issuer_id,
        canonical_name=name,
    )



def _source(
    source_id: str = "SRC000000001",
) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.ISSUER_ANNOUNCEMENT,
        publisher="Example Issuer plc",
        title="Issuer Identity Record",
        access_date=date(2026, 9, 17),
        url="https://example.invalid/identity",
    )

def _evidence(
    evidence_id: str = "EVD000000001",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        source_id="SRC000000001",
        locator="Issuer identity section",
    )


def _ticker(
    *,
    issuer_id: str = "ISS000000001",
    value: str = "EXM",
    venue: str = "XLON",
    assignment_valid_from: date | None = None,
    assignment_valid_to: date | None = None,
) -> IssuerIdentifierRecord:
    return IssuerIdentifierRecord(
        issuer_id=issuer_id,
        identifier_type=IssuerIdentifierType.TICKER,
        identifier_value=value,
        scope_type=IdentifierScopeType.TRADING_VENUE,
        scope_value=venue,
        assignment_valid_from=assignment_valid_from,
        assignment_valid_to=assignment_valid_to,
        evidence_ids=("EVD000000001",),
    )


def test_valid_lei_identifier() -> None:
    record = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.LEI,
        identifier_value="5493001KJTIIGC8Y1R12",
        scope_type=IdentifierScopeType.GLOBAL,
        evidence_ids=("EVD000000001",),
    )

    assert record.scope_value is None


def test_lei_requires_twenty_character_structure() -> None:
    with pytest.raises(ValueError, match="18 upper-case"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.LEI,
            identifier_value="TOO_SHORT",
            scope_type=IdentifierScopeType.GLOBAL,
            evidence_ids=("EVD000000001",),
        )


def test_global_identifier_rejects_scope_value() -> None:
    with pytest.raises(ValueError, match="must not define scope_value"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.LEI,
            identifier_value="5493001KJTIIGC8Y1R12",
            scope_type=IdentifierScopeType.GLOBAL,
            scope_value="XLON",
            evidence_ids=("EVD000000001",),
        )


def test_ticker_requires_trading_venue_scope() -> None:
    with pytest.raises(ValueError, match="TRADING_VENUE"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.GLOBAL,
            evidence_ids=("EVD000000001",),
        )


def test_scoped_identifier_requires_scope_value() -> None:
    with pytest.raises(ValueError, match="require scope_value"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            evidence_ids=("EVD000000001",),
        )


def test_ticker_uses_canonical_upper_case() -> None:
    with pytest.raises(ValueError, match="upper case"):
        _ticker(value="exm")


def test_identifier_requires_source_evidence() -> None:
    with pytest.raises(ValueError, match="require source evidence"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            evidence_ids=(),
        )


def test_validity_interval_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="earlier than"):
        _ticker(
            assignment_valid_from=date(2026, 1, 1),
            assignment_valid_to=date(2026, 1, 1),
        )


def test_bundle_rejects_unknown_issuer() -> None:
    record = _ticker(issuer_id="ISS000000002")

    with pytest.raises(ValueError, match="Unknown issuer"):
        validate_issuer_identity_bundle(
            issuers=(_issuer(),),
            sources=(_source(),),
            identifiers=(record,),
            evidence=(_evidence(),),
        )


def test_bundle_rejects_unknown_evidence() -> None:
    record = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.TICKER,
        identifier_value="EXM",
        scope_type=IdentifierScopeType.TRADING_VENUE,
        scope_value="XLON",
        evidence_ids=("EVD000000002",),
    )

    with pytest.raises(ValueError, match="Unknown evidence"):
        validate_issuer_identity_bundle(
            issuers=(_issuer(),),
            sources=(_source(),),
            identifiers=(record,),
            evidence=(_evidence(),),
        )


def test_same_lei_cannot_map_to_multiple_canonical_issuers() -> None:
    first = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.LEI,
        identifier_value="5493001KJTIIGC8Y1R12",
        scope_type=IdentifierScopeType.GLOBAL,
        evidence_ids=("EVD000000001",),
    )
    second = IssuerIdentifierRecord(
        issuer_id="ISS000000002",
        identifier_type=IssuerIdentifierType.LEI,
        identifier_value="5493001KJTIIGC8Y1R12",
        scope_type=IdentifierScopeType.GLOBAL,
        evidence_ids=("EVD000000001",),
    )

    with pytest.raises(ValueError, match="same LEI"):
        validate_issuer_identity_bundle(
            issuers=(
                _issuer(),
                _issuer("ISS000000002", "Second Issuer plc"),
            ),
            sources=(_source(),),
            identifiers=(first, second),
            evidence=(_evidence(),),
        )


def test_overlapping_scoped_identifier_assignments_are_rejected() -> None:
    first = _ticker(
        issuer_id="ISS000000001",
        assignment_valid_from=date(2020, 1, 1),
        assignment_valid_to=date(2025, 1, 1),
    )
    second = _ticker(
        issuer_id="ISS000000002",
        assignment_valid_from=date(2024, 1, 1),
        assignment_valid_to=date(2026, 1, 1),
    )

    with pytest.raises(ValueError, match="overlap"):
        validate_issuer_identity_bundle(
            issuers=(
                _issuer(),
                _issuer("ISS000000002", "Second Issuer plc"),
            ),
            sources=(_source(),),
            identifiers=(first, second),
            evidence=(_evidence(),),
        )


def test_ticker_can_be_reused_after_prior_assignment_expires() -> None:
    first = _ticker(
        issuer_id="ISS000000001",
        assignment_valid_from=date(2020, 1, 1),
        assignment_valid_to=date(2025, 1, 1),
    )
    second = _ticker(
        issuer_id="ISS000000002",
        assignment_valid_from=date(2025, 1, 1),
    )

    validate_issuer_identity_bundle(
        issuers=(
            _issuer(),
            _issuer("ISS000000002", "Second Issuer plc"),
        ),
        sources=(_source(),),
        identifiers=(first, second),
        evidence=(_evidence(),),
    )


def test_resolution_is_as_of_date_sensitive() -> None:
    first = _ticker(
        issuer_id="ISS000000001",
        assignment_valid_from=date(2020, 1, 1),
        assignment_valid_to=date(2025, 1, 1),
    )
    second = _ticker(
        issuer_id="ISS000000002",
        assignment_valid_from=date(2025, 1, 1),
    )
    identifiers = (first, second)

    assert (
        resolve_issuer_identifier(
            identifiers,
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            as_of_date=date(2024, 12, 31),
        )
        == "ISS000000001"
    )

    assert (
        resolve_issuer_identifier(
            identifiers,
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            as_of_date=date(2025, 1, 1),
        )
        == "ISS000000002"
    )


def test_resolution_returns_none_when_no_mapping_is_active() -> None:
    identifiers = (
        _ticker(
            assignment_valid_from=date(2020, 1, 1),
            assignment_valid_to=date(2025, 1, 1),
        ),
    )

    assert (
        resolve_issuer_identifier(
            identifiers,
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            as_of_date=date(2026, 1, 1),
        )
        is None
    )


def test_resolution_rejects_ambiguous_unvalidated_input() -> None:
    first = _ticker(issuer_id="ISS000000001")
    second = _ticker(issuer_id="ISS000000002")

    with pytest.raises(ValueError, match="ambiguous"):
        resolve_issuer_identifier(
            (first, second),
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            as_of_date=date(2026, 1, 1),
        )


def test_resolution_rejects_invalid_scope_semantics() -> None:
    with pytest.raises(ValueError, match="TRADING_VENUE"):
        resolve_issuer_identifier(
            (),
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="EXM",
            scope_type=IdentifierScopeType.GLOBAL,
            scope_value=None,
            as_of_date=date(2026, 1, 1),
        )


def test_resolution_rejects_noncanonical_ticker() -> None:
    with pytest.raises(ValueError, match="upper case"):
        resolve_issuer_identifier(
            (),
            identifier_type=IssuerIdentifierType.TICKER,
            identifier_value="exm",
            scope_type=IdentifierScopeType.TRADING_VENUE,
            scope_value="XLON",
            as_of_date=date(2026, 1, 1),
        )


def test_lei_requires_numeric_check_digits() -> None:
    with pytest.raises(ValueError, match="numeric check digits"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.LEI,
            identifier_value="5493001KJTIIGC8Y1R1A",
            scope_type=IdentifierScopeType.GLOBAL,
            evidence_ids=("EVD000000001",),
        )


def test_lei_rejects_invalid_check_digits() -> None:
    with pytest.raises(ValueError, match="check digits are invalid"):
        IssuerIdentifierRecord(
            issuer_id="ISS000000001",
            identifier_type=IssuerIdentifierType.LEI,
            identifier_value="5493001KJTIIGC8Y1R13",
            scope_type=IdentifierScopeType.GLOBAL,
            evidence_ids=("EVD000000001",),
        )


def test_duplicate_lei_mapping_for_same_issuer_is_rejected() -> None:
    first = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.LEI,
        identifier_value="5493001KJTIIGC8Y1R12",
        scope_type=IdentifierScopeType.GLOBAL,
        evidence_ids=("EVD000000001",),
    )
    second = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.LEI,
        identifier_value="5493001KJTIIGC8Y1R12",
        scope_type=IdentifierScopeType.GLOBAL,
        evidence_ids=("EVD000000001",),
    )

    with pytest.raises(ValueError, match="consolidate supporting evidence"):
        validate_issuer_identity_bundle(
            issuers=(_issuer(),),
            sources=(_source(),),
            identifiers=(first, second),
            evidence=(_evidence(),),
        )


def test_overlapping_same_issuer_mapping_is_rejected() -> None:
    first = _ticker(
        assignment_valid_from=date(2020, 1, 1),
        assignment_valid_to=date(2025, 1, 1),
    )
    second = _ticker(
        assignment_valid_from=date(2024, 1, 1),
        assignment_valid_to=date(2026, 1, 1),
    )

    with pytest.raises(ValueError, match="consolidate supporting evidence"):
        validate_issuer_identity_bundle(
            issuers=(_issuer(),),
            sources=(_source(),),
            identifiers=(first, second),
            evidence=(_evidence(),),
        )


def test_identity_bundle_rejects_orphan_evidence_source() -> None:
    orphan_evidence = EvidenceRecord(
        evidence_id="EVD000000001",
        source_id="SRC000000002",
        locator="Issuer identity section",
    )

    with pytest.raises(ValueError, match="Unknown source"):
        validate_issuer_identity_bundle(
            issuers=(_issuer(),),
            sources=(_source(),),
            identifiers=(_ticker(),),
            evidence=(orphan_evidence,),
        )


def test_multiple_sources_are_consolidated_into_one_mapping() -> None:
    second_evidence = EvidenceRecord(
        evidence_id="EVD000000002",
        source_id="SRC000000001",
        locator="Secondary identity confirmation",
    )
    record = IssuerIdentifierRecord(
        issuer_id="ISS000000001",
        identifier_type=IssuerIdentifierType.TICKER,
        identifier_value="EXM",
        scope_type=IdentifierScopeType.TRADING_VENUE,
        scope_value="XLON",
        evidence_ids=("EVD000000001", "EVD000000002"),
    )

    validate_issuer_identity_bundle(
        issuers=(_issuer(),),
        sources=(_source(),),
        identifiers=(record,),
        evidence=(_evidence(), second_evidence),
    )
