from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
)
from european_capital_markets.domain.taxonomy import (
    MarketSeriesType,
    SourceTier,
    SourceType,
)
from european_capital_markets.reference_data.market_series_catalog import (
    CATALOG_VERSION,
    PublicationFrequency,
    load_market_series_catalog,
    parse_market_series_catalog,
)


def _source_mapping() -> dict[str, object]:
    return {
        "publisher": "Controlled Test Publisher",
        "source_tier": "OFFICIAL_INSTITUTION",
        "source_type": "OFFICIAL_STATISTICS",
        "provider_series_id": "TEST-SERIES-001",
    }


def _entry(
    *,
    market_series_id: str,
    series_type: str,
    identity: dict[str, object],
) -> dict[str, object]:
    return {
        "market_series_id": market_series_id,
        "series_type": series_type,
        "display_label": f"Test {series_type}",
        "identity": identity,
        "source_mapping": _source_mapping(),
        "expected_publication_frequency": "BUSINESS_DAILY",
        "active_from": "2026-01-01",
        "active_to": None,
        "notes": None,
    }


def _all_family_entries() -> list[dict[str, object]]:
    return [
        _entry(
            market_series_id="MKS000000101",
            series_type="FX_REFERENCE_RATE",
            identity={
                "base_currency": "EUR",
                "quote_currency": "GBP",
                "convention_ref": "market-data/fx-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000102",
            series_type="POLICY_RATE",
            identity={
                "authority": "European Central Bank",
                "jurisdiction": "Euro Area",
                "currency": "EUR",
                "rate_name": "Deposit Facility Rate",
                "convention_ref": "market-data/policy-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000103",
            series_type="GOVERNMENT_YIELD",
            identity={
                "sovereign": "Federal Republic of Germany",
                "jurisdiction": "Germany",
                "currency": "EUR",
                "tenor_months": 120,
                "benchmark_ref": "German sovereign 10Y",
                "convention_ref": "market-data/gov-yield-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000104",
            series_type="SWAP_RATE",
            identity={
                "currency": "EUR",
                "tenor_months": 60,
                "floating_rate_ref": "EURIBOR-6M",
                "fixed_leg_convention_ref": "EUR-IRS-fixed-v1",
                "convention_ref": "market-data/swap-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000105",
            series_type="CREDIT_SPREAD",
            identity={
                "benchmark_family": "European Corporate Credit",
                "currency": "EUR",
                "credit_universe": "Investment Grade",
                "rating_segment": None,
                "sector_segment": None,
                "spread_measure": "OAS",
                "convention_ref": "market-data/credit-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000106",
            series_type="EQUITY_INDEX",
            identity={
                "index_name": "STOXX Europe 600",
                "universe": "Europe",
                "index_variant_ref": "PRICE",
                "methodology_ref": "market-data/equity-v1",
            },
        ),
        _entry(
            market_series_id="MKS000000107",
            series_type="VOLATILITY_INDEX",
            identity={
                "index_name": "European Equity Volatility",
                "underlying_ref": "STOXX Europe 600",
                "horizon_days": None,
                "methodology_ref": "market-data/vol-v1",
            },
        ),
    ]


def _catalog_payload() -> dict[str, object]:
    return {
        "catalog_version": CATALOG_VERSION,
        "series": _all_family_entries(),
    }


def test_committed_reference_catalog_is_valid_and_empty() -> None:
    catalog = load_market_series_catalog(
        Path("data/reference/market_series_catalog.json")
    )

    assert catalog.catalog_version == CATALOG_VERSION
    assert catalog.entries == ()


def test_catalog_parses_all_seven_market_families() -> None:
    catalog = parse_market_series_catalog(
        _catalog_payload()
    )

    assert tuple(
        entry.market_series.series_type
        for entry in catalog.entries
    ) == (
        MarketSeriesType.FX_REFERENCE_RATE,
        MarketSeriesType.POLICY_RATE,
        MarketSeriesType.GOVERNMENT_YIELD,
        MarketSeriesType.SWAP_RATE,
        MarketSeriesType.CREDIT_SPREAD,
        MarketSeriesType.EQUITY_INDEX,
        MarketSeriesType.VOLATILITY_INDEX,
    )

    assert tuple(
        type(entry.definition)
        for entry in catalog.entries
    ) == (
        FXReferenceRateDefinitionRecord,
        PolicyRateDefinitionRecord,
        GovernmentYieldDefinitionRecord,
        SwapRateDefinitionRecord,
        CreditSpreadDefinitionRecord,
        EquityIndexDefinitionRecord,
        VolatilityIndexDefinitionRecord,
    )


def test_catalog_parses_reference_source_mapping() -> None:
    catalog = parse_market_series_catalog(
        _catalog_payload()
    )

    mapping = catalog.entries[0].source_mapping

    assert mapping.publisher == "Controlled Test Publisher"
    assert mapping.source_tier is SourceTier.OFFICIAL_INSTITUTION
    assert mapping.source_type is SourceType.OFFICIAL_STATISTICS
    assert mapping.provider_series_id == "TEST-SERIES-001"


def test_catalog_parses_frequency_and_activity_dates() -> None:
    catalog = parse_market_series_catalog(
        _catalog_payload()
    )

    entry = catalog.entries[0]

    assert (
        entry.expected_publication_frequency
        is PublicationFrequency.BUSINESS_DAILY
    )
    assert entry.active_from is not None
    assert entry.active_from.isoformat() == "2026-01-01"
    assert entry.active_to is None


def test_catalog_rejects_unknown_top_level_fields() -> None:
    payload = _catalog_payload()
    payload["unexpected"] = True

    with pytest.raises(
        ValueError,
        match="unexpected keys",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_unsupported_version() -> None:
    payload = _catalog_payload()
    payload["catalog_version"] = 2

    with pytest.raises(
        ValueError,
        match="Unsupported market-series catalog version",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_duplicate_market_series_ids() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    duplicate = deepcopy(entries[0])
    entries.append(duplicate)

    with pytest.raises(
        ValueError,
        match="duplicate market_series_id",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_wrong_identity_shape_for_type() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    policy_entry = entries[1]
    assert isinstance(policy_entry, dict)

    identity = policy_entry["identity"]
    assert isinstance(identity, dict)

    identity["tenor_months"] = 24

    with pytest.raises(
        ValueError,
        match="unexpected keys",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_active_to_before_active_from() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    first_entry = entries[0]
    assert isinstance(first_entry, dict)

    first_entry["active_to"] = "2025-12-31"

    with pytest.raises(
        ValueError,
        match="active_to must be on or after active_from",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_blank_provider_series_id() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    first_entry = entries[0]
    assert isinstance(first_entry, dict)

    mapping = first_entry["source_mapping"]
    assert isinstance(mapping, dict)

    mapping["provider_series_id"] = "   "

    with pytest.raises(
        ValueError,
        match="provider_series_id must not be blank",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_invalid_source_tier_name() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    first_entry = entries[0]
    assert isinstance(first_entry, dict)

    mapping = first_entry["source_mapping"]
    assert isinstance(mapping, dict)

    mapping["source_tier"] = "UNCONTROLLED"

    with pytest.raises(
        ValueError,
        match="source_tier has unsupported value",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_duplicate_semantic_identity() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    duplicate = deepcopy(entries[0])
    assert isinstance(duplicate, dict)
    duplicate["market_series_id"] = "MKS000000108"
    duplicate["display_label"] = "Duplicate economic series"

    entries.append(duplicate)

    with pytest.raises(
        ValueError,
        match="Duplicate canonical FX reference-rate identity",
    ):
        parse_market_series_catalog(payload)


def test_catalog_rejects_noncanonical_iso_date_format() -> None:
    payload = _catalog_payload()
    entries = payload["series"]
    assert isinstance(entries, list)

    first_entry = entries[0]
    assert isinstance(first_entry, dict)

    first_entry["active_from"] = "20260101"

    with pytest.raises(
        ValueError,
        match="active_from must use ISO YYYY-MM-DD format",
    ):
        parse_market_series_catalog(payload)


def test_catalog_file_loader_rejects_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate-key.json"
    path.write_text(
        (
            '{"catalog_version":1,'
            '"catalog_version":2,'
            '"series":[]}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate JSON object key 'catalog_version'",
    ):
        load_market_series_catalog(path)


def test_catalog_file_loader_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        "{not-valid-json",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Invalid JSON in market-series catalog",
    ):
        load_market_series_catalog(path)


def test_catalog_json_round_trip_preserves_payload(
    tmp_path: Path,
) -> None:
    payload = _catalog_payload()
    path = tmp_path / "catalog.json"

    path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    catalog = load_market_series_catalog(path)

    assert len(catalog.entries) == 7
