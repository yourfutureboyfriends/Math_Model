"""Signal calculations from real market data - no hardcoding.

Every signal returns (score, trend, history). When a required input is missing the
signal returns (None, "unavailable", []) rather than substituting a made-up default.
Only `calculate_growth_signal` sees a time series, so it is the only one that returns a
multi-point history; the scalar signals return just the current point and the caller
builds real history by evaluating them at past dates.
"""
from typing import Tuple, List, Dict, Optional, Sequence

UNAVAILABLE = (None, "unavailable", [])

# Growth momentum lookbacks (trading days) and the offsets at which history is sampled.
_GROWTH_LOOKBACKS = (63, 126)            # 3m and 6m returns
GROWTH_HISTORY_OFFSETS = (63, 47, 31, 16, 0)   # T-4 … Now (~3 months span)
_GROWTH_TREND_OFFSET = 63               # trend = score now vs ~3 months ago (matches the displayed 3M change)


def _growth_score_at(closes: Sequence[float], end: int) -> Optional[float]:
    """Growth score using closes[:end+1]. None if there isn't enough history.

    Momentum = mean of the annualized 3-month and 6-month price returns. Mapped linearly
    so -20%/yr -> 0.0, +5%/yr -> 0.5, +30%/yr -> 1.0 (clamped).
    """
    need = max(_GROWTH_LOOKBACKS)
    if end < need:
        return None
    last = closes[end]
    annualized = []
    for lb in _GROWTH_LOOKBACKS:
        base = closes[end - lb]
        if not base or base <= 0:
            return None
        annualized.append((last / base - 1.0) * (252.0 / lb))
    momentum = sum(annualized) / len(annualized)
    return min(max((momentum + 0.20) / 0.50, 0.0), 1.0)


def calculate_growth_signal(spx_level: Optional[float], spx_history: Optional[Sequence[float]]) -> Tuple[Optional[float], str, List[float]]:
    """
    Growth signal from S&P 500 price momentum.

    Args:
        spx_level: latest price (live quote). If given it is appended after the history.
        spx_history: real DAILY closes, oldest first, excluding the latest price when
            spx_level is given. Needs at least 127 points.

    Returns (score, trend, history). history holds the score sampled at
    GROWTH_HISTORY_OFFSETS trading days ago (oldest first, only the computable points).
    """
    closes = [float(p) for p in (spx_history or []) if p is not None and p == p]
    if spx_level is not None and spx_level > 0:
        closes.append(float(spx_level))
    end = len(closes) - 1

    score = _growth_score_at(closes, end)
    if score is None:
        return UNAVAILABLE

    prior = _growth_score_at(closes, end - _GROWTH_TREND_OFFSET)
    if prior is None:
        trend = "stable"
    elif score > prior + 0.02:
        trend = "improving"
    elif score < prior - 0.02:
        trend = "deteriorating"
    else:
        trend = "stable"

    history = []
    for off in GROWTH_HISTORY_OFFSETS:
        s = _growth_score_at(closes, end - off)
        if s is not None:
            history.append(round(s, 2))

    return round(score, 2), trend, history


def calculate_inflation_signal(cpi_yoy: Optional[float], breakeven_10y: Optional[float]) -> Tuple[Optional[float], str, List[float]]:
    """
    Inflation signal from realized and expected inflation (percent):
      - CPI YoY:              1% -> 0.0, 3% -> 0.5, 5% -> 1.0
      - 10Y breakeven (TIPS): 1.5% -> 0.0, 2.25% -> 0.5, 3.0% -> 1.0
    Score = mean of the available components (clamped to [0, 1]).

    This replaced the 10Y-2Y curve slope, which is not an inflation measure: the curve can
    steepen on growth or term premium with inflation falling, and vice versa.
    """
    parts = []
    if cpi_yoy is not None:
        parts.append(min(max((cpi_yoy - 1.0) / 4.0, 0.0), 1.0))
    if breakeven_10y is not None:
        parts.append(min(max((breakeven_10y - 1.5) / 1.5, 0.0), 1.0))
    if not parts:
        return UNAVAILABLE

    score = sum(parts) / len(parts)
    trend = "elevated" if score > 0.6 else "subdued" if score < 0.4 else "contained"
    return round(score, 2), trend, [round(score, 2)]


def calculate_liquidity_signal(dxy: Optional[float], ten_yr: Optional[float], fed_rate: Optional[float]) -> Tuple[Optional[float], str, List[float]]:
    """
    Calculate liquidity signal from DXY and the Fed-funds minus 10Y spread.
    Lower DXY and a lower policy rate vs 10Y = looser liquidity.
    A 0% policy rate is a valid input (ZIRP), not a missing one.
    """
    if dxy is None or dxy <= 0 or ten_yr is None or fed_rate is None:
        return UNAVAILABLE

    # DXY: 90-110 typical range. Lower = looser global liquidity
    dxy_component = 1.0 - min(max((dxy - 90) / 20.0, 0.0), 1.0)

    # Rate spread (Fed - 10Y): wider = tighter financial conditions
    spread = fed_rate - ten_yr
    spread_component = 1.0 - min(max((spread + 1) / 3.0, 0.0), 1.0)

    score = (dxy_component * 0.6) + (spread_component * 0.4)
    trend = "loose" if score > 0.6 else "tight" if score < 0.4 else "neutral"

    return round(score, 2), trend, [round(score, 2)]


def calculate_risk_signal(vix: Optional[float]) -> Tuple[Optional[float], str, List[float]]:
    """
    Calculate risk signal from VIX level.
    Lower VIX = higher risk appetite (higher score)
    """
    if vix is None or vix <= 0:
        return UNAVAILABLE

    # VIX: 10-40 typical range. Invert so higher score = more risk appetite
    score = 1.0 - min(max((vix - 10) / 30.0, 0.0), 1.0)

    if vix < 15:
        trend = "complacent"
    elif vix < 20:
        trend = "normal"
    elif vix < 25:
        trend = "elevated"
    else:
        trend = "stress"

    return round(score, 2), trend, [round(score, 2)]


def generate_conviction(value: float, threshold_high: float = 0.7, threshold_low: float = 0.4) -> str:
    """Generate conviction level from value."""
    if value > threshold_high:
        return "High"
    elif value > threshold_low:
        return "Medium"
    return "Low"


def generate_signal_state(score: float, thresholds: Dict[str, float]) -> str:
    """Generate signal state from score and thresholds."""
    if score > thresholds.get("strong", 0.7):
        return "Strong"
    elif score > thresholds.get("moderate", 0.5):
        return "Moderate"
    elif score > thresholds.get("weak", 0.3):
        return "Weak"
    return "Very Weak"
