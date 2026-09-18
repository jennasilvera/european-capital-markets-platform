from datetime import UTC, date, datetime
from decimal import Decimal

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence.writer import _encode_scalar_value


def _observation(value: object) -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.ISSUER,
        subject_id="ISS000000001",
        field_name="test.value",
        as_of_date=date(2026, 9, 18),
        verification_state=VerificationState.PENDING,
        value=value,  # type: ignore[arg-type]
        value_class=ValueClass.ASSUMED,
        derivation_ref="tests/persistence-writer",
    )


def test_boolean_uses_boolean_slot_not_integer_slot() -> None:
    encoded = _encode_scalar_value(_observation(True))

    assert encoded["scalar_type"] == "BOOLEAN"
    assert encoded["boolean_value"] is True
    assert encoded["integer_value"] is None


def test_integer_uses_exact_integer_slot() -> None:
    value = 123456789012345678901234567890

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "INTEGER"
    assert encoded["integer_value"] == value
    assert encoded["decimal_value"] is None


def test_decimal_uses_decimal_slot_without_float_conversion() -> None:
    value = Decimal(
        "12345678901234567890.123456789012345678901234567890"
    )

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DECIMAL"
    assert encoded["decimal_value"] == value
    assert isinstance(encoded["decimal_value"], Decimal)


def test_datetime_uses_datetime_slot_not_date_slot() -> None:
    value = datetime(2026, 9, 18, 14, 30, tzinfo=UTC)

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DATETIME"
    assert encoded["datetime_value"] == value
    assert encoded["date_value"] is None


def test_date_uses_date_slot() -> None:
    value = date(2026, 9, 18)

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DATE"
    assert encoded["date_value"] == value


def test_text_uses_text_slot() -> None:
    encoded = _encode_scalar_value(_observation("canonical value"))

    assert encoded["scalar_type"] == "TEXT"
    assert encoded["text_value"] == "canonical value"
