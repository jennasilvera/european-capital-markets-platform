"""Transactional writer for validated canonical datasets."""

from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import EntityType


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


class MarketObservationAppendStatus(StrEnum):
    """Outcome of one canonical market-observation append attempt."""

    INSERTED = "INSERTED"
    ALREADY_PERSISTED = "ALREADY_PERSISTED"


class MarketObservationAppendConflictError(ValueError):
    """Raised when canonical IDs or controlled subjects conflict with storage."""


def persist_market_observation_batch(
    engine: Engine,
    dataset: CanonicalDataset,
) -> MarketObservationAppendStatus:
    """Append one governed market-observation batch against an existing series.

    The supplied dataset must retain the concrete market-series subject and its
    exactly one type-specific definition so normal canonical validation remains
    authoritative. Persistence does not reinsert or update that controlled
    subject.

    Canonical-ID replay semantics are explicit:

    - if every lineage ID is absent, the lineage batch is inserted atomically;
    - if every lineage ID already exists and is byte-for-byte equivalent at the
      canonical relational boundary, the operation returns ALREADY_PERSISTED;
    - partial presence or any content mismatch fails closed.

    A new retrieval with newly allocated SRC/EVD/OBS identifiers remains a new
    append even when it reports the same series, field, analytical date, and
    value as an earlier observation.
    """

    validate_canonical_dataset(dataset)

    series, definition = (
        _validate_market_observation_append_shape(
            dataset
        )
    )

    with engine.begin() as connection:
        _lock_and_validate_existing_market_series(
            connection,
            series,
            definition,
        )

        presence = _classify_lineage_presence(
            connection,
            dataset,
        )

        if presence == "PRESENT":
            _require_existing_market_lineage_matches(
                connection,
                dataset,
            )

            result = (
                MarketObservationAppendStatus.ALREADY_PERSISTED
            )
        else:
            _insert_sources(
                connection,
                dataset,
            )
            _insert_evidence(
                connection,
                dataset,
            )
            _insert_observations(
                connection,
                dataset,
            )
            _insert_observation_evidence(
                connection,
                dataset,
            )
            _insert_observation_inputs(
                connection,
                dataset,
            )

            result = MarketObservationAppendStatus.INSERTED

        connection.execute(
            sa.text(
                "SET CONSTRAINTS ALL IMMEDIATE"
            )
        )

    return result


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
    _insert_policy_rates(connection, dataset)
    _insert_government_yields(connection, dataset)
    _insert_swap_rates(connection, dataset)
    _insert_credit_spreads(connection, dataset)
    _insert_equity_indices(connection, dataset)
    _insert_volatility_indices(connection, dataset)

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



def _insert_policy_rates(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.policy_rates:
        connection.execute(
            sa.text(
                """
                INSERT INTO policy_rate_definitions (
                    market_series_id,
                    authority,
                    jurisdiction,
                    currency,
                    rate_name,
                    convention_ref
                )
                VALUES (
                    :market_series_id,
                    :authority,
                    :jurisdiction,
                    :currency,
                    :rate_name,
                    :convention_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "authority": record.authority,
                "jurisdiction": record.jurisdiction,
                "currency": record.currency,
                "rate_name": record.rate_name,
                "convention_ref": record.convention_ref,
            },
        )


def _insert_government_yields(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.government_yields:
        connection.execute(
            sa.text(
                """
                INSERT INTO government_yield_definitions (
                    market_series_id,
                    sovereign,
                    jurisdiction,
                    currency,
                    tenor_months,
                    benchmark_ref,
                    convention_ref
                )
                VALUES (
                    :market_series_id,
                    :sovereign,
                    :jurisdiction,
                    :currency,
                    :tenor_months,
                    :benchmark_ref,
                    :convention_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "sovereign": record.sovereign,
                "jurisdiction": record.jurisdiction,
                "currency": record.currency,
                "tenor_months": record.tenor_months,
                "benchmark_ref": record.benchmark_ref,
                "convention_ref": record.convention_ref,
            },
        )


def _insert_swap_rates(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.swap_rates:
        connection.execute(
            sa.text(
                """
                INSERT INTO swap_rate_definitions (
                    market_series_id,
                    currency,
                    tenor_months,
                    floating_rate_ref,
                    fixed_leg_convention_ref,
                    convention_ref
                )
                VALUES (
                    :market_series_id,
                    :currency,
                    :tenor_months,
                    :floating_rate_ref,
                    :fixed_leg_convention_ref,
                    :convention_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "currency": record.currency,
                "tenor_months": record.tenor_months,
                "floating_rate_ref": record.floating_rate_ref,
                "fixed_leg_convention_ref": (
                    record.fixed_leg_convention_ref
                ),
                "convention_ref": record.convention_ref,
            },
        )


def _insert_credit_spreads(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.credit_spreads:
        connection.execute(
            sa.text(
                """
                INSERT INTO credit_spread_definitions (
                    market_series_id,
                    benchmark_family,
                    currency,
                    credit_universe,
                    rating_segment,
                    sector_segment,
                    spread_measure,
                    convention_ref
                )
                VALUES (
                    :market_series_id,
                    :benchmark_family,
                    :currency,
                    :credit_universe,
                    :rating_segment,
                    :sector_segment,
                    :spread_measure,
                    :convention_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "benchmark_family": record.benchmark_family,
                "currency": record.currency,
                "credit_universe": record.credit_universe,
                "rating_segment": record.rating_segment,
                "sector_segment": record.sector_segment,
                "spread_measure": record.spread_measure,
                "convention_ref": record.convention_ref,
            },
        )


def _insert_equity_indices(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.equity_indices:
        connection.execute(
            sa.text(
                """
                INSERT INTO equity_index_definitions (
                    market_series_id,
                    index_name,
                    universe,
                    index_variant_ref,
                    methodology_ref
                )
                VALUES (
                    :market_series_id,
                    :index_name,
                    :universe,
                    :index_variant_ref,
                    :methodology_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "index_name": record.index_name,
                "universe": record.universe,
                "index_variant_ref": record.index_variant_ref,
                "methodology_ref": record.methodology_ref,
            },
        )


def _insert_volatility_indices(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    for record in dataset.volatility_indices:
        connection.execute(
            sa.text(
                """
                INSERT INTO volatility_index_definitions (
                    market_series_id,
                    index_name,
                    underlying_ref,
                    horizon_days,
                    methodology_ref
                )
                VALUES (
                    :market_series_id,
                    :index_name,
                    :underlying_ref,
                    :horizon_days,
                    :methodology_ref
                )
                """
            ),
            {
                "market_series_id": record.market_series_id,
                "index_name": record.index_name,
                "underlying_ref": record.underlying_ref,
                "horizon_days": record.horizon_days,
                "methodology_ref": record.methodology_ref,
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


_MARKET_DEFINITION_TABLE_BY_TYPE: dict[type[Any], str] = {
    FXReferenceRateDefinitionRecord:
        "fx_reference_rate_definitions",
    PolicyRateDefinitionRecord:
        "policy_rate_definitions",
    GovernmentYieldDefinitionRecord:
        "government_yield_definitions",
    SwapRateDefinitionRecord:
        "swap_rate_definitions",
    CreditSpreadDefinitionRecord:
        "credit_spread_definitions",
    EquityIndexDefinitionRecord:
        "equity_index_definitions",
    VolatilityIndexDefinitionRecord:
        "volatility_index_definitions",
}


def _validate_market_observation_append_shape(
    dataset: CanonicalDataset,
) -> tuple[MarketSeriesRecord, Any]:
    """Require one controlled market-series lineage append unit."""

    non_market_collections = {
        "issuers": dataset.issuers,
        "transactions": dataset.transactions,
        "instruments": dataset.instruments,
        "issuer_identifiers": dataset.issuer_identifiers,
        "parties": dataset.parties,
        "participations": dataset.participations,
        "lifecycle_events": dataset.lifecycle_events,
    }

    populated_non_market = sorted(
        name
        for name, records
        in non_market_collections.items()
        if records
    )

    if populated_non_market:
        raise ValueError(
            "Market-observation append batches must not "
            "contain non-market canonical entities: "
            f"{populated_non_market!r}."
        )

    if len(dataset.market_series) != 1:
        raise ValueError(
            "Market-observation append requires exactly "
            "one market-series subject."
        )

    definitions = (
        *dataset.fx_reference_rates,
        *dataset.policy_rates,
        *dataset.government_yields,
        *dataset.swap_rates,
        *dataset.credit_spreads,
        *dataset.equity_indices,
        *dataset.volatility_indices,
    )

    if len(definitions) != 1:
        raise ValueError(
            "Market-observation append requires exactly "
            "one type-specific market-series definition."
        )

    if len(dataset.sources) != 1:
        raise ValueError(
            "Market-observation append requires exactly "
            "one canonical source record."
        )

    if not dataset.evidence:
        raise ValueError(
            "Market-observation append requires at least "
            "one canonical evidence record."
        )

    if not dataset.observations:
        raise ValueError(
            "Market-observation append requires at least "
            "one canonical observation."
        )

    series = dataset.market_series[0]

    for observation in dataset.observations:
        if (
            observation.subject_type
            is not EntityType.MARKET_SERIES
            or observation.subject_id
            != series.market_series_id
        ):
            raise ValueError(
                "Every observation in a market append batch "
                "must reference its single market-series subject."
            )

    return (
        series,
        definitions[0],
    )


def _lock_and_validate_existing_market_series(
    connection: Connection,
    series: MarketSeriesRecord,
    definition: Any,
) -> None:
    """Lock and require exact controlled-subject equivalence."""

    row = connection.execute(
        sa.text(
            """
            SELECT
                market_series_id,
                series_type,
                series_label
            FROM market_series
            WHERE market_series_id = :market_series_id
            FOR UPDATE
            """
        ),
        {
            "market_series_id":
                series.market_series_id,
        },
    ).mappings().one_or_none()

    if row is None:
        raise MarketObservationAppendConflictError(
            "Market-observation append requires an "
            "already-persisted market series: "
            f"{series.market_series_id!r}."
        )

    expected_series = {
        "market_series_id":
            series.market_series_id,
        "series_type":
            series.series_type.value,
        "series_label":
            series.series_label,
    }

    if dict(row) != expected_series:
        raise MarketObservationAppendConflictError(
            "Persisted market-series identity does not "
            "match the append handoff for "
            f"{series.market_series_id!r}."
        )

    try:
        table_name = (
            _MARKET_DEFINITION_TABLE_BY_TYPE[
                type(definition)
            ]
        )
    except KeyError as exc:
        raise ValueError(
            "Unsupported market-series definition type "
            f"for append persistence: "
            f"{type(definition).__name__}."
        ) from exc

    column_names = tuple(
        field.name
        for field in fields(
            definition
        )
    )

    columns_sql = ", ".join(
        column_names
    )

    definition_row = connection.execute(
        sa.text(
            f"""
            SELECT
                {columns_sql}
            FROM {table_name}
            WHERE market_series_id = :market_series_id
            FOR UPDATE
            """
        ),
        {
            "market_series_id":
                series.market_series_id,
        },
    ).mappings().one_or_none()

    expected_definition = {
        field.name:
            getattr(
                definition,
                field.name,
            )
        for field in fields(
            definition
        )
    }

    if (
        definition_row is None
        or dict(definition_row)
        != expected_definition
    ):
        raise MarketObservationAppendConflictError(
            "Persisted type-specific market-series "
            "definition does not match the append handoff "
            f"for {series.market_series_id!r}."
        )


def _classify_lineage_presence(
    connection: Connection,
    dataset: CanonicalDataset,
) -> str:
    """Classify one lineage batch as fully absent or fully present."""

    identities: list[
        tuple[str, bool]
    ] = []

    source = dataset.sources[0]

    identities.append(
        (
            f"source:{source.source_id}",
            _canonical_row_exists(
                connection,
                table_name="sources",
                id_column="source_id",
                identifier=source.source_id,
            ),
        )
    )

    for record in dataset.evidence:
        identities.append(
            (
                f"evidence:{record.evidence_id}",
                _canonical_row_exists(
                    connection,
                    table_name="evidence",
                    id_column="evidence_id",
                    identifier=record.evidence_id,
                ),
            )
        )

    for record in dataset.observations:
        identities.append(
            (
                f"observation:{record.observation_id}",
                _canonical_row_exists(
                    connection,
                    table_name="observations",
                    id_column="observation_id",
                    identifier=record.observation_id,
                ),
            )
        )

    present = tuple(
        name
        for name, exists
        in identities
        if exists
    )

    missing = tuple(
        name
        for name, exists
        in identities
        if not exists
    )

    if not present:
        return "ABSENT"

    if not missing:
        return "PRESENT"

    raise MarketObservationAppendConflictError(
        "Partial canonical-ID replay is not permitted. "
        f"Present IDs: {present!r}; "
        f"missing IDs: {missing!r}."
    )


def _canonical_row_exists(
    connection: Connection,
    *,
    table_name: str,
    id_column: str,
    identifier: str,
) -> bool:
    """Return whether one canonical-ID row exists."""

    allowed = {
        ("sources", "source_id"),
        ("evidence", "evidence_id"),
        ("observations", "observation_id"),
    }

    if (
        table_name,
        id_column,
    ) not in allowed:
        raise ValueError(
            "Unsupported canonical existence lookup."
        )

    return (
        connection.execute(
            sa.text(
                f"""
                SELECT 1
                FROM {table_name}
                WHERE {id_column} = :identifier
                """
            ),
            {
                "identifier": identifier,
            },
        ).scalar_one_or_none()
        is not None
    )


def _require_existing_market_lineage_matches(
    connection: Connection,
    dataset: CanonicalDataset,
) -> None:
    """Require a fully present canonical-ID replay to match exactly."""

    source = dataset.sources[0]

    _require_existing_source_matches(
        connection,
        source,
    )

    expected_source_evidence_ids = tuple(
        sorted(
            record.evidence_id
            for record in dataset.evidence
        )
    )

    actual_source_evidence_ids = tuple(
        row["evidence_id"]
        for row in connection.execute(
            sa.text(
                """
                SELECT evidence_id
                FROM evidence
                WHERE source_id = :source_id
                ORDER BY evidence_id
                FOR SHARE
                """
            ),
            {
                "source_id": source.source_id,
            },
        ).mappings()
    )

    if (
        actual_source_evidence_ids
        != expected_source_evidence_ids
    ):
        raise MarketObservationAppendConflictError(
            "Existing source evidence namespace does not "
            "match the replayed retrieval for "
            f"{source.source_id!r}."
        )

    for record in dataset.evidence:
        _require_existing_evidence_matches(
            connection,
            record,
        )

    for record in dataset.observations:
        _require_existing_observation_matches(
            connection,
            record,
        )


def _require_existing_source_matches(
    connection: Connection,
    record: SourceRecord,
) -> None:
    row = connection.execute(
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
            WHERE source_id = :source_id
            FOR SHARE
            """
        ),
        {
            "source_id": record.source_id,
        },
    ).mappings().one()

    expected = {
        "source_id": record.source_id,
        "source_tier": int(record.tier),
        "source_type":
            record.source_type.value,
        "publisher": record.publisher,
        "title": record.title,
        "access_date": record.access_date,
        "document_date":
            record.document_date,
        "publication_date":
            record.publication_date,
        "url": record.url,
        "archived_location":
            record.archived_location,
        "document_version":
            record.document_version,
        "notes": record.notes,
    }

    if dict(row) != expected:
        raise MarketObservationAppendConflictError(
            "Existing source content does not match "
            f"canonical replay ID {record.source_id!r}."
        )


def _require_existing_evidence_matches(
    connection: Connection,
    record: EvidenceRecord,
) -> None:
    row = connection.execute(
        sa.text(
            """
            SELECT
                evidence_id,
                source_id,
                locator,
                label,
                notes
            FROM evidence
            WHERE evidence_id = :evidence_id
            FOR SHARE
            """
        ),
        {
            "evidence_id":
                record.evidence_id,
        },
    ).mappings().one()

    expected = {
        "evidence_id":
            record.evidence_id,
        "source_id":
            record.source_id,
        "locator":
            record.locator,
        "label":
            record.label,
        "notes":
            record.notes,
    }

    if dict(row) != expected:
        raise MarketObservationAppendConflictError(
            "Existing evidence content does not match "
            f"canonical replay ID {record.evidence_id!r}."
        )


def _require_existing_observation_matches(
    connection: Connection,
    record: ObservationRecord,
) -> None:
    scalar_storage = _encode_scalar_value(
        record
    )

    row = connection.execute(
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
            WHERE observation_id = :observation_id
            FOR SHARE
            """
        ),
        {
            "observation_id":
                record.observation_id,
        },
    ).mappings().one()

    expected = {
        "observation_id":
            record.observation_id,
        "subject_type":
            record.subject_type.value,
        "subject_id":
            record.subject_id,
        "field_name":
            record.field_name,
        "as_of_date":
            record.as_of_date,
        "verification_state":
            record.verification_state.value,
        "verified_at":
            record.verified_at,
        **scalar_storage,
        "value_class": (
            record.value_class.value
            if record.value_class
            is not None
            else None
        ),
        "missing_state": (
            record.missing_state.value
            if record.missing_state
            is not None
            else None
        ),
        "unit":
            record.unit,
        "currency":
            record.currency,
        "derivation_ref":
            record.derivation_ref,
        "notes":
            record.notes,
    }

    if dict(row) != expected:
        raise MarketObservationAppendConflictError(
            "Existing observation content does not match "
            f"canonical replay ID {record.observation_id!r}."
        )

    actual_evidence = tuple(
        (
            row["evidence_id"],
            row["evidence_ordinal"],
        )
        for row in connection.execute(
            sa.text(
                """
                SELECT
                    evidence_id,
                    evidence_ordinal
                FROM observation_evidence
                WHERE observation_id = :observation_id
                ORDER BY evidence_ordinal
                FOR SHARE
                """
            ),
            {
                "observation_id":
                    record.observation_id,
            },
        ).mappings()
    )

    expected_evidence = tuple(
        (
            evidence_id,
            ordinal,
        )
        for ordinal, evidence_id
        in enumerate(
            record.evidence_ids
        )
    )

    if actual_evidence != expected_evidence:
        raise MarketObservationAppendConflictError(
            "Existing observation evidence does not match "
            f"canonical replay ID {record.observation_id!r}."
        )

    actual_inputs = tuple(
        (
            row["input_observation_id"],
            row["input_ordinal"],
        )
        for row in connection.execute(
            sa.text(
                """
                SELECT
                    input_observation_id,
                    input_ordinal
                FROM observation_inputs
                WHERE derived_observation_id = :observation_id
                ORDER BY input_ordinal
                FOR SHARE
                """
            ),
            {
                "observation_id":
                    record.observation_id,
            },
        ).mappings()
    )

    expected_inputs = tuple(
        (
            input_id,
            ordinal,
        )
        for ordinal, input_id
        in enumerate(
            record.input_observation_ids
        )
    )

    if actual_inputs != expected_inputs:
        raise MarketObservationAppendConflictError(
            "Existing observation inputs do not match "
            f"canonical replay ID {record.observation_id!r}."
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
