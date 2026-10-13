"""
Price Validation — Ensure price data is valid before caching.
"""

import logging
import math
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PriceValidationError(Exception):
    """Raised when price validation fails."""
    pass


def validate_price(price_data: Dict[str, Any]) -> Optional[str]:
    """
    Validate a single price record.

    Returns:
        Error message if invalid, None if valid.
    """
    # Check required fields
    required = ["symbol", "price", "timestamp"]
    for field in required:
        if field not in price_data:
            return f"Missing required field: {field}"

    # Validate price value
    price = price_data.get("price")
    if price is None:
        return "Price is None"

    if not math.isfinite(price):
        return f"Price is NaN/Inf: {price}"

    if price <= 0:
        return f"Price must be positive: {price}"

    # Validate timestamp
    timestamp = price_data.get("timestamp")
    if not timestamp:
        return "Timestamp is empty"

    return None


def validate_price_batch(prices: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """
    Validate a batch of price records.

    Returns:
        Dict mapping symbol to error message for invalid records.
    """
    errors = {}
    for symbol, data in prices.items():
        error = validate_price(data)
        if error:
            errors[symbol] = error
    return errors


def check_stale_prices(
    prices: Dict[str, Dict[str, Any]],
    max_age_minutes: int = 5
) -> List[str]:
    """
    Check which prices are stale based on timestamp.

    Returns:
        List of stale symbols.
    """
    stale = []
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

    for symbol, data in prices.items():
        ts_str = data.get("timestamp")
        if not ts_str:
            stale.append(symbol)
            continue

        try:
            # Parse ISO timestamp
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo:
                ts = ts.replace(tzinfo=None)

            if ts < cutoff:
                stale.append(symbol)
        except (ValueError, TypeError):
            stale.append(symbol)

    return stale
