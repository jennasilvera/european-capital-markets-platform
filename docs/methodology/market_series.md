# Canonical Market-Series Model

## Purpose

Market data should not be attached directly to a transaction merely because it
is later used in transaction analysis.

An FX reference rate, benchmark yield, credit spread, equity index level, or
volatility measure describes a market series.

The platform therefore introduces a canonical `MARKET_SERIES` subject type.

A market series provides stable economic identity.

A dated market value remains an `ObservationRecord`.

This preserves the existing separation between:

- stable identity;
- type-specific series definition;
- time-varying observations;
- source evidence;
- calculation lineage.

## Generic Identity versus Type-Specific Definition

`MarketSeriesRecord` contains only dimensions that apply to every market series:

- permanent market-series ID;
- market-series type;
- optional display label.

Product- or asset-specific identity dimensions belong in separate definition
records.

The initial type-specific definition is:

`FXReferenceRateDefinitionRecord`

This avoids forcing future government-yield, swap-rate, credit-spread, equity-
index, or volatility series to carry meaningless FX-specific fields.

## Permanent Identifier

Canonical market series use:

`MKS#########`

For example:

`MKS000000001`

The identifier is non-semantic.

It must not encode:

- currencies;
- vendor tickers;
- publishers;
- fixing names;
- benchmark names.

Those semantics belong in governed definition or provenance fields.

## Initial Supported Series Type

The initial supported series type is:

`FX_REFERENCE_RATE`

The platform intentionally does not yet call this `FX_SPOT`.

The current `ObservationRecord` has an `as_of_date` but no observation timestamp
or fixing timestamp.

Calling a date-only observation an unrestricted spot price would imply temporal
precision that the data model does not actually preserve.

True intraday spot snapshots or time-specific fixings should be introduced only
after the observation model has explicit time/fixing semantics.

## FX Reference-Rate Identity

An FX reference-rate series requires an
`FXReferenceRateDefinitionRecord`.

Its economic identity consists of:

- base currency;
- quote currency;
- rate convention reference.

The orientation is meaningful.

For a definition with:

- base currency: `EUR`;
- quote currency: `GBP`;

the platform interprets the rate as:

`1 EUR = rate × GBP`

An observation of `0.8650` therefore means:

`1 EUR = 0.8650 GBP`

The reverse pair is a different canonical orientation.

## Rate Convention Reference

`convention_ref` identifies the governed definition of the rate being observed.

It distinguishes economically different date-level rate series for the same
currency pair.

For example, two EUR/GBP series may legitimately differ because one represents
one governed daily reference methodology and another represents a different
closing or benchmark convention.

Those are not automatically treated as source disagreement.

The convention reference is not:

- an evidence URL;
- a vendor ticker;
- a source-record ID.

It is a stable internal reference to the methodology or benchmark convention
that defines what the series means.

The detailed convention document may later specify:

- administrator or benchmark family where relevant;
- observation/fixing convention;
- applicable timezone;
- publication convention;
- holiday treatment;
- fallback treatment;
- revision handling.

## Provider and Evidence Separation

Provider-specific provenance remains in the source/evidence layer.

Two sources reporting the same economically defined series may support separate
observations on the same market-series subject.

If those sources disagree, the disagreement remains visible in the observation
and verification layers.

A new market-series identity should not be created merely because a different
website or data vendor supplied the value.

Conversely, genuinely different benchmark or fixing conventions should not be
collapsed merely because they use the same currency pair.

## Semantic Uniqueness

Within one canonical market-series bundle, the following FX reference-rate key
must be unique:

`(base_currency, quote_currency, convention_ref)`

Therefore:

- identical pair + identical convention = duplicate canonical identity;
- identical pair + different convention = distinct valid identities;
- reverse pair = distinct valid identity.

Every `FX_REFERENCE_RATE` market series must have exactly one FX reference-rate
definition.

An FX definition may not exist without its corresponding canonical market
series.

## Governed FX Observation

The initial governed field is:

`market_series.fx_rate`

It belongs to:

`EntityType.MARKET_SERIES`

For a populated observation, the rate must:

- be a `Decimal`;
- be strictly greater than zero.

The observation does not carry currency metadata because pair orientation is
defined by the FX reference-rate definition.

The observation does not carry a free-form display unit.

Its semantic unit is:

`quote currency per one base currency`

## Time and Evidence

The canonical market-series identity and FX definition are stable identity
records.

The actual observed rate retains normal observation semantics:

- `as_of_date`;
- value class;
- verification state;
- evidence IDs;
- source provenance;
- derivation reference where applicable;
- explicit missing-data state;
- notes.

The current platform is date-granular.

A convention may define what a date-level reference value means, but the
platform must not claim intraday precision that is absent from the observation
record.

## Missing Rates

A missing FX rate uses the normal explicit missing-data model.

It is not represented as:

- zero;
- one;
- an empty string;
- a copied previous value;
- a fabricated fallback rate.

## Separation from FX Conversion

This market-series layer does not yet perform currency conversion.

It establishes the identities required for the later deterministic conversion
layer.

A future FX conversion should reference the exact
`market_series.fx_rate` observation used.

The conversion methodology should then govern:

- source amount;
- source currency;
- target currency;
- exact FX-rate observation ID;
- pair orientation;
- multiplication versus division;
- conversion date;
- rounding convention;
- calculated-output lineage.

## Cross-Currency Transaction Aggregates

The existing consistency layer correctly continues to defer direct arithmetic
validation of multi-currency transaction aggregates.

Once converted tranche observations carry explicit FX-rate observation lineage,
the platform can validate a converted aggregate from deterministic converted
inputs rather than adding unlike native currencies.

## Future Market-Series Types

The generic `MARKET_SERIES` identity is designed so that future series types can
add their own definition records.

Potential future examples include:

- government yield definitions;
- swap-rate definitions;
- credit-spread definitions;
- equity-index definitions;
- volatility-index definitions.

Each should introduce only the identity dimensions required by that market-data
type.
