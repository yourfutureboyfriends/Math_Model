"""
Price Normalization — Convert raw prices to canonical format.

Handles:
- Symbol standardization
- Timestamp normalization (UTC)
- Price validation (NaN/Inf check)
- Currency standardization
"""

import logging
import math
from typing import Dict, Optional, Any

from api.providers.yahoo_provider import PriceRecord

logger = logging.getLogger(__name__)


def normalize_price(record: PriceRecord) -> Optional[Dict[str, Any]]:
    """
    Normalize a single price record to canonical format.

    Returns:
        Dict with normalized fields or None if invalid.
    """
    # Validate price
    if not math.isfinite(record.price):
        logger.warning(f"Invalid price for {record.symbol}: {record.price}")
        return None

    if record.price <= 0:
        logger.warning(f"Negative/zero price for {record.symbol}: {record.price}")
        return None

    # Normalize timestamp to UTC ISO format
    timestamp_iso = record.timestamp.isoformat() + "Z"

    return {
        "symbol": record.symbol.upper(),
        "price": float(record.price),
        "timestamp": timestamp_iso,
        "currency": record.currency.upper() if record.currency else "USD",
        "source": record.source,
    }


def normalize_prices(records: Dict[str, PriceRecord]) -> Dict[str, Dict[str, Any]]:
    """
    Normalize multiple price records.

    Returns:
        Dict mapping symbol to normalized record.
    """
    results = {}
    for symbol, record in records.items():
        normalized = normalize_price(record)
        if normalized:
            results[symbol] = normalized
    return results


def calculate_price_changes(
    current: Dict[str, float],
    previous: Dict[str, float]
) -> Dict[str, Optional[float]]:
    """
    Calculate percent changes between two price sets.

    Args:
        current: Dict of symbol -> price
        previous: Dict of symbol -> price

    Returns:
        Dict of symbol -> change_pct (e.g., 0.0114 = +1.14%)
    """
    changes = {}
    for symbol, current_price in current.items():
        prev_price = previous.get(symbol)
        if prev_price and prev_price > 0:
            changes[symbol] = (current_price - prev_price) / prev_price
        else:
            changes[symbol] = None
    return changes
