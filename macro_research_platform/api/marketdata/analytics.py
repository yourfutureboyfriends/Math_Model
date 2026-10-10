"""
Cross-asset analytics functions: seasonality (SEAS), correlation matrix (CORR), relative
rotation graph (RRG) and FX forwards from covered interest parity (FRD). Free data only:
Yahoo prices, FRED short-term rates.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f
from api.marketdata.security import _closes

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── SEAS: seasonality ────────────────────────────────────────────────────────
def seasonality(symbol: str, years: int = 15) -> Dict[str, Any]:
    """Monthly returns by calendar month: average, median, hit rate, best/worst, and this year."""
    s = symbol.strip().upper()
    years = max(3, min(int(years), 40))

    def fetch():
        px = _closes([s], "max", "1d")[s].dropna()
        m = px.resample("ME").last()
        r = m.pct_change().dropna()
        cur_year = r.index[-1].year
        r = r[r.index.year >= cur_year - years]
        if len(r) < 24:
            raise NotFound(f"Not enough history for seasonality on {s}.")
        table: Dict[int, Dict[int, float]] = {}
        for ts, v in r.items():
            table.setdefault(ts.year, {})[ts.month] = float(v)
        hist = r[r.index.year < cur_year]            # statistics exclude the current, partial year
        stats = []
        for mth in range(1, 13):
            v = hist[hist.index.month == mth]
            if len(v) == 0:
                stats.append({"month": MONTHS[mth - 1], "n": 0})
                continue
            stats.append({"month": MONTHS[mth - 1], "n": int(len(v)), "mean": float(v.mean()), "median": float(v.median()),
                          "hit_rate": float((v > 0).mean()), "best": float(v.max()), "worst": float(v.min()),
                          "std": float(v.std()) if len(v) > 1 else None,
                          # t-stat of the mean: is the seasonal effect distinguishable from noise?
                          "t_stat": float(v.mean() / (v.std() / math.sqrt(len(v)))) if len(v) > 2 and v.std() > 0 else None,
                          "this_year": table.get(cur_year, {}).get(mth)})
        yearly = [{"year": y, "months": [table[y].get(k) for k in range(1, 13)],
                   "total": float(np.prod([1 + x for x in table[y].values()]) - 1)} for y in sorted(table, reverse=True)]
        return {"symbol": s, "years": years, "from": str(r.index[0].date()), "stats": stats, "yearly": yearly,
                "note": "Monthly total returns (dividends included where Yahoo adjusts). Statistics use completed years only; "
                        "|t| above ~2 suggests a seasonal effect stronger than chance — most are not.",
                "source": "Yahoo Finance"}
    return _cached(f"seas:{s}:{years}", 6 * 3600, fetch)


# ── CORR: correlation matrix ─────────────────────────────────────────────────
def correlation(symbols: List[str], period: str = "1y", freq: str = "daily") -> Dict[str, Any]:
    syms = list(dict.fromkeys(x.strip().upper() for x in symbols if x.strip()))[:30]
    if len(syms) < 2:
        raise NotFound("Give at least two symbols.")
    if period not in ("3mo", "6mo", "1y", "2y", "5y", "10y") or freq not in ("daily", "weekly"):
        raise NotFound("period 3mo…10y; freq daily or weekly")

    def fetch():
        px = _closes(syms, period).ffill()
        if freq == "weekly":
            px = px.resample("W-FRI").last()
        # log returns on each instrument's own trading days, aligned (different holidays per market)
        rets = np.log(px).diff().dropna(how="all")
        rets = rets.dropna(axis=1, thresh=int(len(rets) * 0.6))
        if rets.shape[1] < 2:
            raise NotFound("Not enough overlapping history.")
        if freq == "daily":
            # Asian/European closes happen before New York's: 2-day returns reduce the
            # non-synchronous-trading bias that understates cross-region correlations
            rets = rets.rolling(2).sum().iloc[1::2]
        c = rets.corr(min_periods=20)
        order = _cluster_order(c)
        c = c.loc[order, order]
        vol = (rets.std() * math.sqrt(52 if freq == "weekly" else 126)).reindex(order)
        return {"symbols": order, "matrix": [[None if pd.isna(v) else round(float(v), 3) for v in row] for row in c.values],
                "volatility": [None if pd.isna(v) else float(v) for v in vol], "observations": int(len(rets)),
                "period": period, "freq": freq,
                "note": "Correlation of log returns" + (" over 2-day windows (reduces the time-zone bias between markets)" if freq == "daily" else "")
                        + ". Ordered so that related instruments sit together.", "source": "Yahoo Finance"}
    return _cached(f"corr:{','.join(syms)}:{period}:{freq}", 1800, fetch)


def _cluster_order(c: pd.DataFrame) -> List[str]:
    """Greedy nearest-neighbour ordering on correlation distance (no scipy needed)."""
    names = list(c.columns)
    if len(names) <= 2:
        return names
    d = 1 - c.fillna(0).values
    start = int(np.argmax(c.fillna(0).values.sum(axis=0)))
    order, left = [start], set(range(len(names))) - {start}
    while left:
        last = order[-1]
        nxt = min(left, key=lambda j: d[last, j])
        order.append(nxt)
        left.remove(nxt)
    return [names[i] for i in order]


# ── RRG: relative rotation graph ─────────────────────────────────────────────
RRG_UNIVERSES = {
    "us_sectors": ("SPY", [("XLK", "Technology"), ("XLF", "Financials"), ("XLV", "Health care"), ("XLE", "Energy"),
                           ("XLI", "Industrials"), ("XLY", "Consumer discr."), ("XLP", "Consumer staples"), ("XLU", "Utilities"),
                           ("XLB", "Materials"), ("XLRE", "Real estate"), ("XLC", "Communication")]),
    "countries": ("ACWI", [("SPY", "US"), ("EWJ", "Japan"), ("EWU", "UK"), ("EWG", "Germany"), ("EWQ", "France"), ("MCHI", "China"),
                           ("EWH", "Hong Kong"), ("INDA", "India"), ("EWT", "Taiwan"), ("EWY", "Korea"), ("EWZ", "Brazil"),
                           ("EWC", "Canada"), ("EWA", "Australia"), ("EWW", "Mexico")]),
    "factors": ("SPY", [("MTUM", "Momentum"), ("QUAL", "Quality"), ("VLUE", "Value"), ("USMV", "Min volatility"), ("SIZE", "Size"),
                        ("IWM", "Small caps"), ("RSP", "Equal weight"), ("SPHB", "High beta"), ("SCHD", "Dividend")]),
    "assets": ("ACWI", [("TLT", "Long Treasuries"), ("IEF", "7-10y Treasuries"), ("LQD", "IG credit"), ("HYG", "High yield"),
                        ("GLD", "Gold"), ("DBC", "Commodities"), ("VNQ", "US REITs"), ("EEM", "EM equities"), ("BTC-USD", "Bitcoin"),
                        ("UUP", "US dollar")]),
}


def rrg(universe: str = "us_sectors", tail: int = 8, benchmark: Optional[str] = None) -> Dict[str, Any]:
    """JdK-style relative rotation: RS-Ratio (trend of relative strength vs the benchmark) and
    RS-Momentum (its rate of change), both normalised around 100, on weekly data. Quadrants:
    leading (>100, >100), weakening (>100, <100), lagging (<100, <100), improving (<100, >100)."""
    if universe not in RRG_UNIVERSES:
        raise NotFound(f"Unknown universe — one of {', '.join(RRG_UNIVERSES)}.")
    bench, members = RRG_UNIVERSES[universe]
    bench = (benchmark or bench).upper()
    tail = max(2, min(int(tail), 26))

    def fetch():
        syms = [m[0] for m in members]
        px = _closes(syms + [bench], "3y").ffill().resample("W-FRI").last().dropna(how="all")
        if bench not in px:
            raise NotFound(f"No prices for the benchmark {bench}.")
        out = []
        n = 10                                     # 10-week normalisation window
        for sym, label in members:
            if sym not in px:
                continue
            rs = (px[sym] / px[bench]).dropna()
            if len(rs) < 3 * n:
                continue
            # RS-Ratio: relative strength vs its 10-week average, z-scored over a year and smoothed.
            # RS-Momentum: how far the RS-Ratio is from its own 10-week average (a smoothed rate of
            # change) — smoothing both axes gives the readable clockwise loops of a real RRG.
            trend = rs / rs.ewm(span=n).mean()
            ratio = (100 + (trend - trend.rolling(52).mean()) / trend.rolling(52).std()).ewm(span=3).mean()
            gap = ratio - ratio.ewm(span=n).mean()
            mom = (100 + gap / gap.rolling(52).std()).ewm(span=3).mean()
            df = pd.DataFrame({"x": ratio, "y": mom}).dropna().iloc[-tail:]
            if df.empty:
                continue
            x, y = float(df["x"].iloc[-1]), float(df["y"].iloc[-1])
            quad = "Leading" if x >= 100 and y >= 100 else "Weakening" if x >= 100 else "Lagging" if y < 100 else "Improving"
            ret_4w = float(px[sym].iloc[-1] / px[sym].iloc[-5] - 1) if len(px[sym].dropna()) > 5 else None
            rel_4w = float(rs.iloc[-1] / rs.iloc[-5] - 1) if len(rs) > 5 else None
            out.append({"symbol": sym, "label": label, "quadrant": quad, "rs_ratio": x, "rs_momentum": y,
                        "trail": [{"date": str(i.date()), "x": float(a), "y": float(b)} for i, a, b in zip(df.index, df["x"], df["y"])],
                        "return_4w": ret_4w, "relative_4w": rel_4w})
        if not out:
            raise NotFound("Not enough history to build the rotation graph.")
        return {"universe": universe, "benchmark": bench, "tail_weeks": tail, "points": out, "as_of": str(px.index[-1].date()),
                "universes": list(RRG_UNIVERSES),
                "method": "Weekly closes. RS = price ÷ benchmark; RS-Ratio = 100 + one-year z-score of RS vs its 10-week average "
                          "(smoothed); RS-Momentum = 100 + z-score of the RS-Ratio's distance from its own 10-week average "
                          "(an open approximation of the JdK RRG).",
                "source": "Yahoo Finance"}
    return _cached(f"rrg:{universe}:{bench}:{tail}", 3600, fetch)


# ── FRD: FX forwards from covered interest parity ────────────────────────────
# 3-month interbank rates (OECD via FRED); the dollar uses the 3-month Treasury bill
SHORT_RATE = {"USD": "DTB3", "EUR": "IR3TIB01DEM156N", "GBP": "IR3TIB01GBM156N", "JPY": "IR3TIB01JPM156N", "CHF": "IR3TIB01CHM156N",
              "CAD": "IR3TIB01CAM156N", "AUD": "IR3TIB01AUM156N", "NZD": "IR3TIB01NZM156N", "SEK": "IR3TIB01SEM156N",
              "NOK": "IR3TIB01NOM156N", "DKK": "IR3TIB01DKM156N", "KRW": "IR3TIB01KRM156N", "MXN": "IR3TIB01MXM156N",
              "ZAR": "IR3TIB01ZAM156N", "INR": "IR3TIB01INM156N", "PLN": "IR3TIB01PLM156N", "CZK": "IR3TIB01CZM156N",
              "HUF": "IR3TIB01HUM156N", "ILS": "IR3TIB01ILM156N", "CNY": "IR3TIB01CNM156N", "BRL": "IR3TIB01BRM156N"}
TENORS = [("1W", 7), ("1M", 30), ("2M", 61), ("3M", 91), ("6M", 182), ("9M", 273), ("1Y", 365)]


def _short_rate(ccy: str) -> Dict[str, Any]:
    sid = SHORT_RATE.get(ccy)
    if not sid:
        raise NotFound(f"No short-term rate for {ccy}.")

    def fetch():
        from api.providers.fred_provider import FREDProvider
        obs = [o for o in (FREDProvider().fetch_series(sid).data or []) if o.value is not None]
        if not obs:
            raise Upstream(f"FRED {sid} unavailable")
        return {"rate": obs[-1].value / 100, "date": str(obs[-1].date)[:10], "series": sid}
    return _cached(f"srate:{ccy}", 86400, fetch)


def fx_forwards(base: str, quote: str) -> Dict[str, Any]:
    """Theoretical outright forwards F = S × (1 + r_quote·t) / (1 + r_base·t) (money-market
    convention, act/360). Real forwards differ by the cross-currency basis (a few bp to tens
    of bp a year)."""
    b, q = base.strip().upper(), quote.strip().upper()
    if b == q:
        raise NotFound("Pick two different currencies.")

    def fetch():
        from api.marketdata.core import quote as get_quote
        sym = f"{b}{q}=X" if b != "USD" else f"{q}=X"
        spot = get_quote(sym).get("price")
        if not spot:
            raise NotFound(f"No spot rate for {b}/{q}.")
        rb, rq = _short_rate(b), _short_rate(q)
        pip = 0.01 if q == "JPY" or (spot > 20) else 0.0001
        rows = []
        for name, days in TENORS:
            t = days / 360
            fwd = spot * (1 + rq["rate"] * t) / (1 + rb["rate"] * t)
            rows.append({"tenor": name, "days": days, "forward": fwd, "points": (fwd - spot) / pip,
                         "annualised_premium": (fwd / spot - 1) * 360 / days})
        from datetime import date
        stale = [c for c, r in ((b, rb), (q, rq)) if (date.today() - date.fromisoformat(r["date"])).days > 90]
        return {"pair": f"{b}/{q}", "spot": spot, "rates": {b: rb, q: rq}, "pip": pip, "tenors": rows,
                "stale_rates": stale,
                "method": "Covered interest parity with 3-month money-market rates (USD: 3-month T-bill), act/360. "
                          "Theoretical: traded forwards also price the cross-currency basis.",
                "source": "Yahoo Finance (spot), FRED / OECD (rates)"}
    return _cached(f"frd:{b}{q}", 600, fetch)
