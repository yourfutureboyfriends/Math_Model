"""
Normalization Layer — Convert provider outputs to canonical internal schema.

Rules:
- Canonical symbol names
- Canonical timestamp format (ISO 8601 UTC)
- Canonical units (defined in data_contracts)
- Consistent missing-value handling (NaN → None)
- No business logic
"""

from .prices import normalize_price, normalize_prices
from .macro_series import normalize_macro_value, normalize_macro_series
from .fx import normalize_fx_rate

__all__ = [
    "normalize_price",
    "normalize_prices",
    "normalize_macro_value",
    "normalize_macro_series",
    "normalize_fx_rate",
]
