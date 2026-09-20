# Controlled Market-Data Ingestion

## Purpose

This document freezes the provider-neutral boundary between the controlled
market-series reference catalog and future live market-data retrieval.

The ingestion layer must preserve source material and provenance before values
are admitted to the canonical analytical model.

This increment defines contracts only. It does not implement a live provider,
network transport, credentials, scheduling, or recurring ingestion.

## Architectural Flow

The controlled flow is:

1. select an existing canonical market series from the controlled reference
   catalog;
2. retrieve source material through a separately reviewed provider transport;
3. preserve the retrieved bytes as a raw artifact;
4. calculate and retain raw-artifact integrity metadata;
5. parse and normalize provider-specific content into a provider-neutral market
   datum;
6. construct canonical `SourceRecord`, `EvidenceRecord`, and
   `ObservationRecord` lineage;
7. validate the complete canonical dataset;
8. persist the validated dataset atomically.

Provider-specific schemas stop at the normalization boundary.

They must not become canonical domain semantics.

## Reference Selection Versus Retrieval Source

The controlled market-series catalog identifies the approved economic series
and its reviewed reference-level source/provider selection.

The source actually used for one retrieval is separate.

For example, a later ingestion implementation may require:

- a provider endpoint;
- a distributor-specific field;
- an operational series identifier;
- a licensed delivery channel.

Those operational identifiers must not silently replace the canonical market
series identity or the administrator/reference identifier recorded in the
catalog.

`RetrievalSource` therefore describes the actual source used for one retrieval.

`RawRetrievalArtifact.market_series_id` binds that retrieval back to the
canonical economic series.

## Raw Artifact Contract

Raw source bytes are preserved exactly as retrieved.

Each raw artifact carries:

- canonical `market_series_id`;
- actual retrieval-source metadata;
- timezone-aware retrieval timestamp;
- controlled archived location;
- SHA-256 content digest;
- byte length;
- optional media type.

The raw byte payload is not committed to Git.

The existing `data/raw/` ignore policy remains authoritative.

A raw artifact must not be silently overwritten by a later retrieval. A later
retrieval is a separate source event even when the returned content is
identical.

The SHA-256 digest provides an integrity check. It does not become a canonical
entity identifier and does not replace normal `SRC`, `EVD`, or `OBS`
identifier allocation.

## Retrieval Timestamp Versus Canonical Dates

`RawRetrievalArtifact.retrieved_at` retains an exact timezone-aware retrieval
timestamp.

The current canonical `SourceRecord` stores `access_date` at date granularity.

The current canonical `ObservationRecord` stores `as_of_date` at date
granularity.

The ingestion layer therefore preserves retrieval-time precision without
pretending that the Phase 1 canonical observation model is intraday.

## Normalization Contract

`NormalizedMarketDatum` is the provider-neutral boundary.

It contains:

- canonical market-series ID;
- canonical observation field name;
- observation as-of date;
- one `Decimal` value or one explicit canonical missing-data state;
- evidence locator;
- optional canonical unit and currency metadata;
- optional evidence label and notes.

A parser or provider adapter may understand external column names, API fields,
XML elements, CSV structures, or vendor codes.

Those details must be translated before constructing a
`NormalizedMarketDatum`.

The canonical validators remain authoritative for whether the normalized field,
unit, value, and market-series family are semantically compatible.

## Lineage Construction

`build_pending_market_lineage()` constructs:

- one `SourceRecord`;
- one `EvidenceRecord`;
- one `ObservationRecord`.

Canonical IDs are supplied through `AllocatedLineageIds`.

The ingestion transformation does not invent a second identifier allocation
scheme and does not derive canonical IDs from content hashes.

The source record describes the actual material used for the retrieval.

The evidence record provides the precise locator within that source.

The observation references the evidence record.

## Verification Boundary

Automated ingestion is not equivalent to analytical verification.

A populated ingested market observation is constructed as:

- `ValueClass.DISCLOSED`;
- `VerificationState.PENDING`;
- no `verified_at` timestamp.

A normalized explicit `UNAVAILABLE` state maps to
`VerificationState.UNAVAILABLE`, consistent with the frozen canonical lineage
rules.

No ingestion adapter may automatically convert successful transport or parsing
into `PRIMARY_VERIFIED`, `SECONDARY_VERIFIED`, or `CROSS_VERIFIED`.

Verification remains a separate governed action.

## Persistence Boundary

The existing canonical writer is the persistence boundary.

Ingestion must not bypass `validate_canonical_dataset()`.

The existing writer remains insert-oriented and transactional. Any validation
or database failure aborts the complete logical write unit.

Transport success therefore does not imply canonical persistence success.

## Failure Classes

Future execution layers must keep these failures distinguishable:

1. retrieval failure;
2. raw-artifact integrity failure;
3. parsing failure;
4. normalization failure;
5. canonical validation failure;
6. persistence failure.

A failed or rejected ingestion attempt must not create a partially canonical
dataset.

Operational exception/audit persistence remains a later controlled increment.

## Credentials and Secrets

Credentials do not belong in:

- reference catalog entries;
- raw-artifact metadata;
- canonical source records;
- evidence records;
- observations;
- committed configuration.

The repository's existing environment/secret ignore policy remains in force.

A later transport layer must obtain credentials through an explicitly reviewed
runtime mechanism.

## Licensing Boundary

A reviewed reference mapping is not permission to retrieve or redistribute
licensed observations.

Before activating a live adapter, the project must separately establish:

- permitted access method;
- applicable credentials or entitlement;
- storage rights;
- retention requirements;
- redistribution constraints;
- any restrictions on committed fixtures or test data.

Licensed raw observations must not be committed merely to make an ingestion
test reproducible.

Synthetic fixtures should be used where redistribution rights are absent.

## First Controlled Provider Implementation

Step 13B introduces the first provider transport and parser against the
European Central Bank Data Portal.

The implementation uses the ECB SDMX 2.1 data endpoint with CSV output and a
bounded `lastNObservations` query.

The first supported controlled series is the ECB Deposit Facility Rate
reference mapping already present in the market-series catalog.

The adapter validates provider semantics observed in the reviewed ECB CSV
contract, including:

- the full controlled `KEY`;
- daily frequency (`FREQ=D`);
- euro currency (`CURRENCY=EUR`);
- Deposit Facility Rate provider identifier (`PROVIDER_FM_ID=DFR`);
- level data type (`DATA_TYPE_FM=LEV`);
- provider unit `PCPA`.

`PCPA` is normalized into the canonical `PERCENT` observation unit. The
provider-specific unit code does not enter the canonical domain taxonomy.

HTTPX is the selected HTTP client for this provider implementation. TLS
verification remains enabled. The client uses bounded connect and network
timeouts and follows redirects.

Deterministic tests use HTTPX's in-process mock transport. CI therefore does
not depend on ECB network availability.

The provider adapter returns:

1. transport response bytes and safe response metadata; and
2. provider-neutral `NormalizedMarketDatum` records.

The provider transport itself deliberately does not fabricate an
`archived_location`. Step 13C supplies the controlled raw-artifact landing
boundary that must run before normalization in an ingestion workflow.

## Immutable Raw-Artifact Landing

Step 13C implements an immutable filesystem store for retrieved market-data
bytes.

The production archive convention is:

```text
data/raw/<namespace>/<market_series_id>/<YYYY>/<MM>/<DD>/
<UTC retrieval timestamp>_<storage token>.<suffix>
```

The storage token is a UUID used only to distinguish filesystem retrieval
events. It is not a canonical entity identifier, is not derived from the
content digest, and does not replace `SRC`, `EVD`, or `OBS` allocation.

A successful landing performs these operations in order:

1. validate retrieval metadata and content integrity inputs before creating
   archive content;
2. create or open archive directories without following symbolic links;
3. write exact response bytes to an exclusively created staging file in the
   destination directory;
4. flush and `fsync` the staging file;
5. atomically hard-link the completed staging inode to the final archive name;
6. `fsync` the destination directory;
7. remove the staging directory entry;
8. `fsync` the destination directory again;
9. read the landed bytes and verify SHA-256 and byte length against the
   returned `RawRetrievalArtifact`.

The hard-link publication step is intentionally used instead of `os.replace`.
`os.replace` can overwrite an existing destination. Hard-link creation is
atomic and fails if the final archive name already exists, preserving the
no-silent-overwrite rule.

Path components are controlled. Parent traversal is rejected and archive
directories are opened with no-follow semantics so an existing symbolic link
cannot redirect landing outside the controlled raw root.

Identical provider bytes retrieved at different times or under different
storage tokens remain distinct retrieval events even though their SHA-256
digests are equal.

Raw bytes remain excluded from Git under the existing `data/raw/` ignore
policy.

## Retrieve-Land-Normalize Orchestration

Step 13C also introduces the first controlled orchestration boundary for ECB
Deposit Facility Rate ingestion:

```text
retrieve -> land immutable raw bytes -> verify raw integrity -> normalize
```

The raw artifact must exist before provider parsing begins. If parsing or
normalization fails, the landed provider bytes remain preserved for diagnosis
and later exception handling.

The orchestration result stops at the provider-neutral normalized datum
boundary. It does not allocate canonical lineage IDs, construct canonical
source/evidence/observation records, or write canonical database state.

The existing provider convenience helper that retrieves and normalizes ECB
data is not the canonical ingestion workflow. Any workflow intended to feed
canonical persistence must pass through the raw-landing orchestration boundary
first.

## Remaining Deliberately Deferred

The following remain separate reviewed increments:

- retry/backoff policy;
- rate-limit handling;
- provider credentials and entitlement mechanisms;
- ingestion scheduling;
- staged-data persistence;
- ingestion-run audit persistence;
- exception/quarantine persistence;
- canonical identifier allocation;
- idempotency/revision policy for repeated observations;
- canonical persistence orchestration;
- additional provider adapters.

Live requests may be used as explicit local source-review probes, but normal
unit and CI tests remain deterministic and network-independent.
