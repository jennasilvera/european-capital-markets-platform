# Phase 1 Market Reference Mappings

## Purpose

This document records the reviewed source-selection decisions behind concrete
entries in `data/reference/market_series_catalog.json`.

The catalog stores reference-level selection metadata.

This document explains why a particular economic series and provider identifier
were selected.

Neither the catalog nor this document is observation evidence. Every populated
market observation must still carry normal `SourceRecord` and `EvidenceRecord`
lineage for the material actually accessed when that observation was created.

The mappings below were reviewed on 2026-09-19.

## Selection Principles

Mappings are selected using the following order of preference:

1. official institutional series where the authoritative institution directly
   publishes the required economic value;
2. benchmark administrators or established market-data publishers where the
   required traded benchmark is not an official institutional statistic;
3. no placeholder identifier is committed merely to complete nominal coverage.

Provider identifiers are recorded only where an official or administrator
source exposes a stable identifier suitable for distinguishing the selected
series.

### Publication-Frequency Interpretation

`expected_publication_frequency` records the date-level availability expected by
the Phase 1 canonical market layer. It does not claim that the provider's raw
source is calculated or disseminated only at that frequency.

This distinction matters for the STOXX Europe 600 and VSTOXX selections. Their
official index pages describe the selected indices as real-time calculations,
while the current canonical observation model is deliberately date-granular.
Their catalog value of `BUSINESS_DAILY` therefore means that a governed
date-level observation is expected for each relevant business day. It does not
represent the raw intraday dissemination cadence.

No intraday index levels are made canonical by this mapping increment.

`active_from` and `active_to` remain `null` in this increment because historical
availability and the effective applicability period of the platform's selection
have not yet been separately governed.

No raw external market data is committed by this mapping increment.

## ECB Deposit Facility Rate

Canonical ID:

`MKS000000001`

Selected economic series:

European Central Bank Deposit Facility Rate.

Selected provider series key:

`FM.D.U2.EUR.4F.KR.DFR.LEV`

Official references:

- <https://data.ecb.europa.eu/data/datasets/FM/FM.D.U2.EUR.4F.KR.DFR.LEV>
- <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html>

Rationale:

The ECB Data Portal identifies this as the daily euro-area deposit-facility
level series. The ECB states that the monetary-policy stance is steered through
the deposit facility rate. It is therefore selected as the Phase 1 euro-area
policy-rate reference rather than using an ambiguous generic "ECB rate".

Source classification:

- publisher: European Central Bank;
- source tier: `OFFICIAL_INSTITUTION`;
- source type: `CENTRAL_BANK_PUBLICATION`.

## German Sovereign Benchmarks

Canonical IDs:

- `MKS000000002` — 2Y;
- `MKS000000003` — 5Y;
- `MKS000000004` — 10Y.

Selected provider series:

- 2Y: `BBSSY.D.REN.EUR.A610.000000WT0202.A`;
- 5Y: `BBSSY.D.REN.EUR.A620.000000WT0505.A`;
- 10Y: `BBSSY.D.REN.EUR.A630.000000WT1010.A`.

Official reference:

<https://www.bundesbank.de/en/statistics/overview-of-the-statistical-series/-/3-yields-of-current-federal-securities-914558>

Rationale:

The Deutsche Bundesbank directly publishes daily yields for the current
two-year Federal Treasury notes, current five-year Federal notes, and current
10-year Federal bond. These satisfy the framework's initial German sovereign
2Y/5Y/10Y benchmark requirement without introducing a commercial intermediary.

These are current-security benchmark series. They are not the same economic
concept as constant-maturity fitted sovereign-curve points, and the catalog
identity makes that distinction explicit through `benchmark_ref` and
`convention_ref`.

Source classification:

- publisher: Deutsche Bundesbank;
- source tier: `OFFICIAL_INSTITUTION`;
- source type: `OFFICIAL_STATISTICS`.

## EUR Swap Benchmarks

Canonical IDs:

- `MKS000000005` — 2Y;
- `MKS000000006` — 5Y;
- `MKS000000007` — 10Y.

Selected benchmark:

ICE Swap Rate EUR EURIBOR 1100.

Selected provider identifiers:

- 2Y: `GB00BL53X451`;
- 5Y: `GB00BL53ZG16`;
- 10Y: `GB00BL54030`.

Administrator references:

- <https://www.ice.com/iba/ice-swap-rate>
- <https://www.ice.com/publicdocs/ISR_Benchmark_statement.pdf>

Rationale:

ICE Benchmark Administration publishes EUR EURIBOR 1100 settings for all three
required Phase 1 tenors.

For tenors greater than one year, the administrator specifies:

- floating rate: 6M EURIBOR;
- fixed-leg period: annual;
- fixed-leg day count: 30/360.

The published benchmark ISIN for each tenor is used as
`provider_series_id`. The textual benchmark setting remains part of the
economic convention rather than being encoded into the canonical
`market_series_id`.

Source classification:

- publisher: ICE Benchmark Administration Limited;
- source tier: `ESTABLISHED_MARKET_DATA`;
- source type: `MARKET_DATA`.

### Licensing Boundary

ICE Swap Rate benchmark data is licensed market data.

This repository records only the benchmark selection, economic definition,
administrator references, and identifiers.

It does not commit ICE Swap Rate observations or redistribute licensed
benchmark datasets.

Any later ingestion implementation must separately establish the applicable
access and redistribution rights.

## STOXX Europe 600

Canonical ID:

`MKS000000008`

Selected index:

STOXX Europe 600, EUR price-return version.

Selected provider symbol:

`SXXP`

Official reference:

<https://stoxx.com/index/sxxp/>

Official ISIN:

`EU0009658202`

Rationale:

The framework requires the STOXX Europe 600 as the initial broad European
equity benchmark. The EUR price-return variant is selected explicitly so the
canonical identity does not collapse price, net-return, gross-return, or
currency variants.

Source classification:

- publisher: STOXX Ltd.;
- source tier: `ESTABLISHED_MARKET_DATA`;
- source type: `MARKET_DATA`.

## VSTOXX

Canonical ID:

`MKS000000009`

Selected index:

EURO STOXX 50 Volatility (VSTOXX), 30-day main index.

Selected provider symbol:

`V2TX`

Official references:

- <https://stoxx.com/index/v2tx/>
- <https://stoxx.com/vstoxx-and-volatility-strategy-indices/>

Official ISIN:

`DE000A0C3QF1`

Rationale:

The framework requires a defined European equity-volatility benchmark.
STOXX identifies V2TX as the main 30-day VSTOXX index. It is based on
EURO STOXX 50 options and therefore provides a defined measurable volatility
series rather than a qualitative market-volatility label.

Source classification:

- publisher: STOXX Ltd.;
- source tier: `ESTABLISHED_MARKET_DATA`;
- source type: `MARKET_DATA`.

## Deliberately Deferred Credit Mappings

The Phase 1 framework also requires:

- broad European investment-grade credit spread;
- broad European high-yield credit spread.

Those mappings are intentionally not populated in this increment.

The platform will not commit a placeholder ticker or distributor-specific
series merely to satisfy nominal coverage.

Before adding the credit mappings, the project must separately review:

1. the benchmark family;
2. the exact credit universe and currency;
3. the spread measure, including OAS methodology where applicable;
4. the benchmark administrator versus downstream distributor identifier;
5. licensing and redistribution constraints;
6. whether the selected identifier can support reproducible ingestion.

Until that review is complete, the absence of a `CREDIT_SPREAD` catalog entry
is deliberate and visible.

## Ingestion Boundary

This increment does not:

- fetch market values;
- implement provider APIs;
- store credentials;
- add an ingestion schedule;
- create canonical observations;
- create observation `SourceRecord` or `EvidenceRecord` objects;
- commit raw external datasets;
- calculate market moves.

Those steps remain subsequent controlled increments.
