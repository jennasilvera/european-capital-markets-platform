"""Controlled vocabularies used across the capital markets platform."""

from enum import IntEnum, StrEnum


class EntityType(StrEnum):
    """Canonical entity classes used by the analytical data model."""

    ISSUER = "ISSUER"
    PARTY = "PARTY"
    PARTICIPATION = "PARTICIPATION"
    TRANSACTION = "TRANSACTION"
    INSTRUMENT = "INSTRUMENT"
    OBSERVATION = "OBSERVATION"
    SOURCE = "SOURCE"
    EVIDENCE = "EVIDENCE"
    ASSUMPTION = "ASSUMPTION"
    RELEASE = "RELEASE"


class PartyType(StrEnum):
    """Canonical party classifications used in transaction relationships."""

    CORPORATE = "CORPORATE"
    FINANCIAL_INSTITUTION = "FINANCIAL_INSTITUTION"
    FUND = "FUND"
    GOVERNMENT = "GOVERNMENT"
    INDIVIDUAL = "INDIVIDUAL"
    SPECIAL_PURPOSE_VEHICLE = "SPECIAL_PURPOSE_VEHICLE"
    OTHER = "OTHER"


class ParticipantRole(StrEnum):
    """Role performed by a canonical party in a financing event."""

    LEGAL_ISSUER = "LEGAL_ISSUER"
    BORROWER = "BORROWER"
    GUARANTOR = "GUARANTOR"
    SPONSOR = "SPONSOR"
    SELLING_SHAREHOLDER = "SELLING_SHAREHOLDER"
    ACQUISITION_VEHICLE = "ACQUISITION_VEHICLE"


class ProductFamily(StrEnum):
    """Primary capital-markets product families."""

    ECM = "ECM"
    IG_DCM = "IG_DCM"
    LEVERAGED_FINANCE = "LEVERAGED_FINANCE"
    EQUITY_LINKED = "EQUITY_LINKED"


class ValueClass(StrEnum):
    """Origin of a material analytical value."""

    DISCLOSED = "DISCLOSED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    ASSUMED = "ASSUMED"


class VerificationState(StrEnum):
    """Verification status independent of value origin."""

    PRIMARY_VERIFIED = "PRIMARY_VERIFIED"
    SECONDARY_VERIFIED = "SECONDARY_VERIFIED"
    CROSS_VERIFIED = "CROSS_VERIFIED"
    PENDING = "PENDING"
    CONFLICT = "CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


class MissingDataState(StrEnum):
    """Explicit semantic states for unavailable or inapplicable values."""

    NOT_DISCLOSED = "NOT_DISCLOSED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"


class TransactionStatus(StrEnum):
    """Lifecycle state of a financing transaction."""

    ANNOUNCED = "ANNOUNCED"
    MARKETING = "MARKETING"
    LAUNCHED = "LAUNCHED"
    PRICED = "PRICED"
    ALLOCATED = "ALLOCATED"
    SETTLED = "SETTLED"
    POSTPONED = "POSTPONED"
    WITHDRAWN = "WITHDRAWN"
    CANCELLED = "CANCELLED"


class ReleaseStatus(StrEnum):
    """Controlled analytical release states."""

    WORKING = "WORKING"
    REVIEWED = "REVIEWED"
    RELEASED = "RELEASED"
    SUPERSEDED = "SUPERSEDED"


class SourceTier(IntEnum):
    """Default source-preference hierarchy."""

    PRIMARY_TRANSACTION_OR_ISSUER = 1
    OFFICIAL_INSTITUTION = 2
    ESTABLISHED_MARKET_DATA = 3
    HIGH_QUALITY_SECONDARY = 4
    ANALYST_DERIVED = 5


class SourceType(StrEnum):
    """Nature of the source independently of its evidence tier."""

    PROSPECTUS = "PROSPECTUS"
    OFFERING_DOCUMENT = "OFFERING_DOCUMENT"
    ISSUER_ANNOUNCEMENT = "ISSUER_ANNOUNCEMENT"
    EXCHANGE_ANNOUNCEMENT = "EXCHANGE_ANNOUNCEMENT"
    REGULATORY_FILING = "REGULATORY_FILING"
    FINANCIAL_REPORT = "FINANCIAL_REPORT"
    INVESTOR_PRESENTATION = "INVESTOR_PRESENTATION"
    RATING_AGENCY_PUBLICATION = "RATING_AGENCY_PUBLICATION"
    CENTRAL_BANK_PUBLICATION = "CENTRAL_BANK_PUBLICATION"
    OFFICIAL_STATISTICS = "OFFICIAL_STATISTICS"
    MARKET_DATA = "MARKET_DATA"
    FINANCIAL_NEWS = "FINANCIAL_NEWS"
    ANALYST_WORKPAPER = "ANALYST_WORKPAPER"
    OTHER = "OTHER"


class IssuerIdentifierType(StrEnum):
    """External identifier namespaces used for issuer resolution."""

    LEI = "LEI"
    TICKER = "TICKER"
    COMPANY_REGISTRATION_NUMBER = "COMPANY_REGISTRATION_NUMBER"
    VENDOR_IDENTIFIER = "VENDOR_IDENTIFIER"
    OTHER = "OTHER"


class IdentifierScopeType(StrEnum):
    """Scope required to interpret an external issuer identifier."""

    GLOBAL = "GLOBAL"
    TRADING_VENUE = "TRADING_VENUE"
    REGISTRY = "REGISTRY"
    VENDOR = "VENDOR"
    OTHER = "OTHER"


class ECMStructure(StrEnum):
    """Economic or transaction structure for ECM issuance."""

    IPO = "IPO"
    FOLLOW_ON = "FOLLOW_ON"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    ACCELERATED_BOOKBUILD = "ACCELERATED_BOOKBUILD"
    BLOCK_TRADE = "BLOCK_TRADE"
    OTHER = "OTHER"


class CapitalType(StrEnum):
    """Whether equity proceeds represent primary or secondary capital."""

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    MIXED = "MIXED"


class ECMExecutionMethod(StrEnum):
    """Execution method for an ECM transaction."""

    BOOKBUILT = "BOOKBUILT"
    ACCELERATED_BOOKBUILD = "ACCELERATED_BOOKBUILD"
    RIGHTS_OFFERING = "RIGHTS_OFFERING"
    PLACEMENT = "PLACEMENT"
    OTHER = "OTHER"


class SellerType(StrEnum):
    """Selling-holder classification for ECM transactions."""

    ISSUER = "ISSUER"
    SPONSOR = "SPONSOR"
    FOUNDER = "FOUNDER"
    STRATEGIC_SHAREHOLDER = "STRATEGIC_SHAREHOLDER"
    GOVERNMENT = "GOVERNMENT"
    OTHER_SHAREHOLDER = "OTHER_SHAREHOLDER"
    MULTIPLE = "MULTIPLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DebtRanking(StrEnum):
    """Ranking of a debt instrument in the capital structure."""

    SENIOR_UNSECURED = "SENIOR_UNSECURED"
    SENIOR_SECURED = "SENIOR_SECURED"
    SUBORDINATED = "SUBORDINATED"
    HYBRID = "HYBRID"


class RateType(StrEnum):
    """Interest-rate convention for a debt instrument."""

    FIXED = "FIXED"
    FLOATING = "FLOATING"
    OTHER = "OTHER"


class DebtDistribution(StrEnum):
    """Distribution format for investment-grade debt."""

    PUBLIC_BENCHMARK = "PUBLIC_BENCHMARK"
    PUBLIC_NON_BENCHMARK = "PUBLIC_NON_BENCHMARK"
    PRIVATE_PLACEMENT = "PRIVATE_PLACEMENT"
    OTHER = "OTHER"


class DebtPurpose(StrEnum):
    """Primary stated use of proceeds for investment-grade debt."""

    GENERAL_CORPORATE = "GENERAL_CORPORATE"
    REFINANCING = "REFINANCING"
    ACQUISITION = "ACQUISITION"
    CAPEX = "CAPEX"
    LIABILITY_MANAGEMENT = "LIABILITY_MANAGEMENT"
    ESG_OR_GREEN_USE = "ESG_OR_GREEN_USE"
    OTHER = "OTHER"


class LeveragedFinanceInstrument(StrEnum):
    """Primary leveraged-finance instrument types."""

    HIGH_YIELD_BOND = "HIGH_YIELD_BOND"
    TERM_LOAN_B = "TERM_LOAN_B"
    TERM_LOAN_A = "TERM_LOAN_A"
    RCF = "RCF"
    BRIDGE = "BRIDGE"
    OTHER_LEVERAGED_LOAN = "OTHER_LEVERAGED_LOAN"


class LeveragedFinancePurpose(StrEnum):
    """Primary financing purpose for leveraged-finance transactions."""

    ACQUISITION = "ACQUISITION"
    REFINANCING = "REFINANCING"
    DIVIDEND_RECAP = "DIVIDEND_RECAP"
    GENERAL_CORPORATE = "GENERAL_CORPORATE"
    LIABILITY_MANAGEMENT = "LIABILITY_MANAGEMENT"
    OTHER = "OTHER"


class OwnershipType(StrEnum):
    """Issuer ownership classification relevant to leveraged finance."""

    SPONSOR_BACKED = "SPONSOR_BACKED"
    CORPORATE = "CORPORATE"
    OTHER = "OTHER"


class SecurityType(StrEnum):
    """Security classification for debt instruments."""

    SECURED = "SECURED"
    UNSECURED = "UNSECURED"
