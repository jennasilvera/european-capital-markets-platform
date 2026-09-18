from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from european_capital_markets.persistence.reader import _decode_scalar_value


def _row(
    *,
    scalar_type: str | None,
    text_value: str | None = None,
    integer_value: Decimal | None = None,
    decimal_value: Decimal | None = None,
    boolean_value: bool | None = None,
    date_value: date | None = None,
    datetime_value: datetime | None = None,
) -> dict[str, object | None]:
    return {
        "scalar_type": scalar_type,
        "text_value": text_value,
        "integer_value": integer_value,
        "decimal_value": decimal_value,
        "boolean_value": boolean_value,
        "date_value": date_value,
        "datetime_value": datetime_value,
    }


def test_missing_observation_decodes_to_none() -> None:
    assert _decode_scalar_value(
        _row(scalar_type=None)
    ) is None


def test_text_decodes_exactly() -> None:
    value = "canonical text"

    assert _decode_scalar_value(
        _row(
            scalar_type="TEXT",
            text_value=value,
        )
    ) == value


def test_integer_numeric_decodes_to_python_int() -> None:
    value = Decimal("123456789012345678901234567890")

    decoded = _decode_scalar_value(
        _row(
            scalar_type="INTEGER",
            integer_value=value,
        )
    )

    assert decoded == int(value)
    assert isinstance(decoded, int)
    assert not isinstance(decoded, bool)


def test_decimal_decodes_without_float_conversion() -> None:
    value = Decimal(
        "12345678901234567890.123456789012345678901234567890"
    )

    decoded = _decode_scalar_value(
        _row(
            scalar_type="DECIMAL",
            decimal_value=value,
        )
    )

    assert decoded == value
    assert isinstance(decoded, Decimal)


def test_boolean_decodes_exactly() -> None:
    decoded = _decode_scalar_value(
        _row(
            scalar_type="BOOLEAN",
            boolean_value=True,
        )
    )

    assert decoded is True


def test_date_decodes_as_date() -> None:
    value = date(2026, 9, 18)

    decoded = _decode_scalar_value(
        _row(
            scalar_type="DATE",
            date_value=value,
        )
    )

    assert decoded == value
    assert type(decoded) is date


def test_datetime_decodes_as_datetime() -> None:
    value = datetime(
        2026,
        9,
        18,
        12,
        30,
        tzinfo=UTC,
    )

    decoded = _decode_scalar_value(
        _row(
            scalar_type="DATETIME",
            datetime_value=value,
        )
    )

    assert decoded == value
    assert isinstance(decoded, datetime)


def test_fractional_integer_slot_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="fractional",
    ):
        _decode_scalar_value(
            _row(
                scalar_type="INTEGER",
                integer_value=Decimal("1.5"),
            )
        )


def test_unknown_scalar_discriminator_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported persisted scalar type",
    ):
        _decode_scalar_value(
            _row(scalar_type="UNKNOWN")
        )
