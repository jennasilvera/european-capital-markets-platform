"""Create the initial canonical capital-markets persistence schema.

Revision ID: 0001_canonical_schema
Revises:
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_canonical_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ID_LENGTH = 12

OBSERVABLE_SUBJECT_TYPES = (
    "ISSUER",
    "PARTY",
    "PARTICIPATION",
    "TRANSACTION",
    "INSTRUMENT",
    "MARKET_SERIES",
)

PARTY_TYPES = (
    "CORPORATE",
    "FINANCIAL_INSTITUTION",
    "FUND",
    "GOVERNMENT",
    "INDIVIDUAL",
    "SPECIAL_PURPOSE_VEHICLE",
    "OTHER",
)

PARTICIPANT_ROLES = (
    "LEGAL_ISSUER",
    "BORROWER",
    "GUARANTOR",
    "SPONSOR",
    "SELLING_SHAREHOLDER",
    "ACQUISITION_VEHICLE",
)

PRODUCT_FAMILIES = (
    "ECM",
    "IG_DCM",
    "LEVERAGED_FINANCE",
    "EQUITY_LINKED",
)

TRANSACTION_STATUSES = (
    "ANNOUNCED",
    "MARKETING",
    "LAUNCHED",
    "PRICED",
    "ALLOCATED",
    "SETTLED",
    "POSTPONED",
    "WITHDRAWN",
    "CANCELLED",
)

MARKET_SERIES_TYPES = (
    "FX_REFERENCE_RATE",
)

SOURCE_TYPES = (
    "PROSPECTUS",
    "OFFERING_DOCUMENT",
    "ISSUER_ANNOUNCEMENT",
    "EXCHANGE_ANNOUNCEMENT",
    "REGULATORY_FILING",
    "FINANCIAL_REPORT",
    "INVESTOR_PRESENTATION",
    "RATING_AGENCY_PUBLICATION",
    "CENTRAL_BANK_PUBLICATION",
    "OFFICIAL_STATISTICS",
    "MARKET_DATA",
    "FINANCIAL_NEWS",
    "ANALYST_WORKPAPER",
    "OTHER",
)

ISSUER_IDENTIFIER_TYPES = (
    "LEI",
    "TICKER",
    "COMPANY_REGISTRATION_NUMBER",
    "VENDOR_IDENTIFIER",
    "OTHER",
)

IDENTIFIER_SCOPE_TYPES = (
    "GLOBAL",
    "TRADING_VENUE",
    "REGISTRY",
    "VENDOR",
    "OTHER",
)

VALUE_CLASSES = (
    "DISCLOSED",
    "CALCULATED",
    "ESTIMATED",
    "ASSUMED",
)

VERIFICATION_STATES = (
    "PRIMARY_VERIFIED",
    "SECONDARY_VERIFIED",
    "CROSS_VERIFIED",
    "PENDING",
    "CONFLICT",
    "UNAVAILABLE",
)

VERIFIED_STATES = (
    "PRIMARY_VERIFIED",
    "SECONDARY_VERIFIED",
    "CROSS_VERIFIED",
)

MISSING_DATA_STATES = (
    "NOT_DISCLOSED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "PENDING_VERIFICATION",
)

SCALAR_TYPES = (
    "TEXT",
    "INTEGER",
    "DECIMAL",
    "BOOLEAN",
    "DATE",
    "DATETIME",
)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _enum_check(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IN ({_sql_values(values)})"


def _canonical_id_check(column_name: str, prefix: str) -> str:
    return (
        f"{column_name} ~ '^{prefix}[0-9]{{9}}$' "
        f"AND {column_name} <> '{prefix}000000000'"
    )


def _restrict_fk(
    target: str,
) -> sa.ForeignKey:
    return sa.ForeignKey(
        target,
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def upgrade() -> None:
    """Apply the initial canonical persistence schema."""

    # GiST equality operator classes for text are required by the
    # issuer-identifier exclusion constraints below.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "issuers",
        sa.Column(
            "issuer_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "canonical_name",
            sa.Text(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "issuer_id",
            name="pk_issuers",
        ),
        sa.CheckConstraint(
            _canonical_id_check("issuer_id", "ISS"),
            name="ck_issuers_id_shape",
        ),
        sa.CheckConstraint(
            "btrim(canonical_name) <> ''",
            name="ck_issuers_canonical_name_nonblank",
        ),
    )

    op.create_table(
        "parties",
        sa.Column(
            "party_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "party_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "linked_issuer_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("issuers.issuer_id"),
            nullable=True,
        ),
        sa.Column(
            "canonical_name",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "party_id",
            name="pk_parties",
        ),
        sa.UniqueConstraint(
            "linked_issuer_id",
            name="uq_parties_linked_issuer",
        ),
        sa.CheckConstraint(
            _canonical_id_check("party_id", "PTY"),
            name="ck_parties_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check("party_type", PARTY_TYPES),
            name="ck_parties_party_type",
        ),
        sa.CheckConstraint(
            """
            (
                linked_issuer_id IS NOT NULL
                AND canonical_name IS NULL
            )
            OR
            (
                linked_issuer_id IS NULL
                AND canonical_name IS NOT NULL
                AND btrim(canonical_name) <> ''
            )
            """,
            name="ck_parties_issuer_name_xor",
        ),
    )

    op.create_table(
        "transactions",
        sa.Column(
            "transaction_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "primary_issuer_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("issuers.issuer_id"),
            nullable=False,
        ),
        sa.Column(
            "product_family",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "transaction_label",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "transaction_id",
            name="pk_transactions",
        ),
        sa.CheckConstraint(
            _canonical_id_check("transaction_id", "TXN"),
            name="ck_transactions_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check("product_family", PRODUCT_FAMILIES),
            name="ck_transactions_product_family",
        ),
        sa.CheckConstraint(
            """
            transaction_label IS NULL
            OR btrim(transaction_label) <> ''
            """,
            name="ck_transactions_label_nonblank",
        ),
    )

    op.create_table(
        "instruments",
        sa.Column(
            "instrument_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("transactions.transaction_id"),
            nullable=False,
        ),
        sa.Column(
            "instrument_label",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "instrument_id",
            name="pk_instruments",
        ),
        sa.UniqueConstraint(
            "instrument_id",
            "transaction_id",
            name="uq_instruments_id_transaction",
        ),
        sa.CheckConstraint(
            _canonical_id_check("instrument_id", "INS"),
            name="ck_instruments_id_shape",
        ),
        sa.CheckConstraint(
            """
            instrument_label IS NULL
            OR btrim(instrument_label) <> ''
            """,
            name="ck_instruments_label_nonblank",
        ),
    )

    op.create_table(
        "participations",
        sa.Column(
            "participation_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "party_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("parties.party_id"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("transactions.transaction_id"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.String(length=ID_LENGTH),
            nullable=True,
        ),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "participation_id",
            name="pk_participations",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id", "transaction_id"],
            [
                "instruments.instrument_id",
                "instruments.transaction_id",
            ],
            name="fk_participations_instrument_transaction",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint(
            _canonical_id_check(
                "participation_id",
                "PAR",
            ),
            name="ck_participations_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check("role", PARTICIPANT_ROLES),
            name="ck_participations_role",
        ),
        sa.CheckConstraint(
            """
            notes IS NULL
            OR btrim(notes) <> ''
            """,
            name="ck_participations_notes_nonblank",
        ),
    )

    op.create_index(
        "uq_participations_transaction_scope",
        "participations",
        [
            "party_id",
            "transaction_id",
            "role",
        ],
        unique=True,
        postgresql_where=sa.text(
            "instrument_id IS NULL"
        ),
    )

    op.create_index(
        "uq_participations_instrument_scope",
        "participations",
        [
            "party_id",
            "transaction_id",
            "instrument_id",
            "role",
        ],
        unique=True,
        postgresql_where=sa.text(
            "instrument_id IS NOT NULL"
        ),
    )

    op.create_table(
        "market_series",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "series_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "series_label",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_market_series",
        ),
        sa.CheckConstraint(
            _canonical_id_check(
                "market_series_id",
                "MKS",
            ),
            name="ck_market_series_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check(
                "series_type",
                MARKET_SERIES_TYPES,
            ),
            name="ck_market_series_type",
        ),
        sa.CheckConstraint(
            """
            series_label IS NULL
            OR btrim(series_label) <> ''
            """,
            name="ck_market_series_label_nonblank",
        ),
    )

    op.create_table(
        "fx_reference_rate_definitions",
        sa.Column(
            "market_series_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "market_series.market_series_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "base_currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "quote_currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "convention_ref",
            sa.Text(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "market_series_id",
            name="pk_fx_reference_rate_definitions",
        ),
        sa.UniqueConstraint(
            "base_currency",
            "quote_currency",
            "convention_ref",
            name="uq_fx_reference_rate_identity",
        ),
        sa.CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$'",
            name="ck_fx_reference_rate_base_currency",
        ),
        sa.CheckConstraint(
            "quote_currency ~ '^[A-Z]{3}$'",
            name="ck_fx_reference_rate_quote_currency",
        ),
        sa.CheckConstraint(
            "base_currency <> quote_currency",
            name="ck_fx_reference_rate_distinct_currencies",
        ),
        sa.CheckConstraint(
            "btrim(convention_ref) <> ''",
            name="ck_fx_reference_rate_convention_nonblank",
        ),
    )

    op.create_table(
        "sources",
        sa.Column(
            "source_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "source_tier",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "publisher",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "access_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "document_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "publication_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "archived_location",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "document_version",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "source_id",
            name="pk_sources",
        ),
        sa.CheckConstraint(
            _canonical_id_check("source_id", "SRC"),
            name="ck_sources_id_shape",
        ),
        sa.CheckConstraint(
            "source_tier IN (1, 2, 3, 4, 5)",
            name="ck_sources_tier",
        ),
        sa.CheckConstraint(
            _enum_check(
                "source_type",
                SOURCE_TYPES,
            ),
            name="ck_sources_type",
        ),
        sa.CheckConstraint(
            "btrim(publisher) <> ''",
            name="ck_sources_publisher_nonblank",
        ),
        sa.CheckConstraint(
            "btrim(title) <> ''",
            name="ck_sources_title_nonblank",
        ),
        sa.CheckConstraint(
            """
            (
                url IS NOT NULL
                AND btrim(url) <> ''
            )
            OR
            (
                archived_location IS NOT NULL
                AND btrim(archived_location) <> ''
            )
            """,
            name="ck_sources_location_present",
        ),
    )

    op.create_table(
        "evidence",
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("sources.source_id"),
            nullable=False,
        ),
        sa.Column(
            "locator",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "label",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "evidence_id",
            name="pk_evidence",
        ),
        sa.CheckConstraint(
            _canonical_id_check(
                "evidence_id",
                "EVD",
            ),
            name="ck_evidence_id_shape",
        ),
        sa.CheckConstraint(
            "btrim(locator) <> ''",
            name="ck_evidence_locator_nonblank",
        ),
        sa.CheckConstraint(
            """
            label IS NULL
            OR btrim(label) <> ''
            """,
            name="ck_evidence_label_nonblank",
        ),
    )

    op.create_table(
        "issuer_identifiers",
        sa.Column(
            "issuer_identifier_row_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "issuer_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("issuers.issuer_id"),
            nullable=False,
        ),
        sa.Column(
            "identifier_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "identifier_value",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "scope_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "scope_value",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "assignment_valid_from",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "assignment_valid_to",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "issuer_identifier_row_id",
            name="pk_issuer_identifiers",
        ),
        sa.CheckConstraint(
            _enum_check(
                "identifier_type",
                ISSUER_IDENTIFIER_TYPES,
            ),
            name="ck_issuer_identifiers_type",
        ),
        sa.CheckConstraint(
            _enum_check(
                "scope_type",
                IDENTIFIER_SCOPE_TYPES,
            ),
            name="ck_issuer_identifiers_scope_type",
        ),
        sa.CheckConstraint(
            "btrim(identifier_value) <> ''",
            name="ck_issuer_identifiers_value_nonblank",
        ),
        sa.CheckConstraint(
            """
            (
                identifier_type = 'LEI'
                AND scope_type = 'GLOBAL'
                AND scope_value IS NULL
            )
            OR
            (
                identifier_type = 'TICKER'
                AND scope_type = 'TRADING_VENUE'
                AND scope_value IS NOT NULL
                AND btrim(scope_value) <> ''
            )
            OR
            (
                identifier_type = 'COMPANY_REGISTRATION_NUMBER'
                AND scope_type = 'REGISTRY'
                AND scope_value IS NOT NULL
                AND btrim(scope_value) <> ''
            )
            OR
            (
                identifier_type = 'VENDOR_IDENTIFIER'
                AND scope_type = 'VENDOR'
                AND scope_value IS NOT NULL
                AND btrim(scope_value) <> ''
            )
            OR
            (
                identifier_type = 'OTHER'
                AND scope_type = 'OTHER'
                AND scope_value IS NOT NULL
                AND btrim(scope_value) <> ''
            )
            """,
            name="ck_issuer_identifiers_scope_mapping",
        ),
        sa.CheckConstraint(
            """
            assignment_valid_from IS NULL
            OR assignment_valid_to IS NULL
            OR assignment_valid_from < assignment_valid_to
            """,
            name="ck_issuer_identifiers_validity_order",
        ),
        sa.CheckConstraint(
            """
            notes IS NULL
            OR btrim(notes) <> ''
            """,
            name="ck_issuer_identifiers_notes_nonblank",
        ),
    )

    op.create_index(
        "ix_issuer_identifiers_resolution",
        "issuer_identifiers",
        [
            "identifier_type",
            "identifier_value",
            "scope_type",
            "scope_value",
            "assignment_valid_from",
            "assignment_valid_to",
        ],
        unique=False,
    )

    # LEIs are globally unique in the frozen domain contract. A second
    # canonical assignment for the same LEI is invalid regardless of issuer
    # or assignment-validity interval.
    op.execute(
        """
        ALTER TABLE issuer_identifiers
        ADD CONSTRAINT ex_issuer_identifiers_lei_identity
        EXCLUDE USING gist (
            identifier_value WITH =
        )
        WHERE (identifier_type = 'LEI')
        DEFERRABLE INITIALLY DEFERRED;
        """
    )

    # Non-LEI identifiers may be reused only when assignments for the same
    # identity key do not overlap. daterange(..., '[)') reproduces the
    # domain's half-open [valid_from, valid_to) interval semantics.
    op.execute(
        """
        ALTER TABLE issuer_identifiers
        ADD CONSTRAINT ex_issuer_identifiers_non_lei_validity
        EXCLUDE USING gist (
            identifier_type WITH =,
            identifier_value WITH =,
            scope_type WITH =,
            scope_value WITH =,
            daterange(
                assignment_valid_from,
                assignment_valid_to,
                '[)'
            ) WITH &&
        )
        WHERE (identifier_type <> 'LEI')
        DEFERRABLE INITIALLY DEFERRED;
        """
    )

    op.create_table(
        "transaction_lifecycle_events",
        sa.Column(
            "event_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("transactions.transaction_id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "effective_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "event_order",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "event_id",
            name="pk_transaction_lifecycle_events",
        ),
        sa.UniqueConstraint(
            "transaction_id",
            "effective_date",
            "event_order",
            name="uq_transaction_lifecycle_ordering",
        ),
        sa.CheckConstraint(
            _canonical_id_check("event_id", "TLE"),
            name="ck_transaction_lifecycle_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check(
                "status",
                TRANSACTION_STATUSES,
            ),
            name="ck_transaction_lifecycle_status",
        ),
        sa.CheckConstraint(
            "event_order > 0",
            name="ck_transaction_lifecycle_order_positive",
        ),
        sa.CheckConstraint(
            """
            notes IS NULL
            OR btrim(notes) <> ''
            """,
            name="ck_transaction_lifecycle_notes_nonblank",
        ),
    )

    op.create_index(
        "ix_transaction_lifecycle_as_of",
        "transaction_lifecycle_events",
        [
            "transaction_id",
            "effective_date",
            "event_order",
        ],
        unique=False,
    )

    op.create_table(
        "observation_subjects",
        sa.Column(
            "subject_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "subject_type",
            "subject_id",
            name="pk_observation_subjects",
        ),
        sa.CheckConstraint(
            _enum_check(
                "subject_type",
                OBSERVABLE_SUBJECT_TYPES,
            ),
            name="ck_observation_subjects_type",
        ),
        sa.CheckConstraint(
            """
            (
                subject_type = 'ISSUER'
                AND subject_id ~ '^ISS[0-9]{9}$'
                AND subject_id <> 'ISS000000000'
            )
            OR
            (
                subject_type = 'PARTY'
                AND subject_id ~ '^PTY[0-9]{9}$'
                AND subject_id <> 'PTY000000000'
            )
            OR
            (
                subject_type = 'PARTICIPATION'
                AND subject_id ~ '^PAR[0-9]{9}$'
                AND subject_id <> 'PAR000000000'
            )
            OR
            (
                subject_type = 'TRANSACTION'
                AND subject_id ~ '^TXN[0-9]{9}$'
                AND subject_id <> 'TXN000000000'
            )
            OR
            (
                subject_type = 'INSTRUMENT'
                AND subject_id ~ '^INS[0-9]{9}$'
                AND subject_id <> 'INS000000000'
            )
            OR
            (
                subject_type = 'MARKET_SERIES'
                AND subject_id ~ '^MKS[0-9]{9}$'
                AND subject_id <> 'MKS000000000'
            )
            """,
            name="ck_observation_subjects_id_matches_type",
        ),
    )

    op.create_table(
        "observations",
        sa.Column(
            "observation_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "subject_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "field_name",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "as_of_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "verification_state",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "scalar_type",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "text_value",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "integer_value",
            sa.Numeric(),
            nullable=True,
        ),
        sa.Column(
            "decimal_value",
            sa.Numeric(),
            nullable=True,
        ),
        sa.Column(
            "boolean_value",
            sa.Boolean(),
            nullable=True,
        ),
        sa.Column(
            "date_value",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "datetime_value",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "value_class",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "missing_state",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "unit",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=True,
        ),
        sa.Column(
            "derivation_ref",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "observation_id",
            name="pk_observations",
        ),
        sa.ForeignKeyConstraint(
            [
                "subject_type",
                "subject_id",
            ],
            [
                "observation_subjects.subject_type",
                "observation_subjects.subject_id",
            ],
            name="fk_observations_subject",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint(
            _canonical_id_check(
                "observation_id",
                "OBS",
            ),
            name="ck_observations_id_shape",
        ),
        sa.CheckConstraint(
            _enum_check(
                "subject_type",
                OBSERVABLE_SUBJECT_TYPES,
            ),
            name="ck_observations_subject_type",
        ),
        sa.CheckConstraint(
            """
            field_name ~
            '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)*$'
            """,
            name="ck_observations_field_name_shape",
        ),
        sa.CheckConstraint(
            _enum_check(
                "verification_state",
                VERIFICATION_STATES,
            ),
            name="ck_observations_verification_state",
        ),
        sa.CheckConstraint(
            f"""
            (
                verification_state IN (
                    {_sql_values(VERIFIED_STATES)}
                )
                AND verified_at IS NOT NULL
            )
            OR
            (
                verification_state NOT IN (
                    {_sql_values(VERIFIED_STATES)}
                )
                AND verified_at IS NULL
            )
            """,
            name="ck_observations_verification_timestamp",
        ),
        sa.CheckConstraint(
            f"""
            scalar_type IS NULL
            OR scalar_type IN (
                {_sql_values(SCALAR_TYPES)}
            )
            """,
            name="ck_observations_scalar_type",
        ),
        sa.CheckConstraint(
            f"""
            value_class IS NULL
            OR value_class IN (
                {_sql_values(VALUE_CLASSES)}
            )
            """,
            name="ck_observations_value_class",
        ),
        sa.CheckConstraint(
            f"""
            missing_state IS NULL
            OR missing_state IN (
                {_sql_values(MISSING_DATA_STATES)}
            )
            """,
            name="ck_observations_missing_state",
        ),
        sa.CheckConstraint(
            """
            (
                missing_state IS NULL
                AND value_class IS NOT NULL
                AND scalar_type IS NOT NULL
                AND num_nonnulls(
                    text_value,
                    integer_value,
                    decimal_value,
                    boolean_value,
                    date_value,
                    datetime_value
                ) = 1
            )
            OR
            (
                missing_state IS NOT NULL
                AND value_class IS NULL
                AND scalar_type IS NULL
                AND num_nonnulls(
                    text_value,
                    integer_value,
                    decimal_value,
                    boolean_value,
                    date_value,
                    datetime_value
                ) = 0
            )
            """,
            name="ck_observations_value_missing_exclusivity",
        ),
        sa.CheckConstraint(
            """
            scalar_type IS NULL
            OR (
                scalar_type = 'TEXT'
                AND text_value IS NOT NULL
            )
            OR (
                scalar_type = 'INTEGER'
                AND integer_value IS NOT NULL
            )
            OR (
                scalar_type = 'DECIMAL'
                AND decimal_value IS NOT NULL
            )
            OR (
                scalar_type = 'BOOLEAN'
                AND boolean_value IS NOT NULL
            )
            OR (
                scalar_type = 'DATE'
                AND date_value IS NOT NULL
            )
            OR (
                scalar_type = 'DATETIME'
                AND datetime_value IS NOT NULL
            )
            """,
            name="ck_observations_scalar_slot_matches_type",
        ),
        sa.CheckConstraint(
            """
            integer_value IS NULL
            OR integer_value = trunc(integer_value)
            """,
            name="ck_observations_integer_integral",
        ),
        sa.CheckConstraint(
            """
            unit IS NULL
            OR btrim(unit) <> ''
            """,
            name="ck_observations_unit_nonblank",
        ),
        sa.CheckConstraint(
            """
            currency IS NULL
            OR currency ~ '^[A-Z]{3}$'
            """,
            name="ck_observations_currency_shape",
        ),
        sa.CheckConstraint(
            """
            derivation_ref IS NULL
            OR btrim(derivation_ref) <> ''
            """,
            name="ck_observations_derivation_ref_nonblank",
        ),
    )

    op.create_index(
        "ix_observations_subject_field_as_of",
        "observations",
        [
            "subject_type",
            "subject_id",
            "field_name",
            "as_of_date",
        ],
        unique=False,
    )

    op.create_table(
        "issuer_identifier_evidence",
        sa.Column(
            "issuer_identifier_row_id",
            sa.BigInteger(),
            _restrict_fk(
                "issuer_identifiers.issuer_identifier_row_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("evidence.evidence_id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "issuer_identifier_row_id",
            "evidence_id",
            name="pk_issuer_identifier_evidence",
        ),
        sa.UniqueConstraint(
            "issuer_identifier_row_id",
            "evidence_ordinal",
            name="uq_issuer_identifier_evidence_ordinal",
        ),
        sa.CheckConstraint(
            "evidence_ordinal >= 0",
            name="ck_issuer_identifier_evidence_ordinal",
        ),
    )

    op.create_table(
        "participation_evidence",
        sa.Column(
            "participation_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "participations.participation_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("evidence.evidence_id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "participation_id",
            "evidence_id",
            name="pk_participation_evidence",
        ),
        sa.UniqueConstraint(
            "participation_id",
            "evidence_ordinal",
            name="uq_participation_evidence_ordinal",
        ),
        sa.CheckConstraint(
            "evidence_ordinal >= 0",
            name="ck_participation_evidence_ordinal",
        ),
    )

    op.create_table(
        "transaction_lifecycle_event_evidence",
        sa.Column(
            "event_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "transaction_lifecycle_events.event_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("evidence.evidence_id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "event_id",
            "evidence_id",
            name="pk_transaction_lifecycle_event_evidence",
        ),
        sa.UniqueConstraint(
            "event_id",
            "evidence_ordinal",
            name="uq_transaction_lifecycle_event_evidence_ordinal",
        ),
        sa.CheckConstraint(
            "evidence_ordinal >= 0",
            name="ck_transaction_lifecycle_event_evidence_ordinal",
        ),
    )

    op.create_table(
        "observation_evidence",
        sa.Column(
            "observation_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "observations.observation_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk("evidence.evidence_id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "observation_id",
            "evidence_id",
            name="pk_observation_evidence",
        ),
        sa.UniqueConstraint(
            "observation_id",
            "evidence_ordinal",
            name="uq_observation_evidence_ordinal",
        ),
        sa.CheckConstraint(
            "evidence_ordinal >= 0",
            name="ck_observation_evidence_ordinal",
        ),
    )

    op.create_table(
        "observation_inputs",
        sa.Column(
            "derived_observation_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "observations.observation_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "input_observation_id",
            sa.String(length=ID_LENGTH),
            _restrict_fk(
                "observations.observation_id"
            ),
            nullable=False,
        ),
        sa.Column(
            "input_ordinal",
            sa.Integer(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "derived_observation_id",
            "input_observation_id",
            name="pk_observation_inputs",
        ),
        sa.UniqueConstraint(
            "derived_observation_id",
            "input_ordinal",
            name="uq_observation_inputs_ordinal",
        ),
        sa.CheckConstraint(
            """
            derived_observation_id
            <> input_observation_id
            """,
            name="ck_observation_inputs_no_self_reference",
        ),
        sa.CheckConstraint(
            "input_ordinal >= 0",
            name="ck_observation_inputs_ordinal",
        ),
    )

    # PostgreSQL-specific integrity for the polymorphic observable-subject
    # registry. These functions intentionally enforce persistence structure,
    # not analytical business semantics.

    op.execute(
        """
        CREATE FUNCTION ecm_subject_exists(
            p_subject_type text,
            p_subject_id text
        )
        RETURNS boolean
        LANGUAGE plpgsql
        STABLE
        AS $$
        BEGIN
            CASE p_subject_type
                WHEN 'ISSUER' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM issuers
                        WHERE issuer_id = p_subject_id
                    );
                WHEN 'PARTY' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM parties
                        WHERE party_id = p_subject_id
                    );
                WHEN 'PARTICIPATION' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM participations
                        WHERE participation_id = p_subject_id
                    );
                WHEN 'TRANSACTION' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM transactions
                        WHERE transaction_id = p_subject_id
                    );
                WHEN 'INSTRUMENT' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM instruments
                        WHERE instrument_id = p_subject_id
                    );
                WHEN 'MARKET_SERIES' THEN
                    RETURN EXISTS (
                        SELECT 1
                        FROM market_series
                        WHERE market_series_id = p_subject_id
                    );
                ELSE
                    RETURN FALSE;
            END CASE;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION ecm_validate_registry_row()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_subject_type text;
            v_subject_id text;
            v_exists boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_subject_type := OLD.subject_type;
                v_subject_id := OLD.subject_id;
            ELSE
                v_subject_type := NEW.subject_type;
                v_subject_id := NEW.subject_id;
            END IF;

            v_exists := ecm_subject_exists(
                v_subject_type,
                v_subject_id
            );

            IF TG_OP = 'DELETE' THEN
                IF v_exists THEN
                    RAISE EXCEPTION
                        'Cannot remove registry row for existing subject: % %',
                        v_subject_type,
                        v_subject_id
                        USING ERRCODE = '23503';
                END IF;
            ELSIF NOT v_exists THEN
                RAISE EXCEPTION
                    'Observation subject registry row has no canonical subject: % %',
                    v_subject_type,
                    v_subject_id
                    USING ERRCODE = '23503';
            END IF;

            RETURN NULL;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            ct_observation_subjects_concrete_subject
        AFTER INSERT OR DELETE
        ON observation_subjects
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION ecm_validate_registry_row();
        """
    )

    op.execute(
        """
        CREATE FUNCTION ecm_reject_registry_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'Observation subject registry rows cannot be reassigned'
                USING ERRCODE = '23514';
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER tr_observation_subjects_no_update
        BEFORE UPDATE
        ON observation_subjects
        FOR EACH ROW
        EXECUTE FUNCTION ecm_reject_registry_update();
        """
    )

    op.execute(
        """
        CREATE FUNCTION ecm_validate_entity_registry()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_subject_type text := TG_ARGV[0];
            v_id_column text := TG_ARGV[1];
            v_subject_id text;
            v_registry_exists boolean;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                v_subject_id := to_jsonb(OLD) ->> v_id_column;
            ELSE
                v_subject_id := to_jsonb(NEW) ->> v_id_column;
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM observation_subjects
                WHERE subject_type = v_subject_type
                  AND subject_id = v_subject_id
            )
            INTO v_registry_exists;

            IF TG_OP = 'DELETE' THEN
                IF v_registry_exists THEN
                    RAISE EXCEPTION
                        'Canonical subject deletion requires registry deletion: % %',
                        v_subject_type,
                        v_subject_id
                        USING ERRCODE = '23503';
                END IF;
            ELSIF NOT v_registry_exists THEN
                RAISE EXCEPTION
                    'Canonical observable subject requires registry row: % %',
                    v_subject_type,
                    v_subject_id
                    USING ERRCODE = '23503';
            END IF;

            RETURN NULL;
        END;
        $$;
        """
    )

    observable_entities = (
        (
            "issuers",
            "issuer_id",
            "ISSUER",
        ),
        (
            "parties",
            "party_id",
            "PARTY",
        ),
        (
            "participations",
            "participation_id",
            "PARTICIPATION",
        ),
        (
            "transactions",
            "transaction_id",
            "TRANSACTION",
        ),
        (
            "instruments",
            "instrument_id",
            "INSTRUMENT",
        ),
        (
            "market_series",
            "market_series_id",
            "MARKET_SERIES",
        ),
    )

    for (
        table_name,
        id_column,
        subject_type,
    ) in observable_entities:
        op.execute(
            f"""
            CREATE CONSTRAINT TRIGGER
                ct_{table_name}_observation_subject
            AFTER INSERT OR DELETE
            ON {table_name}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION ecm_validate_entity_registry(
                '{subject_type}',
                '{id_column}'
            );
            """
        )

    # Stable canonical IDs cannot be reassigned after creation.

    op.execute(
        """
        CREATE FUNCTION ecm_reject_canonical_id_update()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_id_column text := TG_ARGV[0];
            v_old_id text;
            v_new_id text;
        BEGIN
            v_old_id := to_jsonb(OLD) ->> v_id_column;
            v_new_id := to_jsonb(NEW) ->> v_id_column;

            IF v_old_id IS DISTINCT FROM v_new_id THEN
                RAISE EXCEPTION
                    'Canonical identifier cannot be reassigned: % -> %',
                    v_old_id,
                    v_new_id
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )

    canonical_id_tables = (
        (
            "issuers",
            "issuer_id",
        ),
        (
            "parties",
            "party_id",
        ),
        (
            "participations",
            "participation_id",
        ),
        (
            "transactions",
            "transaction_id",
        ),
        (
            "instruments",
            "instrument_id",
        ),
        (
            "market_series",
            "market_series_id",
        ),
        (
            "transaction_lifecycle_events",
            "event_id",
        ),
        (
            "sources",
            "source_id",
        ),
        (
            "evidence",
            "evidence_id",
        ),
        (
            "observations",
            "observation_id",
        ),
    )

    for table_name, id_column in canonical_id_tables:
        op.execute(
            f"""
            CREATE TRIGGER tr_{table_name}_immutable_id
            BEFORE UPDATE OF {id_column}
            ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION ecm_reject_canonical_id_update(
                '{id_column}'
            );
            """
        )

    # Input observations may not post-date the observation derived from them.
    # The constraint is deferred so an atomic transaction can insert or adjust
    # all members of one logical calculation unit before validation.

    op.execute(
        """
        CREATE FUNCTION ecm_validate_observation_input_dates()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM observation_inputs AS oi
                JOIN observations AS derived
                  ON derived.observation_id =
                     oi.derived_observation_id
                JOIN observations AS input_observation
                  ON input_observation.observation_id =
                     oi.input_observation_id
                WHERE input_observation.as_of_date
                      > derived.as_of_date
            ) THEN
                RAISE EXCEPTION
                    'Observation input cannot be later than derived observation'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NULL;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            ct_observation_inputs_as_of_date
        AFTER INSERT OR UPDATE
        ON observation_inputs
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION ecm_validate_observation_input_dates();
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            ct_observations_input_as_of_date
        AFTER UPDATE
        ON observations
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION ecm_validate_observation_input_dates();
        """
    )


def downgrade() -> None:
    """Reverse the initial canonical persistence schema."""

    op.drop_table("observation_inputs")
    op.drop_table("observation_evidence")
    op.drop_table(
        "transaction_lifecycle_event_evidence"
    )
    op.drop_table("participation_evidence")
    op.drop_table("issuer_identifier_evidence")
    op.drop_table("observations")
    op.drop_table("observation_subjects")
    op.drop_table("transaction_lifecycle_events")
    op.drop_table("issuer_identifiers")
    op.drop_table("evidence")
    op.drop_table("sources")
    op.drop_table("fx_reference_rate_definitions")
    op.drop_table("market_series")
    op.drop_table("participations")
    op.drop_table("instruments")
    op.drop_table("transactions")
    op.drop_table("parties")
    op.drop_table("issuers")

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_validate_observation_input_dates();
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_reject_canonical_id_update();
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_validate_entity_registry();
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_reject_registry_update();
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_validate_registry_row();
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            ecm_subject_exists(text, text);
        """
    )
