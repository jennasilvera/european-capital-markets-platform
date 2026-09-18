"""Canonical market-series identities and market-data validation."""

from dataclasses import dataclass
from decimal import Decimal
from re import fullmatch

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MarketSeriesType,
)
from european_capital_markets.domain.terms import validate_term_observation


def _require_non_blank(
    value: str,
    field_name: str,
) -> None:
    if not value.strip():
        raise ValueError(
            f"{field_name} must not be blank."
        )


def _require_optional_non_blank(
    value: str | None,
    field_name: str,
) -> None:
    if value is not None:
        _require_non_blank(value, field_name)


def _require_currency_code(
    value: str,
    field_name: str,
) -> None:
    if fullmatch(r"[A-Z]{3}", value) is None:
        raise ValueError(
            f"{field_name} must be a three-letter uppercase currency code."
        )


def _require_positive_tenor_months(
    value: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            "tenor_months must be an integer."
        )
    if value <= 0:
        raise ValueError(
            "tenor_months must be strictly positive."
        )


@dataclass(frozen=True, slots=True)
class MarketSeriesRecord:
    """Stable generic identity for one canonical market-data series."""

    market_series_id: str
    series_type: MarketSeriesType
    series_label: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )

        if not isinstance(self.series_type, MarketSeriesType):
            raise TypeError(
                "series_type must be a MarketSeriesType."
            )

        if self.series_label is not None:
            _require_non_blank(
                self.series_label,
                "series_label",
            )


@dataclass(frozen=True, slots=True)
class FXReferenceRateDefinitionRecord:
    """FX-specific identity dimensions for one reference-rate series."""

    market_series_id: str
    base_currency: str
    quote_currency: str
    convention_ref: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_currency_code(
            self.base_currency,
            "base_currency",
        )
        _require_currency_code(
            self.quote_currency,
            "quote_currency",
        )
        _require_non_blank(
            self.convention_ref,
            "convention_ref",
        )

        if self.base_currency == self.quote_currency:
            raise ValueError(
                "FX base_currency and quote_currency must differ."
            )


@dataclass(frozen=True, slots=True)
class PolicyRateDefinitionRecord:
    """Identity dimensions for one central-bank policy-rate series."""

    market_series_id: str
    authority: str
    jurisdiction: str
    currency: str
    rate_name: str
    convention_ref: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_non_blank(self.authority, "authority")
        _require_non_blank(self.jurisdiction, "jurisdiction")
        _require_currency_code(self.currency, "currency")
        _require_non_blank(self.rate_name, "rate_name")
        _require_non_blank(
            self.convention_ref,
            "convention_ref",
        )


@dataclass(frozen=True, slots=True)
class GovernmentYieldDefinitionRecord:
    """Identity dimensions for one sovereign benchmark-yield series."""

    market_series_id: str
    sovereign: str
    jurisdiction: str
    currency: str
    tenor_months: int
    benchmark_ref: str
    convention_ref: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_non_blank(self.sovereign, "sovereign")
        _require_non_blank(self.jurisdiction, "jurisdiction")
        _require_currency_code(self.currency, "currency")
        _require_positive_tenor_months(self.tenor_months)
        _require_non_blank(
            self.benchmark_ref,
            "benchmark_ref",
        )
        _require_non_blank(
            self.convention_ref,
            "convention_ref",
        )


@dataclass(frozen=True, slots=True)
class SwapRateDefinitionRecord:
    """Identity dimensions for one fixed-versus-floating swap-rate series."""

    market_series_id: str
    currency: str
    tenor_months: int
    floating_rate_ref: str
    fixed_leg_convention_ref: str
    convention_ref: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_currency_code(self.currency, "currency")
        _require_positive_tenor_months(self.tenor_months)
        _require_non_blank(
            self.floating_rate_ref,
            "floating_rate_ref",
        )
        _require_non_blank(
            self.fixed_leg_convention_ref,
            "fixed_leg_convention_ref",
        )
        _require_non_blank(
            self.convention_ref,
            "convention_ref",
        )


@dataclass(frozen=True, slots=True)
class CreditSpreadDefinitionRecord:
    """Identity dimensions for one defined credit-spread benchmark."""

    market_series_id: str
    benchmark_family: str
    currency: str
    credit_universe: str
    spread_measure: str
    convention_ref: str
    rating_segment: str | None = None
    sector_segment: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_non_blank(
            self.benchmark_family,
            "benchmark_family",
        )
        _require_currency_code(self.currency, "currency")
        _require_non_blank(
            self.credit_universe,
            "credit_universe",
        )
        _require_non_blank(
            self.spread_measure,
            "spread_measure",
        )
        _require_non_blank(
            self.convention_ref,
            "convention_ref",
        )
        _require_optional_non_blank(
            self.rating_segment,
            "rating_segment",
        )
        _require_optional_non_blank(
            self.sector_segment,
            "sector_segment",
        )


@dataclass(frozen=True, slots=True)
class EquityIndexDefinitionRecord:
    """Identity dimensions for one defined equity-index series."""

    market_series_id: str
    index_name: str
    universe: str
    index_variant_ref: str
    methodology_ref: str

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_non_blank(self.index_name, "index_name")
        _require_non_blank(self.universe, "universe")
        _require_non_blank(
            self.index_variant_ref,
            "index_variant_ref",
        )
        _require_non_blank(
            self.methodology_ref,
            "methodology_ref",
        )


@dataclass(frozen=True, slots=True)
class VolatilityIndexDefinitionRecord:
    """Identity dimensions for one defined volatility-index series."""

    market_series_id: str
    index_name: str
    underlying_ref: str
    methodology_ref: str
    horizon_days: int | None = None

    def __post_init__(self) -> None:
        validate_identifier(
            self.market_series_id,
            EntityType.MARKET_SERIES,
        )
        _require_non_blank(self.index_name, "index_name")
        _require_non_blank(
            self.underlying_ref,
            "underlying_ref",
        )
        _require_non_blank(
            self.methodology_ref,
            "methodology_ref",
        )

        if self.horizon_days is not None:
            if (
                isinstance(self.horizon_days, bool)
                or not isinstance(self.horizon_days, int)
            ):
                raise TypeError(
                    "horizon_days must be an integer when provided."
                )
            if self.horizon_days <= 0:
                raise ValueError(
                    "horizon_days must be strictly positive when provided."
                )


MarketSeriesDefinitionRecord = (
    FXReferenceRateDefinitionRecord
    | PolicyRateDefinitionRecord
    | GovernmentYieldDefinitionRecord
    | SwapRateDefinitionRecord
    | CreditSpreadDefinitionRecord
    | EquityIndexDefinitionRecord
    | VolatilityIndexDefinitionRecord
)


_EXPECTED_DEFINITION_TYPE: dict[
    MarketSeriesType,
    type[MarketSeriesDefinitionRecord],
] = {
    MarketSeriesType.FX_REFERENCE_RATE: FXReferenceRateDefinitionRecord,
    MarketSeriesType.POLICY_RATE: PolicyRateDefinitionRecord,
    MarketSeriesType.GOVERNMENT_YIELD: GovernmentYieldDefinitionRecord,
    MarketSeriesType.SWAP_RATE: SwapRateDefinitionRecord,
    MarketSeriesType.CREDIT_SPREAD: CreditSpreadDefinitionRecord,
    MarketSeriesType.EQUITY_INDEX: EquityIndexDefinitionRecord,
    MarketSeriesType.VOLATILITY_INDEX: VolatilityIndexDefinitionRecord,
}


_EXPECTED_OBSERVATION_FIELD: dict[
    MarketSeriesType,
    str,
] = {
    MarketSeriesType.FX_REFERENCE_RATE: "market_series.fx_rate",
    MarketSeriesType.POLICY_RATE: "market_series.rate_percent",
    MarketSeriesType.GOVERNMENT_YIELD: "market_series.yield_percent",
    MarketSeriesType.SWAP_RATE: "market_series.rate_percent",
    MarketSeriesType.CREDIT_SPREAD: "market_series.spread_bps",
    MarketSeriesType.EQUITY_INDEX: "market_series.index_level",
    MarketSeriesType.VOLATILITY_INDEX: "market_series.volatility_level",
}


def validate_market_series_bundle(
    market_series: tuple[MarketSeriesRecord, ...],
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ] = (),
    policy_rates: tuple[
        PolicyRateDefinitionRecord,
        ...,
    ] = (),
    government_yields: tuple[
        GovernmentYieldDefinitionRecord,
        ...,
    ] = (),
    swap_rates: tuple[
        SwapRateDefinitionRecord,
        ...,
    ] = (),
    credit_spreads: tuple[
        CreditSpreadDefinitionRecord,
        ...,
    ] = (),
    equity_indices: tuple[
        EquityIndexDefinitionRecord,
        ...,
    ] = (),
    volatility_indices: tuple[
        VolatilityIndexDefinitionRecord,
        ...,
    ] = (),
) -> None:
    """Validate generic identities and type-specific series definitions."""

    series_by_id: dict[str, MarketSeriesRecord] = {}

    for series in market_series:
        if series.market_series_id in series_by_id:
            raise ValueError(
                f"Duplicate identifier: {series.market_series_id!r}"
            )

        series_by_id[series.market_series_id] = series

    definition_groups: tuple[
        tuple[MarketSeriesDefinitionRecord, ...],
        ...,
    ] = (
        fx_reference_rates,
        policy_rates,
        government_yields,
        swap_rates,
        credit_spreads,
        equity_indices,
        volatility_indices,
    )

    definition_by_series_id: dict[
        str,
        MarketSeriesDefinitionRecord,
    ] = {}

    semantic_keys_by_type: dict[
        MarketSeriesType,
        set[tuple[object, ...]],
    ] = {
        series_type: set()
        for series_type in MarketSeriesType
    }

    definitions_by_series_id: dict[
        str,
        list[MarketSeriesDefinitionRecord],
    ] = {}

    for definitions in definition_groups:
        for definition in definitions:
            definitions_by_series_id.setdefault(
                definition.market_series_id,
                [],
            ).append(definition)

    for series_id, definitions in definitions_by_series_id.items():
        try:
            series = series_by_id[series_id]
        except KeyError as exc:
            raise ValueError(
                "Market-series definition references unknown "
                f"market series {series_id!r}."
            ) from exc

        if len(definitions) > 1:
            if all(
                isinstance(
                    definition,
                    FXReferenceRateDefinitionRecord,
                )
                for definition in definitions
            ):
                raise ValueError(
                    "Duplicate FX reference-rate definition for "
                    f"{series_id!r}."
                )

            raise ValueError(
                "Market series has multiple type-specific "
                f"definitions: {series_id!r}."
            )

        definition = definitions[0]

        expected_definition_type = _EXPECTED_DEFINITION_TYPE[
            series.series_type
        ]

        if not isinstance(
            definition,
            expected_definition_type,
        ):
            raise ValueError(
                f"{series.series_type.value} market series "
                "has an incompatible type-specific definition."
            )

        semantic_key = _definition_semantic_key(
            definition
        )

        semantic_keys = semantic_keys_by_type[
            series.series_type
        ]

        if semantic_key in semantic_keys:
            if (
                series.series_type
                is MarketSeriesType.FX_REFERENCE_RATE
            ):
                raise ValueError(
                    "Duplicate canonical FX reference-rate identity."
                )

            raise ValueError(
                "Duplicate canonical "
                f"{series.series_type.value} identity."
            )

        semantic_keys.add(semantic_key)
        definition_by_series_id[series_id] = definition

    for series in market_series:
        if series.market_series_id not in definition_by_series_id:
            raise ValueError(
                f"{series.series_type.value} market series requires "
                "exactly one type-specific definition."
            )


def validate_market_data_bundle(
    market_series: tuple[MarketSeriesRecord, ...],
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ] = (),
    observations: tuple[ObservationRecord, ...] = (),
    *,
    policy_rates: tuple[
        PolicyRateDefinitionRecord,
        ...,
    ] = (),
    government_yields: tuple[
        GovernmentYieldDefinitionRecord,
        ...,
    ] = (),
    swap_rates: tuple[
        SwapRateDefinitionRecord,
        ...,
    ] = (),
    credit_spreads: tuple[
        CreditSpreadDefinitionRecord,
        ...,
    ] = (),
    equity_indices: tuple[
        EquityIndexDefinitionRecord,
        ...,
    ] = (),
    volatility_indices: tuple[
        VolatilityIndexDefinitionRecord,
        ...,
    ] = (),
) -> None:
    """Validate market-series definitions and governed observations."""

    validate_market_series_bundle(
        market_series,
        fx_reference_rates,
        policy_rates,
        government_yields,
        swap_rates,
        credit_spreads,
        equity_indices,
        volatility_indices,
    )

    series_by_id = {
        series.market_series_id: series
        for series in market_series
    }

    for observation in observations:
        is_market_subject = (
            observation.subject_type
            is EntityType.MARKET_SERIES
        )
        is_market_field = observation.field_name.startswith(
            "market_series."
        )

        if not is_market_subject and not is_market_field:
            continue

        validate_term_observation(observation)

        if not is_market_subject:
            continue

        try:
            series = series_by_id[
                observation.subject_id
            ]
        except KeyError as exc:
            raise ValueError(
                "Unknown market-series reference: "
                f"{observation.subject_id!r}"
            ) from exc

        expected_field = _EXPECTED_OBSERVATION_FIELD[
            series.series_type
        ]

        if observation.field_name != expected_field:
            raise ValueError(
                f"{series.series_type.value} market series requires "
                f"observation field {expected_field!r}."
            )

        _validate_market_observation_value(
            observation,
            series.series_type,
        )


def _definition_semantic_key(
    definition: MarketSeriesDefinitionRecord,
) -> tuple[object, ...]:
    if isinstance(
        definition,
        FXReferenceRateDefinitionRecord,
    ):
        return (
            definition.base_currency,
            definition.quote_currency,
            definition.convention_ref,
        )

    if isinstance(
        definition,
        PolicyRateDefinitionRecord,
    ):
        return (
            definition.authority,
            definition.jurisdiction,
            definition.currency,
            definition.rate_name,
            definition.convention_ref,
        )

    if isinstance(
        definition,
        GovernmentYieldDefinitionRecord,
    ):
        return (
            definition.sovereign,
            definition.jurisdiction,
            definition.currency,
            definition.tenor_months,
            definition.benchmark_ref,
            definition.convention_ref,
        )

    if isinstance(
        definition,
        SwapRateDefinitionRecord,
    ):
        return (
            definition.currency,
            definition.tenor_months,
            definition.floating_rate_ref,
            definition.fixed_leg_convention_ref,
            definition.convention_ref,
        )

    if isinstance(
        definition,
        CreditSpreadDefinitionRecord,
    ):
        return (
            definition.benchmark_family,
            definition.currency,
            definition.credit_universe,
            definition.rating_segment,
            definition.sector_segment,
            definition.spread_measure,
            definition.convention_ref,
        )

    if isinstance(
        definition,
        EquityIndexDefinitionRecord,
    ):
        return (
            definition.index_name,
            definition.universe,
            definition.index_variant_ref,
            definition.methodology_ref,
        )

    if isinstance(
        definition,
        VolatilityIndexDefinitionRecord,
    ):
        return (
            definition.index_name,
            definition.underlying_ref,
            definition.horizon_days,
            definition.methodology_ref,
        )

    raise TypeError(
        "Unsupported market-series definition record."
    )


def _validate_market_observation_value(
    observation: ObservationRecord,
    series_type: MarketSeriesType,
) -> None:
    if observation.missing_state is not None:
        return

    if not isinstance(observation.value, Decimal):
        raise TypeError(
            "Populated market-series observations require Decimal values."
        )

    if (
        series_type
        is MarketSeriesType.FX_REFERENCE_RATE
        and observation.value <= 0
    ):
        raise ValueError(
            "FX rate must be strictly positive."
        )

    if (
        series_type
        is MarketSeriesType.EQUITY_INDEX
        and observation.value <= 0
    ):
        raise ValueError(
            "Equity-index level must be strictly positive."
        )

    if (
        series_type
        is MarketSeriesType.VOLATILITY_INDEX
        and observation.value < 0
    ):
        raise ValueError(
            "Volatility-index level must be non-negative."
        )
