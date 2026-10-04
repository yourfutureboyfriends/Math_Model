"""
Commodity macro signals, each judged against the market's own recent history instead of
fixed levels that go stale as prices move.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def copper_gold_signal(copper: Dict[str, float], gold: Dict[str, float],
                       trend_days: int = 63, band: float = 0.03) -> Dict:
    """Copper/gold ratio (copper $/lb ÷ gold $/oz × 1000) on common dates.

    Signal from the ratio's 3-month trend (rising = copper outperforming = growth
    optimism → RISK-ON), with its 1-year percentile for context.
    """
    days = sorted(set(copper) & set(gold))
    ratio = [copper[d] / gold[d] * 1000 for d in days if gold[d]]
    if len(ratio) < trend_days + 1:
        return {"value": round(ratio[-1], 4) if ratio else None, "signal": "UNAVAILABLE",
                "description": "Not enough common history for copper and gold"}
    cur, past = ratio[-1], ratio[-1 - trend_days]
    chg = cur / past - 1
    lo, hi = min(ratio), max(ratio)
    pct = round((cur - lo) / (hi - lo) * 100) if hi > lo else 50
    signal = "RISK-ON" if chg > band else "RISK-OFF" if chg < -band else "NEUTRAL"
    return {"value": round(cur, 4), "signal": signal, "change3m_pct": round(chg * 100, 2),
            "percentile_1y": pct, "as_of": days[-1],
            "description": (f"Copper/gold ratio {'+' if chg >= 0 else ''}{chg * 100:.1f}% over 3M "
                            f"({pct}th pct of 1Y range): rising = growth optimism, falling = defensive")}


def oil_trend_signal(change_1m: Optional[float], band: float = 3.0) -> Dict:
    if change_1m is None:
        return {"direction": "UNAVAILABLE", "interpretation": "No WTI history"}
    if change_1m > band:
        return {"direction": "RISING", "change1m": change_1m,
                "interpretation": "Firm energy prices — inflation pressure / supply tightness"}
    if change_1m < -band:
        return {"direction": "FALLING", "change1m": change_1m,
                "interpretation": "Softening energy prices — easing inflation / weaker demand"}
    return {"direction": "STABLE", "change1m": change_1m, "interpretation": "Range-bound over the month"}


def broad_commodity_momentum(rows: List[Dict], band: float = 2.0) -> Dict:
    moves = [r["change3m"] for r in rows if isinstance(r.get("change3m"), (int, float))]
    if not moves:
        return {"score": None, "signal": "UNAVAILABLE", "components": 0}
    score = sum(moves) / len(moves)
    return {"score": round(score, 2), "components": len(moves),
            "signal": "RISING" if score > band else "FALLING" if score < -band else "STABLE",
            "description": f"Equal-weight 3M price change across {len(moves)} commodities"}
