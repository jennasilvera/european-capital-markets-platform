# Data Governance

## Purpose

This document defines the minimum governance standard for data used by the
European Capital Markets Issuance & Execution Intelligence Platform.

The objective is to ensure that material analytical conclusions can be traced,
verified, reproduced, challenged, and updated without ambiguity over where a
number came from or how it was derived.

## Governing Principles

The platform must:

1. preserve source provenance;
2. distinguish observed facts from analyst-derived values;
3. preserve original values before transformation;
4. identify the relevant observation and verification dates;
5. make missing or unavailable information explicit;
6. surface conflicting evidence rather than silently resolve it;
7. prevent unverified data from appearing as verified fact;
8. preserve historical releases and corrections;
9. respect source licensing and redistribution restrictions;
10. make material analytical transformations reproducible.

## Value Classes

Every material analytical value must be assigned an appropriate value class.

### DISCLOSED

A value explicitly reported by an external source.

Examples:

- transaction size stated in an issuer announcement;
- coupon stated in an offering document;
- reported net debt in financial statements;
- offer price stated in a prospectus.

A disclosed value must not be reclassified as calculated merely because it was
transcribed or normalized.

### CALCULATED

A value derived mechanically from disclosed, verified, or otherwise controlled
inputs using a reproducible methodology.

Examples:

- transaction coverage ratio;
- post-issue leverage;
- equity-offering discount;
- relative share-price performance;
- calculated new-issue premium.

The methodology and material inputs must be identifiable.

### ESTIMATED

A value inferred from incomplete observable information.

An estimated value must not be presented as a disclosed fact.

The basis for the estimate must be documented.

### ASSUMED

A value deliberately selected for analytical or scenario purposes.

Examples:

- assumed financing spread;
- assumed issue discount;
- assumed transaction size;
- forecast operating assumptions.

Assumptions must remain distinguishable from observed market information.

## Verification States

Value class and verification state are separate concepts.

A disclosed value can still be unverified.

The platform will use controlled verification states including:

### PRIMARY_VERIFIED

Verified directly against an authoritative primary source.

### SECONDARY_VERIFIED

Verified against a credible secondary source where primary evidence is not
available or is not reasonably accessible.

### CROSS_VERIFIED

Supported by multiple independent sources or reconciled across relevant
evidence.

### PENDING

Evidence exists or is expected, but verification is incomplete.

### CONFLICT

Relevant sources disagree materially and the conflict has not yet been
resolved.

### UNAVAILABLE

The required information could not be obtained from the available evidence.

## Source Hierarchy

Source tier does not determine truth automatically. It establishes the default
preference for verification and reconciliation.

### Tier 1 — Primary Transaction and Issuer Sources

Examples include:

- prospectuses;
- offering memoranda where legally accessible;
- issuer announcements;
- exchange announcements;
- regulatory filings;
- financial statements;
- investor presentations;
- official transaction documentation.

### Tier 2 — Official Institutions

Examples include:

- central banks;
- regulators;
- statistical agencies;
- ministries;
- public authorities;
- official exchange data.

### Tier 3 — Established Market-Data Sources

Examples include recognized providers of:

- equity prices;
- rates;
- credit indices;
- volatility measures;
- bond pricing;
- benchmark curves;
- primary-market statistics.

Use of these sources remains subject to licensing and redistribution
restrictions.

### Tier 4 — High-Quality Secondary Sources

Examples include reputable financial reporting and established market
commentary.

Secondary evidence may supplement primary evidence but must not silently
override conflicting primary information.

### Tier 5 — Analyst-Derived Information

Includes:

- calculations;
- model outputs;
- documented estimates;
- scenario assumptions;
- analytical judgments.

Analyst-derived information must identify the relevant methodology or
assumption where material.

## Evidence Standard

A source reference should identify enough information for another analyst to
locate the supporting evidence.

Depending on the source, this may include:

- source identifier;
- publisher or issuer;
- document title;
- publication date;
- document version;
- page;
- section;
- table;
- paragraph or announcement heading;
- source URL;
- access date.

The platform should store a precise evidence locator rather than unnecessary
copies of copyrighted source text.

## Missing Data

Numeric zero is a valid value and must never be used as a generic missing-data
marker.

The data model must distinguish between concepts including:

### NOT_DISCLOSED

The relevant information was not disclosed in the available source material.

### UNAVAILABLE

The information could not be obtained.

### NOT_APPLICABLE

The field does not apply to the relevant instrument, transaction, or entity.

### PENDING_VERIFICATION

The field may be populated after verification is completed.

### Storage NULL

NULL is a persistence representation, not a semantic analytical missing-data
state.

### Missingness versus supersession

A missing-data observation describes information availability at a particular
analytical point.

It does not automatically supersede, retract, or invalidate an earlier
populated observation for the same subject and field.

Accordingly:

- `NOT_DISCLOSED` means the reviewed source did not disclose the value;
- `UNAVAILABLE` means the value could not be obtained;
- `PENDING_VERIFICATION` means verification is incomplete;
- `NOT_APPLICABLE` means the missing-state assertion itself is analytically
  relevant for that observation.

None of these states is a general-purpose tombstone.

Where a business fact genuinely changes, a later populated observation may
establish the new value.

Where an earlier populated observation must be explicitly retracted or
invalidated, the platform should introduce a dedicated governed
supersession/retraction mechanism rather than infer that meaning from
missingness.


Optional storage fields may be NULL where appropriate, but an analytical
observation representing missing information must use the applicable explicit
missing-data state.

## Conflicting Evidence

Conflicting information must not be silently overwritten.

Where material sources conflict:

1. retain the competing observations;
2. identify their respective sources;
3. assign an appropriate conflict state;
4. investigate the cause;
5. document the resolution;
6. preserve the audit trail.

## Dates

The system must distinguish different date concepts.

These include, where relevant:

- transaction announcement date;
- launch date;
- pricing date;
- allocation date;
- settlement date;
- observation date;
- source publication date;
- source access date;
- verification date;
- analytical as-of date;
- release date.

Dates must not be substituted for one another merely because only one is
available.

## Currency and Units

Original transaction and source values must be preserved in their native
currency and units where relevant.

Converted values must identify:

- target currency;
- conversion date;
- FX source;
- FX rate;
- calculation method.

Currency conversion must not overwrite the original observed value.

Units must be explicit where ambiguity could affect interpretation.

## Restatements and Corrections

A later source may restate or correct previously reported information.

The system should preserve:

1. the prior observation;
2. the corrected or restated observation;
3. the effective or publication date of the correction;
4. the evidence supporting the change.

Historical analytical releases must not be silently rewritten because a later
restatement becomes available.

## Publication and Licensing

Information being publicly accessible does not automatically mean that it may
be redistributed.

Do not commit externally sourced datasets merely because they are available to
the analyst locally.

Before publication, consider:

- copyright;
- database rights;
- contractual restrictions;
- market-data licensing;
- redistribution permissions;
- privacy or confidentiality;
- issuer-document restrictions where applicable.

Raw licensed or restricted data should remain outside the public repository.

Where necessary, the repository should contain ingestion logic, schemas,
metadata, methodology, and reproducible instructions rather than restricted
source data.

## Secrets and Credentials

The repository must never contain:

- passwords;
- API keys;
- private tokens;
- authentication cookies;
- private certificates;
- connection strings containing credentials;
- confidential client information.

Secrets must be supplied through an appropriate local or deployment mechanism
and must remain outside Git.

## Release Control

Analytical releases should progress through controlled states.

The initial release model is:

- WORKING;
- REVIEWED;
- RELEASED;
- SUPERSEDED.

A released output is immutable.

Corrections or updates must produce a new identifiable release rather than
silently replacing the prior version.

## Auditability Requirement

For a material figure appearing in a released output, another qualified analyst
should be able to determine:

1. what the figure represents;
2. whether it was disclosed, calculated, estimated, or assumed;
3. the relevant as-of date;
4. its supporting source or inputs;
5. its verification state;
6. the methodology used where calculated;
7. whether subsequent corrections or restatements exist.

If those questions cannot be answered, the figure is not sufficiently governed
for release.
