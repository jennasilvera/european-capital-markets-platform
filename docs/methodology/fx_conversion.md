# FX Conversion Methodology

## Purpose

Native transaction economics and analytical currency conversions are different
facts.

The platform must preserve both.

A GBP-denominated tranche remains GBP-denominated after it is translated into
EUR for transaction-level analysis.

The native observation is therefore never overwritten.

## Native Monetary Fact

The canonical native issuance amount remains:

`instrument.issue_size`

Its currency binding is:

`INSTRUMENT_CURRENCY`

This means the observation currency must reconcile with the instrument's latest
known `instrument.currency` state at or before the observation date.

Example:

`instrument.issue_size = GBP 300,000,000`

## Converted Analytical Value

The governed converted field is:

`instrument.issue_size_converted`

Its currency binding is:

`OBSERVATION_CURRENCY`

The observation's currency therefore identifies the target analytical currency
and is not required to match the instrument's denomination currency.

Example:

- native issue size: GBP 300,000,000;
- target analytical currency: EUR;
- converted observation: EUR equivalent.

The converted observation does not replace the GBP observation.

## Required Lineage

A populated `instrument.issue_size_converted` must be a `CALCULATED`
observation.

It must reference exactly two input observations:

1. one native `instrument.issue_size` observation for the same instrument;
2. one `market_series.fx_rate` observation.

No implicit FX lookup is permitted.

The exact FX observation used must therefore be visible in calculation lineage.

The current governed derivation reference is:

`methodology/fx-conversion-v1`

A converted issue-size observation may not substitute an arbitrary derivation
reference. A future calculation methodology requires an explicit versioned
schema and validator change rather than silently changing the meaning of an
existing calculation.

## Pair Orientation

An FX reference-rate definition uses:

- base currency;
- quote currency.

The platform interprets the rate as:

`1 BASE = rate × QUOTE`

If converting BASE to QUOTE:

`target = source × rate`

If converting QUOTE to BASE:

`target = source ÷ rate`

A rate whose pair contains neither the source/target orientation nor its inverse
cannot be used.

## Conversion Date

The converted observation's `as_of_date` must equal the referenced FX-rate
observation's `as_of_date`.

The native issue-size observation may predate the conversion because the native
economic fact can remain valid while the analytical reporting date changes.

A future input observation is never permitted.

## Calculation Precision and Rounding

FX arithmetic uses `Decimal`.

Canonical FX calculation uses:

- precision: 38 significant digits;
- rounding mode: `ROUND_HALF_EVEN`.

Both settings are established inside the conversion calculation rather than
inherited from the caller's ambient Decimal context.

This is a calculation-precision rule. It is necessary because inverse FX
conversion can produce a non-terminating decimal expansion.

It is distinct from presentation rounding.

Formatting to millions, billions, whole currency units, or a chosen number of
display decimal places belongs downstream in presentation or explicitly
governed reporting methodology.

## Same-Currency Conversion

`instrument.issue_size_converted` is reserved for genuine currency conversion.

The source and target currencies must differ.

A same-currency analytical copy should not be created merely for convenience.

## Transaction Aggregation

A calculated `transaction.aggregate_size` may use:

- native `instrument.issue_size` inputs; and/or
- validated `instrument.issue_size_converted` inputs.

When all referenced inputs use the aggregate's currency, the aggregate must
equal their exact Decimal sum.

This allows a multi-currency transaction to be represented without destroying
native economics.

For example:

- EUR tranche native amount: EUR 500m;
- GBP tranche native amount: GBP 300m;
- GBP tranche converted value: EUR 346.8m;
- transaction aggregate: EUR 846.8m.

The aggregate references the EUR native tranche plus the EUR converted GBP
tranche.

It does not add EUR and GBP directly.

## Auditability

A reviewer must be able to recover:

- native amount;
- native currency;
- target currency;
- exact FX series;
- exact FX observation;
- FX observation date;
- pair orientation;
- multiply/divide direction;
- calculated result;
- downstream aggregate using the result.

This allows the analytical currency view to be reproduced without modifying
the source economics.
