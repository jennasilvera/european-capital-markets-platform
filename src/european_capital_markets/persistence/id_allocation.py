"""PostgreSQL-backed allocation for canonical market-ingestion lineage IDs."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from european_capital_markets.domain.identifiers import format_identifier
from european_capital_markets.domain.taxonomy import EntityType
from european_capital_markets.ingestion.contracts import AllocatedLineageIds

_SEQUENCE_NAME_BY_ENTITY_TYPE = {
    EntityType.SOURCE: "canonical_source_id_seq",
    EntityType.EVIDENCE: "canonical_evidence_id_seq",
    EntityType.OBSERVATION: "canonical_observation_id_seq",
}


def allocate_market_lineage_ids(
    engine: Engine,
    datum_count: int,
) -> tuple[AllocatedLineageIds, ...]:
    """Allocate one SRC and one EVD/OBS pair per normalized market datum.

    Allocation is intentionally not idempotent. PostgreSQL sequence values are
    never treated as chronology and are not reclaimed after rollback or failed
    downstream work.

    A caller that needs retry replay must retain the returned allocation and
    reuse it for that same logical ingestion attempt.
    """

    _validate_datum_count(
        datum_count
    )

    with engine.begin() as connection:
        source_sequence = _allocate_sequence_values(
            connection,
            EntityType.SOURCE,
            1,
        )[0]

        evidence_sequences = _allocate_sequence_values(
            connection,
            EntityType.EVIDENCE,
            datum_count,
        )

        observation_sequences = _allocate_sequence_values(
            connection,
            EntityType.OBSERVATION,
            datum_count,
        )

    source_id = format_identifier(
        EntityType.SOURCE,
        source_sequence,
    )

    return tuple(
        AllocatedLineageIds(
            source_id=source_id,
            evidence_id=format_identifier(
                EntityType.EVIDENCE,
                evidence_sequence,
            ),
            observation_id=format_identifier(
                EntityType.OBSERVATION,
                observation_sequence,
            ),
        )
        for (
            evidence_sequence,
            observation_sequence,
        ) in zip(
            evidence_sequences,
            observation_sequences,
            strict=True,
        )
    )


def _validate_datum_count(
    datum_count: int,
) -> None:
    if (
        isinstance(
            datum_count,
            bool,
        )
        or not isinstance(
            datum_count,
            int,
        )
    ):
        raise TypeError(
            "datum_count must be an integer."
        )

    if datum_count < 1:
        raise ValueError(
            "datum_count must be positive."
        )


def _allocate_sequence_values(
    connection: Connection,
    entity_type: EntityType,
    count: int,
) -> tuple[int, ...]:
    """Consume `count` values from one frozen canonical namespace."""

    try:
        sequence_name = (
            _SEQUENCE_NAME_BY_ENTITY_TYPE[
                entity_type
            ]
        )
    except KeyError as exc:
        raise ValueError(
            "Only SOURCE, EVIDENCE, and OBSERVATION "
            "are allocated by the market-lineage allocator."
        ) from exc

    values = connection.execute(
        sa.text(
            """
            SELECT
                nextval(
                    CAST(
                        :sequence_name
                        AS regclass
                    )
                ) AS sequence_value
            FROM generate_series(
                1,
                :allocation_count
            )
            """
        ),
        {
            "sequence_name": sequence_name,
            "allocation_count": count,
        },
    ).scalars()

    return tuple(
        int(value)
        for value in values
    )
