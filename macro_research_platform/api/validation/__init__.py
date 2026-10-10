"""
Validation Layer — Validate normalized data before it enters shared state.

Checks:
- NaN / inf / null
- Stale timestamps
- Impossible ranges
- Inverted FX
- Duplicate rows
- Missing critical fields
- Broken joins
"""

from .prices import validate_price, validate_price_batch

__all__ = [
    "validate_price",
    "validate_price_batch",
]
