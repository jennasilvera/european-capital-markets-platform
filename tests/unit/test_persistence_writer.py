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



def test_phase1_market_definitions_enter_persistence_transaction(
    monkeypatch,
) -> None:
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

    persisted: list[tuple[object, CanonicalDataset]] = []

    class ConnectionProbe:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> None:
            self.statements.append(str(statement))

    class TransactionProbe:
        def __init__(self, connection: ConnectionProbe) -> None:
            self.connection = connection

        def __enter__(self) -> ConnectionProbe:
            return self.connection

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> bool:
            return False

    class EngineProbe:
        def __init__(self) -> None:
            self.begin_called = False
            self.connection = ConnectionProbe()

        def begin(self) -> TransactionProbe:
            self.begin_called = True
            return TransactionProbe(self.connection)

    def fake_persist(
        connection: object,
        dataset: CanonicalDataset,
    ) -> None:
        persisted.append((connection, dataset))

    monkeypatch.setattr(
        "european_capital_markets.persistence.writer."
        "_persist_validated_dataset",
        fake_persist,
    )

    for attribute_name, series_type, definition in cases:
        engine = EngineProbe()

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

        persist_canonical_dataset(
            engine,  # type: ignore[arg-type]
            dataset,
        )

        assert engine.begin_called is True
        assert persisted[-1] == (engine.connection, dataset)
        assert engine.connection.statements == [
            "SET CONSTRAINTS ALL IMMEDIATE",
        ]
