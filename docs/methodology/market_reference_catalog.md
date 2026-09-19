# Market Reference Catalog

## Purpose

The market reference catalog is the controlled selection layer for concrete
external market-series instances.

The canonical domain defines what each `MarketSeriesType` means.

The reference catalog selects which concrete series the platform intends to
use.

Those responsibilities remain separate.

The initial catalog file is:

`data/reference/market_series_catalog.json`

The catalog is intentionally empty when the structure is first introduced.
Actual source/provider mappings and ingestion are a later controlled increment.

## Format

The catalog uses UTF-8 JSON and has exactly two top-level fields:

- `catalog_version`;
- `series`.

The initial supported catalog version is `1`.

`series` is an ordered list of controlled market-series entries.

Unknown fields are rejected rather than silently ignored.

## Series Entry

Each entry contains exactly:

- `market_series_id`;
- `series_type`;
- `display_label`;
- `identity`;
- `source_mapping`;
- `expected_publication_frequency`;
- `active_from`;
- `active_to`;
- `notes`.

The canonical market-series ID must satisfy the normal canonical identifier
contract.

`series_type` must be one of the executable `MarketSeriesType` values.

`display_label` maps to the canonical `MarketSeriesRecord.series_label`.

## Type-Specific Identity

`identity` contains the frozen economic identity dimensions for the selected
series type.

### FX reference rate

- `base_currency`;
- `quote_currency`;
- `convention_ref`.

### Policy rate

- `authority`;
- `jurisdiction`;
- `currency`;
- `rate_name`;
- `convention_ref`.

### Government yield

- `sovereign`;
- `jurisdiction`;
- `currency`;
- `tenor_months`;
- `benchmark_ref`;
- `convention_ref`.

### Swap rate

- `currency`;
- `tenor_months`;
- `floating_rate_ref`;
- `fixed_leg_convention_ref`;
- `convention_ref`.

### Credit spread

- `benchmark_family`;
- `currency`;
- `credit_universe`;
- `rating_segment`;
- `sector_segment`;
- `spread_measure`;
- `convention_ref`.

`rating_segment` and `sector_segment` may be `null`.

### Equity index

- `index_name`;
- `universe`;
- `index_variant_ref`;
- `methodology_ref`.

### Volatility index

- `index_name`;
- `underlying_ref`;
- `horizon_days`;
- `methodology_ref`.

`horizon_days` may be `null`.

The loader constructs the existing frozen domain definition record for the
selected type. The catalog therefore does not introduce a parallel economic
identity model.

## Source Mapping

Each populated series entry contains one `source_mapping` object with exactly:

- `publisher`;
- `source_tier`;
- `source_type`;
- `provider_series_id`.

`source_tier` uses the existing `SourceTier` enum name.

`source_type` uses the existing `SourceType` enum name.

`provider_series_id` may be `null` where the source does not expose a stable
provider identifier.

The source mapping is reference-level selection metadata only.

It is **not** observation evidence.

A canonical market observation must still carry normal `SourceRecord` and
`EvidenceRecord` lineage identifying the actual accessed publication,
document, dataset, endpoint response, or archived material supporting that
observation.

The catalog must never be used as a substitute for observation provenance.

## Publication Frequency

`expected_publication_frequency` uses one of:

- `BUSINESS_DAILY`;
- `DAILY`;
- `WEEKLY`;
- `MONTHLY`;
- `QUARTERLY`;
- `EVENT_DRIVEN`;
- `IRREGULAR`.

This field describes the expected availability/update cadence of the selected
series. It is not an ingestion schedule.

## Activity Dates

`active_from` and `active_to` use ISO `YYYY-MM-DD` dates or `null`.

When both are populated, `active_to` must not precede `active_from`.

These fields describe the applicability of the reference selection. They do
not replace observation dates, publication dates, source access dates, or
ingestion timestamps.

## Validation

The catalog loader must reject:

- unsupported catalog versions;
- unknown or missing structural fields;
- duplicate JSON object keys;
- invalid enum names;
- malformed canonical IDs;
- duplicate canonical market-series IDs;
- identity dimensions incompatible with the selected series type;
- invalid type-specific domain records;
- duplicate semantic series identities;
- blank required strings;
- malformed dates;
- `active_to` before `active_from`.

After parsing, the loader passes the complete selected series bundle through
the existing canonical market-series domain validator.

Reference validation therefore reuses the frozen domain semantics instead of
reimplementing them.

## Boundary With Ingestion

This catalog structure does not:

- select live market providers yet;
- freeze provider API schemas;
- populate provider identifiers;
- fetch market values;
- create canonical observations;
- create `SourceRecord` or `EvidenceRecord` objects;
- schedule recurring ingestion;
- calculate market changes;
- generate market commentary.

Those capabilities follow only after concrete reference mappings are reviewed
and added.

## Change Control

Adding or changing a catalog entry can change the economic series selected by
the platform and must therefore be reviewable in Git.

A changed economic definition must not silently reuse an existing canonical
market-series identity.

Provider changes that preserve the same economic definition must still retain
observation-level source/evidence lineage so historical provenance remains
reproducible.
