"""
Sector EPS revisions from free analyst-estimate data (Yahoo Finance "eps_trend" / "eps_revisions").

For each SPDR sector ETF, its ten largest holdings (Yahoo fund data): the change in the consensus next-fiscal-year
EPS estimate over the last 30 days, and analysts revising up vs down in that window. The sector figure is the
holding-weighted average of the constituents' changes. Cached 12 hours; analysts revise slowly.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional

from api.marketdata.core import _cached, NotFound

logger = logging.getLogger(__name__)

# dashboard sector name → SPDR ETF ("Consumer" is consumer discretionary in the allocation table)
SECTOR_ETF = {"Technology": "XLK", "Financials": "XLF", "Energy": "XLE", "Healthcare": "XLV", "Industrials": "XLI",
              "Consumer Staples": "XLP", "Consumer": "XLY", "Utilities": "XLU", "Materials": "XLB",
              "Real Estate": "XLRE", "Communication": "XLC"}
TOP_N = 10
UP_DOWN_BAND = 0.25          # % change in the estimate counted as a revision direction


def _stock(sym: str) -> Optional[Dict[str, Any]]:
    import yfinance as yf
    t = yf.Ticker(sym)
    tr, rv = t.eps_trend, t.eps_revisions
    if tr is None or tr.empty or "+1y" not in tr.index:
        return None
    cur, ago = tr.loc["+1y", "current"], tr.loc["+1y", "30daysAgo"]
    if cur is None or ago is None or not ago or ago != ago or cur != cur:
        return None
    up = int(rv.loc["+1y", "upLast30days"]) if rv is not None and "+1y" in rv.index else None
    down = int(rv.loc["+1y", "downLast30days"]) if rv is not None and "+1y" in rv.index else None
    return {"symbol": sym, "eps_next_fy": round(float(cur), 3), "eps_30d_ago": round(float(ago), 3),
            "revision_pct": round((float(cur) / float(ago) - 1) * 100, 2) if ago > 0 else None,
            "analysts_up_30d": up, "analysts_down_30d": down}


def _sector(name: str, etf: str) -> Dict[str, Any]:
    import yfinance as yf
    th = yf.Ticker(etf).funds_data.top_holdings
    if th is None or th.empty:
        raise NotFound(f"{etf} holdings unavailable")
    hold = [(str(s), float(w)) for s, w in th["Holding Percent"].head(TOP_N).items()]
    with ThreadPoolExecutor(max_workers=5) as ex:
        stocks = list(ex.map(lambda sw: _safe_stock(sw[0]), hold))
    rows = [(st, w) for st, (_, w) in zip(stocks, hold) if st and st.get("revision_pct") is not None]
    if not rows:
        return {"etf": etf, "available": False, "constituents": []}
    wsum = sum(w for _, w in rows)
    rev = sum(st["revision_pct"] * w for st, w in rows) / wsum
    up = sum(st["analysts_up_30d"] or 0 for st, _ in rows)
    down = sum(st["analysts_down_30d"] or 0 for st, _ in rows)
    return {"etf": etf, "available": True,
            "eps_revision_pct": round(rev, 2),
            "direction": "UP" if rev > UP_DOWN_BAND else "DOWN" if rev < -UP_DOWN_BAND else "FLAT",
            "analysts_up_30d": up, "analysts_down_30d": down,
            "breadth": round((up - down) / (up + down), 2) if up + down else None,
            "coverage_weight": round(wsum, 3), "constituents_used": len(rows),
            "constituents": [{**st, "weight": round(w, 4)} for st, w in rows]}


def _safe_stock(sym: str):
    try:
        return _stock(sym)
    except Exception as e:
        logger.debug("[eps] %s: %s", sym, e)
        return None


def sector_revisions() -> Dict[str, Any]:
    def fetch():
        out = {}
        for name, etf in SECTOR_ETF.items():
            try:
                out[name] = _sector(name, etf)
            except Exception as e:
                logger.info("[eps] sector %s failed: %s", name, e)
                out[name] = {"etf": etf, "available": False, "constituents": []}
        ok = {k: v for k, v in out.items() if v.get("available")}
        if not ok:
            raise NotFound("No sector EPS-revision data (Yahoo estimates unavailable).")
        strongest = max(ok, key=lambda k: ok[k]["eps_revision_pct"])
        weakest = min(ok, key=lambda k: ok[k]["eps_revision_pct"])
        return {"sectors": out, "strongest_positive_revision": strongest, "strongest_negative_revision": weakest,
                "computed_at": datetime.now().isoformat(timespec="seconds"),
                "method": (f"Holding-weighted 30-day change in the consensus next-fiscal-year EPS estimate of each SPDR "
                           f"sector ETF's {TOP_N} largest holdings; analysts revising up/down over 30 days."),
                "source": "Yahoo Finance analyst estimates (eps_trend, eps_revisions) and ETF holdings"}
    return _cached("eps:sector_revisions", 12 * 3600, fetch)
