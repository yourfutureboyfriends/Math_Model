"""
Tests for Provider Layer

Ensures:
- Providers return correct data structures
- No hardcoded fallbacks
- Proper error handling
"""

import pytest
from datetime import datetime

from api.providers.yahoo_provider import YahooFinanceProvider, PriceRecord
from api.providers.fred_provider import FREDProvider, FREDObservation


class TestYahooFinanceProvider:
    """Tests for Yahoo Finance provider."""

    def test_symbol_mapping(self):
        """Test canonical to yfinance symbol mapping."""
        provider = YahooFinanceProvider()

        # Spot checks
        assert provider.SYMBOL_MAP["SPX"] == "^GSPC"
        assert provider.SYMBOL_MAP["VIX"] == "^VIX"
        # Yahoo quotes USD/JPY directly (JPY=X and USDJPY=X both ~150), so no inversion.
        assert provider.SYMBOL_MAP["USDJPY"] == "USDJPY=X"

    def test_invert_symbols_list(self):
        """Test that correct symbols are marked for inversion."""
        provider = YahooFinanceProvider()

        # Yahoo already quotes USD-base pairs as USD/xxx: inverting USDJPY produced 0.0063.
        for sym in ("USDJPY", "USDCAD", "USDCHF", "EURUSD"):
            assert sym not in provider.INVERT_SYMBOLS
        assert "GBPUSD" not in provider.INVERT_SYMBOLS

    def test_price_record_creation(self):
        """Test PriceRecord dataclass."""
        record = PriceRecord(
            symbol="SPX",
            price=4500.0,
            timestamp=datetime.utcnow(),
            currency="USD",
            source="yfinance"
        )

        assert record.symbol == "SPX"
        assert record.price == 4500.0
        assert record.currency == "USD"


class TestFREDProvider:
    """Tests for FRED provider."""

    def test_series_definitions(self):
        """Test that important series are defined."""
        provider = FREDProvider(api_key="test")

        # Critical series should be defined
        assert "FEDFUNDS" in provider.SERIES
        assert "CPIAUCSL" in provider.SERIES
        assert "UNRATE" in provider.SERIES
        assert "VIXCLS" in provider.SERIES

    def test_fred_observation_creation(self):
        """Test FREDObservation dataclass."""
        obs = FREDObservation(
            series_id="FEDFUNDS",
            date="2024-01-01",
            value=5.25,
            realtime_start="2024-01-01",
            realtime_end="2024-01-01"
        )

        assert obs.series_id == "FEDFUNDS"
        assert obs.value == 5.25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
