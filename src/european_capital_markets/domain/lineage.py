"""Source, evidence, observation, and lineage controls."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from re import fullmatch

from european_capital_markets.domain.identifiers import validate_identifier
from european_capital_markets.domain.taxonomy import (
    EntityType,
    MissingDataState,
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)

type ScalarValue = str | int | Decimal | bool | date | datetime

_OBSERVABLE_SUBJECT_TYPES = frozenset(
    {
        EntityType.ISSUER,
        EntityType.PARTY,
        EntityType.PARTICIPATION,
        EntityType.TRANSACTION,
        EntityType.INSTRUMENT,
    }
)

_SOURCE_VERIFIED_STATES = frozenset(
    {
        VerificationState.PRIMARY_VERIFIED,
        VerificationState.SECONDARY_VERIFIED,
    }
)

_VERIFIED_STATES = frozenset(
    {
        VerificationState.PRIMARY_VERIFIED,
        VerificationState.SECONDARY_VERIFIED,
        VerificationState.CROSS_VERIFIED,
    }
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank.")


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates.")


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Metadata required to identify and revisit a source."""

    source_id: str
    tier: SourceTier
    source_type: SourceType
    publisher: str
    title: str
    access_date: date
    document_date: date | None = None
    publication_date: date | None = None
    url: str | None = None
    archived_location: str | None = None
    document_version: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.source_id, EntityType.SOURCE)
        _require_non_blank(self.publisher, "publisher")
        _require_non_blank(self.title, "title")

        if self.url is not None:
            _require_non_blank(self.url, "url")

        if self.archived_location is not None:
            _require_non_blank(self.archived_location, "archived_location")

        if self.url is None and self.archived_location is None:
            raise ValueError(
                "A source requires either a URL or an archived location."
            )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Precise locator connecting a source to an analytical fact."""

    evidence_id: str
    source_id: str
    locator: str
    label: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.evidence_id, EntityType.EVIDENCE)
        validate_identifier(self.source_id, EntityType.SOURCE)
        _require_non_blank(self.locator, "locator")

        if self.label is not None:
            _require_non_blank(self.label, "label")


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    """A governed value or explicit missing-data state about an entity."""

    observation_id: str
    subject_type: EntityType
    subject_id: str
    field_name: str
    as_of_date: date
    verification_state: VerificationState
    verified_at: datetime | None = None
    value: ScalarValue | None = None
    value_class: ValueClass | None = None
    missing_state: MissingDataState | None = None
    unit: str | None = None
    currency: str | None = None
    evidence_ids: tuple[str, ...] = ()
    input_observation_ids: tuple[str, ...] = ()
    derivation_ref: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.observation_id, EntityType.OBSERVATION)
        validate_identifier(self.subject_id, self.subject_type)

        if self.subject_type not in _OBSERVABLE_SUBJECT_TYPES:
            raise ValueError(
                f"{self.subject_type.value} is not an observable business subject."
            )

        if self.verification_state in _VERIFIED_STATES and self.verified_at is None:
            raise ValueError(
                "A verified observation requires a verified_at timestamp."
            )

        if (
            self.verification_state not in _VERIFIED_STATES
            and self.verified_at is not None
        ):
            raise ValueError(
                "An unverified observation cannot have a verified_at timestamp."
            )

        if self.verified_at is not None and self.verified_at.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware.")

        if fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", self.field_name) is None:
            raise ValueError(
                "field_name must use lower-case snake_case segments, optionally "
                "separated by dots."
            )

        if self.unit is not None:
            _require_non_blank(self.unit, "unit")

        if (
            self.currency is not None
            and fullmatch(r"[A-Z]{3}", self.currency) is None
        ):
            raise ValueError("currency must be a three-letter upper-case code.")

        _require_unique(self.evidence_ids, "evidence_ids")
        _require_unique(self.input_observation_ids, "input_observation_ids")

        for evidence_id in self.evidence_ids:
            validate_identifier(evidence_id, EntityType.EVIDENCE)

        for input_observation_id in self.input_observation_ids:
            validate_identifier(input_observation_id, EntityType.OBSERVATION)

        if self.observation_id in self.input_observation_ids:
            raise ValueError("An observation cannot depend on itself.")

        has_value = self.value is not None
        has_missing_state = self.missing_state is not None

        if has_value == has_missing_state:
            raise ValueError(
                "Exactly one of value or missing_state must be populated."
            )

        if has_value and self.value_class is None:
            raise ValueError("A populated value requires value_class.")

        if has_missing_state and self.value_class is not None:
            raise ValueError("A missing-data observation cannot have value_class.")

        if has_value and self.verification_state is VerificationState.UNAVAILABLE:
            raise ValueError(
                "A populated value cannot have UNAVAILABLE verification state."
            )

        if (
            self.value_class is not None
            and self.value_class is not ValueClass.DISCLOSED
            and self.verification_state in _SOURCE_VERIFIED_STATES
        ):
            raise ValueError(
                "Only DISCLOSED values may use source-verification states."
            )

        if self.value_class is ValueClass.DISCLOSED and not self.evidence_ids:
            raise ValueError("A DISCLOSED value requires supporting evidence.")

        if self.value_class is ValueClass.CALCULATED:
            if not self.input_observation_ids:
                raise ValueError(
                    "A CALCULATED value requires input observations."
                )
            if self.derivation_ref is None:
                raise ValueError(
                    "A CALCULATED value requires a derivation reference."
                )

        if self.value_class is ValueClass.ESTIMATED:
            if not self.evidence_ids and not self.input_observation_ids:
                raise ValueError(
                    "An ESTIMATED value requires evidence or input observations."
                )
            if self.derivation_ref is None:
                raise ValueError(
                    "An ESTIMATED value requires a derivation reference."
                )

        if self.value_class is ValueClass.ASSUMED and self.derivation_ref is None:
            raise ValueError("An ASSUMED value requires a rationale reference.")

        if self.derivation_ref is not None:
            _require_non_blank(self.derivation_ref, "derivation_ref")

        if (
            self.missing_state is MissingDataState.NOT_DISCLOSED
            and not self.evidence_ids
        ):
            raise ValueError(
                "NOT_DISCLOSED requires evidence showing the reviewed source."
            )

        if (
            self.missing_state is MissingDataState.UNAVAILABLE
            and self.verification_state is not VerificationState.UNAVAILABLE
        ):
            raise ValueError(
                "UNAVAILABLE missing state requires UNAVAILABLE verification."
            )

        if (
            self.missing_state is MissingDataState.PENDING_VERIFICATION
            and self.verification_state is not VerificationState.PENDING
        ):
            raise ValueError(
                "PENDING_VERIFICATION requires PENDING verification."
            )


def validate_lineage_bundle(
    sources: tuple[SourceRecord, ...],
    evidence: tuple[EvidenceRecord, ...],
    observations: tuple[ObservationRecord, ...],
) -> None:
    """Validate references, uniqueness, and calculation-lineage acyclicity."""

    source_by_id = _index_unique(sources, "source_id")
    evidence_by_id = _index_unique(evidence, "evidence_id")
    observation_by_id = _index_unique(observations, "observation_id")

    for evidence_record in evidence:
        if evidence_record.source_id not in source_by_id:
            raise ValueError(
                f"Unknown source reference: {evidence_record.source_id!r}"
            )

    for observation in observations:
        for evidence_id in observation.evidence_ids:
            if evidence_id not in evidence_by_id:
                raise ValueError(f"Unknown evidence reference: {evidence_id!r}")

        for input_id in observation.input_observation_ids:
            if input_id not in observation_by_id:
                raise ValueError(
                    f"Unknown input observation reference: {input_id!r}"
                )

    _validate_acyclic_observation_lineage(observation_by_id)


def _index_unique[T](
    records: tuple[T, ...],
    id_field: str,
) -> dict[str, T]:
    index: dict[str, T] = {}

    for record in records:
        identifier = getattr(record, id_field)
        if identifier in index:
            raise ValueError(f"Duplicate identifier: {identifier!r}")
        index[identifier] = record

    return index


def _validate_acyclic_observation_lineage(
    observations: dict[str, ObservationRecord],
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(observation_id: str) -> None:
        if observation_id in visiting:
            raise ValueError(
                f"Cycle detected in observation lineage at {observation_id!r}"
            )

        if observation_id in visited:
            return

        visiting.add(observation_id)
        observation = observations[observation_id]

        for dependency in observation.input_observation_ids:
            visit(dependency)

        visiting.remove(observation_id)
        visited.add(observation_id)

    for observation_id in observations:
        visit(observation_id)
