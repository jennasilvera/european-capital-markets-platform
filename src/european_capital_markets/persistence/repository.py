"""Read-only query access over the canonical PostgreSQL store."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from european_capital_markets.domain.entities import IssuerRecord
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.issuer_identity import (
    IssuerIdentifierRecord,
)
from european_capital_markets.domain.issuer_identity import (
    resolve_issuer_identifier as resolve_domain_issuer_identifier,
)
from european_capital_markets.domain.lifecycle import (
    TransactionLifecycleEventRecord,
    derive_transaction_status,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
    TransactionStatus,
)


@dataclass(frozen=True, slots=True)
class CanonicalRepository:
    """Derived read access that preserves canonical domain semantics."""

    engine: Engine

    def get_issuer(
        self,
        issuer_id: str,
    ) -> IssuerRecord | None:
        """Return one canonical issuer by permanent ID."""

        validate_identifier(
            issuer_id,
            EntityType.ISSUER,
        )

        with _read_snapshot(self.engine) as connection:
            row = connection.execute(
                sa.text(
                    """
                    SELECT
                        issuer_id,
                        canonical_name
                    FROM issuers
                    WHERE issuer_id = :issuer_id
                    """
                ),
                {"issuer_id": issuer_id},
            ).mappings().one_or_none()

        if row is None:
            return None

        return IssuerRecord(
            issuer_id=row["issuer_id"],
            canonical_name=row["canonical_name"],
        )

    def resolve_issuer_identifier(
        self,
        *,
        identifier_type: IssuerIdentifierType,
        identifier_value: str,
        scope_type: IdentifierScopeType,
        scope_value: str | None,
        as_of_date: date,
    ) -> str | None:
        """Resolve an external identifier using canonical as-of semantics."""

        # Run the authoritative domain argument validation before touching the
        # database. An empty record set is sufficient because the resolver
        # validates the complete identifier namespace before matching records.
        resolve_domain_issuer_identifier(
            (),
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            scope_type=scope_type,
            scope_value=scope_value,
            as_of_date=as_of_date,
        )

        # Fetch the complete canonical identifier namespace. Validity-window
        # interpretation remains exclusively in the domain resolver below;
        # SQL is intentionally limited to record selection, not business
        # semantics.
        with _read_snapshot(self.engine) as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT
                        ii.issuer_identifier_row_id,
                        ii.issuer_id,
                        ii.identifier_type,
                        ii.identifier_value,
                        ii.scope_type,
                        ii.scope_value,
                        ii.assignment_valid_from,
                        ii.assignment_valid_to,
                        ii.notes,
                        iie.evidence_id,
                        iie.evidence_ordinal
                    FROM issuer_identifiers AS ii
                    LEFT JOIN issuer_identifier_evidence AS iie
                      ON iie.issuer_identifier_row_id
                         = ii.issuer_identifier_row_id
                    WHERE ii.identifier_type = :identifier_type
                      AND ii.identifier_value = :identifier_value
                      AND ii.scope_type = :scope_type
                      AND ii.scope_value
                          IS NOT DISTINCT FROM :scope_value
                    ORDER BY
                        ii.issuer_identifier_row_id,
                        iie.evidence_ordinal NULLS FIRST
                    """
                ),
                {
                    "identifier_type": identifier_type.value,
                    "identifier_value": identifier_value,
                    "scope_type": scope_type.value,
                    "scope_value": scope_value,
                },
            ).mappings().all()

        records = _identifier_records_from_rows(rows)

        return resolve_domain_issuer_identifier(
            records,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            scope_type=scope_type,
            scope_value=scope_value,
            as_of_date=as_of_date,
        )

    def get_transaction_status(
        self,
        transaction_id: str,
        *,
        as_of_date: date | None = None,
    ) -> TransactionStatus | None:
        """Derive transaction status from canonical lifecycle history."""

        # Preserve domain-level permanent-ID validation even when no database
        # lifecycle rows exist for the requested transaction.
        derive_transaction_status(
            transaction_id,
            (),
            as_of_date=as_of_date,
        )

        with _read_snapshot(self.engine) as connection:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT
                        tle.event_id,
                        tle.transaction_id,
                        tle.status,
                        tle.effective_date,
                        tle.event_order,
                        tle.notes,
                        tlee.evidence_id,
                        tlee.evidence_ordinal
                    FROM transaction_lifecycle_events AS tle
                    LEFT JOIN transaction_lifecycle_event_evidence AS tlee
                      ON tlee.event_id = tle.event_id
                    WHERE tle.transaction_id = :transaction_id
                    ORDER BY
                        tle.event_id,
                        tlee.evidence_ordinal NULLS FIRST
                    """
                ),
                {"transaction_id": transaction_id},
            ).mappings().all()

        events = _lifecycle_records_from_rows(rows)

        return derive_transaction_status(
            transaction_id,
            events,
            as_of_date=as_of_date,
        )


@contextmanager
def _read_snapshot(
    engine: Engine,
) -> Iterator[Connection]:
    """Yield one coherent read-only PostgreSQL snapshot."""

    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ",
    ) as connection, connection.begin():
        connection.execute(
            sa.text("SET TRANSACTION READ ONLY")
        )
        yield connection


def _identifier_records_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[IssuerIdentifierRecord, ...]:
    grouped: dict[
        int,
        tuple[Mapping[str, Any], list[str]],
    ] = {}

    for row in rows:
        row_id = int(row["issuer_identifier_row_id"])

        if row_id not in grouped:
            grouped[row_id] = (
                row,
                [],
            )

        evidence_id = row["evidence_id"]
        if evidence_id is not None:
            grouped[row_id][1].append(evidence_id)

    records: list[IssuerIdentifierRecord] = []

    for row_id in sorted(grouped):
        row, evidence_ids = grouped[row_id]

        records.append(
            IssuerIdentifierRecord(
                issuer_id=row["issuer_id"],
                identifier_type=IssuerIdentifierType(
                    row["identifier_type"]
                ),
                identifier_value=row["identifier_value"],
                scope_type=IdentifierScopeType(
                    row["scope_type"]
                ),
                evidence_ids=tuple(evidence_ids),
                scope_value=row["scope_value"],
                assignment_valid_from=row[
                    "assignment_valid_from"
                ],
                assignment_valid_to=row[
                    "assignment_valid_to"
                ],
                notes=row["notes"],
            )
        )

    return tuple(records)


def _lifecycle_records_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[TransactionLifecycleEventRecord, ...]:
    grouped: dict[
        str,
        tuple[Mapping[str, Any], list[str]],
    ] = {}

    for row in rows:
        event_id = row["event_id"]

        if event_id not in grouped:
            grouped[event_id] = (
                row,
                [],
            )

        evidence_id = row["evidence_id"]
        if evidence_id is not None:
            grouped[event_id][1].append(evidence_id)

    records: list[TransactionLifecycleEventRecord] = []

    for event_id in sorted(grouped):
        row, evidence_ids = grouped[event_id]

        records.append(
            TransactionLifecycleEventRecord(
                event_id=row["event_id"],
                transaction_id=row["transaction_id"],
                status=TransactionStatus(
                    row["status"]
                ),
                effective_date=row["effective_date"],
                event_order=row["event_order"],
                evidence_ids=tuple(evidence_ids),
                notes=row["notes"],
            )
        )

    return tuple(records)
