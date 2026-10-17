"""Closed bundle retention/replay contracts with real domain and numerical code."""

import hashlib
import json
import platform
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from european_capital_markets.analytics import _bundle_codec as codec
from european_capital_markets.analytics._bundle_schema import RECORD_FIELDS
from european_capital_markets.analytics.bundles import (
    BundleError,
    ExecutionIdentity,
    ReplayUnavailableError,
    create_rate_change_bundle,
    decode_bundle,
    encode_bundle,
    verify_bundle,
)
from european_capital_markets.analytics.rate_changes import (
    RateChangeRequest,
    RateChangeStatus,
)
from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.entities import (
    InstrumentRecord,
    IssuerRecord,
    TransactionRecord,
)
from european_capital_markets.domain.issuer_identity import IssuerIdentifierRecord
from european_capital_markets.domain.lifecycle import TransactionLifecycleEventRecord
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
)
from european_capital_markets.domain.participations import ParticipationRecord
from european_capital_markets.domain.parties import PartyRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    IdentifierScopeType,
    IssuerIdentifierType,
    MarketSeriesType,
    MissingDataState,
    ParticipantRole,
    PartyType,
    ProductFamily,
    SourceTier,
    SourceType,
    TransactionStatus,
    ValueClass,
    VerificationState,
)
from european_capital_markets.reference_data import load_market_series_catalog

PRIOR = date(2026, 10, 15)
CURRENT = date(2026, 10, 16)
SOURCE_ARTIFACT = b"synthetic retained source artifact"
LOCK_ARTIFACT = b"synthetic retained dependency lock"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def execution(**changes):
    return ExecutionIdentity(
        **{
            "source_commit": "a" * 40,
            "source_artifact_sha256": digest(SOURCE_ARTIFACT),
            "lock_sha256": digest(LOCK_ARTIFACT),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "source_tree_clean": True,
            **changes,
        }
    )


def observation(number, day, value, *, state=VerificationState.PRIMARY_VERIFIED):
    missing = value is None
    return ObservationRecord(
        f"OBS{number:09}",
        EntityType.MARKET_SERIES,
        "MKS000000001",
        "market_series.rate_percent",
        day,
        state,
        verified_at=datetime(2026, 10, 16, 20, tzinfo=UTC)
        if state
        in (
            VerificationState.PRIMARY_VERIFIED,
            VerificationState.SECONDARY_VERIFIED,
            VerificationState.CROSS_VERIFIED,
        )
        else None,
        value=None if missing else Decimal(value),
        value_class=None if missing else ValueClass.DISCLOSED,
        missing_state=MissingDataState.UNAVAILABLE if missing else None,
        unit=None if missing else "PERCENT",
        evidence_ids=("EVD000000002", "EVD000000001"),
    )


def dataset(*observations):
    return CanonicalDataset(
        market_series=(
            MarketSeriesRecord(
                "MKS000000001", MarketSeriesType.POLICY_RATE, "Synthetic rate"
            ),
        ),
        policy_rates=(
            PolicyRateDefinitionRecord(
                "MKS000000001", "Synthetic authority", "EU", "EUR", "Policy", "test/v1"
            ),
        ),
        observations=observations,
        sources=(
            SourceRecord(
                "SRC000000001",
                SourceTier.OFFICIAL_INSTITUTION,
                SourceType.CENTRAL_BANK_PUBLICATION,
                "Synthetic",
                "Rate",
                CURRENT,
                url="https://example.invalid/rate",
                notes='é\nquote: " and slash \\',
            ),
        ),
        evidence=(
            EvidenceRecord("EVD000000001", "SRC000000001", "row 1"),
            EvidenceRecord("EVD000000002", "SRC000000001", "row 2"),
        ),
    )


def bundle(*observations):
    if not observations:
        observations = (
            observation(1, PRIOR, "2.400"),
            observation(2, CURRENT, "2.5500"),
        )
    return create_rate_change_bundle(
        dataset(*observations),
        RateChangeRequest("MKS000000001", "market_series.rate_percent", PRIOR, CURRENT),
        execution(),
    )


def verify(content, **changes):
    return verify_bundle(
        content,
        **{
            "expected_sha256": digest(content),
            "execution": execution(),
            "source_artifact": SOURCE_ARTIFACT,
            "lock_artifact": LOCK_ARTIFACT,
            **changes,
        },
    )


def wire(value):
    # Test mutation helper deliberately uses the documented JSON rules, not codec.
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def test_complete_bundle_replay_retains_representation_and_tuple_order():
    original = bundle()
    content = encode_bundle(original)
    restored = verify(content)
    assert restored == original
    assert encode_bundle(restored) == content
    assert restored.result.value == Decimal("15")
    assert (
        restored.dataset.observations[0].value.as_tuple() == Decimal("2.400").as_tuple()
    )
    assert restored.dataset.observations[1].evidence_ids == (
        "EVD000000002",
        "EVD000000001",
    )
    assert b"\xc3\xa9" in content and not content.endswith(b"\n")


@pytest.mark.parametrize(
    "observations",
    [
        (observation(1, PRIOR, "2.4", state=VerificationState.PENDING),),
        (
            observation(1, PRIOR, None, state=VerificationState.UNAVAILABLE),
            observation(2, CURRENT, None, state=VerificationState.UNAVAILABLE),
        ),
        (
            observation(1, PRIOR, "2.4"),
            observation(2, CURRENT, "2.55"),
            observation(3, CURRENT, "2.65", state=VerificationState.PENDING),
        ),
        (
            observation(1, PRIOR, "2.4"),
            observation(2, CURRENT, "2.55", state=VerificationState.CONFLICT),
        ),
        (observation(1, PRIOR, "1e999999"), observation(2, CURRENT, "0")),
        (observation(1, PRIOR, "1"), observation(2, CURRENT, "1e-100")),
        (
            observation(1, PRIOR, "2.4"),
            replace(
                observation(2, CURRENT, "2.55"),
                value_class=ValueClass.ASSUMED,
                verification_state=VerificationState.PENDING,
                verified_at=None,
                derivation_ref="synthetic/assumption",
            ),
        ),
    ],
)
def test_blocked_outcomes_replay_with_all_diagnostics(observations):
    original = bundle(*observations)
    assert original.result.status is RateChangeStatus.BLOCKED
    assert verify(encode_bundle(original)) == original


@pytest.mark.parametrize(
    "value",
    [
        "",
        "é\u0301",
        True,
        False,
        10**100,
        -12,
        Decimal("-0.000"),
        Decimal("12345678901234567890.12345678901234567890"),
        Decimal("1e-1000036"),
        datetime(2026, 10, 17, tzinfo=timezone(timedelta(hours=-4), "Named offset")),
        PRIOR,
        datetime(2026, 10, 17, 2, 3, 4, 5),
        datetime(2026, 10, 17, 2, 3, 4, 5, tzinfo=UTC, fold=1),
        datetime(
            2026, 10, 17, tzinfo=timezone(timedelta(hours=-4, microseconds=12)), fold=1
        ),
    ],
)
def test_all_scalar_variants_retained_in_unrelated_observation(value):
    original = bundle()
    extra = ObservationRecord(
        "OBS000000099",
        EntityType.ISSUER,
        "ISS000000001",
        "test.scalar",
        CURRENT,
        VerificationState.PENDING,
        value=value,
        value_class=ValueClass.ASSUMED,
        derivation_ref="synthetic/scalar",
    )
    retained = replace(
        original.dataset,
        issuers=(IssuerRecord("ISS000000001", "Synthetic issuer"),),
        observations=(*original.dataset.observations, extra),
    )
    captured = create_rate_change_bundle(retained, original.request, execution())
    restored = verify(encode_bundle(captured)).dataset.observations[-1].value
    assert type(restored) is type(value)
    if isinstance(value, Decimal):
        assert restored.as_tuple() == value.as_tuple()
    elif isinstance(value, datetime):
        assert restored.isoformat() == value.isoformat() and restored.fold == value.fold
        assert restored.tzname() == value.tzname()
    else:
        assert restored == value


def test_all_canonical_record_families_round_trip_as_full_dataset():
    original = bundle()
    catalog = load_market_series_catalog("data/reference/market_series_catalog.json")
    buckets = {
        n: []
        for n in (
            "policy_rates",
            "government_yields",
            "swap_rates",
            "credit_spreads",
            "equity_indices",
            "volatility_indices",
        )
    }
    family_bucket = dict(
        zip(
            (
                MarketSeriesType.POLICY_RATE,
                MarketSeriesType.GOVERNMENT_YIELD,
                MarketSeriesType.SWAP_RATE,
                MarketSeriesType.CREDIT_SPREAD,
                MarketSeriesType.EQUITY_INDEX,
                MarketSeriesType.VOLATILITY_INDEX,
            ),
            buckets,
            strict=True,
        )
    )
    series = []
    for i, family in enumerate(family_bucket, 100):
        entry = next(
            e for e in catalog.entries if e.market_series.series_type is family
        )
        identifier = f"MKS{i:09}"
        series.append(replace(entry.market_series, market_series_id=identifier))
        buckets[family_bucket[family]].append(
            replace(entry.definition, market_series_id=identifier)
        )
    full = replace(
        original.dataset,
        issuers=(IssuerRecord("ISS000000001", "Synthetic issuer"),),
        transactions=(
            TransactionRecord("TXN000000001", "ISS000000001", ProductFamily.IG_DCM),
        ),
        instruments=(InstrumentRecord("INS000000001", "TXN000000001"),),
        issuer_identifiers=(
            IssuerIdentifierRecord(
                "ISS000000001",
                IssuerIdentifierType.TICKER,
                "SYN",
                IdentifierScopeType.TRADING_VENUE,
                ("EVD000000001",),
                "XLON",
            ),
        ),
        parties=(PartyRecord("PTY000000001", PartyType.CORPORATE, "ISS000000001"),),
        participations=(
            ParticipationRecord(
                "PAR000000001",
                "PTY000000001",
                "TXN000000001",
                ParticipantRole.LEGAL_ISSUER,
                ("EVD000000001",),
            ),
        ),
        lifecycle_events=(
            TransactionLifecycleEventRecord(
                "TLE000000001",
                "TXN000000001",
                TransactionStatus.PRICED,
                CURRENT,
                1,
                ("EVD000000001",),
            ),
        ),
        market_series=(
            *original.dataset.market_series,
            *series,
            MarketSeriesRecord("MKS000000200", MarketSeriesType.FX_REFERENCE_RATE),
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                "MKS000000200", "EUR", "GBP", "synthetic/fx"
            ),
        ),
        **{n: (*getattr(original.dataset, n), *v) for n, v in buckets.items()},
    )
    captured = create_rate_change_bundle(full, original.request, execution())
    assert verify(encode_bundle(captured)).dataset == full
    assert all(getattr(full, f.name) for f in fields(full))


def test_empty_dataset_codec_and_closed_record_manifest():
    assert codec.decode(codec.encode(CanonicalDataset())) == CanonicalDataset()
    for record, names in RECORD_FIELDS.items():
        assert tuple(f.name for f in fields(record)) == names


@pytest.mark.parametrize(
    "mutation",
    ["value", "scale", "request", "diagnostic", "candidate", "lineage", "definition"],
)
def test_tampered_stored_result_cannot_pass_replay(mutation):
    original = bundle()
    result = original.result
    if mutation == "value":
        result = replace(result, value=Decimal("16"))
    elif mutation == "scale":
        result = replace(result, value=Decimal("15.0"))
    elif mutation == "request":
        result = replace(
            result, request=replace(result.request, current_date=date(2026, 10, 17))
        )
    elif mutation == "diagnostic":
        result = replace(result, arithmetic_signals=("Inexact",))
    elif mutation == "candidate":
        result = replace(
            result, current=replace(result.current, candidate_decisions=())
        )
    elif mutation == "lineage":
        result = replace(result, current=replace(result.current, evidence=()))
    else:
        result = replace(
            result,
            current=replace(
                result.current,
                definition=replace(result.current.definition, rate_name="Altered"),
            ),
        )
    with pytest.raises(BundleError, match="replay mismatch"):
        verify(encode_bundle(replace(original, result=result)))


def test_deleted_conflicting_candidate_changes_replay_and_old_bytes_stay_unchanged():
    original = bundle(
        observation(1, PRIOR, "2.4"),
        observation(2, CURRENT, "2.55"),
        observation(3, CURRENT, "2.65", state=VerificationState.PENDING),
    )
    content = encode_bundle(original)
    tampered = replace(
        original,
        dataset=replace(
            original.dataset, observations=original.dataset.observations[:2]
        ),
    )
    with pytest.raises(BundleError, match="replay mismatch"):
        verify(encode_bundle(tampered))
    assert verify(content).result.status is RateChangeStatus.BLOCKED


@pytest.mark.parametrize(
    "change",
    [
        {"source_artifact": b"changed"},
        {"lock_artifact": b"changed"},
        {"execution": execution(source_commit="b" * 40)},
    ],
)
def test_missing_or_incompatible_execution_artifact_is_unavailable(change):
    with pytest.raises(ReplayUnavailableError):
        verify(encode_bundle(bundle()), **change)


@pytest.mark.parametrize(
    "change",
    [
        {"source_commit": "abc"},
        {"lock_sha256": "X" * 64},
        {"python_version": "0.0.0"},
        {"source_tree_clean": False},
        {"source_tree_clean": 1},
        {"methodology": "future"},
        {"selection_policy": "future"},
        {"decimal_policy": "future"},
    ],
)
def test_execution_identity_fails_closed(change):
    with pytest.raises(BundleError):
        execution(**change)


@pytest.mark.parametrize(
    "content",
    [
        b'{"t":"null","t":"null"}',
        b'{"t":"null","extra":1}',
        b'{"t":"str","v":1}',
        b'{"t":"int","v":true}',
        b'{"t":"bool","v":1}',
        b'{"t":"float","v":1.5}',
        b'{"t":"str","v":NaN}',
        b'{"t":"null"}\n',
        b'{ "t":"null"}',
        b'\xef\xbb\xbf{"t":"null"}',
        b"\xff",
        b'{"t":"date","v":"20261017"}',
        b'{"d":"01","s":0,"t":"decimal","x":0}',
        b'{"d":"0","s":true,"t":"decimal","x":0}',
        b'{"e":"SourceTier","t":"enum","v":true}',
        b'{"e":"Unknown","t":"enum","v":"A"}',
        b'{"e":"ValueClass","t":"enum","v":"UNKNOWN"}',
        b'{"t":"datetime","v":"2026-10-17T00:00:00+00:00","o":null,"fold":0}',
        b'{"t":"str","v":"\\ud800"}',
        b'{"t":"import os"}',
    ],
)
def test_malformed_or_noncanonical_wire_rejected(content):
    with pytest.raises(BundleError):
        codec.decode(content)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "wrong_type",
        "version",
        "schema",
        "policy",
        "duplicate_id",
        "unit",
    ],
)
def test_bad_envelope_or_canonical_state_rejected(mutation):
    node = json.loads(encode_bundle(bundle()))
    f = node["f"]
    if mutation == "missing":
        del f["result"]["f"]["unit"]
    elif mutation == "extra":
        f["result"]["f"]["value_class"] = {"t": "null"}
    elif mutation == "wrong_type":
        f["dataset"]["f"]["market_series"] = {"t": "str", "v": "bad"}
    elif mutation in ("version", "schema"):
        f["format_version" if mutation == "version" else "record_schema_version"][
            "v"
        ] = "future"
    elif mutation == "policy":
        f["request"]["f"]["methodology_version"]["v"] = "future"
    elif mutation == "duplicate_id":
        records = f["dataset"]["f"]["observations"]["v"]
        records.append(records[0])
    else:
        f["dataset"]["f"]["observations"]["v"][0]["f"]["unit"]["v"] = "INDEX_POINTS"
    content = wire(node)
    with pytest.raises((BundleError, ValueError)):
        decode_bundle(content, expected_sha256=digest(content))


def test_integrity_and_envelope_type_required():
    content = encode_bundle(bundle())
    for bad_digest in ("0" * 64, "ABC", None):
        with pytest.raises(BundleError):
            decode_bundle(content, expected_sha256=bad_digest)
    scalar = b'{"t":"null"}'
    with pytest.raises(BundleError, match="envelope"):
        decode_bundle(scalar, expected_sha256=digest(scalar))


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        1.25,
        Decimal("NaN"),
        Decimal("Infinity"),
        datetime(2026, 10, 17, tzinfo=ZoneInfo("UTC")),
        [1],
        {"a": 1},
        "\ud800",
    ],
)
def test_unsupported_runtime_values_rejected(value):
    with pytest.raises(BundleError):
        codec.encode(value)


def test_context_independence_and_order_sensitive_retention():
    original = bundle()
    expected = encode_bundle(original)
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.Emin, ctx.Emax = -2, 2
        flags = ctx.flags.copy()
        assert encode_bundle(verify(expected)) == expected
        assert ctx.flags == flags
    reordered = create_rate_change_bundle(
        replace(original.dataset, observations=original.dataset.observations[::-1]),
        original.request,
        execution(),
    )
    assert reordered.result == original.result
    assert encode_bundle(reordered) != expected


def test_offline_replay_does_not_load_current_catalog(monkeypatch):
    content = encode_bundle(bundle())

    def forbidden(*args, **kwargs):
        pytest.fail("Replay attempted current reference I/O")

    monkeypatch.setattr(
        "european_capital_markets.reference_data.load_market_series_catalog", forbidden
    )
    assert verify(content).result.value == Decimal("15")


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("-0.00"), b'{"d":"0","s":1,"t":"decimal","x":-2}'),
        (True, b'{"t":"bool","v":true}'),
        (1200, b'{"t":"int","v":1200}'),
        (SourceTier.OFFICIAL_INSTITUTION, b'{"e":"SourceTier","t":"enum","v":2}'),
        (date(2026, 10, 17), b'{"t":"date","v":"2026-10-17"}'),
        (
            datetime(2026, 10, 17, tzinfo=UTC, fold=1),
            b'{"fold":1,"o":0,"t":"datetime","v":"2026-10-17T00:00:00.000000","z":"UTC"}',
        ),
    ],
)
def test_independently_written_golden_scalar_bytes(value, expected):
    assert codec.encode(value) == expected
    assert codec.encode(codec.decode(expected)) == expected


def test_handwritten_empty_dataset_golden():
    expected = Path("tests/fixtures/bundles/empty_dataset_v1.json").read_bytes()
    assert codec.encode(CanonicalDataset()) == expected
    assert (
        digest(expected)
        == "5f2b5a271dda41d819cb68ef6113f9503a2d3ac91d71f5d5ed6f8b42977b679b"
    )


@pytest.mark.parametrize(
    "limit,value",
    [
        ("MAX_STRING", "x" * 11),
        ("MAX_DIGITS", Decimal("12345678901")),
        ("MAX_INTEGER_DIGITS", 12345678901),
        ("MAX_NODES", tuple(range(11))),
        (
            "MAX_RECORDS",
            tuple(IssuerRecord(f"ISS{i:09}", "Synthetic") for i in range(1, 12)),
        ),
    ],
)
def test_limits_reject_on_both_boundaries(monkeypatch, limit, value):
    content = codec.encode(value)
    monkeypatch.setattr(codec, limit, 10)
    with pytest.raises(BundleError):
        codec.encode(value)
    with pytest.raises(BundleError):
        codec.decode(content)


def test_byte_and_preparse_depth_limits(monkeypatch):
    content = codec.encode(bundle())
    monkeypatch.setattr(codec, "MAX_BYTES", len(content) - 1)
    with pytest.raises(BundleError, match="byte limit"):
        codec.decode(content)
    with pytest.raises(BundleError, match="byte limit"):
        encode_bundle(bundle())
    monkeypatch.setattr(codec, "MAX_BYTES", 8 * 1024 * 1024)
    with pytest.raises(BundleError, match="nesting"):
        codec.decode(b"[" * 65 + b"0" + b"]" * 65)
    # A huge raw integer must fail before Python's JSON integer conversion.
    with pytest.raises(BundleError, match="token limit"):
        codec.decode(b'{"t":"int","v":' + b"1" * 257 + b"}")


def test_independent_complete_blocked_bundle_golden():
    golden = Path("tests/fixtures/bundles/blocked_rate_change_v1.json").read_bytes()
    assert digest(golden) == (
        "ba4aa956f759f96844edd17d1a0779c43680b4977cbc0027722fc98698af8016"
    )
    # The fixture freezes CPython 3.12.12. Substitute only the exact patch-version
    # token so CI's supported 3.12 runtime can exercise the identical wire contract.
    content = golden.replace(
        b'"v":"3.12.12"', ('"v":"' + platform.python_version() + '"').encode()
    )
    restored = verify(content)
    assert not restored.dataset.observations
    assert restored.result.status is RateChangeStatus.BLOCKED
    assert encode_bundle(restored) == content


def test_transitive_inputs_and_excluded_equal_candidate_retained():
    prior = observation(1, PRIOR, "2.400")
    current = observation(2, CURRENT, "2.5500")
    pending = replace(
        observation(3, CURRENT, "2.55", state=VerificationState.PENDING),
        input_observation_ids=(prior.observation_id,),
    )
    captured = bundle(prior, current, pending)
    restored = verify(encode_bundle(captured))
    assert restored.result.current.lineage_observations == (prior, current, pending)
    assert restored.result.current.supporting_observation_ids == (
        current.observation_id,
    )
    assert restored.dataset.observations[-1].input_observation_ids == (
        prior.observation_id,
    )
    result = replace(
        captured.result,
        current=replace(
            captured.result.current,
            candidate_decisions=captured.result.current.candidate_decisions[:1],
        ),
    )
    with pytest.raises(BundleError, match="replay mismatch"):
        verify(encode_bundle(replace(captured, result=result)))


def test_exact_scalar_limit_boundaries_and_logical_nesting():
    for value in (
        "x" * codec.MAX_STRING,
        Decimal("1" * codec.MAX_DIGITS),
        10 ** (codec.MAX_INTEGER_DIGITS - 1),
    ):
        assert codec.encode(codec.decode(codec.encode(value))) == codec.encode(value)
    for value in (
        "x" * (codec.MAX_STRING + 1),
        Decimal("1" * (codec.MAX_DIGITS + 1)),
        10**codec.MAX_INTEGER_DIGITS,
    ):
        with pytest.raises(BundleError):
            codec.encode(value)
    nested = None
    for _ in range(33):
        nested = (nested,)
    with pytest.raises(BundleError, match="nesting"):
        codec.encode(nested)


def test_fabricated_runtime_field_types_cannot_be_encoded():
    original = bundle()
    with pytest.raises(BundleError, match="runtime type"):
        encode_bundle(
            replace(
                original,
                dataset=replace(
                    original.dataset, sources=list(original.dataset.sources)
                ),
            )
        )
    with pytest.raises(BundleError, match="runtime type"):
        encode_bundle(replace(original, result=replace(original.result, value=15)))


@pytest.mark.parametrize("trapped", [True, False])
def test_malformed_decimal_exponent_never_changes_caller_context(trapped):
    from decimal import MAX_EMAX, InvalidOperation

    content = wire({"t": "decimal", "s": 0, "d": "11", "x": MAX_EMAX})
    with localcontext() as ctx:
        ctx.clear_flags()
        ctx.traps[InvalidOperation] = trapped
        flags = ctx.flags.copy()
        with pytest.raises(BundleError, match="exponent"):
            codec.decode(content)
        assert ctx.flags == flags
