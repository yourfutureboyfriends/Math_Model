"""
Fund benchmark in the fund's base currency.

BIFS: 50% MSCI World + 50% MSCI World Equal Weighted, net total return, GBP. MSCI's index levels are licensed, so
each half is proxied by an accumulating UCITS ETF tracking that index — its price reinvests the (withholding-taxed)
dividends, which is what a net-total-return index measures, less the ETF's ongoing charge:

  MSCI World                    iShares Core MSCI World UCITS ETF (Acc), LSE, GBp      SWDA.L  TER 0.20%  from 2009
  MSCI World Equal Weighted     Invesco MSCI World Equal Weight UCITS ETF (Acc), LSE, USD  MWEQ.L  TER 0.20%  from 4 Sep 2024

Each leg is converted to the base currency at the same day's FX (WM-style daily close as Yahoo reports it) and the
blend is rebalanced daily (r = 0.5 r_world + 0.5 r_equal_weight) — the usual convention for a composite benchmark.
Before the equal-weighted ETF existed there is no free equal-weighted MSCI World series: the blended benchmark starts
on its first full day and earlier days are reported as unavailable, never filled with the cap-weighted leg.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "BIFS": {"label": "50% MSCI World + 50% MSCI World Equal Weighted (net TR)",
             "legs": [{"index": "MSCI World", "proxy": "SWDA.L", "weight": 0.5, "ter": 0.0020,
                       "proxy_name": "iShares Core MSCI World UCITS ETF USD (Acc), London (GBp)"},
                      {"index": "MSCI World Equal Weighted", "proxy": "MWEQ.L", "weight": 0.5, "ter": 0.0020,
                       "proxy_name": "Invesco MSCI World Equal Weight UCITS ETF USD Acc, London (USD)"}]},
    "MSCI_WORLD": {"label": "MSCI World (net TR)",
                   "legs": [{"index": "MSCI World", "proxy": "SWDA.L", "weight": 1.0, "ter": 0.0020,
                             "proxy_name": "iShares Core MSCI World UCITS ETF USD (Acc), London (GBp)"}]},
    "SPY": {"label": "S&P 500 (SPY, total return)",
            "legs": [{"index": "S&P 500", "proxy": "SPY", "weight": 1.0, "ter": 0.0009, "proxy_name": "SPDR S&P 500 ETF"}]},
}


def _closes_local(sym: str) -> pd.Series:
    """Daily adjusted closes (total return for an accumulating fund) in the listing's quote currency, with it."""
    from api.marketdata.core import _cached

    def fetch():
        import yfinance as yf
        h = yf.Ticker(sym).history(period="max", auto_adjust=True)
        ccy = (yf.Ticker(sym).fast_info or {}).get("currency")
        if h is None or h.empty:
            raise ValueError(f"no price history for {sym}")
        s = h["Close"].dropna()
        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        return {"dates": [d.strftime("%Y-%m-%d") for d in s.index], "close": s.tolist(), "currency": ccy}
    d = _cached(f"bench:closes:{sym}", 6 * 3600, fetch)
    s = pd.Series(d["close"], index=pd.to_datetime(d["dates"]))
    s.attrs["currency"] = d.get("currency") or "USD"
    return s[~s.index.duplicated(keep="last")]


def in_base(sym: str, base: str) -> pd.Series:
    """A listing's daily closes converted to the base currency at each day's FX (pence → pounds etc.)."""
    from api.calculations import fx_accounting as fa
    from api.markets import minor_unit_factor
    s = _closes_local(sym)
    major, div = minor_unit_factor(s.attrs.get("currency"))
    if major == base.upper():
        return s / div
    usd = fa._major_usd_series(major) if major != "USD" else None
    b = fa._major_usd_series(base) if base.upper() != "USD" else None
    idx = s.index
    usd_per = (usd.reindex(usd.index.union(idx)).ffill().reindex(idx) if usd is not None else 1.0)
    usd_per_base = (b.reindex(b.index.union(idx)).ffill().reindex(idx) if b is not None else 1.0)
    out = s / div * usd_per / usd_per_base
    return out.dropna()


def series(code: str = "BIFS", base: str = "GBP") -> Dict[str, Any]:
    """Daily benchmark returns in the base currency on the days every leg traded (from the first day all legs
    exist), the index rebased to 100, and the legs' own returns."""
    spec = BENCHMARKS[code]
    legs = {leg["proxy"]: in_base(leg["proxy"], base) for leg in spec["legs"]}
    frame = pd.DataFrame(legs).dropna()
    rets = frame.pct_change().dropna()
    w = np.array([leg["weight"] for leg in spec["legs"]])
    blend = pd.Series(rets.to_numpy() @ w, index=rets.index)            # daily rebalanced
    starts = {leg["proxy"]: str(legs[leg["proxy"]].index[0].date()) for leg in spec["legs"]}
    return {"code": code, "label": spec["label"], "currency": base, "returns": blend,
            "legs": {k: rets[k] for k in rets.columns}, "start": str(blend.index[0].date()) if len(blend) else None,
            "end": str(blend.index[-1].date()) if len(blend) else None, "leg_starts": starts,
            "proxies": spec["legs"]}


def summary(code: str = "BIFS", base: str = "GBP") -> Dict[str, Any]:
    """Performance of the benchmark over standard windows, with what it is and what it is not."""
    s = series(code, base)
    r = s["returns"]
    if r.empty:
        return {"available": False, "reason": "No common history for the benchmark's legs."}
    idx = (1 + r).cumprod() * 100
    end = r.index[-1]

    def window(days: Optional[int] = None, ytd: bool = False) -> Optional[float]:
        if ytd:
            sub = r[r.index >= pd.Timestamp(year=end.year, month=1, day=1)]
        else:
            sub = r[r.index > end - pd.Timedelta(days=days)]
        return round(float((1 + sub).prod() - 1), 4) if len(sub) else None
    vol = float(r.tail(252).std(ddof=1) * np.sqrt(252)) if len(r) > 20 else None
    legs = {k: round(float((1 + v[v.index > end - pd.Timedelta(days=365)]).prod() - 1), 4) for k, v in s["legs"].items()}
    return {"available": True, "code": code, "label": s["label"], "currency": base, "as_of": s["end"], "start": s["start"],
            "returns": {"1m": window(31), "3m": window(92), "ytd": window(ytd=True), "1y": window(365),
                        "since_start": round(float(idx.iloc[-1] / 100 - 1), 4)},
            "volatility_1y": round(vol, 4) if vol else None, "legs_1y": legs, "leg_starts": s["leg_starts"],
            "proxies": s["proxies"], "rebalancing": "daily (each day's return = weighted sum of the legs' returns)",
            "history": [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 3)} for d, v in idx.items()][-800:],
            "limitations": ["Each half is an accumulating UCITS ETF tracking the index (net of its ~0.20% a year "
                            "ongoing charge and any tracking difference), not MSCI's licensed index level.",
                            f"The blend starts {s['start']}: no free MSCI World Equal Weighted series exists before "
                            "the proxy ETF launched (MWEQ.L, Sep 2024).",
                            "MSCI constituents and official weights are licensed: active weights against the "
                            "benchmark at stock level are not available."] if code == "BIFS" else []}


def returns_in_base(symbols: List[str], base: str) -> pd.DataFrame:
    """Daily returns of holdings in the base currency (local return and currency move together)."""
    cols = {}
    for s in symbols:
        try:
            cols[s] = in_base(s, base)
        except Exception:                                                     # noqa: BLE001 — reported as missing
            continue
    return pd.DataFrame(cols).pct_change()
