"""Rate changes composed with real selection, domain validation, and Decimal."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import (
    ROUND_DOWN,
    Decimal,
    Inexact,
    Rounded,
    localcontext,
)
from itertools import permutations

import pytest

from european_capital_markets.analytics import (
    RATE_CHANGE_DECIMAL_POLICY_REF,
    ExactDateMarketRequest,
    MarketSelectionStatus,
    RateChangeBlockReason,
    RateChangeRequest,
    RateChangeStatus,
    SelectionBlockReason,
    calculate_rate_change,
    select_market_observation,
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
from european_capital_markets.reference_data import load_market_series_catalog

PRIOR = date(2026, 10, 15)
CURRENT = date(2026, 10, 16)
VERIFIED_AT = datetime(2026, 10, 16, 20, tzinfo=UTC)
RATE_FAMILIES = (
    MarketSeriesType.POLICY_RATE,
    MarketSeriesType.GOVERNMENT_YIELD,
    MarketSeriesType.SWAP_RATE,
)
# Expected field/unit contracts are explicit test data, not derived by calling
# the domain helper whose mapping is also exercised by this composition.
FAMILY_FIELDS = {
    MarketSeriesType.POLICY_RATE: (
        "policy_rates",
        "market_series.rate_percent",
        "PERCENT",
    ),
    MarketSeriesType.GOVERNMENT_YIELD: (
        "government_yields",
        "market_series.yield_percent",
        "PERCENT",
    ),
    MarketSeriesType.SWAP_RATE: ("swap_rates", "market_series.rate_percent", "PERCENT"),
    MarketSeriesType.CREDIT_SPREAD: (
        "credit_spreads",
        "market_series.spread_bps",
        "BASIS_POINTS",
    ),
    MarketSeriesType.EQUITY_INDEX: (
        "equity_indices",
        "market_series.index_level",
        "INDEX_POINTS",
    ),
    MarketSeriesType.VOLATILITY_INDEX: (
        "volatility_indices",
        "market_series.volatility_level",
        "INDEX_POINTS",
    ),
    MarketSeriesType.FX_REFERENCE_RATE: (
        "fx_reference_rates",
        "market_series.fx_rate",
        None,
    ),
}


def _observation(number, day, value, *, state=VerificationState.PRIMARY_VERIFIED):
    return ObservationRecord(
        observation_id=f"OBS{number:09}",
        subject_type=EntityType.MARKET_SERIES,
        subject_id="MKS000000001",
        field_name="market_series.rate_percent",
        as_of_date=day,
        verification_state=state,
        verified_at=None
        if state in {VerificationState.PENDING, VerificationState.CONFLICT}
        else VERIFIED_AT,
        value=Decimal(value),
        value_class=ValueClass.DISCLOSED,
        unit="PERCENT",
        evidence_ids=(f"EVD{number:09}",),
    )


def _dataset(*observations, family=MarketSeriesType.POLICY_RATE):
    bucket, field, unit = FAMILY_FIELDS[family]
    if family is MarketSeriesType.FX_REFERENCE_RATE:
        series = MarketSeriesRecord("MKS000000001", family)
        definition = FXReferenceRateDefinitionRecord(
            series.market_series_id, "EUR", "GBP", "test/fx"
        )
    else:
        catalog = load_market_series_catalog(
            "data/reference/market_series_catalog.json"
        )
        entry = next(
            e for e in catalog.entries if e.market_series.series_type is family
        )
        series, definition = entry.market_series, entry.definition
    observations = tuple(
        replace(
            o,
            subject_id=series.market_series_id,
            field_name=field,
            unit=unit if o.value is not None else None,
        )
        for o in observations
    )
    evidence_ids = sorted({e for o in observations for e in o.evidence_ids})
    dataset = CanonicalDataset(
        market_series=(series,),
        observations=observations,
        sources=(
            SourceRecord(
                "SRC000000001",
                SourceTier.OFFICIAL_INSTITUTION,
                SourceType.CENTRAL_BANK_PUBLICATION,
                "Synthetic publisher",
                "Synthetic market observations",
                CURRENT,
                url="https://example.invalid/fixture",
            ),
        ),
        evidence=tuple(
            EvidenceRecord(e, "SRC000000001", f"row/{e}") for e in evidence_ids
        ),
        **{bucket: (definition,)},
    )
    return dataset, RateChangeRequest(series.market_series_id, field, PRIOR, CURRENT)


def _calculate(prior="2.40", current="2.55", *, family=MarketSeriesType.POLICY_RATE):
    dataset, request = _dataset(
        _observation(9, PRIOR, prior), _observation(1, CURRENT, current), family=family
    )
    return calculate_rate_change(dataset, request)


@pytest.mark.parametrize("family", RATE_FAMILIES)
@pytest.mark.parametrize(
    "prior,current,expected",
    [
        ("2.40", "2.55", "15"),
        ("2.55", "2.40", "-15"),
        ("-0.25", "0.10", "35"),
        ("0", "0", "0"),
        ("-0.10", "-0.25", "-15"),
    ],
)
def test_governed_percent_levels_produce_basis_point_changes(
    family, prior, current, expected
):
    result = _calculate(prior, current, family=family)
    assert result.status is RateChangeStatus.CALCULATED
    assert result.value == Decimal(expected)
    assert result.unit == "BASIS_POINTS"
    assert result.value_class is ValueClass.CALCULATED
    assert result.decimal_policy_ref == RATE_CHANGE_DECIMAL_POLICY_REF
    assert result.block_reasons == result.arithmetic_signals == ()
    assert result.input_observation_ids == ("OBS000000009", "OBS000000001")
    assert result.prior.request.as_of_date == PRIOR
    assert result.current.request.as_of_date == CURRENT
    assert result.prior.market_series == result.current.market_series
    assert result.prior.definition == result.current.definition
    with pytest.raises(FrozenInstanceError):
        result.value = Decimal(0)


@pytest.mark.parametrize("which", ["prior", "current", "both"])
def test_blocked_endpoint_never_produces_partial_calculation(which):
    prior = _observation(
        9,
        PRIOR,
        "2.40",
        state=VerificationState.PENDING
        if which in {"prior", "both"}
        else VerificationState.PRIMARY_VERIFIED,
    )
    current = _observation(
        1,
        CURRENT,
        "2.55",
        state=VerificationState.PENDING
        if which in {"current", "both"}
        else VerificationState.PRIMARY_VERIFIED,
    )
    dataset, request = _dataset(prior, current)
    result = calculate_rate_change(dataset, request)
    expected = set()
    if which in {"prior", "both"}:
        expected.add(RateChangeBlockReason.PRIOR_SELECTION_BLOCKED)
    if which in {"current", "both"}:
        expected.add(RateChangeBlockReason.CURRENT_SELECTION_BLOCKED)
    assert result.block_reasons == tuple(sorted(expected))
    assert result.status is RateChangeStatus.BLOCKED
    assert result.value is result.value_class is None
    assert result.input_observation_ids == result.arithmetic_signals == ()
    # Both endpoint decisions are available, even when the prior one blocks.
    assert result.prior.candidate_observation_ids == (prior.observation_id,)
    assert result.current.candidate_observation_ids == (current.observation_id,)


def test_missingness_and_conflict_diagnostics_remain_attached_to_their_endpoint():
    prior = replace(
        _observation(9, PRIOR, "2.40", state=VerificationState.PENDING),
        value=None,
        value_class=None,
        missing_state=MissingDataState.UNAVAILABLE,
        verification_state=VerificationState.UNAVAILABLE,
        unit=None,
    )
    current = _observation(1, CURRENT, "2.55")
    conflicting = _observation(2, CURRENT, "2.65", state=VerificationState.PENDING)
    dataset, request = _dataset(prior, current, conflicting)
    result = calculate_rate_change(dataset, request)
    assert (
        result.prior.lineage_observations[0].missing_state
        is MissingDataState.UNAVAILABLE
    )
    assert result.prior.block_reasons == (
        SelectionBlockReason.NO_ELIGIBLE_POPULATED_VALUE,
    )
    assert result.current.block_reasons == (SelectionBlockReason.CONFLICTING_VALUES,)
    assert len(result.current.evidence) == 2
    assert result.block_reasons == (
        RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,
        RateChangeBlockReason.PRIOR_SELECTION_BLOCKED,
    )
    assert result.value is None


def test_endpoint_roles_all_support_and_original_decimal_scales_survive_reordering():
    observations = (
        _observation(9, PRIOR, "2.400"),
        _observation(7, PRIOR, "2.4", state=VerificationState.SECONDARY_VERIFIED),
        _observation(1, CURRENT, "2.55"),
        _observation(3, CURRENT, "2.5500", state=VerificationState.CROSS_VERIFIED),
    )
    dataset, request = _dataset(*observations)
    expected = calculate_rate_change(dataset, request)
    for order in permutations(dataset.observations):
        reordered = replace(
            dataset, observations=order, evidence=tuple(reversed(dataset.evidence))
        )
        assert calculate_rate_change(reordered, request) == expected
    assert expected.input_observation_ids == (
        "OBS000000007",
        "OBS000000009",
        "OBS000000001",
        "OBS000000003",
    )
    assert str(expected.value) == "15"
    assert str(expected.prior.lineage_observations[1].value) == "2.400"
    assert str(expected.current.lineage_observations[1].value) == "2.5500"
    assert (
        expected.prior.lineage_observations[0].verification_state
        is VerificationState.SECONDARY_VERIFIED
    )
    assert (
        expected.current.lineage_observations[1].verification_state
        is VerificationState.CROSS_VERIFIED
    )
    assert len(expected.prior.evidence) == len(expected.current.evidence) == 2


@pytest.mark.parametrize(
    "prior,current,expected",
    [
        (
            "0",
            "0.12345678901234567890123456789012345678",
            "12.345678901234567890123456789012345678",
        ),
        (
            "123456789012345678901234567890123456789.01",
            "123456789012345678901234567890123456789.02",
            "1",
        ),
        ("0", "1E+999997", "1E+999999"),
        ("0", "1E-1000036", "1E-1000034"),
        ("-0.000", "0.00", "0"),
    ],
)
def test_exact_precision_cancellation_exponent_and_zero_boundaries(
    prior, current, expected
):
    result = _calculate(prior, current)
    assert result.status is RateChangeStatus.CALCULATED
    assert result.value == Decimal(expected)
    assert result.arithmetic_signals == ()
    if Decimal(expected).is_zero():
        assert str(result.value) == "0"
        assert result.prior.lineage_observations[0].value.as_tuple().sign == 1


@pytest.mark.parametrize(
    "current,signal",
    [
        ("0.123456789012345678901234567890123456789", "Inexact"),
        ("1E+999998", "Overflow"),
        ("1E+1000000", "Overflow"),
        ("1E-1000037", "Underflow"),
    ],
)
def test_unrepresentable_arithmetic_blocks_without_losing_verified_inputs(
    current, signal
):
    result = _calculate("0", current)
    assert result.status is RateChangeStatus.BLOCKED
    assert result.value is result.value_class is None
    assert result.block_reasons == (RateChangeBlockReason.ARITHMETIC_NOT_REPRESENTABLE,)
    assert signal in result.arithmetic_signals
    assert result.arithmetic_signals == tuple(sorted(result.arithmetic_signals))
    assert (
        result.prior.status is result.current.status is MarketSelectionStatus.SELECTED
    )
    assert result.prior.supporting_observation_ids == ("OBS000000009",)
    assert result.current.supporting_observation_ids == ("OBS000000001",)
    assert result.input_observation_ids == ()


def test_caller_decimal_settings_and_flags_cannot_change_success_or_failure():
    success_before = _calculate()
    failure_before = _calculate("0", "0.123456789012345678901234567890123456789")
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_DOWN
        context.Emax = 2
        context.Emin = -2
        context.clamp = 1
        context.traps[Inexact] = context.traps[Rounded] = True
        context.flags[Inexact] = True
        flags_before = context.flags.copy()
        assert _calculate() == success_before
        assert (
            _calculate("0", "0.123456789012345678901234567890123456789")
            == failure_before
        )
        assert context.flags == flags_before
        assert context.prec == 1 and context.rounding == ROUND_DOWN
        assert context.Emax == 2 and context.Emin == -2 and context.clamp == 1


@pytest.mark.parametrize(
    "family",
    [
        MarketSeriesType.FX_REFERENCE_RATE,
        MarketSeriesType.CREDIT_SPREAD,
        MarketSeriesType.EQUITY_INDEX,
        MarketSeriesType.VOLATILITY_INDEX,
    ],
)
def test_unsupported_series_families_are_rejected_not_misinterpreted_as_percent(family):
    with pytest.raises(ValueError, match="support POLICY_RATE"):
        _calculate(family=family)


@pytest.mark.parametrize(
    "changes",
    [
        {"prior_date": CURRENT},
        {"current_date": PRIOR - timedelta(days=1)},
        {"prior_date": datetime(2026, 10, 15, tzinfo=UTC)},
        {"current_date": "2026-10-16"},
        {"methodology_version": "market-rate-change-v2"},
        {"selection_policy_version": "market-exact-date-v2"},
    ],
)
def test_invalid_dates_and_forward_incompatible_policy_requests_are_rejected(changes):
    _, request = _dataset()
    with pytest.raises((TypeError, ValueError)):
        replace(request, **changes)


@pytest.mark.parametrize("missing_endpoint", ["prior", "current", "both"])
def test_no_missing_endpoint_is_carried_or_replaced_by_another_date(missing_endpoint):
    prior_day = (
        PRIOR - timedelta(days=1) if missing_endpoint in {"prior", "both"} else PRIOR
    )
    current_day = (
        CURRENT + timedelta(days=1)
        if missing_endpoint in {"current", "both"}
        else CURRENT
    )
    dataset, request = _dataset(
        _observation(9, prior_day, "2.4"), _observation(1, current_day, "2.55")
    )
    result = calculate_rate_change(dataset, request)
    assert result.status is RateChangeStatus.BLOCKED
    assert result.value is None
    if missing_endpoint in {"prior", "both"}:
        assert (
            SelectionBlockReason.NO_EXACT_DATE_OBSERVATION in result.prior.block_reasons
        )
    if missing_endpoint in {"current", "both"}:
        assert (
            SelectionBlockReason.NO_EXACT_DATE_OBSERVATION
            in result.current.block_reasons
        )


def test_malformed_snapshot_is_an_error_not_a_business_or_arithmetic_block():
    dataset, request = _dataset(
        _observation(9, PRIOR, "2.4"), _observation(1, CURRENT, "2.55")
    )
    with pytest.raises(ValueError, match="evidence reference"):
        calculate_rate_change(replace(dataset, evidence=()), request)
    with pytest.raises(ValueError, match="Requested field"):
        calculate_rate_change(
            dataset, replace(request, field_name="market_series.yield_percent")
        )
    with pytest.raises(TypeError, match="RateChangeRequest"):
        calculate_rate_change(dataset, object())
    with pytest.raises(TypeError, match="CanonicalDataset"):
        calculate_rate_change(object(), request)


def test_new_correction_snapshot_does_not_rewrite_prior_calculation():
    dataset, request = _dataset(
        _observation(9, PRIOR, "2.4"), _observation(1, CURRENT, "2.55")
    )
    old_result = calculate_rate_change(dataset, request)
    correction = replace(
        dataset.observations[1], observation_id="OBS000000002", value=Decimal("2.65")
    )
    changed_dataset = replace(dataset, observations=(*dataset.observations, correction))
    new_result = calculate_rate_change(changed_dataset, request)
    assert new_result.block_reasons == (
        RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,
    )
    assert new_result.current.block_reasons == (
        SelectionBlockReason.CONFLICTING_VALUES,
    )
    assert calculate_rate_change(dataset, request) == old_result
    assert old_result.value == Decimal("15")


def test_calculation_does_not_accept_independent_or_fabricated_endpoint_results():
    dataset, request = _dataset(
        _observation(9, PRIOR, "2.4"), _observation(1, CURRENT, "2.55")
    )
    selection = select_market_observation(
        dataset,
        ExactDateMarketRequest(
            request.market_series_id,
            request.field_name,
            PRIOR,
        ),
    )
    with pytest.raises(TypeError, match="CanonicalDataset"):
        calculate_rate_change(selection, request)
    with pytest.raises(TypeError):
        calculate_rate_change(dataset, request, known_at=VERIFIED_AT)


def test_endpoint_from_another_series_cannot_fill_the_requested_series():
    dataset, request = _dataset(
        _observation(9, PRIOR, "2.4"), _observation(1, CURRENT, "2.55")
    )
    other_series = replace(dataset.market_series[0], market_series_id="MKS000000999")
    other_definition = replace(
        dataset.policy_rates[0],
        market_series_id=other_series.market_series_id,
        rate_name="Different policy rate",
    )
    dataset = replace(
        dataset,
        market_series=(*dataset.market_series, other_series),
        policy_rates=(*dataset.policy_rates, other_definition),
        observations=(
            dataset.observations[0],
            replace(
                dataset.observations[1],
                subject_id=other_series.market_series_id,
            ),
        ),
    )
    result = calculate_rate_change(dataset, request)
    assert result.block_reasons == (RateChangeBlockReason.CURRENT_SELECTION_BLOCKED,)
    assert result.prior.status is MarketSelectionStatus.SELECTED
    assert result.current.candidate_observation_ids == ()
    assert result.value is None


def test_mutable_decimal_default_context_cannot_supply_calculation_settings():
    from decimal import DefaultContext

    dataset, request = _dataset(
        _observation(9, PRIOR, "2.4"), _observation(1, CURRENT, "2.55")
    )
    expected = calculate_rate_change(dataset, request)
    original = DefaultContext.copy()
    try:
        DefaultContext.prec = 1
        DefaultContext.rounding = ROUND_DOWN
        DefaultContext.Emin = -2
        DefaultContext.Emax = 2
        DefaultContext.clamp = 1
        for signal in DefaultContext.traps:
            DefaultContext.traps[signal] = True
            DefaultContext.flags[signal] = True
        assert calculate_rate_change(dataset, request) == expected
    finally:
        for attribute in ("prec", "rounding", "Emin", "Emax", "capitals", "clamp"):
            setattr(DefaultContext, attribute, getattr(original, attribute))
        DefaultContext.traps = original.traps.copy()
        DefaultContext.flags = original.flags.copy()
