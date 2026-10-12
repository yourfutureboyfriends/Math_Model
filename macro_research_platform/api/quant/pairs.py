"""
Pairs trading lab — the classic relative-value stat-arb trade of quant market-neutral desks.

scan()      Engle–Granger cointegration test on every pair in a universe over a formation window:
            hedge ratio (OLS of log prices), ADF test on the spread, mean-reversion half-life.
            With hundreds of pairs, ~5% pass p < 0.05 by luck alone, so the scan reports how many
            would be expected by chance and a Bonferroni-adjusted cut.
backtest()  Trades one pair with no look-ahead: each day the hedge ratio, spread mean and spread
            volatility are re-estimated on the trailing `lookback` days only; enter when the
            z-score passes ±entry, exit inside ±exit, stop out beyond ±stop or after `max_hold`
            days. Signals at day t's close trade at day t+1's close; costs are charged per side on
            traded notional. Gross exposure is 1 (both legs together).

References: Gatev, Goetzmann & Rouwenhorst (2006); Engle & Granger (1987); Vidyamurthy (2004).
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from api.quant import data as qdata


class PairsError(ValueError):
    pass


def _closes(symbols: Sequence[str], start: Optional[str] = None) -> pd.DataFrame:
    pan, missing = qdata.panel(list(symbols), start=start)
    if not pan:
        raise PairsError("No price data could be loaded.")
    return pan["close"]


def _half_life(spread: np.ndarray) -> Optional[float]:
    """Days for the spread to close half its gap: from Δs_t = λ s_{t−1} + c, HL = −ln 2 / λ."""
    s = spread[np.isfinite(spread)]
    if s.size < 30:
        return None
    lag, d = s[:-1], np.diff(s)
    lc = lag - lag.mean()
    v = lc @ lc
    if v <= 0:
        return None
    lam = lc @ (d - d.mean()) / v
    return round(-math.log(2) / lam, 1) if lam < 0 else None


def _eg(la: np.ndarray, lb: np.ndarray) -> Dict[str, Any]:
    """Engle–Granger: OLS log A = α + β log B, ADF on the residual (MacKinnon p-value)."""
    from statsmodels.tsa.stattools import adfuller
    bc = lb - lb.mean()
    beta = float(bc @ (la - la.mean()) / (bc @ bc))
    alpha = float(la.mean() - beta * lb.mean())
    resid = la - alpha - beta * lb
    try:
        stat, p, *_ = adfuller(resid, maxlag=1, regression="c", autolag=None)
    except Exception:
        stat, p = float("nan"), 1.0
    return {"beta": beta, "alpha": alpha, "adf": float(stat), "p": float(p), "resid": resid}


def scan(symbols: Sequence[str], years: float = 2.0, top: int = 25, min_corr: float = 0.4) -> Dict[str, Any]:
    syms, bad = qdata.clean_symbols(symbols)
    if bad:
        raise PairsError(f"Invalid ticker(s): {', '.join(bad[:5])}")
    if not 2 <= len(syms) <= qdata.MAX_SYMBOLS:
        raise PairsError(f"Give 2–{qdata.MAX_SYMBOLS} tickers.")
    if not 0.5 <= years <= 10:
        raise PairsError("Formation window must be 0.5–10 years.")
    close = _closes(syms)
    n = int(round(years * 252))
    win = close.iloc[-n:].dropna(axis=1, thresh=int(n * 0.95)).ffill().dropna()
    if win.shape[1] < 2 or len(win) < 60:
        raise PairsError("Not enough overlapping history for these tickers.")
    logp = np.log(win)
    rets = logp.diff().dropna()
    corr = rets.corr()
    rows: List[Dict[str, Any]] = []
    tested = 0
    for a, b in itertools.combinations(win.columns, 2):
        c = float(corr.loc[a, b])
        if c < min_corr:
            continue
        tested += 1
        # Test both orderings and keep the stronger (Engle–Granger is not symmetric).
        best = None
        for y, x in ((a, b), (b, a)):
            r = _eg(logp[y].to_numpy(), logp[x].to_numpy())
            if best is None or r["adf"] < best[2]["adf"]:
                best = (y, x, r)
        y, x, r = best
        if r["beta"] <= 0:                                # not a hedge: the legs would move the same way
            continue
        hl = _half_life(r["resid"])
        z_now = float((r["resid"][-1] - r["resid"].mean()) / r["resid"].std()) if r["resid"].std() > 0 else None
        rows.append({"a": y, "b": x, "corr": round(c, 3), "hedge_ratio": round(r["beta"], 3),
                     "adf": round(r["adf"], 2), "p_value": round(r["p"], 4), "half_life_days": hl,
                     "z_now": None if z_now is None else round(z_now, 2),
                     "spread_vol": round(float(np.std(np.diff(r["resid"])) * math.sqrt(252)), 4)})
    rows.sort(key=lambda r: r["p_value"])
    alpha = 0.05
    passed = sum(1 for r in rows if r["p_value"] < alpha)
    bonf = alpha / max(tested, 1)
    for r in rows:
        r["significant_after_bonferroni"] = r["p_value"] < bonf
        r["tradeable"] = r["p_value"] < alpha and r["half_life_days"] is not None and 1 <= r["half_life_days"] <= 60
    return {"symbols": list(win.columns), "missing": [s for s in syms if s not in win.columns],
            "window": {"start": str(win.index[0].date()), "end": str(win.index[-1].date()), "days": len(win)},
            "pairs_tested": tested, "min_corr": min_corr, "passed_5pct": passed,
            "expected_by_chance": round(tested * alpha, 1), "bonferroni_p": bonf,
            "pairs": rows[:top],
            "note": (f"{passed} of {tested} pairs pass p < 5%, against about {tested * alpha:.0f} expected by luck alone. "
                     "Cointegration found in-sample often breaks out of sample (Gatev et al. 2006 trade the closest "
                     "pairs and still see returns fade after 2002) — backtest a pair after its formation window.")}


def backtest(a: str, b: str, lookback: int = 252, entry: float = 2.0, exit: float = 0.5, stop: float = 4.0,
             max_hold: int = 60, bps: float = 3.0, start: Optional[str] = None) -> Dict[str, Any]:
    syms, bad = qdata.clean_symbols([a, b])
    if bad or len(syms) != 2:
        raise PairsError("Give two different valid tickers.")
    if not 40 <= lookback <= 1260:
        raise PairsError("Lookback must be 40–1260 days.")
    if not 0 <= exit < entry < stop <= 10:
        raise PairsError("Need 0 ≤ exit < entry < stop ≤ 10 (z-scores).")
    if not 1 <= max_hold <= 500 or not 0 <= bps <= 100:
        raise PairsError("Max hold 1–500 days; costs 0–100 bp.")
    a, b = syms
    close = _closes([a, b]).dropna()
    if start:
        warm = pd.Timestamp(start) - pd.Timedelta(days=int(lookback * 1.6))
        close = close[close.index >= warm]
    if len(close) < lookback + 60:
        raise PairsError("Not enough overlapping history for this pair and lookback.")
    la, lb = np.log(close[a].to_numpy()), np.log(close[b].to_numpy())
    ra, rb = close[a].pct_change().to_numpy(), close[b].pct_change().to_numpy()
    T = len(close)
    z = np.full(T, np.nan)
    beta = np.full(T, np.nan)
    for t in range(lookback - 1, T):                      # estimates use data up to and including t
        ya, xb = la[t - lookback + 1:t + 1], lb[t - lookback + 1:t + 1]
        xc = xb - xb.mean()
        v = xc @ xc
        if v <= 0:
            continue
        bt = xc @ (ya - ya.mean()) / v
        sp = ya - bt * xb
        sd = sp.std()
        if sd > 0:
            beta[t], z[t] = bt, (sp[-1] - sp.mean()) / sd
    pos = np.zeros(T)                                     # +1 long spread (long A, short B), −1 short spread
    held = 0
    trades: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for t in range(T):
        p = pos[t - 1] if t else 0.0
        zt = z[t]
        reason = None
        if not np.isfinite(zt):
            new = p
        elif p == 0:
            new = -1.0 if zt > entry else (1.0 if zt < -entry else 0.0)
        else:
            held += 1
            new = p
            if abs(zt) < exit or (p > 0 and zt > 0) or (p < 0 and zt < 0):
                new, reason = 0.0, "converged"
            elif abs(zt) > stop:
                new, reason = 0.0, "stop-loss"
            elif held >= max_hold:
                new, reason = 0.0, "time stop"
        if new != p:
            if p != 0 and cur is not None:
                cur.update(exit_date=str(close.index[t].date()), exit_z=round(float(zt), 2), reason=reason, days=held)
                trades.append(cur)
                cur = None
            if new != 0:
                cur = {"side": "long spread" if new > 0 else "short spread", "entry_date": str(close.index[t].date()),
                       "entry_z": round(float(zt), 2), "hedge_ratio": round(float(beta[t]), 3)}
                held = 0
        pos[t] = new
    # Leg weights (gross 1) fixed by the hedge ratio at entry; signals trade at the next close.
    wa = np.zeros(T)
    wb = np.zeros(T)
    bt_entry = 1.0
    for t in range(T):
        if pos[t] != 0 and (t == 0 or pos[t - 1] != pos[t]):
            bt_entry = beta[t] if np.isfinite(beta[t]) else 1.0
        if pos[t] != 0:
            g = 1 + abs(bt_entry)
            wa[t], wb[t] = pos[t] / g, -pos[t] * bt_entry / g
    ha, hb = np.r_[0, wa[:-1]], np.r_[0, wb[:-1]]          # held on day t = decided at t−1
    gross = np.nan_to_num(ha * ra) + np.nan_to_num(hb * rb)
    traded = np.abs(np.diff(np.r_[0, ha])) + np.abs(np.diff(np.r_[0, hb]))
    net = gross - traded * bps / 1e4
    first = lookback
    if start:
        first = max(first, int(np.searchsorted(close.index.values, np.datetime64(pd.Timestamp(start)))))
    idx = close.index[first:]
    net, gross_r = net[first:], gross[first:]
    eq = np.cumprod(1 + net)
    yrs = len(net) / 252
    vol = float(np.std(net) * math.sqrt(252))
    in_mkt = float((np.abs(ha[first:]) > 0).mean())
    dd = eq / np.maximum.accumulate(eq) - 1
    closed = [t for t in trades if t["entry_date"] >= str(idx[0].date())]
    for t in closed:
        m = (idx >= pd.Timestamp(t["entry_date"])) & (idx <= pd.Timestamp(t["exit_date"]))
        t["return"] = round(float(np.prod(1 + net[m]) - 1), 4) if m.any() else None
    wins = [t for t in closed if (t.get("return") or 0) > 0]
    thin = max(1, len(idx) // 600)
    return {
        "a": a, "b": b, "params": {"lookback": lookback, "entry": entry, "exit": exit, "stop": stop, "max_hold": max_hold, "bps": bps},
        "period": {"start": str(idx[0].date()), "end": str(idx[-1].date()), "years": round(yrs, 1)},
        "metrics": {"cagr": round(float(eq[-1] ** (1 / yrs) - 1), 4) if yrs > 0 and eq[-1] > 0 else None,
                    "vol": round(vol, 4),
                    "sharpe": round(float(np.mean(net) / np.std(net) * math.sqrt(252)), 2) if np.std(net) > 0 else None,
                    "sharpe_gross": round(float(np.mean(gross_r) / np.std(gross_r) * math.sqrt(252)), 2) if np.std(gross_r) > 0 else None,
                    "max_drawdown": round(float(dd.min()), 4), "time_in_market": round(in_mkt, 3),
                    "trades": len(closed), "win_rate": round(len(wins) / len(closed), 3) if closed else None,
                    "avg_days": round(float(np.mean([t["days"] for t in closed])), 1) if closed else None,
                    "stop_losses": sum(1 for t in closed if t["reason"] == "stop-loss")},
        "curve": [{"date": str(idx[i].date()), "equity": round(float(eq[i]), 5), "z": None if not np.isfinite(z[first + i]) else round(float(z[first + i]), 3),
                   "pos": int(pos[first + i])} for i in sorted(set(range(0, len(idx), thin)) | {len(idx) - 1})],
        "z_now": None if not np.isfinite(z[-1]) else round(float(z[-1]), 2),
        "hedge_ratio_now": None if not np.isfinite(beta[-1]) else round(float(beta[-1]), 3),
        "position_now": {1: "long spread", -1: "short spread"}.get(int(pos[-1]), "flat"),
        "trades": closed[-50:][::-1],
        "notes": ["Rolling estimates use only the trailing lookback window — no look-ahead.",
                  "Signals at the close trade at the next close; costs are per side on traded notional.",
                  "Shorting assumes borrow is available at no fee; hard-to-borrow names cost more."],
    }
