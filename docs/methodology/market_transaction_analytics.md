# Market and Transaction Analytics: Phase 1 Design

## Status and decision

This is the analytical design following Step 13H. The exact-date market
selector, pure two-date rate/yield changes, and PostgreSQL snapshot composition
are implemented. Durable analytical releases remain a subsequent increment.
Implementation status and executable contracts are recorded below. Canonical schema,
ingestion contracts, and verification states remain unchanged.

Start with deterministic selection of market observations on explicit economic
dates. Then calculate two-date policy-rate, government-yield, and swap-rate
changes in basis points. These operations establish selection, disagreement,
precision, and lineage contracts before adding wider analytics.

A verified, reproducible result is the objective. The current ECB adapter emits
`PENDING` populated observations, so successful ingestion alone cannot supply
eligible production inputs. This design does not invent or automate a
verification workflow to work around that constraint.

## Review of existing boundaries

| Existing contract | Consequence for analytics |
| --- | --- |
| Seven market-series families and typed definitions | Match canonical economic identity and the governed field/unit; do not substitute a provider ticker. |
| Append writer permits multiple observations for a series/date | Selection must inspect disagreement and repeated evidence; an economic tuple is not unique. |
| `ObservationRecord` separates value class, verification, economic date, evidence, and calculation inputs | Reuse those distinctions; ingestion and evidence quality are not analytical approval. |
| `load_canonical_dataset` validates one read-only repeatable-read snapshot | Use one reconstructed dataset for a calculation; separate repository calls do not share a snapshot. |
| Source access/publication dates are date-granular and publication dates optional | They cannot prove when a fact first became available to the platform. |
| `verified_at` records verification, not ingestion or a history of all verification transitions | It is not a substitute for knowledge-time versioning. |
| Existing FX conversion uses explicit inputs and a private Decimal context | Reuse that discipline; do not add implicit FX lookup to market changes. |
| `REL` and `ASM` concepts exist without frozen release/assumption record models | Do not create database-only release semantics or claim durable release support. |

The historical market-series document describes its original FX-only increment;
the European market framework, current domain code, migration `0002`, and the
persistence contract establish the implemented seven-family extension. Existing
canonical FX conversion and currency-normalized aggregate validation are already
implemented; this layer does not replace them.

The tracked tree has no `analytics/market`, `analytics/ecm`, `analytics/ig_dcm`,
or `analytics/leveraged_finance` directories. Their README representation is an
intended organization, not existing implementation. Keep methodology here;
place future reusable Python under `src/european_capital_markets/analytics/`.
Create product-specific directories only when a concrete calculation needs them.

## Canonical facts and derived outputs

Canonical storage remains the source of stable identities, disclosed levels,
source evidence, explicit missingness, and governed canonical calculations such
as FX conversion. A market change is a downstream `CALCULATED` result, not a
new sourced market level. It receives no fabricated `OBS` ID.

Estimates, assumptions, and judgments cannot enter the initial calculation as
observed levels. Commentary, market favorability scores, issuer recommendations,
and execution judgments remain outside numerical results.

Initially return immutable in-memory records. Do not persist analytics, add a
migration, allocate release IDs, or write calculations back through the append
writer. Durable output/release contracts need a separate design increment.

## Dates, snapshots, and reproducibility

Every request supplies a canonical series ID, the governed field, and exact
`prior_date` and `current_date`, with `prior_date < current_date`. Dates are
calendar dates, not instants. Reject datetimes at a date-only API boundary;
do not truncate caller timestamps or use the machine's current date.

Both endpoints use the same validated frozen dataset. No hidden query, provider
retrieval, clock read, reference-catalog reload, or second database snapshot may
occur during selection or calculation.

Two temporal questions must remain distinct:

1. **Economic-date calculation over a supplied snapshot:** what do these exact
   retained records report for the requested dates? This is the initial mode.
2. **Known-at historical reconstruction:** which records and verification state
   were actually available at a historical instant? This is not supported by the
   current canonical model and must fail as an unsupported request, not degrade
   silently into mode 1.

A repeatable-read transaction guarantees coherence during acquisition; it is
not a durable historical snapshot. An observation-ID list or digest alone also
cannot reconstruct content if records are later changed. Repeatability in this
increment means equal retained input content plus equal policy/methodology gives
equal output. Long-term replay requires retaining the full input bundle and
versioned methodology; durable storage of that bundle is a later prerequisite
for released outputs. No historical backtest or no-look-ahead claim is made.

Do not infer availability from source access/publication date, `verified_at`,
run creation time, sequence allocation, or canonical ID order. Corrections
appended for an old economic date enter a newly acquired snapshot; they never
silently change an already retained input bundle or result.

## Exact-date selection policy v1

The first selector is pure and operates on a validated `CanonicalDataset`.
Validation of the whole dataset remains authoritative; a convenience slice
must not bypass subject, lineage, field, or cross-record consistency checks.

For one series, field, and requested date:

1. Require the canonical series and exactly one compatible typed definition.
   The governed field and unit must match the series family. Reference labels
   or current provider mappings cannot override persisted economic identity.
2. Inspect all observations for that exact subject/field/date, preserving every
   candidate ID. Older/newer records are outside the candidate set and never
   fill the endpoint. No business-day inference or frequency-based carry occurs.
3. A candidate with `CONFLICT` verification blocks selection even if another
   candidate is verified. Any populated candidate whose value class is not
   `DISCLOSED` blocks this initial sourced-level selector as unsupported input.
4. Require all populated candidates to contain finite Decimals with compatible
   units. Different numeric values among populated candidates block selection,
   including disagreement from `PENDING` candidates. Source tier and ID ordering
   cannot resolve disagreement. Decimal numeric equality accepts `2.5 == 2.50`;
   exact source representations remain retained for replay.
5. Eligible populated candidates use `PRIMARY_VERIFIED`, `SECONDARY_VERIFIED`,
   or `CROSS_VERIFIED` and retain a timezone-aware `verified_at` plus complete
   evidence/source closure. Preserve each verification state; secondary data
   must never be represented as primary. `PENDING` is never eligible.
6. Equal eligible populated candidates yield one selected numeric value with
   **all** eligible supporting observation IDs. No representative is chosen by
   minimum/maximum ID. Repeated retrievals do not increase numerical weight.
   Equal pending candidates remain visible as excluded candidates.
7. Missing candidates are retained in diagnostics. They do not retract a
   populated candidate or create a zero. A `CONFLICT` candidate still blocks
   under rule 3; otherwise missingness alongside a usable value is not itself
   contradictory. With no eligible populated candidate, return a blocked result.

These are analytical eligibility rules, not changes to canonical validity.
For example, a canonical pending value can be valid and analytically ineligible.

The selection outcome contains the request, policy version, status, selected
value/unit if successful, all eligible supporting IDs, all candidate IDs,
explicit exclusion/block reasons, and original missing states. Candidate and
support sets are serialized in stable ID order solely for deterministic output;
that ordering conveys neither chronology nor source priority.

Expected block reasons include `NO_EXACT_DATE_OBSERVATION`,
`NO_ELIGIBLE_POPULATED_VALUE`, `CONFLICTING_VALUES`, `CONFLICT_STATE`, and
`UNSUPPORTED_VALUE_CLASS`. Invalid identity, missing lineage, malformed scalar,
nonfinite Decimal, or inconsistent field/unit is a validation error and cannot
produce a partial numerical result. Block reason names are frozen by
`SelectionBlockReason`; per-candidate exclusions use `CandidateExclusionReason`.

If multiple block reasons apply, retain the complete reason set in stable
lexical order. There is no arbitrary first-row error determining business
status. Malformed input fails before analytical status evaluation.

### Staleness and calendars

An absent exact-date value is absent even when yesterday's value exists. This
policy makes no implicit claim that every series publishes daily, or that a
weekend date should resolve to Friday. A rate effective from a prior date is
not automatically a same-date published observation. No market-calendar
package or holiday dependency is introduced.

Latest-on-or-before selection, validity intervals, maximum-age tolerances,
calendar-day versus trading-day age, benchmark holidays, timezone/fixing
conventions, and publication lag require separately reviewed policies. They
must be explicit request parameters under versioned semantics before adoption.

## Interfaces and lineage

The staged interfaces use frozen typed records:

| Interface | Input | Output and ownership |
| --- | --- | --- |
| Exact-date selector (implemented) | Validated dataset, series ID, field, date, policy version | Selection outcome including support and exclusion provenance; no I/O |
| Two-date rate change (implemented) | Same dataset, two dates, compatible rate/yield series, fixed methodology version | Calculated Decimal or explicit blocked outcome; preserves both selections |
| PostgreSQL composition adapter (implemented) | Engine plus analytical request | Acquire one full canonical dataset through the existing reader; invoke pure analytics |

Do not expose unvalidated constructors as proof of coherent dataset validation.
The public function validates its input aggregate, or consumes an explicitly
validated wrapper whose only construction path performs that validation.

A calculated result retains series identity and full typed definition, field,
ordered endpoint roles/dates, endpoint selections, original input values/units,
all supporting OBS IDs, and complete OBS -> EVD -> SRC record closure. It also
retains excluded/conflicting candidate records needed to explain why selection
succeeded or blocked. Preserve any source tuple ordering inside records; stable
outer record ordering must not discard that structure.

The result identifies the selection policy and calculation methodology versions,
Decimal policy, output unit, and `CALCULATED` value class. Calculation success
is not a new canonical verification state or release approval. A blocked result
has no numerical value; one endpoint's success cannot conceal the other's
failure. Retaining only a union of IDs loses endpoint roles and is insufficient.

Any future snapshot digest must use a versioned lossless encoding of record
types, dates/timestamps, Decimal strings, enums, and lineage ordering. It must
cover selection candidates and the economic definition, not merely chosen
values. A digest is an integrity aid, not a new canonical ID or an archived
snapshot. Do not add a digest API until its serialization contract is tested.

## Initial calculation and numerical policy

For `POLICY_RATE`, `GOVERNMENT_YIELD`, and `SWAP_RATE` with canonical `PERCENT`:

`change_bps = (current_percent - prior_percent) * Decimal('100')`

Example: `2.40 -> 2.55` produces `+15` basis points. Zero changes and negative
levels remain valid where permitted by the canonical family; no division is
needed. Both endpoints must describe the same canonical economic series.

Use an explicit local Decimal context with precision 38 and `ROUND_HALF_EVEN`.
Do not inherit precision, rounding, exponent limits, or traps from caller
state: define a complete fresh context. Trap invalid operations, division by
zero, overflow, underflow, and inexact arithmetic for the initial subtraction/
scaling calculation. Inputs and outputs must be finite. If the exact result
cannot be represented under this policy, fail explicitly rather than silently
round. Ambient precision/rounding/traps must not change the answer.

Do not quantize results for presentation. Signed zero may be normalized to
`Decimal('0')` at the derived-result boundary; preserve original input values.
Output representation and serialization must be deterministic, including
numerically equal supporting inputs with different scales. Specify a canonical
result encoding during implementation, without using ambient-context
`Decimal.normalize()` on canonical inputs.

Subsequent methods require their own versions and tests:

| Method | Formula | Additional decisions before implementation |
| --- | --- | --- |
| Credit-spread change | current_bps - prior_bps | Preserve spread measure/benchmark identity and BASIS_POINTS units |
| Volatility change | current_level - prior_level | Output INDEX_POINTS, not percentage or a generic volatility score |
| Equity-index return | ((current_level / prior_level) - 1) * 100 | Require positive prior level; document division rounding and index variant; price return is not total return |
| Curve slope/change | Explicit tenor levels and differences | Compatible benchmark/conventions, same endpoint dates, complete lineage for every leg |

FX returns and cross-currency transaction analytics are not part of the first
rate-change method. Existing FX conversion remains a canonical governed
calculation with its own explicit two-input contract and precision policy.

## Transaction analytics sequencing

Transaction counts and issuance volumes follow market selection/calculation
contracts rather than shipping as an ungoverned dashboard query.

Before implementing them, freeze product scope, universe/coverage, date basis
(announcement/pricing/settlement), lifecycle eligibility as of that date,
transaction versus instrument granularity, amendment treatment, and treatment
of cancelled, withdrawn, postponed, and failed events. Preserve those records;
activity metrics can classify them explicitly instead of deleting them.

Issuance volume additionally requires native versus reporting-currency policy,
complete tranche coverage, exact issue-size input selection, explicit FX input
lineage where necessary, and prevention of transaction/tranche double counting.
An empty observed universe is not proof that market-wide issuance was zero.
Do not infer market closure from missing coverage.

## Dependency path and test matrix

The initial path is controlled economic identity -> validated canonical snapshot
-> exact-date candidates -> disagreement and eligibility -> two selections ->
versioned arithmetic -> result with full material lineage. Database acquisition
is a separate integration seam; release persistence remains deferred.

The following matrix defines acceptance coverage across the staged delivery.
Selector/domain and pure calculation cases are now exercised by the
implementation tests below. Database-adapter rows are covered by real
PostgreSQL composition tests. Durable analytical replay remains a future
acceptance requirement, not implemented coverage.

| Component | Dependency | Contract | Failure mode | Expected behavior | Test level | Real or mocked |
| --- | --- | --- | --- | --- | --- | --- |
| Selector | Canonical domain validator | Identity/field/unit/lineage coherence | Wrong family, missing subject/evidence/source, duplicate IDs | Validation error before value selection | Contract/composition | Real domain records/validators |
| Selector | Candidate set | Order-independent exact-date consensus | Reordering, equal repeated retrievals, differing Decimal scales | Same value and complete stable support set | Unit/property cases | Real frozen records |
| Selector | Verification and missingness | Explicit eligibility without hidden fallback | Pending-only, conflict beside verified, unequal pending, all missing, same-date missing beside populated | Block or select under rules above; no zero/tombstone | Unit/contract | Real domain records |
| Selector | Dates | Exact economic dates | Older-only/newer-only input, weekend, datetime supplied, changed local timezone | No carry or date truncation; deterministic blocked result | Unit | Real date/timestamp values |
| Result | Full candidate/evidence closure | Explain every material input and decision | Missing locator/source, candidate lost from diagnostics | Reject incomplete lineage | Composition | Real canonical bundle |
| Calculation | Two successful selections | Both endpoints required, same series | One endpoint blocked, reversed/equal dates, cross-series mix | No numerical result or request validation error | Unit/composition | Real selector and calculation |
| Calculation | Decimal runtime | Context-independent exact additive arithmetic | Low ambient precision, alternate traps/rounding, nonfinite input, exponent/precision limit, signed zero | Same exact answer or documented arithmetic failure | Unit | Real Decimal implementation |
| Database adapter | Reader and PostgreSQL | One coherent full snapshot | Concurrent append during multi-table reconstruction | Pre-commit or post-commit coherent view; no torn OBS/EVD/SRC graph | PostgreSQL integration | Real PostgreSQL, separate writer connection |
| Database adapter | Persistence/reader/selector/calculation | Lossless composed calculation | Decimal scale, repeated equal observations, appended correction | Same frozen result; new snapshot blocks changed-value conflict | PostgreSQL composition | Real database and domain; synthetic fixtures |
| Acquisition | Database availability | Failed acquisition yields no analytical value | Connection failure or reconstruction exception | Propagate failure; no partial/cached result | Adapter tests; real DB where transaction behavior matters | Controlled failures; real transaction tests |
| Replay, later | Retained full input bundle and methodology | Historical output never silently rewritten | New source correction or new policy version | Old bundle repeats; new bundle/version is a distinct computation | System/composition | Real retained records; durable storage only when implemented |

No provider network is required. No runtime/package versions, direct or
transitive dependencies, lockfile, database schema, or migrations change here.
Do not add calendar, dataframe, numerical, or workflow frameworks for this scope.
Use current Python 3.12 and locked dependencies; `uv lock --check` remains a gate.

## Delivery increments and acceptance gates

1. **Exact-date selection contract and implementation (implemented).** Frozen
   outcome/request types, deterministic consensus and diagnostics, complete candidate lineage,
   and domain-composed tests. No calculation, database adapter, or persistence.
2. **Two-date rate/yield changes (implemented).** Pure composition using the
   selector, complete Decimal context, explicit blocked outcomes and lineage; test both boundaries
   together. No live provider or canonical write.
3. **Snapshot-reader composition (implemented).** Compose the existing full
   reader and pure analytics. Real PostgreSQL concurrent append and round-trip
   tests prove the new seam. Avoid premature filtered-query infrastructure.
4. **Broader market and transaction methods.** Add only reviewed formulas and
   universe/coverage contracts with corresponding awkward-case tests.
5. **Durable analytical bundles and releases.** Freeze serialization, historical
   retention, methodology identity, correction/supersession, and release approval
   before claiming persistent reproducibility or emitting released outputs.

For the pure implementation increments, concurrency is deterministic access to
immutable records, not a new database-locking contract. Migration/recovery tests
are not invented for functions that perform no writes. Existing database CI
continues to guard the baseline. Escalate to real PostgreSQL when the reader is
composed, and to real storage/restart tests when durable bundles are introduced.

Remaining risks are explicit: production inputs still need governed verification;
exact-date coverage may be sparse; historical knowledge-time reconstruction is
unavailable; conflicting corrections block until governed resolution exists;
in-memory results are not durable releases. These limits are acceptable for the
first pure analytical boundary, and prohibit stronger production/release claims.

## Implemented Exact-Date Selector

The executable boundary is `european_capital_markets.analytics`:

```python
from datetime import date
from european_capital_markets.analytics import (
    ExactDateMarketRequest,
    select_market_observation,
)

result = select_market_observation(
    dataset,
    ExactDateMarketRequest(
        market_series_id="MKS000000001",
        field_name="market_series.rate_percent",
        as_of_date=date(2026, 10, 16),
    ),
)
```

`dataset` is a caller-supplied `CanonicalDataset`; selection performs no I/O.
`ExactDateMarketRequest.policy_version` defaults to `market-exact-date-v1`.
Unknown versions are rejected. There is no `known_at` parameter or historical
knowledge-time mode. Genuine date objects are required; datetimes are rejected.

`MarketSelectionResult` is a frozen in-memory outcome with the request, canonical
series/definition, `SELECTED` or `BLOCKED` status, optional value/unit, sorted
block reasons, and candidate decisions. Each decision retains its original
`ObservationRecord` and exclusion reasons. Missing-state and verification
metadata remain on that exact record. It retains:

- `candidate_observation_ids`: every exact-date candidate, sorted by ID;
- `eligible_observation_ids`: candidates individually eligible under the policy,
  even if another candidate blocks the overall outcome;
- `supporting_observation_ids`: all eligible support on success, empty on block;
- `lineage_observations`: candidates plus transitive input observations;
- `evidence` and `sources`: complete provenance closure for those observations.

A blocked outcome always has `value=None` and `unit=None`. With no candidates,
both `NO_EXACT_DATE_OBSERVATION` and `NO_ELIGIBLE_POPULATED_VALUE` are retained.
All block and exclusion reasons have stable lexical ordering. Outer lineage
collections are sorted by canonical ID, preserving original evidence/input
ordering inside each record. ID sorting is presentation only.

Successful values remove trailing coefficient zeros by Decimal tuple
reconstruction, without arithmetic or ambient-context normalization. Signed
zero becomes `Decimal('0')`. Original candidate Decimal scale and sign remain
unchanged. This makes selected-value representation independent of which equal
source value was encountered first, without choosing a preferred observation.

The analytical boundary requires tuple dataset collections and observation
reference tuples, genuine observation taxonomy enums, date-only economic dates,
and finite Decimal values throughout the supplied snapshot. The full canonical
dataset validator then checks composition before filtering candidates. Invalid
unrelated records therefore cannot be hidden by an otherwise successful request.
`TypeError`/`ValueError` indicate malformed or unsupported input; business
ineligibility and disagreement produce `BLOCKED`, not fabricated values.

The family-to-field mapping is exposed by the domain helper
`expected_market_observation_field`; the existing market validator and selector
share it. Analytics does not maintain a second economic-field mapping.

### Executed Selection Boundary Coverage

`tests/unit/test_market_selection.py` exercises the real domain validators,
reference-catalog loader with synthetic observations, ingestion handoff,
selection, and lineage assembly. No validator, provider, or database mocks are
used in these new tests. Catalog reads occur only in test setup; selection
itself does not load the catalog.

Coverage includes all seven families, missing/incorrect economic identity and
units, incomplete source/evidence graphs, duplicate IDs, equal repeated
retrievals, same-date disagreement including pending values, all canonical
missing states, all eligible verification states, unsupported value classes,
input ordering permutations, exact dates/weekends, datetime rejection,
nonfinite Decimal values, restrictive Decimal contexts, transitive input
closure, many-to-many evidence, and unchanged historical input bundles after
an appended correction. A real ingestion handoff remains `PENDING` and is
blocked. A mixed market/transaction dataset also exercises exact aggregate
validation before selection under restrictive caller precision/traps/exponents.

The latter seam exposed pre-existing context-dependent canonical arithmetic.
Aggregate validation now compares exact rational equivalents of finite Decimal
amounts, and canonical FX conversion uses its complete private context. Their
regression coverage is in `test_consistency.py` and `test_fx_conversion.py`.
These corrections preserve the canonical accounting and FX methodology rather
than bypassing validation in the selector.

Database transaction/concurrency, crash recovery, and migration downgrade/
re-upgrade behavior continue to run in existing PostgreSQL CI. No new database
adapter, storage boundary, or migration is introduced by selection, so those
checks protect the baseline rather than proving an unimplemented analytics
adapter. Pure two-date rate/yield composition is documented below.

## Implemented Two-Date Rate/Yield Changes

`calculate_rate_change(dataset, RateChangeRequest(...))` composes the public
exact-date selector twice over the same caller-supplied canonical dataset.
Neither caller-created endpoint selections nor independently acquired snapshots
are accepted as inputs. Full canonical validation remains in the selector;
there is no unvalidated fast path or cached query. The function performs no I/O.

The supported families are `POLICY_RATE`, `GOVERNMENT_YIELD`, and `SWAP_RATE`.
Their governed fields must carry percentage-point levels; the output is basis
points. Other families and incompatible requested fields are validation errors,
not alternative formulas selected by a display unit.

```python
from datetime import date
from european_capital_markets.analytics import RateChangeRequest, calculate_rate_change

result = calculate_rate_change(
    dataset,
    RateChangeRequest(
        market_series_id="MKS000000001",
        field_name="market_series.rate_percent",
        prior_date=date(2026, 10, 15),
        current_date=date(2026, 10, 16),
    ),
)
```

Request defaults identify `market-rate-change-v1` and `market-exact-date-v1`.
Unknown versions are rejected; economic dates must be genuine dates with
`prior_date < current_date`. There is no knowledge-time cutoff, implicit clock,
calendar adjustment, carry-forward, interpolation, or provider fallback.

### Outcome and Lineage Contract

The frozen `RateChangeResult` retains `request`, `prior`, and `current`.
The latter two are complete `MarketSelectionResult` records with their own
endpoint roles, exact source representations, supporting IDs, excluded or
conflicting candidates, and transitive observation/evidence/source closure.
This preserves mixed verification states without promoting them or choosing one
source as the representative. Both endpoint decisions are retained even when
the prior selection blocks.

Successful outcomes have status `CALCULATED`, a Decimal `value`,
`value_class=CALCULATED`, and empty block reasons. Their convenience
`input_observation_ids` concatenate all prior support followed by all current
support. ID order inside an endpoint has no chronological or quality meaning.
The nested endpoint records remain authoritative for roles and provenance.

A `BLOCKED` outcome has `value=None`, `value_class=None`, and no claimed
`input_observation_ids`; the endpoint selections still retain every candidate
and eligible supporting ID. Block reasons are sorted lexically:

- `PRIOR_SELECTION_BLOCKED` and/or `CURRENT_SELECTION_BLOCKED`: the corresponding
  endpoint retains the detailed selection reasons and original missing states;
- `ARITHMETIC_NOT_REPRESENTABLE`: both endpoints selected successfully but the
  calculation failed the numerical policy. `arithmetic_signals` retains the
  sorted names of Decimal signals raised by the private calculation context.

The result's `unit=BASIS_POINTS` identifies the requested metric even when
blocked; it is not a fabricated value. `decimal_policy_ref` is
`market-rate-change-decimal-38-v1`. No canonical observation or release ID is
allocated; success is neither source verification nor release approval.

### Numerical Policy v1

The formula is `(current_percent - prior_percent) * Decimal('100')`.
Both operations run in one fresh context with precision 38, `ROUND_HALF_EVEN`,
`Emin=-999999`, `Emax=999999`, `clamp=0`, and initially clear flags. Traps are
explicitly enabled for `InvalidOperation`, `DivisionByZero`, `Overflow`,
`Underflow`, and `Inexact`. Caller context and mutable `decimal.DefaultContext`
do not supply any setting.

Subtraction and scaling must each be exact within this context. A representable
final value does not rescue an inexact or unrepresentable intermediate step.
`Rounded` without `Inexact` can merely discard coefficient zeros and is allowed;
exact subnormal results are allowed. Underflow with information loss is blocked.
No arithmetic failure is silently rounded into an apparently valid change.
Malformed canonical inputs remain validation errors, not arithmetic blocks.

Result scale and signed zero use the same context-independent tuple
canonicalization as selection. Original endpoint values retain their scale and
sign. No presentation quantization, binary floating point, or caller precision
participates. A high-precision pair can legitimately cancel to an exactly
representable small change; input digit count alone is not an eligibility rule.

### Dependency and Test Completion

`tests/unit/test_rate_changes.py` composes real canonical records, reference
catalog parsing with synthetic observations, full domain validation, both real
selectors, and real Decimal arithmetic. It does not mock a dependency. The
shared internal Decimal representation helper is also regression-checked by the
existing selection tests after extraction for this second consumer.

The dependency matrix above is exercised for the pure calculation rows:

- three supported families, positive/negative/zero changes, and percentage-point
  versus basis-point semantics;
- one or both endpoints pending, missing, or conflicting, preserving diagnostics
  rather than returning a partial value;
- repeated equal observations, mixed verified states, original Decimal scales,
  all supporting IDs, evidence, and input-order permutations;
- separate series identities cannot fill one another's missing endpoint;
- precision limits, exact cancellation beyond 38 input digits, upper exponent
  boundaries, exact subnormals, underflow, overflow, and signed zero;
- restrictive caller precision, rounding, traps, exponent limits, and pre-existing
  flags leave success/failure and caller state unchanged;
- malformed source/evidence composition, date errors, unsupported families,
  unknown method/selection versions, and rejected knowledge-time parameters;
- a later correction blocks a new snapshot without changing an earlier result
  or the retained input dataset.

The pure calculation increment introduced no database, filesystem publication,
worker, schema, migration, release store, external dependency, or lockfile change.
PostgreSQL CI guarded the persistence baseline at that step. The adapter below
adds real snapshot-to-calculation composition coverage, including concurrent
append and exact Decimal/lineage reconstruction. Durable analytical replay and
release versioning remain later scope. Production inputs still require governed
verification; ingestion's `PENDING` values remain blocked.

## PostgreSQL Snapshot Composition

`calculate_rate_change_from_database(engine, request)` is exported from
`european_capital_markets.persistence`. The adapter composes the existing
`load_canonical_dataset` reader and pure `calculate_rate_change`; it adds no
query framework, filtered reader, migration, or persisted analytical result.
The pure `analytics` package continues to depend only on domain records and
standard-library arithmetic; database I/O stays in the persistence adapter.

```python
from european_capital_markets.persistence import calculate_rate_change_from_database

result = calculate_rate_change_from_database(engine, request)
```

The adapter rejects an invalid request type before opening the database. For a
valid request it calls the canonical reader exactly once. That reader owns one
read-only `REPEATABLE READ` transaction spanning all canonical tables and their
lineage junctions, reconstructs the complete dataset, and validates it. Only
after the transaction closes does pure selection/calculation consume those
retained records. The two endpoints cannot acquire independent snapshots.

A concurrent append committed after the reader's snapshot is established is
excluded from that in-flight reconstruction. A later invocation acquires a new
snapshot and may gain equal supporting observations or block on a new conflict.
This is coherent current acquisition, not a historical knowledge-time query or
an archived snapshot. An old in-memory result does not change when a subsequent
call sees new records. Long-term replay still requires durable analytical
bundles and governed methodology/release retention.

### Failures and Recovery Boundary

Database acquisition, connection loss, query execution, reconstruction, and
canonical validation failures propagate to the caller. They cannot become a
normal `BLOCKED` analytical result, a cached value, or a partially populated
calculation. There is no automatic retry. A caller can make a new invocation
after the dependency is available; it then obtains a new snapshot.

Missingness, pending verification, conflicts, and arithmetic representability
continue to use the existing typed `BLOCKED` outcomes after successful canonical
acquisition. The adapter changes neither eligibility nor numerical policy.

Engine configuration and connection-pool health remain caller-owned. The tests
use SQLAlchemy's real pool with pre-ping; the adapter does not add health checks,
worker ownership, retry/backoff, provider access, or background recovery.

### Dependency Verification

| Component | Dependency | Contract | Failure mode | Expected behavior | Test level | Real or mocked |
| --- | --- | --- | --- | --- | --- | --- |
| Adapter | Canonical reader | Exactly one full snapshot before pure calculation | Independent endpoint acquisitions | One read-only repeatable-read transaction for the adapter invocation | PostgreSQL composition/concurrency | Real database/reader |
| Calculation input | Writer, Numeric storage, reader, lineage ordinals | Preserve Decimal values, scales, verification, and source/evidence ordering | Representation or graph loss across persistence | Same result as the supplied canonical records; exact retained values and evidence tuples | PostgreSQL round trip | Real writer/database/reader/analytics |
| Snapshot reconstruction | Concurrent append writer and PostgreSQL MVCC | No torn evidence/observation graph | Append commits between relation and observation reads | In-flight result keeps old coherent state; next acquisition sees the complete append | PostgreSQL concurrency | Real independent connections |
| Adapter acquisition | PostgreSQL session and connection pool | Dependency failure is not analytical missingness | Reader backend connection terminated | Propagate DBAPI error; later explicit invocation can acquire successfully | PostgreSQL fault/recovery | Real backend termination |
| Reconstructed canonical state | Reader and domain validators | Structural storage success is not semantic validity | Persisted unit incompatible with policy-rate field | Validation error; no calculated/blocked value returned | PostgreSQL composition | Real SQL fault injection and domain validators |
| Adapter error routing | Reader/caller boundary | Reject bad request before I/O; no fallback after reader error | Invalid request, unavailable or malformed dependency | Preserve original exception; forbid downstream calculation | Unit | Mocked reader/calculator for routing only |

`tests/integration/test_rate_change_snapshot.py` covers this composition using
synthetic records in real PostgreSQL. Its concurrent test pauses reconstruction
after the observation-evidence relation query, commits a public append writer
on another connection, and then resumes. It checks actual server isolation and
read-only settings and counts exactly one reader transaction. Equal and
conflicting appends test both later outcomes. The pause occurs where independent
READ COMMITTED queries could combine an old evidence map with new observations;
no component or SQL response is replaced.

Coordination uses SQLAlchemy events and bounded thread events/futures, not
sleeps. Connection-loss injection terminates only the test's own paused reader
backend and waits for termination before resuming it. Invalid-unit injection
changes only synthetic test rows outside the canonical writer to demonstrate
that reconstructed state must still pass domain validation. A subsequent
explicit call after repair succeeds; this is not an adapter retry policy.

Fixtures delete only their synthetic market-series records, lineage rows, and
explicit source-ID namespace. They do not truncate unrelated canonical tables
or touch ingestion-run state. Connections, listeners, and threads are cleaned
up before fixture teardown. Real database execution is required: unit stubs
prove only call routing and forbidden operations, not MVCC or recovery.

No runtime dependency/version, lockfile, canonical writer/reader API, transaction
isolation policy, schema, migration, or CI workflow change is introduced. The
existing PostgreSQL CI job discovers these tests and reruns them after the
migration downgrade/re-upgrade cycle. The full-dataset reader's memory and
query cost remain unchanged; this is not yet a scaled analytical query service.

The next justified increment is a design review of durable analytical bundles:
lossless serialization, complete input/candidate retention, methodology identity,
versioning, correction relationships, and release boundaries. Freeze those
contracts before implementing archival writes or claiming durable historical
reproducibility. Broader market/transaction formulas remain separately reviewed
work rather than an automatic consequence of adding this adapter.

## Durable Bundle Contract Review

The [durable analytical bundle contract](analytical_bundles.md) now specifies
full acquired-dataset retention, strict lossless encoding, execution identity,
complete result replay, and correction/release boundaries. This is design only;
no archive or codec is implemented. The next increment is a pure codec and
replay verifier before choosing and testing an archival backend.
