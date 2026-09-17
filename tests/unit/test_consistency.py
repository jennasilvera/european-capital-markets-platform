from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.consistency import (
    validate_cross_observation_consistency,
)
from european_capital_markets.domain.entities import InstrumentRecord
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


def _instrument(
    instrument_id: str = "INS000000001",
    transaction_id: str = "TXN000000001",
) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=instrument_id,
        transaction_id=transaction_id,
    )


def _assumed(
    *,
    observation_id: str,
    subject_type: EntityType,
    subject_id: str,
    field_name: str,
    value: object,
    as_of_date: date = date(2026, 9, 17),
    unit: str | None = None,
    currency: str | None = None,
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=subject_type,
        subject_id=subject_id,
        field_name=field_name,
        as_of_date=as_of_date,
        verification_state=VerificationState.PENDING,
        value=value,  # type: ignore[arg-type]
        value_class=ValueClass.ASSUMED,
        unit=unit,
        currency=currency,
        derivation_ref="test://consistency-assumption",
    )


def _currency(
    *,
    observation_id: str = "OBS000000001",
    instrument_id: str = "INS000000001",
    value: str = "EUR",
    as_of_date: date = date(2026, 9, 1),
) -> ObservationRecord:
    return _assumed(
        observation_id=observation_id,
        subject_type=EntityType.INSTRUMENT,
        subject_id=instrument_id,
        field_name="instrument.currency",
        value=value,
        as_of_date=as_of_date,
    )


def _issue_size(
    *,
    observation_id: str = "OBS000000002",
    instrument_id: str = "INS000000001",
    value: Decimal = Decimal("500000000"),
    currency: str = "EUR",
    as_of_date: date = date(2026, 9, 2),
) -> ObservationRecord:
    return _assumed(
        observation_id=observation_id,
        subject_type=EntityType.INSTRUMENT,
        subject_id=instrument_id,
        field_name="instrument.issue_size",
        value=value,
        currency=currency,
        as_of_date=as_of_date,
    )


def _calculated_aggregate(
    *,
    observation_id: str = "OBS000000010",
    transaction_id: str = "TXN000000001",
    value: Decimal = Decimal("1000000000"),
    currency: str = "EUR",
    as_of_date: date = date(2026, 9, 3),
    input_observation_ids: tuple[str, ...] = (
        "OBS000000002",
        "OBS000000003",
    ),
) -> ObservationRecord:
    return ObservationRecord(
        observation_id=observation_id,
        subject_type=EntityType.TRANSACTION,
        subject_id=transaction_id,
        field_name="transaction.aggregate_size",
        as_of_date=as_of_date,
        verification_state=VerificationState.PENDING,
        value=value,
        value_class=ValueClass.CALCULATED,
        currency=currency,
        input_observation_ids=input_observation_ids,
        derivation_ref="calc://sum-tranche-issue-size",
    )


def test_matching_instrument_currency_is_valid() -> None:
    observations = (
        _currency(),
        _issue_size(),
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=observations,
    )


def test_instrument_currency_mismatch_is_rejected() -> None:
    observations = (
        _currency(value="EUR"),
        _issue_size(currency="GBP"),
    )

    with pytest.raises(ValueError, match="currency conflicts"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=observations,
        )


def test_later_currency_change_does_not_rewrite_earlier_observation() -> None:
    observations = (
        _currency(
            observation_id="OBS000000001",
            value="EUR",
            as_of_date=date(2026, 9, 1),
        ),
        _issue_size(
            observation_id="OBS000000002",
            currency="EUR",
            as_of_date=date(2026, 9, 2),
        ),
        _currency(
            observation_id="OBS000000003",
            value="GBP",
            as_of_date=date(2026, 9, 3),
        ),
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=observations,
    )


def test_conflicting_latest_same_day_currency_is_rejected() -> None:
    observations = (
        _currency(
            observation_id="OBS000000001",
            value="EUR",
        ),
        _currency(
            observation_id="OBS000000002",
            value="GBP",
        ),
        _issue_size(
            observation_id="OBS000000003",
            currency="EUR",
        ),
    )

    with pytest.raises(ValueError, match="Conflicting latest observations"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=observations,
        )


def test_latest_missing_currency_state_does_not_use_stale_value() -> None:
    missing_currency = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.currency",
        as_of_date=date(2026, 9, 2),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    observations = (
        _currency(
            observation_id="OBS000000001",
            value="EUR",
            as_of_date=date(2026, 9, 1),
        ),
        missing_currency,
        _issue_size(
            observation_id="OBS000000003",
            currency="GBP",
            as_of_date=date(2026, 9, 3),
        ),
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=observations,
    )


def test_future_input_observation_is_rejected() -> None:
    input_observation = _issue_size(
        observation_id="OBS000000002",
        as_of_date=date(2026, 9, 5),
    )
    aggregate = _calculated_aggregate(
        value=Decimal("500000000"),
        as_of_date=date(2026, 9, 4),
        input_observation_ids=("OBS000000002",),
    )

    with pytest.raises(ValueError, match="future input"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=(
                input_observation,
                aggregate,
            ),
        )


def test_same_currency_calculated_aggregate_reconciles() -> None:
    first = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000001",
        value=Decimal("600000000"),
    )
    second = _issue_size(
        observation_id="OBS000000003",
        instrument_id="INS000000002",
        value=Decimal("400000000"),
    )
    aggregate = _calculated_aggregate()

    validate_cross_observation_consistency(
        instruments=(
            _instrument("INS000000001"),
            _instrument("INS000000002"),
        ),
        observations=(
            first,
            second,
            aggregate,
        ),
    )


def test_same_currency_calculated_aggregate_mismatch_is_rejected() -> None:
    first = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000001",
        value=Decimal("600000000"),
    )
    second = _issue_size(
        observation_id="OBS000000003",
        instrument_id="INS000000002",
        value=Decimal("400000000"),
    )
    aggregate = _calculated_aggregate(
        value=Decimal("999000000"),
    )

    with pytest.raises(ValueError, match="does not equal"):
        validate_cross_observation_consistency(
            instruments=(
                _instrument("INS000000001"),
                _instrument("INS000000002"),
            ),
            observations=(
                first,
                second,
                aggregate,
            ),
        )


def test_aggregate_rejects_non_issue_size_input() -> None:
    coupon = _assumed(
        observation_id="OBS000000002",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.coupon_percent",
        value=Decimal("4.25"),
        as_of_date=date(2026, 9, 2),
        unit="PERCENT",
    )
    aggregate = _calculated_aggregate(
        value=Decimal("4.25"),
        input_observation_ids=("OBS000000002",),
    )

    with pytest.raises(ValueError, match="instrument.issue_size"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=(
                coupon,
                aggregate,
            ),
        )


def test_aggregate_rejects_instrument_from_other_transaction() -> None:
    issue_size = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000002",
    )
    aggregate = _calculated_aggregate(
        value=Decimal("500000000"),
        input_observation_ids=("OBS000000002",),
    )

    with pytest.raises(ValueError, match="another transaction"):
        validate_cross_observation_consistency(
            instruments=(
                _instrument(
                    instrument_id="INS000000002",
                    transaction_id="TXN000000002",
                ),
            ),
            observations=(
                issue_size,
                aggregate,
            ),
        )


def test_aggregate_rejects_multiple_revisions_for_same_instrument() -> None:
    earlier = _issue_size(
        observation_id="OBS000000002",
        value=Decimal("400000000"),
        as_of_date=date(2026, 9, 1),
    )
    later = _issue_size(
        observation_id="OBS000000003",
        value=Decimal("500000000"),
        as_of_date=date(2026, 9, 2),
    )
    aggregate = _calculated_aggregate(
        value=Decimal("900000000"),
    )

    with pytest.raises(ValueError, match="same instrument"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=(
                earlier,
                later,
                aggregate,
            ),
        )


def test_cross_currency_aggregate_requires_converted_inputs() -> None:
    euro = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000001",
        value=Decimal("500000000"),
        currency="EUR",
    )
    sterling = _issue_size(
        observation_id="OBS000000003",
        instrument_id="INS000000002",
        value=Decimal("300000000"),
        currency="GBP",
    )
    aggregate = _calculated_aggregate(
        value=Decimal("850000000"),
        currency="EUR",
    )

    with pytest.raises(
        ValueError,
        match="instrument.issue_size_converted",
    ):
        validate_cross_observation_consistency(
            instruments=(
                _instrument("INS000000001"),
                _instrument("INS000000002"),
            ),
            observations=(
                euro,
                sterling,
                aggregate,
            ),
        )


def test_non_calculated_aggregate_is_not_forced_to_equal_tranches() -> None:
    tranche = _issue_size(
        observation_id="OBS000000002",
        value=Decimal("500000000"),
    )
    disclosed_aggregate = _assumed(
        observation_id="OBS000000010",
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="transaction.aggregate_size",
        value=Decimal("510000000"),
        currency="EUR",
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=(
            tranche,
            disclosed_aggregate,
        ),
    )


def test_consistency_layer_reuses_field_semantics() -> None:
    invalid_spread = _assumed(
        observation_id="OBS000000001",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.spread_bps",
        value=Decimal("125"),
        unit="PERCENT",
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=(invalid_spread,),
        )


def test_identical_latest_same_day_currency_values_are_valid() -> None:
    observations = (
        _currency(
            observation_id="OBS000000001",
            value="EUR",
            as_of_date=date(2026, 9, 1),
        ),
        _currency(
            observation_id="OBS000000002",
            value="EUR",
            as_of_date=date(2026, 9, 1),
        ),
        _issue_size(
            observation_id="OBS000000003",
            currency="EUR",
            as_of_date=date(2026, 9, 2),
        ),
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=observations,
    )


def test_populated_and_missing_latest_same_day_currency_is_rejected() -> None:
    missing_currency = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.currency",
        as_of_date=date(2026, 9, 1),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    observations = (
        _currency(
            observation_id="OBS000000001",
            value="EUR",
            as_of_date=date(2026, 9, 1),
        ),
        missing_currency,
        _issue_size(
            observation_id="OBS000000003",
            currency="EUR",
            as_of_date=date(2026, 9, 2),
        ),
    )

    with pytest.raises(ValueError, match="Ambiguous latest field state"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=observations,
        )


def test_calculated_aggregate_rejects_missing_issue_size_input() -> None:
    missing_issue_size = ObservationRecord(
        observation_id="OBS000000002",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size",
        as_of_date=date(2026, 9, 2),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )
    aggregate = _calculated_aggregate(
        value=Decimal("500000000"),
        as_of_date=date(2026, 9, 3),
        input_observation_ids=("OBS000000002",),
    )

    with pytest.raises(ValueError, match="missing instrument.issue_size"):
        validate_cross_observation_consistency(
            instruments=(_instrument(),),
            observations=(
                missing_issue_size,
                aggregate,
            ),
        )


def test_converted_issue_size_may_differ_from_instrument_currency() -> None:
    native_currency = _currency(
        observation_id="OBS000000001",
        value="GBP",
        as_of_date=date(2026, 9, 1),
    )
    native_size = _issue_size(
        observation_id="OBS000000002",
        value=Decimal("300000000"),
        currency="GBP",
        as_of_date=date(2026, 9, 2),
    )
    fx_rate = ObservationRecord(
        observation_id="OBS000000003",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.75"),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://fx-rate",
    )
    converted = ObservationRecord(
        observation_id="OBS000000004",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size_converted",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("400000000"),
        value_class=ValueClass.CALCULATED,
        currency="EUR",
        input_observation_ids=(
            "OBS000000002",
            "OBS000000003",
        ),
        derivation_ref="methodology/fx-conversion-v1",
    )

    validate_cross_observation_consistency(
        instruments=(_instrument(),),
        observations=(
            native_currency,
            native_size,
            fx_rate,
            converted,
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000001",
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
    )


def test_converted_tranche_can_reconcile_transaction_aggregate() -> None:
    euro_native = _issue_size(
        observation_id="OBS000000001",
        instrument_id="INS000000001",
        value=Decimal("500000000"),
        currency="EUR",
        as_of_date=date(2026, 9, 2),
    )
    sterling_native = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000002",
        value=Decimal("300000000"),
        currency="GBP",
        as_of_date=date(2026, 9, 2),
    )
    fx_rate = ObservationRecord(
        observation_id="OBS000000003",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.75"),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://fx-rate",
    )
    sterling_in_eur = ObservationRecord(
        observation_id="OBS000000004",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000002",
        field_name="instrument.issue_size_converted",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("400000000"),
        value_class=ValueClass.CALCULATED,
        currency="EUR",
        input_observation_ids=(
            "OBS000000002",
            "OBS000000003",
        ),
        derivation_ref="methodology/fx-conversion-v1",
    )
    aggregate = _calculated_aggregate(
        value=Decimal("900000000"),
        currency="EUR",
        as_of_date=date(2026, 9, 3),
        input_observation_ids=(
            "OBS000000001",
            "OBS000000004",
        ),
    )

    validate_cross_observation_consistency(
        instruments=(
            _instrument(
                instrument_id="INS000000001",
            ),
            _instrument(
                instrument_id="INS000000002",
            ),
        ),
        observations=(
            euro_native,
            sterling_native,
            fx_rate,
            sterling_in_eur,
            aggregate,
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000001",
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
    )


def test_converted_tranche_aggregate_mismatch_is_rejected() -> None:
    euro_native = _issue_size(
        observation_id="OBS000000001",
        instrument_id="INS000000001",
        value=Decimal("500000000"),
        currency="EUR",
        as_of_date=date(2026, 9, 2),
    )
    sterling_native = _issue_size(
        observation_id="OBS000000002",
        instrument_id="INS000000002",
        value=Decimal("300000000"),
        currency="GBP",
        as_of_date=date(2026, 9, 2),
    )
    fx_rate = ObservationRecord(
        observation_id="OBS000000003",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.fx_rate",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("0.75"),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test://fx-rate",
    )
    sterling_in_eur = ObservationRecord(
        observation_id="OBS000000004",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000002",
        field_name="instrument.issue_size_converted",
        as_of_date=date(2026, 9, 3),
        verification_state=VerificationState.PENDING,
        value=Decimal("400000000"),
        value_class=ValueClass.CALCULATED,
        currency="EUR",
        input_observation_ids=(
            "OBS000000002",
            "OBS000000003",
        ),
        derivation_ref="methodology/fx-conversion-v1",
    )
    aggregate = _calculated_aggregate(
        value=Decimal("899999999"),
        currency="EUR",
        as_of_date=date(2026, 9, 3),
        input_observation_ids=(
            "OBS000000001",
            "OBS000000004",
        ),
    )

    with pytest.raises(ValueError, match="does not equal"):
        validate_cross_observation_consistency(
            instruments=(
                _instrument(
                    instrument_id="INS000000001",
                ),
                _instrument(
                    instrument_id="INS000000002",
                ),
            ),
            observations=(
                euro_native,
                sterling_native,
                fx_rate,
                sterling_in_eur,
                aggregate,
            ),
            fx_reference_rates=(
                FXReferenceRateDefinitionRecord(
                    market_series_id="MKS000000001",
                    base_currency="EUR",
                    quote_currency="GBP",
                    convention_ref="market-data/fx/reference-rate-v1",
                ),
            ),
        )
