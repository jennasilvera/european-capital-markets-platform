from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    ValueClass,
    VerificationState,
)
from european_capital_markets.domain.terms import (
    FIELD_DEFINITIONS,
    CurrencyBinding,
    MetadataRequirement,
    ObservationFieldDefinition,
    ObservationUnit,
    ObservationValueType,
    get_field_definition,
    validate_field_catalog,
    validate_term_observation,
)


def _observation(
    *,
    subject_type: EntityType = EntityType.INSTRUMENT,
    subject_id: str = "INS000000001",
    field_name: str = "instrument.issue_size",
    value: object = Decimal("500000000"),
    unit: str | None = None,
    currency: str | None = "EUR",
) -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000100",
        subject_type=subject_type,
        subject_id=subject_id,
        field_name=field_name,
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        value=value,  # type: ignore[arg-type]
        value_class=ValueClass.ASSUMED,
        unit=unit,
        currency=currency,
        derivation_ref="test://terms-field-schema-assumption",
        notes="Test assumption for field-schema validation.",
    )


def test_default_field_catalog_is_unique() -> None:
    validate_field_catalog()


def test_duplicate_field_definition_is_rejected() -> None:
    definition = FIELD_DEFINITIONS[0]

    with pytest.raises(ValueError, match="Duplicate field definition"):
        validate_field_catalog(
            (
                definition,
                definition,
            )
        )


def test_field_name_prefix_must_match_subject_type() -> None:
    with pytest.raises(ValueError, match="must start"):
        ObservationFieldDefinition(
            field_name="transaction.issue_size",
            subject_type=EntityType.INSTRUMENT,
            value_type=ObservationValueType.DECIMAL,
            description="Invalid scope.",
        )


def test_required_unit_definition_requires_allowed_units() -> None:
    with pytest.raises(ValueError, match="allowed_units"):
        ObservationFieldDefinition(
            field_name="instrument.test_metric",
            subject_type=EntityType.INSTRUMENT,
            value_type=ObservationValueType.DECIMAL,
            description="Test metric.",
            unit_requirement=MetadataRequirement.REQUIRED,
        )


def test_issue_size_accepts_decimal_with_currency() -> None:
    validate_term_observation(_observation())


def test_issue_size_rejects_wrong_subject_scope() -> None:
    observation = _observation(
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
    )

    with pytest.raises(ValueError, match="requires subject type INSTRUMENT"):
        validate_term_observation(observation)


def test_decimal_field_rejects_float() -> None:
    observation = _observation(
        value=500000000.0,
    )

    with pytest.raises(TypeError, match="DECIMAL"):
        validate_term_observation(observation)


def test_monetary_field_requires_currency() -> None:
    observation = _observation(
        currency=None,
    )

    with pytest.raises(ValueError, match="requires currency"):
        validate_term_observation(observation)


def test_currency_code_must_be_uppercase_three_letter_code() -> None:
    with pytest.raises(ValueError, match="three-letter upper-case code"):
        _observation(
            currency="eur",
        )


def test_issue_size_forbids_unit_metadata() -> None:
    observation = _observation(
        unit="MILLIONS",
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_spread_requires_basis_point_unit() -> None:
    observation = _observation(
        field_name="instrument.spread_bps",
        value=Decimal("125"),
        unit=None,
        currency=None,
    )

    with pytest.raises(ValueError, match="requires unit"):
        validate_term_observation(observation)


def test_spread_rejects_percentage_unit() -> None:
    observation = _observation(
        field_name="instrument.spread_bps",
        value=Decimal("125"),
        unit="PERCENT",
        currency=None,
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_spread_accepts_basis_points() -> None:
    observation = _observation(
        field_name="instrument.spread_bps",
        value=Decimal("125"),
        unit="BASIS_POINTS",
        currency=None,
    )

    validate_term_observation(observation)


def test_transaction_aggregate_size_has_transaction_scope() -> None:
    observation = _observation(
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="transaction.aggregate_size",
        value=Decimal("1000000000"),
        currency="EUR",
    )

    validate_term_observation(observation)


def test_participation_shares_sold_has_relationship_scope() -> None:
    observation = _observation(
        subject_type=EntityType.PARTICIPATION,
        subject_id="PAR000000001",
        field_name="participation.shares_sold",
        value=Decimal("2500000"),
        unit="SHARES",
        currency=None,
    )

    validate_term_observation(observation)


def test_offer_price_requires_per_share_unit_and_currency() -> None:
    observation = _observation(
        field_name="instrument.offer_price_per_share",
        value=Decimal("24.50"),
        unit="PER_SHARE",
        currency="GBP",
    )

    validate_term_observation(observation)


def test_missing_value_does_not_require_currency_or_unit() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000101",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
    )

    validate_term_observation(observation)


def test_maturity_date_requires_date_value() -> None:
    observation = _observation(
        field_name="instrument.maturity_date",
        value="2031-09-17",
        currency=None,
    )

    with pytest.raises(TypeError, match="DATE"):
        validate_term_observation(observation)


def test_unknown_governed_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown governed observation field"):
        get_field_definition("instrument.unknown_metric")


def test_field_definition_rejects_uncontrolled_unit_values() -> None:
    with pytest.raises(TypeError, match="ObservationUnit"):
        ObservationFieldDefinition(
            field_name="instrument.test_metric",
            subject_type=EntityType.INSTRUMENT,
            value_type=ObservationValueType.DECIMAL,
            description="Test metric.",
            unit_requirement=MetadataRequirement.REQUIRED,
            allowed_units=frozenset(
                {"PERCENT"}  # type: ignore[arg-type]
            ),
        )


def test_instrument_currency_accepts_currency_code_value() -> None:
    observation = _observation(
        field_name="instrument.currency",
        value="EUR",
        currency=None,
    )

    validate_term_observation(observation)


def test_instrument_currency_rejects_arbitrary_string() -> None:
    observation = _observation(
        field_name="instrument.currency",
        value="EURO",
        currency=None,
    )

    with pytest.raises(TypeError, match="CURRENCY_CODE"):
        validate_term_observation(observation)


def test_missing_issue_size_still_rejects_forbidden_unit_metadata() -> None:
    observation = ObservationRecord(
        observation_id="OBS000000102",
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size",
        as_of_date=date(2026, 9, 17),
        verification_state=VerificationState.PENDING,
        missing_state=MissingDataState.PENDING_VERIFICATION,
        unit="MILLIONS",
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_multi_currency_tranches_keep_currency_at_instrument_level() -> None:
    euro_tranche = _observation(
        subject_id="INS000000001",
        value=Decimal("500000000"),
        currency="EUR",
    )
    sterling_tranche = _observation(
        subject_id="INS000000002",
        value=Decimal("350000000"),
        currency="GBP",
    )

    validate_term_observation(euro_tranche)
    validate_term_observation(sterling_tranche)

    assert euro_tranche.currency == "EUR"
    assert sterling_tranche.currency == "GBP"


def test_debt_issue_price_accepts_percent_of_par_only() -> None:
    observation = _observation(
        field_name="instrument.issue_price_percent_of_par",
        value=Decimal("99.375"),
        unit=ObservationUnit.PERCENT_OF_PAR.value,
        currency=None,
    )

    validate_term_observation(observation)


def test_debt_issue_price_rejects_per_share_unit() -> None:
    observation = _observation(
        field_name="instrument.issue_price_percent_of_par",
        value=Decimal("99.375"),
        unit=ObservationUnit.PER_SHARE.value,
        currency=None,
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_ecm_offer_price_rejects_percent_of_par_unit() -> None:
    observation = _observation(
        field_name="instrument.offer_price_per_share",
        value=Decimal("24.50"),
        unit=ObservationUnit.PERCENT_OF_PAR.value,
        currency="GBP",
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_discount_rejects_basis_point_unit() -> None:
    observation = _observation(
        field_name="instrument.discount_percent",
        value=Decimal("6.5"),
        unit=ObservationUnit.BASIS_POINTS.value,
        currency=None,
    )

    with pytest.raises(ValueError, match="does not permit unit"):
        validate_term_observation(observation)


def test_seller_gross_proceeds_remain_participation_scoped() -> None:
    first_seller = _observation(
        subject_type=EntityType.PARTICIPATION,
        subject_id="PAR000000001",
        field_name="participation.gross_proceeds",
        value=Decimal("125000000"),
        currency="EUR",
    )
    second_seller = _observation(
        subject_type=EntityType.PARTICIPATION,
        subject_id="PAR000000002",
        field_name="participation.gross_proceeds",
        value=Decimal("75000000"),
        currency="EUR",
    )

    validate_term_observation(first_seller)
    validate_term_observation(second_seller)

    assert first_seller.subject_id != second_seller.subject_id


def test_transaction_and_instrument_size_fields_are_distinct() -> None:
    aggregate = get_field_definition(
        "transaction.aggregate_size"
    )
    tranche = get_field_definition(
        "instrument.issue_size"
    )

    assert aggregate.subject_type is EntityType.TRANSACTION
    assert tranche.subject_type is EntityType.INSTRUMENT
    assert aggregate.field_name != tranche.field_name


def test_issue_size_uses_instrument_currency_binding() -> None:
    definition = get_field_definition(
        "instrument.issue_size"
    )

    assert (
        definition.currency_binding
        is CurrencyBinding.INSTRUMENT_CURRENCY
    )


def test_converted_issue_size_uses_observation_currency_binding() -> None:
    definition = get_field_definition(
        "instrument.issue_size_converted"
    )

    assert (
        definition.currency_binding
        is CurrencyBinding.OBSERVATION_CURRENCY
    )


def test_currency_bearing_field_requires_explicit_binding() -> None:
    with pytest.raises(ValueError, match="explicit currency binding"):
        ObservationFieldDefinition(
            field_name="transaction.test_amount",
            subject_type=EntityType.TRANSACTION,
            value_type=ObservationValueType.DECIMAL,
            description="Invalid unbound currency-bearing field.",
            currency_requirement=MetadataRequirement.REQUIRED,
        )


def test_instrument_currency_binding_requires_instrument_scope() -> None:
    with pytest.raises(ValueError, match="requires INSTRUMENT"):
        ObservationFieldDefinition(
            field_name="transaction.test_amount",
            subject_type=EntityType.TRANSACTION,
            value_type=ObservationValueType.DECIMAL,
            description="Invalid instrument-bound transaction field.",
            currency_requirement=MetadataRequirement.REQUIRED,
            currency_binding=CurrencyBinding.INSTRUMENT_CURRENCY,
        )


def test_converted_issue_size_requires_target_currency() -> None:
    observation = _observation(
        field_name="instrument.issue_size_converted",
        value=Decimal("550000000"),
        currency=None,
    )

    with pytest.raises(ValueError, match="requires currency"):
        validate_term_observation(observation)
