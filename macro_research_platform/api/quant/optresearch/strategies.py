"""
The four defined-risk strategies: their legs, entry signals (causal: computed from data up to the decision close) and
the parameter grids the research explores. Decisions are made at a weekly close; the order fills at the next session's
close (strikes are chosen from that session's price and volatility, as a trader would at execution).

  bull_put      short put at delta Δs, long put `width` below (credit). Uptrend (above the 200-day average, 50 above
                200), implied/realised volatility ratio ≥ iv_rv_min, liquidity.
  bull_call     long call at Δl, short call at Δs (debit). Momentum: 12-1 and 6-1 month momentum positive, cross-sectional
                12-1 rank ≥ mom_q, trend strength ADX ≥ adx_min, above the 50-day average. Debit ≤ max_debit × width
                (breakeven requirement).
  bear_put      long put at Δl, short put at Δs (debit). Downtrend (below 200, 50 below 200, 6-1 momentum < 0); the
                market weak (S&P below its 200-day) and no sharp rebound (S&P 20-day return < max_rebound) — momentum-crash
                guard (Daniel & Moskowitz); implied vol percentile ≤ iv_pct_max (avoid buying expensive puts).
  iron_condor   short put and call at Δs, wings `width` beyond (credit). Range: ADX < adx_max, the 20-day move inside
                range_sigma × the realised-vol-implied move, IV/RV ≥ iv_rv_min.

Widths are fractions of the share price, rounded to the listed strike grid (at least one increment).
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

STRATEGIES = ["bull_put", "bull_call", "bear_put", "iron_condor"]
LABEL = {"bull_put": "Bull put credit spread", "bull_call": "Bull call debit spread",
         "bear_put": "Bear put debit spread", "iron_condor": "Short iron condor"}
CREDIT = {"bull_put": True, "bull_call": False, "bear_put": False, "iron_condor": True}

# Defaults: practitioner-standard starting points (45 DTE, 50% profit-take, 21-DTE exit for credit spreads), not
# optimised values. Grids are explored by the runner; sensitivity is reported around these.
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "bull_put": {"short_delta": 0.25, "width": 0.05, "dte": 45, "iv_rv_min": 1.0, "profit_take": 0.5,
                 "stop_loss": 2.0, "exit_dte": 21},
    "bull_call": {"long_delta": 0.60, "short_delta": 0.30, "dte": 60, "mom_q": 0.8, "adx_min": 20.0, "max_debit": 0.6,
                  "profit_take": 0.75, "stop_loss": 0.5, "exit_dte": 21},
    "bear_put": {"long_delta": 0.60, "short_delta": 0.30, "dte": 45, "max_rebound": 0.05, "iv_pct_max": 0.8,
                 "profit_take": 0.75, "stop_loss": 0.5, "exit_dte": 14},
    "iron_condor": {"short_delta": 0.16, "width": 0.05, "dte": 45, "adx_max": 20.0, "range_sigma": 1.0, "iv_rv_min": 1.1,
                    "profit_take": 0.5, "stop_loss": 2.0, "exit_dte": 21},
}
STRUCTURE = {"bull_put": ("short_delta", "width", "dte"), "bull_call": ("long_delta", "short_delta", "dte"),
             "bear_put": ("long_delta", "short_delta", "dte"), "iron_condor": ("short_delta", "width", "dte")}
EXIT = ("profit_take", "stop_loss", "exit_dte")
FILTERS = {"bull_put": ("iv_rv_min",), "bull_call": ("mom_q", "adx_min", "max_debit"),
           "bear_put": ("max_rebound", "iv_pct_max"), "iron_condor": ("adx_max", "range_sigma", "iv_rv_min")}

GRIDS: Dict[str, Dict[str, List[Any]]] = {
    "bull_put": {"short_delta": [0.15, 0.20, 0.25, 0.30], "width": [0.025, 0.05, 0.10], "dte": [30, 45, 60],
                 "iv_rv_min": [0.0, 1.0, 1.2], "profit_take": [0.5, 0.75, None], "stop_loss": [1.0, 2.0, None],
                 "exit_dte": [21, 7, 0]},
    "bull_call": {"long_delta": [0.50, 0.60, 0.70], "short_delta": [0.20, 0.30, 0.40], "dte": [30, 60, 90],
                  "mom_q": [0.7, 0.8, 0.9], "adx_min": [0.0, 20.0, 25.0], "max_debit": [0.5, 0.6, 0.7],
                  "profit_take": [0.5, 0.75, 1.0], "stop_loss": [0.5, None], "exit_dte": [21, 7, 0]},
    "bear_put": {"long_delta": [0.50, 0.60, 0.70], "short_delta": [0.20, 0.30], "dte": [30, 45, 60],
                 "max_rebound": [0.03, 0.05, 1.0], "iv_pct_max": [0.6, 0.8, 1.0],
                 "profit_take": [0.5, 0.75, 1.0], "stop_loss": [0.5, None], "exit_dte": [14, 7, 0]},
    "iron_condor": {"short_delta": [0.10, 0.16, 0.20], "width": [0.025, 0.05, 0.10], "dte": [30, 45, 60],
                    "adx_max": [15.0, 20.0, 100.0], "range_sigma": [0.75, 1.0, 10.0], "iv_rv_min": [0.0, 1.1, 1.3],
                    "profit_take": [0.25, 0.5, None], "stop_loss": [1.0, 2.0, None], "exit_dte": [21, 7, 0]},
}


# ── Features (causal) ────────────────────────────────────────────────────────
def _adx(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up, dn = high.diff(), -low.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()]).groupby(level=0).max()
    atr = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def features(panel, surf: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """Per (session, underlying) signals, every value using data up to that session's close only."""
    c = panel.frame("close")
    hi, lo = panel.frame("high"), panel.frame("low")
    sma50 = c.rolling(50, min_periods=45).mean()
    sma200 = c.rolling(200, min_periods=180).mean()
    mom12 = c.shift(21) / c.shift(252) - 1
    mom6 = c.shift(21) / c.shift(126) - 1
    ret20 = c / c.shift(20) - 1
    rv21 = pd.DataFrame(surf["rv"]["rv21"], index=c.index, columns=c.columns)
    atm = pd.DataFrame(surf["atm"], index=c.index, columns=c.columns)
    iv_rv = atm / rv21.clip(lower=0.03)
    iv_pct = atm.rolling(252, min_periods=120).rank(pct=True)
    stocks = np.array([panel.info[t].get("kind") == "stock" for t in panel.tickers])
    ranked = mom12.where(pd.Series(stocks, index=c.columns), np.nan)
    mom_rank = ranked.rank(axis=1, pct=True)
    mom_rank = mom_rank.where(pd.Series(stocks, index=c.columns), 1.0)          # ETFs: absolute momentum only
    adx = _adx(hi, lo, c)
    spy = c["SPY"]
    spy_trend = (spy > spy.rolling(200, min_periods=180).mean()).to_numpy()
    spy_ret20 = (spy / spy.shift(20) - 1).to_numpy()
    move = rv21 * np.sqrt(20 / 252)
    f = {"close": c.to_numpy(), "sma50": sma50.to_numpy(), "sma200": sma200.to_numpy(), "mom12": mom12.to_numpy(),
         "mom6": mom6.to_numpy(), "ret20": ret20.to_numpy(), "rv21": rv21.to_numpy(), "iv": atm.to_numpy(),
         "iv_rv": iv_rv.to_numpy(), "iv_pct": iv_pct.to_numpy(), "mom_rank": mom_rank.to_numpy(), "adx": adx.to_numpy(),
         "range_z": (ret20.abs() / move.where(move > 0)).to_numpy(),
         "spy_trend": np.repeat(spy_trend[:, None], c.shape[1], axis=1),
         "spy_ret20": np.repeat(spy_ret20[:, None], c.shape[1], axis=1)}
    return f


def decision_days(dates: pd.DatetimeIndex, first: str) -> np.ndarray:
    """Session positions of the weekly decision closes (last session of each week) from `first` on."""
    w = dates.to_period("W")
    last = np.r_[w[1:] != w[:-1], True]
    return np.where(last & (dates >= pd.Timestamp(first)))[0]


def candidates(name: str, f: Dict[str, np.ndarray], panel, days: np.ndarray, p: Dict[str, Any],
               min_adv: float = 20e6, eligible: np.ndarray | None = None) -> Dict[str, np.ndarray]:
    """Entry candidates (decision day, underlying, score) passing the signal and liquidity filters for parameters p.
    `eligible` [T, N] restricts the universe (e.g. point-in-time S&P membership)."""
    T, N = f["close"].shape
    t = days[days < T - 2]
    g = {k: v[t] for k, v in f.items()}
    ok = np.isfinite(g["close"]) & np.isfinite(g["iv"]) & np.isfinite(g["sma200"]) & (panel.a["adv"][t] >= min_adv)
    ok &= panel.a["observed"][t]
    if eligible is not None:
        ok &= eligible[t]
    up = (g["close"] > g["sma200"]) & (g["sma50"] > g["sma200"])
    down = (g["close"] < g["sma200"]) & (g["sma50"] < g["sma200"])
    if name == "bull_put":
        ok &= up & (g["iv_rv"] >= p["iv_rv_min"])
        score = g["iv_rv"] + 0.5 * np.nan_to_num(g["mom_rank"])
    elif name == "bull_call":
        ok &= (g["mom12"] > 0) & (g["mom6"] > 0) & (g["mom_rank"] >= p["mom_q"]) & (np.nan_to_num(g["adx"]) >= p["adx_min"])
        ok &= g["close"] > g["sma50"]
        score = np.nan_to_num(g["mom_rank"]) + np.nan_to_num(g["adx"]) / 100
    elif name == "bear_put":
        ok &= down & (g["mom6"] < 0) & ~g["spy_trend"].astype(bool) & (g["spy_ret20"] < p["max_rebound"])
        ok &= np.nan_to_num(g["iv_pct"], nan=1.0) <= p["iv_pct_max"]
        score = -np.nan_to_num(g["mom6"])
    elif name == "iron_condor":
        ok &= (np.nan_to_num(g["adx"], nan=99) < p["adx_max"]) & (np.nan_to_num(g["range_z"], nan=99) < p["range_sigma"])
        ok &= g["iv_rv"] >= p["iv_rv_min"]
        score = g["iv_rv"]
    else:
        raise ValueError(f"Unknown strategy {name}")
    ok &= np.isfinite(score)
    ti, ji = np.nonzero(ok)
    return {"t": t[ti], "j": ji, "score": score[ti, ji].astype(np.float32),
            "feat": {k: g[k][ti, ji].astype(np.float32) for k in ("iv_rv", "iv_pct", "mom_rank", "adx", "range_z", "mom6",
                                                                  "spy_ret20")}}


def loosest(name: str) -> Dict[str, Any]:
    """Filter values that admit every candidate any grid point admits — simulate once, filter later."""
    g = GRIDS[name]
    p = dict(DEFAULTS[name])
    for k in FILTERS[name]:
        vals = [v for v in g[k] if v is not None]
        p[k] = max(vals) if k in ("max_rebound", "iv_pct_max", "adx_max", "range_sigma", "max_debit") else min(vals)
    return p


def admits(name: str, feat: Dict[str, np.ndarray], p: Dict[str, Any]) -> np.ndarray:
    """Which simulated candidates pass the (stricter) filter values in p."""
    if name == "bull_put":
        return feat["iv_rv"] >= p["iv_rv_min"]
    if name == "bull_call":
        return (feat["mom_rank"] >= p["mom_q"]) & (np.nan_to_num(feat["adx"]) >= p["adx_min"])
    if name == "bear_put":
        return (feat["spy_ret20"] < p["max_rebound"]) & (np.nan_to_num(feat["iv_pct"], nan=1.0) <= p["iv_pct_max"])
    return ((np.nan_to_num(feat["adx"], nan=99) < p["adx_max"]) & (np.nan_to_num(feat["range_z"], nan=99) < p["range_sigma"])
            & (feat["iv_rv"] >= p["iv_rv_min"]))
