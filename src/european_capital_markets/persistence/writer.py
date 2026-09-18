"""Transactional writer for validated canonical datasets."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.lineage import ObservationRecord


def persist_canonical_dataset(
    engine: Engine,
    dataset: CanonicalDataset,
) -> None:
    """Validate and persist one canonical dataset atomically.

    The domain model remains authoritative for analytical semantics. The
    relational backend supplements it with structural, referential, and
    cross-row integrity constraints.

    This operation is insert-oriented. Any validation or database failure
    aborts the complete logical write unit.
    """

    validate_canonical_dataset(dataset)

    with engine.begin() as connection:
        _persist_validated_dataset(connection, dataset)

        # Force every deferred PostgreSQL constraint to execute before this
        # function leaves the transaction body. Any violation therefore raises
        # here and causes Engine.begin() to roll back the entire dataset.
        connection.execute(
            sa.text("SET CONSTRAINTS ALL IMMEDIATE")
        )


def _persist_validated_dataset(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    """Persist a dataset that has already passed canonical validation."""

    _insert_issuers(connection, dataset)
    _insert_parties(connection, dataset)
    _insert_transactions(connection, dataset)
    _insert_instruments(connection, dataset)
    _insert_market_series(connection, dataset)
    _insert_fx_reference_rates(connection, dataset)

    _insert_sources(connection, dataset)
    _insert_evidence(connection, dataset)

    _insert_issuer_identifiers(connection, dataset)
    _insert_participations(connection, dataset)
    _insert_lifecycle_events(connection, dataset)

    _insert_observations(connection, dataset)
    _insert_observation_evidence(connection, dataset)
    _insert_observation_inputs(connection, dataset)


def _insert_observation_subject(
    connection: Connection,
    *,
    subject_type: str,
    subject_id: str,
) -> None:
    """Register one already-inserted observable canonical entity."""

    connection.execute(
        sa.text(
            """
            INSERT INTO observation_subjects (
                subject_type,
                subject_id
            )
            VALUES (
                :subject_type,
                :subject_id
            )
            """
        ),
        {
            "subject_type": subject_type,
            "subject_id": subject_id,
        },
    )


def _insert_issuers(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.issuers:
        connection.execute(
            sa.text(
                """
                INSERT INTO issuers (
                    issuer_id,
                    canonical_name
                )
                VALUES (
                    :issuer_id,
                    :canonical_name
                )
                """
            ),
            {
                "issuer_id": record.issuer_id,
                "canonical_name": record.canonical_name,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="ISSUER",
            subject_id=record.issuer_id,
        )


def _insert_parties(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.parties:
        connection.execute(
            sa.text(
                """
                INSERT INTO parties (
                    party_id,
                    party_type,
                    linked_issuer_id,
                    canonical_name
                )
                VALUES (
                    :party_id,
                    :party_type,
                    :linked_issuer_id,
                    :canonical_name
                )
                """
            ),
            {
                "party_id": record.party_id,
                "party_type": record.party_type.value,
                "linked_issuer_id": record.linked_issuer_id,
                "canonical_name": record.canonical_name,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="PARTY",
            subject_id=record.party_id,
        )


def _insert_transactions(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.transactions:
        connection.execute(
            sa.text(
                """
                INSERT INTO transactions (
                    transaction_id,
                    primary_issuer_id,
                    product_family,
                    transaction_label
                )
                VALUES (
                    :transaction_id,
                    :primary_issuer_id,
                    :product_family,
                    :transaction_label
                )
                """
            ),
            {
                "transaction_id": record.transaction_id,
                "primary_issuer_id": record.primary_issuer_id,
                "product_family": record.product_family.value,
                "transaction_label": record.transaction_label,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="TRANSACTION",
            subject_id=record.transaction_id,
        )


def _insert_instruments(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.instruments:
        connection.execute(
            sa.text(
                """
                INSERT INTO instruments (
                    instrument_id,
                    transaction_id,
                    instrument_label
                )
                VALUES (
                    :instrument_id,
                    :transaction_id,
                    :instrument_label
                )
                """
            ),
            {
                "instrument_id": record.instrument_id,
                "transaction_id": record.transaction_id,
                "instrument_label": record.instrument_label,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="INSTRUMENT",
            subject_id=record.instrument_id,
        )


def _insert_market_series(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.market_series:
        connection.execute(
            sa.text(
                """
                INSERT INTO market_series (
                    market_series_id,
                    series_type,
                    series_label
                )
                VALUES (
                    :market_series_id,
                    :series_type,
                    :series_label
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "series_type": record.series_type.value,
                "series_label": record.series_label,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="MARKET_SERIES",
            subject_id=record.market_series_id,
        )


def _insert_fx_reference_rates(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.fx_reference_rates:
        connection.execute(
            sa.text(
                """
                INSERT INTO fx_reference_rate_definitions (
                    market_series_id,
                    base_currency,
                    quote_currency,
                    convention_ref
                )
                VALUES (
                    :market_series_id,
                    :base_currency,
                    :quote_currency,
                    :convention_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "base_currency": record.base_currency,
                "quote_currency": record.quote_currency,
                "convention_ref": record.convention_ref,
            },
        )


def _insert_sources(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.sources:
        connection.execute(
            sa.text(
                """
                INSERT INTO sources (
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
                )
                VALUES (
                    :source_id,
                    :source_tier,
                    :source_type,
                    :publisher,
                    :title,
                    :access_date,
                    :document_date,
                    :publication_date,
                    :url,
                    :archived_location,
                    :document_version,
                    :notes
                )
                """
            ),
            {
                "source_id": record.source_id,
                "source_tier": int(record.tier),
                "source_type": record.source_type.value,
                "publisher": record.publisher,
                "title": record.title,
                "access_date": record.access_date,
                "document_date": record.document_date,
                "publication_date": record.publication_date,
                "url": record.url,
                "archived_location": record.archived_location,
                "document_version": record.document_version,
                "notes": record.notes,
            },
        )


def _insert_evidence(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.evidence:
        connection.execute(
            sa.text(
                """
                INSERT INTO evidence (
                    evidence_id,
                    source_id,
                    locator,
                    label,
                    notes
                )
                VALUES (
                    :evidence_id,
                    :source_id,
                    :locator,
                    :label,
                    :notes
                )
                """
            ),
            {
                "evidence_id": record.evidence_id,
                "source_id": record.source_id,
                "locator": record.locator,
                "label": record.label,
                "notes": record.notes,
            },
        )


def _insert_issuer_identifiers(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.issuer_identifiers:
        row_id = connection.execute(
            sa.text(
                """
                INSERT INTO issuer_identifiers (
                    issuer_id,
                    identifier_type,
                    identifier_value,
                    scope_type,
                    scope_value,
                    assignment_valid_from,
                    assignment_valid_to,
                    notes
                )
                VALUES (
                    :issuer_id,
                    :identifier_type,
                    :identifier_value,
                    :scope_type,
                    :scope_value,
                    :assignment_valid_from,
                    :assignment_valid_to,
                    :notes
                )
                RETURNING issuer_identifier_row_id
                """
            ),
            {
                "issuer_id": record.issuer_id,
                "identifier_type": record.identifier_type.value,
                "identifier_value": record.identifier_value,
                "scope_type": record.scope_type.value,
                "scope_value": record.scope_value,
                "assignment_valid_from": record.assignment_valid_from,
                "assignment_valid_to": record.assignment_valid_to,
                "notes": record.notes,
            },
        ).scalar_one()

        for ordinal, evidence_id in enumerate(record.evidence_ids):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO issuer_identifier_evidence (
                        issuer_identifier_row_id,
                        evidence_id,
                        evidence_ordinal
                    )
                    VALUES (
                        :issuer_identifier_row_id,
                        :evidence_id,
                        :evidence_ordinal
                    )
                    """
                ),
                {
                    "issuer_identifier_row_id": row_id,
                    "evidence_id": evidence_id,
                    "evidence_ordinal": ordinal,
                },
            )


def _insert_participations(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.participations:
        connection.execute(
            sa.text(
                """
                INSERT INTO participations (
                    participation_id,
                    party_id,
                    transaction_id,
                    instrument_id,
                    role,
                    notes
                )
                VALUES (
                    :participation_id,
                    :party_id,
                    :transaction_id,
                    :instrument_id,
                    :role,
                    :notes
                )
                """
            ),
            {
                "participation_id": record.participation_id,
                "party_id": record.party_id,
                "transaction_id": record.transaction_id,
                "instrument_id": record.instrument_id,
                "role": record.role.value,
                "notes": record.notes,
            },
        )

        _insert_observation_subject(
            connection,
            subject_type="PARTICIPATION",
            subject_id=record.participation_id,
        )

        for ordinal, evidence_id in enumerate(record.evidence_ids):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO participation_evidence (
                        participation_id,
                        evidence_id,
                        evidence_ordinal
                    )
                    VALUES (
                        :participation_id,
                        :evidence_id,
                        :evidence_ordinal
                    )
                    """
                ),
                {
                    "participation_id": record.participation_id,
                    "evidence_id": evidence_id,
                    "evidence_ordinal": ordinal,
                },
            )


def _insert_lifecycle_events(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.lifecycle_events:
        connection.execute(
            sa.text(
                """
                INSERT INTO transaction_lifecycle_events (
                    event_id,
                    transaction_id,
                    status,
                    effective_date,
                    event_order,
                    notes
                )
                VALUES (
                    :event_id,
                    :transaction_id,
                    :status,
                    :effective_date,
                    :event_order,
                    :notes
                )
                """
            ),
            {
                "event_id": record.event_id,
                "transaction_id": record.transaction_id,
                "status": record.status.value,
                "effective_date": record.effective_date,
                "event_order": record.event_order,
                "notes": record.notes,
            },
        )

        for ordinal, evidence_id in enumerate(record.evidence_ids):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO transaction_lifecycle_event_evidence (
                        event_id,
                        evidence_id,
                        evidence_ordinal
                    )
                    VALUES (
                        :event_id,
                        :evidence_id,
                        :evidence_ordinal
                    )
                    """
                ),
                {
                    "event_id": record.event_id,
                    "evidence_id": evidence_id,
                    "evidence_ordinal": ordinal,
                },
            )


def _insert_observations(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    # Insert every observation before its dependency junctions so calculated
    # observations may reference inputs regardless of tuple ordering.
    for record in dataset.observations:
        scalar_storage = _encode_scalar_value(record)

        connection.execute(
            sa.text(
                """
                INSERT INTO observations (
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
                )
                VALUES (
                    :observation_id,
                    :subject_type,
                    :subject_id,
                    :field_name,
                    :as_of_date,
                    :verification_state,
                    :verified_at,
                    :scalar_type,
                    :text_value,
                    :integer_value,
                    :decimal_value,
                    :boolean_value,
                    :date_value,
                    :datetime_value,
                    :value_class,
                    :missing_state,
                    :unit,
                    :currency,
                    :derivation_ref,
                    :notes
                )
                """
            ),
            {
                "observation_id": record.observation_id,
                "subject_type": record.subject_type.value,
                "subject_id": record.subject_id,
                "field_name": record.field_name,
                "as_of_date": record.as_of_date,
                "verification_state": record.verification_state.value,
                "verified_at": record.verified_at,
                **scalar_storage,
                "value_class": (
                    record.value_class.value
                    if record.value_class is not None
                    else None
                ),
                "missing_state": (
                    record.missing_state.value
                    if record.missing_state is not None
                    else None
                ),
                "unit": record.unit,
                "currency": record.currency,
                "derivation_ref": record.derivation_ref,
                "notes": record.notes,
            },
        )


def _insert_observation_evidence(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.observations:
        for ordinal, evidence_id in enumerate(record.evidence_ids):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO observation_evidence (
                        observation_id,
                        evidence_id,
                        evidence_ordinal
                    )
                    VALUES (
                        :observation_id,
                        :evidence_id,
                        :evidence_ordinal
                    )
                    """
                ),
                {
                    "observation_id": record.observation_id,
                    "evidence_id": evidence_id,
                    "evidence_ordinal": ordinal,
                },
            )


def _insert_observation_inputs(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.observations:
        for ordinal, input_id in enumerate(
            record.input_observation_ids
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO observation_inputs (
                        derived_observation_id,
                        input_observation_id,
                        input_ordinal
                    )
                    VALUES (
                        :derived_observation_id,
                        :input_observation_id,
                        :input_ordinal
                    )
                    """
                ),
                {
                    "derived_observation_id": record.observation_id,
                    "input_observation_id": input_id,
                    "input_ordinal": ordinal,
                },
            )


def _empty_scalar_storage() -> dict[str, Any]:
    return {
        "scalar_type": None,
        "text_value": None,
        "integer_value": None,
        "decimal_value": None,
        "boolean_value": None,
        "date_value": None,
        "datetime_value": None,
    }


def _encode_scalar_value(
    record: ObservationRecord,
) -> dict[str, Any]:
    """Map a domain scalar into exactly one canonical database value slot."""

    storage = _empty_scalar_storage()
    value = record.value

    if value is None:
        return storage

    # bool must precede int because bool is a subclass of int.
    if isinstance(value, bool):
        storage["scalar_type"] = "BOOLEAN"
        storage["boolean_value"] = value
        return storage

    if isinstance(value, int):
        storage["scalar_type"] = "INTEGER"
        storage["integer_value"] = value
        return storage

    if isinstance(value, Decimal):
        storage["scalar_type"] = "DECIMAL"
        storage["decimal_value"] = value
        return storage

    # datetime must precede date because datetime is a subclass of date.
    if isinstance(value, datetime):
        storage["scalar_type"] = "DATETIME"
        storage["datetime_value"] = value
        return storage

    if isinstance(value, date):
        storage["scalar_type"] = "DATE"
        storage["date_value"] = value
        return storage

    if isinstance(value, str):
        storage["scalar_type"] = "TEXT"
        storage["text_value"] = value
        return storage

    raise TypeError(
        "Unsupported canonical observation scalar type: "
        f"{type(value).__name__}."
    )
