# Canonical Persistence Contract

## Purpose

The persistence layer must preserve the analytical semantics already defined by
the domain model.

The database is not a second source of business meaning.

Its responsibilities are to provide:

- durable canonical storage;
- referential integrity;
- uniqueness enforcement;
- exact scalar-value round trips;
- source and evidence lineage;
- calculation lineage;
- historical reproducibility;
- deterministic reconstruction of domain records;
- controlled schema evolution.

This document defines the logical relational contract before any database
adapter, ORM, migration framework, or database-specific DDL is selected.

## Governing Principle

Persistence must reproduce the domain model rather than redefine it.

Where a domain rule cannot be represented safely by a portable declarative
database constraint, the first persistence implementation must:

1. retain the domain validator as the authoritative semantic control;
2. enforce all feasible database-level constraints;
3. document any remaining application-enforced invariant;
4. add database-native enforcement later only if it preserves the same
   semantics.

A database implementation must not silently strengthen or weaken a domain rule.

## Canonical IDs versus Storage Keys

Permanent platform IDs remain the canonical identity of records that already
possess them.

Examples include:

- `ISS...` — issuer;
- `PTY...` — party;
- `PAR...` — participation;
- `TXN...` — transaction;
- `TLE...` — transaction lifecycle event;
- `INS...` — instrument;
- `MKS...` — market series;
- `SRC...` — source;
- `EVD...` — evidence;
- `OBS...` — observation.

These IDs must not be replaced by database-generated surrogate identities in
the domain interface.

A storage-only surrogate key may be introduced where a domain record does not
possess its own canonical identifier and a relational child table needs a
stable parent key.

The initial example is an issuer-identifier assignment.

Such a surrogate:

- has no analytical meaning;
- is not exposed as a canonical platform ID;
- must not replace the semantic uniqueness rules of the record;
- exists only to support persistence mechanics.

## Logical Table Families

The initial canonical persistence boundary consists of the following logical
table families.

### Stable canonical entities

- `issuers`
- `parties`
- `transactions`
- `instruments`
- `participations`
- `market_series`

### Type-specific canonical definitions

- `fx_reference_rate_definitions`

### Historical transaction state

- `transaction_lifecycle_events`

### External identity

- `issuer_identifiers`

### Source lineage

- `sources`
- `evidence`

### Observation lineage

- `observation_subjects`
- `observations`
- `observation_evidence`
- `observation_inputs`

### Evidence-backed relationship junctions

- `issuer_identifier_evidence`
- `participation_evidence`
- `transaction_lifecycle_event_evidence`

The exact physical names may be adjusted during DDL implementation only if the
same logical separation is preserved.

## Issuers

`issuers` persists `IssuerRecord`.

Canonical key:

`issuer_id`

Persisted domain fields:

- issuer ID;
- canonical name.

The canonical issuer ID is permanent.

The canonical name is an operational identity label, not a substitute for
historical sourced names. Historical or source-specific names belong in
governed observations and evidence rather than silent identity-history
rewrites.

## Issuer Identifiers

`issuer_identifiers` persists `IssuerIdentifierRecord`.

The domain record currently has no dedicated platform identifier.

The persistence layer may therefore allocate a storage-only
`issuer_identifier_row_id`.

Persisted domain fields are:

- issuer ID;
- identifier type;
- identifier value;
- scope type;
- scope value;
- assignment valid from;
- assignment valid to;
- notes.

Evidence is stored through `issuer_identifier_evidence`.

Validity intervals remain half-open:

`[assignment_valid_from, assignment_valid_to)`

where either boundary may be open.

The persistence layer must preserve the existing identity-resolution rules,
including:

- LEI global uniqueness semantics;
- scope requirements;
- deterministic as-of-date resolution;
- rejection of overlapping assignments in the same identifier namespace where
  the domain validator rejects them.

A storage surrogate does not weaken these semantic constraints.

The storage-only surrogate is not a semantic identifier.

In particular, it must not be used as:

- an issuer-identifier deduplication key;
- a cross-database canonical identifier;
- an analytical identifier exposed to downstream users;
- a substitute for identifier namespace, assignment-validity, or evidence
  semantics.

Its purpose is to give persistence children such as
`issuer_identifier_evidence` a stable relational parent.

Collision detection, as-of resolution, and assignment validity continue to be
defined by the domain model rather than by surrogate-key equality.

## Parties

`parties` persists `PartyRecord`.

Canonical key:

`party_id`

Persisted domain fields are:

- party ID;
- party type;
- optional linked issuer ID;
- optional canonical name.

Database constraints should preserve the current XOR-style naming rule:

- issuer-linked party → `linked_issuer_id` populated and `canonical_name` NULL;
- non-issuer-linked party → `linked_issuer_id` NULL and `canonical_name`
  populated.

`linked_issuer_id`, where present, references `issuers`.

Within the current model, one canonical issuer may link to at most one canonical
party.

## Transactions

`transactions` persists `TransactionRecord`.

Canonical key:

`transaction_id`

Persisted domain fields are:

- transaction ID;
- primary analytical issuer ID;
- product family;
- optional transaction label.

`primary_issuer_id` references `issuers`.

The primary analytical issuer remains an analytical hierarchy anchor.

It must not be inferred to be:

- legal issuer;
- borrower;
- guarantor;
- sponsor;
- selling shareholder.

Those relationships remain explicit participation records.

## Instruments

`instruments` persists `InstrumentRecord`.

Canonical key:

`instrument_id`

Persisted domain fields are:

- instrument ID;
- parent transaction ID;
- optional instrument label.

`transaction_id` references `transactions`.

One instrument belongs to exactly one canonical transaction.

Time-varying economics such as currency, size, pricing, coupon, yield, spread,
margin, maturity, books, discount, and aftermarket measures remain
observations rather than mutable columns on `instruments`.

## Participations

`participations` persists `ParticipationRecord`.

Canonical key:

`participation_id`

Persisted domain fields are:

- participation ID;
- party ID;
- transaction ID;
- role;
- optional instrument ID;
- optional notes.

Evidence is stored through `participation_evidence`.

Foreign keys are:

- party ID → `parties`;
- transaction ID → `transactions`;
- instrument ID → `instruments`, when populated.

For instrument-scoped participations, the instrument's parent transaction must
equal the participation transaction.

The current semantic uniqueness key is:

`(party_id, transaction_id, instrument_id, role)`

SQL NULL semantics must not weaken that rule.

A physical implementation should therefore enforce transaction-scoped and
instrument-scoped uniqueness separately when necessary, for example:

- transaction scope:
  `(party_id, transaction_id, role)` where `instrument_id IS NULL`;
- instrument scope:
  `(party_id, transaction_id, instrument_id, role)` where
  `instrument_id IS NOT NULL`.

Multiple different roles for the same party remain valid.

## Transaction Lifecycle Events

`transaction_lifecycle_events` persists
`TransactionLifecycleEventRecord`.

Canonical key:

`event_id`

Persisted domain fields are:

- event ID;
- transaction ID;
- status;
- effective date;
- event order;
- notes.

Evidence is stored through `transaction_lifecycle_event_evidence`.

`transaction_id` references `transactions`.

The canonical database ordering constraint is:

`UNIQUE(transaction_id, effective_date, event_order)`

The database must not introduce a universal status-transition graph.

The database also must not impose a stronger universal uniqueness rule such as:

`UNIQUE(transaction_id, status, effective_date)`

unless the domain methodology is explicitly changed first.

Postponed, withdrawn, and cancelled executions remain historical records.

Current transaction status is derived from lifecycle history rather than stored
as a mutable field on `transactions`.

## Market Series

`market_series` persists `MarketSeriesRecord`.

Canonical key:

`market_series_id`

Persisted domain fields are:

- market-series ID;
- series type;
- optional series label.

A market series is an observable canonical subject.

## FX Reference-Rate Definitions

`fx_reference_rate_definitions` persists
`FXReferenceRateDefinitionRecord`.

Canonical key and foreign key:

`market_series_id`

This creates a one-to-one type-specific extension of `market_series`.

Persisted domain fields are:

- market-series ID;
- base currency;
- quote currency;
- convention reference.

The referenced market series must have type:

`FX_REFERENCE_RATE`

Semantic uniqueness of:

`(base_currency, quote_currency, convention_ref)`

must be preserved.

The reverse currency pair remains a different orientation.

## Sources

`sources` persists `SourceRecord`.

Canonical key:

`source_id`

Persisted fields are:

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

At least one of URL or archived location must be populated.

Source access, publication, document, effective, and analytical as-of dates are
different concepts and must remain separate.

## Evidence

`evidence` persists `EvidenceRecord`.

Canonical key:

`evidence_id`

Persisted fields are:

- evidence ID;
- source ID;
- locator;
- optional label;
- optional notes.

`source_id` references `sources`.

Evidence is the reusable source locator.

Business records reference evidence through explicit junction tables rather
than embedding source URLs directly into transaction or observation rows.

## Observable-Subject Registry

`ObservationRecord` uses the polymorphic pair:

`(subject_type, subject_id)`

A plain relational foreign key cannot safely point one column at six unrelated
tables.

The persistence layer therefore introduces an
`observation_subjects` registry.

Logical columns are:

- subject ID;
- subject type.

The composite pair is unique.

The current observable subject types are:

- ISSUER;
- PARTY;
- PARTICIPATION;
- TRANSACTION;
- INSTRUMENT;
- MARKET_SERIES.

Transaction lifecycle events are not currently observable subjects.

Sources, evidence records, and observations are also not business subjects.

Each observable canonical entity must have exactly one corresponding registry
entry with the matching entity type.

A registry row is valid only when exactly one matching concrete canonical
entity exists for that subject ID and subject type.

A registry row by itself is therefore not sufficient proof that a business
subject exists.

The physical persistence implementation must prevent orphan registry rows.

Because ordinary portable foreign keys cannot express a foreign key from one
registry row conditionally into six different concrete tables, the selected
database must provide a database-enforced mechanism such as a constraint
trigger or an equivalent integrity mechanism.

Application-only validation is not sufficient for this particular invariant,
because an orphan registry row would otherwise allow an observation to satisfy
its foreign key while referring to no real canonical business subject.

The registry is persistence infrastructure.

It is not a new analytical entity and is not independently authored.

Creation and deletion of an observable entity and its registry row must occur
atomically.

Registry rows must not be inserted, reassigned, or deleted independently of
their corresponding concrete canonical entity.

`observations(subject_id, subject_type)` references the registry pair.

The combined registry and concrete-subject integrity controls provide
database-level referential integrity without weakening the domain model into an
unchecked polymorphic identifier.

## Observations

`observations` persists `ObservationRecord`.

Canonical key:

`observation_id`

Persisted structural fields include:

- observation ID;
- subject type;
- subject ID;
- field name;
- as-of date;
- verification state;
- verified-at timestamp;
- value class;
- missing-data state;
- unit;
- currency;
- derivation reference;
- notes.

Evidence and calculation inputs use separate junction tables.

## Typed Observation Values

Canonical observation values must not be flattened into floating point or an
untyped generic string.

`ScalarValue` currently permits:

- string;
- integer;
- Decimal;
- boolean;
- date;
- datetime.

The physical schema must preserve those scalar types exactly enough to rebuild
the corresponding Python value.

The logical observation row therefore contains a scalar-type discriminator and
typed value slots equivalent to:

- text value;
- integer value;
- decimal value;
- boolean value;
- date value;
- datetime value.

For a populated observation:

- exactly one typed value slot is populated;
- `value_class` is populated;
- `missing_state` is NULL.

For a missing-data observation:

- all typed value slots are NULL;
- `value_class` is NULL;
- `missing_state` is populated.

No canonical monetary or rate calculation may pass through binary
floating-point storage.

`Decimal` values require exact decimal/numeric persistence.

The concrete datetime storage type must round-trip the governed Python datetime
semantics, including timezone awareness where required.

## Missingness versus Retraction

A persisted missing observation remains a first-class observation row.

It does not:

- delete an earlier populated observation;
- overwrite an earlier populated observation;
- invalidate an earlier populated observation;
- act as a tombstone.

Latest-known-value queries must select the latest applicable populated
observation when the analytical rule requires a known value.

An explicit future retraction or invalidation mechanism, if required, must be a
separate governed concept.

It must not be inferred from `MissingDataState`.

## Observation Evidence

`observation_evidence` implements:

Observation
→ Evidence

Logical key:

`(observation_id, evidence_id)`

The junction should also preserve evidence ordinal where lossless reconstruction
of the domain tuple is required.

Both columns are foreign keys.

## Observation Calculation Inputs

`observation_inputs` implements directed calculation lineage:

Derived Observation
→ Input Observation

Logical fields are:

- derived observation ID;
- input observation ID;
- input ordinal.

The pair:

`(derived_observation_id, input_observation_id)`

must be unique.

`input_ordinal` must be unique within one derived observation so that the input
tuple can be reconstructed deterministically.

Self-reference is prohibited.

Future-dated inputs remain prohibited:

`input.as_of_date <= derived.as_of_date`

The calculation graph must remain acyclic.

Graph acyclicity is an example of an invariant that may remain enforced by the
domain validator in the first persistence implementation if the selected
database cannot express it safely as a declarative constraint.

## Evidence Junction Ordering

Current domain records represent evidence IDs as tuples.

Where exact record reconstruction is a persistence requirement, evidence
junction tables should include an ordinal.

This applies initially to:

- issuer identifier evidence;
- participation evidence;
- transaction lifecycle event evidence;
- observation evidence.

The ordinal is structural persistence metadata.

It does not imply evidentiary priority unless a future methodology explicitly
defines such meaning.

## Verification Timestamps

`verified_at` must preserve timezone-aware timestamps.

Verified observations require a verification timestamp under the existing
domain rules.

Unverified observations must not acquire a synthetic verification timestamp
during persistence.

Database defaults must therefore not auto-populate `verified_at`.

## Controlled Taxonomy Values

Controlled Python enums should initially persist using their canonical string
values.

The database may use CHECK constraints derived from the governed taxonomy.

Database-vendor enum types should not be introduced merely for convenience if
they make controlled taxonomy migrations unnecessarily destructive.

The Python taxonomy remains the semantic source of truth.

## Currency and Units

Currency codes persist as canonical three-letter uppercase codes.

The persistence layer must not infer currency from display formatting.

Native monetary observations retain native currency.

Converted observations retain their explicit analytical target currency.

Units remain explicit governed metadata where the field definition permits or
requires them.

## Persistence Enforcement Boundary

Not every domain invariant has the same relational shape.

The persistence implementation must make the enforcement boundary explicit
rather than silently relying on whichever layer happens to reject invalid
data.

### Database-enforced structural invariants

The database must directly enforce, where applicable:

- canonical primary-key uniqueness;
- ordinary foreign-key integrity;
- restrictive referential actions;
- required versus nullable columns;
- controlled scalar-shape constraints;
- party linked-issuer versus canonical-name exclusivity;
- one canonical party per linked issuer under the current model;
- source URL or archived-location presence;
- evidence-junction uniqueness;
- evidence ordinal uniqueness within its parent;
- observation-input pair uniqueness;
- observation-input ordinal uniqueness within one derived observation;
- prohibition of direct observation self-reference;
- lifecycle ordering-slot uniqueness;
- market-series to FX-definition one-to-one identity;
- FX-definition semantic uniqueness;
- observation populated-value versus missing-state structural exclusivity;
- exact typed-value-slot exclusivity;
- observation-subject registry integrity, including prevention of orphan
  registry rows.

These controls protect relational structure even if data reaches the database
through a path other than the primary Python adapter.

### Database-enforced cross-row or cross-table invariants

Some invariants may require backend-specific facilities such as:

- partial unique indexes;
- exclusion constraints;
- deferred constraints;
- constraint triggers;
- ordinary triggers.

Examples include:

- issuer-identifier interval overlap rules;
- global LEI assignment constraints;
- instrument-scoped participation transaction-parent consistency;
- observation-subject concrete-entity existence;
- observation input as-of dates not later than the derived observation.

Where the selected relational backend can enforce these semantics safely, the
database implementation should do so.

The mechanism must preserve the existing domain meaning rather than introduce a
stronger or weaker approximation.

### Domain-validator invariants

Some analytical invariants are intentionally richer than ordinary relational
constraints.

The domain validator remains authoritative for semantics such as:

- field-definition compatibility;
- observation value-class rules;
- evidence requirements associated with analytical value classes;
- currency-binding semantics;
- deterministic FX conversion arithmetic;
- currency-normalized transaction aggregation;
- calculation-lineage graph acyclicity where the selected database does not
  provide a safe equivalent;
- product-specific structural rules;
- analytical conflict interpretation.

Every supported canonical write path must execute the applicable domain
validation before committing its transaction.

Database enforcement supplements those validators.

It does not replace them.

### No false claim of database enforcement

Documentation and tests must distinguish:

- invariants physically enforced by the database;
- invariants enforced by the persistence adapter;
- invariants enforced by domain validation.

An invariant must not be described as database-enforced merely because normal
application code happens to validate it before insertion.

## Referential Actions

Canonical persistence must default to restrictive referential actions.

A parent canonical record with historical dependants must not disappear through
an accidental cascading delete.

In particular, deleting an issuer, transaction, instrument, source, evidence
record, market series, or observation must not silently erase analytical
history.

Physical foreign keys should therefore prefer restrictive delete behavior.

Administrative purge tooling, if ever introduced, is outside normal analytical
workflows and must be explicitly governed.

## Insert and Update Semantics

Evidence-backed historical records should be treated as append-oriented.

Examples include:

- observations;
- lifecycle events;
- source records;
- evidence records.

Corrections should normally produce new governed records or explicit corrected
relationships rather than destructive history rewrites.

Stable canonical IDs must never be reassigned to a different business entity.

This contract does not yet invent generic row-versioning for identity labels
where the domain model has not defined such semantics.

## Transaction Boundaries

Writes that create a logical canonical unit must be atomic.

Examples include:

- observable entity + observation-subject registry entry;
- observation + evidence junctions;
- calculated observation + input lineage;
- participation + evidence junctions;
- lifecycle event + evidence junctions;
- issuer identifier + evidence junctions.

A failed child write must not leave a partially persisted canonical record.

## Reconstruction Requirement

The persistence adapter must be able to reconstruct the supported frozen domain
records without loss of governed information.

Round-trip testing will therefore be required for:

- issuers;
- issuer identifiers;
- parties;
- transactions;
- instruments;
- participations;
- lifecycle events;
- market series;
- FX reference-rate definitions;
- sources;
- evidence;
- observations.

Persistence-only surrogate keys and junction ordinals must disappear from the
reconstructed domain object unless the domain model itself later adopts them.

## Query Views versus Canonical Storage

Convenience views may expose:

- current transaction status;
- latest known populated instrument currency;
- transaction-level size summaries;
- source coverage;
- current identifier resolution.

Such views are derived access paths.

They must not replace the underlying historical rows from which the values are
derived.

A convenient current-state query is not permission to denormalize away history.

## Product-Specific Analytics

ECM, IG DCM, leveraged-finance, and equity-linked analytical views may consume
the same canonical tables.

Product-specific convenience columns must not be added to the core transaction
table merely to simplify one analytical workbook or dashboard.

Product-specific semantics should remain in:

- governed observations;
- product-specific validators;
- analytical views;
- downstream models.

## Assumptions and Releases

The taxonomy already reserves canonical concepts for assumptions and releases,
but dedicated frozen domain record models have not yet been established for
them.

The first persistence schema must not invent database-only business semantics
for those concepts.

Their tables should be introduced only after their domain contracts are frozen.

## Migration Contract

Schema changes must be versioned.

A migration must not silently alter the meaning of previously persisted
canonical data.

Migration review must consider:

- domain-record round-trip compatibility;
- identifier stability;
- lineage preservation;
- historical as-of reproducibility;
- taxonomy compatibility;
- Decimal precision;
- temporal semantics;
- missing-data semantics;
- released-output reproducibility.

Where a migration changes interpretation rather than physical representation,
the methodology change must be explicit and reviewed before the migration is
accepted.

## Database and ORM Selection

This contract intentionally precedes database-driver and ORM selection.

The next implementation step should choose the relational backend and migration
mechanism based on the ability to satisfy this contract.

An ORM is optional.

If introduced, it is an adapter over the canonical relational model.

It must not become the place where business semantics are hidden or silently
redefined.

## Initial Persistence Completion Criteria

The initial canonical persistence layer is complete only when:

1. the normalized schema is migration-controlled;
2. canonical foreign keys are enforced;
3. observations cannot reference nonexistent concrete canonical subjects and
   the observation-subject registry cannot contain orphan subject rows;
4. evidence relationships are durable;
5. calculation input lineage is durable;
6. Decimal values round-trip exactly;
7. explicit missing states round-trip without tombstone behavior;
8. lifecycle history reproduces as-of status derivation;
9. identifier assignments reproduce deterministic as-of resolution;
10. domain records survive persist/load round trips unchanged;
11. the full domain validation suite remains green after persistence is added;
12. integration tests exercise the real selected database backend.
