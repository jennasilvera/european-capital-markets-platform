"""Exact economic-date consensus selection; no implicit retrieval or carry."""

from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from enum import StrEnum

from european_capital_markets.domain.dataset import (
    CanonicalDataset,
    validate_canonical_dataset,
)
from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
)
from european_capital_markets.domain.market_data import (
    MarketSeriesDefinitionRecord,
    MarketSeriesRecord,
    expected_market_observation_field,
)
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    ValueClass,
    VerificationState,
)

EXACT_DATE_POLICY_VERSION = "market-exact-date-v1"
_VERIFIED = frozenset(
    {
        VerificationState.PRIMARY_VERIFIED,
        VerificationState.SECONDARY_VERIFIED,
        VerificationState.CROSS_VERIFIED,
    }
)


class MarketSelectionStatus(StrEnum):
    SELECTED = "SELECTED"
    BLOCKED = "BLOCKED"


class SelectionBlockReason(StrEnum):
    CONFLICTING_VALUES = "CONFLICTING_VALUES"
    CONFLICT_STATE = "CONFLICT_STATE"
    NO_ELIGIBLE_POPULATED_VALUE = "NO_ELIGIBLE_POPULATED_VALUE"
    NO_EXACT_DATE_OBSERVATION = "NO_EXACT_DATE_OBSERVATION"
    UNSUPPORTED_VALUE_CLASS = "UNSUPPORTED_VALUE_CLASS"


class CandidateExclusionReason(StrEnum):
    CONFLICT_STATE = "CONFLICT_STATE"
    MISSING_VALUE = "MISSING_VALUE"
    UNSUPPORTED_VALUE_CLASS = "UNSUPPORTED_VALUE_CLASS"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ExactDateMarketRequest:
    market_series_id: str
    field_name: str
    as_of_date: date
    policy_version: str = EXACT_DATE_POLICY_VERSION

    def __post_init__(self) -> None:
        validate_identifier(self.market_series_id, EntityType.MARKET_SERIES)
        if not isinstance(self.field_name, str) or not self.field_name.strip():
            raise ValueError("field_name must be a nonblank string.")
        # datetime is a date subclass; silently truncating it is not permitted.
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date must be a date, not a datetime.")
        if self.policy_version != EXACT_DATE_POLICY_VERSION:
            raise ValueError(f"Unsupported selection policy: {self.policy_version!r}.")


@dataclass(frozen=True, slots=True)
class MarketCandidateDecision:
    observation: ObservationRecord
    exclusion_reasons: tuple[CandidateExclusionReason, ...]


@dataclass(frozen=True, slots=True)
class MarketSelectionResult:
    """An analytical outcome, not canonical verification or release approval.

    Candidate decisions explain eligibility even when disagreement blocks the
    entire selection. lineage_observations includes candidates and their full
    transitive input closure; evidence and sources retain its provenance.
    """

    request: ExactDateMarketRequest
    market_series: MarketSeriesRecord
    definition: MarketSeriesDefinitionRecord
    status: MarketSelectionStatus
    value: Decimal | None
    unit: str | None
    block_reasons: tuple[SelectionBlockReason, ...]
    candidate_decisions: tuple[MarketCandidateDecision, ...]
    lineage_observations: tuple[ObservationRecord, ...]
    evidence: tuple[EvidenceRecord, ...]
    sources: tuple[SourceRecord, ...]

    @property
    def candidate_observation_ids(self) -> tuple[str, ...]:
        return tuple(d.observation.observation_id for d in self.candidate_decisions)

    @property
    def eligible_observation_ids(self) -> tuple[str, ...]:
        return tuple(
            d.observation.observation_id
            for d in self.candidate_decisions
            if not d.exclusion_reasons
        )

    @property
    def supporting_observation_ids(self) -> tuple[str, ...]:
        if self.status is MarketSelectionStatus.BLOCKED:
            return ()
        return self.eligible_observation_ids


def select_market_observation(
    dataset: CanonicalDataset,
    request: ExactDateMarketRequest,
) -> MarketSelectionResult:
    """Validate the supplied snapshot and select exact-date disclosed consensus.

    Every populated candidate participates in disagreement detection, including
    pending candidates. Missing values do not retract populated observations.
    Unknown policies and malformed canonical input are errors, not BLOCKED.
    No clock, catalog, provider, filesystem, or database access occurs here.
    """

    if not isinstance(request, ExactDateMarketRequest):
        raise TypeError("request must be an ExactDateMarketRequest.")
    _validate_snapshot(dataset)
    validate_canonical_dataset(dataset)

    series = next(
        (
            s
            for s in dataset.market_series
            if s.market_series_id == request.market_series_id
        ),
        None,
    )
    if series is None:
        raise ValueError(f"Unknown market series: {request.market_series_id!r}.")
    if request.field_name != expected_market_observation_field(series.series_type):
        raise ValueError("Requested field does not match the market-series family.")
    definition = next(
        d
        for bucket in (
            dataset.fx_reference_rates,
            dataset.policy_rates,
            dataset.government_yields,
            dataset.swap_rates,
            dataset.credit_spreads,
            dataset.equity_indices,
            dataset.volatility_indices,
        )
        for d in bucket
        if d.market_series_id == request.market_series_id
    )
    candidates = tuple(
        sorted(
            (
                o
                for o in dataset.observations
                if o.subject_type is EntityType.MARKET_SERIES
                and o.subject_id == request.market_series_id
                and o.field_name == request.field_name
                and o.as_of_date == request.as_of_date
            ),
            key=lambda o: o.observation_id,
        )
    )
    decisions = tuple(_candidate_decision(o) for o in candidates)
    eligible = tuple(d.observation for d in decisions if not d.exclusion_reasons)
    reasons: set[SelectionBlockReason] = set()
    if not candidates:
        reasons.add(SelectionBlockReason.NO_EXACT_DATE_OBSERVATION)
    if not eligible:
        reasons.add(SelectionBlockReason.NO_ELIGIBLE_POPULATED_VALUE)
    if any(o.verification_state is VerificationState.CONFLICT for o in candidates):
        reasons.add(SelectionBlockReason.CONFLICT_STATE)
    populated = tuple(o for o in candidates if o.value is not None)
    if any(o.value_class is not ValueClass.DISCLOSED for o in populated):
        reasons.add(SelectionBlockReason.UNSUPPORTED_VALUE_CLASS)
    if len({o.value for o in populated}) > 1:
        reasons.add(SelectionBlockReason.CONFLICTING_VALUES)

    observations, evidence, sources = _lineage_closure(dataset, candidates)
    value = None
    unit = None
    if not reasons:
        # All eligible values are numerically equal; none is a preferred source.
        value = _canonical_decimal(eligible[0].value)
        unit = eligible[0].unit
    return MarketSelectionResult(
        request=request,
        market_series=series,
        definition=definition,
        status=MarketSelectionStatus.BLOCKED
        if reasons
        else MarketSelectionStatus.SELECTED,
        value=value,
        unit=unit,
        block_reasons=tuple(sorted(reasons)),
        candidate_decisions=decisions,
        lineage_observations=observations,
        evidence=evidence,
        sources=sources,
    )


def _validate_snapshot(dataset: CanonicalDataset) -> None:
    """Require immutable collections and guard Decimal comparisons before domain work.

    The domain constructors use type annotations for some of these shapes.
    Selection cannot retain mutable lists or allow nonfinite values to reach
    comparison logic whose behavior depends on ambient Decimal traps.
    """

    if not isinstance(dataset, CanonicalDataset):
        raise TypeError("dataset must be a CanonicalDataset.")
    for field in fields(dataset):
        if not isinstance(getattr(dataset, field.name), tuple):
            raise TypeError(f"dataset.{field.name} must be a tuple.")
    for o in dataset.observations:
        if not isinstance(o, ObservationRecord):
            raise TypeError(
                "dataset.observations must contain ObservationRecord values."
            )
        if not isinstance(o.evidence_ids, tuple) or not isinstance(
            o.input_observation_ids, tuple
        ):
            raise TypeError("Observation lineage references must be tuples.")
        if type(o.as_of_date) is not date:
            raise TypeError("Observation as_of_date must be a date, not a datetime.")
        if not isinstance(o.subject_type, EntityType):
            raise TypeError("Observation subject_type must be an EntityType.")
        if not isinstance(o.verification_state, VerificationState):
            raise TypeError(
                "Observation verification_state must be a VerificationState."
            )
        if o.value_class is not None and not isinstance(o.value_class, ValueClass):
            raise TypeError("Observation value_class must be a ValueClass.")
        if o.missing_state is not None and not isinstance(
            o.missing_state, MissingDataState
        ):
            raise TypeError("Observation missing_state must be a MissingDataState.")
        if isinstance(o.value, Decimal) and not o.value.is_finite():
            raise ValueError("Observation Decimal values must be finite.")


def _candidate_decision(o: ObservationRecord) -> MarketCandidateDecision:
    reasons: set[CandidateExclusionReason] = set()
    if o.value is None:
        reasons.add(CandidateExclusionReason.MISSING_VALUE)
    elif o.value_class is not ValueClass.DISCLOSED:
        reasons.add(CandidateExclusionReason.UNSUPPORTED_VALUE_CLASS)
    if o.verification_state is VerificationState.CONFLICT:
        reasons.add(CandidateExclusionReason.CONFLICT_STATE)
    elif o.verification_state not in _VERIFIED:
        reasons.add(CandidateExclusionReason.UNVERIFIED)
    return MarketCandidateDecision(o, tuple(sorted(reasons)))


def _canonical_decimal(value: Decimal) -> Decimal:
    """Remove scale-only differences without rounding or using Decimal context."""

    if value.is_zero():
        return Decimal(0)
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while digits[end - 1] == 0:
        end -= 1
    return Decimal((sign, digits[:end], exponent + len(digits) - end))


def _lineage_closure(
    dataset: CanonicalDataset,
    candidates: tuple[ObservationRecord, ...],
) -> tuple[
    tuple[ObservationRecord, ...], tuple[EvidenceRecord, ...], tuple[SourceRecord, ...]
]:
    by_id = {o.observation_id: o for o in dataset.observations}
    pending = [o.observation_id for o in candidates]
    retained: set[str] = set()
    while pending:
        observation_id = pending.pop()
        if observation_id not in retained:
            retained.add(observation_id)
            pending.extend(by_id[observation_id].input_observation_ids)
    observations = tuple(by_id[i] for i in sorted(retained))
    evidence_ids = {e for o in observations for e in o.evidence_ids}
    evidence = tuple(
        sorted(
            (e for e in dataset.evidence if e.evidence_id in evidence_ids),
            key=lambda e: e.evidence_id,
        )
    )
    source_ids = {e.source_id for e in evidence}
    sources = tuple(
        sorted(
            (s for s in dataset.sources if s.source_id in source_ids),
            key=lambda s: s.source_id,
        )
    )
    return observations, evidence, sources
