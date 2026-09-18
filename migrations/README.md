# Database Migrations

This directory contains the canonical PostgreSQL schema migration history.

The governing documents are:

- `docs/methodology/persistence_contract.md`;
- `docs/methodology/persistence_backend.md`.

Migration revisions live in `migrations/versions/`.

Migrations use `DATABASE_URL` for database connectivity.

No credentials belong in repository configuration.

The initial schema is intentionally hand-reviewed against the persistence
contract. Alembic autogeneration is not the source of truth for business or
analytical constraints.
