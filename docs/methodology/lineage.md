# Source, Evidence, and Observation Lineage

## Purpose

The platform does not treat a URL attached to a transaction row as sufficient
data lineage.

Material analytical values must be traceable through explicit records.

The core lineage path is:

Source
→ Evidence
→ Observation
→ Canonical Entity or Calculation
→ Analytical Output

Calculated values may additionally depend on prior observations.

## Permanent Identifiers

Canonical records use permanent, non-semantic identifiers.

Initial namespaces are:

- ISS000000001 — issuer;
- `PTY000000001` — party;
- `PAR000000001` — participation relationship;
- TXN000000001 — transaction;
- INS000000001 — instrument;
- OBS000000001 — observation;
- SRC000000001 — source;
- EVD000000001 — evidence;
- ASM000000001 — assumption;
- REL000000001 — release.

Each namespace supports up to 999,999,999 permanent identifiers.

The numeric component conveys identity only.

It must not encode:

- year;
- country;
- product;
- issuer;
- status;
- chronology outside the allocation sequence.

An identifier must not be changed merely because the entity's classification
or attributes change.

Identifier allocation itself will be implemented separately from identifier
validation so that persistent storage can enforce uniqueness safely.

## Source Record

A source record identifies a document, publication, dataset, or other evidence
container.

Minimum source metadata includes:

- permanent source ID;
- source tier;
- source type;
- publisher;
- title;
- access date;
- a URL or controlled archived location.

Where relevant, it may also contain:

- document date;
- publication date;
- document version;
- notes.

Source type and source tier are separate dimensions.

For example, a MARKET_DATA source describes what kind of source it is, while
its tier describes its default place in the evidence hierarchy.

A source record does not claim that every fact in the source has been verified.

## Evidence Record

An evidence record points to the precise location supporting an analytical
observation.

Examples of evidence locators include:

- page and table;
- document section;
- announcement heading;
- filing section;
- dataset series and observation key.

Evidence should point to source material rather than duplicate unnecessary
copyrighted text.

A source can support many evidence records.

## Observation Record

An observation represents either:

1. a governed analytical value; or
2. an explicit missing-data state.

The initial observable business subjects are:

- issuer;
- party;
- participation;
- transaction;
- instrument.

Sources, evidence records, observations, assumptions, and releases are governed
records but are not observation subjects. Additional subject types must be
introduced explicitly when new analytical domains require them.

An observation records:

- observation ID;
- subject entity and permanent ID;
- field name;
- analytical as-of date;
- verification state;
- verification timestamp when verified;
- value and value class, when populated;
- missing-data state, when not populated;
- unit and currency where relevant;
- supporting evidence;
- input observations for derived values;
- derivation or rationale reference where required.

## Value versus Missing State

A single observation cannot simultaneously contain a value and a missing-data
state.

A populated value requires a value class.

A missing-data observation does not receive a value class.

This prevents records such as zero, empty string, and NULL from being used
interchangeably to mean different things.

## Disclosed Values

A DISCLOSED observation requires evidence.

The evidence record then links the observation to a precise location in a
source.

This creates:

Source
→ Evidence
→ Disclosed Observation

rather than:

Transaction
→ generic URL

## Verification Semantics

PRIMARY_VERIFIED and SECONDARY_VERIFIED are source-verification states and may
be assigned only to DISCLOSED values.

CALCULATED, ESTIMATED, and ASSUMED values must not imply that the value itself
was directly verified against a primary or secondary source.

A calculated value may instead be CROSS_VERIFIED when its derivation has been
independently checked and its controlled inputs are appropriately governed.

Verified observations record a timezone-aware verification timestamp.

## Calculated Values

A CALCULATED observation requires:

- at least one input observation; and
- a derivation reference.

The derivation reference identifies the controlled methodology or calculation
definition.

The calculation lineage therefore becomes:

Input Observation(s)
→ Controlled Methodology
→ Calculated Observation

The platform rejects circular calculation dependencies.

## Estimated Values

An ESTIMATED value requires:

- evidence or input observations; and
- a derivation reference.

This prevents an analyst estimate from appearing without a documented basis.

## Assumed Values

An ASSUMED value requires a rationale reference.

An assumption does not become a market observation merely because it is used
in a model.

Dedicated assumption records and assumption registers will be implemented in a
later phase.

## Missing Information

NOT_DISCLOSED requires evidence identifying the material reviewed.

This distinguishes:

"We checked the relevant source and the information was not disclosed"

from:

"We have not researched this yet."

UNAVAILABLE must use the UNAVAILABLE verification state.

PENDING_VERIFICATION must use the PENDING verification state.

## Currency

Currency codes are stored separately from the value and use three-letter
upper-case codes.

Currency conversion does not overwrite the native observation.

Converted observations will be represented as separately traceable calculated
values.

## Bundle Validation

Lineage validation operates across records, not only within individual rows.

The validator checks:

- unique source IDs;
- unique evidence IDs;
- unique observation IDs;
- evidence-to-source references;
- observation-to-evidence references;
- calculated-input references;
- absence of calculation-lineage cycles.

Persistent storage will later add database-level uniqueness and referential
integrity controls.

## Design Boundary

These domain records define analytical semantics.

They are not yet database models.

Storage technology will be selected after the entity and lineage rules are
stable enough that persistence reflects the analytical model rather than
dictating it.
