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

Instrument monetary observations should agree with the latest known populated
`instrument.currency` observation at or before the monetary observation's
as-of date.

The control applies to governed instrument fields whose currency binding is
`INSTRUMENT_CURRENCY`.

Examples include:

- `instrument.issue_size`;
- `instrument.book_size`;
- `instrument.offer_price_per_share`.

If no populated instrument-currency observation exists at or before the
relevant date, the consistency layer does not invent one and does not fail the
monetary observation.

## Missingness Is Not Retraction

A missing-data observation records the state of available information.

It does not, by itself, invalidate or retract an earlier populated observation.

For example:

- EUR observed on 1 September;
- currency pending verification on 2 September;
- EUR-denominated issue size observed on 3 September.

The latest known populated currency remains EUR.

The 2 September missing observation remains part of the audit trail because it
records what was or was not available at that point, but it does not behave as
a tombstone.

Similarly, a populated EUR observation and a missing currency observation on
the same date are not inherently contradictory. One source or workflow may
lack the value while another establishes it.

If the platform later requires explicit retraction, invalidation, or
supersession of a populated fact, that state must be represented by a dedicated
governed mechanism. It must not be inferred from `MissingDataState`.

## Same-Date Populated Conflicts

If the latest populated instrument-currency date contains multiple populated
observations with different values, the currency state is contradictory and
validation fails.

If multiple populated observations carry the same value on that date, the
economic conclusion is not ambiguous.

Missing observations on the same date do not change either rule.

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

The platform does not add unlike native currencies and no longer defers
validation of such a calculation.

Every input to a calculated `transaction.aggregate_size` must already be
expressed in the aggregate's currency.

A native tranche whose currency equals the aggregate currency may be referenced
directly through `instrument.issue_size`.

A tranche denominated in another currency must first be represented by a
validated `instrument.issue_size_converted` observation.

That converted observation must retain explicit lineage to:

- the native `instrument.issue_size`;
- the exact `market_series.fx_rate` observation used;
- the governed FX conversion methodology.

For example, an EUR aggregate containing an EUR tranche and a GBP tranche must
reference:

- the native EUR `instrument.issue_size`; and
- the EUR `instrument.issue_size_converted` derived from the native GBP tranche.

It must not reference the native GBP amount directly.

Once all inputs are currency-normalized, exact `Decimal` arithmetic is enforced
against the calculated aggregate.

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
