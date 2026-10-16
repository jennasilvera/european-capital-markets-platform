"""Internal exact Decimal representation shared by analytical results."""

from decimal import Decimal


def canonical_decimal(value: Decimal) -> Decimal:
    """Remove scale-only differences without rounding or using Decimal context."""

    if value.is_zero():
        return Decimal(0)
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while digits[end - 1] == 0:
        end -= 1
    return Decimal((sign, digits[:end], exponent + len(digits) - end))
