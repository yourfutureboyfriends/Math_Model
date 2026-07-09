"""
Tests for Normalization Layer

Ensures:
- Unit conversions are correct
- FX inversion is handled properly
- Timestamps are normalized to UTC
"""

import pytest
from datetime import datetime

from api.providers.yahoo_provider import PriceRecord
from api.normalization.prices import normalize_price, calculate_price_changes
from api.normalization.fx import normalize_fx_rate, invert_fx_rate
from api.normalization.macro_series import normalize_macro_value


class TestPriceNormalization:
    """Tests for price normalization."""

    def test_normalize_valid_price(self):
        """Test normalizing a valid price record."""
        record = PriceRecord(
            symbol="SPX",
            price=4500.0,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            currency="USD",
            source="yfinance"
        )

        normalized = normalize_price(record)

        assert normalized is not None
        assert normalized["symbol"] == "SPX"
        assert normalized["price"] == 4500.0
        assert normalized["currency"] == "USD"
        assert "timestamp" in normalized

    def test_normalize_invalid_price_nan(self):
        """Test that NaN prices are rejected."""
        record = PriceRecord(
            symbol="SPX",
            price=float("nan"),
            timestamp=datetime.utcnow(),
            currency="USD",
            source="yfinance"
        )

        normalized = normalize_price(record)
        assert normalized is None

    def test_normalize_invalid_price_zero(self):
        """Test that zero prices are rejected."""
        record = PriceRecord(
            symbol="SPX",
            price=0.0,
            timestamp=datetime.utcnow(),
            currency="USD",
            source="yfinance"
        )

        normalized = normalize_price(record)
        assert normalized is None

    def test_calculate_price_changes(self):
        """Test price change calculation."""
        current = {"SPX": 4500.0, "NDX": 15000.0}
        previous = {"SPX": 4455.0, "NDX": 14850.0}

        changes = calculate_price_changes(current, previous)

        # SPX: (4500 - 4455) / 4455 = ~1.01%
        assert changes["SPX"] == pytest.approx(0.0101, abs=0.001)
        # NDX: (15000 - 14850) / 14850 = ~1.01%
        assert changes["NDX"] == pytest.approx(0.0101, abs=0.001)


class TestFXNormalization:
    """Tests for FX normalization."""

    def test_normalize_fx_valid(self):
        """Test normalizing a valid FX rate."""
        result = normalize_fx_rate("EURUSD", 1.08)

        assert result is not None
        assert result["pair"] == "EURUSD"
        assert result["rate"] == pytest.approx(1.08, abs=0.001)
        assert result["base"] == "USD"

    def test_normalize_fx_invalid_nan(self):
        """Test that NaN FX rates are rejected."""
        result = normalize_fx_rate("EURUSD", float("nan"))
        assert result is None

    def test_invert_fx_rate(self):
        """Test FX rate inversion."""
        # If JPY=X returns 0.0067 (JPY per USD), inverted should be ~149
        result = invert_fx_rate("USDJPY", 0.0067)

        assert result is not None
        assert result["rate"] == pytest.approx(149.25, abs=0.1)
        assert result["inverted"] is True

    def test_fx_ranges_warning(self):
        """Test that out-of-range FX rates trigger warnings."""
        # USDJPY of 200 should trigger warning (range is 100-160)
        result = normalize_fx_rate("USDJPY", 200.0)

        # Should still return but logged warning
        assert result is not None
        assert result["rate"] == 200.0


class TestMacroNormalization:
    """Tests for macro series normalization."""

    def test_normalize_fed_funds(self):
        """Test normalizing Fed Funds rate."""
        result = normalize_macro_value("fed_funds", 5.25, "FRED:FEDFUNDS")

        assert result is not None
        assert result["metric"] == "fed_funds"
        assert result["value"] == 5.25
        assert result["unit"] == "percent"

    def test_normalize_hy_spread_conversion(self):
        """Test HY spread unit conversion (percent to bps)."""
        # FRED returns as percent (e.g., 2.83), should become 283 bps
        result = normalize_macro_value("hy_spread", 2.83, "FRED:BAMLH0A0HYM2")

        assert result is not None
        assert result["value"] == pytest.approx(283.0, abs=0.1)
        assert result["unit"] == "bps"

    def test_normalize_out_of_bounds(self):
        """Test that out-of-bounds values are rejected."""
        # Fed Funds of 100% should be rejected
        result = normalize_macro_value("fed_funds", 100.0, "FRED:FEDFUNDS")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
