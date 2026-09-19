from datetime import UTC, date, datetime
from decimal import Decimal

from european_capital_markets.domain.lineage import ObservationRecord
from european_capital_markets.domain.taxonomy import (
    EntityType,
    ValueClass,
    VerificationState,
)
from european_capital_markets.persistence.writer import _encode_scalar_value


def _observation(value: object) -> ObservationRecord:
    return ObservationRecord(
        observation_id="OBS000000001",
        subject_type=EntityType.ISSUER,
        subject_id="ISS000000001",
        field_name="test.value",
        as_of_date=date(2026, 9, 18),
        verification_state=VerificationState.PENDING,
        value=value,  # type: ignore[arg-type]
        value_class=ValueClass.ASSUMED,
        derivation_ref="tests/persistence-writer",
    )


def test_boolean_uses_boolean_slot_not_integer_slot() -> None:
    encoded = _encode_scalar_value(_observation(True))

    assert encoded["scalar_type"] == "BOOLEAN"
    assert encoded["boolean_value"] is True
    assert encoded["integer_value"] is None


def test_integer_uses_exact_integer_slot() -> None:
    value = 123456789012345678901234567890

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "INTEGER"
    assert encoded["integer_value"] == value
    assert encoded["decimal_value"] is None


def test_decimal_uses_decimal_slot_without_float_conversion() -> None:
    value = Decimal(
        "12345678901234567890.123456789012345678901234567890"
    )

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DECIMAL"
    assert encoded["decimal_value"] == value
    assert isinstance(encoded["decimal_value"], Decimal)


def test_datetime_uses_datetime_slot_not_date_slot() -> None:
    value = datetime(2026, 9, 18, 14, 30, tzinfo=UTC)

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DATETIME"
    assert encoded["datetime_value"] == value
    assert encoded["date_value"] is None


def test_date_uses_date_slot() -> None:
    value = date(2026, 9, 18)

    encoded = _encode_scalar_value(_observation(value))

    assert encoded["scalar_type"] == "DATE"
    assert encoded["date_value"] == value


def test_text_uses_text_slot() -> None:
    encoded = _encode_scalar_value(_observation("canonical value"))

    assert encoded["scalar_type"] == "TEXT"
    assert encoded["text_value"] == "canonical value"


def test_phase1_market_definitions_fail_before_transaction_begins() -> None:
    from european_capital_markets.domain.dataset import CanonicalDataset
    from european_capital_markets.domain.market_data import (
        CreditSpreadDefinitionRecord,
        EquityIndexDefinitionRecord,
        GovernmentYieldDefinitionRecord,
        MarketSeriesRecord,
        PolicyRateDefinitionRecord,
        SwapRateDefinitionRecord,
        VolatilityIndexDefinitionRecord,
    )
    from european_capital_markets.domain.taxonomy import MarketSeriesType
    from european_capital_markets.persistence.writer import (
        persist_canonical_dataset,
    )

    cases = (
        (
            "policy_rates",
            "POLICY_RATE",
            MarketSeriesType.POLICY_RATE,
            PolicyRateDefinitionRecord(
                market_series_id="MKS000000100",
                authority="European Central Bank",
                jurisdiction="Euro Area",
                currency="EUR",
                rate_name="Deposit Facility Rate",
                convention_ref="market-data/ecb/policy-rate-v1",
            ),
        ),
        (
            "government_yields",
            "GOVERNMENT_YIELD",
            MarketSeriesType.GOVERNMENT_YIELD,
            GovernmentYieldDefinitionRecord(
                market_series_id="MKS000000100",
                sovereign="Federal Republic of Germany",
                jurisdiction="Germany",
                currency="EUR",
                tenor_months=120,
                benchmark_ref="German sovereign 10Y benchmark",
                convention_ref="market-data/government-yield-v1",
            ),
        ),
        (
            "swap_rates",
            "SWAP_RATE",
            MarketSeriesType.SWAP_RATE,
            SwapRateDefinitionRecord(
                market_series_id="MKS000000100",
                currency="EUR",
                tenor_months=60,
                floating_rate_ref="EURIBOR-6M",
                fixed_leg_convention_ref="EUR-IRS-fixed-leg-v1",
                convention_ref="market-data/swap-rate-v1",
            ),
        ),
        (
            "credit_spreads",
            "CREDIT_SPREAD",
            MarketSeriesType.CREDIT_SPREAD,
            CreditSpreadDefinitionRecord(
                market_series_id="MKS000000100",
                benchmark_family="European Corporate Credit",
                currency="EUR",
                credit_universe="Investment Grade",
                spread_measure="OAS",
                convention_ref="market-data/credit-spread-v1",
            ),
        ),
        (
            "equity_indices",
            "EQUITY_INDEX",
            MarketSeriesType.EQUITY_INDEX,
            EquityIndexDefinitionRecord(
                market_series_id="MKS000000100",
                index_name="STOXX Europe 600",
                universe="Europe",
                index_variant_ref="PRICE",
                methodology_ref="market-data/equity-index-v1",
            ),
        ),
        (
            "volatility_indices",
            "VOLATILITY_INDEX",
            MarketSeriesType.VOLATILITY_INDEX,
            VolatilityIndexDefinitionRecord(
                market_series_id="MKS000000100",
                index_name="European Equity Volatility",
                underlying_ref="STOXX Europe 600",
                methodology_ref="market-data/volatility-index-v1",
                horizon_days=30,
            ),
        ),
    )

    class BeginProbe:
        def __init__(self) -> None:
            self.begin_called = False

        def begin(self) -> None:
            self.begin_called = True
            raise AssertionError(
                "Persistence transaction must not begin."
            )

    for attribute_name, family_name, series_type, definition in cases:
        engine = BeginProbe()

        dataset = CanonicalDataset(
            market_series=(
                MarketSeriesRecord(
                    market_series_id="MKS000000100",
                    series_type=series_type,
                ),
            ),
            **{
                attribute_name: (definition,),
            },
        )

        try:
            persist_canonical_dataset(
                engine,  # type: ignore[arg-type]
                dataset,
            )
        except ValueError as exc:
            message = str(exc)
            assert (
                "Canonical PostgreSQL persistence does not yet support"
                in message
            )
            assert family_name in message
        else:
            raise AssertionError(
                f"{family_name} unexpectedly reached persistence."
            )

        assert engine.begin_called is False
