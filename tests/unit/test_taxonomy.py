from enum import Enum

from european_capital_markets.domain.taxonomy import (
    CapitalType,
    DebtDistribution,
    DebtPurpose,
    DebtRanking,
    ECMExecutionMethod,
    ECMStructure,
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
    LeveragedFinanceInstrument,
    LeveragedFinancePurpose,
    MissingDataState,
    OwnershipType,
    ParticipantRole,
    PartyType,
    ProductFamily,
    RateType,
    ReleaseStatus,
    SecurityType,
    SellerType,
    SourceTier,
    SourceType,
    TransactionStatus,
    ValueClass,
    VerificationState,
)


def _values(enum_type: type[Enum]) -> list[object]:
    return [member.value for member in enum_type]


def test_product_families_are_explicit() -> None:
    assert set(_values(ProductFamily)) == {
        "ECM",
        "IG_DCM",
        "LEVERAGED_FINANCE",
        "EQUITY_LINKED",
    }


def test_party_types_are_explicit() -> None:
    assert set(_values(PartyType)) == {
        "CORPORATE",
        "FINANCIAL_INSTITUTION",
        "FUND",
        "GOVERNMENT",
        "INDIVIDUAL",
        "SPECIAL_PURPOSE_VEHICLE",
        "OTHER",
    }


def test_transaction_status_preserves_unsuccessful_execution() -> None:
    assert TransactionStatus.POSTPONED.value == "POSTPONED"
    assert TransactionStatus.WITHDRAWN.value == "WITHDRAWN"
    assert TransactionStatus.CANCELLED.value == "CANCELLED"


def test_value_class_and_verification_are_separate_dimensions() -> None:
    assert ValueClass.DISCLOSED.value == "DISCLOSED"
    assert VerificationState.PENDING.value == "PENDING"
    assert VerificationState.PRIMARY_VERIFIED.value == "PRIMARY_VERIFIED"


def test_missing_data_states_do_not_use_numeric_zero() -> None:
    assert 0 not in _values(MissingDataState)


def test_source_tier_order_is_explicit() -> None:
    assert _values(SourceTier) == [1, 2, 3, 4, 5]


def test_source_type_is_separate_from_source_tier() -> None:
    assert SourceType.PROSPECTUS.value == "PROSPECTUS"
    assert SourceType.MARKET_DATA.value == "MARKET_DATA"
    assert SourceType.ANALYST_WORKPAPER.value == "ANALYST_WORKPAPER"


def test_issuer_identifier_taxonomy_is_explicit() -> None:
    assert IssuerIdentifierType.LEI.value == "LEI"
    assert IssuerIdentifierType.TICKER.value == "TICKER"
    assert IdentifierScopeType.GLOBAL.value == "GLOBAL"
    assert IdentifierScopeType.TRADING_VENUE.value == "TRADING_VENUE"


def test_ecm_dimensions_are_separate() -> None:
    assert ECMStructure.RIGHTS_ISSUE.value == "RIGHTS_ISSUE"
    assert CapitalType.SECONDARY.value == "SECONDARY"
    assert ECMExecutionMethod.BOOKBUILT.value == "BOOKBUILT"
    assert SellerType.SPONSOR.value == "SPONSOR"


def test_ig_dcm_dimensions_are_separate() -> None:
    assert DebtRanking.SENIOR_UNSECURED.value == "SENIOR_UNSECURED"
    assert RateType.FLOATING.value == "FLOATING"
    assert DebtDistribution.PUBLIC_BENCHMARK.value == "PUBLIC_BENCHMARK"
    assert DebtPurpose.REFINANCING.value == "REFINANCING"


def test_leveraged_finance_dimensions_are_separate() -> None:
    assert LeveragedFinanceInstrument.TERM_LOAN_B.value == "TERM_LOAN_B"
    assert LeveragedFinancePurpose.ACQUISITION.value == "ACQUISITION"
    assert OwnershipType.SPONSOR_BACKED.value == "SPONSOR_BACKED"
    assert SecurityType.SECURED.value == "SECURED"


def test_core_entity_types_are_stable() -> None:
    assert set(_values(EntityType)) == {
        "ISSUER",
        "PARTY",
        "PARTICIPATION",
        "TRANSACTION",
        "INSTRUMENT",
        "OBSERVATION",
        "SOURCE",
        "EVIDENCE",
        "ASSUMPTION",
        "RELEASE",
    }


def test_release_states_are_explicit() -> None:
    assert _values(ReleaseStatus) == [
        "WORKING",
        "REVIEWED",
        "RELEASED",
        "SUPERSEDED",
    ]


def test_all_string_enums_have_unique_values() -> None:
    enum_types = (
        EntityType,
        ParticipantRole,
        PartyType,
        ProductFamily,
        IssuerIdentifierType,
        IdentifierScopeType,
        ValueClass,
        VerificationState,
        MissingDataState,
        TransactionStatus,
        ReleaseStatus,
        SourceType,
        ECMStructure,
        CapitalType,
        ECMExecutionMethod,
        SellerType,
        DebtRanking,
        RateType,
        DebtDistribution,
        DebtPurpose,
        LeveragedFinanceInstrument,
        LeveragedFinancePurpose,
        OwnershipType,
        SecurityType,
    )

    for enum_type in enum_types:
        values = _values(enum_type)
        assert len(values) == len(set(values)), enum_type.__name__

def test_participant_roles_are_explicit() -> None:
    assert set(_values(ParticipantRole)) == {
        "LEGAL_ISSUER",
        "BORROWER",
        "GUARANTOR",
        "SPONSOR",
        "SELLING_SHAREHOLDER",
        "ACQUISITION_VEHICLE",
    }
