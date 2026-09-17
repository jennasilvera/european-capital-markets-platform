# Governed Observation Field Dictionary

## Purpose

Transaction economics and execution terms are not stable identity attributes.

Fields such as:

- issue size;
- currency;
- coupon;
- yield;
- spread;
- margin;
- maturity;
- book size;
- new-issue premium;
- offer price;
- discount;
- seller proceeds

may be disclosed, revised, calculated, estimated, or observed at different
points in time.

They therefore remain in the governed observation layer rather than becoming
mutable fields on `TransactionRecord`, `InstrumentRecord`, `PartyRecord`, or
`ParticipationRecord`.

The field dictionary controls the semantics of those observations.

## Field Definition

A governed field definition specifies:

- canonical field name;
- permitted subject type;
- expected scalar value type;
- unit requirements;
- allowed units where relevant;
- currency requirements;
- analytical description.

The field definition does not replace observation lineage.

Every observation still retains the normal:

- value class;
- verification state;
- as-of date;
- evidence references;
- derivation references where applicable;
- missing-data state;
- notes.

## Subject Scope

Field scope is explicit.

Examples:

`transaction.aggregate_size`

belongs to the transaction.

`instrument.issue_size`

belongs to an individual instrument or tranche.

`participation.shares_sold`

belongs to a specific party-to-transaction participation relationship.

The same economic concept should not be copied to multiple subject levels merely
for convenience.

Derived roll-ups belong in analytical calculations unless there is a separately
meaningful and governed observation at the higher level.

## Transaction-Level Aggregate Size

`transaction.aggregate_size` is deliberately distinct from
`instrument.issue_size`.

It should be populated only where an aggregate transaction amount is itself
meaningful and supportable.

Examples may include:

- a source explicitly disclosing total transaction size;
- a governed same-currency calculation across instruments;
- a controlled converted aggregate produced under a documented FX methodology.

A multi-currency financing should not receive a native-currency aggregate merely
by adding unlike currencies.

Converted values must preserve the platform's separate FX assumptions, dates,
and methodology.

## Instrument-Level Terms

Instrument-specific economics should normally remain instrument observations.

The initial field set includes:

- currency;
- issue size;
- issue price as percent of par;
- coupon;
- yield;
- spread;
- margin;
- maturity date;
- book size;
- new-issue premium;
- ECM offer price per share;
- ECM discount.

This prevents multi-tranche transactions from collapsing economically different
instruments into one transaction-level row.

## Participation-Level Economics

Some economics belong to the relationship between one party and the financing.

For example, in an ECM transaction containing multiple selling shareholders:

- the number of shares sold by one seller;
- proceeds attributable to that seller

belong naturally to the selling-shareholder participation rather than to the
party identity or transaction as a whole.

The initial governed participation fields therefore include:

- `participation.shares_sold`;
- `participation.gross_proceeds`.

## Decimal Precision

Financial numeric observations in the initial economics dictionary use
`Decimal`.

Binary floating-point values are not accepted for these governed monetary,
percentage, spread, or quantity fields.

This avoids silent representation error and creates a consistent basis for later
financial calculations and persistence.

## Units

Units are explicit where the numeric value is otherwise ambiguous.

Initial controlled units include:

- `PERCENT`;
- `PERCENT_OF_PAR`;
- `BASIS_POINTS`;
- `PER_SHARE`;
- `SHARES`.

A field requiring a unit must use one of the units explicitly allowed by its
definition.

A field that forbids unit metadata must not carry a unit merely for display
convenience.

## Currency

Currency-bearing monetary observations require a three-letter uppercase
currency code.

Examples:

- `EUR`;
- `GBP`;
- `USD`.

The initial validator checks canonical code shape.

An authoritative ISO currency reference table may later provide membership and
historical-validity checks.

Currency metadata is forbidden on fields where currency has no economic
meaning, such as:

- coupon percentage;
- yield percentage;
- basis-point spread;
- maturity date.

## Missing Data

A governed observation with an explicit missing-data state is valid without
unit or currency metadata.

For example, if issue size is pending verification, the platform should record
that state rather than inventing a currency or zero amount.

Once a value is populated, its field-level unit and currency requirements apply.

## Monetary Scale

Canonical monetary observations are stored in actual major currency units.

For example, EUR 500 million is represented as:

- value: `500000000`;
- currency: `EUR`.

Canonical values should not encode display scaling such as:

- millions;
- billions;
- thousands.

Display layers may scale values for presentation, but the canonical observation
must preserve the unscaled amount.

This prevents `500`, `500000000`, and similar representations from being
mistaken for economically different values.

## Gross versus Net Proceeds

`participation.gross_proceeds` means proceeds attributable to the participation
before transaction costs or other deductions.

It is intentionally not named simply `proceeds`.

If net proceeds become analytically necessary, they should use a separate
governed field with explicit semantics rather than changing the meaning of the
gross-proceeds field.

## Instrument Currency

`instrument.currency` records the denomination or issuance currency as a
currency-code scalar value.

The initial validator requires the same three-letter uppercase shape used by
currency metadata.

Authoritative currency-membership and historical-validity checks remain a
future reference-data responsibility.

Monetary observations such as `instrument.issue_size` still carry their own
currency metadata so that each fact remains independently interpretable and
auditable.

A later cross-observation validator may reconcile an instrument's denomination
currency with monetary observations where product semantics require them to
match.

## Missing-Value Metadata

A missing observation does not have to invent metadata that would normally be
required for a populated value.

For example, an `instrument.issue_size` that is pending verification may omit
currency.

However, metadata that is supplied on a missing observation must still be
semantically valid for that field.

A missing issue-size observation therefore may not carry a unit such as
`MILLIONS` when the issue-size field forbids unit metadata.

## Product-Specific Validation

The generic field dictionary defines field semantics and subject scope.

It does not yet assert that every field is valid for every product family.

For example:

- coupon and spread are usually debt concepts;
- offer price per share and discount are usually ECM concepts;
- margin is particularly relevant to floating-rate and leveraged-finance
  instruments.

Product-specific validators should be introduced separately after the generic
economic field semantics are stable.

## Persistence Boundary

The field dictionary is analytical schema metadata.

A later persistence layer should preserve:

- canonical field names;
- subject-scope constraints;
- scalar value types;
- unit rules;
- currency rules;
- field-definition versioning where methodology changes require it.
