"""
Benzinga APIs — analyst rating actions (firm, named analyst, rating and price-target changes), company guidance
changes, earnings / dividend / economic calendars and news headlines. Key: BENZINGA_API_KEY in .env (never logged).
Every call is cached; without a key `available()` is False and callers keep their other sources.
"""
from __future__ import annotations

import ast
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)
BASE = "https://api.benzinga.com/api"


class BenzingaError(RuntimeError):
    """The request failed or the key / plan does not allow it."""


def api_key() -> Optional[str]:
    k = os.getenv("BENZINGA_API_KEY")
    if not k:
        try:
            from dotenv import dotenv_values
            k = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get("BENZINGA_API_KEY")
        except Exception:
            k = None
    return k or None


def available() -> bool:
    return api_key() is not None


def _get(path: str, params: Dict[str, Any], ttl: float) -> Any:
    from api.marketdata.core import _cached
    key = api_key()
    if not key:
        raise BenzingaError("BENZINGA_API_KEY is not set.")

    def fetch():
        r = requests.get(f"{BASE}{path}", params={**params, "token": key}, headers={"accept": "application/json"}, timeout=25)
        if r.status_code in (401, 403):
            raise BenzingaError(f"Benzinga refused the request ({r.status_code}) — not in this key's plan.")
        if r.status_code != 200:
            raise BenzingaError(f"Benzinga HTTP {r.status_code}")
        return r.json() if r.text.strip() else {}
    return _cached("bz:" + path + ":" + "&".join(f"{k}={v}" for k, v in sorted(params.items())), ttl, fetch)


def _num(x) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def ratings(ticker: Optional[str] = None, days: int = 30, limit: int = 100) -> List[Dict[str, Any]]:
    """Analyst rating actions, newest first: firm, analyst, action (upgrade / downgrade / initiate / maintain),
    rating, price-target change. Market-wide when no ticker."""
    p: Dict[str, Any] = {"pagesize": min(limit, 1000), "parameters[date_from]": (date.today() - timedelta(days=days)).isoformat()}
    if ticker:
        p["parameters[tickers]"] = ticker.upper()
    j = _get("/v2.1/calendar/ratings", p, 900)
    out = []
    for r in (j or {}).get("ratings") or []:
        pt, pt0 = _num(r.get("adjusted_pt_current") or r.get("pt_current")), _num(r.get("adjusted_pt_prior") or r.get("pt_prior"))
        out.append({"date": r.get("date"), "time": r.get("time"), "ticker": r.get("ticker"), "name": r.get("name"),
                    "firm": r.get("analyst"), "analyst": r.get("analyst_name"), "action": r.get("action_company"),
                    "pt_action": r.get("action_pt"), "rating": r.get("rating_current"), "rating_prior": r.get("rating_prior"),
                    "pt": pt, "pt_prior": pt0, "pt_change": (pt / pt0 - 1) if pt and pt0 else None,
                    "currency": r.get("currency"), "importance": int(r.get("importance") or 0), "url": r.get("url_calendar")})
    out.sort(key=lambda x: (x["date"] or "", x["time"] or ""), reverse=True)
    return out


def guidance(days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
    """Company EPS / revenue guidance changes (raised, lowered, initiated)."""
    j = _get("/v2.1/calendar/guidance", {"pagesize": limit, "parameters[date_from]": (date.today() - timedelta(days=days)).isoformat()}, 1800)
    out = []
    for g in (j or {}).get("guidance") or []:
        lo, hi = _num(g.get("eps_guidance_min")), _num(g.get("eps_guidance_max"))
        plo, phi = _num(g.get("eps_guidance_prior_min")), _num(g.get("eps_guidance_prior_max"))
        mid = (lo + hi) / 2 if lo and hi else lo or hi
        pmid = (plo + phi) / 2 if plo and phi else plo or phi
        out.append({"date": g.get("date"), "ticker": g.get("ticker"), "name": g.get("name"), "period": f"{g.get('period', '')} {g.get('period_year', '')}".strip(),
                    "eps_low": lo, "eps_high": hi, "eps_prior_low": plo, "eps_prior_high": phi, "eps_consensus": _num(g.get("eps_guidance_est")),
                    "revenue_low": _num(g.get("revenue_guidance_min")), "revenue_high": _num(g.get("revenue_guidance_max")),
                    "direction": (None if not mid else "initiated" if not pmid else "raised" if mid > pmid * 1.001
                                  else "lowered" if mid < pmid * 0.999 else "maintained"),
                    "notes": (g.get("notes") or "")[:240], "importance": int(g.get("importance") or 0)})
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


def news(limit: int = 40, tickers: Optional[str] = None) -> List[Dict[str, Any]]:
    """Latest headlines (headline-level access) with tickers and channels."""
    p: Dict[str, Any] = {"pageSize": min(limit, 100), "displayOutput": "headline"}
    if tickers:
        p["tickers"] = tickers
    j = _get("/v2/news", p, 120)
    out = []
    for n in j if isinstance(j, list) else []:
        def lst(v):
            if isinstance(v, list):
                return v
            try:
                return ast.literal_eval(v) if v else []
            except Exception:
                return []
        try:
            ts = datetime.strptime(n.get("created", ""), "%a, %d %b %Y %H:%M:%S %z").isoformat()
        except Exception:
            ts = n.get("created")
        out.append({"title": n.get("title"), "url": n.get("url"), "published": ts, "source": "Benzinga",
                    "tickers": [s.get("name") for s in lst(n.get("stocks")) if isinstance(s, dict)],
                    "channels": [c.get("name") for c in lst(n.get("channels")) if isinstance(c, dict)]})
    return out
