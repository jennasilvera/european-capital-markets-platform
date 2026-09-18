# Persistence Backend

## Decision

The canonical relational persistence backend is PostgreSQL.

The initial supported major version is PostgreSQL 18.

Production and integration environments should run a currently supported minor
release within PostgreSQL 18 rather than pinning application semantics to one
patch release.

The initial Python persistence stack is:

- Psycopg 3 for PostgreSQL connectivity;
- SQLAlchemy 2.0 Core for connection, transaction, SQL-expression, and schema
  integration;
- Alembic for versioned schema migrations.

The SQLAlchemy ORM is not part of the initial persistence architecture.

## Rationale

The persistence contract requires relational capabilities beyond a minimal
embedded database.

PostgreSQL provides the mechanisms needed to implement the frozen contract
without weakening it, including:

- exact `NUMERIC` storage;
- ordinary and composite foreign keys;
- CHECK constraints;
- partial unique indexes;
- exclusion constraints;
- deferrable constraints;
- constraint triggers;
- recursive queries;
- transactional DDL;
- robust timestamp and timezone support.

These facilities are relevant to existing platform semantics such as:

- exact Decimal financial values;
- temporal issuer-identifier assignments;
- nullable participation scopes;
- observation-subject referential integrity;
- lifecycle ordering;
- calculation lineage;
- append-oriented historical storage.

## PostgreSQL Major-Version Policy

PostgreSQL 18 is the initial supported major release.

The project should follow the latest supported PostgreSQL 18 minor release in
deployed environments.

A PostgreSQL major-version change requires explicit compatibility testing of:

- migrations;
- constraints;
- indexes;
- triggers;
- query semantics;
- Decimal round trips;
- timestamp round trips;
- integration tests.

A new PostgreSQL major version is not adopted merely because a beta or release
candidate exists.

## Psycopg

Psycopg 3 is the canonical Python PostgreSQL driver.

The initial implementation uses the synchronous API unless a concrete
application requirement establishes that asynchronous database access provides
material value.

Database URLs use the SQLAlchemy Psycopg dialect form:

`postgresql+psycopg://...`

Credentials must come from environment configuration.

Credentials must never be committed to repository configuration.

## SQLAlchemy Core

SQLAlchemy is initially used as a database toolkit, not as an object-relational
mapper.

The project may use SQLAlchemy Core for:

- engine and connection management;
- explicit transactions;
- safe SQL parameterization;
- dialect-aware SQL integration;
- schema reflection where useful;
- persistence adapter implementation.

Domain dataclasses remain the analytical domain model.

They are not replaced by SQLAlchemy declarative ORM classes.

If ORM adoption is considered later, it requires a separate architecture
decision showing that it improves maintainability without duplicating or
obscuring domain semantics.

## Alembic

Alembic is the canonical migration mechanism.

Every persistent schema change must be represented by a versioned migration.

Migrations should be reviewed as database changes, not treated as incidental
generated artifacts.

The initial migration series may use explicit PostgreSQL SQL where required for
constraints that cannot be represented clearly through portable abstractions.

Autogeneration is not authoritative.

A generated migration must never be accepted without review against the
canonical persistence contract.

## Migration Directory

The migration environment lives under:

`migrations/`

Revision files live under:

`migrations/versions/`

The repository-level Alembic configuration is:

`alembic.ini`

The migration environment reads the database connection URL from:

`DATABASE_URL`

No production or developer credentials are stored in `alembic.ini`.

## Transaction Policy

Schema migrations should execute transactionally wherever PostgreSQL permits.

Canonical application writes will also use explicit database transactions.

A write that spans a parent record and its required junction, lineage, or
registry rows must commit atomically.

## ORM Boundary

The absence of ORM models is intentional.

The first persistence implementation should demonstrate the relational schema,
database constraints, migrations, and domain-record round trips before adding a
second class-model layer.

This prevents persistence tooling from becoming a parallel definition of
capital-markets business semantics.

## Integration Testing

The persistence layer is not considered complete merely because migration SQL
parses or unit tests pass.

Integration tests must eventually execute against a real PostgreSQL 18
instance.

Those tests must verify both:

- successful persistence and round-trip behavior;
- database rejection of states the persistence contract marks as
  database-enforced.

Local Docker availability is not a prerequisite for defining the migration
architecture.

CI may provide PostgreSQL independently of the developer workstation runtime.

## Version Discipline

Dependency ranges should stay on stable release lines.

The project should not adopt beta, release-candidate, or development database
or persistence-library releases for the canonical path without an explicit
reason and compatibility review.

## PostgreSQL Extensions

The initial canonical schema requires PostgreSQL's `btree_gist` extension.

The extension supplies GiST equality operator classes used to enforce the
frozen issuer-identity collision contract:

- a LEI may have only one canonical assignment;
- a non-LEI identifier may be reused only when assignment-validity intervals
  for the same identifier namespace do not overlap.

Validity intervals use half-open `[valid_from, valid_to)` semantics. Therefore
an assignment ending on a date does not conflict with a successor beginning on
that same date.

The migration installs `btree_gist` with `CREATE EXTENSION IF NOT EXISTS`.

Downgrade intentionally leaves the extension installed because extensions are
shared database infrastructure rather than canonical platform data.
