"""Chart bars: interval/period limits are enforced, not silently changed."""
import pytest

from api import market_bars as mb


def test_limits():
    assert mb.allowed("1h", "1y") and not mb.allowed("1h", "2y")      # Yahoo: 730 days of hourly bars
    assert mb.allowed("5m", "1mo") and not mb.allowed("5m", "3mo")
    assert mb.allowed("1d", "max") and mb.allowed("1mo", "max")
    assert "max" not in mb.allowed_periods("15m")
    with pytest.raises(ValueError):
        mb.bars("AAPL", "5m", "1y")
