# Transaction and Instrument Participation

## Purpose

Canonical parties become economically meaningful to a financing event through
explicit participation relationships.

A participation record answers:

- which canonical party participates;
- in which financing transaction;
- in what role;
- whether the role applies to the transaction generally or to one specific
  instrument;
- what evidence supports the relationship.

The relationship is represented as a first-class canonical record rather than
as a mutable list stored on a transaction or instrument.

## Participation Identifier

Participation relationships use permanent identifiers in the `PAR...`
namespace.

For example:

`PAR000000001`

A participation ID identifies the canonical relationship record.

It does not encode:

- product;
- issuer;
- role;
- date;
- instrument;
- geography.

## Relationship Structure

Every participation contains:

- permanent participation ID;
- canonical party ID;
- canonical transaction ID;
- controlled participant role;
- supporting evidence;
- optional canonical instrument ID;
- optional notes.

The structural model is:

Party
→ Participation
→ Transaction

or, for an instrument-specific relationship:

Party
→ Participation
→ Transaction
→ Instrument

An instrument-specific participation always retains its transaction ID.

This makes the transaction context explicit and permits validation that the
instrument actually belongs to that transaction.

## Transaction-Level versus Instrument-Level Roles

When `instrument_id` is absent, the participation applies at transaction level.

When `instrument_id` is populated, the participation is specific to that
instrument or tranche.

Examples:

- a sponsor may normally be represented at transaction level;
- a selling shareholder may normally be represented at transaction level;
- a legal issuer may be transaction-level in a simple issue;
- a legal issuer may be instrument-specific where different issuance entities
  issue different tranches;
- a guarantor may apply to one instrument but not another;
- a borrower may be instrument-specific in a multi-facility financing.

The generic relationship layer does not assume that a role must always occur at
only one of these levels.

Product-specific validation may later impose tighter rules.

## Scope Specificity

Transaction-level participation is not a synthetic roll-up of
instrument-level participation.

If a party is known only to perform a role for a specific instrument, the
relationship should be recorded at instrument level rather than duplicated at
transaction level for convenience.

Transaction-level and instrument-level records for the same party and role may
coexist only when the evidence supports two independently meaningful
relationships at those different scopes.

Derived analytical roll-ups should be produced by calculation or query logic,
not by creating duplicate canonical participation records.

## Participant Roles

The initial controlled participant roles are:

- `LEGAL_ISSUER`;
- `BORROWER`;
- `GUARANTOR`;
- `SPONSOR`;
- `SELLING_SHAREHOLDER`;
- `ACQUISITION_VEHICLE`.

These roles describe transaction function rather than party identity.

For example:

- a FUND may be a SPONSOR;
- a GOVERNMENT may be a SELLING_SHAREHOLDER;
- a SPECIAL_PURPOSE_VEHICLE may be a LEGAL_ISSUER;
- a CORPORATE may be a BORROWER or GUARANTOR.

## Cardinality

The role vocabulary deliberately avoids labels such as:

- co-issuer;
- co-borrower.

Multiple parties may hold the same controlled role in the same transaction or
instrument.

For example, two parties with role `BORROWER` represent co-borrowers without
requiring a separate role value.

Likewise, multiple `LEGAL_ISSUER` relationships represent co-issuers where
appropriate.

This avoids encoding relationship cardinality into the role taxonomy.

## Primary Analytical Issuer

`TransactionRecord.primary_issuer_id` remains separate from participation
roles.

The primary analytical issuer is the canonical company anchor used for
aggregation and analysis.

It does not automatically imply:

- legal issuer;
- borrower;
- guarantor;
- seller;
- sponsor.

Where the primary analytical issuer also performs one of those legal or
economic functions, the corresponding issuer-linked `PartyRecord` receives an
explicit participation relationship.

This prevents analytical hierarchy from being mistaken for legal transaction
structure.

## Evidence

Every participation relationship requires one or more evidence records.

Participation-bundle validation checks the complete:

Source
→ Evidence
→ Participation

reference chain.

Multiple sources supporting the same semantic relationship are consolidated by
adding their evidence IDs to one participation record.

Parallel duplicate participation records are rejected.

## Semantic Uniqueness

A participation relationship is semantically identified by:

- party ID;
- transaction ID;
- optional instrument ID;
- participant role.

Two records with the same semantic key are duplicates.

They must be consolidated rather than preserved as parallel rows.

Different roles for the same party are valid.

For example, one party may be both:

- `LEGAL_ISSUER`;
- `BORROWER`.

Transaction-level and instrument-level relationships are also distinct.

## Instrument Parent Integrity

For an instrument-specific participation:

- the instrument must exist;
- the transaction must exist;
- the instrument's canonical parent transaction must equal the participation's
  transaction ID.

A participation cannot attach an instrument from one transaction to another
transaction.

## Relationship-Level Observations

A participation relationship is itself an observable analytical subject.

This allows source-derived or calculated facts that belong specifically to the
party-to-transaction relationship to use the governed observation system.

Examples may include:

- shares sold by one selling shareholder in a transaction containing multiple
  sellers;
- proceeds attributable to a specific seller;
- a guarantee percentage or limited guarantee amount;
- other party-role-specific facts that do not belong cleanly to the party,
  transaction, or instrument in isolation.

Such facts should not be added as mutable fields to `ParticipationRecord`
merely because they concern the relationship.

They should be represented as governed observations using:

- `subject_type = PARTICIPATION`;
- the permanent `PAR...` participation ID as `subject_id`;
- the normal evidence, verification, value-class, as-of-date, and derivation
  controls.

This preserves the distinction between stable relationship identity and
source-derived relationship attributes.

## Time-Varying Roles

The initial canonical relationship does not add role-validity dates.

Most primary issuance participant roles are defined in the context of a
specific financing event.

If later use cases require participant-role history across amendments or
transaction stages, temporal semantics should be introduced explicitly rather
than inferred from source access or publication dates.

## Product-Specific Rules

The generic participation layer intentionally does not enforce assumptions such
as:

- only leveraged-finance transactions may have sponsors;
- only ECM transactions may have selling shareholders;
- every debt instrument must have exactly one legal issuer;
- every financing must have exactly one borrower.

Those rules vary by product structure and transaction circumstances.

They belong in later product-specific structural validators.

## Deliberately Awkward Validation Cases

The generic relationship model is expected to support, without changing its
identity semantics:

- a multi-tranche bond in which different instruments have different legal
  issuers;
- instrument-specific guarantors within the same financing event;
- an ECM secondary block in which the selling shareholder is not the primary
  analytical issuer;
- a sponsor-backed leveraged financing containing separate sponsor,
  acquisition-vehicle, borrower, and guarantor relationships;
- multiple parties holding the same role, such as co-borrowers;
- the same party and role appearing once at transaction level and separately at
  instrument level where both relationships are economically meaningful.

These cases are maintained as regression tests because they challenge the
difference between analytical hierarchy, legal structure, and transaction-role
cardinality.

## Persistence Boundary

`ParticipationRecord` defines canonical analytical relationship semantics.

It is not yet a database persistence model.

Persistence constraints should preserve the same semantic uniqueness rules when
the storage layer is introduced.
