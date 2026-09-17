# Canonical Entity Model

## Purpose

The canonical entity model establishes the stable identity and parent-child
relationships used throughout the European Capital Markets Issuance &
Execution Intelligence Platform.

The initial hierarchy is:

Issuer
→ Transaction
→ Instrument

These records intentionally remain narrower than the full analytical dataset.

## Design Principle

Canonical entity records answer:

- what entity is this;
- what is its permanent platform identifier;
- what is its parent entity;
- what top-level analytical domain does the transaction belong to.

They do not attempt to store every known fact about the entity.

Material source-derived or time-varying facts are represented through governed
observations.

This avoids duplicating the same fact between entity rows and the lineage
system.

## Issuer

An IssuerRecord is the stable internal identity anchor for a corporate or other
capital-markets issuer.

It contains:

- permanent issuer ID;
- canonical name.

The canonical name is an operational display label.

It is not a substitute for a sourced legal-name observation where the legal
name at a particular date matters analytically.

Future identity work may add controlled external-identifier mappings such as:

- LEI;
- exchange identifiers;
- tickers;
- vendor identifiers;
- historical names.

Those mappings should not alter the permanent issuer ID.

## Transaction

A TransactionRecord represents one canonical financing event.

It contains:

- permanent transaction ID;
- primary analytical issuer ID;
- top-level product family;
- optional transaction label.

A transaction has exactly one primary analytical issuer anchor.

This anchor establishes the canonical hierarchy used for aggregation and
analysis. It does not assert that only one legal or economic entity participates
in the financing.

Later participant relationships may separately identify roles such as:

- legal issuer;
- co-issuer;
- borrower;
- co-borrower;
- guarantor;
- acquisition vehicle;
- selling shareholder;
- sponsor;
- other transaction party.

Where required, an instrument may also have participant relationships distinct
from the transaction-level analytical issuer anchor.

The product family determines the appropriate downstream analytical rules and
product-specific schema.

The current controlled families are:

- ECM;
- IG_DCM;
- LEVERAGED_FINANCE;
- EQUITY_LINKED.

## Instrument

An InstrumentRecord represents an individual instrument or tranche within a
transaction.

It contains:

- permanent instrument ID;
- parent transaction ID;
- optional instrument label.

An instrument does not duplicate the transaction's primary analytical issuer
ID.

The analytical issuer anchor is reached through:

Instrument
→ Transaction
→ Primary Analytical Issuer

This prevents contradictory canonical parent relationships.

Instrument-specific legal issuers, borrowers, guarantors, or other parties
will later be represented as explicit participant relationships rather than by
duplicating the canonical parent field.

An instrument also does not duplicate product family because the product family
is inherited from its parent transaction.

## Facts Excluded from Core Entity Rows

The following examples are deliberately not stored directly on these core
entity records:

- transaction status;
- announcement date;
- launch date;
- pricing date;
- settlement date;
- issue size;
- offer price;
- coupon;
- yield;
- spread;
- margin;
- rating;
- leverage;
- book size;
- discount;
- new-issue premium;
- aftermarket performance.

These are source-derived, calculated, estimated, assumed, or time-varying facts
and belong in governed observations or later controlled analytical records.

## Transaction Status

Transaction status is time-varying.

A transaction may progress through states such as:

ANNOUNCED
→ MARKETING
→ LAUNCHED
→ PRICED
→ ALLOCATED
→ SETTLED

It may instead become POSTPONED, WITHDRAWN, or CANCELLED.

For this reason the core TransactionRecord does not treat one mutable status
field as transaction identity.

Lifecycle history will be modeled separately so prior states remain auditable.

## Relationship Invariants

The canonical hierarchy enforces the following rules:

1. issuer IDs must use the issuer namespace;
2. transaction IDs must use the transaction namespace;
3. instrument IDs must use the instrument namespace;
4. every transaction must reference an existing primary analytical issuer;
5. every instrument must reference an existing transaction;
6. IDs must be unique within each entity class;
7. product family must use the controlled ProductFamily vocabulary;
8. optional display labels must not be blank when populated.

## Multi-Instrument Transactions

A single transaction may contain multiple instruments.

Examples include:

- multi-tranche investment-grade bond issuance;
- multiple leveraged-loan tranches;
- a bond transaction containing several maturities.

Each tranche receives its own permanent instrument ID.

Terms specific to the tranche are then attached to that instrument through
observations.

## Identity versus Classification

Permanent identity and analytical classification are separate concepts.

Changing or correcting:

- product classification;
- issuer display name;
- instrument label;
- transaction label;

must not cause a new permanent ID merely because descriptive metadata changed.

A genuinely distinct financing event or instrument receives a distinct ID.

## Persistence Boundary

These classes define canonical analytical semantics.

They are not yet persistence models.

Database tables, constraints, migrations, and identifier allocation will be
implemented only after the entity relationships and product-specific rules are
sufficiently stable.

## Next Extensions

The next canonical-model extensions are expected to cover:

- issuer external-identifier crosswalks;
- transaction and instrument participant relationships;
- transaction lifecycle history;
- ECM classifications;
- IG DCM instrument classifications;
- leveraged-finance instrument classifications;
- product-specific structural validation.
