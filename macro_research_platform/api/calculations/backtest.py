"""
Signal backtesting math — pure, tested (Phase 4).

Given a price series and a per-date signal state (BULLISH / BEARISH / NEUTRAL,
reconstructed with no look-ahead), measure the signal's historical track record:
hit rate, forward return by state, the Sharpe/drawdown of a naive strategy that follows
the signal, and a confusion matrix of signal vs realized direction.

Conventions:
- Signals and forward returns are aligned so signal[t] is evaluated against the return
  from t to t+horizon (strictly forward — no look-ahead).
- A strategy following the signal is +1 (long) when BULLISH, -1 (short) when BEARISH,
  0 (flat) when NEUTRAL, earning the next-period return.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Optional, Tuple
import numpy as np

BULLISH, BEARISH, NEUTRAL = "BULLISH", "BEARISH", "NEUTRAL"
_POS = {BULLISH: 1, BEARISH: -1, NEUTRAL: 0}


def forward_returns(closes: Sequence[float], horizon: int = 21) -> np.ndarray:
    """h-day forward simple return at each t: close[t+h]/close[t] - 1. Length trimmed."""
    c = np.asarray(closes, dtype=float)
    if c.size <= horizon:
        return np.array([])
    return c[horizon:] / c[:-horizon] - 1.0


def hit_rate(signals: Sequence[str], fwd_ret: Sequence[float]) -> float:
    """Fraction of directional (non-neutral) signals whose sign matches the forward
    return sign. Neutral signals are excluded from the base."""
    n_correct, n_dir = 0, 0
    for s, r in zip(signals, fwd_ret):
        d = _POS.get(s, 0)
        if d == 0:
            continue
        n_dir += 1
        if (d > 0 and r > 0) or (d < 0 and r < 0):
            n_correct += 1
    return round(n_correct / n_dir, 4) if n_dir else 0.0


def forward_return_by_state(signals: Sequence[str], fwd_ret: Sequence[float]) -> Dict[str, Dict[str, float]]:
    """Average forward return (and count) for each signal state."""
    buckets: Dict[str, List[float]] = {BULLISH: [], BEARISH: [], NEUTRAL: []}
    for s, r in zip(signals, fwd_ret):
        if s in buckets:
            buckets[s].append(r)
    out = {}
    for state, rs in buckets.items():
        out[state] = {"avg_forward_return": round(float(np.mean(rs)), 5) if rs else 0.0,
                      "count": len(rs)}
    return out


def strategy_daily_returns(signals: Sequence[str], daily_ret: Sequence[float]) -> np.ndarray:
    """Daily returns of following the signal: position[t] * daily_return[t+1].

    signals aligned to daily_ret such that signal[t] earns daily_ret[t] (next day).
    """
    pos = np.array([_POS.get(s, 0) for s in signals], dtype=float)
    r = np.asarray(daily_ret, dtype=float)
    n = min(pos.size, r.size)
    return pos[:n] * r[:n]


def sharpe(daily_ret: Sequence[float], periods: int = 252) -> float:
    """Annualized Sharpe of a daily return series (rf=0)."""
    r = np.asarray(daily_ret, dtype=float)
    r = r[~np.isnan(r)]
    if r.size < 2 or r.std(ddof=1) == 0:
        return 0.0
    return round(float(r.mean() / r.std(ddof=1) * (periods ** 0.5)), 3)


def max_drawdown(daily_ret: Sequence[float]) -> float:
    """Worst peak-to-trough drawdown of the cumulative return path (fraction, <=0)."""
    r = np.asarray(daily_ret, dtype=float)
    if r.size == 0:
        return 0.0
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return round(float(dd.min()), 4)


def confusion_matrix(signals: Sequence[str], fwd_ret: Sequence[float]) -> Dict[str, Dict[str, int]]:
    """Signal state vs realized direction (Up/Down) counts."""
    m = {s: {"Up": 0, "Down": 0} for s in (BULLISH, BEARISH, NEUTRAL)}
    for s, r in zip(signals, fwd_ret):
        if s in m:
            m[s]["Up" if r > 0 else "Down"] += 1
    return m


def backtest_signal(
    closes: Sequence[float],
    signals: Sequence[str],
    horizon: int = 21,
) -> Dict:
    """Full backtest scorecard for a signal series aligned to `closes`.

    signals[t] is the signal known at date t (built from data <= t). Evaluated against
    the forward return over the next `horizon` days and against next-day strategy returns.
    """
    c = np.asarray(closes, dtype=float)
    sig = list(signals)
    n = min(len(sig), c.size)
    if n <= horizon + 5:
        return {"available": False, "reason": "insufficient history"}
    sig = sig[:n]
    c = c[:n]

    fwd = forward_returns(c, horizon)                 # len n-horizon
    sig_fwd = sig[:fwd.size]                           # align
    daily = c[1:] / c[:-1] - 1.0                       # len n-1
    strat = strategy_daily_returns(sig[:daily.size], daily)

    return {
        "available": True,
        "horizon_days": horizon,
        "observations": int(fwd.size),
        "hit_rate": hit_rate(sig_fwd, fwd),
        "forward_return_by_state": forward_return_by_state(sig_fwd, fwd),
        "strategy_sharpe": sharpe(strat),
        "strategy_max_drawdown": max_drawdown(strat),
        "strategy_total_return": round(float(np.prod(1.0 + strat) - 1.0), 4),
        "confusion_matrix": confusion_matrix(sig_fwd, fwd),
    }


# ── Signal reconstruction (no look-ahead) — built only from data up to each date ──
def momentum_signal(closes: Sequence[float], lookback: int = 252, skip: int = 21) -> List[str]:
    """12-1 month price momentum sign. BULLISH if (close[t-skip]/close[t-lookback]-1)>0."""
    c = np.asarray(closes, dtype=float)
    out: List[str] = []
    for t in range(c.size):
        if t < lookback:
            out.append(NEUTRAL)
            continue
        m = c[t - skip] / c[t - lookback] - 1.0
        out.append(BULLISH if m > 0.02 else BEARISH if m < -0.02 else NEUTRAL)
    return out


def vol_regime_signal(vix_closes: Sequence[float], window: int = 126) -> List[str]:
    """Vol-regime signal for equities: VIX below its trailing median => risk-on
    (BULLISH), above => risk-off (BEARISH). No look-ahead (median uses data <= t)."""
    v = np.asarray(vix_closes, dtype=float)
    out: List[str] = []
    for t in range(v.size):
        if t < window:
            out.append(NEUTRAL)
            continue
        med = float(np.median(v[t - window + 1: t + 1]))
        out.append(BULLISH if v[t] < med else BEARISH if v[t] > med else NEUTRAL)
    return out


def trend_signal(closes: Sequence[float], window: int = 200) -> List[str]:
    """Price vs its own `window`-day moving average. Above => BULLISH, below => BEARISH."""
    c = np.asarray(closes, dtype=float)
    out: List[str] = []
    for t in range(c.size):
        if t < window:
            out.append(NEUTRAL)
            continue
        ma = c[t - window + 1: t + 1].mean()
        out.append(BULLISH if c[t] > ma * 1.005 else BEARISH if c[t] < ma * 0.995 else NEUTRAL)
    return out
