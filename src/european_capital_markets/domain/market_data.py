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


def _require_currency_code(
    value: str,
    field_name: str,
) -> None:
    if fullmatch(r"[A-Z]{3}", value) is None:
        raise ValueError(
            f"{field_name} must be a three-letter uppercase currency code."
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


def validate_market_series_bundle(
    market_series: tuple[MarketSeriesRecord, ...],
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ],
) -> None:
    """Validate generic identities and FX reference-rate definitions."""

    series_by_id: dict[str, MarketSeriesRecord] = {}

    for series in market_series:
        if series.market_series_id in series_by_id:
            raise ValueError(
                f"Duplicate identifier: {series.market_series_id!r}"
            )

        series_by_id[series.market_series_id] = series

    fx_definition_by_id: dict[
        str,
        FXReferenceRateDefinitionRecord,
    ] = {}
    semantic_keys: set[
        tuple[
            str,
            str,
            str,
        ]
    ] = set()

    for definition in fx_reference_rates:
        if definition.market_series_id in fx_definition_by_id:
            raise ValueError(
                "Duplicate FX reference-rate definition for "
                f"{definition.market_series_id!r}."
            )

        fx_definition_by_id[
            definition.market_series_id
        ] = definition

        try:
            series = series_by_id[
                definition.market_series_id
            ]
        except KeyError as exc:
            raise ValueError(
                "FX reference-rate definition references unknown "
                f"market series {definition.market_series_id!r}."
            ) from exc

        if (
            series.series_type
            is not MarketSeriesType.FX_REFERENCE_RATE
        ):
            raise ValueError(
                "FX reference-rate definition requires an "
                "FX_REFERENCE_RATE market series."
            )

        semantic_key = (
            definition.base_currency,
            definition.quote_currency,
            definition.convention_ref,
        )

        if semantic_key in semantic_keys:
            raise ValueError(
                "Duplicate canonical FX reference-rate identity: "
                f"{definition.base_currency}/"
                f"{definition.quote_currency} "
                f"{definition.convention_ref!r}."
            )

        semantic_keys.add(semantic_key)

    for series in market_series:
        if (
            series.series_type
            is MarketSeriesType.FX_REFERENCE_RATE
            and series.market_series_id
            not in fx_definition_by_id
        ):
            raise ValueError(
                "FX_REFERENCE_RATE market series requires exactly "
                "one FX reference-rate definition."
            )


def validate_market_data_bundle(
    market_series: tuple[MarketSeriesRecord, ...],
    fx_reference_rates: tuple[
        FXReferenceRateDefinitionRecord,
        ...,
    ],
    observations: tuple[ObservationRecord, ...],
) -> None:
    """Validate market-series references and governed observations."""

    validate_market_series_bundle(
        market_series,
        fx_reference_rates,
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

        if observation.field_name == "market_series.fx_rate":
            _validate_fx_rate_observation(
                observation,
                series,
            )


def _validate_fx_rate_observation(
    observation: ObservationRecord,
    series: MarketSeriesRecord,
) -> None:
    if (
        series.series_type
        is not MarketSeriesType.FX_REFERENCE_RATE
    ):
        raise ValueError(
            "market_series.fx_rate requires an "
            "FX_REFERENCE_RATE series."
        )

    if observation.missing_state is not None:
        return

    if not isinstance(observation.value, Decimal):
        raise TypeError(
            "market_series.fx_rate requires a Decimal value."
        )

    if observation.value <= 0:
        raise ValueError(
            "FX rate must be strictly positive."
        )
