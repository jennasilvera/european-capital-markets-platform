# Controlled Market-Data Ingestion

## Purpose

This document freezes the provider-neutral boundary between the controlled
market-series reference catalog and controlled market-data retrieval.

The ingestion layer must preserve source material and provenance before values
are admitted to the canonical analytical model.

Step 13A established the provider-neutral contracts. Steps 13B through 13H
implement controlled ECB Deposit Facility Rate retrieval, immutable raw landing,
canonical append persistence, and durable same-logical-attempt recovery.
Credentials, scheduling, and automatic retry policy remain deferred.

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

Durable operational run checkpoints are implemented by Step 13H below.
Exception/quarantine persistence and broader operational audit facilities remain
separate reviewed scope.

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

## Canonical Market-Ingestion Handoff

Step 13D adds the provider-neutral transformation from a successfully landed
raw retrieval and normalized datums into a validated canonical dataset.

The handoff sequence is:

```text
landed RawRetrievalArtifact
+ normalized market datums
+ externally allocated SRC / EVD / OBS identifiers
-> build pending source / evidence / observation lineage
-> assemble controlled market-series subject and definition
-> validate CanonicalDataset
```

One raw retrieval maps to one canonical `SourceRecord`. All normalized datums
from that retrieval therefore share one externally allocated `source_id`.
Each datum receives its own externally allocated evidence and observation IDs.

The handoff reuses `build_pending_market_lineage`; it does not duplicate the
source/evidence/observation governance rules and does not promote observations
to verified state.

The selected catalog entry contributes exactly one canonical market-series
record and its matching type-specific definition. The resulting
`CanonicalDataset` is validated using the existing domain validator before it
is returned.

### Persistence remains a separate boundary

Step 13D deliberately stops before database persistence.

The current `persist_canonical_dataset` writer is insert-oriented and expects
the concrete observation subject to be present in the dataset. Reusing that
writer for recurring observations of an already-persisted market series would
attempt to insert the same market-series subject and definition again.

Accordingly, Step 13D does not:

- allocate canonical identifiers;
- define repeated-observation idempotency or revision semantics;
- introduce a second persistence writer;
- use conflict-ignore or upsert behavior;
- persist the handoff automatically.

Safe append persistence against an already-existing canonical market-series
subject requires its own reviewed contract and must preserve the current
atomicity and lineage guarantees.


### Step 13E append persistence contract

Recurring canonical market ingestion persists lineage against an already-existing
controlled market-series subject. The append operation does not recreate or
update the `market_series` row or its type-specific definition.

The supplied append dataset still carries that market-series record and exactly
one matching definition so the normal `CanonicalDataset` validation boundary
remains authoritative before database work begins.

Inside one database transaction the append writer:

1. locks the existing `market_series` row;
2. requires the persisted series identity and type-specific definition to match
   the validated handoff exactly;
3. classifies the supplied `SRC`, `EVD`, and `OBS` identifiers as either wholly
   absent or wholly present;
4. inserts source, evidence, observations, and their lineage junctions when all
   supplied lineage identifiers are absent;
5. treats a wholly present and exactly matching canonical-ID batch as an
   explicit `ALREADY_PERSISTED` replay;
6. rejects partial canonical-ID presence or any persisted-content mismatch;
7. forces deferred relational constraints before transaction completion.

Idempotency is therefore canonical-ID replay idempotency. It is not economic-key
deduplication.

In particular, the tuple:

`(subject_type, subject_id, field_name, as_of_date)`

is not a canonical uniqueness key. A later retrieval with newly allocated
canonical lineage IDs remains a new append even when it reports the same
market-series/date/value combination. This preserves source conflicts,
corrections, repeated retrieval provenance, and historical reproducibility.

The append path deliberately does not use:

- `ON CONFLICT`;
- upsert behavior;
- conflict-ignore behavior;
- destructive updates;
- semantic same-series/date deduplication;
- database-side canonical identifier allocation.

The existing `persist_canonical_dataset` operation remains unchanged and
insert-oriented for complete canonical logical units.

The Step 13E writer also does not broaden the current domain boundary for
calculated observations that depend on observations outside the supplied
validated dataset. Such cross-batch calculation-lineage requirements remain a
separate reviewed design problem if needed.

## Step 13F canonical lineage identifier allocation

Step 13F introduces PostgreSQL-backed allocation for recurring
market-ingestion lineage identifiers only.

The controlled allocator owns these namespaces:

- `SRC` for canonical source records;
- `EVD` for canonical evidence records;
- `OBS` for canonical observations.

`MKS` identifiers remain governed by the reviewed market reference catalog.
Issuer, transaction, instrument, party, participation, lifecycle-event,
assumption, and release allocation remain outside this increment.

Each namespace uses an independent PostgreSQL `bigint` sequence bounded to the
existing nine-digit canonical range `1..999999999`. The sequences do not cycle.

Migration initializes each sequence above the highest already-persisted
identifier in that namespace. An existing namespace at `999999999` is treated
as exhausted rather than wrapped or reused.

Sequence values are deliberately not transactional. A failed transaction,
failed persistence attempt, or abandoned allocation may therefore create gaps.
Those gaps are valid. The numeric component of a canonical identifier conveys
identity only and must not be interpreted as chronology.

One market retrieval allocation returns:

- one `source_id`, shared by every normalized datum from that retrieval;
- one distinct `evidence_id` per datum;
- one distinct `observation_id` per datum.

Allocation itself is not idempotent. Calling the allocator again creates a new
allocation. A retry of the same logical ingestion attempt must retain and reuse
its prior `AllocatedLineageIds` bundle. Durable ingestion-run state and
crash-recovery persistence remain separate reviewed work.

Downgrade is fail-closed. The allocation migration refuses to drop a sequence
when that sequence has issued identifiers above the highest persisted canonical
identifier in its namespace. This prevents downgrade/re-upgrade cycles from
silently reissuing an identifier that was allocated but never persisted.

Step 13F does not:

- allocate controlled market-series identifiers;
- allocate non-lineage canonical entity identifiers;
- derive identifiers from provider keys, hashes, dates, or values;
- alter Step 13E replay semantics;
- orchestrate retrieval through canonical persistence;
- add scheduler, retry, quarantine, or run-state persistence.

## Step 13G end-to-end canonical persistence orchestration

Step 13G composes the already-reviewed ECB Deposit Facility Rate ingestion
boundaries into one successful ingestion-to-persistence path:

```text
retrieve
-> land immutable raw bytes
-> normalize
-> allocate SRC / EVD / OBS identifiers
-> build and validate canonical handoff
-> controlled market-observation append persistence
```

The orchestration is deliberately a composition layer. It does not replace or
weaken any boundary owned by Steps 13C through 13F.

A successful orchestration result retains:

- the retrieval and immutable raw-landing result;
- the allocated lineage identifiers;
- the validated canonical handoff;
- the explicit append-persistence status.

There is no transaction spanning the complete workflow. Raw landing is a
filesystem durability boundary, canonical identifier allocation retains its
PostgreSQL sequence semantics, and append persistence retains its own atomic
database transaction and canonical-ID replay rules.

The orchestration performs no automatic retries. Exceptions from retrieval,
normalization, allocation, handoff construction, or persistence propagate to
the caller.

Failure ordering remains intentional:

- provider parsing or normalization cannot occur before immutable raw landing;
- a failure before allocation consumes no canonical lineage identifiers;
- a failure after allocation may leave unused sequence values, which are valid
  gaps under the Step 13F contract;
- a persistence failure does not trigger an implicit second allocation,
  retrieval, or append attempt.

Calling the full orchestration again is a new retrieval event and may allocate
new canonical lineage identifiers. Durable same-attempt retry recovery requires
retained allocation/run context and remains outside this increment.

Step 13G does not add:

- retry or backoff policy;
- rate-limit handling;
- scheduler behavior;
- provider credential or entitlement management;
- staged-data persistence;
- ingestion-run audit persistence;
- crash-recovery state;
- exception or quarantine persistence;
- broader correction or retraction workflows;
- additional provider adapters.

## Step 13H durable same-logical-attempt recovery

Step 13H adds durable recovery state for one logical market-ingestion attempt.
It closes the recovery gap identified by Steps 13F and 13G: a retry of the same
logical attempt must retain its original raw evidence and reuse its prior
lineage allocation rather than becoming a new retrieval event.

The Step 13F and Step 13G scope statements above describe those increments.
Their APIs and contracts remain unchanged. Recovery uses the separate
`ingest_ecb_dfr_to_durable_canonical_persistence` entry point with a caller-supplied
UUID `run_id`, bound permanently to one controlled market series.

Migration `0004_ingestion_run_state` adds durable run and ordered lineage state.
Its Alembic predecessor is `0003_lineage_id_sequences` (the migration file is
named `0003_canonical_lineage_id_sequences.py`). Run IDs and filesystem storage
tokens are operational identifiers; neither replaces canonical lineage IDs.

### Checkpoints and replay

| Checkpoint | Durable context | Execution or recovery behavior |
| --- | --- | --- |
| `STARTED` | Run ID and controlled market-series ID | Only this checkpoint may retrieve; land immutable bytes and commit raw context before parsing. |
| `RAW_LANDED` | Raw provenance, archived locator, integrity metadata, and storage token | Verify and reparse retained bytes without retrieving again; allocate and retain lineage with the normalized fingerprint. |
| `LINEAGE_ALLOCATED` | Ordered batch fingerprint, datum count, shared SRC, ordered EVD/OBS bundles | Reparse retained bytes and require an exact fingerprint match before reusing retained IDs and calling the append writer. |
| `PERSISTED` | Completed run with retained raw/lineage state and persisted timestamp | Terminal canonical no-op; the durable orchestration returns no new persistence status. |

The fingerprint binds the exact ordered normalized representation, including
Decimal serialization, missingness, dates, units, currency, and evidence
metadata. Changed content or ordering fails closed rather than allocating new
IDs under an already-bound run.

Recovery obtains the original provider identifier from retained
`RetrievalSource.retrieval_identifier`. A changed current provider mapping does
not redefine the historical retrieval. The canonical handoff and append writer
still validate controlled economic identity; recovery does not waive them.
Populated ingested values remain `PENDING`; explicit unavailable data retain
`UNAVAILABLE`. Neither state confers analytical approval.

### Verified raw reload

`ImmutableRawArtifactStore.load_verified_content` checks archive-prefix and
locator structure, market-series namespace, UTC retrieval date/timestamp,
storage token, regular-file status, exact byte length, and SHA-256. Traversal
uses trusted-root, descriptor-relative no-follow opens; intermediate and final
symlinks are rejected. Missing, unsafe, or changed bytes fail closed.

### Canonical commit before checkpoint update

Canonical persistence and the final run checkpoint use separate transactions.
If canonical rows commit while the run remains `LINEAGE_ALLOCATED`, recovery
revalidates raw bytes and normalized content, reuses retained IDs, and receives
`ALREADY_PERSISTED` from the exact canonical-ID append replay. Only after the
writer succeeds does orchestration advance the run to `PERSISTED`. Writer
failure does not mark the run persisted.

This composition is covered by
`tests/integration/test_durable_ingestion_recovery.py` using real PostgreSQL,
real filesystem storage, and a synthetic provider response via mock transport.
The test commits canonical rows, leaves the final checkpoint unadvanced, and
recovers with provider retrieval unavailable. It asserts unchanged canonical
row counts, retained IDs, replay status, and the durable terminal checkpoint.
It models the committed crash state rather than killing an operating-system
process or proving power-loss durability.

### Dependency and failure coverage

This documentation reconciliation changes no runtime dependency, schema, or API.
The existing implementation's important boundaries are:

| Component | Dependency | Contract | Failure mode | Expected behavior | Test level | Real or mocked |
| --- | --- | --- | --- | --- | --- | --- |
| ECB orchestration | Provider/parser | Land before parsing; preserve original retrieval identity | Malformed CSV or current mapping drift | Retain raw checkpoint; recover using original provider identity | Unit/composition | Mock transport and isolated persistence calls |
| Raw recovery | Filesystem | Trusted locator and exact retained content | Symlink, unsafe locator, wrong token, length or digest | Reject reload | Filesystem tests | Real filesystem |
| Run creation | PostgreSQL uniqueness/locking | Same run and series converge; different series conflict | Concurrent first creation | One durable run; identity mismatch fails closed | PostgreSQL integration | Real database |
| Retained allocation | PostgreSQL and ordered fingerprint | Allocate once for exact normalized batch | Changed batch or replay mismatch | Reject drift; reuse exact IDs on matching replay | Unit and PostgreSQL integration | Real database for persistence |
| Append writer | PostgreSQL identity/constraints | Exact canonical-ID replay only | Partial presence or changed content | Reject; no semantic deduplication or destructive update | PostgreSQL integration | Real database |
| Durable orchestration | Raw store, run state, append writer | Canonical commit precedes final checkpoint | Commit succeeds before checkpoint update | Recover as `ALREADY_PERSISTED`, without duplicate rows | PostgreSQL composition | Real database/filesystem; synthetic transport |
| Migration downgrade | Recoverable run state | Do not discard in-flight recovery context | `RAW_LANDED` or `LINEAGE_ALLOCATED` run exists | Refuse downgrade | PostgreSQL integration | Real database |

### Remaining reliability boundaries

There is no distributed transaction across raw publication and the database.
A crash after filesystem publication but before the raw checkpoint commits can
leave an unbound artifact and a `STARTED` run. This state cannot automatically
recover that artifact; a later invocation may retrieve again. Raw evidence is
not overwritten, but orphan discovery/reconciliation is outside Step 13H.

Concurrent first run creation is tested, but this is not a worker lease or an
exactly-once provider-retrieval guarantee. Concurrent orchestration callers can
both observe `STARTED`; conflicting raw bindings fail closed. Callers must not
assume distributed ownership. Automatic retries, scheduler behavior, worker
leases, a `FAILED` checkpoint, and quarantine are not implemented.

Missing or contradictory retained state is an error, not permission to retrieve
again after `RAW_LANDED`. Parser/fingerprint compatibility across future code
changes must be reviewed; replay drift is rejected rather than silently migrated.

## Remaining Deliberately Deferred

The following remain separate reviewed increments:

- retry/backoff policy;
- rate-limit handling;
- provider credentials and entitlement mechanisms;
- ingestion scheduling;
- staged-data persistence;
- broader operational audit facilities beyond the implemented run checkpoints;
- exception/quarantine persistence;
- broader correction/retraction workflows beyond canonical-ID replay;
- additional provider adapters.

Live requests may be used as explicit local source-review probes, but normal
unit and CI tests remain deterministic and network-independent.
