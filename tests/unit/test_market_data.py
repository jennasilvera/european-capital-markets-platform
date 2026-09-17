from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
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
