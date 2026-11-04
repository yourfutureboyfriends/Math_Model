"""
Next central-bank decisions with the consensus available free:
  * Fed — the next FOMC date (Federal Reserve calendar) priced by fed funds futures (WIRP), plus the survey consensus
    once the weekly calendar feed lists it;
  * ECB, BoE, BoJ, BoC, RBA, RBNZ, SNB — the weekly calendar feed's consensus forecast once the meeting is in the
    current week (the feed publishes one week at a time). Otherwise the meeting is reported as not yet listed.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BANKS = [("Federal Reserve", "USD", r"^Federal Funds Rate$"), ("ECB", "EUR", r"^Main Refinancing Rate$"),
         ("Bank of England", "GBP", r"^Official Bank Rate$"), ("Bank of Japan", "JPY", r"^BOJ Policy Rate$"),
         ("Bank of Canada", "CAD", r"^Overnight Rate$"), ("Reserve Bank of Australia", "AUD", r"^Cash Rate$"),
         ("Reserve Bank of New Zealand", "NZD", r"^Official Cash Rate$"), ("Swiss National Bank", "CHF", r"^SNB Policy Rate$")]


# bank → (Global Macro economy code for the BIS policy rate, government curve code)
_CURVE = {"ECB": ("EA", "EA"), "Bank of England": ("GB", "GB"), "Bank of Japan": ("JP", "JP"),
          "Bank of Canada": ("CA", "CA"), "Reserve Bank of Australia": ("AU", "AU")}


def curve_implied(policy: Optional[float], points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Short government yield (shortest tenor ≤ 2y, preferring ≤ 1y) minus the policy rate: a rough market read of
    the policy path (it includes a term premium and credit spread, so ±25bp is treated as on hold)."""
    if policy is None or not points:
        return None
    short = sorted((p for p in points if 0.2 <= p["tenor"] <= 2.01), key=lambda p: (p["tenor"] > 1.01, p["tenor"]))
    if not short:
        return None
    one = next((x for x in short if 0.99 <= x["tenor"] <= 1.01), None)
    p = one or short[0]
    bp = round((p["yield"] - policy) * 100)
    return {"tenor_years": p["tenor"], "yield": p["yield"], "policy_rate": policy, "spread_bp": bp,
            "read": "cuts priced" if bp <= -25 else "hikes priced" if bp >= 25 else "on hold",
            "source": "government curve vs BIS policy rate"}


def next_decisions(policy_rates: Optional[Dict[str, float]] = None,
                   curves: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The next policy decision of each major central bank: date (from the economic-calendar feed), current policy rate
    and the market-implied move where a curve is available.

    Args:
        policy_rates: current policy rates by bank, when already loaded.
        curves: market-implied paths by bank (e.g. from futures), when available.

    Returns:
        {as_of, banks: [...]} — a bank without a scheduled date is listed with a reason.
    """
    today = date.today().isoformat()
    feed: List[Dict[str, Any]] = []
    try:
        from api.marketdata import econ
        feed = econ.calendar(0, None, "Low").get("events") or []
    except Exception as e:
        logger.info("[cb] calendar feed unavailable: %s", e)
    out = []
    for bank, ccy, pat in BANKS:
        hit = next((f for f in sorted(feed, key=lambda f: str(f.get("date")))
                    if f.get("country") == ccy and re.match(pat, f.get("title") or "") and str(f.get("date"))[:10] >= today), None)
        row = {"bank": bank, "currency": ccy, "date": str(hit["date"])[:10] if hit else None,
               "consensus": hit.get("forecast") if hit else None, "previous": hit.get("previous") if hit else None,
               "consensus_source": "weekly calendar feed (survey forecast)" if hit and hit.get("forecast") else None}
        if bank == "Federal Reserve":
            try:
                from api.release_calendar import FOMC_DECISIONS
                row["date"] = row["date"] or next((d for d in FOMC_DECISIONS if d >= today), None)
                from api.marketdata import extras
                w = extras.wirp()
                m0 = (w.get("meetings") or [None])[0]
                if m0:
                    probs = m0.get("probabilities") or {}
                    top = max(probs, key=probs.get) if probs else None
                    row["market_implied"] = {"meeting": m0["meeting"], "probabilities": probs, "most_likely": top,
                                             "expected_change_bp": round(m0.get("change_bp") or 0, 1),
                                             "source": "fed funds futures (WIRP)"}
            except Exception as e:
                logger.info("[cb] fed pricing unavailable: %s", e)
        if bank in _CURVE and policy_rates is not None and curves is not None:
            econ, cc = _CURVE[bank]
            ci = curve_implied(policy_rates.get(econ), (curves.get(cc) or {}).get("points") or [])
            if ci:
                row["market_implied"] = {**ci, "curve_date": (curves.get(cc) or {}).get("date")}
        if not row["date"]:
            row["note"] = "next meeting not yet in the free weekly feed (it lists one week at a time)"
        out.append(row)
    return {"banks": out, "as_of": today,
            "method": "Consensus = the survey forecast in the free weekly calendar feed once the meeting week starts. "
                      "Market pricing: fed funds futures (WIRP) for the Fed; for others, the 1-year (or shortest) "
                      "government yield minus the policy rate — a rough read (term premium included; ±25bp = on hold)."}
