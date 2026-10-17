# PostgreSQL Analytical Archive: Backend Contract

## Decision and status

Use PostgreSQL as the first immutable analytical archive backend. Retain bundle
bytes, source/build artifact bytes, dependency-lock bytes, and their descriptor
in one logged row committed by one transaction. The repository already operates
and integration-tests PostgreSQL; this choice avoids a second filesystem/object
store and a distributed commit between bytes and receipt registration.

This is a reviewed implementation specification, not an implemented archive,
migration, publisher, loader, role deployment, or release service. The current
head remains migration `0004_ingestion_run_state`. Existing bundle capture and
pure replay APIs remain unchanged. Implement this boundary in a subsequent
coherent increment with real migration, concurrency, and recovery tests.

The archive supports the existing rate-change bundle format only. A stored
`BLOCKED` outcome is legitimate diagnostic content. Archiving does not approve a
release, verify canonical observations, or enable known-at historical queries.

## Existing storage review

`ImmutableRawArtifactStore` already demonstrates preflight validation, opaque
storage tokens, exclusive staging creation, no-replace hard-link publication,
file/directory synchronization, and verified read-back. Its contract is provider
retrieval evidence with an ingestion-specific path and raw-artifact metadata.
It does not atomically retain an analytical envelope plus execution artifacts
and an independently registered receipt. Do not couple analytical archival to
its provider namespaces, private filesystem helpers, or raw-retrieval records.

Reuse its principles of validation before publication, immutable identity,
content verification, and explicit uncertain outcomes. PostgreSQL provides the
selected transaction boundary; no raw-storage implementation changes are needed.
Object storage, filesystem export, compression, content deduplication, garbage
collection, and external artifact references remain separately reviewed scope.

## Permanent identity and retained package

The caller supplies one non-nil UUID as an operational permanent archive handle;
use a randomly generated UUID for new work. The handle is not a canonical `REL`,
`OBS`, `SRC`, or `EVD` ID, contains no economic meaning, and is independent of
content digests. Preserve it across retries of the same intended publication.
Equal content may have different archive handles; no digest uniqueness rule
silently merges different publication intents. There is no chronological
meaning in UUID or digest order.

One prospective `analytical_bundle_archives` row contains exactly:

| Column group | Required retained values |
| --- | --- |
| Identity | `archive_id` UUID primary key; non-nil |
| Descriptor | `descriptor_version = rate-change-archive-receipt-v1`, `digest_algorithm = sha256` |
| Bundle | `bundle_content` bytea, `bundle_sha256` lowercase hex, `bundle_byte_length` integer |
| Execution source/build | `source_artifact` bytea, `source_sha256` lowercase hex, `source_byte_length` integer |
| Dependency lock | `lock_artifact` bytea, `lock_sha256` lowercase hex, `lock_byte_length` integer |

Every column is non-null. No acquisition/release timestamp, mutable status,
reviewer, or source-series foreign key is inferred. The envelope already retains
its full economic identity, request, outcome, and execution declaration. Archive
rows are independent of subsequent canonical record changes/deletions and are
not part of `CanonicalDataset` or canonical reader reconstruction.

The receipt is a frozen typed projection of identity, descriptor version,
algorithm, and all three digests/lengths; it excludes large byte payloads. It is
constructed from verified persisted content and returned only after successful
transaction exit. A publication result may separately indicate `INSERTED` or
`ALREADY_PRESENT`; disposition is not stored as mutable archive state. The
receipt is integrity metadata, not an authenticated signature or release record.

Archive limits are additional to the unchanged bundle codec limits:

| Payload | Accepted byte length |
| --- | --- |
| Bundle | 1 through 8 MiB |
| Source/build artifact | 1 through 64 MiB |
| Dependency lock artifact | 1 through 4 MiB |

The total payload bound is 76 MiB per row before database/protocol overhead.
These are deliberate bounded in-memory limits, not throughput/capacity claims.
Reject rather than truncate, stream incompletely, or substitute an external URL.
Storage budgeting, backups, restore drills, access controls, and replication
capacity must be established by deployment before production retention.

## Integrity and immutability controls

The planned migration creates a regular logged table. Database checks enforce
non-nil identity, descriptor/algorithm constants, lowercase digest shape, byte
bounds, and `octet_length` matching each declared length. Each digest must equal
`encode(sha256(payload), 'hex')` for its own payload. PostgreSQL 18 provides these
binary-string primitives without adding an extension [1]. Constraints protect
byte integrity; they do not parse the analytical schema or establish that a
result was correctly calculated.

Install unconditional statement triggers rejecting `UPDATE`, `DELETE`, and
`TRUNCATE`, including no-op statements. Never use `ON CONFLICT DO UPDATE`, even
for an equal replay. Statement triggers cover operations with zero affected rows;
`TRUNCATE` requires a statement trigger [4]. Application roles need only archive
`SELECT` and `INSERT`; deploy grants separately from schema ownership. No automatic
role creation or grants to unrelated existing tables belong in this increment.

Owners/superusers, disabled triggers, replication bypass, storage corruption,
and administrative DDL remain outside the immutability trust boundary. There is
no database-enforced WORM or malicious-administrator claim. Direct SQL can insert
self-consistent bytes that do not represent a valid bundle; publication preflight
and explicit replay verification remain authoritative for analytical validity.

The migration downgrade must refuse to remove a populated archive. Empty-table
downgrade/re-upgrade remains supported. Corrections get new archive handles and
preserve prior rows; a future release model owns correction/supersession links.
There is no ordinary delete, retention expiry, or archival overwrite API.

## Publication protocol

The planned publisher accepts an Engine, caller-retained archive UUID, exact
canonical bundle bytes, expected bundle digest, execution declaration, and
source/build and lock bytes. It never captures or recalculates against the live
database as a hidden publication step.

1. Validate argument types, handle, and all payload bounds before opening the
   database. Call the existing pure `verify_bundle` with the expected digest,
   execution declaration, and supplied artifacts. Require complete replay match;
   do not accept `encode_bundle` alone as proof. Artifact-to-commit and running
   environment attestation remain caller-owned as in the bundle contract.
2. Open one publisher-owned `READ COMMITTED` transaction. Require server `fsync`
   and `full_page_writes` on; fail closed if unavailable/off. Set transaction-local
   `synchronous_commit=on` and verify that setting. Do not weaken a configured
   standby requirement, change global settings, or return success on setting error.
3. Attempt `INSERT ... ON CONFLICT (archive_id) DO NOTHING RETURNING archive_id`.
   No pre-read decides whether an insertion is safe. The primary key arbitrates
   concurrent attempts; the archive is not a worker lease or distributed lock.
4. In a separate command in that transaction, load the complete row by handle.
   Verify descriptor, lengths, digests, and exact equality of all three payloads
   with the submitted bytes. Equal hashes alone do not establish equality.
   Different content under an occupied handle raises a typed conflict and rolls
   back this attempt. A missing row is an integrity/protocol error, not success.
5. Build the receipt, exit/commit the transaction, and only then return it and
   the disposition. Pre-commit read-back is part of the same transaction; no
   additional post-commit database request is required for acknowledgment.

The separate read in step 4 is essential. Under `READ COMMITTED`, a conflicting
`DO NOTHING` insert can skip because of a row not visible to that command's
snapshot; a subsequent command obtains a fresh snapshot [3]. Do not combine
insert and fallback selection in a single CTE/snapshot. Once a conforming row is
committed it cannot disappear through an application deletion path. A waiting
insert can proceed if its competing transaction rolls back. Timeouts/deadlocks
propagate without an internal retry loop; caller Engine timeout/pool policy
remains explicit and no arbitrary global timeout is introduced.

A retry of a confirmed or uncertain publication must reuse the exact UUID,
bundle bytes, and artifacts. It returns the same receipt for an identical row;
changing any retained byte is a conflict. The caller must retain the intended
package and UUID until the outcome is resolved. Losing that context and inventing
a fresh UUID cannot establish exactly-once publication. No durable publication
attempt journal or scheduling/worker framework is introduced here.

## Commit, failure, and durability boundary

| Failure point | Observable contract and recovery |
| --- | --- |
| Invalid package or replay mismatch | No archive transaction or row; report validation failure |
| Database/settings unavailable | No success; propagate dependency/configuration error |
| Exception before commit | Transaction rolls back; no partial bundle/artifact/descriptor row |
| Competing equal publication commits | Wait under database arbitration, then return matching receipt |
| Competing different publication commits | Preserve winner; report conflict without overwrite |
| Competitor rolls back | This insertion may complete; no abandoned reservation |
| Commit/connection outcome uncertain | Raise; caller must not assume absence or mint a replacement handle |
| Commit succeeds but process dies before receipt delivery | Complete row remains; explicit identical retry recovers the receipt |
| Returned receipt later fails integrity checks | Report corruption; never repair or rewrite in place |

The success guarantee is conditional on the configured PostgreSQL cluster and
honest storage. With synchronization enabled, commit waits for the required WAL
flush; asynchronous acknowledgment is insufficient [2]. Setting checks cannot
prove that hardware honors flushes, attest past server configuration, or repair
a cluster previously run unsafely. Deployment owns that history and its storage
assurance. Existing-row retries assume prior publication through this protocol;
they cannot retroactively certify a row inserted by an arbitrary asynchronous
SQL client. Do not claim durability from row visibility alone.

There is no cross-system partial receipt registration: all retained components
share the transaction. This does not provide backup retention, geographic
redundancy, point-in-time recovery, failover correctness, or power-loss testing.
Application-process crash tests prove acknowledgment/retry semantics, not
physical-media survival. Never kill unrelated CI sessions or the shared database
server to manufacture a durability test.

## Read-back and replay interfaces

The planned loader accepts the expected receipt, queries by its UUID in one
read-only transaction, and returns the exact three retained byte payloads plus
that receipt after checking bounds, constants, hashes, lengths, and expected
metadata. Absence, altered metadata, or corrupted bytes is an error. There is
no archive-listing discovery API that substitutes untrusted stored hashes for an
independently retained expected receipt. All expected metadata can be constructed
from the retained intended package when resolving an uncertain publication.

Loading bytes must not dispatch to a newer calculation method or reinterpret an
old bundle. Byte retrieval and semantic replay stay separate: an archive can
remain readable when the current runtime cannot instantiate its execution
identity. A caller then invokes `verify_bundle` with the loaded artifacts and
its matching execution attestation, or receives the existing explicit replay
unavailable/mismatch error. Retaining artifacts does not install or execute them,
validate their licensing, or prove their binding to the declared source commit.
The archive supports future offline restoration, not automatic historical
runtime orchestration or independent source-document reverification.

## Implementation acceptance matrix

These are required future tests; no archival behavior is implemented by this
contract-only increment.

| Component | Dependency | Contract | Failure mode | Expected behavior | Test level | Real or mocked |
| --- | --- | --- | --- | --- | --- | --- |
| Publisher preflight | Existing codec/replay and retained artifacts | Analytical validity and bounds before I/O | Forged result, missing artifact, over-limit bytes, invalid UUID | Reject without database acquisition | Unit/composition | Real replay; mocked connection only to forbid I/O |
| Migration | PostgreSQL checks and binary hashing | Every payload agrees with descriptor | Bad length/hash/algorithm, nil ID, oversize payload | Direct SQL constraint rejection | PostgreSQL integration | Real migration/database |
| Immutability | Triggers and application SQL | No replacement or deletion | Update/no-op update, delete/no-op delete, truncate | Statement fails; original row unchanged | PostgreSQL integration | Real SQL and triggers |
| Publish/load | Driver, transaction, bytea, codec | Exact content plus artifacts round trip | Decimal/UTF-8/lineage or binary artifact damage | Matching receipt and exact replay using loaded bytes | PostgreSQL composition | Real database and pure replay |
| Concurrency | Unique index and separate command snapshots | One immutable row per handle | Equal/different simultaneous writers, first writer rollback | Equal receipt or explicit conflict; no torn state | PostgreSQL concurrency | Real independent connections, bounded coordination |
| Recovery | Commit boundary and retained caller intent | No false success or duplicate logical retry | Backend loss before commit; child process exits after commit before return | Rollback or identical receipt recovery as applicable | PostgreSQL process/fault recovery | Real database and process termination; no mocked commit |
| Durability policy | Server/session settings | Synchronous logged publication | Caller session initially asynchronous; unsafe server settings | Transaction-local override/restoration; reject unsafe settings | PostgreSQL integration | Real settings; unsafe-server test only in isolated disposable cluster |
| Loader | Receipt and immutable payloads | Stored metadata is not caller trust | Wrong expected receipt, missing row, corrupted contents | Explicit integrity error, no partial payload | PostgreSQL contract | Real stored records, controlled isolated corruption |
| Version boundary | Opaque load and explicit replay | Preserve old bytes without fallback dispatch | Unsupported execution identity/policy | Retrieval intact; replay explicitly unavailable | Composition | Real loader/codec/version checks |
| Migration lifecycle | Data-preservation guard | Historical archive cannot vanish on downgrade | Nonempty downgrade | Reject; empty downgrade/re-upgrade succeeds | PostgreSQL migration integration | Real Alembic/database |

Integration fixtures must isolate archive data in disposable test schemas or
clusters, use the actual migration path, and keep the shared migration-cycle
schema empty. Administrative teardown of those dedicated fixtures is permitted;
ordinary application deletion must still be rejected and tested. Do not weaken
triggers or truncate shared canonical/archive tables as routine cleanup.

Use event/barrier coordination with bounded waits rather than sleeps. Observe
real lock/wait behavior and server settings. A forced post-commit crash must
occur after the actual database commit and before delivery to the caller;
replacing commit with a stub is not evidence. Unit injection can exercise error
routing or an inaccessible settings branch but must not be labeled physical
crash recovery or real unsafe-cluster coverage. Record any environmental test
limitations explicitly rather than claiming a simulated power-loss guarantee.

The next increment implements this bounded PostgreSQL archive contract, including
its guarded migration, publisher, verified byte loader, and the required real
transaction/concurrency/recovery tests. Broader formulas and release approval
remain separate from storage implementation.

## Primary technical references

1. [PostgreSQL 18 binary string functions](https://www.postgresql.org/docs/18/functions-binarystring.html): `sha256`, `encode`, and `octet_length`.
2. [PostgreSQL 18 WAL configuration](https://www.postgresql.org/docs/18/runtime-config-wal.html): synchronization, server configuration, and commit acknowledgment.
3. [PostgreSQL 18 transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html): `READ COMMITTED` and conflict visibility.
4. [PostgreSQL 18 CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html): statement events and `TRUNCATE`.
