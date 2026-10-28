"""
FX Normalization — Convert FX rates to canonical USD-base format.

Ensures all FX rates use USD as base currency:
- EURUSD = 1.08 (1 USD = 0.925 EUR)
- USDJPY = 145 (1 USD = 145 JPY)

Handles:
- Rate inversion for quote currencies
- Validation of reasonable ranges
- Standardization to 6 decimal places
"""

import logging
import math
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# Canonical FX pairs with expected ranges (USD-base)
FX_RANGES = {
    # Wide plausibility bands in market quoting convention (units of quote currency per
    # 1 base). The old bands had GBPUSD at 0.60-1.00 ("GBP per USD") — the inverse of how
    # it is quoted — so every real cable print (~1.3) was flagged as bad data.
    "EURUSD": (0.80, 1.60),    # USD per EUR
    "GBPUSD": (1.00, 2.10),    # USD per GBP
    "USDJPY": (70, 250),       # JPY per USD
    "USDCAD": (0.95, 1.80),    # CAD per USD
    "USDCHF": (0.55, 1.30),    # CHF per USD
    "AUDUSD": (0.45, 1.10),    # USD per AUD
    "NZDUSD": (0.40, 0.95),    # USD per NZD
}


def normalize_fx_rate(pair: str, rate: float) -> Optional[Dict[str, Any]]:
    """
    Normalize an FX rate to canonical format.

    Args:
        pair: FX pair symbol (e.g., "EURUSD")
        rate: Raw exchange rate

    Returns:
        Normalized FX rate dict or None if invalid.
    """
    pair = pair.upper()

    # Validate rate
    if not math.isfinite(rate) or rate <= 0:
        logger.warning(f"Invalid FX rate for {pair}: {rate}")
        return None

    # Check expected ranges
    expected_range = FX_RANGES.get(pair)
    if expected_range:
        lo, hi = expected_range
        if not (lo <= rate <= hi):
            logger.warning(
                f"FX rate {pair}={rate} outside expected range [{lo}, {hi}]. "
                "May indicate wrong direction or bad data."
            )
            # Still return it, but logged

    return {
        "pair": pair,
        "rate": round(float(rate), 6),
        "base": pair[:3],    # EURUSD: base EUR, quote USD (was hard-coded "USD")
        "quote": pair[3:6],
        "inverted": False,  # Track if we had to invert
    }


def invert_fx_rate(pair: str, rate: float) -> Optional[Dict[str, Any]]:
    """
    Invert an FX rate (e.g., EURUSD from USD-EUR rate).

    Args:
        pair: Target pair (e.g., "EURUSD")
        rate: Raw rate that needs inversion

    Returns:
        Normalized inverted FX rate or None.
    """
    if not math.isfinite(rate) or rate == 0:
        logger.warning(f"Cannot invert FX rate for {pair}: {rate}")
        return None

    inverted_rate = 1.0 / rate
    result = normalize_fx_rate(pair, inverted_rate)
    if result:
        result["inverted"] = True
    return result


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    fx_rates: Dict[str, float]
) -> Optional[float]:
    """
    Convert amount between currencies using FX rates.

    Args:
        amount: Amount in from_currency
        from_currency: Source currency (e.g., "EUR")
        to_currency: Target currency (e.g., "USD")
        fx_rates: Dict of pair -> rate

    Returns:
        Converted amount or None.
    """
    if from_currency == to_currency:
        return amount

    # Try direct pair
    pair = f"{to_currency}{from_currency}"
    if pair in fx_rates:
        return amount * fx_rates[pair]

    # Try inverse pair
    pair = f"{from_currency}{to_currency}"
    if pair in fx_rates:
        return amount / fx_rates[pair]

    logger.warning(f"Cannot convert {from_currency} to {to_currency}: no rate")
    return None
