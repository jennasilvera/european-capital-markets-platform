"""Governed capital-markets observation field definitions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from re import fullmatch

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.taxonomy import EntityType


class ObservationValueType(StrEnum):
    """Expected scalar type for a governed observation field."""

    STRING = "STRING"
    CURRENCY_CODE = "CURRENCY_CODE"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"


class MetadataRequirement(StrEnum):
    """Whether unit or currency metadata is permitted or required."""

    FORBIDDEN = "FORBIDDEN"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class ObservationUnit(StrEnum):
    """Controlled unit vocabulary for governed observation fields."""

    PERCENT = "PERCENT"
    PERCENT_OF_PAR = "PERCENT_OF_PAR"
    BASIS_POINTS = "BASIS_POINTS"
    PER_SHARE = "PER_SHARE"
    SHARES = "SHARES"


@dataclass(frozen=True, slots=True)
class ObservationFieldDefinition:
    """Schema metadata for one governed analytical observation field."""

    field_name: str
    subject_type: EntityType
    value_type: ObservationValueType
    description: str
    unit_requirement: MetadataRequirement = MetadataRequirement.FORBIDDEN
    allowed_units: frozenset[ObservationUnit] = frozenset()
    currency_requirement: MetadataRequirement = MetadataRequirement.FORBIDDEN

    def __post_init__(self) -> None:
        expected_prefix = f"{self.subject_type.value.lower()}."

        if not self.field_name.startswith(expected_prefix):
            raise ValueError(
                f"field_name must start with {expected_prefix!r}."
            )

        if not self.description.strip():
            raise ValueError("description must not be blank.")

        if (
            self.unit_requirement is MetadataRequirement.FORBIDDEN
            and self.allowed_units
        ):
            raise ValueError(
                "A unit-forbidden field cannot define allowed_units."
            )

        if (
            self.unit_requirement is MetadataRequirement.REQUIRED
            and not self.allowed_units
        ):
            raise ValueError(
                "A unit-required field must define allowed_units."
            )

        for unit in self.allowed_units:
            if not isinstance(unit, ObservationUnit):
                raise TypeError(
                    "allowed_units must contain ObservationUnit values."
                )


FIELD_DEFINITIONS: tuple[ObservationFieldDefinition, ...] = (
    ObservationFieldDefinition(
        field_name="market_series.fx_rate",
        subject_type=EntityType.MARKET_SERIES,
        value_type=ObservationValueType.DECIMAL,
        description=(
            "FX reference rate expressed as quote-currency units "
            "per one base-currency unit."
        ),
    ),
    ObservationFieldDefinition(
        field_name="transaction.aggregate_size",
        subject_type=EntityType.TRANSACTION,
        value_type=ObservationValueType.DECIMAL,
        description=(
            "Explicit or governed calculated aggregate transaction size."
        ),
        currency_requirement=MetadataRequirement.REQUIRED,
    ),
    ObservationFieldDefinition(
        field_name="instrument.currency",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.CURRENCY_CODE,
        description="Instrument denomination or issuance currency.",
    ),
    ObservationFieldDefinition(
        field_name="instrument.issue_size",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Principal or issuance amount for the instrument.",
        currency_requirement=MetadataRequirement.REQUIRED,
    ),
    ObservationFieldDefinition(
        field_name="instrument.issue_price_percent_of_par",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Debt issue price expressed as percent of par.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.PERCENT_OF_PAR}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.coupon_percent",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Stated coupon rate.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.PERCENT}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.yield_percent",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Observed or calculated instrument yield.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.PERCENT}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.spread_bps",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Credit spread expressed in basis points.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.BASIS_POINTS}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.margin_bps",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Floating-rate margin expressed in basis points.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.BASIS_POINTS}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.maturity_date",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DATE,
        description="Contractual instrument maturity date.",
    ),
    ObservationFieldDefinition(
        field_name="instrument.book_size",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="Instrument-level investor order-book size.",
        currency_requirement=MetadataRequirement.REQUIRED,
    ),
    ObservationFieldDefinition(
        field_name="instrument.new_issue_premium_bps",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="New-issue premium expressed in basis points.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.BASIS_POINTS}),
    ),
    ObservationFieldDefinition(
        field_name="instrument.offer_price_per_share",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="ECM offer price per share.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.PER_SHARE}),
        currency_requirement=MetadataRequirement.REQUIRED,
    ),
    ObservationFieldDefinition(
        field_name="instrument.discount_percent",
        subject_type=EntityType.INSTRUMENT,
        value_type=ObservationValueType.DECIMAL,
        description="ECM offer or placement discount.",
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.PERCENT}),
    ),
    ObservationFieldDefinition(
        field_name="participation.shares_sold",
        subject_type=EntityType.PARTICIPATION,
        value_type=ObservationValueType.DECIMAL,
        description=(
            "Shares sold attributable to one participation relationship."
        ),
        unit_requirement=MetadataRequirement.REQUIRED,
        allowed_units=frozenset({ObservationUnit.SHARES}),
    ),
    ObservationFieldDefinition(
        field_name="participation.gross_proceeds",
        subject_type=EntityType.PARTICIPATION,
        value_type=ObservationValueType.DECIMAL,
        description=(
            "Gross proceeds attributable to one participation relationship "
            "before transaction costs or other deductions."
        ),
        currency_requirement=MetadataRequirement.REQUIRED,
    ),
)


FIELD_DEFINITION_BY_NAME: dict[
    str,
    ObservationFieldDefinition,
] = {
    definition.field_name: definition
    for definition in FIELD_DEFINITIONS
}


def validate_field_catalog(
    definitions: tuple[
        ObservationFieldDefinition,
        ...,
    ] = FIELD_DEFINITIONS,
) -> None:
    """Validate field-name uniqueness for a catalog."""

    field_names: set[str] = set()

    for definition in definitions:
        if definition.field_name in field_names:
            raise ValueError(
                f"Duplicate field definition: {definition.field_name!r}"
            )

        field_names.add(definition.field_name)


def get_field_definition(
    field_name: str,
) -> ObservationFieldDefinition:
    """Return one governed field definition."""

    try:
        return FIELD_DEFINITION_BY_NAME[field_name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown governed observation field: {field_name!r}"
        ) from exc


def validate_term_observation(
    observation: ObservationRecord,
) -> None:
    """Validate one economic-term observation against its field definition."""

    definition = get_field_definition(
        observation.field_name
    )

    if observation.subject_type is not definition.subject_type:
        raise ValueError(
            f"{observation.field_name!r} requires subject type "
            f"{definition.subject_type.value}."
        )

    is_missing = observation.missing_state is not None

    if not is_missing:
        _validate_value_type(
            observation.value,
            definition.value_type,
            observation.field_name,
        )

    _validate_unit(
        observation.unit,
        definition,
        enforce_required=not is_missing,
    )

    _validate_currency(
        observation.currency,
        definition,
        enforce_required=not is_missing,
    )


def _validate_value_type(
    value: object,
    expected: ObservationValueType,
    field_name: str,
) -> None:
    valid = False

    if expected is ObservationValueType.STRING:
        valid = isinstance(value, str)
    elif expected is ObservationValueType.CURRENCY_CODE:
        valid = (
            isinstance(value, str)
            and fullmatch(r"[A-Z]{3}", value) is not None
        )
    elif expected is ObservationValueType.INTEGER:
        valid = (
            isinstance(value, int)
            and not isinstance(value, bool)
        )
    elif expected is ObservationValueType.DECIMAL:
        valid = isinstance(value, Decimal)
    elif expected is ObservationValueType.BOOLEAN:
        valid = isinstance(value, bool)
    elif expected is ObservationValueType.DATE:
        valid = type(value) is date

    if not valid:
        raise TypeError(
            f"{field_name!r} requires {expected.value} value."
        )


def _validate_unit(
    unit: str | None,
    definition: ObservationFieldDefinition,
    *,
    enforce_required: bool,
) -> None:
    requirement = definition.unit_requirement

    if requirement is MetadataRequirement.FORBIDDEN:
        if unit is not None:
            raise ValueError(
                f"{definition.field_name!r} does not permit unit metadata."
            )
        return

    if (
        requirement is MetadataRequirement.REQUIRED
        and enforce_required
        and unit is None
    ):
        raise ValueError(
            f"{definition.field_name!r} requires unit metadata."
        )

    if unit is None:
        return

    if not unit.strip():
        raise ValueError("unit must not be blank.")

    allowed_unit_values = {
        allowed_unit.value
        for allowed_unit in definition.allowed_units
    }

    if (
        allowed_unit_values
        and unit not in allowed_unit_values
    ):
        raise ValueError(
            f"{definition.field_name!r} does not permit unit {unit!r}."
        )


def _validate_currency(
    currency: str | None,
    definition: ObservationFieldDefinition,
    *,
    enforce_required: bool,
) -> None:
    requirement = definition.currency_requirement

    if requirement is MetadataRequirement.FORBIDDEN:
        if currency is not None:
            raise ValueError(
                f"{definition.field_name!r} does not permit currency metadata."
            )
        return

    if (
        requirement is MetadataRequirement.REQUIRED
        and enforce_required
        and currency is None
    ):
        raise ValueError(
            f"{definition.field_name!r} requires currency metadata."
        )

    if currency is None:
        return

    if fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError(
            "currency must use a three-letter uppercase code."
        )
