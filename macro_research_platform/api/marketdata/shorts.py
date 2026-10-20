"""
SI — short selling, free sources:
  · Official short interest (exchange-reported twice a month): shares short, % of float,
    days to cover, change vs the prior report — Yahoo Finance.
  · Daily short-sale volume (FINRA Reg SHO consolidated file, every US-listed stock) — the
    share of each day's volume that was a short sale. Note: most of it is market makers and
    hedgers providing liquidity, so 40–50% is normal; what matters is the trend and outliers.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from api.marketdata.core import NotFound, _cached, _f, _info

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "finra"
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"


def _day(d: date) -> Optional[str]:
    """One day's consolidated short-volume file (cached on disk; None on holidays)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{d:%Y%m%d}.txt"
    miss = CACHE / f"{d:%Y%m%d}.missing"
    if path.exists():
        return path.read_text()
    if miss.exists() and (datetime.now().timestamp() - miss.stat().st_mtime) < 86400:
        return None
    try:
        import requests
        r = requests.get(URL.format(d=f"{d:%Y%m%d}"), timeout=20)
        if r.status_code != 200 or not r.text.startswith("Date|"):
            if d < date.today() - timedelta(days=1):
                miss.touch()
            return None
        if d < date.today():                     # today's file can still be replaced
            path.write_text(r.text)
        return r.text
    except Exception as e:
        logger.debug("[finra] %s: %s", d, e)
        return None


def _parse(text: str, sym: str) -> Optional[Dict[str, float]]:
    i = text.find(f"|{sym}|")
    if i < 0:
        return None
    line = text[text.rfind("\n", 0, i) + 1: text.find("\n", i)]
    p = line.split("|")
    try:
        return {"short": float(p[2]), "exempt": float(p[3]), "total": float(p[4])}
    except (IndexError, ValueError):
        return None


def short_selling(symbol: str, days: int = 60) -> Dict[str, Any]:
    s = symbol.strip().upper()
    if "." in s or "=" in s or "^" in s:
        raise NotFound("Short-sale data is published for US-listed stocks and ETFs (FINRA Reg SHO).")
    days = max(10, min(int(days), 120))

    def fetch():
        i = _info(s)
        # business days back from yesterday (US/Eastern) until we have `days` files
        today = datetime.now(timezone.utc).date()
        cands, d = [], today
        while len(cands) < int(days * 1.25) + 5:
            if d.weekday() < 5:
                cands.append(d)
            d -= timedelta(days=1)
        with cf.ThreadPoolExecutor(6) as ex:
            texts = dict(zip(cands, ex.map(_day, cands)))
        series: List[Dict[str, Any]] = []
        for dd in sorted(texts):
            t = texts[dd]
            if not t:
                continue
            row = _parse(t, s.replace("-", "/"))          # FINRA writes share classes as BRK/B
            if row and row["total"] > 0:
                series.append({"date": str(dd), "short_volume": row["short"], "total_volume": row["total"],
                               "ratio": row["short"] / row["total"]})
        series = series[-days:]
        if not series:
            raise NotFound(f"No FINRA short-sale volume for {s}.")
        ratios = np.array([x["ratio"] for x in series])
        last20 = ratios[-20:]
        si_date = i.get("dateShortInterest")
        prior = _f(i.get("sharesShortPriorMonth"))
        shares_short = _f(i.get("sharesShort"))
        official = {
            "shares_short": shares_short, "prior": prior,
            "change": (shares_short / prior - 1) if shares_short and prior else None,
            "percent_of_float": _f(i.get("shortPercentOfFloat")),
            "percent_of_shares": _f(i.get("sharesPercentSharesOut")),
            "days_to_cover": _f(i.get("shortRatio")),
            "as_of": datetime.fromtimestamp(si_date, tz=timezone.utc).strftime("%Y-%m-%d") if isinstance(si_date, (int, float)) else None,
        }
        return {"symbol": s, "official": official, "daily": series,
                "ratio_latest": float(ratios[-1]), "ratio_20d": float(last20.mean()),
                "ratio_prev_20d": float(ratios[-40:-20].mean()) if len(ratios) >= 40 else None,
                # today vs the 20 days before it (today excluded from its own baseline)
                "ratio_zscore": (float((ratios[-1] - ratios[-21:-1].mean()) / ratios[-21:-1].std())
                                 if len(ratios) > 6 and ratios[-21:-1].std() > 0 else None),
                "note": "Daily short volume is the share of trading that was a short sale — mostly market makers and hedgers, "
                        "so 40–50% is typical. Watch the trend and unusual days. Short interest (positions held) is reported "
                        "twice a month.",
                "source": "FINRA Reg SHO daily short-sale volume (consolidated); short interest via Yahoo Finance"}
    return _cached(f"si:{s}:{days}", 3600, fetch)
