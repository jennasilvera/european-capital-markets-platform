"""Top-level canonical dataset composition and validation."""

from dataclasses import dataclass

from european_capital_markets.domain.consistency import (
    validate_cross_observation_consistency,
)
from european_capital_markets.domain.entities import (
    InstrumentRecord,
    IssuerRecord,
    TransactionRecord,
    validate_entity_bundle,
)
from european_capital_markets.domain.issuer_identity import (
    IssuerIdentifierRecord,
    validate_issuer_identity_bundle,
)
from european_capital_markets.domain.lifecycle import (
    TransactionLifecycleEventRecord,
    validate_lifecycle_bundle,
)
from european_capital_markets.domain.lineage import (
    EvidenceRecord,
    ObservationRecord,
    SourceRecord,
    validate_lineage_bundle,
)
from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
    validate_market_data_bundle,
)
from european_capital_markets.domain.participations import (
    ParticipationRecord,
    validate_participation_bundle,
)
from european_capital_markets.domain.parties import (
    PartyRecord,
    validate_party_bundle,
)
from european_capital_markets.domain.taxonomy import EntityType
from european_capital_markets.domain.terms import validate_field_catalog


@dataclass(frozen=True, slots=True)
class CanonicalDataset:
    """One coherent canonical data bundle at the validation boundary."""

    issuers: tuple[IssuerRecord, ...] = ()
    transactions: tuple[TransactionRecord, ...] = ()
    instruments: tuple[InstrumentRecord, ...] = ()
    issuer_identifiers: tuple[IssuerIdentifierRecord, ...] = ()
    parties: tuple[PartyRecord, ...] = ()
    participations: tuple[ParticipationRecord, ...] = ()
    lifecycle_events: tuple[TransactionLifecycleEventRecord, ...] = ()
    market_series: tuple[MarketSeriesRecord, ...] = ()
    fx_reference_rates: tuple[FXReferenceRateDefinitionRecord, ...] = ()
    policy_rates: tuple[PolicyRateDefinitionRecord, ...] = ()
    government_yields: tuple[GovernmentYieldDefinitionRecord, ...] = ()
    swap_rates: tuple[SwapRateDefinitionRecord, ...] = ()
    credit_spreads: tuple[CreditSpreadDefinitionRecord, ...] = ()
    equity_indices: tuple[EquityIndexDefinitionRecord, ...] = ()
    volatility_indices: tuple[VolatilityIndexDefinitionRecord, ...] = ()
    sources: tuple[SourceRecord, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    observations: tuple[ObservationRecord, ...] = ()


def validate_canonical_dataset(dataset: CanonicalDataset) -> None:
    """Validate one canonical dataset across all frozen domain boundaries."""

    validate_field_catalog()

    validate_entity_bundle(
        issuers=dataset.issuers,
        transactions=dataset.transactions,
        instruments=dataset.instruments,
    )

    validate_lineage_bundle(
        sources=dataset.sources,
        evidence=dataset.evidence,
        observations=dataset.observations,
    )

    validate_issuer_identity_bundle(
        issuers=dataset.issuers,
        identifiers=dataset.issuer_identifiers,
        sources=dataset.sources,
        evidence=dataset.evidence,
    )

    validate_party_bundle(
        issuers=dataset.issuers,
        parties=dataset.parties,
    )

    validate_participation_bundle(
        parties=dataset.parties,
        transactions=dataset.transactions,
        instruments=dataset.instruments,
        participations=dataset.participations,
        sources=dataset.sources,
        evidence=dataset.evidence,
    )

    validate_lifecycle_bundle(
        transactions=dataset.transactions,
        events=dataset.lifecycle_events,
        sources=dataset.sources,
        evidence=dataset.evidence,
    )

    _validate_observation_subject_references(dataset)

    validate_market_data_bundle(
        market_series=dataset.market_series,
        fx_reference_rates=dataset.fx_reference_rates,
        observations=dataset.observations,
        policy_rates=dataset.policy_rates,
        government_yields=dataset.government_yields,
        swap_rates=dataset.swap_rates,
        credit_spreads=dataset.credit_spreads,
        equity_indices=dataset.equity_indices,
        volatility_indices=dataset.volatility_indices,
    )

    validate_cross_observation_consistency(
        instruments=dataset.instruments,
        observations=dataset.observations,
        fx_reference_rates=dataset.fx_reference_rates,
    )


def _validate_observation_subject_references(
    dataset: CanonicalDataset,
) -> None:
    """Require every observation to reference a concrete canonical subject."""

    subject_ids_by_type = {
        EntityType.ISSUER: {
            issuer.issuer_id
            for issuer in dataset.issuers
        },
        EntityType.PARTY: {
            party.party_id
            for party in dataset.parties
        },
        EntityType.PARTICIPATION: {
            participation.participation_id
            for participation in dataset.participations
        },
        EntityType.TRANSACTION: {
            transaction.transaction_id
            for transaction in dataset.transactions
        },
        EntityType.INSTRUMENT: {
            instrument.instrument_id
            for instrument in dataset.instruments
        },
        EntityType.MARKET_SERIES: {
            series.market_series_id
            for series in dataset.market_series
        },
    }

    for observation in dataset.observations:
        known_subject_ids = subject_ids_by_type[observation.subject_type]

        if observation.subject_id not in known_subject_ids:
            raise ValueError(
                "Unknown observation subject reference: "
                f"{observation.subject_type.value} "
                f"{observation.subject_id!r}."
            )
