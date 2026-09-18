"""Snapshot-consistent reconstruction of canonical PostgreSQL datasets."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.entities import (
    InstrumentRecord,
    IssuerRecord,
    TransactionRecord,
)
from european_capital_markets.domain.issuer_identity import (
    IssuerIdentifierRecord,
)
from european_capital_markets.domain.lifecycle import (
    TransactionLifecycleEventRecord,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
)
from european_capital_markets.domain.participations import (
    ParticipationRecord,
)
from european_capital_markets.domain.parties import PartyRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
    MarketSeriesType,
    MissingDataState,
    ParticipantRole,
    PartyType,
    ProductFamily,
    SourceTier,
    SourceType,
    TransactionStatus,
    ValueClass,
    VerificationState,
)


def load_canonical_dataset(engine: Engine) -> CanonicalDataset:
    """Reconstruct and validate the complete supported canonical dataset.

    Reconstruction occurs inside one PostgreSQL REPEATABLE READ, read-only
    transaction so every table is observed from one coherent database
    snapshot. Persistence-only registry rows, surrogate keys, and junction
    ordinals are consumed by the adapter but do not leak into domain records.
    """

    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ",
    ) as connection, connection.begin():
        connection.execute(
            sa.text("SET TRANSACTION READ ONLY")
        )

        dataset = _load_canonical_dataset(connection)
        validate_canonical_dataset(dataset)

        return dataset


def _load_canonical_dataset(
    connection: Connection,
) -> CanonicalDataset:
    identifier_evidence = _load_ordered_relation(
        connection,
        """
        SELECT
            issuer_identifier_row_id AS parent_id,
            evidence_id AS related_id
        FROM issuer_identifier_evidence
        ORDER BY
            issuer_identifier_row_id,
            evidence_ordinal
        """,
    )

    participation_evidence = _load_ordered_relation(
        connection,
        """
        SELECT
            participation_id AS parent_id,
            evidence_id AS related_id
        FROM participation_evidence
        ORDER BY
            participation_id,
            evidence_ordinal
        """,
    )

    lifecycle_evidence = _load_ordered_relation(
        connection,
        """
        SELECT
            event_id AS parent_id,
            evidence_id AS related_id
        FROM transaction_lifecycle_event_evidence
        ORDER BY
            event_id,
            evidence_ordinal
        """,
    )

    observation_evidence = _load_ordered_relation(
        connection,
        """
        SELECT
            observation_id AS parent_id,
            evidence_id AS related_id
        FROM observation_evidence
        ORDER BY
            observation_id,
            evidence_ordinal
        """,
    )

    observation_inputs = _load_ordered_relation(
        connection,
        """
        SELECT
            derived_observation_id AS parent_id,
            input_observation_id AS related_id
        FROM observation_inputs
        ORDER BY
            derived_observation_id,
            input_ordinal
        """,
    )

    return CanonicalDataset(
        issuers=_load_issuers(connection),
        transactions=_load_transactions(connection),
        instruments=_load_instruments(connection),
        issuer_identifiers=_load_issuer_identifiers(
            connection,
            identifier_evidence,
        ),
        parties=_load_parties(connection),
        participations=_load_participations(
            connection,
            participation_evidence,
        ),
        lifecycle_events=_load_lifecycle_events(
            connection,
            lifecycle_evidence,
        ),
        market_series=_load_market_series(connection),
        fx_reference_rates=_load_fx_reference_rates(connection),
        sources=_load_sources(connection),
        evidence=_load_evidence(connection),
        observations=_load_observations(
            connection,
            observation_evidence,
            observation_inputs,
        ),
    )


def _load_ordered_relation(
    connection: Connection,
    statement: str,
) -> dict[Any, tuple[str, ...]]:
    grouped: dict[Any, list[str]] = {}

    rows = connection.execute(
        sa.text(statement)
    ).mappings()

    for row in rows:
        grouped.setdefault(
            row["parent_id"],
            [],
        ).append(row["related_id"])

    return {
        parent_id: tuple(related_ids)
        for parent_id, related_ids in grouped.items()
    }


def _load_issuers(
    connection: Connection,
) -> tuple[IssuerRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                issuer_id,
                canonical_name
            FROM issuers
            ORDER BY issuer_id
            """
        )
    ).mappings()

    return tuple(
        IssuerRecord(
            issuer_id=row["issuer_id"],
            canonical_name=row["canonical_name"],
        )
        for row in rows
    )


def _load_transactions(
    connection: Connection,
) -> tuple[TransactionRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                transaction_id,
                primary_issuer_id,
                product_family,
                transaction_label
            FROM transactions
            ORDER BY transaction_id
            """
        )
    ).mappings()

    return tuple(
        TransactionRecord(
            transaction_id=row["transaction_id"],
            primary_issuer_id=row["primary_issuer_id"],
            product_family=ProductFamily(
                row["product_family"]
            ),
            transaction_label=row["transaction_label"],
        )
        for row in rows
    )


def _load_instruments(
    connection: Connection,
) -> tuple[InstrumentRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                instrument_id,
                transaction_id,
                instrument_label
            FROM instruments
            ORDER BY instrument_id
            """
        )
    ).mappings()

    return tuple(
        InstrumentRecord(
            instrument_id=row["instrument_id"],
            transaction_id=row["transaction_id"],
            instrument_label=row["instrument_label"],
        )
        for row in rows
    )


def _load_issuer_identifiers(
    connection: Connection,
    evidence_by_row: dict[Any, tuple[str, ...]],
) -> tuple[IssuerIdentifierRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                issuer_identifier_row_id,
                issuer_id,
                identifier_type,
                identifier_value,
                scope_type,
                scope_value,
                assignment_valid_from,
                assignment_valid_to,
                notes
            FROM issuer_identifiers
            ORDER BY
                issuer_id,
                identifier_type,
                identifier_value,
                scope_type,
                scope_value NULLS FIRST,
                assignment_valid_from NULLS FIRST,
                assignment_valid_to NULLS FIRST,
                issuer_identifier_row_id
            """
        )
    ).mappings()

    return tuple(
        IssuerIdentifierRecord(
            issuer_id=row["issuer_id"],
            identifier_type=IssuerIdentifierType(
                row["identifier_type"]
            ),
            identifier_value=row["identifier_value"],
            scope_type=IdentifierScopeType(
                row["scope_type"]
            ),
            evidence_ids=evidence_by_row.get(
                row["issuer_identifier_row_id"],
                (),
            ),
            scope_value=row["scope_value"],
            assignment_valid_from=row[
                "assignment_valid_from"
            ],
            assignment_valid_to=row[
                "assignment_valid_to"
            ],
            notes=row["notes"],
        )
        for row in rows
    )


def _load_parties(
    connection: Connection,
) -> tuple[PartyRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                party_id,
                party_type,
                linked_issuer_id,
                canonical_name
            FROM parties
            ORDER BY party_id
            """
        )
    ).mappings()

    return tuple(
        PartyRecord(
            party_id=row["party_id"],
            party_type=PartyType(row["party_type"]),
            linked_issuer_id=row["linked_issuer_id"],
            canonical_name=row["canonical_name"],
        )
        for row in rows
    )


def _load_participations(
    connection: Connection,
    evidence_by_participation: dict[Any, tuple[str, ...]],
) -> tuple[ParticipationRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                participation_id,
                party_id,
                transaction_id,
                instrument_id,
                role,
                notes
            FROM participations
            ORDER BY participation_id
            """
        )
    ).mappings()

    return tuple(
        ParticipationRecord(
            participation_id=row["participation_id"],
            party_id=row["party_id"],
            transaction_id=row["transaction_id"],
            role=ParticipantRole(row["role"]),
            evidence_ids=evidence_by_participation.get(
                row["participation_id"],
                (),
            ),
            instrument_id=row["instrument_id"],
            notes=row["notes"],
        )
        for row in rows
    )


def _load_lifecycle_events(
    connection: Connection,
    evidence_by_event: dict[Any, tuple[str, ...]],
) -> tuple[TransactionLifecycleEventRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                event_id,
                transaction_id,
                status,
                effective_date,
                event_order,
                notes
            FROM transaction_lifecycle_events
            ORDER BY event_id
            """
        )
    ).mappings()

    return tuple(
        TransactionLifecycleEventRecord(
            event_id=row["event_id"],
            transaction_id=row["transaction_id"],
            status=TransactionStatus(row["status"]),
            effective_date=row["effective_date"],
            event_order=row["event_order"],
            evidence_ids=evidence_by_event.get(
                row["event_id"],
                (),
            ),
            notes=row["notes"],
        )
        for row in rows
    )


def _load_market_series(
    connection: Connection,
) -> tuple[MarketSeriesRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                market_series_id,
                series_type,
                series_label
            FROM market_series
            ORDER BY market_series_id
            """
        )
    ).mappings()

    return tuple(
        MarketSeriesRecord(
            market_series_id=row["market_series_id"],
            series_type=MarketSeriesType(
                row["series_type"]
            ),
            series_label=row["series_label"],
        )
        for row in rows
    )


def _load_fx_reference_rates(
    connection: Connection,
) -> tuple[FXReferenceRateDefinitionRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                market_series_id,
                base_currency,
                quote_currency,
                convention_ref
            FROM fx_reference_rate_definitions
            ORDER BY market_series_id
            """
        )
    ).mappings()

    return tuple(
        FXReferenceRateDefinitionRecord(
            market_series_id=row["market_series_id"],
            base_currency=row["base_currency"],
            quote_currency=row["quote_currency"],
            convention_ref=row["convention_ref"],
        )
        for row in rows
    )


def _load_sources(
    connection: Connection,
) -> tuple[SourceRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                source_id,
                source_tier,
                source_type,
                publisher,
                title,
                access_date,
                document_date,
                publication_date,
                url,
                archived_location,
                document_version,
                notes
            FROM sources
            ORDER BY source_id
            """
        )
    ).mappings()

    return tuple(
        SourceRecord(
            source_id=row["source_id"],
            tier=SourceTier(row["source_tier"]),
            source_type=SourceType(
                row["source_type"]
            ),
            publisher=row["publisher"],
            title=row["title"],
            access_date=row["access_date"],
            document_date=row["document_date"],
            publication_date=row["publication_date"],
            url=row["url"],
            archived_location=row["archived_location"],
            document_version=row["document_version"],
            notes=row["notes"],
        )
        for row in rows
    )


def _load_evidence(
    connection: Connection,
) -> tuple[EvidenceRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                evidence_id,
                source_id,
                locator,
                label,
                notes
            FROM evidence
            ORDER BY evidence_id
            """
        )
    ).mappings()

    return tuple(
        EvidenceRecord(
            evidence_id=row["evidence_id"],
            source_id=row["source_id"],
            locator=row["locator"],
            label=row["label"],
            notes=row["notes"],
        )
        for row in rows
    )


def _load_observations(
    connection: Connection,
    evidence_by_observation: dict[Any, tuple[str, ...]],
    inputs_by_observation: dict[Any, tuple[str, ...]],
) -> tuple[ObservationRecord, ...]:
    rows = connection.execute(
        sa.text(
            """
            SELECT
                observation_id,
                subject_type,
                subject_id,
                field_name,
                as_of_date,
                verification_state,
                verified_at,
                scalar_type,
                text_value,
                integer_value,
                decimal_value,
                boolean_value,
                date_value,
                datetime_value,
                value_class,
                missing_state,
                unit,
                currency,
                derivation_ref,
                notes
            FROM observations
            ORDER BY observation_id
            """
        )
    ).mappings()

    return tuple(
        ObservationRecord(
            observation_id=row["observation_id"],
            subject_type=EntityType(row["subject_type"]),
            subject_id=row["subject_id"],
            field_name=row["field_name"],
            as_of_date=row["as_of_date"],
            verification_state=VerificationState(
                row["verification_state"]
            ),
            verified_at=row["verified_at"],
            value=_decode_scalar_value(row),
            value_class=(
                ValueClass(row["value_class"])
                if row["value_class"] is not None
                else None
            ),
            missing_state=(
                MissingDataState(row["missing_state"])
                if row["missing_state"] is not None
                else None
            ),
            unit=row["unit"],
            currency=row["currency"],
            evidence_ids=evidence_by_observation.get(
                row["observation_id"],
                (),
            ),
            input_observation_ids=inputs_by_observation.get(
                row["observation_id"],
                (),
            ),
            derivation_ref=row["derivation_ref"],
            notes=row["notes"],
        )
        for row in rows
    )


def _require_slot_value(
    row: Mapping[str, Any],
    slot_name: str,
    scalar_type: str,
) -> Any:
    value = row[slot_name]

    if value is None:
        raise ValueError(
            f"{scalar_type} observation has no {slot_name}."
        )

    return value


def _decode_scalar_value(
    row: Mapping[str, Any],
) -> str | int | Decimal | bool | date | datetime | None:
    """Decode one canonical typed observation slot without precision loss."""

    scalar_type = row["scalar_type"]

    if scalar_type is None:
        return None

    if scalar_type == "TEXT":
        value = _require_slot_value(
            row,
            "text_value",
            scalar_type,
        )
        if not isinstance(value, str):
            raise TypeError("TEXT slot did not return str.")
        return value

    if scalar_type == "INTEGER":
        value = _require_slot_value(
            row,
            "integer_value",
            scalar_type,
        )
        if not isinstance(value, Decimal):
            raise TypeError(
                "INTEGER NUMERIC slot did not return Decimal."
            )
        if value != value.to_integral_value():
            raise ValueError(
                "INTEGER NUMERIC slot contains a fractional value."
            )
        return int(value)

    if scalar_type == "DECIMAL":
        value = _require_slot_value(
            row,
            "decimal_value",
            scalar_type,
        )
        if not isinstance(value, Decimal):
            raise TypeError(
                "DECIMAL NUMERIC slot did not return Decimal."
            )
        return value

    if scalar_type == "BOOLEAN":
        value = _require_slot_value(
            row,
            "boolean_value",
            scalar_type,
        )
        if not isinstance(value, bool):
            raise TypeError("BOOLEAN slot did not return bool.")
        return value

    if scalar_type == "DATE":
        value = _require_slot_value(
            row,
            "date_value",
            scalar_type,
        )
        if not isinstance(value, date) or isinstance(
            value,
            datetime,
        ):
            raise TypeError("DATE slot did not return date.")
        return value

    if scalar_type == "DATETIME":
        value = _require_slot_value(
            row,
            "datetime_value",
            scalar_type,
        )
        if not isinstance(value, datetime):
            raise TypeError(
                "DATETIME slot did not return datetime."
            )
        return value

    raise ValueError(
        f"Unsupported persisted scalar type: {scalar_type!r}."
    )
