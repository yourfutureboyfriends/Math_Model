"""
Financial Modeling Prep (free plan: US listings, 250 requests a day) — analyst grade history and consensus, price-target
trends, multi-year analyst estimates, and the earnings calendar with revenue estimates. Key: FMP_API_KEY in .env.

The daily allowance is guarded: every response is cached (hours for analyst data), and a counter stops at
DAILY_BUDGET so the platform never trips FMP's limit. Non-US symbols are not requested (they need a paid plan).
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)
BASE = "https://financialmodelingprep.com/stable/"
DAILY_BUDGET = 230                     # of FMP's 250 free requests a day
_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "fmp"
_USAGE = _DIR / "usage.json"           # survives restarts: an in-memory counter reset on every restart
_used = {"day": None, "n": 0}
_lock = threading.Lock()


class FmpError(RuntimeError):
    """No key, a non-US symbol, the daily budget is spent, or FMP refused the request."""


def api_key() -> Optional[str]:
    k = os.getenv("FMP_API_KEY")
    if not k:
        try:
            from dotenv import dotenv_values
            k = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get("FMP_API_KEY")
        except Exception:
            k = None
    return k or None


def available() -> bool:
    return api_key() is not None


def _us(symbol: str) -> str:
    s = symbol.strip().upper()
    if "." in s or any(c in s for c in "=^"):
        raise FmpError("FMP's free plan covers US listings only.")
    return s


def _spend() -> None:
    import json
    with _lock:
        today = date.today()
        if _used["day"] != today:                        # first use today in this process: pick up the saved count
            try:
                saved = json.loads(_USAGE.read_text())
                _used.update(day=today, n=int(saved["n"]) if saved.get("day") == today.isoformat() else 0)
            except Exception:
                _used.update(day=today, n=0)
        if _used["n"] >= DAILY_BUDGET:
            raise FmpError("Today's FMP allowance is used up — cached data only until tomorrow.")
        _used["n"] += 1
        try:
            _DIR.mkdir(parents=True, exist_ok=True)
            _USAGE.write_text(json.dumps({"day": today.isoformat(), "n": _used["n"]}))
        except Exception:
            pass


def _get(endpoint: str, params: Dict[str, Any], ttl: float) -> Any:
    from api.marketdata.core import _cached
    key = api_key()
    if not key:
        raise FmpError("FMP_API_KEY is not set.")

    import hashlib
    import json
    import time as _t
    ident = endpoint + ":" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    disk = _DIR / "cache" / (hashlib.sha1(ident.encode()).hexdigest() + ".json")

    def fetch():
        try:                                             # a disk copy within its TTL costs no request after a restart
            if _t.time() - disk.stat().st_mtime < ttl:
                return json.loads(disk.read_text())
        except Exception:
            pass
        _spend()
        r = requests.get(BASE + endpoint, params={**params, "apikey": key}, timeout=25)
        if r.status_code == 402:
            raise FmpError("Not in FMP's free plan.")
        if r.status_code == 429:
            raise FmpError("FMP's daily limit was reached.")
        if r.status_code != 200:
            raise FmpError(f"FMP HTTP {r.status_code}")
        data = r.json()
        try:
            disk.parent.mkdir(parents=True, exist_ok=True)
            disk.write_text(json.dumps(data))
        except Exception:
            pass
        return data
    return _cached("fmp:" + ident, ttl, fetch)


def _num(x) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def analyst_view(symbol: str) -> Dict[str, Any]:
    """Grade consensus, the price-target consensus and its trend (last month / quarter / year), and recent grade changes."""
    s = _us(symbol)
    cons = (_get("grades-consensus", {"symbol": s}, 6 * 3600) or [{}])[0]
    tgt = (_get("price-target-consensus", {"symbol": s}, 6 * 3600) or [{}])[0]
    trend = (_get("price-target-summary", {"symbol": s}, 6 * 3600) or [{}])[0]
    grades = _get("grades", {"symbol": s, "limit": 40}, 6 * 3600) or []
    return {"symbol": s,
            "consensus": {k: _num(cons.get(k)) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")} | {"label": cons.get("consensus")},
            "target": {"consensus": _num(tgt.get("targetConsensus")), "median": _num(tgt.get("targetMedian")),
                       "high": _num(tgt.get("targetHigh")), "low": _num(tgt.get("targetLow"))},
            "target_trend": [{"window": w, "count": _num(trend.get(f"{k}Count")), "average": _num(trend.get(f"{k}AvgPriceTarget"))}
                             for w, k in (("last month", "lastMonth"), ("last quarter", "lastQuarter"), ("last year", "lastYear"))],
            "grade_changes": [{"date": g.get("date"), "firm": g.get("gradingCompany"), "from": g.get("previousGrade"),
                               "to": g.get("newGrade"), "action": g.get("action")} for g in grades[:40]],
            "source": "Financial Modeling Prep"}


def estimates(symbol: str, years: int = 5) -> List[Dict[str, Any]]:
    """Analyst consensus by fiscal year (revenue, EBITDA, EPS: low / average / high, analyst counts), oldest first."""
    s = _us(symbol)
    rows = _get("analyst-estimates", {"symbol": s, "period": "annual", "limit": 10}, 12 * 3600) or []
    out = [{"fiscal_year_end": r.get("date"), "revenue": _num(r.get("revenueAvg")), "revenue_low": _num(r.get("revenueLow")),
            "revenue_high": _num(r.get("revenueHigh")), "ebitda": _num(r.get("ebitdaAvg")), "eps": _num(r.get("epsAvg")),
            "eps_low": _num(r.get("epsLow")), "eps_high": _num(r.get("epsHigh")),
            "analysts_revenue": _num(r.get("numAnalystsRevenue")), "analysts_eps": _num(r.get("numAnalystsEps"))} for r in rows]
    out.sort(key=lambda r: r["fiscal_year_end"] or "")
    return [r for r in out if (r["fiscal_year_end"] or "") >= str(date.today().year)][:years]


def earnings_calendar(start: date, days: int) -> List[Dict[str, Any]]:
    """US earnings dates with EPS and revenue estimates / actuals (FMP's calendar spans up to ~3 months a request)."""
    end = start + timedelta(days=max(1, days))
    rows = _get("earnings-calendar", {"from": start.isoformat(), "to": end.isoformat()}, 3600) or []
    return [{"symbol": r.get("symbol"), "date": r.get("date"), "eps_estimate": _num(r.get("epsEstimated")),
             "eps_reported": _num(r.get("epsActual")), "revenue_estimate": _num(r.get("revenueEstimated")),
             "revenue_reported": _num(r.get("revenueActual"))} for r in rows]


def budget() -> Dict[str, Any]:
    """Requests used today (in this process, or saved by an earlier one) against the daily budget."""
    import json
    n = _used["n"] if _used["day"] == date.today() else 0
    if not n:
        try:
            saved = json.loads(_USAGE.read_text())
            n = int(saved["n"]) if saved.get("day") == date.today().isoformat() else 0
        except Exception:
            pass
    return {"used_today": n, "daily_budget": DAILY_BUDGET}
