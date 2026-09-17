# Issuer Identity Resolution

## Purpose

External identifiers are used to resolve source records to canonical internal
issuer IDs.

The platform does not use external identifiers as primary internal keys.

Canonical issuer identity remains the permanent `ISS...` identifier.

## Identifier Record

An issuer identifier record contains:

- canonical issuer ID;
- external identifier type;
- external identifier value;
- identifier scope type;
- optional scope value;
- validity interval;
- supporting evidence.

Every persisted identifier assertion requires source evidence.

## Identifier Types

The initial controlled identifier types are:

- LEI;
- ticker;
- company registration number;
- vendor identifier;
- other.

These identifiers do not have the same uniqueness semantics.

## Scope

Identifier scope is explicit.

### LEI

An LEI uses GLOBAL scope.

No additional scope value is permitted.

The implementation validates the LEI code structure and check digits:

- characters 1-18 must be upper-case alphanumeric characters;
- characters 19-20 must be numeric check digits;
- the check digits must validate successfully.

Authoritative registry existence, registration status, and reference-data
validation remain separate ingestion concerns.

### Ticker

A ticker uses TRADING_VENUE scope.

A ticker without its trading venue is not treated as a complete issuer
identifier.

For example, two issuers may use the same ticker symbol on different venues.

Ticker values are stored in canonical upper case.

### Company Registration Number

A company registration number uses REGISTRY scope.

The scope value identifies the relevant registry or registration namespace.

A registration number without its registry namespace is not assumed globally
unique.

### Vendor Identifier

A vendor identifier uses VENDOR scope.

The scope value identifies the vendor namespace.

Vendor identifiers must not be treated as interchangeable with public legal
identifiers.

### Other

An OTHER identifier requires an explicit OTHER scope value.

This prevents uncategorized identifiers from silently entering a global
namespace.

## Assignment Validity Intervals

Identifier records may have:

- `assignment_valid_from`;
- `assignment_valid_to`.

These fields describe the period during which the external identifier was
assigned to the canonical issuer.

They do not represent:

- source publication date;
- source document date;
- source access date;
- the date on which an analyst first observed the identifier.

Those source dates remain governed separately by `SourceRecord`.

The assignment-validity model uses a half-open interval:

`[assignment_valid_from, assignment_valid_to)`

`assignment_valid_from` is inclusive.

`assignment_valid_to` is exclusive.

Either boundary may be open when the assignment boundary is unknown or remains
current.

This permits historical identifier changes without creating artificial
one-day overlaps.

## Collision Rules

The canonical crosswalk must remain deterministic.

### LEI

The same LEI must not resolve to multiple canonical issuer IDs.

Historical validity periods do not make LEI reuse across different canonical
issuers acceptable.

### Canonical Mapping Records

An `IssuerIdentifierRecord` represents a canonical issuer-to-identifier mapping,
not one row per source document.

When multiple sources support the same mapping, their evidence IDs are
consolidated onto the same mapping record.

Overlapping duplicate mappings for the same issuer are rejected rather than
retained as parallel assertions.

### Scoped Identifiers

For tickers, registration numbers, vendor identifiers, and other scoped
identifiers, the same complete identifier key may be reused over time.

The complete key includes:

- identifier type;
- identifier value;
- scope type;
- scope value.

However, assignment-validity intervals for the same complete key must not
overlap.

Therefore a ticker may be reassigned after a prior assignment expires, while
resolution at a specific as-of date remains deterministic.

## Resolution

Resolution requires:

- identifier type;
- identifier value;
- scope type;
- scope value where required;
- as-of date.

Resolution requests are validated against the same identifier-type and scope
rules used for persisted identifier records.

Malformed requests are rejected rather than being reported as an ordinary
"not found" result.

The resolver returns:

- one canonical issuer ID when exactly one mapping is active;
- no issuer when no mapping is active;
- an error when unvalidated identifier data produces an ambiguous result.

## Relationship to Legal Identity

An external identifier maps to a canonical issuer record.

This mapping does not determine the transaction participant role of that
issuer.

A transaction may have a primary analytical issuer while separate participant
relationships identify:

- legal issuers;
- borrowers;
- guarantors;
- acquisition vehicles;
- selling shareholders;
- other parties.

Identity resolution and transaction-role modeling are therefore separate
concerns.

## Evidence

Every identifier assertion requires one or more evidence records.

Examples include:

- official LEI records;
- issuer filings;
- exchange records;
- official company registries;
- controlled vendor documentation.

Evidence references use the existing `EVD...` namespace.

Identity-bundle validation also validates the supplied source/evidence lineage,
so an identifier cannot rely on an evidence record whose source is absent from
the controlled source registry.

## Persistence Boundary

These records define analytical identity semantics.

They are not yet database persistence models.

A later storage layer may add surrogate persistence keys without changing the
canonical issuer IDs or the semantic identifier key.
