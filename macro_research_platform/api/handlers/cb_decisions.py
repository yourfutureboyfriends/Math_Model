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
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

BANKS = [("Federal Reserve", "USD", r"^Federal Funds Rate$"), ("ECB", "EUR", r"^Main Refinancing Rate$"),
         ("Bank of England", "GBP", r"^Official Bank Rate$"), ("Bank of Japan", "JPY", r"^BOJ Policy Rate$"),
         ("Bank of Canada", "CAD", r"^Overnight Rate$"), ("Reserve Bank of Australia", "AUD", r"^Cash Rate$"),
         ("Reserve Bank of New Zealand", "NZD", r"^Official Cash Rate$"), ("Swiss National Bank", "CHF", r"^SNB Policy Rate$")]


def next_decisions() -> Dict[str, Any]:
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
        if not row["date"]:
            row["note"] = "next meeting not yet in the free weekly feed (it lists one week at a time)"
        out.append(row)
    return {"banks": out, "as_of": today,
            "method": "Consensus = the survey forecast in the free weekly calendar feed once the meeting week starts; "
                      "the Fed also has fed-funds-futures pricing (WIRP)."}
