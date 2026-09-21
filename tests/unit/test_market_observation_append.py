from datetime import date
from decimal import Decimal

import pytest

from european_capital_markets.domain.dataset import CanonicalDataset
from european_capital_markets.domain.entities import IssuerRecord
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
    SourceTier,
    SourceType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence.writer import (
    MarketObservationAppendStatus,
    _validate_market_observation_append_shape,
)


def _dataset() -> CanonicalDataset:
    return CanonicalDataset(
        market_series=(
            MarketSeriesRecord(
                market_series_id="MKS000000001",
                series_type=MarketSeriesType.FX_REFERENCE_RATE,
                series_label="EUR/GBP reference rate",
            ),
        ),
        fx_reference_rates=(
            FXReferenceRateDefinitionRecord(
                market_series_id="MKS000000001",
                base_currency="EUR",
                quote_currency="GBP",
                convention_ref="market-data/fx/reference-rate-v1",
            ),
        ),
        sources=(
            SourceRecord(
                source_id="SRC000000001",
                tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
                source_type=SourceType.MARKET_DATA,
                publisher="Example market-data provider",
                title="EUR/GBP daily reference rate",
                access_date=date(2026, 9, 20),
                url="https://example.invalid/market-data",
                archived_location=(
                    "data/raw/test/MKS000000001/"
                    "2026/09/20/example.csv"
                ),
            ),
        ),
        evidence=(
            EvidenceRecord(
                evidence_id="EVD000000001",
                source_id="SRC000000001",
                locator="TIME_PERIOD=2026-09-19",
            ),
        ),
        observations=(
            ObservationRecord(
                observation_id="OBS000000001",
                subject_type=EntityType.MARKET_SERIES,
                subject_id="MKS000000001",
                field_name="market_series.fx_rate",
                as_of_date=date(2026, 9, 19),
                verification_state=VerificationState.PENDING,
                value=Decimal("0.8650"),
                value_class=ValueClass.DISCLOSED,
                evidence_ids=("EVD000000001",),
            ),
        ),
    )


def test_append_status_is_explicit() -> None:
    assert (
        MarketObservationAppendStatus.INSERTED.value
        == "INSERTED"
    )
    assert (
        MarketObservationAppendStatus.ALREADY_PERSISTED.value
        == "ALREADY_PERSISTED"
    )


def test_append_shape_accepts_one_market_lineage_batch() -> None:
    dataset = _dataset()

    series, definition = (
        _validate_market_observation_append_shape(
            dataset
        )
    )

    assert (
        series
        == dataset.market_series[0]
    )
    assert (
        definition
        == dataset.fx_reference_rates[0]
    )


def test_append_shape_rejects_multiple_sources() -> None:
    dataset = _dataset()

    second_source = SourceRecord(
        source_id="SRC000000002",
        tier=SourceTier.PRIMARY_TRANSACTION_OR_ISSUER,
        source_type=SourceType.MARKET_DATA,
        publisher="Second provider",
        title="Second source",
        access_date=date(2026, 9, 20),
        url="https://example.invalid/second",
    )

    invalid = CanonicalDataset(
        market_series=dataset.market_series,
        fx_reference_rates=dataset.fx_reference_rates,
        sources=(
            *dataset.sources,
            second_source,
        ),
        evidence=dataset.evidence,
        observations=dataset.observations,
    )

    with pytest.raises(
        ValueError,
        match="exactly one canonical source",
    ):
        _validate_market_observation_append_shape(
            invalid
        )


def test_append_shape_rejects_non_market_entities() -> None:
    dataset = _dataset()

    invalid = CanonicalDataset(
        issuers=(
            IssuerRecord(
                issuer_id="ISS000000001",
                canonical_name="Example Issuer",
            ),
        ),
        market_series=dataset.market_series,
        fx_reference_rates=dataset.fx_reference_rates,
        sources=dataset.sources,
        evidence=dataset.evidence,
        observations=dataset.observations,
    )

    with pytest.raises(
        ValueError,
        match="non-market canonical entities",
    ):
        _validate_market_observation_append_shape(
            invalid
        )
