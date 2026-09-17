# Canonical Party Model

## Purpose

Capital-markets transactions involve entities beyond the primary analytical
issuer.

Examples include:

- legal issuers;
- borrowers;
- co-borrowers;
- guarantors;
- acquisition vehicles;
- sponsors;
- selling shareholders;
- governments;
- funds;
- financial institutions;
- individuals.

These entities must not be forced into `IssuerRecord` merely because they
participate in a transaction.

The platform therefore maintains a separate canonical party namespace.

## Party Identifier

Canonical parties use permanent identifiers in the `PTY...` namespace.

For example:

`PTY000000001`

The identifier is non-semantic and follows the same permanent-ID principles as
the other canonical entity namespaces.

## Party Types

The initial controlled party types are:

- CORPORATE;
- FINANCIAL_INSTITUTION;
- FUND;
- GOVERNMENT;
- INDIVIDUAL;
- SPECIAL_PURPOSE_VEHICLE;
- OTHER.

Party type describes the broad nature of the participant.

It does not describe the participant's role in a particular transaction.

For example, a FUND may act as a sponsor or selling shareholder.

Those transaction-specific roles will be modeled separately.

## Relationship to IssuerRecord

Some parties correspond directly to a canonical issuer already represented by
`IssuerRecord`.

For these parties, `linked_issuer_id` creates an explicit bridge to the existing
issuer identity.

An issuer-linked party does not store its own canonical name.

Its display name is derived from the linked `IssuerRecord`.

This prevents two independent canonical-name fields from drifting apart.

## Non-Issuer Parties

A party that does not correspond to an existing issuer carries its own
`canonical_name`.

Examples may include:

- a private-equity sponsor;
- a government selling shareholder;
- an acquisition vehicle;
- an individual founder;
- a fund that is not represented in the issuer registry.

A non-issuer party must have a non-blank canonical name.

## One-to-One Issuer Bridge

Within the current model, a canonical issuer may be linked to at most one
canonical party.

This prevents parallel party records from being created for the same existing
issuer identity.

If future requirements show that one issuer record legitimately requires
multiple legal-party identities, that should be introduced as an explicit
methodology change rather than through uncontrolled duplicate records.

## Identity versus Transaction Role

Party identity and transaction role are separate concepts.

`PartyRecord` answers:

- who is this participant;
- what broad type of party is it;
- whether it corresponds to an existing canonical issuer.

A later participant-relationship record will answer:

- in which transaction or instrument does the party participate;
- what role does it perform;
- during what period or transaction stage, where relevant.

This separation allows the same party to perform different roles across
different transactions.

## Naming

For issuer-linked parties, naming remains governed by `IssuerRecord`.

For other parties, `PartyRecord.canonical_name` is an operational display
label.

Where a sourced historical or legal name matters analytically, it should be
represented through governed evidence and observations rather than by mutating
identity history silently.

## Persistence Boundary

`PartyRecord` defines analytical identity semantics.

It is not yet a persistence model.

Database constraints and party-identifier allocation will be implemented after
participant-role semantics are stable.
