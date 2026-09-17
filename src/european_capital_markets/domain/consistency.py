"""Cross-observation consistency controls."""

from datetime import date
from decimal import Decimal

from european_capital_markets.domain.entities import InstrumentRecord
from european_capital_markets.domain.fx_conversion import (
    validate_fx_conversion_bundle,
)
from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    ValueClass,
)
from european_capital_markets.domain.terms import (
    FIELD_DEFINITION_BY_NAME,
    CurrencyBinding,
    validate_term_observation,
)


def validate_cross_observation_consistency(
    instruments: tuple[InstrumentRecord, ...],
    observations: tuple[ObservationRecord, ...],
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ] = (),
) -> None:
    """Validate deterministic relationships across observations."""

    instrument_by_id = _index_unique(
        instruments,
        "instrument_id",
    )
    observation_by_id = _index_unique(
        observations,
        "observation_id",
    )

    _validate_governed_terms(observations)
    _validate_input_dates(
        observations,
        observation_by_id,
    )
    validate_fx_conversion_bundle(
        fx_reference_rates=fx_reference_rates,
        observations=observations,
    )
    _validate_instrument_currency_consistency(
        observations,
    )
    _validate_calculated_transaction_aggregates(
        observations,
        observation_by_id,
        instrument_by_id,
    )


def _validate_governed_terms(
    observations: tuple[ObservationRecord, ...],
) -> None:
    for observation in observations:
        if observation.field_name in FIELD_DEFINITION_BY_NAME:
            validate_term_observation(observation)


def _validate_input_dates(
    observations: tuple[ObservationRecord, ...],
    observation_by_id: dict[str, ObservationRecord],
) -> None:
    for observation in observations:
        for input_observation_id in observation.input_observation_ids:
            try:
                input_observation = observation_by_id[
                    input_observation_id
                ]
            except KeyError as exc:
                raise ValueError(
                    "Unknown input observation reference: "
                    f"{input_observation_id!r}"
                ) from exc

            if (
                input_observation.as_of_date
                > observation.as_of_date
            ):
                raise ValueError(
                    "Derived observation cannot depend on a future "
                    "input observation."
                )


def _validate_instrument_currency_consistency(
    observations: tuple[ObservationRecord, ...],
) -> None:
    monetary_observations = [
        observation
        for observation in observations
        if (
            observation.subject_type is EntityType.INSTRUMENT
            and observation.missing_state is None
            and (
                definition := FIELD_DEFINITION_BY_NAME.get(
                    observation.field_name
                )
            )
            is not None
            and definition.currency_binding
            is CurrencyBinding.INSTRUMENT_CURRENCY
        )
    ]

    for observation in monetary_observations:
        currency_observation = _latest_populated_field_observation(
            observations=observations,
            subject_type=EntityType.INSTRUMENT,
            subject_id=observation.subject_id,
            field_name="instrument.currency",
            as_of_date=observation.as_of_date,
        )

        if currency_observation is None:
            continue

        if currency_observation.value != observation.currency:
            raise ValueError(
                "Instrument monetary observation currency conflicts "
                "with the latest known instrument currency."
            )


def _latest_populated_field_observation(
    *,
    observations: tuple[ObservationRecord, ...],
    subject_type: EntityType,
    subject_id: str,
    field_name: str,
    as_of_date: date,
) -> ObservationRecord | None:
    """Return the latest known populated observation for one field."""

    candidates = [
        observation
        for observation in observations
        if observation.subject_type is subject_type
        and observation.subject_id == subject_id
        and observation.field_name == field_name
        and observation.as_of_date <= as_of_date
        and observation.missing_state is None
    ]

    if not candidates:
        return None

    latest_date = max(
        observation.as_of_date
        for observation in candidates
    )

    latest = [
        observation
        for observation in candidates
        if observation.as_of_date == latest_date
    ]

    values = {
        observation.value
        for observation in latest
    }

    if len(values) > 1:
        raise ValueError(
            "Conflicting latest populated observations exist for the same "
            "subject, field, and as-of date."
        )

    # Multiple observations carrying the same economic value are not
    # economically ambiguous. Select deterministically for callers that
    # require the source record rather than only its value.
    return min(
        latest,
        key=lambda observation: observation.observation_id,
    )


def _validate_calculated_transaction_aggregates(
    observations: tuple[ObservationRecord, ...],
    observation_by_id: dict[str, ObservationRecord],
    instrument_by_id: dict[str, InstrumentRecord],
) -> None:
    aggregates = [
        observation
        for observation in observations
        if observation.field_name == "transaction.aggregate_size"
        and observation.value_class is ValueClass.CALCULATED
        and observation.missing_state is None
    ]

    for aggregate in aggregates:
        inputs = [
            observation_by_id[input_observation_id]
            for input_observation_id
            in aggregate.input_observation_ids
        ]

        instrument_ids: set[str] = set()

        for input_observation in inputs:
            if (
                input_observation.subject_type
                is not EntityType.INSTRUMENT
                or input_observation.field_name
                not in {
                    "instrument.issue_size",
                    "instrument.issue_size_converted",
                }
            ):
                raise ValueError(
                    "Calculated transaction aggregate size may only use "
                    "instrument.issue_size or "
                    "instrument.issue_size_converted inputs."
                )

            if input_observation.missing_state is not None:
                raise ValueError(
                    "Calculated transaction aggregate size cannot "
                    "use a missing instrument.issue_size input."
                )

            instrument_id = input_observation.subject_id

            if instrument_id in instrument_ids:
                raise ValueError(
                    "Calculated transaction aggregate size cannot "
                    "include multiple issue-size observations for "
                    "the same instrument."
                )

            instrument_ids.add(instrument_id)

            try:
                instrument = instrument_by_id[
                    instrument_id
                ]
            except KeyError as exc:
                raise ValueError(
                    "Unknown instrument referenced by aggregate input: "
                    f"{instrument_id!r}"
                ) from exc

            if instrument.transaction_id != aggregate.subject_id:
                raise ValueError(
                    "Calculated transaction aggregate size contains "
                    "an instrument from another transaction."
                )

        input_currencies = {
            input_observation.currency
            for input_observation in inputs
        }

        if input_currencies != {aggregate.currency}:
            raise ValueError(
                "Calculated transaction aggregate inputs must all be "
                "expressed in the aggregate currency. Foreign-currency "
                "tranches require instrument.issue_size_converted inputs."
            )

        input_total = sum(
            (
                input_observation.value
                for input_observation in inputs
            ),
            Decimal("0"),
        )

        if input_total != aggregate.value:
            raise ValueError(
                "Calculated transaction aggregate does not equal its "
                "currency-normalized tranche-size inputs."
            )


def _index_unique[T](
    records: tuple[T, ...],
    id_field: str,
) -> dict[str, T]:
    indexed: dict[str, T] = {}

    for record in records:
        identifier = getattr(record, id_field)

        if identifier in indexed:
            raise ValueError(
                f"Duplicate identifier: {identifier!r}"
            )

        indexed[identifier] = record

    return indexed
