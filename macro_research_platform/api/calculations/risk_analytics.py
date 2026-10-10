"""
Portfolio risk analytics from realised returns (replaces /api/risk/full's formulas, which
derived "Sharpe" from a growth score and VIX, Sortino as Sharpe×1.2, max drawdown as
−VIX/2 and a correlation matrix from the regime label — none of it measured).

Everything here is computed from a daily return series; inputs are plain lists so the
maths is unit-testable.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

TRADING_DAYS = 252


def _mean(x: Sequence[float]) -> float:
    return sum(x) / len(x)


def _std(x: Sequence[float]) -> float:
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else 0.0


def _r(v: Optional[float], d: int = 2) -> Optional[float]:
    return None if v is None or not math.isfinite(v) else round(v, d)


def performance_stats(port: Sequence[float], bench: Optional[Sequence[float]] = None,
                      rf_annual: float = 0.0) -> Dict[str, Optional[float]]:
    """Annualised return/vol, Sharpe & Sortino (excess of rf), Calmar, beta and
    information ratio vs the benchmark, 1-day historical VaR/CVaR 95% — all from data."""
    n = len(port)
    if n < 20:
        return {"available": False, "observations": n}
    growth = 1.0
    for r in port:
        growth *= 1 + r
    ann_ret = growth ** (TRADING_DAYS / n) - 1
    vol = _std(port) * math.sqrt(TRADING_DAYS)
    downside = [min(0.0, r - rf_annual / TRADING_DAYS) for r in port]
    dd_dev = math.sqrt(sum(d * d for d in downside) / n) * math.sqrt(TRADING_DAYS)
    mdd = drawdown_stats(port)["max_drawdown"]
    srt = sorted(port)
    k = max(1, int(0.05 * n))
    var95 = -srt[k - 1] if srt[k - 1] < 0 else 0.0
    cvar95 = -_mean(srt[:k]) if _mean(srt[:k]) < 0 else 0.0
    out = {
        "available": True, "observations": n,
        "annualReturn": _r(ann_ret * 100, 1), "annualVolatility": _r(vol * 100, 1),
        "sharpeRatio": _r((ann_ret - rf_annual) / vol) if vol > 0 else None,
        "sortinoRatio": _r((ann_ret - rf_annual) / dd_dev) if dd_dev > 0 else None,
        "calmarRatio": _r(ann_ret / abs(mdd)) if mdd else None,
        "var95": _r(var95, 4), "cvar95": _r(cvar95, 4),
        "betaVsSpy": None, "informationRatio": None,
    }
    if bench and len(bench) == n:
        vb = _std(bench) ** 2
        if vb > 0:
            mp, mb = _mean(port), _mean(bench)
            cov = sum((p - mp) * (b - mb) for p, b in zip(port, bench)) / (n - 1)
            out["betaVsSpy"] = _r(cov / vb)
        active = [p - b for p, b in zip(port, bench)]
        te = _std(active) * math.sqrt(TRADING_DAYS)
        out["informationRatio"] = _r(_mean(active) * TRADING_DAYS / te) if te > 0 else None
    return out


def drawdown_stats(port: Sequence[float]) -> Dict:
    """Current and max drawdown (as fractions, ≤ 0) and trading days since the last peak."""
    level, peak, max_dd, since_peak = 1.0, 1.0, 0.0, 0
    for r in port:
        level *= 1 + r
        if level >= peak:
            peak, since_peak = level, 0
        else:
            since_peak += 1
        max_dd = min(max_dd, level / peak - 1)
    cur = level / peak - 1
    sev = ("NONE" if cur > -0.01 else "MILD" if cur > -0.05 else
           "SIGNIFICANT" if cur > -0.10 else "SEVERE")
    return {"current_drawdown": cur, "max_drawdown": max_dd, "days_in_drawdown": since_peak,
            "severity": sev}


def correlation_block(returns: Dict[str, Sequence[float]], window: int = 63) -> Dict:
    """Pairwise correlation of the last `window` daily returns, plus a diversification
    score = 1 − mean |pairwise correlation| (1 = uncorrelated, 0 = moving as one)."""
    assets = [a for a, r in returns.items() if len(r) >= window]
    if len(assets) < 2:
        return {"available": False, "assets": assets, "matrix3m": []}
    cols = {a: [float(v) for v in list(returns[a])[-window:]] for a in assets}

    def corr(x, y):
        mx, my = _mean(x), _mean(y)
        sx, sy = _std(x), _std(y)
        if sx == 0 or sy == 0:
            return 0.0
        return sum((a - mx) * (b - my) for a, b in zip(x, y)) / ((len(x) - 1) * sx * sy)

    m = [[1.0 if i == j else round(float(corr(cols[a], cols[b])), 2) for j, b in enumerate(assets)]
         for i, a in enumerate(assets)]
    pairs = [(assets[i], assets[j], m[i][j]) for i in range(len(assets)) for j in range(i + 1, len(assets))]
    score = 1 - _mean([abs(c) for _, _, c in pairs])
    return {"available": True, "assets": assets, "matrix3m": m, "window_days": window,
            "diversificationScore": round(score, 2),
            "diversificationRating": "GOOD" if score > 0.5 else "FAIR" if score > 0.3 else "POOR",
            "highCorrelationPairs": [{"pair": f"{a}/{b}", "corr": c} for a, b, c in pairs if abs(c) >= 0.7]}
