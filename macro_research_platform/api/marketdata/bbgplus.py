"""Screens modelled on standard Bloomberg functions the platform lacked, built from free data:

    IMOV  index movers     — which members moved an index today, in index points (weight × return)
    TRA   total returns    — dividend-reinvested returns over standard periods for a set of assets
    WPE   world valuations — trailing P/E, earnings yield and dividend yield by country, via each country's ETF
    VAP   volume at price  — where an instrument traded most over a window (volume profile, value area)
    MRR   member returns   — every index member ranked by its return over a period, against the index
    GE    P/E history      — trailing P/E from filed EPS over up to 15 years, with mean and standard-deviation bands
    WB    world bonds      — 10-year yields across ~35 markets: spreads, policy rate, real yield, 2s10s
    DS    filing search    — the best-matching passages in a company's latest 10-K, 10-Qs and 8-Ks for a question

Each answers from free public data (Yahoo, SEC EDGAR, issuers, BIS, IMF). Weights come from the index-members screen (MEMB).
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f, _info, yahoo_download

logger = logging.getLogger(__name__)

INDEX_TICKER = {"SPX": "^GSPC", "NDX": "^NDX", "INDU": "^DJI"}


def _closes(symbols: List[str], period: str, adjusted: bool) -> pd.DataFrame:
    """Daily closes, one column per symbol (yfinance's shape differs for one symbol vs many)."""
    df = yahoo_download(symbols, period=period, auto_adjust=adjusted, threads=True)
    if df is None or df.empty:
        raise Upstream("Yahoo returned no prices — try again in a minute.")
    c = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": symbols[0]})
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c.sort_index()


# ── IMOV ─────────────────────────────────────────────────────────────────────
def _store_closes(symbols: List[str], index_ticker: str) -> Optional[pd.DataFrame]:
    """Member closes from the local daily-bars store (Massive; well under a second for 500 names) with the index's own
    closes from Yahoo on the same sessions. None when the store is behind the index, so the caller downloads instead."""
    try:
        from api.providers import massive
        days = massive.stored_days()
        if len(days) < 2 or (date.today() - days[-1]).days > 4:
            return None
        panel = massive.panel(symbols, days=6)
        if panel.empty or panel.iloc[-1].notna().sum() < 0.9 * len(symbols):
            return None
        panel.index = pd.to_datetime(panel.index).normalize()
        index = _closes([index_ticker], "7d", adjusted=False)[index_ticker].dropna()
        if index.index[-1] != panel.index[-1]:                     # the index has a newer session than the store
            return None
        return panel.join(index, how="inner")
    except Exception as e:                                          # noqa: BLE001 — fall back to Yahoo
        logger.info("imov store: %s", e)
        return None



def index_movers(code: str, top: int = 15) -> Dict[str, Any]:
    """Each member's contribution to the index's last move: weight × the member's return, in basis points of the
    index and in index points. Breadth and sector contributions summarise the same numbers."""
    code = code.strip().upper()
    if code not in INDEX_TICKER:
        raise NotFound("Index movers covers SPX, NDX and INDU (the indices with free member weights).")

    def build():
        from api.marketdata import funds
        memb = funds.index_members(code)
        members = [m for m in memb["members"] if m.get("weight") and m.get("symbol")]
        if not members:
            raise Upstream("No member weights available right now.")
        ysym = {m["symbol"]: str(m["symbol"]).replace(".", "-") for m in members}   # BRK.B → BRK-B
        idx = INDEX_TICKER[code]
        closes = _store_closes(sorted(set(ysym.values())), idx)
        if closes is None:                                         # store not current: ~500 Yahoo downloads (about a minute)
            closes = _closes(sorted(set(ysym.values())) + [idx], "7d", adjusted=False)
        closes = closes.dropna(how="all")
        if len(closes) < 2:
            raise Upstream("Not enough recent sessions to measure a move.")
        last, prev = closes.iloc[-1], closes.iloc[-2]
        level, level_prev = _f(last.get(idx)), _f(prev.get(idx))
        rows, wsum = [], 0.0
        for m in members:
            p1, p0 = _f(last.get(ysym[m["symbol"]])), _f(prev.get(ysym[m["symbol"]]))
            if not p1 or not p0:
                continue
            r = p1 / p0 - 1
            w = float(m["weight"])
            wsum += w
            rows.append({"symbol": m["symbol"], "name": m.get("name"), "sector": m.get("sector"), "weight": w,
                         "price": p1, "change_pct": r, "contrib_bps": w * r * 1e4})
        if not rows:
            raise Upstream("No member prices came back.")
        for r in rows:   # index points: the member's share of the index's prior level
            r["contrib_pts"] = r["contrib_bps"] / 1e4 * level_prev if level_prev else None
        rows.sort(key=lambda r: r["contrib_bps"])
        sectors: Dict[str, float] = {}
        for r in rows:
            sectors[r["sector"] or "Other"] = sectors.get(r["sector"] or "Other", 0.0) + r["contrib_bps"]
        implied = sum(r["contrib_bps"] for r in rows)
        actual = (level / level_prev - 1) * 1e4 if level and level_prev else None
        return {
            "code": code, "name": memb["name"], "as_of": str(closes.index[-1].date()), "prev_date": str(closes.index[-2].date()),
            "level": level, "change_pts": level - level_prev if level and level_prev else None, "change_bps": actual,
            "implied_bps": implied, "coverage": wsum,
            "advancers": sum(r["change_pct"] > 0 for r in rows), "decliners": sum(r["change_pct"] < 0 for r in rows), "count": len(rows),
            "leaders": rows[::-1][:top], "laggards": rows[:top],
            "sectors": sorted(({"sector": k, "contrib_bps": v} for k, v in sectors.items()), key=lambda x: -x["contrib_bps"]),
            "top10_share": (sum(abs(r["contrib_bps"]) for r in sorted(rows, key=lambda r: -abs(r["contrib_bps"]))[:10])
                            / (sum(abs(r["contrib_bps"]) for r in rows) or 1)),
            "note": memb.get("note"),
            "source": f"{memb['source']}; prices Yahoo Finance (last two sessions). Members' sum can differ from the index "
                      "by float, capping and weight drift since the holdings file.",
        }
    return _cached(f"imov:{code}", 300, build)


# ── TRA ──────────────────────────────────────────────────────────────────────
TRA_SETS: Dict[str, Dict[str, str]] = {
    "assets": {"SPY": "US large cap", "QQQ": "Nasdaq 100", "IWM": "US small cap", "EFA": "Developed ex-US", "EEM": "Emerging markets",
               "AGG": "US aggregate bonds", "TLT": "US Treasuries 20y+", "TIP": "US TIPS", "LQD": "IG credit", "HYG": "High yield",
               "GLD": "Gold", "DBC": "Commodities", "VNQ": "US REITs", "BIL": "T-bills (cash)"},
    "sectors": {"XLK": "Technology", "XLC": "Communication", "XLY": "Consumer discretionary", "XLF": "Financials", "XLV": "Health care",
                "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials", "XLP": "Consumer staples", "XLU": "Utilities", "XLRE": "Real estate"},
    "factors": {"SPY": "Market", "MTUM": "Momentum", "QUAL": "Quality", "VLUE": "Value", "USMV": "Min volatility", "SIZE": "Size",
                "RSP": "Equal weight", "SCHD": "Dividend", "SPHB": "High beta"},
    "countries": {"SPY": "United States", "EWC": "Canada", "EWU": "United Kingdom", "EWG": "Germany", "EWQ": "France", "EWJ": "Japan",
                  "MCHI": "China", "EWH": "Hong Kong", "INDA": "India", "EWY": "South Korea", "EWT": "Taiwan", "EWA": "Australia",
                  "EWZ": "Brazil", "EWW": "Mexico", "EZA": "South Africa"},
}
PERIODS = ["1D", "1W", "1M", "MTD", "QTD", "YTD", "1Y", "3Y", "5Y"]


def _period_returns(s: pd.Series, today: pd.Timestamp) -> Dict[str, Optional[float]]:
    s = s.dropna()
    if len(s) < 2:
        return {p: None for p in PERIODS}
    last = s.iloc[-1]

    def since(start: pd.Timestamp, annualise: Optional[float] = None) -> Optional[float]:
        base = s[s.index <= start]
        if base.empty or s.index[0] > start - timedelta(days=7):   # history doesn't reach back far enough
            return None
        r = last / base.iloc[-1] - 1
        return (1 + r) ** (1 / annualise) - 1 if annualise else r
    q_start = pd.Timestamp(today.year, 3 * ((today.month - 1) // 3) + 1, 1) - timedelta(days=1)
    return {
        "1D": last / s.iloc[-2] - 1, "1W": since(today - timedelta(days=7)), "1M": since(today - pd.DateOffset(months=1)),
        "MTD": since(pd.Timestamp(today.year, today.month, 1) - timedelta(days=1)), "QTD": since(q_start),
        "YTD": since(pd.Timestamp(today.year, 1, 1) - timedelta(days=1)), "1Y": since(today - pd.DateOffset(years=1)),
        "3Y": since(today - pd.DateOffset(years=3), 3), "5Y": since(today - pd.DateOffset(years=5), 5),
    }


def total_returns(set_name: str = "assets", symbols: Optional[str] = None) -> Dict[str, Any]:
    """Dividend-reinvested (adjusted-close) returns over standard periods; 3Y and 5Y annualised."""
    if symbols:
        names = {s.strip().upper(): s.strip().upper() for s in symbols.split(",") if s.strip()}
        if not names or len(names) > 30:
            raise NotFound("Give 1–30 comma-separated symbols.")
        set_name = "custom"
    else:
        if set_name not in TRA_SETS:
            raise NotFound(f"Unknown set — try {', '.join(TRA_SETS)}.")
        names = TRA_SETS[set_name]

    def build():
        closes = _closes(list(names), "6y", adjusted=True)
        today = closes.index[-1]
        rows = []
        for sym, label in names.items():
            if sym not in closes:
                continue
            rows.append({"symbol": sym, "name": label, **_period_returns(closes[sym], today),
                         "vol_1y": _f(closes[sym].dropna().pct_change().iloc[-252:].std() * np.sqrt(252))})
        if not rows:
            raise Upstream("No prices came back for these symbols.")
        return {"set": set_name, "sets": list(TRA_SETS), "periods": PERIODS, "as_of": str(today.date()), "rows": rows,
                "source": "Yahoo Finance adjusted closes (dividends reinvested); 3Y and 5Y annualised; 1Y volatility from daily returns."}
    return _cached(f"tra:{set_name}:{','.join(names)}", 1800, build)


# ── WPE ──────────────────────────────────────────────────────────────────────
COUNTRY_ETF = {"US": "SPY", "CA": "EWC", "GB": "EWU", "DE": "EWG", "FR": "EWQ", "IT": "EWI", "ES": "EWP", "CH": "EWL", "NL": "EWN",
               "SE": "EWD", "JP": "EWJ", "CN": "MCHI", "HK": "EWH", "IN": "INDA", "KR": "EWY", "TW": "EWT", "AU": "EWA",
               "SG": "EWS", "BR": "EWZ", "MX": "EWW", "ZA": "EZA", "SA": "KSA", "ID": "EIDO", "PL": "EPOL", "TR": "TUR"}


def world_valuations() -> Dict[str, Any]:
    """Trailing P/E, earnings yield and dividend yield for each country's broad ETF, with 1-year return and where the
    country sits against the cross-section (cheap / expensive relative to the median)."""
    def build():
        import concurrent.futures as cf
        out: List[Dict[str, Any]] = []

        def one(item):
            iso, etf = item
            try:
                i = _info(etf)
            except Exception as e:                                  # noqa: BLE001 — one failed country is skipped
                logger.info("wpe %s: %s", etf, e)
                return None
            pe = _f(i.get("trailingPE"))
            pe = pe if pe and 0 < pe < 80 else None
            dy = _f(i.get("yield"))
            return {"iso": iso, "etf": etf, "name": i.get("longName") or i.get("shortName"), "pe": pe,
                    "earnings_yield": 1 / pe if pe else None, "div_yield": dy if dy is not None and 0 <= dy < 0.2 else None,
                    "aum": _f(i.get("totalAssets"))}
        with cf.ThreadPoolExecutor(8) as ex:
            out = [r for r in ex.map(one, COUNTRY_ETF.items()) if r]
        # 1-year total return from adjusted closes (Yahoo's fund "52WeekChange" comes in percent for some ETFs, a
        # fraction for others), so it matches TRA
        try:
            closes = _closes([r["etf"] for r in out], "2y", adjusted=True)
            today = closes.index[-1]
            for r in out:
                r["ret_1y"] = _period_returns(closes[r["etf"]], today)["1Y"] if r["etf"] in closes else None
        except Exception as e:                                      # noqa: BLE001 — valuations still show without returns
            logger.info("wpe returns: %s", e)
            for r in out:
                r["ret_1y"] = None
        pes = sorted(r["pe"] for r in out if r["pe"])
        if not pes:
            raise Upstream("Yahoo returned no valuation data — try again shortly.")
        med = float(np.median(pes))
        for r in out:
            r["vs_median"] = r["pe"] / med - 1 if r["pe"] else None
        out.sort(key=lambda r: (r["pe"] is None, r["pe"] or 0))
        return {"as_of": str(date.today()), "median_pe": med, "rows": out,
                "source": "Yahoo Finance fund data for each country's iShares/SPDR ETF (trailing P/E of the holdings, "
                          "trailing 12-month distribution yield). ETF P/E excludes loss-makers the way the issuer reports it."}
    return _cached("wpe:v2", 6 * 3600, build)


# ── VAP ──────────────────────────────────────────────────────────────────────
def volume_at_price(symbol: str, days: int = 120, bins: int = 40) -> Dict[str, Any]:
    """Volume profile from daily bars: each session's volume spread evenly across its high–low range, summed into price
    bins. Gives the point of control (most-traded price) and the 70% value area around it."""
    symbol = symbol.strip().upper()
    days = max(20, min(int(days), 750))

    def build():
        from api.marketdata.toolkit import _history
        df = _history(symbol, "5y").iloc[-days:]
        df = df[(df["High"] > 0) & (df["Low"] > 0) & (df["Volume"] > 0)]
        if len(df) < 10:
            raise NotFound(f"Not enough traded sessions for {symbol} (indices and FX have no volume).")
        lo, hi = float(df["Low"].min()), float(df["High"].max())
        if hi <= lo:
            raise NotFound("No price range in this window.")
        edges = np.linspace(lo, hi, bins + 1)
        vol = np.zeros(bins)
        for h, l, v in zip(df["High"].to_numpy(float), df["Low"].to_numpy(float), df["Volume"].to_numpy(float)):
            if h <= l:
                vol[min(np.searchsorted(edges, h, side="right") - 1, bins - 1)] += v
                continue
            overlap = np.clip(np.minimum(edges[1:], h) - np.maximum(edges[:-1], l), 0, None)
            vol += v * overlap / (h - l)
        poc = int(np.argmax(vol))
        # value area: grow from the point of control toward the heavier neighbour until 70% of volume is inside
        lo_i = hi_i = poc
        inside, total = vol[poc], vol.sum()
        while inside < 0.7 * total and (lo_i > 0 or hi_i < bins - 1):
            down = vol[lo_i - 1] if lo_i > 0 else -1
            up = vol[hi_i + 1] if hi_i < bins - 1 else -1
            if up >= down:
                hi_i += 1
                inside += vol[hi_i]
            else:
                lo_i -= 1
                inside += vol[lo_i]
        last = float(df["Close"].iloc[-1])
        return {"symbol": symbol, "days": len(df), "from": str(df.index[0].date()), "to": str(df.index[-1].date()), "last": last,
                "bins": [{"low": float(edges[i]), "high": float(edges[i + 1]), "volume": float(vol[i]), "share": float(vol[i] / total)}
                         for i in range(bins)],
                "poc": float((edges[poc] + edges[poc + 1]) / 2), "value_low": float(edges[lo_i]), "value_high": float(edges[hi_i + 1]),
                "position": "above value" if last > edges[hi_i + 1] else "below value" if last < edges[lo_i] else "inside value",
                "source": "Yahoo Finance daily bars; each day's volume spread evenly over its high–low range (an approximation "
                          "of intraday trading)."}
    return _cached(f"vap:{symbol}:{days}:{bins}", 1800, build)


# ── MRR ──────────────────────────────────────────────────────────────────────
MRR_INDEX = {"SPX": "^GSPC", "NDX": "^NDX", "INDU": "^DJI", "UKX": "^FTSE", "DAX": "^GDAXI", "CAC": "^FCHI", "SX5E": "^STOXX50E",
             "HSI": "^HSI"}
MRR_PERIODS = ["1D", "1W", "1M", "3M", "YTD", "1Y"]


def _returns_table(closes: pd.DataFrame) -> pd.DataFrame:
    """Price returns of every column over MRR_PERIODS, measured from the last close on or before each period's start."""
    closes = closes.dropna(how="all").ffill()
    today = closes.index[-1]
    starts = {"1W": today - timedelta(days=7), "1M": today - pd.DateOffset(months=1), "3M": today - pd.DateOffset(months=3),
              "YTD": pd.Timestamp(today.year, 1, 1) - timedelta(days=1), "1Y": today - pd.DateOffset(years=1)}
    last = closes.iloc[-1]
    out = {"1D": last / closes.iloc[-2] - 1}
    for p, start in starts.items():
        base = closes[closes.index <= start]
        out[p] = (last / base.iloc[-1] - 1) if len(base) and closes.index[0] <= start - timedelta(days=3) else pd.Series(np.nan, index=last.index)
    return pd.DataFrame(out)


def member_returns(code: str, period: str = "YTD") -> Dict[str, Any]:
    """Every member of an index ranked by its price return over a period, against the index itself: how many beat it,
    the spread between the top and bottom fifth, and each sector's median member."""
    code, period = code.strip().upper(), period.strip().upper()
    if code not in MRR_INDEX:
        raise NotFound(f"Member returns covers {', '.join(MRR_INDEX)}.")
    if period not in MRR_PERIODS:
        raise NotFound(f"Period must be one of {', '.join(MRR_PERIODS)}.")

    def build():
        from api.marketdata import funds
        memb = funds.index_members(code)
        members = [m for m in memb["members"] if m.get("symbol")]
        if not members:
            raise Upstream("No members available right now.")
        ysym = {m["symbol"]: str(m["symbol"]).replace(".", "-") if code in INDEX_TICKER else str(m["symbol"]) for m in members}
        syms, idx = sorted(set(ysym.values())), MRR_INDEX[code]
        closes = None
        if code in INDEX_TICKER:                                   # US: the local split-adjusted store, ~a second
            try:
                from api.providers import massive
                days = massive.stored_days()
                if len(days) > 260 and (date.today() - days[-1]).days <= 4:
                    panel = massive.panel(syms, days=400)
                    panel.index = pd.to_datetime(panel.index).normalize()
                    index = _closes([idx], "2y", adjusted=False)[idx].dropna()
                    if index.index[-1] == panel.index[-1] and panel.iloc[-1].notna().sum() >= 0.9 * len(syms):
                        closes = panel.join(index, how="inner")
            except Exception as e:                                  # noqa: BLE001 — fall back to Yahoo
                logger.info("mrr store: %s", e)
        if closes is None:
            closes = _closes(syms + [idx], "2y", adjusted=False)
        else:
            # a one-day move beyond ±50% is usually a reused ticker or a bad print in the store (BNY was a muni fund's
            # ticker until 2026): take those names from Yahoo instead
            jumps = closes[[c for c in syms if c in closes]].ffill().pct_change(fill_method=None).abs().max()
            suspect = [c for c in syms if (jumps.get(c) or 0) > 0.5]
            if suspect:
                try:
                    y = _closes(suspect, "2y", adjusted=False).reindex(closes.index)
                    for c in suspect:
                        if c in y and y[c].notna().any():
                            closes[c] = y[c]
                except Exception as e:                              # noqa: BLE001 — keep the store's numbers
                    logger.info("mrr recheck: %s", e)
        tab = _returns_table(closes)
        if idx not in tab.index:
            raise Upstream("No index level came back.")
        bench = {p: _f(tab.at[idx, p]) for p in MRR_PERIODS}
        rows = []
        for m in members:
            s = ysym[m["symbol"]]
            if s not in tab.index or pd.isna(tab.at[s, period]):
                continue
            rows.append({"symbol": m["symbol"], "name": m.get("name"), "sector": m.get("sector"), "weight": _f(m.get("weight")),
                         **{p: _f(tab.at[s, p]) for p in MRR_PERIODS}})
        if not rows:
            raise Upstream("No member prices came back.")
        rows.sort(key=lambda r: -r[period])
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        vals = np.array([r[period] for r in rows])
        n5 = max(1, len(rows) // 5)
        by_sector: Dict[str, List[float]] = {}
        for r in rows:
            by_sector.setdefault(r["sector"] or "Other", []).append(r[period])
        b = bench[period]
        weighted = [r for r in rows if r["weight"]]
        return {
            "code": code, "name": memb["name"], "period": period, "periods": MRR_PERIODS, "as_of": str(closes.index[-1].date()),
            "index_return": b, "index_returns": bench, "count": len(rows), "members_total": len(members),
            "beat_index": int((vals > b).sum()) if b is not None else None, "median": float(np.median(vals)),
            "equal_weight": float(vals.mean()),
            # today's weights already include the period's moves: start-of-period weight ∝ w / (1 + r)
            "cap_weight": (sum(r["weight"] * r[period] / (1 + r[period]) for r in weighted)
                           / sum(r["weight"] / (1 + r[period]) for r in weighted)) if weighted else None,
            "top_quintile": float(vals[:n5].mean()), "bottom_quintile": float(vals[-n5:].mean()),
            "positive": int((vals > 0).sum()),
            "sectors": sorted(({"sector": k, "median": float(np.median(v)), "count": len(v)} for k, v in by_sector.items()),
                              key=lambda x: -x["median"]),
            "rows": rows,
            "source": f"{memb['source']}; price returns (dividends excluded) from "
                      + ("the local daily-bars store (Massive, split-adjusted)" if code in INDEX_TICKER else "Yahoo Finance") + ".",
        }
    return _cached(f"mrr:{code}:{period}", 900, build)


# ── GE ───────────────────────────────────────────────────────────────────────
def pe_history(symbol: str, years: int = 10) -> Dict[str, Any]:
    """Trailing P/E over time: weekly close ÷ diluted EPS for the last four quarters as first filed with the SEC, with
    the period's mean and ±1/±2 standard-deviation bands and the prices those bands imply on today's earnings."""
    from api.marketdata.extras import _company_only
    symbol = symbol.strip().upper()
    years = max(3, min(int(years), 15))
    _company_only(symbol, "P/E history")

    def build():
        from api.providers import sec_edgar
        if not sec_edgar.resolve(symbol):
            raise NotFound(f"{symbol} doesn't file with the SEC, so there is no filed earnings history for it.")
        eps = sec_edgar.pit_events(symbol).get("eps_ttm") or []
        if len(eps) < 4:
            raise NotFound(f"Not enough quarterly EPS in {symbol}'s filings to build a P/E history.")
        px = _closes([symbol], f"{years + 1}y", adjusted=False)[symbol].dropna()   # split-adjusted, dividends not added back
        try:
            from api.marketdata.corporate import actions
            splits = [(pd.Timestamp(s["date"]), float(s["ratio"])) for s in actions(symbol).get("splits", []) if s.get("ratio")]
        except Exception as e:                                      # noqa: BLE001 — no splits is the common case
            logger.info("ge splits %s: %s", symbol, e)
            splits = []
        # EPS as filed is on the share count of the day; restate it on today's basis like the split-adjusted price
        ev = []
        for filed, val in eps:
            t = pd.Timestamp(filed)
            factor = float(np.prod([r for d, r in splits if d > t])) if splits else 1.0
            ev.append((t + pd.Timedelta(days=1), val / factor))
        es = pd.Series(dict(ev)).sort_index()
        es = es[~es.index.duplicated(keep="last")]
        wk = px.resample("W-FRI").last().dropna()
        wk = wk[wk.index >= wk.index[-1] - pd.DateOffset(years=years)]
        e_on = es.reindex(wk.index.union(es.index)).ffill().reindex(wk.index)
        filed_on = pd.Series(es.index, index=es.index).reindex(wk.index.union(es.index)).ffill().reindex(wk.index)
        e_on[(wk.index.to_series() - filed_on).dt.days > 200] = np.nan        # no filing for over six months: unknown
        pe = (wk / e_on).where(e_on > 0)
        valid = pe.dropna()
        if len(valid) < 26:
            raise NotFound(f"{symbol} hasn't had positive earnings for long enough to chart a P/E.")
        # extreme multiples on near-zero earnings swamp the statistics: judge the band on the middle 98%
        lo_q, hi_q = valid.quantile([0.01, 0.99])
        core = valid[(valid >= lo_q) & (valid <= hi_q)]
        mean, sd, med = float(core.mean()), float(core.std()), float(core.median())
        last_eps, last_px = _f(e_on.iloc[-1]), float(wk.iloc[-1])
        cur = last_px / last_eps if last_eps and last_eps > 0 else None
        bands = {"-2sd": mean - 2 * sd, "-1sd": mean - sd, "mean": mean, "+1sd": mean + sd, "+2sd": mean + 2 * sd}
        return {
            "symbol": symbol, "years": years, "as_of": str(wk.index[-1].date()), "price": last_px, "eps_ttm": last_eps, "pe": cur,
            "mean": mean, "median": med, "sd": sd, "min": float(valid.min()), "max": float(valid.max()),
            "percentile": float((valid < cur).mean()) if cur else None, "z": (cur - mean) / sd if cur and sd else None,
            "bands": bands,
            "band_prices": {k: (v * last_eps if last_eps and last_eps > 0 and v > 0 else None) for k, v in bands.items()},
            "points": [{"date": str(d.date()), "price": float(wk[d]), "eps": _f(e_on[d]), "pe": _f(pe[d])} for d in wk.index],
            "eps_history": [{"date": str((d - pd.Timedelta(days=1)).date()), "eps": float(v)} for d, v in es.items()
                            if d >= wk.index[0] - pd.Timedelta(days=400)],
            "note": "Trailing diluted EPS as first filed (no later restatements), restated for splits. Weeks with negative or "
                    "no recent earnings have no P/E.",
            "source": "SEC EDGAR XBRL (diluted EPS, four quarters summed); prices Yahoo Finance weekly closes.",
        }
    return _cached(f"ge:{symbol}:{years}", 6 * 3600, build)


# ── WB ───────────────────────────────────────────────────────────────────────
STALE_YIELD_DAYS = 45


def world_bonds() -> Dict[str, Any]:
    """Government 10-year yields across ~35 markets with spreads to Treasuries and Bunds, the policy rate, inflation
    and the real yield; plus the 2s10s slope where the issuer publishes a full daily curve."""
    def build():
        from api.marketdata import countries
        from api.marketdata.curves import curves
        from api.marketdata.toolkit import central_banks
        wd = countries.world_data()["countries"]
        try:
            gc = curves()["curves"]
        except Exception as e:                                      # noqa: BLE001 — the 10-years still show
            logger.info("wb curves: %s", e)
            gc = {}
        try:
            cb = {b["code"]: b for b in central_banks()["banks"]}
        except Exception as e:                                      # noqa: BLE001
            logger.info("wb policy rates: %s", e)
            cb = {}
        euro = {"AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK"}
        us10 = _f((wd.get("US") or {}).get("yield_10y"))
        de10 = _f((wd.get("DE") or {}).get("yield_10y"))
        today = date.today()
        rows = []
        for iso, c in wd.items():
            y = _f(c.get("yield_10y"))
            if y is None:
                continue
            ydate = c.get("yield_date")
            age = (today - date.fromisoformat(str(ydate)[:10])).days if ydate else None
            pol = cb.get("XM" if iso in euro else iso)
            infl = _f(c.get("inflation"))
            curve = gc.get(iso) or {}
            pts = {p["tenor"]: p for p in curve.get("points", [])}
            two, thirty = pts.get(2.0), pts.get(30.0)
            rows.append({
                "iso": iso, "name": c["name"], "region": c.get("region"), "currency": c.get("currency"), "rating": c.get("rating"),
                "yield_10y": y, "date": ydate, "daily": bool(age is not None and age <= 7 and "OECD" not in str(c.get("yield_source"))),
                "stale": bool(age is not None and age > STALE_YIELD_DAYS), "source": c.get("yield_source"),
                "change_1m_bp": _f(c.get("yield_change_1m_bp")), "change_1y_bp": _f(c.get("yield_change_1y_bp")),
                "spread_us_bp": (y - us10) * 100 if us10 is not None and iso != "US" else None,
                "spread_de_bp": (y - de10) * 100 if de10 is not None and iso in euro and iso != "DE" else None,
                "policy_rate": _f(pol["rate"]) if pol else None,
                "term_spread_bp": (y - pol["rate"]) * 100 if pol and pol.get("rate") is not None else None,
                "inflation": infl, "real_yield": y - infl if infl is not None else None,
                "yield_2y": two["yield"] if two else None, "yield_30y": thirty["yield"] if thirty else None,
                "slope_2s10s_bp": curve.get("slope_2s10s_bp"), "gov_debt": _f(c.get("gov_debt")),
            })
        if not rows:
            raise Upstream("No government yields available right now.")
        rows.sort(key=lambda r: -r["yield_10y"])
        live = [r for r in rows if not r["stale"]]
        return {"as_of": str(today), "rows": rows, "us_10y": us10, "de_10y": de10,
                "median_10y": float(np.median([r["yield_10y"] for r in live])) if live else None,
                "inverted": [r["iso"] for r in rows if (r["slope_2s10s_bp"] or 0) < 0],
                "negative_real": [r["iso"] for r in live if r["real_yield"] is not None and r["real_yield"] < 0],
                "source": "Issuers' daily curves (US, DE, UK, JP, CA, AU), live quotes where available, OECD monthly averages "
                          "elsewhere; policy rates BIS; inflation IMF WEO (this year's estimate); ratings Damodaran.",
                "note": "Real yield = 10-year minus the IMF's inflation estimate for this year — a rough guide, not a TIPS-style "
                        "market real yield. Euro-area members use the ECB rate."}
    return _cached("wb:v1", 1800, build)


# ── DS: search inside a company's filings ────────────────────────────────────
DS_FORMS = ("10-K", "20-F", "40-F", "10-Q", "8-K")
_STOP = set("a an and are as at be by for from has have how in is it its of on or that the their this to was were what when "
            "which who why will with does did do about any our we they company".split())
_ITEM = re.compile(r"^\s*(item\s+\d+[a-z]?\.?.{0,90}|part\s+i{1,3}v?\b.{0,60})$", re.I)


def _terms(q: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-&$%.]*[a-z0-9%]|[a-z0-9]", q.lower()) if t not in _STOP]


def _stem(t: str) -> str:
    """Crude suffix stripping so 'repurchase', 'repurchased' and 'repurchases' meet on 'repurchas'."""
    for suf in ("ies", "ing", "es", "ed", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t[:-1] if len(t) > 4 and t.endswith("e") else t


def _passages(text: str, size: int = 900) -> List[Dict[str, Any]]:
    """Lines joined into ~size-character passages that end on a sentence where possible, each tagged with the filing
    section (Item 1A …) it sits in. EDGAR's inline XBRL breaks text into many short lines, not blank-line paragraphs."""
    out, buf, n, section = [], [], 0, None

    def flush():
        nonlocal buf, n
        if buf:
            out.append({"section": section, "text": " ".join(buf)})
        buf, n = [], 0
    for line in text.split("\n"):
        ln = re.sub(r"\s+", " ", line).strip()
        if not ln:
            continue
        if len(ln) < 120 and _ITEM.match(ln):
            flush()
            section = ln[:100]
            continue
        buf.append(ln)
        n += len(ln) + 1
        if n >= size and (ln.endswith((".", ":", ";")) or n >= 1.6 * size):
            flush()
    flush()
    return [x for x in out if len(x["text"]) > 80]


def _recent_documents(symbol: str, forms: List[str], per_form: Dict[str, int]) -> List[Dict[str, Any]]:
    from api.marketdata.extras import _sec_get
    from api.providers import sec_edgar
    ent = sec_edgar.resolve(symbol)
    cik = ent.get("cik") if isinstance(ent, dict) else ent
    if not cik:
        raise NotFound(f"{symbol} doesn't file with the SEC, so its filings can't be searched here.")
    try:
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
    except Exception:                                               # SEC unreachable: the bulk index on disk
        f = sec_edgar._bulk_file("submissions", int(cik))
        if not f:
            raise
        import json
        sub = json.loads(f.read_text())
    r = sub["filings"]["recent"]
    taken: Dict[str, int] = {}
    docs = []
    for i, form in enumerate(r["form"]):
        if form not in forms or taken.get(form, 0) >= per_form.get(form, 1):
            continue
        taken[form] = taken.get(form, 0) + 1
        acc = r["accessionNumber"][i].replace("-", "")
        docs.append({"form": form, "filed": r["filingDate"][i], "period": r.get("reportDate", [None] * len(r["form"]))[i] or None,
                     "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{r['primaryDocument'][i]}"})
    return docs


def filing_search(symbol: str, query: str, forms: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    """Search the text of a company's latest annual report, recent quarterly reports and 8-Ks (with their press-release
    exhibits) for a question or phrase; the best-matching passages come back ranked (BM25), with the section and filing
    they come from."""
    symbol = symbol.strip().upper()
    terms = _terms(query or "")
    if not terms:
        raise NotFound("Type a few words to search for, e.g. 'share repurchase' or 'China revenue risk'.")
    want = [f for f in (forms.split(",") if forms else DS_FORMS) if f in DS_FORMS] or list(DS_FORMS)
    limit = max(1, min(int(limit), 30))

    def corpus():
        from api.marketdata.research import filing_text
        import concurrent.futures as cf
        docs = _recent_documents(symbol, list(DS_FORMS), {"10-K": 1, "20-F": 1, "40-F": 1, "10-Q": 2, "8-K": 3})
        if not docs:
            raise NotFound(f"No annual, quarterly or current reports found for {symbol}.")

        def load(d):
            try:
                t = filing_text(d["url"], max_chars=1_500_000)
            except Exception as e:                                  # noqa: BLE001 — one unreadable filing is skipped
                logger.info("ds %s: %s", d["url"], e)
                return d, []
            ps = [{**p, "part": "main"} for p in _passages(t["text"])]
            for ex in t.get("exhibits", []):
                ps += [{**p, "part": ex["name"], "section": p["section"] or "Press release (exhibit 99)"} for p in _passages(ex["text"])]
            return d, ps
        with cf.ThreadPoolExecutor(3) as ex:
            loaded = list(ex.map(load, docs))
        return [{**d, "passages": ps} for d, ps in loaded]
    docs = _cached(f"ds:corpus3:{symbol}", 6 * 3600, corpus)
    pool = [(d, p) for d in docs if d["form"] in want for p in d["passages"]]
    if not pool:
        raise NotFound("Those filings couldn't be read — try again shortly.")
    qs = [_stem(t) for t in terms]
    toks = [[_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9\-&$%.]*[a-z0-9%]|[a-z0-9]", p["text"].lower())] for _, p in pool]
    n = len(toks)
    avg = sum(len(t) for t in toks) / n
    df = {q: sum(1 for t in toks if q in t) for q in set(qs)}
    phrase = re.sub(r"\s+", " ", query.strip().lower())
    scored = []
    for (d, p), t in zip(pool, toks):
        s = 0.0
        L = len(t)
        for q in set(qs):
            tf = t.count(q)
            if tf:
                idf = np.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * L / avg))
        if not s:
            continue
        if len(qs) > 1 and phrase in p["text"].lower():
            s *= 1.6                                                # the exact phrase
        coverage = sum(1 for q in set(qs) if q in t) / len(set(qs))
        if sum(w[:1].isdigit() or w in ("$", "%", "na") for w in t) > 0.3 * L:
            s *= 0.4                                                # mostly figures: a table, rarely the answer
        scored.append((s * (0.5 + coverage), d, p, coverage))
    scored.sort(key=lambda x: -x[0])
    hits = []
    pat = re.compile(r"\b(" + "|".join(re.escape(q) for q in sorted(set(qs), key=len, reverse=True)) + r")", re.I)
    for s, d, p, cov in scored[:limit]:
        text = p["text"]
        m = pat.search(text)
        if m and m.start() > 150:                                   # open at the sentence holding the first match
            cut = max(text.rfind(". ", 0, m.start()) + 2, m.start() - 400)
            text = "… " + text[cut:]
        hits.append({"form": d["form"], "filed": d["filed"], "period": d["period"], "url": d["url"], "section": p["section"],
                     "part": p["part"], "text": text[:1500], "score": round(float(s), 2), "coverage": cov})
    return {"symbol": symbol, "query": query, "terms": terms, "forms": want, "hits": hits, "matches": len(scored),
            "documents": [{k: d[k] for k in ("form", "filed", "period", "url")} | {"passages": len(d["passages"])} for d in docs],
            "source": "SEC EDGAR full text of the latest 10-K (or 20-F/40-F), the last two 10-Qs and the last three 8-Ks with "
                      "their press releases; ranked by BM25 relevance."}
