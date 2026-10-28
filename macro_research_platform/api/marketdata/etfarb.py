"""
ETF premium / discount to NAV — the gap ETF market makers and authorized participants arbitrage.

When an ETF trades above the value of its holdings (premium), an authorized participant (Jane
Street is one of the largest) buys the basket, delivers it to the fund for new shares and sells
them; at a discount it does the reverse. So the gap is usually tiny — and when it is not, it says
something: the basket is hard to trade (bonds in March 2020: LQD ~−5%), the basket's market is
closed (international ETFs trade on US hours against stale foreign closes), or creations are
restricted.

Premium = last close ÷ NAV per share − 1, both as of the same close (Yahoo's NAV is the fund's
last published NAV). Intraday, the move since that close is shown separately — it is not a premium.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.marketdata.core import Upstream, _cached, yahoo_call

GROUPS: Dict[str, List[str]] = {
    "US equity": ["SPY", "IVV", "VOO", "QQQ", "IWM", "DIA", "VTI", "SMH", "XLE", "XLF", "ARKK"],
    "International equity": ["EFA", "VEA", "EEM", "VWO", "EWJ", "EWZ", "FXI", "INDA", "EWY", "EWT", "EWG", "EWU"],
    "Treasuries & TIPS": ["SHY", "IEF", "TLT", "TIP", "GOVT"],
    "Credit & bonds": ["AGG", "BND", "LQD", "VCIT", "HYG", "JNK", "EMB", "MUB", "BKLN", "MBB"],
    "Commodities": ["GLD", "IAU", "SLV", "USO", "UNG", "DBC"],
    "Crypto": ["IBIT", "FBTC", "GBTC", "ETHA"],
    "Real estate": ["VNQ"],
}
WHY: Dict[str, str] = {
    "International equity": "Holdings trade in other time zones: NAV uses their earlier local closes, so the 'premium' mostly "
                            "reflects news since those markets shut — not mispricing.",
    "Credit & bonds": "NAV marks bonds at evaluated bid prices while the ETF trades near mid, so bond ETFs normally sit at a "
                      "small premium; deep discounts appear when the bond market is stressed (March 2020).",
    "Commodities": "Gold and silver trusts value metal at the London (LBMA) price set hours before the US close, and "
                   "futures funds at settlement times before 4pm — gaps here are mostly the metal or future moving since.",
    "Crypto": "NAV uses a benchmark price at 4pm ET; bitcoin trades 24/7, so small gaps are timing.",
}


def _one(sym: str) -> Optional[Dict[str, Any]]:
    import yfinance as yf
    try:
        i = yahoo_call(lambda: yf.Ticker(sym).info) or {}
    except Upstream:
        raise
    except Exception:                                        # noqa: BLE001 — one fund failing must not sink the table
        return None
    nav, prev, last = i.get("navPrice"), i.get("previousClose"), i.get("regularMarketPrice")
    if not nav or not prev:
        return None
    t = i.get("regularMarketTime")
    return {"symbol": sym, "name": i.get("shortName") or i.get("longName"), "nav": round(float(nav), 4),
            "close": round(float(prev), 4), "last": None if last is None else round(float(last), 4),
            "premium_bp": round((float(prev) / float(nav) - 1) * 1e4, 1),
            "move_since_close_bp": None if not last else round((float(last) / float(prev) - 1) * 1e4, 1),
            "aum": i.get("totalAssets"), "volume": i.get("averageVolume"),
            "expense_pct": i.get("netExpenseRatio"),                       # Yahoo quotes this in percent (SPY 0.0945)
            "as_of": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if t else None}


def snapshot() -> Dict[str, Any]:
    """ETF premium / discount to NAV across groups, flagging suspect data."""
    def build():
        syms = [(g, s) for g, ss in GROUPS.items() for s in ss]
        with ThreadPoolExecutor(6) as ex:
            got = list(ex.map(lambda gs: _one(gs[1]), syms))
        rows, suspect = [], []
        for (g, _), r in zip(syms, got):
            if not r:
                continue
            r["group"] = g
            # Liquid ETFs are arbitraged to within a few percent even in crises (LQD ≈ −5% in March 2020);
            # a 10%+ gap means Yahoo's NAV is stale or per a different share basis, not a real premium.
            (suspect if abs(r["premium_bp"]) >= 1000 else rows).append(r)
        if not rows:
            raise Upstream("Yahoo returned no NAV data just now — try again shortly.")
        groups = []
        for g in GROUPS:
            rs = [r for r in rows if r["group"] == g]
            if rs:
                prem = sorted(r["premium_bp"] for r in rs)
                groups.append({"group": g, "median_bp": prem[len(prem) // 2], "n": len(rs), "why": WHY.get(g)})
        flagged = [r for r in rows if abs(r["premium_bp"]) >= (50 if r["group"] in WHY else 15)]
        return {"rows": sorted(rows, key=lambda r: -abs(r["premium_bp"])), "groups": groups, "flagged": [r["symbol"] for r in flagged],
                "missing": [s for (_, s), r in zip(syms, got) if not r],
                "unreliable": [{"symbol": r["symbol"], "nav": r["nav"], "close": r["close"]} for r in suspect],
                "note": "Premium = last close ÷ NAV − 1, both as of the same close. Authorized participants (e.g. Jane Street, "
                        "Citadel Securities, Virtu) close gaps by creating or redeeming shares; what is left is mostly costs and "
                        "timing. Flagged: beyond ±15bp for US-traded baskets, ±50bp where the basket trades elsewhere or as bonds. "
                        "NAVs more than 10% from the price are set aside as stale data."}
    return _cached("etfarb:snapshot", 900, build)
