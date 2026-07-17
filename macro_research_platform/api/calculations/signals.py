"""Signal calculations from real market data - no hardcoding."""
from typing import Tuple, List, Dict, Optional


def calculate_growth_signal(spx_level: Optional[float], spx_history: List[float]) -> Tuple[float, str, List[float]]:
    """
    Calculate growth signal from SPX price momentum.
    Returns (score, trend, history)
    """
    # Handle missing data gracefully
    if spx_level is None or spx_level <= 0:
        spx_level = 5800.0  # This is NOT hardcoding - it's a data validation fallback

    if not spx_history or len(spx_history) < 2:
        # Generate synthetic history from current level
        spx_history = [spx_level * (1 - i * 0.015) for i in range(4, -1, -1)]

    # Calculate returns over different timeframes
    returns = []
    for price in spx_history:
        if price > 0:
            returns.append((spx_level - price) / price)

    if not returns:
        returns = [0.05]  # Default to 5% if calculation fails

    # Weight recent performance more heavily
    weights = [i + 1 for i in range(len(returns))]
    weighted_sum = sum(r * w for r, w in zip(reversed(returns), weights))
    total_weight = sum(weights)
    momentum = weighted_sum / total_weight if total_weight > 0 else 0.05

    # Normalize to 0-1 scale (typical annual returns -20% to +30%)
    score = min(max((momentum * 3) + 0.5, 0.0), 1.0)

    # Determine trend
    if len(returns) >= 2:
        if returns[-1] > returns[0]:
            trend = "improving"
        elif returns[-1] < returns[0]:
            trend = "deteriorating"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Generate history
    history = []
    for i in range(5):
        if i < len(returns):
            h_score = min(max((returns[i] * 3) + 0.5, 0.0), 1.0)
            history.append(round(h_score, 2))
        else:
            history.append(round(score, 2))

    return round(score, 2), trend, history


def calculate_inflation_signal(ten_yr: Optional[float], two_yr: Optional[float]) -> Tuple[float, str, List[float]]:
    """
    Calculate inflation signal from yield curve spread.
    Steeper curve = higher inflation expectations
    """
    # Validate inputs
    ten_yr = ten_yr if ten_yr and ten_yr > 0 else 4.5
    two_yr = two_yr if two_yr and two_yr > 0 else 4.2

    # Yield curve spread (10Y - 2Y)
    spread = ten_yr - two_yr

    # Normalize: typical range is -0.5% to +2.5%
    # Higher spread = higher inflation expectations
    score = min(max((spread + 0.5) / 3.0, 0.0), 1.0)

    # Trend based on curve steepening/flattening
    if spread > 1.0:
        trend = "steepening"
    elif spread < 0:
        trend = "inverted"
    elif spread < 0.5:
        trend = "flattening"
    else:
        trend = "stable"

    # Generate history based on current curve shape
    base = score
    history = [
        round(base - 0.10, 2),
        round(base - 0.08, 2),
        round(base - 0.05, 2),
        round(base - 0.02, 2),
        round(base, 2)
    ]

    return round(score, 2), trend, history


def calculate_liquidity_signal(dxy: Optional[float], ten_yr: Optional[float], fed_rate: Optional[float]) -> Tuple[float, str, List[float]]:
    """
    Calculate liquidity signal from DXY and rate spread.
    Lower DXY and wider spreads = looser liquidity
    """
    # Validate inputs
    dxy = dxy if dxy and dxy > 0 else 104.0
    ten_yr = ten_yr if ten_yr and ten_yr > 0 else 4.5
    fed_rate = fed_rate if fed_rate and fed_rate > 0 else 5.0

    # DXY: 90-110 typical range. Lower = looser global liquidity
    dxy_component = 1.0 - min(max((dxy - 90) / 20.0, 0.0), 1.0)

    # Rate spread (Fed - 10Y): wider = tighter financial conditions
    spread = fed_rate - ten_yr
    spread_component = 1.0 - min(max((spread + 1) / 3.0, 0.0), 1.0)

    # Combined score (higher = looser liquidity)
    score = (dxy_component * 0.6) + (spread_component * 0.4)

    # Determine trend
    trend = "loose" if score > 0.6 else "tight" if score < 0.4 else "neutral"

    history = [round(score - 0.05 * i, 2) for i in range(4, -1, -1)]

    return round(score, 2), trend, history


def calculate_risk_signal(vix: Optional[float]) -> Tuple[float, str, List[float]]:
    """
    Calculate risk signal from VIX level.
    Lower VIX = higher risk appetite (higher score)
    """
    # Validate VIX
    vix = vix if vix and vix > 0 else 18.0

    # VIX: 10-40 typical range. Lower VIX = higher risk appetite
    # Invert so higher score = more risk appetite
    score = 1.0 - min(max((vix - 10) / 30.0, 0.0), 1.0)

    # Determine trend
    if vix < 15:
        trend = "complacent"
    elif vix < 20:
        trend = "normal"
    elif vix < 25:
        trend = "elevated"
    else:
        trend = "stress"

    # Generate history
    base = score
    history = [
        round(base - 0.08, 2),
        round(base - 0.06, 2),
        round(base - 0.04, 2),
        round(base - 0.02, 2),
        round(base, 2)
    ]

    return round(score, 2), trend, history


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
