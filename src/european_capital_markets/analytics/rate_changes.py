"""Pure two-date changes in governed percentage-point market levels."""

from dataclasses import dataclass
from datetime import date
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from enum import StrEnum

from european_capital_markets.analytics._decimal import canonical_decimal
from european_capital_markets.analytics.market_selection import (
    EXACT_DATE_POLICY_VERSION,
    ExactDateMarketRequest,
    MarketSelectionResult,
    MarketSelectionStatus,
    select_market_observation,
)
from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.taxonomy import MarketSeriesType, ValueClass

RATE_CHANGE_METHODOLOGY_VERSION = "market-rate-change-v1"
RATE_CHANGE_DECIMAL_POLICY_REF = "market-rate-change-decimal-38-v1"
_RATE_FAMILIES = frozenset(
    {
        MarketSeriesType.POLICY_RATE,
        MarketSeriesType.GOVERNMENT_YIELD,
        MarketSeriesType.SWAP_RATE,
    }
)


class RateChangeStatus(StrEnum):
    CALCULATED = "CALCULATED"
    BLOCKED = "BLOCKED"


class RateChangeBlockReason(StrEnum):
    ARITHMETIC_NOT_REPRESENTABLE = "ARITHMETIC_NOT_REPRESENTABLE"
    CURRENT_SELECTION_BLOCKED = "CURRENT_SELECTION_BLOCKED"
    PRIOR_SELECTION_BLOCKED = "PRIOR_SELECTION_BLOCKED"


@dataclass(frozen=True, slots=True)
class RateChangeRequest:
    market_series_id: str
    field_name: str
    prior_date: date
    current_date: date
    methodology_version: str = RATE_CHANGE_METHODOLOGY_VERSION
    selection_policy_version: str = EXACT_DATE_POLICY_VERSION

    def __post_init__(self) -> None:
        # Reuse exact-date request semantics, including strict date-only values
        # and fail-closed policy versions, rather than maintaining a second rule.
        ExactDateMarketRequest(
            self.market_series_id,
            self.field_name,
            self.prior_date,
            self.selection_policy_version,
        )
        ExactDateMarketRequest(
            self.market_series_id,
            self.field_name,
            self.current_date,
            self.selection_policy_version,
        )
        if self.prior_date >= self.current_date:
            raise ValueError("prior_date must be before current_date.")
        if self.methodology_version != RATE_CHANGE_METHODOLOGY_VERSION:
            raise ValueError(
                f"Unsupported rate-change methodology: {self.methodology_version!r}."
            )


@dataclass(frozen=True, slots=True)
class RateChangeResult:
    """Calculated change or explicit block with both endpoint roles intact.

    Nested selections retain the economic definition, exact original records,
    eligibility diagnostics, and full input/evidence/source closure. Success is
    not canonical verification or release approval. No canonical IDs are issued.
    """

    request: RateChangeRequest
    prior: MarketSelectionResult
    current: MarketSelectionResult
    status: RateChangeStatus
    value: Decimal | None
    block_reasons: tuple[RateChangeBlockReason, ...]
    arithmetic_signals: tuple[str, ...] = ()
    unit: str = "BASIS_POINTS"
    decimal_policy_ref: str = RATE_CHANGE_DECIMAL_POLICY_REF

    @property
    def value_class(self) -> ValueClass | None:
        if self.status is RateChangeStatus.BLOCKED:
            return None
        return ValueClass.CALCULATED

    @property
    def input_observation_ids(self) -> tuple[str, ...]:
        if self.status is RateChangeStatus.BLOCKED:
            return ()
        # Endpoint order is explicit; ID sorting inside each selection is not
        # chronology or evidentiary priority. Both dates use the same series.
        return (
            self.prior.supporting_observation_ids
            + self.current.supporting_observation_ids
        )


def calculate_rate_change(
    dataset: CanonicalDataset,
    request: RateChangeRequest,
) -> RateChangeResult:
    """Calculate (current_percent - prior_percent) * 100 without silent rounding.

    Obtain both selections from the same supplied dataset through the existing
    public validation boundary. Do not accept caller-built selection results,
    retrieve missing values, or perform independent database/catalog reads.
    """

    if not isinstance(request, RateChangeRequest):
        raise TypeError("request must be a RateChangeRequest.")
    prior = select_market_observation(
        dataset,
        ExactDateMarketRequest(
            request.market_series_id,
            request.field_name,
            request.prior_date,
            request.selection_policy_version,
        ),
    )
    if prior.market_series.series_type not in _RATE_FAMILIES:
        raise ValueError(
            "Rate changes support POLICY_RATE, GOVERNMENT_YIELD, and SWAP_RATE only."
        )
    current = select_market_observation(
        dataset,
        ExactDateMarketRequest(
            request.market_series_id,
            request.field_name,
            request.current_date,
            request.selection_policy_version,
        ),
    )
    reasons: set[RateChangeBlockReason] = set()
    if prior.status is MarketSelectionStatus.BLOCKED:
        reasons.add(RateChangeBlockReason.PRIOR_SELECTION_BLOCKED)
    if current.status is MarketSelectionStatus.BLOCKED:
        reasons.add(RateChangeBlockReason.CURRENT_SELECTION_BLOCKED)

    value = None
    signals: tuple[str, ...] = ()
    if not reasons:
        # All settings, including flags/traps, are independent of caller state
        # and mutable decimal.DefaultContext. Rounded without Inexact can be
        # exact (discarded zeros); presentation quantization is never applied.
        context = Context(
            prec=38,
            rounding=ROUND_HALF_EVEN,
            Emin=-999999,
            Emax=999999,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Inexact],
        )
        with localcontext(context) as calculation_context:
            try:
                raw_value = (current.value - prior.value) * Decimal("100")
            except DecimalException:
                reasons.add(RateChangeBlockReason.ARITHMETIC_NOT_REPRESENTABLE)
                signals = tuple(
                    sorted(
                        signal.__name__
                        for signal, raised in calculation_context.flags.items()
                        if raised
                    )
                )
            else:
                value = canonical_decimal(raw_value)
    return RateChangeResult(
        request=request,
        prior=prior,
        current=current,
        status=RateChangeStatus.BLOCKED if reasons else RateChangeStatus.CALCULATED,
        value=value,
        block_reasons=tuple(sorted(reasons)),
        arithmetic_signals=signals,
    )
