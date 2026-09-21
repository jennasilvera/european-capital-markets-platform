import pytest

from european_capital_markets.domain.taxonomy import EntityType
from european_capital_markets.persistence.id_allocation import (
    _validate_datum_count,
)


@pytest.mark.parametrize(
    "datum_count",
    [
        1,
        2,
        250,
    ],
)
def test_positive_integer_datum_count_is_valid(
    datum_count: int,
) -> None:
    _validate_datum_count(
        datum_count
    )


@pytest.mark.parametrize(
    "datum_count",
    [
        0,
        -1,
    ],
)
def test_non_positive_datum_count_is_rejected(
    datum_count: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="positive",
    ):
        _validate_datum_count(
            datum_count
        )


@pytest.mark.parametrize(
    "datum_count",
    [
        True,
        1.5,
        "1",
    ],
)
def test_non_integer_datum_count_is_rejected(
    datum_count: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="integer",
    ):
        _validate_datum_count(
            datum_count  # type: ignore[arg-type]
        )


def test_allocator_scope_is_lineage_only() -> None:
    from european_capital_markets.persistence import (
        id_allocation,
    )

    assert set(
        id_allocation._SEQUENCE_NAME_BY_ENTITY_TYPE
    ) == {
        EntityType.SOURCE,
        EntityType.EVIDENCE,
        EntityType.OBSERVATION,
    }
