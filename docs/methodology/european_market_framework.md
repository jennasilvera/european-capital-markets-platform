# European Market Framework

## Purpose

Phase 1 establishes the canonical market framework required to assess European
capital-markets issuance conditions.

The framework defines:

- which external market concepts belong in canonical market-series data;
- how those series are identified;
- which values are stored as governed observations;
- how point-in-time market changes are calculated;
- which concepts remain downstream analytics rather than canonical facts;
- how future source mappings and recurring updates can be added without changing
  the underlying analytical meaning.

This document freezes analytical semantics before additional market-series
domain models, persistence tables, reference catalogs, or ingestion pipelines
are introduced.

It does not freeze a specific market-data vendor.

It does not populate live market observations.

## Analytical Objective

The Phase 1 market framework must support the question:

> What changed in European financing conditions, why does it matter, and what
> does it imply for potential issuers?

Only market variables with a defensible relationship to issuance conditions
belong in the initial framework.

The initial external-market coverage is organized around:

1. monetary policy;
2. sovereign benchmark yields;
3. swap rates;
4. credit spreads;
5. equity-market levels;
6. volatility.

Primary-market issuance aggregates are treated separately because they can
ultimately be derived from the platform's canonical transaction universe.

## Canonical Boundary

A market series represents a stable economic concept through time.

A date-level observation represents the value reported for that series on a
specific analytical date.

Those concepts must remain separate.

For example:

- "EUR 5-year swap rate" is a series identity;
- "2.43% on 2026-09-18" is an observation.

A new observation does not create a new market-series identity.

A change in the economic definition of the series does.

## Generic Market-Series Identity

`MarketSeriesRecord` remains the generic canonical identity anchor.

Product- or asset-specific identity dimensions belong in separate definition
records rather than being added directly to `MarketSeriesRecord`.

This preserves the existing pattern established by:

`FXReferenceRateDefinitionRecord`

and avoids forcing unrelated market series to carry meaningless dimensions.

The Phase 1 framework anticipates the following additional
`MarketSeriesType` concepts:

- `POLICY_RATE`;
- `GOVERNMENT_YIELD`;
- `SWAP_RATE`;
- `CREDIT_SPREAD`;
- `EQUITY_INDEX`;
- `VOLATILITY_INDEX`.

These values are frozen here as analytical concepts only.

Adding them to the executable taxonomy requires a separately reviewed domain
and persistence migration because the current PostgreSQL schema constrains the
permitted market-series types.

## Policy Rates

A policy-rate series represents one explicitly identified central-bank policy
rate.

Required identity dimensions should be sufficient to distinguish:

- central bank or policy authority;
- jurisdiction;
- currency;
- named policy rate;
- rate convention or methodology reference.

The initial European framework must support the relevant ECB policy-rate
series.

The model must not assume that one generic "ECB rate" permanently identifies
the economically relevant policy instrument.

If the central bank changes its operating framework, the convention reference
must preserve which rate is being observed.

### Observation

The governed value should use:

`market_series.rate_percent`

with:

- scalar type: `Decimal`;
- unit: `PERCENT`;
- no currency metadata on the observation value itself.

Currency is an identity dimension of the series rather than a monetary amount
attached to the rate observation.

## Government Benchmark Yields

A government-yield series represents the yield of a defined sovereign benchmark
or sovereign curve point.

Required identity dimensions should be sufficient to distinguish:

- sovereign or jurisdiction;
- currency;
- tenor or maturity point;
- benchmark or instrument-family definition;
- yield convention reference.

The initial European framework must support the German sovereign curve used as
the primary EUR risk-free or near-risk-free government reference for issuance
analysis.

Initial analytical tenor coverage should include, where supported by the
selected source:

- 2-year;
- 5-year;
- 10-year.

Additional curve points may be added without changing the underlying domain
meaning.

### Observation

The governed value should use:

`market_series.yield_percent`

with:

- scalar type: `Decimal`;
- unit: `PERCENT`;
- no observation currency metadata.

Negative yields must remain representable.

The domain must therefore not impose a generic positive-value constraint on
government yields.

## Swap Rates

A swap-rate series represents one defined fixed-versus-floating interest-rate
swap benchmark.

Required identity dimensions should be sufficient to distinguish:

- currency;
- tenor;
- floating-rate index or benchmark;
- fixed-leg convention;
- broader market-convention reference where necessary.

The initial framework must support the EUR swap curve.

Initial analytical tenor coverage should include, where supported by the
selected source:

- 2-year;
- 5-year;
- 10-year.

### Observation

The governed value should use:

`market_series.rate_percent`

with:

- scalar type: `Decimal`;
- unit: `PERCENT`;
- no observation currency metadata.

Negative swap rates must remain representable.

## Credit Spreads

A credit-spread series represents a defined spread measure for a specified
credit universe or index.

Required identity dimensions should be sufficient to distinguish:

- index or benchmark family;
- currency;
- credit universe;
- rating or quality segment where relevant;
- sector segment where relevant;
- spread measure;
- convention or methodology reference.

The initial framework must support at least:

- European investment-grade credit;
- European high-yield credit.

More granular rating, sector, tenor, or index-family series may be added later
without changing the meaning of those broad market concepts.

The framework must not collapse:

- investment grade and high yield;
- rating segments;
- sectors;
- different spread measures

into one generic spread series.

### Observation

The governed value should use:

`market_series.spread_bps`

with:

- scalar type: `Decimal`;
- unit: `BASIS_POINTS`;
- no observation currency metadata.

A source-specific spread methodology must remain visible in the series
definition or convention reference.

## Equity Indices

An equity-index series represents one economically defined equity benchmark.

Required identity dimensions should be sufficient to distinguish:

- canonical index identifier or name;
- geographic or sector universe;
- index variant where economically relevant;
- price versus total-return convention;
- calculation or methodology reference.

The initial broad European equity benchmark should support the
STOXX Europe 600 framework requirement.

Selected country and sector indices belong in controlled reference data rather
than in the domain taxonomy itself.

The list of required country and sector indices may therefore evolve without
requiring a Python enum change.

### Observation

The governed value should use:

`market_series.index_level`

with:

- scalar type: `Decimal`;
- unit: `INDEX_POINTS`;
- no currency metadata unless a future index methodology demonstrates that
  currency is analytically necessary for the canonical value.

A populated index level must be greater than zero unless a later documented
series methodology establishes a legitimate exception.

## Volatility Indices

A volatility-index series represents a defined market-implied or published
volatility benchmark.

Required identity dimensions should be sufficient to distinguish:

- benchmark or index name;
- underlying market or equity index;
- horizon where economically relevant;
- methodology or convention reference.

The framework must not treat generic statements such as "volatility is high" as
canonical observations.

Only a defined measurable series belongs in the canonical market layer.

### Observation

The governed value should use:

`market_series.volatility_level`

with:

- scalar type: `Decimal`;
- unit: `INDEX_POINTS`;
- no currency metadata.

A populated volatility-index level must be non-negative.

## Observation Units

The existing controlled units remain authoritative.

Phase 1 requires one additional controlled unit:

`INDEX_POINTS`

It is intended for:

- equity-index levels;
- published volatility-index levels.

Display formatting must not change the canonical stored value.

## Observation Dates

The initial Phase 1 market framework is daily.

`ObservationRecord.as_of_date` represents the economic date of the observed
market value.

It is not:

- the source access date;
- the publication timestamp;
- the ingestion timestamp.

Those source and processing concepts remain governed separately.

The initial framework does not attempt to represent intraday ticks.

If intraday market data later becomes analytically necessary, the temporal
domain contract must be explicitly extended rather than encoding timestamps in
notes or source locators.

## Source and Evidence Requirements

Every populated external market observation must remain traceable to evidence.

Source preference depends on the series.

Official institutional sources are preferred where they publish the canonical
economic value directly, including central-bank or official statistical data.

Established market-data sources may be required for market-traded indices,
credit benchmarks, or other values not available from an official institution.

A lower-tier source must not silently redefine an economically different series
under the same canonical market-series ID.

Source identity and economic series identity remain separate concepts.

Two sources reporting the same economically defined series may support the same
canonical series.

## Verification and Value Class

Externally reported market observations should normally be represented as
source-backed disclosed values where the existing lineage rules permit that
classification.

Calculated market values remain separate observations and must retain explicit:

- input observation IDs;
- derivation reference;
- calculation methodology.

Estimated or assumed market values must never be presented as observed market
facts.

## Missing Market Data

Missing data uses the platform's normal explicit missing-data semantics.

A missing market observation must not be replaced by:

- zero;
- the previous day's value;
- an undocumented interpolation;
- a secondary fallback value represented as though it were the primary series;
- an analyst estimate represented as an observed value.

Where interpolation, carry-forward, or another transformation becomes
analytically necessary, it must be represented as an explicit calculated or
estimated observation under a governed methodology.

## Historical Corrections and Conflicts

Historical source corrections must not silently rewrite the economic meaning of
the canonical series.

Conflicting source observations should remain traceable.

The platform should preserve enough lineage to distinguish:

- the value originally observed;
- a later corrected source value;
- competing source values;
- the value ultimately selected for a controlled analytical output.

A convenience "latest" view must never destroy the underlying history.

## Market Change Calculations

Canonical observations store market levels.

Period-over-period changes are analytical calculations.

### Rates and Yields

For values stored in percentage points:

`change_bps = (current_percent - prior_percent) * 100`

Example:

- prior: 2.40%;
- current: 2.55%;
- change: +15 bps.

### Credit Spreads

For values already stored in basis points:

`change_bps = current_bps - prior_bps`

### Equity Indices

Equity-market performance should normally be calculated as:

`return_percent = ((current_level / prior_level) - 1) * 100`

The underlying canonical index levels remain unchanged.

### Volatility Indices

The primary change measure should be the point change:

`change_points = current_level - prior_level`

A percentage change may be calculated separately when analytically useful.

## Calculation Precision

Canonical numeric market observations use `Decimal`.

Analytical change calculations must not pass through binary floating point.

Presentation rounding belongs downstream from canonical storage and analytical
calculation.

## Initial Phase 1 Coverage

The initial European market framework must be capable of representing:

### Monetary Policy

- relevant ECB policy rate.

### Sovereign Rates

- German sovereign benchmark curve;
- minimum initial analytical tenor set of 2Y, 5Y, and 10Y where available.

### Swap Rates

- EUR swap curve;
- minimum initial analytical tenor set of 2Y, 5Y, and 10Y where available.

### Credit

- broad European investment-grade spread benchmark;
- broad European high-yield spread benchmark.

### Equity

- STOXX Europe 600;
- selected major country indices;
- selected sector indices relevant to issuer analysis.

### Volatility

- at least one defined European equity-volatility benchmark appropriate for the
  selected equity-market framework.

Exact source instruments, provider identifiers, country indices, sector
indices, and series IDs belong in controlled reference data.

They must not be hard-coded into the domain taxonomy.

## Primary-Market Metrics Boundary

Primary-market activity is analytically important but is not automatically an
external `MarketSeriesType`.

Metrics such as:

- weekly issuance volume;
- monthly issuance volume;
- year-to-date issuance volume;
- transaction count;
- average transaction size;
- market reopening or closure patterns

should ultimately be derived from the platform's canonical transaction
databases where those databases provide sufficient coverage.

Those metrics therefore belong to transaction and market analytics rather than
being duplicated as independent canonical market observations merely for
dashboard convenience.

If an external primary-market aggregate later provides distinct analytical
value, it must receive its own explicitly governed methodology rather than being
silently treated as equivalent to the platform-derived aggregate.

## Reference-Data Boundary

Concrete market-series instances belong in controlled reference data.

A future reference catalog should define, at minimum:

- canonical market-series ID;
- series type;
- display label;
- type-specific identity dimensions;
- source or provider mapping;
- provider series identifier where applicable;
- expected publication frequency;
- active-from date where known;
- active-to date where known;
- methodology or convention reference;
- notes.

Reference data selects concrete series.

Domain code defines their semantics.

The two responsibilities must not be collapsed.

## Analytics Boundary

The canonical market layer stores:

- stable series identity;
- type-specific economic definition;
- sourced observations;
- evidence and lineage.

The analytical layer derives:

- changes over selected periods;
- curve moves;
- spread tightening or widening;
- equity performance;
- volatility moves;
- comparisons with prior issuance windows;
- market-condition commentary.

The canonical layer must not store dashboard conclusions such as:

- favorable;
- mixed;
- unfavorable.

Those are downstream analytical judgments.

## Commentary Boundary

Recurring market commentary should use the structure:

1. WHAT CHANGED
2. WHY IT MATTERS
3. IMPLICATION FOR ISSUERS

The first section must be mechanically supported by canonical observations and
reproducible calculations.

The second and third sections are analytical interpretation.

Interpretation must not be written back into canonical market observations as
though it were sourced market data.

## Quality Controls

The Phase 1 implementation should eventually enforce or test:

- permanent canonical market-series ID shape;
- unique market-series IDs;
- unique type-specific economic identities;
- one valid type-specific definition for each typed series where required;
- no type-specific definition attached to an incompatible series type;
- observation field compatible with series type;
- required units present on populated observations;
- forbidden units absent;
- evidence and verification rules satisfied;
- duplicate same-series/date source records identifiable;
- missing values remain explicit;
- no undocumented interpolation;
- no binary floating-point market values;
- historical observations remain reproducible.

Range validation should remain economically defensible.

The platform must not reject legitimate negative government yields or swap
rates merely because most observed values are positive.

## Implementation Sequence

After this methodology is reviewed and frozen, implementation should proceed in
small controlled increments:

1. extend `MarketSeriesType`;
2. define type-specific frozen market-series definition records;
3. extend governed observation fields and units;
4. extend market-data bundle validation;
5. extend `CanonicalDataset`;
6. add unit tests for normal and awkward cases;
7. design the persistence extension;
8. add a reviewed Alembic migration;
9. extend writer and reader round-trip coverage;
10. add PostgreSQL integration tests;
11. establish controlled reference-series catalog structure;
12. only then add actual series mappings or ingestion.

No live market source should be wired into the canonical platform before the
semantic and persistence contracts for that series family are frozen.

## Deliberately Deferred

Phase 1 does not yet freeze:

- a particular commercial data vendor;
- provider API schemas;
- live provider identifiers;
- ingestion scheduling;
- intraday observations;
- arbitrary market-condition scores;
- primary-market volume aggregates duplicated from transaction data;
- product-specific dashboard layouts;
- client recommendations.

Those belong to later implementation or analytical phases.

## Completion Standard

The European market framework convention is complete when another analyst can
determine, without relying on undocumented assumptions:

1. what each canonical market series represents;
2. which dimensions define its identity;
3. which observation field and unit represent its value;
4. what date the observation describes;
5. what source evidence supports it;
6. how historical changes are calculated;
7. which metrics are canonical facts versus downstream analytics;
8. which concepts remain deliberately deferred.

Only after those questions are answerable should Phase 1 move from convention
design into executable domain-model implementation.
