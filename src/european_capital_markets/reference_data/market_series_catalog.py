"""Controlled market-series reference catalog.

This module governs selection metadata for concrete canonical market-series
instances. It deliberately does not create SourceRecord or EvidenceRecord
objects: observation-level provenance remains in the source/evidence layer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from european_capital_markets.domain.market_data import (
    CreditSpreadDefinitionRecord,
    EquityIndexDefinitionRecord,
    FXReferenceRateDefinitionRecord,
    GovernmentYieldDefinitionRecord,
    MarketSeriesDefinitionRecord,
    MarketSeriesRecord,
    PolicyRateDefinitionRecord,
    SwapRateDefinitionRecord,
    VolatilityIndexDefinitionRecord,
    validate_market_series_bundle,
)
from european_capital_markets.domain.taxonomy import (
    MarketSeriesType,
    SourceTier,
    SourceType,
)

CATALOG_VERSION = 1


class PublicationFrequency(StrEnum):
    """Controlled expected publication/update frequencies."""

    BUSINESS_DAILY = "BUSINESS_DAILY"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    IRREGULAR = "IRREGULAR"


@dataclass(frozen=True, slots=True)
class MarketSeriesSourceMapping:
    """Reference-level source/provider selection metadata.

    This is not observation evidence. A populated canonical observation still
    requires normal SourceRecord and EvidenceRecord lineage.
    """

    publisher: str
    source_tier: SourceTier
    source_type: SourceType
    provider_series_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.publisher, "publisher")

        if self.provider_series_id is not None:
            _require_non_blank(
                self.provider_series_id,
                "provider_series_id",
            )


@dataclass(frozen=True, slots=True)
class MarketSeriesCatalogEntry:
    """One selected concrete canonical market-series definition."""

    market_series: MarketSeriesRecord
    definition: MarketSeriesDefinitionRecord
    source_mapping: MarketSeriesSourceMapping
    expected_publication_frequency: PublicationFrequency
    active_from: date | None = None
    active_to: date | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if (
            self.active_from is not None
            and self.active_to is not None
            and self.active_to < self.active_from
        ):
            raise ValueError(
                "active_to must be on or after active_from."
            )

        if self.notes is not None:
            _require_non_blank(self.notes, "notes")


@dataclass(frozen=True, slots=True)
class MarketSeriesCatalog:
    """Validated controlled reference-series catalog."""

    catalog_version: int
    entries: tuple[MarketSeriesCatalogEntry, ...]

    def __post_init__(self) -> None:
        if self.catalog_version != CATALOG_VERSION:
            raise ValueError(
                "Unsupported market-series catalog version: "
                f"{self.catalog_version!r}."
            )

        series_ids = tuple(
            entry.market_series.market_series_id
            for entry in self.entries
        )

        if len(series_ids) != len(set(series_ids)):
            raise ValueError(
                "Market-series catalog contains duplicate "
                "market_series_id values."
            )

        _validate_catalog_domain_bundle(self.entries)


_TOP_LEVEL_KEYS = frozenset(
    {
        "catalog_version",
        "series",
    }
)

_ENTRY_KEYS = frozenset(
    {
        "market_series_id",
        "series_type",
        "display_label",
        "identity",
        "source_mapping",
        "expected_publication_frequency",
        "active_from",
        "active_to",
        "notes",
    }
)

_SOURCE_MAPPING_KEYS = frozenset(
    {
        "publisher",
        "source_tier",
        "source_type",
        "provider_series_id",
    }
)

_IDENTITY_KEYS: dict[MarketSeriesType, frozenset[str]] = {
    MarketSeriesType.FX_REFERENCE_RATE: frozenset(
        {
            "base_currency",
            "quote_currency",
            "convention_ref",
        }
    ),
    MarketSeriesType.POLICY_RATE: frozenset(
        {
            "authority",
            "jurisdiction",
            "currency",
            "rate_name",
            "convention_ref",
        }
    ),
    MarketSeriesType.GOVERNMENT_YIELD: frozenset(
        {
            "sovereign",
            "jurisdiction",
            "currency",
            "tenor_months",
            "benchmark_ref",
            "convention_ref",
        }
    ),
    MarketSeriesType.SWAP_RATE: frozenset(
        {
            "currency",
            "tenor_months",
            "floating_rate_ref",
            "fixed_leg_convention_ref",
            "convention_ref",
        }
    ),
    MarketSeriesType.CREDIT_SPREAD: frozenset(
        {
            "benchmark_family",
            "currency",
            "credit_universe",
            "rating_segment",
            "sector_segment",
            "spread_measure",
            "convention_ref",
        }
    ),
    MarketSeriesType.EQUITY_INDEX: frozenset(
        {
            "index_name",
            "universe",
            "index_variant_ref",
            "methodology_ref",
        }
    ),
    MarketSeriesType.VOLATILITY_INDEX: frozenset(
        {
            "index_name",
            "underlying_ref",
            "horizon_days",
            "methodology_ref",
        }
    ),
}


def _reject_duplicate_json_object_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON object key {key!r}."
            )

        result[key] = value

    return result


def load_market_series_catalog(
    path: str | Path,
) -> MarketSeriesCatalog:
    """Load and validate one UTF-8 JSON market-series catalog."""

    catalog_path = Path(path)

    try:
        with catalog_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            payload = json.load(
                handle,
                object_pairs_hook=_reject_duplicate_json_object_keys,
            )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in market-series catalog {catalog_path}."
        ) from exc

    return parse_market_series_catalog(payload)


def parse_market_series_catalog(
    payload: object,
) -> MarketSeriesCatalog:
    """Parse and validate one already-decoded catalog payload."""

    root = _require_mapping(
        payload,
        "catalog",
    )
    _require_exact_keys(
        root,
        _TOP_LEVEL_KEYS,
        "catalog",
    )

    catalog_version = root["catalog_version"]

    if type(catalog_version) is not int:
        raise ValueError(
            "catalog_version must be an integer."
        )

    raw_series = root["series"]

    if not isinstance(raw_series, list):
        raise ValueError("series must be a list.")

    entries = tuple(
        _parse_entry(raw_entry, index)
        for index, raw_entry in enumerate(raw_series)
    )

    return MarketSeriesCatalog(
        catalog_version=catalog_version,
        entries=entries,
    )


def _parse_entry(
    payload: object,
    index: int,
) -> MarketSeriesCatalogEntry:
    context = f"series[{index}]"
    raw = _require_mapping(payload, context)
    _require_exact_keys(
        raw,
        _ENTRY_KEYS,
        context,
    )

    market_series_id = _require_string(
        raw["market_series_id"],
        f"{context}.market_series_id",
    )

    series_type = _parse_enum(
        MarketSeriesType,
        raw["series_type"],
        f"{context}.series_type",
    )

    display_label = _require_string(
        raw["display_label"],
        f"{context}.display_label",
    )

    identity = _require_mapping(
        raw["identity"],
        f"{context}.identity",
    )

    _require_exact_keys(
        identity,
        _IDENTITY_KEYS[series_type],
        f"{context}.identity",
    )

    source_mapping = _parse_source_mapping(
        raw["source_mapping"],
        f"{context}.source_mapping",
    )

    frequency = _parse_enum(
        PublicationFrequency,
        raw["expected_publication_frequency"],
        f"{context}.expected_publication_frequency",
    )

    active_from = _parse_optional_date(
        raw["active_from"],
        f"{context}.active_from",
    )
    active_to = _parse_optional_date(
        raw["active_to"],
        f"{context}.active_to",
    )

    notes = _parse_optional_string(
        raw["notes"],
        f"{context}.notes",
    )

    market_series = MarketSeriesRecord(
        market_series_id=market_series_id,
        series_type=series_type,
        series_label=display_label,
    )

    definition = _parse_definition(
        market_series_id,
        series_type,
        identity,
    )

    return MarketSeriesCatalogEntry(
        market_series=market_series,
        definition=definition,
        source_mapping=source_mapping,
        expected_publication_frequency=frequency,
        active_from=active_from,
        active_to=active_to,
        notes=notes,
    )


def _parse_source_mapping(
    payload: object,
    context: str,
) -> MarketSeriesSourceMapping:
    raw = _require_mapping(payload, context)
    _require_exact_keys(
        raw,
        _SOURCE_MAPPING_KEYS,
        context,
    )

    publisher = _require_string(
        raw["publisher"],
        f"{context}.publisher",
    )

    source_tier = _parse_enum(
        SourceTier,
        raw["source_tier"],
        f"{context}.source_tier",
    )

    source_type = _parse_enum(
        SourceType,
        raw["source_type"],
        f"{context}.source_type",
    )

    provider_series_id = _parse_optional_string(
        raw["provider_series_id"],
        f"{context}.provider_series_id",
    )

    return MarketSeriesSourceMapping(
        publisher=publisher,
        source_tier=source_tier,
        source_type=source_type,
        provider_series_id=provider_series_id,
    )


def _parse_definition(
    market_series_id: str,
    series_type: MarketSeriesType,
    identity: Mapping[str, Any],
) -> MarketSeriesDefinitionRecord:
    if series_type is MarketSeriesType.FX_REFERENCE_RATE:
        return FXReferenceRateDefinitionRecord(
            market_series_id=market_series_id,
            base_currency=_identity_string(
                identity,
                "base_currency",
            ),
            quote_currency=_identity_string(
                identity,
                "quote_currency",
            ),
            convention_ref=_identity_string(
                identity,
                "convention_ref",
            ),
        )

    if series_type is MarketSeriesType.POLICY_RATE:
        return PolicyRateDefinitionRecord(
            market_series_id=market_series_id,
            authority=_identity_string(
                identity,
                "authority",
            ),
            jurisdiction=_identity_string(
                identity,
                "jurisdiction",
            ),
            currency=_identity_string(
                identity,
                "currency",
            ),
            rate_name=_identity_string(
                identity,
                "rate_name",
            ),
            convention_ref=_identity_string(
                identity,
                "convention_ref",
            ),
        )

    if series_type is MarketSeriesType.GOVERNMENT_YIELD:
        return GovernmentYieldDefinitionRecord(
            market_series_id=market_series_id,
            sovereign=_identity_string(
                identity,
                "sovereign",
            ),
            jurisdiction=_identity_string(
                identity,
                "jurisdiction",
            ),
            currency=_identity_string(
                identity,
                "currency",
            ),
            tenor_months=_identity_int(
                identity,
                "tenor_months",
            ),
            benchmark_ref=_identity_string(
                identity,
                "benchmark_ref",
            ),
            convention_ref=_identity_string(
                identity,
                "convention_ref",
            ),
        )

    if series_type is MarketSeriesType.SWAP_RATE:
        return SwapRateDefinitionRecord(
            market_series_id=market_series_id,
            currency=_identity_string(
                identity,
                "currency",
            ),
            tenor_months=_identity_int(
                identity,
                "tenor_months",
            ),
            floating_rate_ref=_identity_string(
                identity,
                "floating_rate_ref",
            ),
            fixed_leg_convention_ref=_identity_string(
                identity,
                "fixed_leg_convention_ref",
            ),
            convention_ref=_identity_string(
                identity,
                "convention_ref",
            ),
        )

    if series_type is MarketSeriesType.CREDIT_SPREAD:
        return CreditSpreadDefinitionRecord(
            market_series_id=market_series_id,
            benchmark_family=_identity_string(
                identity,
                "benchmark_family",
            ),
            currency=_identity_string(
                identity,
                "currency",
            ),
            credit_universe=_identity_string(
                identity,
                "credit_universe",
            ),
            spread_measure=_identity_string(
                identity,
                "spread_measure",
            ),
            convention_ref=_identity_string(
                identity,
                "convention_ref",
            ),
            rating_segment=_identity_optional_string(
                identity,
                "rating_segment",
            ),
            sector_segment=_identity_optional_string(
                identity,
                "sector_segment",
            ),
        )

    if series_type is MarketSeriesType.EQUITY_INDEX:
        return EquityIndexDefinitionRecord(
            market_series_id=market_series_id,
            index_name=_identity_string(
                identity,
                "index_name",
            ),
            universe=_identity_string(
                identity,
                "universe",
            ),
            index_variant_ref=_identity_string(
                identity,
                "index_variant_ref",
            ),
            methodology_ref=_identity_string(
                identity,
                "methodology_ref",
            ),
        )

    if series_type is MarketSeriesType.VOLATILITY_INDEX:
        return VolatilityIndexDefinitionRecord(
            market_series_id=market_series_id,
            index_name=_identity_string(
                identity,
                "index_name",
            ),
            underlying_ref=_identity_string(
                identity,
                "underlying_ref",
            ),
            methodology_ref=_identity_string(
                identity,
                "methodology_ref",
            ),
            horizon_days=_identity_optional_int(
                identity,
                "horizon_days",
            ),
        )

    raise AssertionError(
        f"Unhandled market-series type: {series_type!r}."
    )


def _validate_catalog_domain_bundle(
    entries: tuple[MarketSeriesCatalogEntry, ...],
) -> None:
    market_series = tuple(
        entry.market_series
        for entry in entries
    )

    fx_reference_rates = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            FXReferenceRateDefinitionRecord,
        )
    )
    policy_rates = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            PolicyRateDefinitionRecord,
        )
    )
    government_yields = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            GovernmentYieldDefinitionRecord,
        )
    )
    swap_rates = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            SwapRateDefinitionRecord,
        )
    )
    credit_spreads = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            CreditSpreadDefinitionRecord,
        )
    )
    equity_indices = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            EquityIndexDefinitionRecord,
        )
    )
    volatility_indices = tuple(
        entry.definition
        for entry in entries
        if isinstance(
            entry.definition,
            VolatilityIndexDefinitionRecord,
        )
    )

    validate_market_series_bundle(
        market_series,
        fx_reference_rates,
        policy_rates=policy_rates,
        government_yields=government_yields,
        swap_rates=swap_rates,
        credit_spreads=credit_spreads,
        equity_indices=equity_indices,
        volatility_indices=volatility_indices,
    )


def _require_mapping(
    value: object,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"{context} must be an object."
        )

    if not all(
        isinstance(key, str)
        for key in value
    ):
        raise ValueError(
            f"{context} keys must be strings."
        )

    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = frozenset(value)

    if actual == expected:
        return

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    details: list[str] = []

    if missing:
        details.append(
            f"missing keys {missing!r}"
        )

    if unexpected:
        details.append(
            f"unexpected keys {unexpected!r}"
        )

    raise ValueError(
        f"{context} has invalid structure: "
        + "; ".join(details)
        + "."
    )


def _require_string(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string."
        )

    _require_non_blank(
        value,
        field_name,
    )

    return value


def _parse_optional_string(
    value: object,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    return _require_string(
        value,
        field_name,
    )


def _require_non_blank(
    value: str,
    field_name: str,
) -> None:
    if not value.strip():
        raise ValueError(
            f"{field_name} must not be blank."
        )


def _parse_enum(
    enum_type: type[StrEnum] | type[SourceTier] | type[SourceType],
    value: object,
    field_name: str,
) -> Any:
    enum_name = _require_string(
        value,
        field_name,
    )

    try:
        return enum_type[enum_name]
    except KeyError as exc:
        raise ValueError(
            f"{field_name} has unsupported value "
            f"{enum_name!r}."
        ) from exc


def _parse_optional_date(
    value: object,
    field_name: str,
) -> date | None:
    if value is None:
        return None

    raw = _require_string(
        value,
        field_name,
    )

    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must use ISO YYYY-MM-DD format."
        ) from exc

    if parsed.isoformat() != raw:
        raise ValueError(
            f"{field_name} must use ISO YYYY-MM-DD format."
        )

    return parsed


def _identity_string(
    identity: Mapping[str, Any],
    key: str,
) -> str:
    return _require_string(
        identity[key],
        f"identity.{key}",
    )


def _identity_optional_string(
    identity: Mapping[str, Any],
    key: str,
) -> str | None:
    return _parse_optional_string(
        identity[key],
        f"identity.{key}",
    )


def _identity_int(
    identity: Mapping[str, Any],
    key: str,
) -> int:
    value = identity[key]

    if type(value) is not int:
        raise ValueError(
            f"identity.{key} must be an integer."
        )

    return value


def _identity_optional_int(
    identity: Mapping[str, Any],
    key: str,
) -> int | None:
    value = identity[key]

    if value is None:
        return None

    return _identity_int(
        identity,
        key,
    )
