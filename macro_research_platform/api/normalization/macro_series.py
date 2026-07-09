"""
Macro Series Normalization — Convert FRED/other macro data to canonical format.

Handles:
- Unit conversion (percent, bps, index)
- Frequency standardization
- Timestamp normalization
- Missing value handling
"""

import logging
import math
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from api.providers.fred_provider import FREDObservation
from api.data_contracts import CONTRACTS

logger = logging.getLogger(__name__)


def normalize_macro_value(
    metric_name: str,
    raw_value: float,
    source: str = "unknown"
) -> Optional[Dict[str, Any]]:
    """
    Normalize a macroeconomic value using its data contract.

    Args:
        metric_name: Name of the metric (must be in CONTRACTS)
        raw_value: Raw value from provider
        source: Data source identifier

    Returns:
        Normalized value dict or None if invalid.
    """
    contract = CONTRACTS.get(metric_name)
    if not contract:
        logger.warning(f"No contract for metric: {metric_name}")
        return None

    # Validate raw value
    if not math.isfinite(raw_value):
        logger.warning(f"Non-finite value for {metric_name}: {raw_value}")
        return None

    # Apply unit conversion
    converted = raw_value * contract.multiply_by

    # Check hard bounds (reject)
    if not (contract.hard_min <= converted <= contract.hard_max):
        logger.warning(
            f"{metric_name}: {converted} outside hard bounds "
            f"[{contract.hard_min}, {contract.hard_max}] — REJECTED"
        )
        return None

    # Check soft bounds (warn but allow)
    if not (contract.typical_min <= converted <= contract.typical_max):
        logger.warning(
            f"{metric_name}: {converted} outside typical range "
            f"[{contract.typical_min}, {contract.typical_max}]"
        )

    return {
        "metric": metric_name,
        "value": round(converted, 6),
        "unit": contract.unit,
        "raw_value": raw_value,
        "multiply_by": contract.multiply_by,
        "source": source,
        "contract": contract.name,
    }


def normalize_macro_series(
    metric_name: str,
    observations: List[FREDObservation]
) -> List[Dict[str, Any]]:
    """
    Normalize a series of macro observations.

    Args:
        metric_name: Name of the metric
        observations: List of FRED observations

    Returns:
        List of normalized observation dicts.
    """
    results = []
    for obs in observations:
        normalized = normalize_macro_value(
            metric_name,
            obs.value,
            source=f"FRED:{obs.series_id}"
        )
        if normalized:
            normalized["date"] = obs.date
            normalized["realtime_start"] = obs.realtime_start
            normalized["realtime_end"] = obs.realtime_end
            results.append(normalized)
    return results


def calculate_yoy_growth(
    current: float,
    year_ago: float,
    as_percent: bool = True
) -> Optional[float]:
    """
    Calculate year-over-year growth rate.

    Args:
        current: Current value
        year_ago: Value one year ago
        as_percent: Return as percentage (True) or decimal (False)

    Returns:
        YoY growth rate or None.
    """
    if not math.isfinite(current) or not math.isfinite(year_ago):
        return None
    if year_ago == 0:
        return None

    growth = (current / year_ago) - 1.0
    if as_percent:
        return growth * 100
    return growth


def annualize_monthly_rate(monthly_rate: float, as_percent: bool = True) -> float:
    """
    Convert monthly rate to annualized rate.

    Args:
        monthly_rate: Monthly rate (as decimal)
        as_percent: Return as percentage

    Returns:
        Annualized rate.
    """
    # (1 + r_monthly)^12 - 1
    annual = (1 + monthly_rate) ** 12 - 1
    if as_percent:
        return annual * 100
    return annual
