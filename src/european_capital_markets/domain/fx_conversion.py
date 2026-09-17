"""Deterministic FX conversion of governed monetary observations."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    ValueClass,
)

FX_CONVERSION_DERIVATION_REF = "methodology/fx-conversion-v1"


class FXConversionDirection(StrEnum):
    """Arithmetic direction implied by an oriented FX pair."""

    MULTIPLY = "MULTIPLY"
    DIVIDE = "DIVIDE"


def resolve_fx_conversion_direction(
    *,
    source_currency: str,
    target_currency: str,
    definition: FXReferenceRateDefinitionRecord,
) -> FXConversionDirection:
    """Resolve conversion arithmetic from canonical FX pair orientation."""

    if source_currency == target_currency:
        raise ValueError(
            "FX conversion requires different source and target currencies."
        )

    if (
        source_currency == definition.base_currency
        and target_currency == definition.quote_currency
    ):
        return FXConversionDirection.MULTIPLY

    if (
        source_currency == definition.quote_currency
        and target_currency == definition.base_currency
    ):
        return FXConversionDirection.DIVIDE

    raise ValueError(
        "FX reference-rate pair does not cover the requested "
        f"{source_currency}/{target_currency} conversion."
    )


def calculate_fx_conversion(
    *,
    amount: Decimal,
    source_currency: str,
    target_currency: str,
    rate: Decimal,
    definition: FXReferenceRateDefinitionRecord,
) -> Decimal:
    """Calculate a canonical FX conversion at governed precision."""

    if rate <= 0:
        raise ValueError("FX rate must be strictly positive.")

    direction = resolve_fx_conversion_direction(
        source_currency=source_currency,
        target_currency=target_currency,
        definition=definition,
    )

    # Freeze calculation precision and rounding rather than inheriting
    # either setting from the caller's ambient Decimal context.
    # Presentation rounding remains a separate downstream concern.
    with localcontext() as context:
        context.prec = 38
        context.rounding = ROUND_HALF_EVEN

        if direction is FXConversionDirection.MULTIPLY:
            return amount * rate

        return amount / rate


def validate_fx_conversion_bundle(
    *,
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ],
    observations: tuple[ObservationRecord, ...],
) -> None:
    """Validate governed instrument issue-size FX conversions."""

    observation_by_id = _index_observations(observations)

    definition_by_series_id: dict[
        str,
        FXReferenceRateDefinitionRecord,
    ] = {}

    for definition in fx_reference_rates:
        if definition.market_series_id in definition_by_series_id:
            raise ValueError(
                "Duplicate FX reference-rate definition for "
                f"{definition.market_series_id!r}."
            )

        definition_by_series_id[
            definition.market_series_id
        ] = definition

    converted_observations = [
        observation
        for observation in observations
        if observation.field_name
        == "instrument.issue_size_converted"
    ]

    for converted in converted_observations:
        _validate_converted_issue_size(
            converted=converted,
            observation_by_id=observation_by_id,
            definition_by_series_id=definition_by_series_id,
        )


def _validate_converted_issue_size(
    *,
    converted: ObservationRecord,
    observation_by_id: dict[str, ObservationRecord],
    definition_by_series_id: dict[
        str,
        FXReferenceRateDefinitionRecord,
    ],
) -> None:
    if converted.subject_type is not EntityType.INSTRUMENT:
        raise ValueError(
            "instrument.issue_size_converted requires INSTRUMENT scope."
        )

    if converted.value_class is not ValueClass.CALCULATED:
        raise ValueError(
            "instrument.issue_size_converted must be CALCULATED."
        )

    if converted.derivation_ref != FX_CONVERSION_DERIVATION_REF:
        raise ValueError(
            "instrument.issue_size_converted must use the governed "
            f"derivation reference {FX_CONVERSION_DERIVATION_REF!r}."
        )

    if converted.missing_state is not None:
        raise ValueError(
            "A converted issue-size calculation cannot be a missing value."
        )

    if len(converted.input_observation_ids) != 2:
        raise ValueError(
            "instrument.issue_size_converted requires exactly two inputs: "
            "one native issue size and one FX rate."
        )

    inputs: list[ObservationRecord] = []

    for input_id in converted.input_observation_ids:
        try:
            input_observation = observation_by_id[input_id]
        except KeyError as exc:
            raise ValueError(
                f"Unknown FX-conversion input observation: {input_id!r}"
            ) from exc

        if input_observation.as_of_date > converted.as_of_date:
            raise ValueError(
                "FX conversion cannot depend on a future input observation."
            )

        inputs.append(input_observation)

    native_candidates = [
        observation
        for observation in inputs
        if (
            observation.subject_type is EntityType.INSTRUMENT
            and observation.field_name == "instrument.issue_size"
        )
    ]

    rate_candidates = [
        observation
        for observation in inputs
        if (
            observation.subject_type is EntityType.MARKET_SERIES
            and observation.field_name == "market_series.fx_rate"
        )
    ]

    if len(native_candidates) != 1:
        raise ValueError(
            "FX conversion requires exactly one native "
            "instrument.issue_size input."
        )

    if len(rate_candidates) != 1:
        raise ValueError(
            "FX conversion requires exactly one market_series.fx_rate input."
        )

    native = native_candidates[0]
    rate = rate_candidates[0]

    if native.subject_id != converted.subject_id:
        raise ValueError(
            "Converted issue size must use the native issue size "
            "from the same instrument."
        )

    if native.missing_state is not None:
        raise ValueError(
            "FX conversion cannot use a missing native issue size."
        )

    if rate.missing_state is not None:
        raise ValueError(
            "FX conversion cannot use a missing FX rate."
        )

    if not isinstance(native.value, Decimal):
        raise TypeError(
            "Native instrument.issue_size must contain a Decimal value."
        )

    if not isinstance(rate.value, Decimal):
        raise TypeError(
            "market_series.fx_rate must contain a Decimal value."
        )

    if native.currency is None:
        raise ValueError(
            "Native instrument.issue_size requires source currency."
        )

    if converted.currency is None:
        raise ValueError(
            "Converted issue size requires target currency."
        )

    if rate.as_of_date != converted.as_of_date:
        raise ValueError(
            "Converted issue-size as_of_date must equal the referenced "
            "FX-rate as_of_date."
        )

    try:
        definition = definition_by_series_id[rate.subject_id]
    except KeyError as exc:
        raise ValueError(
            "FX conversion references a market series without an "
            f"FX reference-rate definition: {rate.subject_id!r}"
        ) from exc

    expected = calculate_fx_conversion(
        amount=native.value,
        source_currency=native.currency,
        target_currency=converted.currency,
        rate=rate.value,
        definition=definition,
    )

    if converted.value != expected:
        raise ValueError(
            "Converted issue-size value does not equal the deterministic "
            "FX conversion of its referenced inputs."
        )


def _index_observations(
    observations: tuple[ObservationRecord, ...],
) -> dict[str, ObservationRecord]:
    indexed: dict[str, ObservationRecord] = {}

    for observation in observations:
        if observation.observation_id in indexed:
            raise ValueError(
                f"Duplicate identifier: {observation.observation_id!r}"
            )

        indexed[observation.observation_id] = observation

    return indexed
