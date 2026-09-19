# European Capital Markets Issuance & Execution Intelligence Platform

A governed analytical and engineering platform for European capital-markets
issuance, financing conditions, transaction intelligence, execution analysis,
and reproducible decision support.

The system is designed to connect canonical transaction data, external market
conditions, precedent analysis, company financing models, and controlled
analytical outputs while preserving the lineage required to explain how a
conclusion was produced.

> **Development status**
>
> The foundational canonical domain, source and evidence framework, PostgreSQL
> persistence layer, European market-series model, database integrity controls,
> and lossless market-series persistence are implemented.
>
> Controlled reference-series catalog structure and the first reviewed
> source/provider mappings are implemented.
> Remaining provider mappings, ingestion, market analytics, financing models, dashboards,
> and client-facing outputs follow as separately reviewed layers.

---

## Contents

- [Purpose](#purpose)
- [Architecture](#architecture)
- [Design Principles](#design-principles)
- [Analytical Scope](#analytical-scope)
- [Canonical Data Model](#canonical-data-model)
- [Market-Series Framework](#market-series-framework)
- [Source, Evidence, and Lineage](#source-evidence-and-lineage)
- [Information Governance](#information-governance)
- [Persistence Architecture](#persistence-architecture)
- [Database Integrity](#database-integrity)
- [Repository Structure](#repository-structure)
- [Technology Stack](#technology-stack)
- [Development](#development)
- [Testing and CI](#testing-and-ci)
- [Current Implementation](#current-implementation)
- [Roadmap](#roadmap)
- [Methodology](#methodology)
- [Intended Use](#intended-use)

---

## Purpose

Capital-markets analysis rarely depends on one source or one model.

A financing decision can require information from:

- transaction documentation;
- issuer disclosures;
- historical precedents;
- market-data sources;
- central banks and official institutions;
- credit and equity benchmarks;
- company financial statements;
- capital-structure models;
- execution calendars;
- analyst assumptions;
- strategic judgment.

The engineering problem is therefore not simply acquiring data.

The platform is designed to preserve enough structure and provenance to answer:

- What is a sourced fact?
- What was calculated?
- What was estimated or assumed?
- Which evidence supports a value?
- Which economic definition does a market series represent?
- Which data and methodology produced an analytical conclusion?
- Can the analysis be reproduced later?
- If a conclusion changes, can the reason for that change be identified?

The objective is an analytical environment in which material conclusions are
traceable, reproducible, and reviewable.

---

## Architecture

The target analytical chain is:

~~~text
Transaction Data
      ↓
Market Conditions
      ↓
Precedent Analysis
      ↓
Company / Capital-Structure Model
      ↓
Financing Alternatives
      ↓
Execution Assessment
      ↓
Recommendation + Plan B
~~~

Each stage should be able to trace material inputs back through the layers that
produced them.

The platform therefore distinguishes between:

~~~text
Canonical Facts
      ↓
Reproducible Calculations
      ↓
Analytical Interpretation
      ↓
Strategic Judgment
~~~

Those layers are related, but they are not interchangeable.

---

## Design Principles

| Principle | Requirement |
| --- | --- |
| **Traceability** | Material facts and observations retain explicit source and evidence lineage. |
| **Reproducibility** | Historical analyses should be reconstructable from governed inputs and methodologies. |
| **Stable identity** | Canonical entities represent stable economic concepts rather than temporary source representations. |
| **Separation of concerns** | Facts, calculations, estimates, assumptions, and recommendations remain distinguishable. |
| **Explicit missingness** | Missing information is represented explicitly rather than silently replaced. |
| **Lossless persistence** | Frozen domain records survive database persistence and reconstruction without semantic loss. |
| **Database integrity** | Critical relational invariants are enforced by PostgreSQL as well as application code. |
| **Controlled change** | Methodology, schema, reference data, and release-state changes remain reviewable. |
| **Auditability** | Important transformations, exceptions, and assumptions remain visible. |
| **Institutional usability** | Architecture supports repeatable analytical workflows rather than isolated demonstrations. |

---

## Analytical Scope

The target platform spans five connected areas.

### Transaction Intelligence

The canonical transaction architecture is designed to support analysis across:

- Equity Capital Markets;
- Investment-Grade Debt Capital Markets;
- Leveraged Finance;
- capital-structure and financing events;
- instruments and tranches;
- observed transaction terms;
- execution outcomes;
- postponed transactions;
- withdrawn transactions;
- cancelled transactions.

Incomplete transactions remain analytically relevant.

The platform therefore avoids survivorship bias created by preserving only
completed deals.

### External Market Conditions

The canonical market layer currently supports seven market-series families:

- FX reference rates;
- monetary-policy rates;
- government benchmark yields;
- swap rates;
- credit spreads;
- equity indices;
- volatility indices.

A market series represents a stable economic concept through time.

A date-level observation represents the value associated with that series on a
specific economic date.

For example:

~~~text
Series identity
EUR 5-year swap rate

Observation
2.43% on a specified analytical date
~~~

A new observation does not create a new market-series identity.

A change in the economic definition of the series does.

### Precedent and Market Analytics

The analytical layer is intended to derive measures such as:

- transaction comparables;
- issuance volumes;
- transaction counts;
- average transaction size;
- rate and yield changes;
- curve movements;
- spread tightening and widening;
- equity-market performance;
- volatility movements;
- market reopening or closure patterns;
- execution-window comparisons.

Derived metrics remain separate from canonical source observations.

### Capital Structure and Financing

The architecture is intended to support company-level analysis of:

- historical financial performance;
- forecasts;
- existing capital structure;
- debt capacity;
- liquidity;
- maturity schedules;
- refinancing requirements;
- equity issuance;
- debt issuance;
- dilution;
- leverage;
- interest expense;
- financing alternatives;
- scenario analysis;
- execution timing.

### Decision Support

Recurring market commentary is intended to follow:

~~~text
WHAT CHANGED
      ↓
WHY IT MATTERS
      ↓
IMPLICATION FOR ISSUERS
~~~

`WHAT CHANGED` should be mechanically supportable from governed observations
and reproducible calculations.

`WHY IT MATTERS` and `IMPLICATION FOR ISSUERS` are analytical interpretation.

Interpretation must not be written into canonical data as though it were a
sourced fact.

---

## Canonical Data Model

The platform does not use a flat spreadsheet as its canonical architecture.

A simplified transaction hierarchy is:

~~~text
Issuer
  └── Financing Event / Transaction
        └── Instrument / Tranche
              └── Observed Terms
                    └── Source Evidence
~~~

External market data follows a parallel structure:

~~~text
MarketSeriesRecord
  └── Type-Specific Definition
        └── ObservationRecord
              └── EvidenceRecord
                    └── SourceRecord
~~~

The separation allows:

- economic identity to remain stable;
- observations to accumulate through time;
- source evidence to evolve independently;
- multiple evidence records to support governed facts;
- provider changes without silently redefining economic meaning.

---

## Market-Series Framework

Each supported market series has:

1. one generic `MarketSeriesRecord`; and
2. exactly one compatible type-specific definition.

| Series family | Economic identity |
| --- | --- |
| `FX_REFERENCE_RATE` | Base currency, quote currency, convention |
| `POLICY_RATE` | Authority, jurisdiction, currency, named rate, convention |
| `GOVERNMENT_YIELD` | Sovereign, jurisdiction, currency, tenor, benchmark, convention |
| `SWAP_RATE` | Currency, tenor, floating-rate reference, fixed-leg convention, broader convention |
| `CREDIT_SPREAD` | Benchmark family, currency, universe, optional rating/sector segments, spread measure, convention |
| `EQUITY_INDEX` | Index name, universe, index variant, methodology |
| `VOLATILITY_INDEX` | Index name, underlying reference, optional horizon, methodology |

The domain validates that:

- canonical IDs are valid;
- every typed market series has exactly one definition;
- the definition belongs to the correct series family;
- type-specific dimensions are valid;
- semantic identities are unique;
- observation fields are compatible with series type;
- units and scalar semantics are governed.

PostgreSQL independently enforces the corresponding persistence invariants.

---

## Source, Evidence, and Lineage

Provenance is a first-class part of the canonical architecture.

### Sources

`SourceRecord` identifies material that can be revisited.

Governed metadata includes:

- source ID;
- source tier;
- source type;
- publisher;
- title;
- access date;
- document date;
- publication date;
- URL;
- archived location;
- document version;
- notes.

### Evidence

`EvidenceRecord` identifies the reusable locator within a source that supports a
fact or observation.

Business records reference evidence explicitly rather than embedding
ungoverned URLs directly inside analytical records.

This supports:

- one source supporting multiple facts;
- reusable evidence locators;
- multiple pieces of evidence supporting one governed fact;
- reproducible historical lineage.

### Source hierarchy

The controlled source-preference hierarchy is:

1. `PRIMARY_TRANSACTION_OR_ISSUER`
2. `OFFICIAL_INSTITUTION`
3. `ESTABLISHED_MARKET_DATA`
4. `HIGH_QUALITY_SECONDARY`
5. `ANALYST_DERIVED`

Source tier and source type are separate concepts.

Controlled source types include:

- `PROSPECTUS`;
- `OFFERING_DOCUMENT`;
- `ISSUER_ANNOUNCEMENT`;
- `EXCHANGE_ANNOUNCEMENT`;
- `REGULATORY_FILING`;
- `FINANCIAL_REPORT`;
- `INVESTOR_PRESENTATION`;
- `RATING_AGENCY_PUBLICATION`;
- `CENTRAL_BANK_PUBLICATION`;
- `OFFICIAL_STATISTICS`;
- `MARKET_DATA`;
- `FINANCIAL_NEWS`;
- `ANALYST_WORKPAPER`;
- `OTHER`.

---

## Information Governance

### Value classes

Material analytical values remain distinguishable as:

~~~text
DISCLOSED
CALCULATED
ESTIMATED
ASSUMED
~~~

### Verification states

~~~text
PRIMARY_VERIFIED
SECONDARY_VERIFIED
CROSS_VERIFIED
PENDING
CONFLICT
UNAVAILABLE
~~~

### Missing-data states

~~~text
NOT_DISCLOSED
UNAVAILABLE
NOT_APPLICABLE
PENDING_VERIFICATION
~~~

Missing information must not silently become:

- zero;
- an empty-string proxy;
- the prior observation;
- an undocumented interpolation;
- a lower-quality source represented as a primary source;
- an analyst estimate represented as an observed fact.

Where interpolation, carry-forward, or estimation becomes analytically
necessary, the result should be represented as an explicit transformation
under a governed methodology.

### Currency and numerical discipline

Native currency is preserved.

Currency conversion is represented as a separate, dated transformation rather
than overwriting the native value.

Canonical financial values use decimal semantics where precision is material.

Presentation rounding belongs downstream from canonical storage and analytical
calculation.

---

## Persistence Architecture

The persistence layer uses:

- PostgreSQL;
- SQLAlchemy 2.x;
- psycopg 3;
- Alembic;
- atomic transactional writes;
- repeatable-read reconstruction;
- relational constraints;
- deferred integrity checks.

Current schema history:

~~~text
0001_canonical_schema
        ↓
0002_market_series_defs
~~~

### Transactional writer

`persist_canonical_dataset()`:

1. validates the complete canonical dataset;
2. opens one transaction;
3. persists canonical entities and relationships;
4. persists type-specific market-series definitions;
5. forces deferred PostgreSQL integrity checks before completion.

Supported canonical records must not be silently omitted.

### Snapshot reader

`load_canonical_dataset()` reconstructs the canonical dataset from a
repeatable-read, read-only database snapshot.

The reconstructed dataset is validated again before being returned.

### Lossless market persistence

All seven market-series definition families currently have:

- PostgreSQL storage;
- transactional writer support;
- reader reconstruction;
- domain validation;
- database integrity controls;
- PostgreSQL integration coverage;
- lossless persist/load round-trip testing.

---

## Database Integrity

Critical invariants are protected at the database boundary.

Current controls include:

- canonical identifier immutability;
- restrictive foreign-key behavior;
- observation-subject referential integrity;
- exact-one-definition enforcement for market series;
- compatibility between series type and definition table;
- semantic uniqueness constraints;
- tenor constraints where economically required;
- optional positive volatility horizons;
- controlled currency-code structure;
- nonblank persisted identity fields;
- nullable semantic uniqueness using PostgreSQL `NULLS NOT DISTINCT`;
- guarded downgrade behavior.

The current integration target is PostgreSQL 18.

---

## Release Governance

Analytical releases use controlled states:

~~~text
WORKING
   ↓
REVIEWED
   ↓
RELEASED
   ↓
SUPERSEDED
~~~

Released work should not be silently rewritten.

Corrections should produce a new governed version while preserving prior
released state and lineage.

---

## Repository Structure

~~~text
.
├── .github/
│   └── workflows/
├── analytics/
│   ├── ecm/
│   ├── ig_dcm/
│   ├── leveraged_finance/
│   └── market/
├── config/
├── controls/
│   ├── audit/
│   ├── exceptions/
│   └── release_checklists/
├── data/
│   ├── canonical/
│   ├── raw/
│   ├── reference/
│   └── staged/
├── docs/
│   └── methodology/
├── migrations/
│   └── versions/
├── models/
│   └── client/
├── outputs/
│   ├── client_materials/
│   ├── dashboards/
│   └── market_updates/
├── scripts/
├── sources/
├── src/
│   └── european_capital_markets/
│       ├── domain/
│       └── persistence/
└── tests/
    ├── integration/
    └── unit/
~~~

The intended information flow is:

~~~text
Raw Data
    ↓
Staged Data
    ↓
Canonical Data
    ↓
Analytics / Models
    ↓
Controlled Outputs
~~~

Reference data and source evidence remain separately governed.

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.12 |
| Package and environment management | `uv` |
| Database | PostgreSQL |
| Database abstraction | SQLAlchemy 2.x |
| PostgreSQL driver | psycopg 3 |
| Schema migrations | Alembic |
| Testing | pytest |
| Static analysis | Ruff |
| CI | GitHub Actions |
| Package layout | Python `src/` layout |

Python is currently constrained to:

~~~text
>=3.12,<3.13
~~~

---

## Development

### Requirements

- Git
- Python 3.12
- `uv`
- PostgreSQL for database integration work

### Clone and install

~~~bash
git clone https://github.com/jennasilvera/european-capital-markets-platform.git
cd european-capital-markets-platform

uv sync --all-groups
~~~

### Verify the environment

~~~bash
uv run python --version
uv run pytest --version
uv run ruff --version
uv run alembic --version
~~~

### Static analysis

~~~bash
uv run ruff check .
~~~

### Test suite

~~~bash
uv run pytest -q -ra
~~~

PostgreSQL integration tests are skipped when `DATABASE_URL` is unavailable.

### Lockfile integrity

~~~bash
uv lock --check
~~~

### Whitespace validation

~~~bash
git diff --check
~~~

---

## Testing and CI

Unit tests cover areas including:

- taxonomy;
- canonical identifiers;
- entities;
- issuer identity;
- parties;
- transaction participations;
- transaction lifecycle;
- source and evidence lineage;
- governed terms;
- market-data semantics;
- cross-record consistency;
- FX conversion;
- canonical dataset validation;
- persistence reader behavior;
- persistence writer behavior.

PostgreSQL integration tests cover:

- real Alembic migrations;
- PostgreSQL constraints;
- constraint triggers;
- deferred integrity enforcement;
- restrictive-delete behavior;
- observation-subject integrity;
- transactional canonical persistence;
- canonical reconstruction;
- market-series persistence;
- lossless round trips;
- downgrade and re-upgrade behavior.

CI provisions PostgreSQL independently and validates:

~~~text
Upgrade canonical schema
          ↓
PostgreSQL migration integration tests
          ↓
Downgrade canonical schema
          ↓
Re-upgrade canonical schema
          ↓
Verify schema after migration cycle
~~~

This keeps database correctness separate from local environment availability.

---

## Current Implementation

| Capability | Status |
| --- | --- |
| Canonical identifiers and taxonomy | Implemented |
| Issuer / transaction / instrument domain | Implemented |
| Party and participation model | Implemented |
| Lifecycle model | Implemented |
| Source / evidence / observation lineage | Implemented |
| Explicit missing-data semantics | Implemented |
| FX conversion controls | Implemented |
| Canonical dataset validation | Implemented |
| PostgreSQL canonical schema | Implemented |
| Transactional writer | Implemented |
| Repeatable-read reader | Implemented |
| Canonical query repository | Implemented |
| European market methodology | Implemented |
| Seven-family market domain | Implemented |
| Market-series PostgreSQL schema | Implemented |
| Market-series writer / reader adapters | Implemented |
| PostgreSQL lossless market round trip | Implemented |
| Controlled reference-series catalog | Implemented |
| Concrete provider mappings | In progress — ECB, Bundesbank, ICE Swap Rate, STOXX/VSTOXX mapped; credit benchmarks pending |
| Market-data ingestion | Deferred |
| Market analytics | Planned |
| Financing models | Planned |
| Client-facing outputs | Planned |

---

## Roadmap

The current controlled sequence is:

~~~text
Methodology
    ↓
Domain Contract
    ↓
Validation
    ↓
Persistence Design
    ↓
Database Migration
    ↓
Writer / Reader
    ↓
PostgreSQL Integration
    ↓
Reference-Series Catalog
    ↓
Reviewed Source / Provider Mappings
    ↓
Controlled Ingestion
    ↓
Market and Transaction Analytics
    ↓
Capital-Structure Analysis
    ↓
Execution Assessment
    ↓
Controlled Outputs
~~~

### Next Phase 1 increment

The controlled market reference-series catalog is implemented. The next Phase 1
work is to complete reviewed concrete mappings, most notably the remaining
European credit-spread benchmarks, before ingestion.

The catalog governs selection metadata such as:

- canonical market-series ID;
- series type;
- display label;
- type-specific identity dimensions;
- source/provider selection metadata;
- provider series identifier where applicable;
- expected publication frequency;
- active dates;
- methodology or convention references;
- notes.

The catalog structure is implemented. Concrete provider mappings are added
through source-specific reviewed increments before live ingestion.

### Initial European market coverage

The framework is designed to support:

**Monetary policy**

- relevant ECB policy-rate series.

**Sovereign rates**

- German sovereign benchmark curve;
- initial 2Y, 5Y, and 10Y coverage where available.

**Swap rates**

- EUR swap curve;
- initial 2Y, 5Y, and 10Y coverage where available.

**Credit**

- broad European investment-grade spread benchmark;
- broad European high-yield spread benchmark.

**Equity**

- STOXX Europe 600;
- selected major country indices;
- selected sector indices relevant to issuer analysis.

**Volatility**

- at least one defined European equity-volatility benchmark appropriate for
  the selected equity framework.

Concrete instruments and provider identifiers belong in controlled reference
data rather than executable domain taxonomy.

---

## Methodology

The repository contains explicit methodology and persistence contracts rather
than relying on implementation behavior as undocumented specification.

Key documents include:

- [European Market Framework](docs/methodology/european_market_framework.md)
- [Market-Series Methodology](docs/methodology/market_series.md)
- [Persistence Contract](docs/methodology/persistence_contract.md)
- [Data Governance](docs/data_governance.md)

The distinction is intentional:

~~~text
Domain code
defines economic semantics.

Reference data
selects concrete series.

Source / evidence records
prove what was actually observed.

Analytics
derive reproducible conclusions.

Judgment
interprets the analytical result.
~~~

These responsibilities should not be collapsed.

---

## Analytical Boundaries

### Canonical layer

Stores or governs:

- stable identities;
- economic definitions;
- transaction structure;
- sourced observations;
- evidence;
- provenance;
- explicit missingness.

### Analytical layer

Derives:

- changes;
- returns;
- curve movements;
- spread movements;
- precedent comparisons;
- financing scenarios;
- execution assessments;
- market commentary.

### Judgment layer

Includes:

- strategic interpretation;
- issuer implications;
- execution preference;
- recommendations;
- contingency planning.

Judgment must not be represented as though it were a sourced canonical fact.

---

## Intended Use

This repository is designed as professional capital-markets analytical
infrastructure and as an engineering foundation for reproducible financing
analysis.

It is not a substitute for:

- original transaction documentation;
- official issuer disclosures;
- regulated market-data services;
- legal review;
- accounting review;
- investment-banking judgment;
- investment advice.

Where real listed companies are used in future analytical simulations, their
inclusion does not imply an advisory, banking, commercial, or other
relationship with the project or its author.

---

## Project Standard

A feature is not considered complete merely because it produces an output.

The standard is that another qualified reviewer should be able to:

~~~text
Trace it
Validate it
Reproduce it
Update it
Audit it
~~~

without relying on undocumented assumptions.
