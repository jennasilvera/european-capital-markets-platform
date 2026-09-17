# Cross-Observation Consistency Controls

## Purpose

An observation can be individually valid while still conflicting with other
facts in the analytical dataset.

For example:

- an instrument may be observed as EUR-denominated while its issue size is
  recorded in GBP;
- a calculated transaction total may not equal the tranche amounts from which
  it claims to be derived;
- a derived observation may depend on information whose as-of date is later
  than the derived observation itself.

These are not entity-identity problems and they are not field-definition
problems.

They are cross-observation consistency problems.

The platform therefore maintains a separate validation layer for relationships
between otherwise valid observations.

## Validation Layers

The analytical controls are intentionally layered.

### Observation structure

`ObservationRecord` controls:

- identifiers;
- subject identity;
- populated versus missing state;
- verification state;
- value class;
- evidence requirements;
- calculation inputs;
- derivation references;
- lineage cycles.

### Field semantics

The governed observation field dictionary controls:

- field name;
- subject scope;
- scalar value type;
- unit semantics;
- currency semantics.

### Cross-observation consistency

The consistency layer controls relationships that require multiple records to
be interpreted together.

No one layer should absorb the responsibilities of the others merely for
convenience.

## Temporal Input Integrity

A derived observation must not depend on a future input observation.

For every referenced input:

`input.as_of_date <= derived.as_of_date`

must hold.

This protects historical analysis from look-ahead contamination.

The rule applies to any observation containing input-observation references,
not only capital-markets size calculations.

## Instrument Currency Reconciliation

Instrument monetary observations should agree with the latest known
`instrument.currency` observation at or before the monetary observation's
as-of date.

The initial control applies to governed instrument fields that require currency
metadata.

Examples include:

- `instrument.issue_size`;
- `instrument.book_size`;
- `instrument.offer_price_per_share`.

If no instrument-currency observation exists at or before the relevant date,
the consistency layer does not invent one and does not fail the observation.

If the latest currency state is explicitly missing, the monetary observation is
not compared against an older currency value.

## Same-Date Currency Ambiguity

If the latest instrument-currency date contains multiple populated observations
with conflicting values, the currency state is ambiguous and validation fails.

If identical values are represented by multiple observations on that date, the
economic conclusion is not ambiguous.

If both populated and explicitly missing observations exist at the same latest
date, the state is also ambiguous.

These situations should ultimately feed the platform's exception-control
workflow.

## Calculated Transaction Aggregate Size

`transaction.aggregate_size` may be:

- disclosed directly by a source; or
- calculated from governed inputs.

The initial arithmetic consistency control applies only to a
`CALCULATED` aggregate.

Its explicitly referenced inputs must be:

- `instrument.issue_size` observations;
- populated rather than explicit missing-data observations;
- attached to instruments belonging to the same transaction;
- no more than one issue-size observation per instrument.

The validator does not infer calculation inputs by scanning every tranche in
the transaction.

The calculation's lineage must state which observation IDs were actually used.

## Same-Currency Reconciliation

If every referenced tranche-size input uses the same currency as the calculated
transaction aggregate, then:

`transaction.aggregate_size == sum(instrument.issue_size inputs)`

must hold exactly using `Decimal` arithmetic.

This is a deterministic accounting identity and therefore should not be handled
as an analyst judgment or tolerance-based check.

## Cross-Currency Aggregation

A multi-currency financing may legitimately have a calculated aggregate in one
reporting currency.

For example:

- EUR tranche;
- GBP tranche;
- USD-equivalent aggregate.

Such a calculation requires FX rates, rate dates, conversion conventions, and
rounding methodology.

The initial consistency layer therefore does not directly sum unlike currencies.

A cross-currency aggregate remains dependent on its explicit lineage and
derivation reference, but full arithmetic validation is deferred until the FX
methodology and reference-data layer exist.

This is deliberate.

The platform must not pretend that adding unlike currencies is meaningful.

## Disclosed Aggregate Size

A disclosed `transaction.aggregate_size` is not mechanically forced to equal
the currently available instrument observations.

Potential reasons include:

- source rounding;
- incomplete tranche information;
- different source timing;
- transaction-scope differences;
- amendments;
- source disagreement.

Such discrepancies may later generate analytical exceptions, but the initial
hard-consistency validator applies arithmetic equality only where the platform
itself claims the aggregate was calculated from explicit inputs.

## Revision Awareness

Economic facts can change over time.

Currency reconciliation therefore uses the latest known instrument-currency
state at or before the monetary observation's as-of date rather than using a
single timeless currency attribute.

This preserves historical reproducibility.

## Hard Error versus Analytical Exception

The initial implementation raises hard validation errors only where the
relationship is deterministic.

Examples:

- future-dated calculation input;
- contradictory latest currency state;
- missing tranche-size input used in a calculated aggregate;
- aggregate input from another transaction;
- duplicate tranche input inside one aggregate calculation;
- same-currency arithmetic mismatch.

Other economically interesting discrepancies should later become structured
exceptions rather than being forced into binary validity rules.

## Persistence Boundary

Cross-observation consistency is a validation layer, not a new canonical entity
type.

A later persistence implementation may store generated exceptions and review
outcomes, but the underlying economic facts remain ordinary governed
observations with their original lineage.
