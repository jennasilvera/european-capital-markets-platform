from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
    validate_market_data_bundle,
    validate_market_series_bundle,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MarketSeriesType,
    MissingDataState,
    ValueClass,
    VerificationState,
)


def _series(
    *,
    market_series_id: str = "MKS000000001",
    series_label: str | None = "EUR/GBP daily reference rate",
) -> MarketSeriesRecord:
    return MarketSeriesRecord(
        market_series_id=market_series_id,
        series_type=MarketSeriesType.FX_REFERENCE_RATE,
        series_label=series_label,
    )


def _fx_definition(
    *,
    market_series_id: str = "MKS000000001",
    base_currency: str = "EUR",
    quote_currency: str = "GBP",
    convention_ref: str = "market-data/fx/reference-rate-v1",
) -> FXReferenceRateDefinitionRecord:
    return FXReferenceRateDefinitionRecord(
        market_series_id=market_series_id,
        base_currency=base_currency,
        quote_currency=quote_currency,
        convention_ref=convention_ref,
    )


def _fx_rate(
    *,
    observation_id: str = "OBS000000001",
    market_series_id: str = "MKS000000001",
    value: Decimal = Decimal("0.8650"),
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=EntityType.MARKET_SERIES,
        subject_id=market_series_id,
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://market-data-assumption",
    )


def _validate(
    *,
    series: tuple[MarketSeriesRecord, ...] | None = None,
    definitions: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ]
    | None = None,
    observations: tuple[ObservationRecord, ...] = (),
) -> None:
    validate_market_data_bundle(
        market_series=series or (_series(),),
        fx_reference_rates=definitions or (_fx_definition(),),
        observations=observations,
    )


def test_valid_generic_market_series_identity() -> None:
    series = _series()

    assert (
        series.series_type
        is MarketSeriesType.FX_REFERENCE_RATE
    )
    assert series.market_series_id == "MKS000000001"


def test_market_series_identifier_namespace_is_enforced() -> None:
    with pytest.raises(ValueError, match="not MARKET_SERIES"):
        _series(
            market_series_id="INS000000001",
        )


def test_series_label_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="series_label"):
        _series(
            series_label="   ",
        )


def test_base_currency_must_be_uppercase_three_letter_code() -> None:
    with pytest.raises(ValueError, match="base_currency"):
        _fx_definition(
            base_currency="eur",
        )


def test_quote_currency_must_be_uppercase_three_letter_code() -> None:
    with pytest.raises(ValueError, match="quote_currency"):
        _fx_definition(
            quote_currency="pounds",
        )


def test_fx_pair_must_use_different_currencies() -> None:
    with pytest.raises(ValueError, match="must differ"):
        _fx_definition(
            base_currency="EUR",
            quote_currency="EUR",
        )


def test_convention_reference_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="convention_ref"):
        _fx_definition(
            convention_ref="   ",
        )


def test_bundle_rejects_duplicate_market_series_identifier() -> None:
    with pytest.raises(ValueError, match="Duplicate identifier"):
        validate_market_series_bundle(
            market_series=(
                _series(),
                _series(),
            ),
            fx_reference_rates=(
                _fx_definition(),
            ),
        )


def test_bundle_rejects_duplicate_fx_definition_for_series() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate FX reference-rate definition",
    ):
        validate_market_series_bundle(
            market_series=(
                _series(),
            ),
            fx_reference_rates=(
                _fx_definition(),
                _fx_definition(),
            ),
        )


def test_fx_series_requires_definition() -> None:
    with pytest.raises(
        ValueError,
        match="requires exactly one",
    ):
        validate_market_series_bundle(
            market_series=(
                _series(),
            ),
            fx_reference_rates=(),
        )


def test_fx_definition_rejects_unknown_market_series() -> None:
    with pytest.raises(
        ValueError,
        match="references unknown market series",
    ):
        validate_market_series_bundle(
            market_series=(
                _series(
                    market_series_id="MKS000000001",
                ),
            ),
            fx_reference_rates=(
                _fx_definition(
                    market_series_id="MKS000000002",
                ),
            ),
        )


def test_duplicate_pair_and_convention_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate canonical FX reference-rate identity",
    ):
        validate_market_series_bundle(
            market_series=(
                _series(
                    market_series_id="MKS000000001",
                ),
                _series(
                    market_series_id="MKS000000002",
                    series_label="Second EUR/GBP series",
                ),
            ),
            fx_reference_rates=(
                _fx_definition(
                    market_series_id="MKS000000001",
                ),
                _fx_definition(
                    market_series_id="MKS000000002",
                ),
            ),
        )


def test_same_pair_different_convention_is_valid() -> None:
    validate_market_series_bundle(
        market_series=(
            _series(
                market_series_id="MKS000000001",
            ),
            _series(
                market_series_id="MKS000000002",
                series_label="EUR/GBP alternate reference",
            ),
        ),
        fx_reference_rates=(
            _fx_definition(
                market_series_id="MKS000000001",
                convention_ref=(
                    "market-data/fx/reference-rate-v1"
                ),
            ),
            _fx_definition(
                market_series_id="MKS000000002",
                convention_ref=(
                    "market-data/fx/alternate-reference-v1"
                ),
            ),
        ),
    )


def test_reverse_pair_is_distinct_identity() -> None:
    validate_market_series_bundle(
        market_series=(
            _series(
                market_series_id="MKS000000001",
            ),
            _series(
                market_series_id="MKS000000002",
                series_label="GBP/EUR daily reference rate",
            ),
        ),
        fx_reference_rates=(
            _fx_definition(
                market_series_id="MKS000000001",
                base_currency="EUR",
                quote_currency="GBP",
            ),
            _fx_definition(
                market_series_id="MKS000000002",
                base_currency="GBP",
                quote_currency="EUR",
            ),
        ),
    )


def test_valid_positive_fx_rate() -> None:
    _validate(
        observations=(_fx_rate(),),
    )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("0"),
        Decimal("-0.01"),
    ],
)
def test_fx_rate_must_be_strictly_positive(
    value: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="strictly positive",
    ):
        _validate(
            observations=(
                _fx_rate(value=value),
            ),
        )


def test_market_data_bundle_rejects_unknown_series_reference() -> None:
    with pytest.raises(
        ValueError,
        match="Unknown market-series reference",
    ):
        _validate(
            observations=(
                _fx_rate(
                    market_series_id="MKS000000002",
                ),
            ),
        )


def test_fx_rate_rejects_currency_metadata() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.8650"),
        value_class=ValueClass.ASSUMED,
        currency="GBP",
        derivation_ref="test://market-data-assumption",
    )

    with pytest.raises(
        ValueError,
        match="does not permit currency",
    ):
        _validate(
            observations=(observation,),
        )


def test_fx_rate_rejects_unit_metadata() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.8650"),
        value_class=ValueClass.ASSUMED,
        unit="GBP_PER_EUR",
        derivation_ref="test://market-data-assumption",
    )

    with pytest.raises(
        ValueError,
        match="does not permit unit",
    ):
        _validate(
            observations=(observation,),
        )


def test_missing_fx_rate_is_valid() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    _validate(
        observations=(observation,),
    )


def test_market_series_field_rejects_non_market_subject() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.8650"),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://market-data-assumption",
    )

    with pytest.raises(
        ValueError,
        match="requires subject type MARKET_SERIES",
    ):
        _validate(
            observations=(observation,),
        )


def _phase1_series(
    series_type: MarketSeriesType,
    *,
    market_series_id: str = "MKS000000100",
) -> MarketSeriesRecord:
    return MarketSeriesRecord(
        market_series_id=market_series_id,
        series_type=series_type,
        series_label=f"Phase 1 {series_type.value}",
    )


def _phase1_policy_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> PolicyRateDefinitionRecord:
    return PolicyRateDefinitionRecord(
        market_series_id=market_series_id,
        authority="European Central Bank",
        jurisdiction="Euro Area",
        currency="EUR",
        rate_name="Deposit Facility Rate",
        convention_ref="market-data/ecb/policy-rate-v1",
    )


def _phase1_government_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> GovernmentYieldDefinitionRecord:
    return GovernmentYieldDefinitionRecord(
        market_series_id=market_series_id,
        sovereign="Federal Republic of Germany",
        jurisdiction="Germany",
        currency="EUR",
        tenor_months=120,
        benchmark_ref="German sovereign 10Y benchmark",
        convention_ref="market-data/government-yield-v1",
    )


def _phase1_swap_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> SwapRateDefinitionRecord:
    return SwapRateDefinitionRecord(
        market_series_id=market_series_id,
        currency="EUR",
        tenor_months=60,
        floating_rate_ref="EURIBOR-6M",
        fixed_leg_convention_ref="EUR-IRS-fixed-leg-v1",
        convention_ref="market-data/swap-rate-v1",
    )


def _phase1_credit_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> CreditSpreadDefinitionRecord:
    return CreditSpreadDefinitionRecord(
        market_series_id=market_series_id,
        benchmark_family="European Corporate Credit",
        currency="EUR",
        credit_universe="Investment Grade",
        spread_measure="OAS",
        convention_ref="market-data/credit-spread-v1",
    )


def _phase1_equity_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> EquityIndexDefinitionRecord:
    return EquityIndexDefinitionRecord(
        market_series_id=market_series_id,
        index_name="STOXX Europe 600",
        universe="Europe",
        index_variant_ref="PRICE",
        methodology_ref="market-data/equity-index-v1",
    )


def _phase1_volatility_definition(
    *,
    market_series_id: str = "MKS000000100",
) -> VolatilityIndexDefinitionRecord:
    return VolatilityIndexDefinitionRecord(
        market_series_id=market_series_id,
        index_name="European Equity Volatility",
        underlying_ref="STOXX Europe 600",
        methodology_ref="market-data/volatility-index-v1",
        horizon_days=30,
    )


def _phase1_observation(
    field_name: str,
    *,
    market_series_id: str = "MKS000000100",
    value: Decimal = Decimal("2.5"),
    unit: str | None = None,
) -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000100",
        subject_type=EntityType.MARKET_SERIES,
        subject_id=market_series_id,
        field_name=field_name,
        as_of_date=date(2026, 9, 18),
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=ValueClass.ASSUMED,
        unit=unit,
        derivation_ref="test://phase1-market",
    )


@pytest.mark.parametrize(
    ("series_type", "definition_name", "definition"),
    [
        (
            MarketSeriesType.POLICY_RATE,
            "policy_rates",
            _phase1_policy_definition(),
        ),
        (
            MarketSeriesType.GOVERNMENT_YIELD,
            "government_yields",
            _phase1_government_definition(),
        ),
        (
            MarketSeriesType.SWAP_RATE,
            "swap_rates",
            _phase1_swap_definition(),
        ),
        (
            MarketSeriesType.CREDIT_SPREAD,
            "credit_spreads",
            _phase1_credit_definition(),
        ),
        (
            MarketSeriesType.EQUITY_INDEX,
            "equity_indices",
            _phase1_equity_definition(),
        ),
        (
            MarketSeriesType.VOLATILITY_INDEX,
            "volatility_indices",
            _phase1_volatility_definition(),
        ),
    ],
)
def test_phase1_market_series_accepts_matching_definition(
    series_type: MarketSeriesType,
    definition_name: str,
    definition: object,
) -> None:
    validate_market_series_bundle(
        (_phase1_series(series_type),),
        **{
            definition_name: (definition,),
        },  # type: ignore[arg-type]
    )


def test_phase1_series_requires_type_specific_definition() -> None:
    with pytest.raises(
        ValueError,
        match="requires exactly one type-specific definition",
    ):
        validate_market_series_bundle(
            (_phase1_series(MarketSeriesType.POLICY_RATE),),
        )


def test_phase1_series_rejects_incompatible_definition() -> None:
    incompatible = FXReferenceRateDefinitionRecord(
        market_series_id="MKS000000100",
        base_currency="EUR",
        quote_currency="GBP",
        convention_ref="market-data/fx/reference-rate-v1",
    )

    with pytest.raises(
        ValueError,
        match="incompatible type-specific definition",
    ):
        validate_market_series_bundle(
            (_phase1_series(MarketSeriesType.POLICY_RATE),),
            fx_reference_rates=(incompatible,),
        )


def test_phase1_series_rejects_multiple_definition_families() -> None:
    incompatible = FXReferenceRateDefinitionRecord(
        market_series_id="MKS000000100",
        base_currency="EUR",
        quote_currency="GBP",
        convention_ref="market-data/fx/reference-rate-v1",
    )

    with pytest.raises(
        ValueError,
        match="multiple type-specific definitions",
    ):
        validate_market_series_bundle(
            (_phase1_series(MarketSeriesType.POLICY_RATE),),
            fx_reference_rates=(incompatible,),
            policy_rates=(_phase1_policy_definition(),),
        )


def test_phase1_duplicate_policy_rate_identity_is_rejected() -> None:
    first = _phase1_policy_definition(
        market_series_id="MKS000000100",
    )
    second = _phase1_policy_definition(
        market_series_id="MKS000000101",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate canonical POLICY_RATE identity",
    ):
        validate_market_series_bundle(
            (
                _phase1_series(
                    MarketSeriesType.POLICY_RATE,
                    market_series_id="MKS000000100",
                ),
                _phase1_series(
                    MarketSeriesType.POLICY_RATE,
                    market_series_id="MKS000000101",
                ),
            ),
            policy_rates=(first, second),
        )


@pytest.mark.parametrize(
    ("series_type", "field_name", "unit", "definition_name", "definition"),
    [
        (
            MarketSeriesType.POLICY_RATE,
            "market_series.rate_percent",
            "PERCENT",
            "policy_rates",
            _phase1_policy_definition(),
        ),
        (
            MarketSeriesType.GOVERNMENT_YIELD,
            "market_series.yield_percent",
            "PERCENT",
            "government_yields",
            _phase1_government_definition(),
        ),
        (
            MarketSeriesType.SWAP_RATE,
            "market_series.rate_percent",
            "PERCENT",
            "swap_rates",
            _phase1_swap_definition(),
        ),
        (
            MarketSeriesType.CREDIT_SPREAD,
            "market_series.spread_bps",
            "BASIS_POINTS",
            "credit_spreads",
            _phase1_credit_definition(),
        ),
        (
            MarketSeriesType.EQUITY_INDEX,
            "market_series.index_level",
            "INDEX_POINTS",
            "equity_indices",
            _phase1_equity_definition(),
        ),
        (
            MarketSeriesType.VOLATILITY_INDEX,
            "market_series.volatility_level",
            "INDEX_POINTS",
            "volatility_indices",
            _phase1_volatility_definition(),
        ),
    ],
)
def test_phase1_series_accepts_its_governed_observation_field(
    series_type: MarketSeriesType,
    field_name: str,
    unit: str,
    definition_name: str,
    definition: object,
) -> None:
    validate_market_data_bundle(
        (_phase1_series(series_type),),
        observations=(
            _phase1_observation(
                field_name,
                unit=unit,
            ),
        ),
        **{
            definition_name: (definition,),
        },  # type: ignore[arg-type]
    )


def test_phase1_series_rejects_wrong_governed_field() -> None:
    with pytest.raises(
        ValueError,
        match="POLICY_RATE market series requires observation field",
    ):
        validate_market_data_bundle(
            (_phase1_series(MarketSeriesType.POLICY_RATE),),
            policy_rates=(_phase1_policy_definition(),),
            observations=(
                _phase1_observation(
                    "market_series.spread_bps",
                    unit="BASIS_POINTS",
                ),
            ),
        )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-1.00"),
        Decimal("0"),
        Decimal("4.75"),
    ],
)
def test_phase1_government_yield_allows_negative_zero_and_positive(
    value: Decimal,
) -> None:
    validate_market_data_bundle(
        (_phase1_series(MarketSeriesType.GOVERNMENT_YIELD),),
        government_yields=(_phase1_government_definition(),),
        observations=(
            _phase1_observation(
                "market_series.yield_percent",
                value=value,
                unit="PERCENT",
            ),
        ),
    )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-1.00"),
        Decimal("0"),
        Decimal("4.75"),
    ],
)
def test_phase1_swap_rate_allows_negative_zero_and_positive(
    value: Decimal,
) -> None:
    validate_market_data_bundle(
        (_phase1_series(MarketSeriesType.SWAP_RATE),),
        swap_rates=(_phase1_swap_definition(),),
        observations=(
            _phase1_observation(
                "market_series.rate_percent",
                value=value,
                unit="PERCENT",
            ),
        ),
    )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("0"),
        Decimal("-0.01"),
    ],
)
def test_phase1_equity_index_requires_positive_level(
    value: Decimal,
) -> None:
    with pytest.raises(
        ValueError,
        match="Equity-index level must be strictly positive",
    ):
        validate_market_data_bundle(
            (_phase1_series(MarketSeriesType.EQUITY_INDEX),),
            equity_indices=(_phase1_equity_definition(),),
            observations=(
                _phase1_observation(
                    "market_series.index_level",
                    value=value,
                    unit="INDEX_POINTS",
                ),
            ),
        )


def test_phase1_volatility_index_rejects_negative_level() -> None:
    with pytest.raises(
        ValueError,
        match="Volatility-index level must be non-negative",
    ):
        validate_market_data_bundle(
            (_phase1_series(MarketSeriesType.VOLATILITY_INDEX),),
            volatility_indices=(_phase1_volatility_definition(),),
            observations=(
                _phase1_observation(
                    "market_series.volatility_level",
                    value=Decimal("-0.01"),
                    unit="INDEX_POINTS",
                ),
            ),
        )


def test_phase1_missing_market_observation_is_valid() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000100",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000100",
        field_name="market_series.rate_percent",
        as_of_date=date(2026, 9, 18),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    validate_market_data_bundle(
        (_phase1_series(MarketSeriesType.POLICY_RATE),),
        policy_rates=(_phase1_policy_definition(),),
        observations=(observation,),
    )


def test_phase1_government_yield_rejects_zero_tenor() -> None:
    with pytest.raises(
        ValueError,
        match="tenor_months must be strictly positive",
    ):
        GovernmentYieldDefinitionRecord(
            market_series_id="MKS000000100",
            sovereign="Federal Republic of Germany",
            jurisdiction="Germany",
            currency="EUR",
            tenor_months=0,
            benchmark_ref="German sovereign benchmark",
            convention_ref="market-data/government-yield-v1",
        )


def test_phase1_government_yield_rejects_boolean_tenor() -> None:
    with pytest.raises(
        TypeError,
        match="tenor_months must be an integer",
    ):
        GovernmentYieldDefinitionRecord(
            market_series_id="MKS000000100",
            sovereign="Federal Republic of Germany",
            jurisdiction="Germany",
            currency="EUR",
            tenor_months=True,  # type: ignore[arg-type]
            benchmark_ref="German sovereign benchmark",
            convention_ref="market-data/government-yield-v1",
        )


def test_phase1_volatility_horizon_rejects_boolean() -> None:
    with pytest.raises(
        TypeError,
        match="horizon_days must be an integer",
    ):
        VolatilityIndexDefinitionRecord(
            market_series_id="MKS000000100",
            index_name="European Equity Volatility",
            underlying_ref="STOXX Europe 600",
            methodology_ref="market-data/volatility-index-v1",
            horizon_days=True,  # type: ignore[arg-type]
        )


def test_phase1_policy_rate_rejects_invalid_currency_code() -> None:
    with pytest.raises(
        ValueError,
        match="currency",
    ):
        PolicyRateDefinitionRecord(
            market_series_id="MKS000000100",
            authority="European Central Bank",
            jurisdiction="Euro Area",
            currency="eur",
            rate_name="Deposit Facility Rate",
            convention_ref="market-data/ecb/policy-rate-v1",
        )


def test_phase1_credit_optional_segment_rejects_blank_value() -> None:
    with pytest.raises(
        ValueError,
        match="rating_segment",
    ):
        CreditSpreadDefinitionRecord(
            market_series_id="MKS000000100",
            benchmark_family="European Corporate Credit",
            currency="EUR",
            credit_universe="Investment Grade",
            spread_measure="OAS",
            convention_ref="market-data/credit-spread-v1",
            rating_segment="   ",
        )
