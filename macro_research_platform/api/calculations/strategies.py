"""
Systematic strategies for the Strategy Lab — each a function from data known at a month-end
to target weights, run through one walk-forward engine (monthly rebalance, daily returns,
costs on turnover). Pure functions; no look-ahead: weights set at the close of month-end t
earn returns from t+1.

  * Cross-asset trend following — time-series momentum on liquid ETFs (equities, bonds,
    gold, commodities, dollar, real estate): long when the blended 1/3/12-month return is
    positive, short when negative (or flat if long-only), each position scaled to the same
    volatility, the whole book to a volatility target. Moskowitz, Ooi & Pedersen (2012);
    Hurst, Ooi & Pedersen (2017).
  * Sector momentum — the top sector ETFs by 12-1-month return, equal weight, long-only.
    Moskowitz & Grinblatt (1999); Andreu et al. (2013, sector ETFs).
  * Low volatility — the least volatile stocks of the sample (1-year daily volatility),
    long-only, inverse-volatility weighted. Ang, Hodrick, Xing & Zhang (2006); Frazzini &
    Pedersen (2014).
  * Residual momentum — stocks ranked on 12-1-month momentum of the residual from a
    regression on their home index (36 months), scaled by residual volatility; top names,
    equal weight. Blitz, Huij & Martens (2011).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

TD_MONTH = 21


def month_ends(dates: Sequence[str]) -> List[int]:
    """Indices of the last trading day of each month."""
    return [i for i in range(len(dates)) if i == len(dates) - 1 or dates[i][:7] != dates[i + 1][:7]]


def _ret(px: np.ndarray, t: int, lag: int) -> np.ndarray:
    """Simple return over the `lag` days ending at t (NaN where unavailable)."""
    if t - lag < 0:
        return np.full(px.shape[1], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return px[t] / px[t - lag] - 1


def _vol(px: np.ndarray, t: int, window: int = 63) -> np.ndarray:
    if t - window < 1:
        return np.full(px.shape[1], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.diff(np.log(px[t - window:t + 1]), axis=0)
    return np.nanstd(r, axis=0, ddof=1) * math.sqrt(252)


# ── Signals → weights ────────────────────────────────────────────────────────
def trend_weights(px: np.ndarray, t: int, vol_target: float = 0.10, long_only: bool = False,
                  max_gross: float = 2.0) -> np.ndarray:
    """Blended 1/3/12-month time-series momentum; inverse-volatility sized; book scaled to
    `vol_target` assuming zero correlation (a conservative, standard simplification)."""
    sig = np.nanmean(np.vstack([np.sign(_ret(px, t, TD_MONTH)), np.sign(_ret(px, t, 3 * TD_MONTH)),
                                np.sign(_ret(px, t, 12 * TD_MONTH))]), axis=0)
    vol = _vol(px, t)
    ok = np.isfinite(sig) & np.isfinite(vol) & (vol > 0)
    w = np.zeros(px.shape[1])
    if not ok.any():
        return w
    if long_only:
        sig = np.clip(sig, 0, None)
    n = ok.sum()
    w[ok] = sig[ok] * (vol_target / math.sqrt(n)) / vol[ok]
    g = np.abs(w).sum()
    return w * (max_gross / g) if g > max_gross else w


def sector_momentum_weights(px: np.ndarray, t: int, top: int = 3, market_col: Optional[int] = None) -> np.ndarray:
    """Top `top` sectors by 12-1-month return, equal weight; if `market_col` is given and the
    market is below its 10-month (210-day) average, hold nothing (Faber 2007 filter)."""
    mom = _ret(px, t - TD_MONTH, 11 * TD_MONTH)
    w = np.zeros(px.shape[1])
    if market_col is not None and t >= 210:
        m = px[t - 209:t + 1, market_col]
        if np.isfinite(m).all() and px[t, market_col] < np.mean(m):
            return w
    ok = np.isfinite(mom)
    if market_col is not None:
        ok[market_col] = False
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return w
    pick = idx[np.argsort(-mom[idx])[:top]]
    w[pick] = 1.0 / pick.size
    return w


def low_vol_weights(px: np.ndarray, t: int, quantile: float = 0.2, min_names: int = 10) -> np.ndarray:
    vol = _vol(px, t, 252)
    ok = np.isfinite(vol) & (vol > 0)
    w = np.zeros(px.shape[1])
    if ok.sum() < min_names:
        return w
    idx = np.flatnonzero(ok)
    k = max(min_names, int(round(idx.size * quantile)))
    pick = idx[np.argsort(vol[idx])[:k]]
    iv = 1 / vol[pick]
    w[pick] = iv / iv.sum()
    return w


def residual_momentum_scores(px_m: np.ndarray, idx_m: np.ndarray, m: int, lookback: int = 36) -> np.ndarray:
    """Monthly data: at month m, regress each stock's monthly returns on its home index over
    the trailing `lookback` months; score = sum of residuals over months m-11..m-1 divided by
    their standard deviation (skip the latest month)."""
    n = px_m.shape[1]
    out = np.full(n, np.nan)
    if m < lookback + 1:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        r = px_m[m - lookback:m + 1][1:] / px_m[m - lookback:m + 1][:-1] - 1
        f = idx_m[m - lookback:m + 1][1:] / idx_m[m - lookback:m + 1][:-1] - 1
    for j in range(n):
        y, x = r[:, j], f[:, j]
        ok = np.isfinite(y) & np.isfinite(x)
        if ok.sum() < lookback * 0.8:
            continue
        X = np.column_stack([np.ones(ok.sum()), x[ok]])
        beta, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
        resid = np.full(lookback, np.nan)
        resid[ok] = y[ok] - X @ beta
        win = resid[-12:-1]
        if np.isfinite(win).sum() >= 9:
            sd = np.nanstd(win, ddof=1)
            if sd > 0:
                out[j] = np.nansum(win) / sd
    return out


def top_equal(scores: np.ndarray, top: int) -> np.ndarray:
    w = np.zeros(scores.size)
    idx = np.flatnonzero(np.isfinite(scores))
    if idx.size == 0:
        return w
    pick = idx[np.argsort(-scores[idx])[:top]]
    w[pick] = 1.0 / pick.size
    return w


# ── Engine ───────────────────────────────────────────────────────────────────
def run_monthly(px: np.ndarray, dates: Sequence[str], weight_fn: Callable[[int], np.ndarray],
                cost_bps: float | np.ndarray = 10.0, start: int = 260) -> Dict[str, object]:
    """Daily returns of rebalancing to weight_fn(t) at every month-end t ≥ start. Weights
    drift with prices between rebalances; costs = |Δw| × cost per side. Cash earns nothing,
    shorts pay nothing (no financing modelled)."""
    T, N = px.shape
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(np.isfinite(px[1:]) & np.isfinite(px[:-1]) & (px[:-1] > 0), px[1:] / px[:-1] - 1, 0.0)
    r = np.vstack([np.zeros(N), r])
    ends = set(i for i in month_ends(dates) if i >= start)
    cost = np.broadcast_to(np.asarray(cost_bps, dtype=float), (N,)) / 1e4
    w = np.zeros(N)
    out, turnover, weights_hist = [], [], []
    first = min(ends) if ends else T
    for t in range(first, T):
        day = float(w @ r[t]) if t > first else 0.0
        if t > first and 1 + day > 0:
            w = w * (1 + r[t]) / (1 + day)                     # drift: weights stay shares of equity
        if t in ends:
            target = np.nan_to_num(weight_fn(t))
            to = np.abs(target - w)
            day -= float(to @ cost)
            turnover.append(float(to.sum()))
            w = target.copy()
            weights_hist.append((dates[t], target))
        out.append(day)
    rets = np.array(out)
    return {"dates": list(dates[first:]), "returns": rets, "equity": np.cumprod(1 + rets),
            "turnover": float(np.mean(turnover) * 12) if turnover else None, "last_weights": weights_hist[-1] if weights_hist else None}


def correlation(series: Dict[str, np.ndarray]) -> Dict[str, Dict[str, float]]:
    keys = list(series)
    m = np.vstack([series[k] for k in keys])
    c = np.corrcoef(m)
    return {a: {b: round(float(c[i, j]), 3) for j, b in enumerate(keys)} for i, a in enumerate(keys)}


def combine_erc(series: Dict[str, np.ndarray], lookback: int = 252, rebalance: int = 21) -> Dict[str, object]:
    """Walk-forward equal-risk-contribution mix of strategy return streams (aligned daily):
    re-estimated every `rebalance` days on the trailing `lookback`."""
    from api.calculations.optimizer import erc, shrunk_cov
    keys = list(series)
    R = np.column_stack([series[k] for k in keys])
    T = R.shape[0]
    w = np.ones(len(keys)) / len(keys)
    out, hist = [], []
    for t in range(T):
        if t >= lookback and (t - lookback) % rebalance == 0:
            w = erc(shrunk_cov(R[t - lookback:t]), 1.0)
            hist.append(w.copy())
        out.append(float(w @ R[t]) if t >= lookback else 0.0)
    return {"returns": np.array(out[lookback:]), "weights": dict(zip(keys, (hist[-1] if hist else w).round(4).tolist())),
            "avg_weights": dict(zip(keys, (np.mean(hist, axis=0) if hist else w).round(4).tolist()))}
