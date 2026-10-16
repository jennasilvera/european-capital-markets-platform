# Durable Analytical Bundles: Contract Review

## Decision and implementation status

This document specifies the next boundary after coherent PostgreSQL rate-change
composition. It is a design contract, not an implemented codec, archive, release
store, or historical query service. Existing APIs and canonical storage are
unchanged. The first implementation should be a pure, lossless codec and replay
verifier for the existing rate-change method; archival publication follows only
after that boundary is tested.

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
| Datetime | Distinct tag preserving wall-clock components, microseconds, numeric UTC offset and fold; v1 supports naive values or fixed-offset `datetime.timezone` only, rejecting other tzinfo classes rather than discarding zone identity |
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

These are future acceptance requirements, not claims of existing test coverage.

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

The next implementation increment is the pure codec plus replay verifier, with
explicit limits and golden fixtures. It introduces no archival writes, release
state machine, canonical migrations, identifiers, or additional formulas.
