"""Real domain/selection composition: no database, provider, or validator mocks."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from itertools import permutations

import pytest

from european_capital_markets.analytics import (
    CandidateExclusionReason as Exclusion,
)
from european_capital_markets.analytics import (
    ExactDateMarketRequest,
    MarketSelectionStatus,
    select_market_observation,
)
from european_capital_markets.analytics import (
    SelectionBlockReason as Block,
)
from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    FXReferenceRateDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    expected_market_observation_field,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MarketSeriesType,
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)

DAY = date(2026, 10, 16)
VERIFIED_AT = datetime(2026, 10, 16, 16, tzinfo=UTC)
REQUEST = ExactDateMarketRequest("MKS000000001", "market_series.rate_percent", DAY)
VERIFIED = (
    VerificationState.PRIMARY_VERIFIED,
    VerificationState.SECONDARY_VERIFIED,
    VerificationState.CROSS_VERIFIED,
)


def _observation(number=1, value="2.50", state=VerificationState.PRIMARY_VERIFIED):
    return ObservationRecord(
        observation_id=f"OBS{number:09}",
        subject_type=EntityType.MARKET_SERIES,
        subject_id=REQUEST.market_series_id,
        field_name=REQUEST.field_name,
        as_of_date=DAY,
        verification_state=state,
        verified_at=VERIFIED_AT if state in VERIFIED else None,
        value=Decimal(value),
        value_class=ValueClass.DISCLOSED,
        unit="PERCENT",
        evidence_ids=(f"EVD{number:09}",),
    )


def _missing(number, missing_state):
    state = {
        MissingDataState.UNAVAILABLE: VerificationState.UNAVAILABLE,
        MissingDataState.PENDING_VERIFICATION: VerificationState.PENDING,
    }.get(missing_state, VerificationState.PENDING)
    return replace(
        _observation(number),
        value=None,
        value_class=None,
        missing_state=missing_state,
        verification_state=state,
        verified_at=None,
        unit=None,
    )


def _dataset(*observations):
    evidence_ids = sorted({e for o in observations for e in o.evidence_ids})
    return CanonicalDataset(
        market_series=(
            MarketSeriesRecord(
                REQUEST.market_series_id,
                MarketSeriesType.POLICY_RATE,
            ),
        ),
        policy_rates=(
            PolicyRateDefinitionRecord(
                REQUEST.market_series_id,
                "Synthetic authority",
                "Euro Area",
                "EUR",
                "Synthetic policy rate",
                "test/policy-rate-v1",
            ),
        ),
        observations=tuple(observations),
        evidence=tuple(
            EvidenceRecord(e, "SRC000000001", f"row/{e}") for e in evidence_ids
        ),
        sources=(
            SourceRecord(
                "SRC000000001",
                SourceTier.OFFICIAL_INSTITUTION,
                SourceType.CENTRAL_BANK_PUBLICATION,
                "Synthetic authority",
                "Fixture",
                DAY,
                url="https://example.invalid/fixture",
            ),
        ),
    )


def _select(*observations):
    return select_market_observation(_dataset(*observations), REQUEST)


@pytest.mark.parametrize("state", VERIFIED)
def test_verified_disclosed_levels_preserve_verification_and_lineage(state):
    observation = _observation(state=state)
    result = _select(observation)
    assert result.status is MarketSelectionStatus.SELECTED
    assert result.value == Decimal("2.5")
    assert str(result.value) == "2.5"
    assert result.unit == "PERCENT"
    assert result.supporting_observation_ids == (observation.observation_id,)
    assert result.lineage_observations == (observation,)
    assert result.candidate_decisions[0].observation.verification_state is state
    assert result.evidence[0].evidence_id == observation.evidence_ids[0]
    assert result.sources[0].source_id == result.evidence[0].source_id
    assert result.block_reasons == ()
    with pytest.raises(FrozenInstanceError):
        result.value = Decimal("9")


def test_equal_candidates_preserve_all_support_and_excluded_pending():
    observations = (
        _observation(8, "2.50"),
        _observation(2, "2.500", VerificationState.SECONDARY_VERIFIED),
        _observation(5, "2.5", VerificationState.PENDING),
    )
    baseline = _select(*observations)
    for order in permutations(observations):
        dataset = _dataset(*order)
        dataset = replace(dataset, evidence=tuple(reversed(dataset.evidence)))
        assert select_market_observation(dataset, REQUEST) == baseline
    assert baseline.supporting_observation_ids == ("OBS000000002", "OBS000000008")
    assert baseline.candidate_observation_ids == (
        "OBS000000002",
        "OBS000000005",
        "OBS000000008",
    )
    assert baseline.candidate_decisions[1].exclusion_reasons == (Exclusion.UNVERIFIED,)
    assert len(baseline.evidence) == 3
    assert str(baseline.value) == "2.5"
    assert baseline.lineage_observations[-1].value.as_tuple().exponent == -2


@pytest.mark.parametrize("state", (*VERIFIED, VerificationState.PENDING))
def test_any_populated_disagreement_blocks_without_source_or_id_priority(state):
    result = _select(_observation(9), _observation(1, "2.6", state))
    assert result.status is MarketSelectionStatus.BLOCKED
    assert result.value is None and result.unit is None
    assert result.block_reasons == (Block.CONFLICTING_VALUES,)
    assert result.supporting_observation_ids == ()
    assert len(result.lineage_observations) == 2


@pytest.mark.parametrize("populated", [True, False])
def test_conflict_state_blocks_even_beside_verified_agreement(populated):
    other = _observation(2, state=VerificationState.CONFLICT)
    if not populated:
        other = replace(
            other,
            value=None,
            value_class=None,
            missing_state=MissingDataState.NOT_DISCLOSED,
        )
    result = _select(_observation(), other)
    assert result.block_reasons == (Block.CONFLICT_STATE,)
    assert Exclusion.CONFLICT_STATE in result.candidate_decisions[1].exclusion_reasons


def test_all_business_block_reasons_are_retained_in_stable_order():
    assumed = replace(
        _observation(3, "3", VerificationState.PENDING),
        value_class=ValueClass.ASSUMED,
        derivation_ref="test/assumption",
    )
    observations = (
        _observation(1, state=VerificationState.PENDING),
        _observation(2, "4", VerificationState.CONFLICT),
        assumed,
    )
    results = [_select(*order) for order in permutations(observations)]
    assert all(r == results[0] for r in results)
    assert results[0].block_reasons == (
        Block.CONFLICTING_VALUES,
        Block.CONFLICT_STATE,
        Block.NO_ELIGIBLE_POPULATED_VALUE,
        Block.UNSUPPORTED_VALUE_CLASS,
    )


@pytest.mark.parametrize("missing_state", list(MissingDataState))
def test_missingness_is_explicit_and_does_not_retract_usable_value(missing_state):
    missing = _missing(2, missing_state)
    result = _select(_observation(), missing)
    assert result.status is MarketSelectionStatus.SELECTED
    assert result.supporting_observation_ids == ("OBS000000001",)
    assert result.candidate_decisions[1].observation.missing_state is missing_state
    assert Exclusion.MISSING_VALUE in result.candidate_decisions[1].exclusion_reasons
    only_missing = _select(missing)
    assert only_missing.value is None
    assert only_missing.block_reasons == (Block.NO_ELIGIBLE_POPULATED_VALUE,)


def test_pending_is_never_promoted_to_verified():
    result = _select(_observation(state=VerificationState.PENDING))
    assert result.block_reasons == (Block.NO_ELIGIBLE_POPULATED_VALUE,)
    assert result.lineage_observations[0].verified_at is None


@pytest.mark.parametrize("offsets", [(), (-1,), (1,), (-1, 1), (-7, 7)])
def test_exact_date_never_uses_older_or_future_observations(offsets):
    observations = tuple(
        replace(_observation(i + 1), as_of_date=DAY + timedelta(days=n))
        for i, n in enumerate(offsets)
    )
    result = _select(*observations)
    assert result.block_reasons == (
        Block.NO_ELIGIBLE_POPULATED_VALUE,
        Block.NO_EXACT_DATE_OBSERVATION,
    )
    assert result.candidate_observation_ids == ()
    assert result.lineage_observations == result.evidence == result.sources == ()


def test_weekend_request_has_no_business_day_substitution():
    result = select_market_observation(
        _dataset(_observation()),
        replace(REQUEST, as_of_date=DAY + timedelta(days=1)),
    )
    assert Block.NO_EXACT_DATE_OBSERVATION in result.block_reasons


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "-0.000",
        "-0.2500",
        "1E+1000",
        "1E-1000",
        "123456789012345678901234567890123456789.0000",
    ],
)
def test_selection_does_no_rounding_even_under_hostile_decimal_context(value):
    observation = _observation(value=value)
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.Emax = 2
        ctx.Emin = -2
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        ctx.clear_flags()
        result = _select(observation)
        assert not any(ctx.flags.values())
    assert result.value == Decimal(value)
    assert result.lineage_observations[0].value.as_tuple() == Decimal(value).as_tuple()
    if Decimal(value).is_zero():
        assert str(result.value) == "0"


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("trap", [False, True])
def test_nonfinite_dependency_output_fails_before_context_sensitive_comparisons(
    value, trap
):
    with localcontext() as ctx:
        ctx.traps[InvalidOperation] = trap
        with pytest.raises(ValueError, match="finite"):
            _select(_observation(value=value))


@pytest.mark.parametrize(
    "change,match",
    [
        ({"sources": ()}, "source reference"),
        ({"evidence": ()}, "evidence reference"),
        ({"policy_rates": ()}, "exactly one"),
        ({"market_series": ()}, "Unknown observation subject"),
    ],
)
def test_invalid_canonical_composition_is_an_error_not_a_blocked_value(change, match):
    with pytest.raises(ValueError, match=match):
        select_market_observation(replace(_dataset(_observation()), **change), REQUEST)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"unit": "BASIS_POINTS"}, "unit"),
        ({"currency": "EUR"}, "currency"),
        ({"field_name": "market_series.yield_percent"}, "observation field"),
        ({"value": 2.5}, "DECIMAL"),
    ],
)
def test_individually_constructible_but_incompatible_observation_is_rejected(
    change, match
):
    with pytest.raises((TypeError, ValueError), match=match):
        _select(replace(_observation(), **change))


def test_whole_dataset_validation_is_not_bypassed_by_candidate_filtering():
    outside_date = replace(
        _observation(2),
        as_of_date=DAY - timedelta(days=1),
        evidence_ids=("EVD000000999",),
    )
    dataset = replace(
        _dataset(_observation()), observations=(_observation(), outside_date)
    )
    with pytest.raises(ValueError, match="evidence reference"):
        select_market_observation(dataset, REQUEST)
    with pytest.raises(ValueError, match="Duplicate identifier"):
        _select(_observation(), _observation())


@pytest.mark.parametrize(
    "change",
    [
        {"as_of_date": VERIFIED_AT},
        {"as_of_date": datetime(2026, 10, 16)},
        {"as_of_date": "2026-10-16"},
        {"policy_version": "market-exact-date-v2"},
        {"market_series_id": "SRC000000001"},
        {"field_name": ""},
    ],
)
def test_invalid_or_forward_incompatible_request_is_rejected(change):
    with pytest.raises((TypeError, ValueError)):
        replace(REQUEST, **change)


def test_unknown_series_and_mismatched_field_are_errors_without_candidates():
    with pytest.raises(ValueError, match="Unknown market series"):
        select_market_observation(
            _dataset(), replace(REQUEST, market_series_id="MKS000000999")
        )
    with pytest.raises(ValueError, match="Requested field"):
        select_market_observation(
            _dataset(), replace(REQUEST, field_name="market_series.fx_rate")
        )
    with pytest.raises(TypeError, match="MarketSeriesType"):
        expected_market_observation_field("POLICY_RATE")


def test_mutable_snapshots_and_mutable_lineage_are_not_retained():
    with pytest.raises(TypeError, match="tuple"):
        select_market_observation(replace(_dataset(), observations=[]), REQUEST)
    with pytest.raises(TypeError, match="tuples"):
        _select(replace(_observation(), evidence_ids=["EVD000000001"]))


@pytest.mark.parametrize(
    "change",
    [
        {"verification_state": "PENDING", "verified_at": None},
        {
            "value_class": "DISCLOSED",
            "verification_state": VerificationState.PENDING,
            "verified_at": None,
        },
        {"as_of_date": VERIFIED_AT},
    ],
)
def test_malformed_runtime_taxonomy_and_dates_are_errors(change):
    with pytest.raises(TypeError):
        _select(replace(_observation(), **change))


def test_input_lineage_is_transitive_and_preserved_for_unsupported_calculation():
    original = replace(_observation(1), as_of_date=DAY - timedelta(days=2))
    intermediate = replace(
        _observation(2, state=VerificationState.PENDING),
        as_of_date=DAY - timedelta(days=1),
        value_class=ValueClass.CALCULATED,
        input_observation_ids=(original.observation_id,),
        derivation_ref="test/intermediate",
    )
    candidate = replace(
        _observation(3, state=VerificationState.PENDING),
        value_class=ValueClass.CALCULATED,
        input_observation_ids=(intermediate.observation_id,),
        derivation_ref="test/derived",
    )
    result = _select(candidate, intermediate, original)
    assert result.block_reasons == (
        Block.NO_ELIGIBLE_POPULATED_VALUE,
        Block.UNSUPPORTED_VALUE_CLASS,
    )
    assert result.lineage_observations == (original, intermediate, candidate)
    assert len(result.evidence) == 3
    assert result.candidate_observation_ids == (candidate.observation_id,)


def test_evidence_order_many_to_many_support_and_unrelated_sources_are_preserved():
    observation = replace(_observation(), evidence_ids=("EVD000000002", "EVD000000001"))
    other = replace(_observation(2), evidence_ids=("EVD000000002",))
    dataset = _dataset(observation, other)
    second_source = replace(dataset.sources[0], source_id="SRC000000002")
    unused_source = replace(dataset.sources[0], source_id="SRC000000003")
    dataset = replace(
        dataset,
        sources=(unused_source, second_source, *dataset.sources),
        evidence=(
            dataset.evidence[0],
            replace(dataset.evidence[1], source_id=second_source.source_id),
        ),
    )
    result = select_market_observation(dataset, REQUEST)
    assert result.lineage_observations[0].evidence_ids == observation.evidence_ids
    assert len(result.evidence) == 2
    assert tuple(s.source_id for s in result.sources) == (
        "SRC000000001",
        "SRC000000002",
    )
    assert len(result.supporting_observation_ids) == 2


def test_verification_timestamp_is_preserved_not_used_as_historical_knowledge_cutoff():
    timestamp = datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=-5)))
    observation = replace(_observation(), verified_at=timestamp)
    result = _select(observation)
    assert result.status is MarketSelectionStatus.SELECTED
    assert result.lineage_observations[0].verified_at is timestamp
    with pytest.raises(TypeError):
        select_market_observation(_dataset(observation), REQUEST, known_at=VERIFIED_AT)


def test_new_snapshot_correction_blocks_without_rewriting_old_result():
    dataset = _dataset(_observation())
    before = select_market_observation(dataset, REQUEST)
    corrected = _observation(2, "2.75")
    after = _select(_observation(), corrected)
    assert after.block_reasons == (Block.CONFLICTING_VALUES,)
    assert select_market_observation(dataset, REQUEST) == before
    assert before.value == Decimal("2.5")


@pytest.mark.parametrize(
    "family,bucket,field,unit",
    [
        (
            MarketSeriesType.FX_REFERENCE_RATE,
            "fx_reference_rates",
            "market_series.fx_rate",
            None,
        ),
        (
            MarketSeriesType.POLICY_RATE,
            "policy_rates",
            "market_series.rate_percent",
            "PERCENT",
        ),
        (
            MarketSeriesType.GOVERNMENT_YIELD,
            "government_yields",
            "market_series.yield_percent",
            "PERCENT",
        ),
        (
            MarketSeriesType.SWAP_RATE,
            "swap_rates",
            "market_series.rate_percent",
            "PERCENT",
        ),
        (
            MarketSeriesType.CREDIT_SPREAD,
            "credit_spreads",
            "market_series.spread_bps",
            "BASIS_POINTS",
        ),
        (
            MarketSeriesType.EQUITY_INDEX,
            "equity_indices",
            "market_series.index_level",
            "INDEX_POINTS",
        ),
        (
            MarketSeriesType.VOLATILITY_INDEX,
            "volatility_indices",
            "market_series.volatility_level",
            "INDEX_POINTS",
        ),
    ],
)
def test_seven_family_catalog_domain_selection_contract(family, bucket, field, unit):
    from european_capital_markets.reference_data import load_market_series_catalog

    if family is MarketSeriesType.FX_REFERENCE_RATE:
        series = MarketSeriesRecord("MKS000000001", family)
        definition = FXReferenceRateDefinitionRecord(
            series.market_series_id,
            "EUR",
            "GBP",
            "test/reference-rate-v1",
        )
    else:
        catalog = load_market_series_catalog(
            "data/reference/market_series_catalog.json"
        )
        entry = next(
            e for e in catalog.entries if e.market_series.series_type is family
        )
        series, definition = entry.market_series, entry.definition
    observation = replace(
        _observation(), subject_id=series.market_series_id, field_name=field, unit=unit
    )
    updates = {"market_series": (series,), "policy_rates": ()}
    updates[bucket] = (definition,)
    dataset = replace(_dataset(observation), **updates)
    request = ExactDateMarketRequest(series.market_series_id, field, DAY)
    result = select_market_observation(dataset, request)
    assert result.status is MarketSelectionStatus.SELECTED
    assert result.definition == definition
    assert result.value == Decimal("2.5") and result.unit == unit
    assert expected_market_observation_field(family) == field


@pytest.mark.parametrize(
    "value_class", [ValueClass.ASSUMED, ValueClass.ESTIMATED, ValueClass.CALCULATED]
)
def test_nondisclosed_candidates_block_even_when_verified_disclosed_value_exists(
    value_class,
):
    input_value = replace(_observation(3), as_of_date=DAY - timedelta(days=1))
    candidate = replace(
        _observation(2, state=VerificationState.PENDING),
        value_class=value_class,
        derivation_ref="test/non-disclosed",
        input_observation_ids=(input_value.observation_id,),
    )
    result = _select(_observation(), candidate, input_value)
    assert result.block_reasons == (Block.UNSUPPORTED_VALUE_CLASS,)
    assert result.eligible_observation_ids == ("OBS000000001",)
    assert result.supporting_observation_ids == ()
    assert result.candidate_decisions[1].exclusion_reasons == (
        Exclusion.UNSUPPORTED_VALUE_CLASS,
        Exclusion.UNVERIFIED,
    )


def test_observations_from_another_series_do_not_create_false_disagreement():
    other = replace(_observation(2, "9"), subject_id="MKS000000002")
    dataset = _dataset(_observation(), other)
    dataset = replace(
        dataset,
        market_series=(
            *dataset.market_series,
            replace(dataset.market_series[0], market_series_id=other.subject_id),
        ),
        policy_rates=(
            *dataset.policy_rates,
            replace(
                dataset.policy_rates[0],
                market_series_id=other.subject_id,
                rate_name="Different rate",
            ),
        ),
    )
    result = select_market_observation(dataset, REQUEST)
    assert result.value == Decimal("2.5")
    assert result.candidate_observation_ids == ("OBS000000001",)


def test_canonical_ingestion_handoff_remains_pending_at_analytical_boundary():
    from hashlib import sha256

    from european_capital_markets.ingestion.contracts import (
        AllocatedLineageIds,
        NormalizedMarketDatum,
        RawRetrievalArtifact,
        RetrievalSource,
    )
    from european_capital_markets.ingestion.orchestration import (
        build_canonical_market_ingestion_handoff,
    )
    from european_capital_markets.reference_data import load_market_series_catalog

    catalog = load_market_series_catalog("data/reference/market_series_catalog.json")
    entry = next(
        e
        for e in catalog.entries
        if e.market_series.market_series_id == REQUEST.market_series_id
    )
    artifact = RawRetrievalArtifact(
        REQUEST.market_series_id,
        RetrievalSource(
            "Synthetic authority",
            SourceTier.OFFICIAL_INSTITUTION,
            SourceType.CENTRAL_BANK_PUBLICATION,
            "Synthetic retrieval",
            url="https://example.invalid/fixture",
        ),
        VERIFIED_AT,
        "data/raw/synthetic.csv",
        sha256(b"synthetic").hexdigest(),
        9,
    )
    datum = NormalizedMarketDatum(
        REQUEST.market_series_id,
        REQUEST.field_name,
        DAY,
        "row/1",
        value=Decimal("2.5"),
        unit="PERCENT",
    )
    handoff = build_canonical_market_ingestion_handoff(
        entry,
        artifact,
        (datum,),
        (AllocatedLineageIds("SRC000000001", "EVD000000001", "OBS000000001"),),
    )
    result = select_market_observation(handoff.dataset, REQUEST)
    assert result.block_reasons == (Block.NO_ELIGIBLE_POPULATED_VALUE,)
    assert result.lineage_observations == handoff.dataset.observations
    assert result.evidence == handoff.dataset.evidence
    assert result.sources == handoff.dataset.sources


def test_full_snapshot_selection_composes_with_exact_transaction_validation():
    from european_capital_markets.domain.entities import (
        InstrumentRecord,
        IssuerRecord,
        TransactionRecord,
    )
    from european_capital_markets.domain.taxonomy import ProductFamily

    tranche = replace(
        _observation(2),
        subject_type=EntityType.INSTRUMENT,
        subject_id="INS000000001",
        field_name="instrument.issue_size",
        unit=None,
        currency="EUR",
        value=Decimal("100000000000000000000000000000000000000"),
    )
    second = replace(
        tranche,
        observation_id="OBS000000003",
        subject_id="INS000000002",
        value=Decimal("0.01"),
    )
    aggregate = replace(
        _observation(4, state=VerificationState.PENDING),
        subject_type=EntityType.TRANSACTION,
        subject_id="TXN000000001",
        field_name="transaction.aggregate_size",
        value_class=ValueClass.CALCULATED,
        value=Decimal("100000000000000000000000000000000000000.01"),
        unit=None,
        currency="EUR",
        derivation_ref="test/exact-aggregate",
        input_observation_ids=(tranche.observation_id, second.observation_id),
    )
    dataset = replace(
        _dataset(_observation(), tranche, second, aggregate),
        issuers=(IssuerRecord("ISS000000001", "Synthetic issuer"),),
        transactions=(
            TransactionRecord("TXN000000001", "ISS000000001", ProductFamily.IG_DCM),
        ),
        instruments=(
            InstrumentRecord("INS000000001", "TXN000000001"),
            InstrumentRecord("INS000000002", "TXN000000001"),
        ),
    )
    with localcontext() as context:
        context.prec = 1
        context.Emax = 2
        context.Emin = -2
        context.traps[Inexact] = context.traps[Rounded] = True
        result = select_market_observation(dataset, REQUEST)
    assert result.value == Decimal("2.5")
    assert result.candidate_observation_ids == ("OBS000000001",)
    assert result.lineage_observations == (_observation(),)


@pytest.mark.parametrize(
    "dataset,selection_request",
    [
        (object(), REQUEST),
        (_dataset(), object()),
        (replace(_dataset(), observations=(object(),)), REQUEST),
    ],
)
def test_public_boundary_rejects_wrong_runtime_record_types(dataset, selection_request):
    with pytest.raises(TypeError):
        select_market_observation(dataset, selection_request)
