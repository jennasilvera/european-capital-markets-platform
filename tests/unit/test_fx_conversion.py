from datetime import date
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext

import pytest

from european_capital_markets.domain.fx_conversion import (
    FXConversionDirection,
    calculate_fx_conversion,
    resolve_fx_conversion_direction,
    validate_fx_conversion_bundle,
)
from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    ValueClass,
    VerificationState,
)

FX_DATE = date(2026, 9, 17)


def _definition(
    *,
    market_series_id: str = "MKS000000001",
    base_currency: str = "EUR",
    quote_currency: str = "GBP",
) -> FXReferenceRateDefinitionRecord:
    return FXReferenceRateDefinitionRecord(
        market_series_id=market_series_id,
        base_currency=base_currency,
        quote_currency=quote_currency,
        convention_ref="market-data/fx/reference-rate-v1",
    )


def _native_issue_size(
    *,
    observation_id: str = "OBS000000001",
    instrument_id: str = "INS000000001",
    value: Decimal = Decimal("300000000"),
    currency: str = "GBP",
    as_of_date: date = date(2026, 9, 16),
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=EntityType.INSTRUMENT,
        subject_id=instrument_id,
        field_name="instrument.issue_size",
        as_of_date=as_of_date,
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=ValueClass.ASSUMED,
        currency=currency,
        derivation_ref="test://native-issue-size",
    )


def _rate(
    *,
    observation_id: str = "OBS000000002",
    market_series_id: str = "MKS000000001",
    value: Decimal = Decimal("0.75"),
    as_of_date: date = FX_DATE,
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=EntityType.MARKET_SERIES,
        subject_id=market_series_id,
        field_name="market_series.fx_rate",
        as_of_date=as_of_date,
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://fx-rate",
    )


def _converted(
    *,
    observation_id: str = "OBS000000003",
    instrument_id: str = "INS000000001",
    value: Decimal = Decimal("400000000"),
    currency: str = "EUR",
    as_of_date: date = FX_DATE,
    input_observation_ids: tuple[str, ...] = (
        "OBS000000001",
        "OBS000000002",
    ),
    value_class: ValueClass = ValueClass.CALCULATED,
    derivation_ref: str = "methodology/fx-conversion-v1",
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=EntityType.INSTRUMENT,
        subject_id=instrument_id,
        field_name="instrument.issue_size_converted",
        as_of_date=as_of_date,
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=value_class,
        currency=currency,
        input_observation_ids=input_observation_ids,
        derivation_ref=derivation_ref,
    )


def test_direct_pair_conversion_multiplies() -> None:
    definition = _definition(
        base_currency="GBP",
        quote_currency="EUR",
    )

    direction = resolve_fx_conversion_direction(
        source_currency="GBP",
        target_currency="EUR",
        definition=definition,
    )

    assert direction is FXConversionDirection.MULTIPLY

    result = calculate_fx_conversion(
        amount=Decimal("300"),
        source_currency="GBP",
        target_currency="EUR",
        rate=Decimal("1.20"),
        definition=definition,
    )

    assert result == Decimal("360.00")


def test_inverse_pair_conversion_divides() -> None:
    definition = _definition(
        base_currency="EUR",
        quote_currency="GBP",
    )

    direction = resolve_fx_conversion_direction(
        source_currency="GBP",
        target_currency="EUR",
        definition=definition,
    )

    assert direction is FXConversionDirection.DIVIDE

    result = calculate_fx_conversion(
        amount=Decimal("300"),
        source_currency="GBP",
        target_currency="EUR",
        rate=Decimal("0.75"),
        definition=definition,
    )

    assert result == Decimal("400")


def test_fx_conversion_is_independent_of_ambient_rounding() -> None:
    definition = _definition(
        base_currency="EUR",
        quote_currency="GBP",
    )

    with localcontext() as context:
        context.rounding = ROUND_DOWN
        round_down_result = calculate_fx_conversion(
            amount=Decimal("1"),
            source_currency="GBP",
            target_currency="EUR",
            rate=Decimal("3"),
            definition=definition,
        )

    with localcontext() as context:
        context.rounding = ROUND_UP
        round_up_result = calculate_fx_conversion(
            amount=Decimal("1"),
            source_currency="GBP",
            target_currency="EUR",
            rate=Decimal("3"),
            definition=definition,
        )

    expected = Decimal(
        "0.33333333333333333333333333333333333333"
    )

    assert round_down_result == expected
    assert round_up_result == expected


def test_conversion_rejects_same_currency() -> None:
    with pytest.raises(ValueError, match="different source and target"):
        resolve_fx_conversion_direction(
            source_currency="EUR",
            target_currency="EUR",
            definition=_definition(),
        )


def test_conversion_rejects_unrelated_pair() -> None:
    with pytest.raises(ValueError, match="does not cover"):
        resolve_fx_conversion_direction(
            source_currency="USD",
            target_currency="EUR",
            definition=_definition(),
        )


def test_valid_converted_issue_size() -> None:
    validate_fx_conversion_bundle(
        fx_reference_rates=(_definition(),),
        observations=(
            _native_issue_size(),
            _rate(),
            _converted(),
        ),
    )


def test_converted_issue_size_must_be_calculated() -> None:
    converted = ObservationRecord(
        observation_id="OBS000000003",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size_converted",
        as_of_date=FX_DATE,
        verification_state=VerificationState.PENDING,
        value=Decimal("400000000"),
        value_class=ValueClass.ASSUMED,
        currency="EUR",
        derivation_ref="test://invalid-assumed-conversion",
    )

    with pytest.raises(ValueError, match="must be CALCULATED"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(converted,),
        )


def test_conversion_requires_exactly_two_inputs() -> None:
    with pytest.raises(ValueError, match="exactly two inputs"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                _rate(),
                _converted(
                    input_observation_ids=(
                        "OBS000000001",
                        "OBS000000002",
                        "OBS000000004",
                    ),
                ),
            ),
        )


def test_conversion_rejects_unknown_input() -> None:
    with pytest.raises(ValueError, match="Unknown FX-conversion input"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                _converted(
                    input_observation_ids=(
                        "OBS000000001",
                        "OBS000000999",
                    ),
                ),
            ),
        )


def test_conversion_requires_native_issue_size_input() -> None:
    other = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.coupon_percent",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        value=Decimal("4.0"),
        value_class=ValueClass.ASSUMED,
        unit="PERCENT",
        derivation_ref="test://coupon",
    )

    with pytest.raises(ValueError, match="native instrument.issue_size"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                other,
                _rate(),
                _converted(),
            ),
        )


def test_conversion_requires_fx_rate_input() -> None:
    non_rate_input = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.coupon_percent",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        value=Decimal("4.0"),
        value_class=ValueClass.ASSUMED,
        unit="PERCENT",
        derivation_ref="test://coupon",
    )

    with pytest.raises(ValueError, match="market_series.fx_rate"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                non_rate_input,
                _converted(),
            ),
        )


def test_native_issue_size_must_belong_to_same_instrument() -> None:
    with pytest.raises(ValueError, match="same instrument"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(
                    instrument_id="INS000000002",
                ),
                _rate(),
                _converted(),
            ),
        )


def test_conversion_rejects_missing_native_amount() -> None:
    missing_native = ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size",
        as_of_date=date(2026, 9, 16),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    with pytest.raises(ValueError, match="missing native issue size"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                missing_native,
                _rate(),
                _converted(),
            ),
        )


def test_conversion_rejects_missing_fx_rate() -> None:
    missing_rate = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=FX_DATE,
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    with pytest.raises(ValueError, match="missing FX rate"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                missing_rate,
                _converted(),
            ),
        )


def test_conversion_date_must_match_fx_rate_date() -> None:
    with pytest.raises(ValueError, match="as_of_date"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                _rate(
                    as_of_date=date(2026, 9, 16),
                ),
                _converted(
                    as_of_date=FX_DATE,
                ),
            ),
        )


def test_conversion_rejects_missing_fx_definition() -> None:
    with pytest.raises(
        ValueError,
        match="without an FX reference-rate definition",
    ):
        validate_fx_conversion_bundle(
            fx_reference_rates=(),
            observations=(
                _native_issue_size(),
                _rate(),
                _converted(),
            ),
        )


def test_conversion_rejects_arithmetic_mismatch() -> None:
    with pytest.raises(ValueError, match="does not equal"):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                _rate(),
                _converted(
                    value=Decimal("399999999"),
                ),
            ),
        )


def test_conversion_requires_governed_derivation_reference() -> None:
    with pytest.raises(
        ValueError,
        match="governed derivation reference",
    ):
        validate_fx_conversion_bundle(
            fx_reference_rates=(_definition(),),
            observations=(
                _native_issue_size(),
                _rate(),
                _converted(
                    derivation_ref="test://alternate-fx-method",
                ),
            ),
        )


def test_conversion_rejects_duplicate_fx_definitions() -> None:
    first = _definition()

    second = FXReferenceRateDefinitionRecord(
        market_series_id="MKS000000001",
        base_currency="GBP",
        quote_currency="EUR",
        convention_ref="market-data/fx/alternate-reference-v1",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate FX reference-rate definition",
    ):
        validate_fx_conversion_bundle(
            fx_reference_rates=(
                first,
                second,
            ),
            observations=(
                _native_issue_size(),
                _rate(),
                _converted(),
            ),
        )
