# Platform Architecture

## Purpose

The European Capital Markets Issuance & Execution Intelligence Platform is
maintained analytical infrastructure for European primary capital markets.

It connects:

1. sourced market and transaction observations;
2. controlled canonical data;
3. transaction precedent analytics;
4. market-condition monitoring;
5. company and capital-structure analysis;
6. financing alternatives;
7. transaction pricing and execution assessment;
8. client-ready analytical outputs.

The system is designed to be auditable, reproducible, maintainable, and
updateable.

## Core Data Flow

External Sources
    |
    v
Raw Data / Source Evidence
    |
    v
Staging and Normalization
    |
    v
Validation and Exception Controls
    |
    v
Canonical Data
    |
    +--------------------+
    |                    |
    v                    v
Market Analytics     Transaction Analytics
    |                    |
    +----------+---------+
               |
               v
      Financing Analysis
               |
               v
     Recommendation Layer
               |
               v
       Controlled Outputs

## Data Layers

### Raw

Preserves source-derived information as obtained.

Raw data is not assumed to be validated, normalized, or publishable.

### Staged

Contains normalized data undergoing validation.

### Canonical

Contains approved analytical data conforming to the platform's schema,
taxonomy, sourcing, and validation requirements.

### Reference

Contains controlled reference information such as currencies, classifications,
benchmark mappings, and other supporting dimensions.

## Software Boundary

Reusable implementation code belongs under
`src/european_capital_markets/`.

Analytical specifications and domain-specific work belong under
`analytics/`.

Generated professional outputs belong under
`outputs/`.

## Control Principle

Every material number in a released analytical output must ultimately be
traceable either:

- to source evidence; or
- to a reproducible calculation whose material inputs are themselves
  traceable.

## Release Principle

Working analytical files may change.

Released outputs are immutable. Corrections or updates produce a new release.

## Persistence Contract

The canonical relational persistence boundary is governed by
[`docs/methodology/persistence_contract.md`](methodology/persistence_contract.md).

Persistence must reproduce the frozen domain semantics rather than redefine
them.

The selected backend and migration tooling are documented in
[`docs/methodology/persistence_backend.md`](methodology/persistence_backend.md).

PostgreSQL is the canonical relational backend. The initial implementation uses
Psycopg 3, SQLAlchemy Core, and Alembic without introducing ORM models.

## Canonical Dataset Validation Boundary

The current in-memory canonical state represented by the frozen domain
record families is grouped in `CanonicalDataset`.

Before a canonical dataset is persisted, it must pass
`validate_canonical_dataset()`.

The aggregate validator composes the frozen domain validators rather than
reimplementing their semantics. It also enforces the cross-family invariant
that every observation references a concrete canonical subject of the declared
subject type.

Persistence adapters must not treat successful construction of individual
records as proof that the complete canonical dataset is coherent.

## European Market Framework

Phase 1 market-series semantics are governed by
[`docs/methodology/european_market_framework.md`](methodology/european_market_framework.md).

The framework separates stable market-series identity, date-level sourced
observations, and downstream market analytics before additional rate, yield,
spread, equity-index, or volatility series are added to the executable domain
model.
