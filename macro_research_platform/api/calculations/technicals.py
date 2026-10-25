"""
Technical snapshot for entry and execution timing (not a trading signal on its own; the investment case is
fundamental). Standard definitions, on daily bars:

  RSI(14)          Wilder: average gain / average loss with smoothing α = 1/14; RSI = 100 − 100/(1+RS)
  SMA 20/50/200    simple moving averages of the close; price vs each, and the 50/200 cross state
  MACD 12/26/9     EMA12 − EMA26 (EMAs with α = 2/(n+1)), signal = EMA9 of MACD, histogram = MACD − signal
  Bollinger 20,2   SMA20 ± 2 population σ; %B = (close − lower)/(upper − lower)
  ATR(14)          Wilder average of true range max(H−L, |H−C₋₁|, |L−C₋₁|); also as % of price
  Volatility       close-to-close log returns, σ × √252, 20 and 60 sessions
  Volume           20-session average vs 60-session average; today's volume as a z-score vs the last 60 sessions
  Levels           20 / 60-session low and high, 52-week low and high (support / resistance ranges)
  Drawdown         maximum peak-to-trough decline over 1 and 5 years, and the distance from the 52-week high
  Relative strength excess return vs a benchmark series over 3 / 6 / 12 months (both in the same currency)
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> Optional[float]:
    d = close.diff().dropna()
    if len(d) < n + 1:
        return None
    gain, loss = d.clip(lower=0), -d.clip(upper=0)
    ag = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1]
    al = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1]
    if al == 0:
        return 100.0
    return float(100 - 100 / (1 + ag / al))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> Optional[float]:
    if len(close) < n + 1:
        return None
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1).dropna()
    return float(tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1])


def max_drawdown(close: pd.Series) -> Optional[float]:
    if len(close) < 2:
        return None
    return float((close / close.cummax() - 1).min())


def snapshot(bars: pd.DataFrame, bench: Optional[pd.Series] = None, px_in_bench_ccy: Optional[pd.Series] = None
             ) -> Dict[str, Any]:
    """bars: DataFrame indexed by date with open, high, low, close, volume (local currency). bench: benchmark
    level series; px_in_bench_ccy: the stock's closes in the benchmark's currency (for relative strength)."""
    b = bars.dropna(subset=["close"]).sort_index()
    c, h, l, v = b["close"], b["high"].fillna(b["close"]), b["low"].fillna(b["close"]), b["volume"].fillna(0)
    out: Dict[str, Any] = {"as_of": str(b.index[-1].date()) if len(b) else None, "sessions": int(len(b))}
    if len(b) < 30:
        out["available"] = False
        out["reason"] = "Under 30 sessions of history."
        return out
    last = float(c.iloc[-1])
    out["available"] = True
    out["price"] = last
    out["rsi14"] = round(rsi(c), 1) if rsi(c) is not None else None
    for n in (20, 50, 200):
        if len(c) >= n:
            sma = float(c.tail(n).mean())
            out[f"sma{n}"] = round(sma, 4)
            out[f"vs_sma{n}"] = round(last / sma - 1, 4)
    if "sma50" in out and "sma200" in out:
        out["trend"] = "50-day above 200-day (uptrend)" if out["sma50"] > out["sma200"] else "50-day below 200-day (downtrend)"
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = e12 - e26
    sig = macd.ewm(span=9, adjust=False).mean()
    out["macd"] = {"macd": round(float(macd.iloc[-1]), 4), "signal": round(float(sig.iloc[-1]), 4),
                   "histogram": round(float(macd.iloc[-1] - sig.iloc[-1]), 4),
                   "state": "above signal" if macd.iloc[-1] > sig.iloc[-1] else "below signal"}
    if len(c) >= 20:
        m, s = float(c.tail(20).mean()), float(c.tail(20).std(ddof=0))
        up, lo = m + 2 * s, m - 2 * s
        out["bollinger"] = {"upper": round(up, 4), "middle": round(m, 4), "lower": round(lo, 4),
                            "pct_b": round((last - lo) / (up - lo), 3) if up > lo else None}
    a = atr(h, l, c)
    if a is not None:
        out["atr14"] = round(a, 4)
        out["atr14_pct"] = round(a / last, 4)
    lr = np.log(c).diff().dropna()
    for n in (20, 60):
        if len(lr) >= n:
            out[f"vol{n}"] = round(float(lr.tail(n).std(ddof=1) * math.sqrt(252)), 4)
    if len(v) >= 60:
        v20, v60 = float(v.tail(20).mean()), float(v.tail(60).mean())
        out["volume_trend"] = round(v20 / v60 - 1, 3) if v60 else None
        hist = v.tail(61).iloc[:-1]
        sd = float(hist.std(ddof=1))
        out["volume_z"] = round((float(v.iloc[-1]) - float(hist.mean())) / sd, 2) if sd > 0 else None
        out["unusual_volume"] = bool(out["volume_z"] is not None and abs(out["volume_z"]) >= 2.5)
    yr = c[c.index > c.index[-1] - pd.Timedelta(days=365)]
    out["levels"] = {"low20": round(float(l.tail(20).min()), 4), "high20": round(float(h.tail(20).max()), 4),
                     "low60": round(float(l.tail(60).min()), 4), "high60": round(float(h.tail(60).max()), 4),
                     "low52w": round(float(yr.min()), 4), "high52w": round(float(yr.max()), 4)}
    out["from_52w_high"] = round(last / float(yr.max()) - 1, 4)
    out["max_drawdown_1y"] = round(max_drawdown(yr), 4)
    five = c[c.index > c.index[-1] - pd.Timedelta(days=5 * 365)]
    out["max_drawdown_5y"] = round(max_drawdown(five), 4)
    out["max_drawdown_5y_years"] = round(len(five) / 252, 1)
    if bench is not None and px_in_bench_ccy is not None and len(bench) > 60:
        rs = {}
        p = px_in_bench_ccy.dropna()
        bb = bench.dropna()
        for label, days in (("3m", 92), ("6m", 183), ("12m", 365)):
            t0 = p.index[-1] - pd.Timedelta(days=days)
            ps, bs = p[p.index >= t0], bb[bb.index >= t0]
            if len(ps) > 10 and len(bs) > 10:
                rs[label] = round(float(ps.iloc[-1] / ps.iloc[0] - (bs.iloc[-1] / bs.iloc[0])), 4)
        out["relative_strength_vs_benchmark"] = rs
    return out
