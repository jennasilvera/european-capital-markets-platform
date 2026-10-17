# Durable Analytical Bundles: Contract Review

## Decision and implementation status

This document specifies the next boundary after coherent PostgreSQL rate-change
composition. The pure lossless codec and offline replay verifier are now
implemented for the existing rate-change method. Archive publication, database
capture, release storage, and historical queries remain unimplemented. Canonical
storage and existing calculation APIs are unchanged.

A bundle retains one complete validated `CanonicalDataset`, one
`RateChangeRequest`, the complete computed `RateChangeResult`, and explicit
format and execution identities. Capture calculated and blocked outcomes alike.
Acquisition or validation exceptions produce no successful analytical bundle.
A bundle is evidence of a computation over retained content, not release approval.

## Retention boundary

Retain the entire dataset supplied to the calculation, including every populated,
pending, conflicting, missing, and unrelated record. Retain all entity and typed
definition collections, observation inputs, evidence, sources, notes, verification
states/timestamps, and relationship tuple order. An empty collection is explicit.
This deliberately accepts the full reader's existing memory/storage cost.

The result's endpoint closures explain its decisions but are not an independently
validated canonical dataset. They do not prove the absence of other candidates,
and transitive input observations can reference subjects outside the selected
series. Reconstructing a reduced dataset from result lineage would require a
separately designed completeness/closure contract. Do not silently introduce one.

Both endpoints must be calculated from the very dataset retained in the bundle.
The future capture path owns acquisition once and invokes the pure calculator;
it must not call the current database calculation adapter and then load another
dataset for archival. Reader transaction closure remains before calculation and
encoding. No database transaction spans archival I/O.

Retained source metadata and URLs do not archive the underlying source documents.
Raw source bytes, entitlements, and document retention need their own controls;
this contract supports replay of retained canonical facts, not independent
reverification of a remote document.

## Logical envelope and identities

| Required part | Contract |
| --- | --- |
| Format identity | Explicit bundle-format and record-schema versions; no inference from package version |
| Dataset | Complete canonical record collections used for calculation |
| Request | Every request field, including endpoint roles/dates and selection/method versions |
| Result | Every stored result field and nested endpoint decision; computed properties are recomputed, not trusted wire fields |
| Execution identity | Full source commit, retained build/source artifact digest, Python implementation/version, dependency lock digest, selection/method/Decimal policy identities |

The reproducibility claim requires retention of the referenced source/build and
lock artifacts; names and digests alone are insufficient. A dirty source tree or
unavailable required execution artifact cannot qualify for durable replay.
Execution identity is caller-supplied provenance, not proof that code actually ran
in that environment. Hashes provide integrity checks, not authentication.

Bundle identity is separate from canonical `OBS`, `SRC`, `EVD`, and future `REL`
identities. Do not allocate or overload a canonical ID for an in-memory bundle.
A future archive may assign an opaque nonsemantic permanent handle; a digest is
not that handle and must not encode economic meaning. Identical content can be
retained under the same content digest without implying the same release event.

Acquisition times, database transaction identifiers, archive receipts, reviewer
identity, and release events belong in separately versioned provenance records.
They are not candidate eligibility or historical availability inputs. Do not
invent a historical snapshot instant from a timestamp taken after acquisition.

## Wire format v1 requirements

Use a closed, versioned UTF-8 JSON schema with explicit record/scalar type tags.
No Python pickle, dynamic import, class-name evaluation, binary float conversion,
or automatic coercion. Encode every dataclass field, including explicit nulls;
unknown/missing/duplicate object keys and unknown tags or enum members fail closed.
Schema defaults must never fill a missing archived field.

| Value | Lossless encoding requirement |
| --- | --- |
| Decimal | Tagged sign, coefficient digit string, and integer exponent from `as_tuple()`; preserve scale, signed zero, and finite exponent without ambient-context arithmetic |
| Integer / boolean | Distinct tags; booleans cannot pass as integers; no lossy JSON-number path |
| String / null | Preserve exact Unicode content and explicit null; no trimming or Unicode normalization |
| Date | Tagged strict ISO calendar date; reject datetime substitution |
| Datetime | Distinct tag preserving wall-clock components, microseconds, numeric UTC offset, timezone name, and fold; v1 supports naive values or fixed-offset `datetime.timezone` only, rejecting other tzinfo classes rather than discarding zone identity |
| Enum | Explicit approved enum type and member value, not an untyped string |
| Record / collection | Explicit approved record type and every field; collections are ordered arrays with duplicates rejected where canonical validation requires uniqueness |

Canonical validation and analytical scalar checks still apply after decoding;
the codec must not relax them. Nonfinite Decimals are rejected. Unsupported
runtime scalar/tzinfo types fail encoding rather than become strings. Supporting
naive timestamps in the wire format does not make naive verification timestamps
valid for analytical selection. The timestamp restriction is a new serialization
boundary; current in-memory APIs are unchanged.

Canonical bytes use sorted object keys, compact separators, UTF-8 without BOM,
non-ASCII characters emitted directly, no JSON numeric NaN/Infinity, and no
trailing newline. Integer tokens use ordinary base-10 without redundant zeros.
Retain original array/tuple order, including top-level dataset collections;
reordering such a dataset changes bundle bytes even if analytics are order
independent. Selector-owned output ordering remains governed by its policy.

Compute SHA-256 over exactly those canonical envelope bytes. Store the digest
outside those bytes to avoid self-reference; version the digest algorithm in an
archive descriptor. On import, reject noncanonical bytes rather than silently
normalizing an alternate representation. A recomputed hash alone cannot detect
an attacker replacing both content and digest; trust/authenticity is separate.
Bounded input size, nesting, string length, integer/Decimal coefficient length,
and record counts must be explicit codec limits tested before archive exposure.
Exceeding a limit is an import failure, never truncation or partial replay.

## Verification and replay

Verification has separate outcomes from analytical `BLOCKED`:

1. Check canonical bytes and expected digest, supported schema/tags and limits.
2. Reconstruct approved frozen types without coercion and validate the complete
   dataset and request through the public boundaries.
3. Require the declared execution and policy versions. No dispatch to the newest
   implementation when an old one is absent. Incompatible or unavailable runtime
   artifacts mean replay unavailable, not a successful recomputation.
4. Recompute with `calculate_rate_change` over the retained dataset, without
   PostgreSQL, provider, current catalog, clock, or network access.
5. Compare the complete canonical encoding of the recomputed result with the
   stored result, including Decimal representations, endpoint candidates,
   exclusions, support, lineage, block reasons, and arithmetic signals.

Ordinary dataclass equality is insufficient: Decimal numeric equality hides
scale/sign changes. A supplied frozen result can also be fabricated; immutability
is not validation. Only a matching recomputation qualifies as verified replay.
A missing candidate, altered stored answer, or changed policy is a verification
failure, not ordinary analytical missingness. A valid retained blocked outcome
must replay to that same complete blocked outcome.

Version evolution requires a new decoder/method handler or explicit migration
producing a new bundle linked to its predecessor. Preserve original bytes and
digest. Never reinterpret old bytes under a new schema or overwrite an old
bundle after a methodology correction.

## Archive and release boundary

Archive durability is not implemented here. Its later contract must define
immutable publication, collision/conflicting-content rejection, concurrent
publish behavior, permissions, read-back integrity, and recovery when bytes are
published but receipt registration fails. A failed write cannot report success;
a retry must identify the same intended content without replacing another
bundle. Filesystem rename or a database transaction alone does not establish
cross-system atomicity. Choose the storage backend before specifying its crash
and durability guarantees, then test them against that real backend.

Archiving a bundle does not move it through `WORKING`, `REVIEWED`, `RELEASED`,
or `SUPERSEDED`. Those existing governance concepts still lack implemented
release records. A later release record must bind the exact bundle digest and
permanent handle, rendered outputs, method identities, approval evidence, and
explicit correction/supersession relationships. Approval changes are append-only
events; supersession does not mutate earlier released bytes or delete evidence.

A newly acquired snapshot may add equal support, add a conflict, or reflect a
changed verification state. Produce a new bundle. Do not automatically label it
a correction or suppress a prior release. A human-governed relation must explain
whether it is an update, methodological revision, or correction. Bundle capture
and replay never auto-verify canonical observations or infer reviewer approval.
Economic-date replay remains distinct from unsupported known-at reconstruction.

## Dependency and acceptance matrix

The codec, decoder, replay, and integrity rows are implemented and exercised by
`tests/unit/test_analytical_bundles.py`. Database capture, archive, and release
rows remain future acceptance requirements; they are not implemented coverage.

| Component | Dependency | Contract | Failure mode | Expected behavior | Test level | Real or mocked |
| --- | --- | --- | --- | --- | --- | --- |
| Codec | Domain records and scalar types | Every field and representation retained | Decimal scale/sign, bool/int, null, enum, timestamp or tuple order lost | Exact encoded round trip; unsupported types rejected | Unit/contract | Real codec/domain/Decimal |
| Decoder | Closed schema and limits | Fail before calculation on malformed input | Duplicate/unknown keys, tags, versions, noncanonical bytes, excessive size | Explicit import error; no coercion/partial object | Adversarial contract | Real parser/validator |
| Capture | Reader and pure calculator | Same full dataset retained and used once | Second acquisition sees correction | Retained dataset and result replay together | PostgreSQL composition/concurrency | Real reader/database, timing hooks only |
| Replay | Versioned calculator and retained execution artifacts | Complete result matches | Changed answer, missing conflicting candidate, changed policy/runtime | Verification failure or explicit unavailable replay | Unit/composition | Real codec/selector/calculator; routing mocks only for forbidden I/O |
| Integrity | Canonical bytes and digest | Detect content mismatch | Modified byte, stale external digest | Reject before accepting replay | Contract | Real hash/bytes |
| Archive, later | Chosen durable backend | Immutable publication and recoverable receipt | Crash, concurrent collision, partial write | No false success or overwritten bundle | Backend integration/fault recovery | Real chosen backend |
| Release, later | Bundle archive and approval records | Exact reviewed content and immutable history | Unapproved release, correction overwrites predecessor | Reject transition; retain prior release and explicit relation | Domain and storage integration | Real state model/backend |

Codec fixtures must include all canonical record families and supported scalar
variants, empty and full datasets, calculated and every blocked category,
transitive lineage, repeated evidence order, and strict caller Decimal contexts.
Golden bytes/digests must be independently reviewed, not generated and accepted
by the same serializer under test. Mutation cases must change semantically
material retained content, including excluded candidates and stored diagnostics.
Existing tests already prove selector order independence and PostgreSQL snapshot
coherence; new tests should target retention/replay seams rather than duplicate
those guarantees.

The pure codec and replay increment introduces no archival writes, release
state machine, canonical migrations, identifiers, or additional formulas.
The next increment is database-to-bundle capture using exactly one retained
reader dataset; archival backend selection/publication follows separately.


## Implemented v1 API and limits

Public functions live in `european_capital_markets.analytics.bundles`:

| API | Guarantee |
| --- | --- |
| `create_rate_change_bundle(dataset, request, execution)` | Real calculation over the supplied dataset; retains all records and rejects content outside the codec boundary |
| `encode_bundle(bundle)` | Strict typed canonical bytes, not certification of a caller-built result |
| `decode_bundle(content, expected_sha256=...)` | Integrity/canonical-wire checks, closed reconstruction, and complete canonical dataset validation; not result replay certification |
| `verify_bundle(content, expected_sha256=..., execution=..., source_artifact=..., lock_artifact=...)` | Matching execution declaration/artifact hashes, real recomputation, and full result encoding comparison |

A separately retained descriptor must carry `sha256` and the expected lowercase
hex digest from `hashlib.sha256(content).hexdigest()`. The API does not create or
persist a descriptor, allocate a bundle ID, or imply authenticity. Replacing both
content and descriptor is outside its integrity guarantee.

`ExecutionIdentity` requires a full lowercase 40-character Git commit, two
SHA-256 digests, exact Python implementation/patch version, a true clean-tree
attestation, and the three current analytical policies. Unsupported identities
raise `ReplayUnavailableError`; malformed wire, integrity, or replay mismatch
raise `BundleError`. Domain validation failures on decoded datasets are wrapped
in `BundleError`. Capture's calculation/domain errors retain their existing API
behavior. Analytical blocked results remain ordinary retained outcomes.

The verifier compares the supplied execution identity with the retained one and
hashes supplied source/build and lock bytes. It does not inspect Git, execute an
artifact, install dependencies, launch a historical interpreter, or attest the
loaded deployment. The caller must establish that the artifact corresponds to
the declared commit and the running code/environment. Successful replay is
conditional on that attestation. Arbitrary matching artifact bytes alone cannot
prove historical execution. The pure API makes no durable environment-retention
claim and performs no filesystem, database, provider, or network access.

The v1 registry explicitly enumerates record types/fields and enum types; wire
tags never cause imports or class lookup outside it. Enum payloads use exact
member values, including integer `SourceTier` values. Every record field is
required. Dataclass annotations are checked with exact runtime types, including
bool versus int, tuple element types, and date versus datetime. Added fields
cannot silently enter the format. A future change to annotations or enum meaning
requires schema review/versioning, even if field names are unchanged.

Limits are fixed by v1, applied on encoding and decoding, and cannot be supplied
by an import request:

| Limit | Maximum |
| --- | --- |
| Content bytes | 8 MiB, checked before JSON parsing and public import hashing |
| JSON container nesting | 64, checked before parsing with strings/escapes respected |
| Logical tagged-value nesting | 64 |
| Tagged-value occurrences | 200,000 |
| Record occurrences | 20,000, including repeated records in nested result lineage |
| String length | 262,144 Unicode code points, valid UTF-8 only |
| Decimal coefficient | 4,096 digits |
| Integer token/value | 256 base-10 digits, excluding sign |

Byte/nesting limits bound parser allocation before reconstruction; tagged-node,
record, and string limits are enforced during reconstruction and re-encoding.
These limits reject large datasets rather than streaming or slicing them. The
full-dataset reader cost remains unchanged. A descriptor's expected digest is a
required argument; a caller must not treat hashing untrusted bytes themselves
as establishing their provenance.

The tests use real codecs, domain validation, selector, Decimal, and calculator.
They retain all canonical record families, scalar variants, timestamp names and
folds, transitive inputs, unrelated records, excluded equal candidates, source
order, and original Decimal scale/sign. They reject malformed/duplicate fields,
future versions, unsupported values, over-limit content, changed results and
removed conflicting candidates. Exact hand-specified scalar bytes, an independently
specified empty-dataset fixture, and a complete blocked bundle fixture freeze
wire examples and SHA-256 digests. The latter pins CPython 3.12.12; the test
verifies its fixed digest before substituting only the current supported Python
patch-version token for runtime replay. No database behavior is inferred from
these tests. A forbidden-catalog monkeypatch checks only that current catalog
loading is not used during replay; limit monkeypatches exercise smaller versions
of the same enforced budgets, with actual scalar/depth boundary cases as well.
