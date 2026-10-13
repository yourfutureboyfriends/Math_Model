"""
Market-making simulator — Avellaneda–Stoikov (2008) quoting on free intraday bars.

What electronic market makers (Citadel Securities, Jane Street, Virtu…) do at heart: quote a bid
and an ask around a *reservation price* that leans against inventory, earn the spread when both
sides trade, and lose when the price runs away from the inventory they hold.

    reservation  r = mid − q · γ · σ² · τ           (q = inventory in lots, τ = fraction of day left)
    half-spread  h = base · mid + γ · σ² · τ / 2      (base stands in for A–S's (1/γ)·ln(1+γ/k))

σ² is the price variance per day estimated from the previous 60 bars only. γ is calibrated so
that at the inventory limit with a full day to go the quotes lean by 2× the base half-spread,
times the user's `aversion` (0 = symmetric quoting, the comparison run).

Fill model (bars, not the order book): quotes are set from the prior bar's close and fill when
the bar trades *through* them by at least one tick — a crude stand-in for queue position. Inventory
is flattened at each day's last close, paying the base half-spread. Fills are 1 lot each, at most
one per side per bar. Requiring a trade-through means fills happen only when price moves through the
quote (pessimistic: heavy adverse selection), while queue position and faster traders picking off
stale quotes are ignored (optimistic). A rough guide, not a P&L forecast; compare the two runs.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, yahoo_call

INTERVALS = {"1m": "7d", "2m": "30d", "5m": "60d"}
TICK = 0.01
MARKOUT_BARS = 5


def _bars(symbol: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    def fetch():
        df = yahoo_call(lambda: yf.Ticker(symbol).history(period=INTERVALS[interval], interval=interval,
                                                          prepost=False, auto_adjust=False))
        if df is None or df.empty:
            raise NotFound(f"No intraday bars for {symbol}.")
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = pd.DatetimeIndex(df.index)
        return df
    return _cached(f"mm:{symbol}:{interval}", 300, fetch)


def _run(df: pd.DataFrame, gamma: float, base: float, max_inv: int, lot: int, rebate: float) -> Dict[str, Any]:
    days = df.index.date
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(df)
    dmid = np.r_[np.nan, np.diff(c)]
    q = 0
    cash = 0.0
    spread_pnl = rebates = flatten_cost = 0.0
    eq = np.zeros(n)
    inv = np.zeros(n, int)
    fills: List[Dict[str, Any]] = []
    day_pnl: Dict[str, float] = {}
    day_start_eq = 0.0
    bars_per_day = pd.Series(days).value_counts().max()
    for t in range(n):
        new_day = t == 0 or days[t] != days[t - 1]
        if new_day:
            day_start_eq = eq[t - 1] if t else 0.0
            j0 = t
        last_of_day = t == n - 1 or days[t + 1] != days[t]
        mid = c[t - 1] if not new_day else o[t]
        w = dmid[max(1, t - 60):t]
        w = w[np.isfinite(w)]
        if w.size >= 20:
            var_day = float(np.var(w) * bars_per_day)
            tau = max(0.0, 1 - (t - j0) / bars_per_day)
            r = mid - q * gamma * var_day * tau
            half = base * mid + gamma * var_day * tau / 2
            bid = min(math.floor((r - half) / TICK) * TICK, mid - TICK)
            ask = max(math.ceil((r + half) / TICK) * TICK, mid + TICK)
            if q < max_inv and l[t] <= bid - TICK:
                q += 1
                cash -= bid * lot
                spread_pnl += (mid - bid) * lot
                rebates += rebate * lot
                fills.append({"t": t, "side": 1, "px": bid, "mid": mid})
            if q > -max_inv and h[t] >= ask + TICK:
                q -= 1
                cash += ask * lot
                spread_pnl += (ask - mid) * lot
                rebates += rebate * lot
                fills.append({"t": t, "side": -1, "px": ask, "mid": mid})
        if last_of_day and q != 0:                         # flatten at the close, crossing the base spread
            cost = abs(q) * lot * base * c[t]
            cash += q * lot * c[t] - cost
            flatten_cost += cost
            q = 0
        eq[t] = cash + q * lot * c[t] + rebates
        inv[t] = q
        if last_of_day:
            day_pnl[str(days[t])] = eq[t] - day_start_eq
    marks = []
    for f in fills:
        k = min(f["t"] + MARKOUT_BARS, n - 1)
        if days[k] == days[f["t"]]:
            marks.append(f["side"] * (c[k] - f["px"]) / f["px"] * 1e4)
    total = float(eq[-1])
    dp = np.array(list(day_pnl.values()))
    return {"total_pnl": round(total, 2),
            "spread_capture": round(spread_pnl, 2), "rebates": round(rebates, 2), "flatten_cost": round(flatten_cost, 2),
            "inventory_pnl": round(total - spread_pnl - rebates + flatten_cost, 2),
            "fills": len(fills), "round_trips": min(sum(f["side"] > 0 for f in fills), sum(f["side"] < 0 for f in fills)),
            "avg_edge_bps": round(float(np.mean([abs(f["px"] - f["mid"]) / f["mid"] * 1e4 for f in fills])), 2) if fills else None,
            "markout_bps": round(float(np.mean(marks)), 2) if marks else None,
            "max_abs_inventory": int(np.abs(inv).max()) if n else 0,
            "avg_abs_inventory": round(float(np.abs(inv).mean()), 2),
            "win_days": int((dp > 0).sum()), "days": len(dp),
            "daily_sharpe_ann": round(float(dp.mean() / dp.std() * math.sqrt(252)), 2) if dp.size > 1 and dp.std() > 0 else None,
            "worst_day": round(float(dp.min()), 2) if dp.size else None,
            "by_day": [{"date": d, "pnl": round(v, 2)} for d, v in day_pnl.items()],
            "_eq": eq, "_inv": inv}


def simulate(symbol: str, interval: str = "1m", half_spread_bps: float = 1.0, aversion: float = 1.0,
             max_inventory: int = 10, lot: int = 100, rebate_per_share: float = 0.0) -> Dict[str, Any]:
    symbol = symbol.strip().upper()
    if interval not in INTERVALS:
        raise ValueError(f"Interval must be one of {', '.join(INTERVALS)}.")
    if not 0.1 <= half_spread_bps <= 100 or not 0 <= aversion <= 10:
        raise ValueError("Half-spread 0.1–100 bp; risk aversion 0–10×.")
    if not 1 <= max_inventory <= 100 or not 1 <= lot <= 10000 or not -0.01 <= rebate_per_share <= 0.01:
        raise ValueError("Inventory limit 1–100 lots; lot 1–10,000 shares; rebate −$0.01 to $0.01 per share.")
    try:
        df = _bars(symbol, interval)
    except (NotFound, Upstream):
        raise
    except Exception as e:                                   # noqa: BLE001 — yfinance raises many types
        raise Upstream(f"Intraday bars for {symbol} are unavailable right now: {e}")
    if len(df) < 200:
        raise NotFound(f"Too few intraday bars for {symbol} to simulate.")
    base = half_spread_bps / 1e4
    dmid = df["Close"].diff()
    per_day = df.groupby(df.index.date).size().max()
    var_day = float(np.nanmedian(dmid.rolling(60).var().to_numpy()) * per_day)
    mid = float(df["Close"].median())
    g_ref = 2 * (2 * base * mid) / (max_inventory * var_day) if var_day > 0 else 0.0
    runs = {"avellaneda_stoikov": _run(df, g_ref * aversion, base, max_inventory, lot, rebate_per_share),
            "symmetric": _run(df, 0.0, base, max_inventory, lot, rebate_per_share)}
    idx = df.index
    thin = max(1, len(idx) // 800)
    path = [{"t": idx[i].strftime("%m-%d %H:%M"), "price": round(float(df["Close"].iat[i]), 4),
             "eq_as": round(float(runs["avellaneda_stoikov"]["_eq"][i]), 2), "eq_sym": round(float(runs["symmetric"]["_eq"][i]), 2),
             "inv_as": int(runs["avellaneda_stoikov"]["_inv"][i]), "inv_sym": int(runs["symmetric"]["_inv"][i])}
            for i in sorted(set(range(0, len(idx), thin)) | {len(idx) - 1})]
    for r in runs.values():
        r.pop("_eq"), r.pop("_inv")
    px_vol = float(np.log(df["Close"]).diff().std() * math.sqrt(per_day * 252))
    return {"symbol": symbol, "interval": interval, "bars": len(df),
            "period": {"start": idx[0].strftime("%Y-%m-%d %H:%M"), "end": idx[-1].strftime("%Y-%m-%d %H:%M"),
                       "days": int(len(set(idx.date)))},
            "params": {"half_spread_bps": half_spread_bps, "aversion": aversion, "gamma": g_ref * aversion,
                       "max_inventory": max_inventory, "lot": lot, "rebate_per_share": rebate_per_share},
            "market": {"median_price": round(mid, 2), "realized_vol_ann": round(px_vol, 4),
                       "daily_price_sd": round(math.sqrt(var_day), 4) if var_day > 0 else None,
                       "skew_per_lot_open_bps": round(g_ref * aversion * var_day / mid * 1e4, 3) if mid else None},
            "runs": runs, "path": path,
            "caveats": ["Bars hide the order book. A quote fills only when the bar trades through it by a tick, so every fill "
                        "comes with the price moving against you (pessimistic); queue position and faster traders picking "
                        "off stale quotes are ignored (optimistic). Use it to compare quoting rules, not to forecast P&L.",
                        "Yahoo intraday bars are last trades, not mid-quotes; bars can be missing or late.",
                        f"Negative markout = the price kept moving against fills over the next {MARKOUT_BARS} bars (adverse selection).",
                        "Only a few days of history are free at this resolution — far too short to judge a strategy."]}
