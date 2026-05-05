"""
Centralised data fetcher — the ONLY way metrics should be read.
Applies unit conversions, bounds checks, NaN guards, and fallbacks.
"""
import logging, math, time
from typing import Any, Optional, Callable
from api.data_contracts import CONTRACTS, MetricContract

logger = logging.getLogger(__name__)

# Single module-level cache — all metrics share one TTL store
_METRIC_CACHE: dict[str, tuple[float, float]] = {}   # {name: (value, timestamp)}
CACHE_TTL_SECONDS = 900  # 15 minutes

def fetch_metric(
    metric_name: str,
    fred_fetch_fn: Optional[Callable[[str], Optional[float]]] = None,  # callable: fred_fetch_fn(series_id) -> float | None
    yf_fetch_fn: Optional[Callable[[str], Optional[float]]] = None,     # callable: yf_fetch_fn(ticker) -> float | None
    force_refresh: bool = False,
) -> float:
    """
    THE ONLY way to get a metric value. Never call FRED/yfinance directly.
    Returns a validated, unit-converted, NaN-free float. Always.
    """
    contract: Optional[MetricContract] = CONTRACTS.get(metric_name)
    if not contract:
        raise ValueError(
            f"No contract for '{metric_name}'. "
            f"Add it to data_contracts.py first."
        )

    # Check cache
    if not force_refresh and metric_name in _METRIC_CACHE:
        cached_val, cached_ts = _METRIC_CACHE[metric_name]
        if time.time() - cached_ts < CACHE_TTL_SECONDS:
            return cached_val

    raw_value: Optional[float] = None
    source = "none"

    # Try FRED
    if contract.fred_series and fred_fetch_fn:
        try:
            raw_value = fred_fetch_fn(contract.fred_series)
            if raw_value is not None:
                source = f"FRED:{contract.fred_series}"
        except Exception as e:
            logger.warning(f"[FETCH] {metric_name}: FRED error — {e}")

    # Try yfinance fallback
    if raw_value is None and contract.yf_ticker and yf_fetch_fn:
        try:
            raw_value = yf_fetch_fn(contract.yf_ticker)
            if raw_value is not None:
                source = f"YF:{contract.yf_ticker}"
        except Exception as e:
            logger.warning(f"[FETCH] {metric_name}: YF fallback error — {e}")

    # All sources failed
    if raw_value is None:
        logger.error(
            f"[FETCH] {metric_name}: ALL SOURCES FAILED — "
            f"using fallback={contract.fallback_value}. INVESTIGATE."
        )
        result = contract.fallback_value if contract.fallback_value is not None else 0.0
        _METRIC_CACHE[metric_name] = (result, time.time())
        return result

    # Apply unit conversion
    converted = raw_value * contract.multiply_by

    # NaN / Inf guard
    if not math.isfinite(converted):
        logger.critical(
            f"[FETCH] {metric_name}: NaN/Inf from {source} "
            f"(raw={raw_value}) — using fallback."
        )
        result = contract.fallback_value if contract.fallback_value is not None else 0.0
        _METRIC_CACHE[metric_name] = (result, time.time())
        return result

    # Hard bounds check — reject completely implausible values
    if not (contract.hard_min <= converted <= contract.hard_max):
        logger.critical(
            f"[FETCH] {metric_name}: {converted} from {source} "
            f"outside hard bounds [{contract.hard_min}, {contract.hard_max}] "
            f"— REJECTED. Using fallback={contract.fallback_value}. "
            f"INVESTIGATE SOURCE."
        )
        result = contract.fallback_value if contract.fallback_value is not None else 0.0
        _METRIC_CACHE[metric_name] = (result, time.time())
        return result

    # Soft bounds — warn only
    if not (contract.typical_min <= converted <= contract.typical_max):
        logger.warning(
            f"[FETCH] {metric_name}: {converted} from {source} "
            f"outside typical range [{contract.typical_min}, {contract.typical_max}]. "
            f"Allowing — verify if unexpected."
        )

    logger.info(
        f"[FETCH] {metric_name}: raw={raw_value} × {contract.multiply_by} "
        f"= {converted} [{contract.unit}] [{source}]"
    )

    _METRIC_CACHE[metric_name] = (converted, time.time())
    return converted


def validate_dashboard_snapshot(data: dict) -> list[str]:
    """
    Run after computing the full dashboard. Returns list of errors.
    Wire into /api/dashboard endpoint so errors surface in UI debug panel.
    """
    errors: list[str] = []

    def chk(path: str, lo: float, hi: float):
        keys = path.split(".")
        val: Any = data
        for k in keys:
            val = val.get(k) if isinstance(val, dict) else None
        if val is None:
            errors.append(f"MISSING: {path}")
            return
        try:
            v = float(val)
            if not math.isfinite(v):
                errors.append(f"NaN/Inf: {path}={val}")
            elif not (lo <= v <= hi):
                errors.append(f"OUT_OF_BOUNDS: {path}={v} expected [{lo}, {hi}]")
        except (TypeError, ValueError):
            errors.append(f"NOT_NUMERIC: {path}={val}")

    chk("keyMetrics.growth.value",        -15,   15)
    chk("keyMetrics.inflation.value",      -5,   25)
    chk("keyMetrics.vix",                   5,   90)
    chk("keyMetrics.recessionRisk",          0,  100)
    chk("riskIndicators.hyCredit",          50, 2000)
    chk("riskIndicators.vix",               5,   90)
    chk("riskIndicators.yieldCurve",      -300,  300)

    # Regime consistency check (BUG-05)
    master_regime = data.get("regime", {}).get("current", "")
    intl_macro = data.get("internationalMacro", {}) or {}
    # Handle both old {"us": {...}} and new {"economies": [...]} structures
    intl_us_regime = ""
    if "us" in intl_macro:
        intl_us_regime = intl_macro.get("us", {}).get("regime", "")
    elif "economies" in intl_macro:
        us_econ = next((e for e in intl_macro.get("economies", []) if e.get("name") == "US"), {})
        intl_us_regime = us_econ.get("regime", "")
    if master_regime and intl_us_regime and master_regime != intl_us_regime:
        errors.append(f"REGIME_MISMATCH:master={master_regime} vs intl_macro_us={intl_us_regime}")

    for asset in data.get("gmoForecasts", {}).get("assets", []):
        try:
            v = float(asset.get("expectedReturn", 0))
            if abs(v) > 30:
                errors.append(
                    f"GMO_IMPLAUSIBLE: {asset.get('ticker')}={v}% "
                    f"(annualised must be -30% to +30%)"
                )
        except (TypeError, ValueError):
            pass

    if errors:
        logger.critical(f"[VALIDATE] {len(errors)} integrity errors: {errors}")
    else:
        logger.info("[VALIDATE] All integrity checks passed ✓")

    return errors
