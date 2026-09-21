"""Tests for canonical market-ingestion handoff assembly."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    MissingDataState,
    SourceTier,
    SourceType,
    VerificationState,
)
from european_capital_markets.ingestion.contracts import (
    AllocatedLineageIds,
    NormalizedMarketDatum,
    RawRetrievalArtifact,
    RetrievalSource,
)
from european_capital_markets.ingestion.orchestration import (
    build_canonical_market_ingestion_handoff,
)
from european_capital_markets.reference_data import (
    load_market_series_catalog,
)

_CATALOG_PATH = (
    "data/reference/market_series_catalog.json"
)

_ARTIFACT_URL = (
    "https://example.test/provider"
)


def _catalog_entry(
    market_series_id: str = "MKS000000001",
):
    catalog = load_market_series_catalog(
        _CATALOG_PATH
    )

    return next(
        entry
        for entry in catalog.entries
        if (
            entry.market_series.market_series_id
            == market_series_id
        )
    )


def _artifact(
    market_series_id: str = "MKS000000001",
) -> RawRetrievalArtifact:
    return RawRetrievalArtifact(
        market_series_id=market_series_id,
        source=RetrievalSource(
            publisher="Synthetic Provider",
            source_tier=(
                SourceTier.OFFICIAL_INSTITUTION
            ),
            source_type=(
                SourceType.CENTRAL_BANK_PUBLICATION
            ),
            title="Synthetic raw retrieval",
            url=_ARTIFACT_URL,
            retrieval_identifier="TEST.SERIES",
        ),
        retrieved_at=datetime(
            2026,
            9,
            20,
            17,
            0,
            tzinfo=UTC,
        ),
        archived_location=(
            f"data/raw/test/{market_series_id}/"
            "2026/09/20/example.csv"
        ),
        content_sha256=(
            "0" * 64
        ),
        byte_length=0,
        media_type="text/csv",
    )


def _datum(
    *,
    market_series_id: str = "MKS000000001",
    as_of_date: date = date(
        2026,
        9,
        20,
    ),
    value: Decimal | None = Decimal("2.5"),
    missing_state: MissingDataState | None = None,
) -> NormalizedMarketDatum:
    return NormalizedMarketDatum(
        market_series_id=market_series_id,
        field_name="market_series.rate_percent",
        as_of_date=as_of_date,
        evidence_locator=(
            f"TIME_PERIOD={as_of_date.isoformat()}"
        ),
        value=value,
        missing_state=missing_state,
        unit="PERCENT",
        evidence_label=(
            as_of_date.isoformat()
        ),
    )


def _ids(
    sequence: int,
    *,
    source_id: str = "SRC000000001",
) -> AllocatedLineageIds:
    return AllocatedLineageIds(
        source_id=source_id,
        evidence_id=(
            f"EVD{sequence:09d}"
        ),
        observation_id=(
            f"OBS{sequence:09d}"
        ),
    )


def test_handoff_builds_one_source_and_per_datum_lineage() -> None:
    datums = (
        _datum(
            as_of_date=date(
                2026,
                9,
                18,
            )
        ),
        _datum(
            as_of_date=date(
                2026,
                9,
                19,
            )
        ),
        _datum(
            as_of_date=date(
                2026,
                9,
                20,
            )
        ),
    )

    result = (
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            datums,
            (
                _ids(1),
                _ids(2),
                _ids(3),
            ),
        )
    )

    dataset = result.dataset

    assert len(
        dataset.sources
    ) == 1

    assert dataset.sources[0].source_id == (
        "SRC000000001"
    )

    assert tuple(
        record.evidence_id
        for record in dataset.evidence
    ) == (
        "EVD000000001",
        "EVD000000002",
        "EVD000000003",
    )

    assert tuple(
        record.observation_id
        for record in dataset.observations
    ) == (
        "OBS000000001",
        "OBS000000002",
        "OBS000000003",
    )

    assert all(
        record.verification_state
        is VerificationState.PENDING
        for record in dataset.observations
    )

    assert len(
        result.lineage
    ) == 3


def test_handoff_preserves_raw_archive_location() -> None:
    result = (
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(),
            ),
            (
                _ids(1),
            ),
        )
    )

    assert (
        result.dataset.sources[0].archived_location
        == (
            "data/raw/test/MKS000000001/"
            "2026/09/20/example.csv"
        )
    )


def test_handoff_rejects_empty_datums() -> None:
    with pytest.raises(
        ValueError,
        match="at least one normalized datum",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (),
            (),
        )


def test_handoff_rejects_id_count_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="exactly one lineage-ID bundle",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(),
                _datum(
                    as_of_date=date(
                        2026,
                        9,
                        19,
                    )
                ),
            ),
            (
                _ids(1),
            ),
        )


def test_handoff_requires_one_source_id_per_retrieval() -> None:
    with pytest.raises(
        ValueError,
        match="share one externally allocated source_id",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(),
                _datum(
                    as_of_date=date(
                        2026,
                        9,
                        19,
                    )
                ),
            ),
            (
                _ids(
                    1,
                    source_id="SRC000000001",
                ),
                _ids(
                    2,
                    source_id="SRC000000002",
                ),
            ),
        )


def test_handoff_rejects_wrong_artifact_series() -> None:
    with pytest.raises(
        ValueError,
        match="Raw artifact market_series_id",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(
                market_series_id="MKS000000002"
            ),
            (
                _datum(),
            ),
            (
                _ids(1),
            ),
        )


def test_handoff_rejects_wrong_datum_series() -> None:
    with pytest.raises(
        ValueError,
        match="Normalized datum market_series_id",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(
                    market_series_id="MKS000000002"
                ),
            ),
            (
                _ids(1),
            ),
        )


def test_unavailable_datum_remains_first_class_observation() -> None:
    result = (
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(
                    value=None,
                    missing_state=(
                        MissingDataState.UNAVAILABLE
                    ),
                ),
            ),
            (
                _ids(1),
            ),
        )
    )

    observation = (
        result.dataset.observations[0]
    )

    assert observation.value is None

    assert (
        observation.missing_state
        is MissingDataState.UNAVAILABLE
    )

    assert (
        observation.verification_state
        is VerificationState.UNAVAILABLE
    )


@pytest.mark.parametrize(
    (
        "market_series_id",
        "definition_type",
        "bucket_name",
    ),
    (
        (
            "MKS000000001",
            PolicyRateDefinitionRecord,
            "policy_rates",
        ),
        (
            "MKS000000002",
            GovernmentYieldDefinitionRecord,
            "government_yields",
        ),
        (
            "MKS000000005",
            SwapRateDefinitionRecord,
            "swap_rates",
        ),
        (
            "MKS000000008",
            EquityIndexDefinitionRecord,
            "equity_indices",
        ),
        (
            "MKS000000009",
            VolatilityIndexDefinitionRecord,
            "volatility_indices",
        ),
        (
            "MKS000000010",
            CreditSpreadDefinitionRecord,
            "credit_spreads",
        ),
    ),
)
def test_definition_is_placed_in_correct_dataset_bucket(
    market_series_id: str,
    definition_type: type[object],
    bucket_name: str,
) -> None:
    entry = _catalog_entry(
        market_series_id
    )

    assert isinstance(
        entry.definition,
        definition_type,
    )

    artifact = _artifact(
        market_series_id
    )

    field_name = {
        PolicyRateDefinitionRecord: (
            "market_series.rate_percent"
        ),
        GovernmentYieldDefinitionRecord: (
            "market_series.yield_percent"
        ),
        SwapRateDefinitionRecord: (
            "market_series.rate_percent"
        ),
        CreditSpreadDefinitionRecord: (
            "market_series.spread_bps"
        ),
        EquityIndexDefinitionRecord: (
            "market_series.index_level"
        ),
        VolatilityIndexDefinitionRecord: (
            "market_series.volatility_level"
        ),
    }[
        definition_type
    ]

    unit = {
        PolicyRateDefinitionRecord: "PERCENT",
        GovernmentYieldDefinitionRecord: "PERCENT",
        SwapRateDefinitionRecord: "PERCENT",
        CreditSpreadDefinitionRecord: "BASIS_POINTS",
        EquityIndexDefinitionRecord: "INDEX_POINTS",
        VolatilityIndexDefinitionRecord: "INDEX_POINTS",
    }[
        definition_type
    ]

    datum = NormalizedMarketDatum(
        market_series_id=(
            market_series_id
        ),
        field_name=field_name,
        as_of_date=date(
            2026,
            9,
            20,
        ),
        evidence_locator="synthetic",
        value=Decimal("1.25"),
        unit=unit,
    )

    result = (
        build_canonical_market_ingestion_handoff(
            entry,
            artifact,
            (
                datum,
            ),
            (
                _ids(1),
            ),
        )
    )

    populated_bucket = getattr(
        result.dataset,
        bucket_name,
    )

    assert populated_bucket == (
        entry.definition,
    )

    definition_counts = {
        name: len(
            getattr(
                result.dataset,
                name,
            )
        )
        for name in (
            "fx_reference_rates",
            "policy_rates",
            "government_yields",
            "swap_rates",
            "credit_spreads",
            "equity_indices",
            "volatility_indices",
        )
    }

    assert sum(
        definition_counts.values()
    ) == 1


def test_duplicate_evidence_ids_are_rejected_by_canonical_validation() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate identifier",
    ):
        build_canonical_market_ingestion_handoff(
            _catalog_entry(),
            _artifact(),
            (
                _datum(
                    as_of_date=date(
                        2026,
                        9,
                        19,
                    )
                ),
                _datum(
                    as_of_date=date(
                        2026,
                        9,
                        20,
                    )
                ),
            ),
            (
                _ids(1),
                AllocatedLineageIds(
                    source_id="SRC000000001",
                    evidence_id="EVD000000001",
                    observation_id="OBS000000002",
                ),
            ),
        )
