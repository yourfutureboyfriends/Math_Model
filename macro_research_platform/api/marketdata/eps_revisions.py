"""
Sector EPS revisions from free analyst-estimate data (Yahoo Finance "eps_trend" / "eps_revisions").

Every S&P 500 member (SPY's daily holdings file, with index weights): the change in the consensus next-fiscal-year
EPS estimate over the last 30 days, and analysts revising up vs down in that window. A sector's figure is the
index-weighted average of its members' changes. If the holdings file can't be read, each SPDR sector ETF's ten
largest holdings are used instead. Cached 12 hours; analysts revise slowly.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

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


# GICS (SSGA file) and Yahoo sector names → the allocation table's names
_GICS = {"Information Technology": "Technology", "Technology": "Technology", "Financials": "Financials",
         "Financial Services": "Financials", "Health Care": "Healthcare", "Healthcare": "Healthcare",
         "Consumer Discretionary": "Consumer", "Consumer Cyclical": "Consumer", "Consumer Staples": "Consumer Staples",
         "Consumer Defensive": "Consumer Staples", "Industrials": "Industrials", "Energy": "Energy",
         "Utilities": "Utilities", "Materials": "Materials", "Basic Materials": "Materials", "Real Estate": "Real Estate",
         "Communication Services": "Communication"}


def _yahoo_sector(sym: str) -> Optional[str]:
    try:
        import yfinance as yf
        return (yf.Ticker(sym).info or {}).get("sector")
    except Exception:
        return None


def _index_wide() -> Dict[str, Dict[str, Any]]:
    """Per sector: index-weighted revision across all S&P 500 members."""
    from api.marketdata.funds import index_members
    members = [m for m in index_members("SPX")["members"] if m.get("symbol") and m.get("weight")]
    if len(members) < 400:
        raise NotFound("S&P 500 holdings incomplete")
    for m in members:
        m["yf"] = str(m["symbol"]).replace(".", "-")             # BRK.B → BRK-B
    with ThreadPoolExecutor(max_workers=8) as ex:
        stocks = list(ex.map(lambda m: _safe_stock(m["yf"]), members))
        missing = [m for m in members if not m.get("sector")]
        for m, sec in zip(missing, ex.map(lambda m: _yahoo_sector(m["yf"]), missing)):
            m["sector"] = sec
    by: Dict[str, List] = {}
    for m, st in zip(members, stocks):
        sec = _GICS.get(m.get("sector") or "")
        if sec and st and st.get("revision_pct") is not None:
            by.setdefault(sec, []).append((st, m["weight"], m))
    out = {}
    for name, etf in SECTOR_ETF.items():
        rows = by.get(name) or []
        if not rows:
            out[name] = {"etf": etf, "available": False, "constituents": []}
            continue
        wsum = sum(w for _, w, _ in rows)
        rev = sum(st["revision_pct"] * w for st, w, _ in rows) / wsum
        up = sum(st["analysts_up_30d"] or 0 for st, _, _ in rows)
        down = sum(st["analysts_down_30d"] or 0 for st, _, _ in rows)
        n_up = sum(1 for st, _, _ in rows if st["revision_pct"] > UP_DOWN_BAND)
        n_dn = sum(1 for st, _, _ in rows if st["revision_pct"] < -UP_DOWN_BAND)
        movers = sorted(rows, key=lambda r: -abs(r[0]["revision_pct"]) * r[1])[:5]
        out[name] = {"etf": etf, "available": True, "eps_revision_pct": round(rev, 2),
                     "direction": "UP" if rev > UP_DOWN_BAND else "DOWN" if rev < -UP_DOWN_BAND else "FLAT",
                     "analysts_up_30d": up, "analysts_down_30d": down,
                     "breadth": round((up - down) / (up + down), 2) if up + down else None,
                     "companies_up": n_up, "companies_down": n_dn,
                     "coverage_weight": round(wsum, 4), "constituents_used": len(rows),
                     "constituents": [{**st, "weight": round(w, 5), "name": m.get("name")} for st, w, m in movers]}
    return out


def sector_revisions() -> Dict[str, Any]:
    def fetch():
        out, basis = None, "all S&P 500 members, index-weighted"
        try:
            out = _index_wide()
        except Exception as e:
            logger.info("[eps] index-wide revisions failed (%s); using sector ETF top holdings", e)
        if not out or not any(v.get("available") for v in out.values()):
            basis, out = f"each SPDR sector ETF's {TOP_N} largest holdings", {}
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
                "basis": basis,
                "method": (f"Weighted 30-day change in the consensus next-fiscal-year EPS estimate — {basis}; "
                           "analysts revising up/down over 30 days."),
                "source": "Yahoo Finance analyst estimates (eps_trend, eps_revisions) and ETF holdings"}
    return _cached("eps:sector_revisions", 12 * 3600, fetch)
