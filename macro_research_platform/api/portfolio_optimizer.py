"""
Portfolio optimisation service (engine: api/calculations/optimizer.py).

For a set of holdings — your positions, the auto (paper) book, or any list of tickers —
estimates risk on ~3 years of daily USD returns (local prices converted at daily FX, so a
global portfolio's risk is measured in one currency), proposes weights by six methods, and
tests each method walk-forward (re-estimated monthly on the trailing year, after costs) so
the choice rests on out-of-sample evidence rather than in-sample fit. Black-Litterman views
come from the entry model's set-up score as it stood on each rebalance day.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from api.calculations import optimizer as op

logger = logging.getLogger(__name__)
_CACHE: Dict[tuple, tuple] = {}
_TTL = 1800
MAX_NAMES = 40


def _usd_returns(symbols: List[str], years: int = 3):
    """(dates, symbols kept, T×n daily USD returns, T×n setup scores aligned to returns)."""
    import pandas as pd
    import yfinance as yf
    from api.calculations.stock_timing import signal_frame
    from api.markets import fx_ticker, minor_unit_factor

    df = yf.download(symbols, period=f"{years + 1}y", interval="1d", auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    closes, highs, lows, ccys = {}, {}, {}, {}
    for s in symbols:
        try:
            sub = df[s] if len(symbols) > 1 else df
            c = sub["Close"].dropna()
        except Exception:
            continue
        if len(c) > 300:
            closes[s], highs[s], lows[s] = c, sub["High"].reindex(c.index), sub["Low"].reindex(c.index)
    if not closes:
        return None
    # Quote currency per symbol (fast metadata), then daily FX → USD.
    for s in closes:
        try:
            ccys[s] = (yf.Ticker(s).fast_info.get("currency") or "USD")
        except Exception:
            ccys[s] = "USD"
    majors = {s: minor_unit_factor(ccys[s]) for s in closes}
    fx_needed = sorted({m for m, _ in majors.values() if m != "USD"})
    fx = {}
    if fx_needed:
        fdf = yf.download([fx_ticker(m) for m in fx_needed], period=f"{years + 1}y", interval="1d",
                          auto_adjust=True, group_by="ticker", threads=True, progress=False)
        for m in fx_needed:
            t = fx_ticker(m)
            try:
                fx[m] = (fdf[t] if len(fx_needed) > 1 else fdf)["Close"].dropna()
            except Exception:
                pass
    usd = {}
    setups = {}
    for s, c in closes.items():
        major, div = majors[s]
        if major == "USD":
            px = c / div
        elif major in fx:
            rate = fx[major].reindex(c.index, method="ffill")
            px = (c / div) / rate
        else:
            continue
        usd[s] = px
        f = signal_frame(c.to_numpy(dtype=float), highs[s].ffill().to_numpy(dtype=float),
                         lows[s].ffill().to_numpy(dtype=float))
        setups[s] = pd.Series(f["setup"].to_numpy(), index=c.index)
    if not usd:
        return None
    panel = pd.DataFrame(usd).ffill().dropna()
    panel = panel.iloc[-(years * 252 + 1):]
    rets = panel.pct_change().iloc[1:]
    keep = [s for s in rets.columns if rets[s].std() > 0]
    rets = rets[keep]
    setup_panel = pd.DataFrame({s: setups[s] for s in keep}).reindex(rets.index, method="ffill")
    last_usd = {s: float(panel[s].iloc[-1]) for s in keep}
    return [d.strftime("%Y-%m-%d") for d in rets.index], keep, rets.to_numpy(), setup_panel.to_numpy(), last_usd


def optimise(symbols: Sequence[str], current_usd: Optional[Dict[str, float]] = None, max_weight: float = 0.25,
             years: int = 3, cost_bps: float = 10.0, current_qty: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """`current_usd` (market values) or `current_qty` (shares, valued at the latest USD
    price) describe the holdings to rebalance from; neither → no trade list."""
    syms = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))[:MAX_NAMES]
    if len(syms) < 2:
        return {"available": False, "reason": "Need at least two holdings with price history to optimise."}
    key = (tuple(sorted(syms)), round(max_weight, 3), years,
           tuple(sorted((k, round(v)) for k, v in (current_usd or {}).items())),
           tuple(sorted((k.upper(), v) for k, v in (current_qty or {}).items())))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    data = _usd_returns(syms, years)
    if not data:
        return {"available": False, "reason": "No price history for these symbols."}
    dates, keep, r, setup, last_usd = data
    if current_qty and not current_usd:
        current_usd = {s: float(q) * last_usd[s] for s, q in ((k.upper(), v) for k, v in current_qty.items())
                       if s in last_usd}
    n = len(keep)
    if n < 2:
        return {"available": False, "reason": "Fewer than two holdings have ~1 year of prices."}
    dropped = [s for s in syms if s not in keep]
    # A cap at or below 1/N leaves equal weight as the only feasible portfolio, so every
    # method would collapse to 1/N; raise it to 2/N (≤ 100%) and say so.
    requested_cap = max_weight
    if max_weight * n < 1.0 + 1e-9:
        max_weight = min(1.0, 2.0 / n)
    cov = op.shrunk_cov(r[-252:])
    cur = np.array([max(0.0, (current_usd or {}).get(s, 0.0)) for s in keep])
    cur_w = cur / cur.sum() if cur.sum() > 0 else None
    latest_setup = [None if not np.isfinite(x) else round(float(x), 3) for x in setup[-1]]

    def setup_at(t):          # scores known at the close before day t
        row = setup[t - 1]
        return [None if not np.isfinite(x) else float(x) for x in row]

    methods, curves = [], {}
    for m in op.METHODS:
        try:
            w = op.weights_for(m, r[-252:], cov, max_weight, cur_w, latest_setup)
            wf = op.walk_forward(r, m, max_weight, cost_bps=cost_bps, prior_w=None, setup_fn=setup_at)
        except Exception as e:
            logger.warning("[optimizer] %s failed: %s", m, e)
            continue
        nav = wf.pop("nav", None)
        if nav is not None:
            curves[m] = nav
        methods.append({"method": m, "label": op.LABELS[m], "citation": op.CITATIONS[m],
                        "weights": {s: round(float(x), 4) for s, x in zip(keep, w)},
                        **op.describe(w, cov), "walk_forward": wf})
    current = {"weights": {s: round(float(x), 4) for s, x in zip(keep, cur_w)}, **op.describe(cur_w, cov)} \
        if cur_w is not None else None
    scored = [m for m in methods if (m["walk_forward"] or {}).get("sharpe") is not None]
    best = max(scored, key=lambda m: m["walk_forward"]["sharpe"])["method"] if scored else None
    ew = next((m for m in methods if m["method"] == "equal_weight"), None)
    beats_1n = [m["method"] for m in scored if ew and ew["walk_forward"].get("sharpe") is not None
                and m["method"] != "equal_weight" and m["walk_forward"]["sharpe"] > ew["walk_forward"]["sharpe"]]
    start = len(dates) - len(next(iter(curves.values()))) if curves else 0
    step = 5
    curve = [{"date": dates[start + k], **{m: round(float(v[k]), 4) for m, v in curves.items()}}
             for k in range(0, len(next(iter(curves.values()))), step)] if curves else []
    total = float(cur.sum())
    trades = None
    if total > 0 and best:
        bw = next(m for m in methods if m["method"] == best)["weights"]
        trades = [{"symbol": s, "current_usd": round(float(cur[i]), 2), "target_usd": round(bw[s] * total, 2),
                   "trade_usd": round(bw[s] * total - float(cur[i]), 2)} for i, s in enumerate(keep)]
        trades.sort(key=lambda t: -abs(t["trade_usd"]))
    out = {"available": True, "symbols": keep, "dropped": dropped, "as_of": dates[-1],
           "window": {"start": dates[0], "end": dates[-1], "estimation_days": 252},
           "max_weight": max_weight, "requested_max_weight": requested_cap,
           "cap_note": (f"A {requested_cap:.0%} cap with {n} holdings only allows equal weights; "
                        f"raised to {max_weight:.0%} so the methods can differ.") if max_weight != requested_cap else None,
           "setup_scores": dict(zip(keep, latest_setup)),
           "methods": methods, "current": current, "best_out_of_sample": best,
           "beats_equal_weight": beats_1n, "curve": curve, "rebalance_to_best": trades,
           "notes": ["Covariance: Ledoit-Wolf shrinkage on the last 252 days of USD returns.",
                     "Walk-forward: re-estimated every 21 days on the trailing 252, costs "
                     f"{cost_bps:g} bp on turnover; the ranking is out of sample.",
                     "Black-Litterman views: entry-model set-up score × 10% a year, confidence |score|."]}
    _CACHE[key] = (time.time(), out)
    if len(_CACHE) > 50:
        _CACHE.pop(next(iter(_CACHE)))
    return out


async def optimise_async(*args, **kwargs) -> Dict[str, Any]:
    return await asyncio.to_thread(optimise, *args, **kwargs)
