# Capital Markets Taxonomy

## Purpose

This document defines the controlled classification vocabulary used by the
European Capital Markets Issuance & Execution Intelligence Platform.

The taxonomy exists to prevent economically different transactions from being
grouped together merely because market sources use overlapping terminology.

## Classification Principles

1. Classify the economic substance of the financing.
2. Preserve transaction structure separately from financing purpose.
3. Preserve transaction-level concepts separately from instrument-level terms.
4. Do not infer undisclosed characteristics solely to complete a taxonomy.
5. Use OTHER only when the transaction genuinely falls outside the controlled
   categories.
6. Do not use OTHER as a substitute for incomplete research.
7. A classification may be revised when better evidence becomes available,
   but the change must remain auditable.

## Entity Hierarchy

The initial conceptual hierarchy is:

Issuer
→ Transaction
→ Instrument
→ Observation
→ Evidence

Sources support evidence.

Evidence supports observations.

Observations populate or support canonical entities and calculations.

Assumptions and releases are separately governed entities.

## Product Families

### ECM

Equity Capital Markets transactions involving issuance or distribution of
listed or listing-related equity securities.

Examples include:

- IPOs;
- follow-ons;
- rights issues;
- accelerated bookbuilds;
- block trades.

ECM structure, capital type, execution method, and seller type are separate
dimensions.

A secondary block trade, for example, must not be represented as primary
capital simply because it is an ECM transaction.

### IG_DCM

Investment-grade debt capital markets issuance.

Transaction-level information must remain separable from tranche-level
economics because one financing event may contain multiple instruments.

Coupon, yield, spread, margin, benchmark, and new-issue premium are distinct
economic concepts and must not be treated interchangeably.

### LEVERAGED_FINANCE

Financing associated with leveraged corporate or sponsor-backed capital
structures.

The instrument type must remain separate from financing purpose.

For example, TERM_LOAN_B describes an instrument while ACQUISITION describes
a purpose.

### EQUITY_LINKED

Equity-linked financing is maintained as a separate top-level product family
because its economics combine characteristics of equity and debt.

Detailed equity-linked sub-taxonomy is intentionally deferred until that
product is implemented.

## Transaction Status

Transaction lifecycle status must preserve unsuccessful or interrupted
transactions.

Controlled states include:

- ANNOUNCED;
- MARKETING;
- LAUNCHED;
- PRICED;
- ALLOCATED;
- SETTLED;
- POSTPONED;
- WITHDRAWN;
- CANCELLED.

Withdrawn and postponed transactions are analytically valuable and must not be
removed merely because they did not settle.

## Value Class versus Verification

Value origin and verification are independent.

A value may be DISCLOSED while still PENDING verification.

A CALCULATED value may rely entirely on PRIMARY_VERIFIED inputs.

The platform therefore records these dimensions separately.

## Missing Information

Missing-data semantics are distinct from numeric values.

Zero must never be used to mean:

- not disclosed;
- unavailable;
- not applicable;
- pending verification.

Storage NULL is not a controlled analytical missing-data state.

## Source Tier

Source tiers establish a default evidence preference:

1. primary transaction or issuer source;
2. official institution;
3. established market-data source;
4. high-quality secondary source;
5. analyst-derived information.

Tier ranking does not eliminate the need to investigate conflicting evidence.

## ECM Dimensions

ECM uses separate controlled dimensions for:

- structure;
- capital type;
- execution method;
- seller type.

This prevents examples such as accelerated execution, secondary ownership,
and primary issuance from being collapsed into a single ambiguous deal-type
field.

## Investment-Grade Debt Dimensions

IG DCM uses separate dimensions for:

- ranking;
- rate type;
- distribution format;
- financing purpose.

Instrument economics will be modeled at the tranche level.

## Leveraged-Finance Dimensions

Leveraged finance uses separate dimensions for:

- instrument;
- financing purpose;
- ownership type;
- security type.

Leverage measures will later record their own numerator, denominator,
measurement type, as-of date, and value provenance rather than being stored as
an unexplained single leverage field.

## Change Control

Taxonomy values should be stable once production data uses them.

Adding, renaming, merging, or retiring a controlled value is a methodology
change and must consider:

- historical data compatibility;
- migrations;
- analytical comparability;
- released outputs;
- downstream models and dashboards.

Display labels may evolve without changing the stable machine-readable value
where appropriate.
