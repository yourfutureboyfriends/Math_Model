"""Screens modelled on standard Bloomberg functions the platform lacked, built from free data:

    IMOV  index movers     — which members moved an index today, in index points (weight × return)
    TRA   total returns    — dividend-reinvested returns over standard periods for a set of assets
    WPE   world valuations — trailing P/E, earnings yield and dividend yield by country, via each country's ETF
    VAP   volume at price  — where an instrument traded most over a window (volume profile, value area)

Each answers from Yahoo's public data. Weights come from the index-members screen (MEMB).
"""
from __future__ import annotations

import logging
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
