"""Reusable Pydantic validators."""
import numpy as np
from typing import Any


def clean_float(value: Any, default: float = 0.0) -> float:
    """
    Clean float value, replacing NaN/Inf with default.

    Args:
        value: Input value
        default: Default value for invalid inputs

    Returns:
        Cleaned float value
    """
    if value is None:
        return default

    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def clean_float_rounded(value: Any, decimals: int = 6, default: float = 0.0) -> float:
    """
    Clean and round float value.

    Args:
        value: Input value
        decimals: Number of decimal places
        default: Default value for invalid inputs

    Returns:
        Cleaned and rounded float
    """
    cleaned = clean_float(value, default)
    return round(cleaned, decimals)


def clean_float_list(values: list, decimals: int = 6, default: float = 0.0) -> list:
    """
    Clean list of float values.

    Args:
        values: List of values
        decimals: Number of decimal places
        default: Default for invalid values

    Returns:
        List of cleaned floats
    """
    return [clean_float_rounded(v, decimals, default) for v in values]
