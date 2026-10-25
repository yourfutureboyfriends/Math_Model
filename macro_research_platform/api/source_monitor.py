"""
Free-data source monitor. Every source the platform parses (Fed, Treasury, CFTC, Cboe, AAII, Shiller, FRED, Yahoo …)
is checked on a schedule: does it still parse, and how old is its latest observation against what is normal for it?
A format change upstream (the Fed's EBP file switching to ISO dates, Oct 2026) used to turn a panel "unavailable"
with only a log line; now the source shows FAILING in System Health and, when it flips, an alert is sent through
the alert channels (api/notify.py, if configured).

Status per source: ok · stale (parses, but the latest observation is older than the source's normal lag) ·
degraded (served from the last good copy, or part of the source failed) · failing (does not parse / unreachable).
State persists in data/processed/source_monitor.json (status, latest observation, age, error, since when).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
STATE = Path(__file__).resolve().parents[1] / "data" / "processed" / "source_monitor.json"     # gitignored
INTERVAL_S = 6 * 3600
_lock = threading.Lock()


def _d(x: Any) -> Optional[str]:
    """A date string (YYYY-MM-DD) from a date / datetime / 'YYYY-MM' / ISO string."""
    if x is None:
        return None
    s = str(x)
    if len(s) == 7 and s[4] == "-":                      # a month: its last day is when it is "as of"
        import calendar
        y, m = int(s[:4]), int(s[5:7])
        return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    return s[:10]


def _fred_latest() -> Dict[str, Any]:
    from api.handlers.macro_inputs import _fetch_fred_history_sync
    s = _fetch_fred_history_sync("DGS10", 30)
    return {"latest": s.dates[-1] if s.dates else None}


def _yahoo_latest() -> Dict[str, Any]:
    from api.quant import data as qdata
    pan, missing = qdata.panel(["SPY"], start=(date.today().replace(day=1)).isoformat())
    idx = pan["close"].index if pan else []
    return {"latest": str(idx[-1].date()) if len(idx) else None, "missing": missing}


def _sec_latest() -> Dict[str, Any]:
    from api.providers import sec_edgar
    m = sec_edgar.ticker_map() if hasattr(sec_edgar, "ticker_map") else None
    return {"latest": date.today().isoformat() if m else None, "tickers": len(m or {})}


def _sources() -> List[Dict[str, Any]]:
    """name, what it feeds, how to fetch it, how to read its latest observation, its normal lag (days)."""
    from api.marketdata import freedata, fixed_income, extras
    from api import research_indicators as ri, cot, econ_calendar
    return [
        {"name": "Federal Reserve — excess bond premium", "feeds": "credit stress (Research → credit)", "max_age": 75,
         "fetch": ri._fetch_ebp, "latest": lambda v: _d(v[-1][0]) if v else None},
        {"name": "Federal Reserve — GSW zero-coupon curve (NTFS)", "feeds": "near-term forward spread, recession probit",
         "max_age": 10, "fetch": ri.ntfs_block, "latest": lambda v: v.get("as_of") if v.get("available") else None},
        {"name": "Caldara–Iacoviello geopolitical risk (daily)", "feeds": "Risk Indicators → geopolitical risk",
         "max_age": 8, "fetch": freedata.gpr_daily, "latest": lambda v: (v.get("dates") or [None])[-1]},
        {"name": "Shiller CAPE (ie_data.xls)", "feeds": "Valuation → CAPE", "max_age": 160,
         "fetch": freedata.shiller_cape, "latest": lambda v: _d(v.get("latest_month"))},
        {"name": "AAII sentiment survey", "feeds": "Sentiment, Daily Brief positioning", "max_age": 10,
         "fetch": freedata.aaii_sentiment, "latest": lambda v: (v.get("latest") or {}).get("date")},
        {"name": "NY Fed Staff Nowcast", "feeds": "GDP nowcast band", "max_age": 10,
         "fetch": freedata.nyfed_nowcast, "latest": lambda v: (v.get("latest") or {}).get("date")},
        {"name": "Cboe daily put/call ratios", "feeds": "options context, Daily Brief", "max_age": 5,
         "fetch": lambda: freedata.cboe_put_call(10), "latest": lambda v: (v.get("latest") or {}).get("date")},
        {"name": "CFTC Commitments of Traders", "feeds": "COT positioning", "max_age": 12,
         "fetch": cot.fetch_cot, "latest": lambda v: v.get("report_date")},
        {"name": "TreasuryDirect FedInvest prices", "feeds": "Treasury board, YAS", "max_age": 6,
         "fetch": fixed_income.treasuries, "latest": lambda v: v.get("price_date")},
        {"name": "TreasuryDirect auctions", "feeds": "AUCT", "max_age": 21,
         "fetch": lambda: extras.auctions("Note", 10),
         "latest": lambda v: max([str(a.get("auction_date") or a.get("date") or "")[:10]
                                  for a in (v.get("auctions") or v.get("rows") or [])] or [None])},
        {"name": "Economic calendar (consensus feed + ALFRED)", "feeds": "ECO, Daily Brief releases", "max_age": None,
         "fetch": econ_calendar.get_calendar, "latest": lambda v: _d(v.get("as_of")),
         "partial": lambda v: v.get("sources_failed") or None},
        {"name": "Nasdaq IPO calendar", "feeds": "IPO", "max_age": None,
         "fetch": freedata.nasdaq_ipos, "latest": lambda v: date.today().isoformat() if v.get("ipos") is not None else None},
        {"name": "FRED (St. Louis Fed)", "feeds": "most macro series", "max_age": 6,
         "fetch": _fred_latest, "latest": lambda v: v.get("latest")},
        {"name": "Yahoo Finance prices", "feeds": "prices, backtests", "max_age": 5,
         "fetch": _yahoo_latest, "latest": lambda v: v.get("latest")},
    ]


def _state() -> Dict[str, Any]:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(s: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, default=str))


def check_one(src: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    out: Dict[str, Any] = {"name": src["name"], "feeds": src["feeds"], "max_age_days": src["max_age"],
                           "checked_at": datetime.now().isoformat(timespec="seconds")}
    try:
        v = src["fetch"]()
        latest = src["latest"](v)
        out["latest"] = latest
        age = (date.today() - date.fromisoformat(latest)).days if latest else None
        out["age_days"] = age
        partial = src.get("partial", lambda _v: None)(v) if isinstance(v, dict) else None
        stale_copy = isinstance(v, dict) and v.get("stale")
        if latest is None:
            out.update(status="failing", error="parsed, but no observation found")
        elif stale_copy:
            out.update(status="degraded", error=f"upstream refresh failed — serving a copy {v.get('stale_age_s', 0) // 3600} h old")
        elif partial:
            out.update(status="degraded", error=f"part of the source failed: {partial}"[:200])
        elif src["max_age"] is not None and age is not None and age > src["max_age"]:
            out.update(status="stale", error=f"latest observation {age} days old (normal lag up to {src['max_age']})")
        else:
            out["status"] = "ok"
    except Exception as e:                                                     # noqa: BLE001 — that is the finding
        out.update(status="failing", error=f"{type(e).__name__}: {str(e)[:200]}")
    out["seconds"] = round(time.time() - t0, 1)
    return out


def run_checks(notify_changes: bool = True) -> Dict[str, Any]:
    """Check every source; record status changes (with when they started) and alert on new failures."""
    with _lock:
        prev = _state().get("sources", {})
        results, changed = {}, []
        for src in _sources():
            r = check_one(src)
            old = prev.get(r["name"], {})
            r["since"] = old.get("since") if old.get("status") == r["status"] else r["checked_at"]
            if old and old.get("status") != r["status"]:
                changed.append((r["name"], old.get("status"), r["status"], r.get("error")))
            results[r["name"]] = r
        s = {"sources": results, "checked_at": datetime.now().isoformat(timespec="seconds"),
             "summary": {k: sum(1 for r in results.values() if r["status"] == k) for k in ("ok", "stale", "degraded", "failing")}}
        _save(s)
    bad = [c for c in changed if c[2] in ("failing", "stale")]
    for name, was, now, err in changed:
        logger.warning("[sources] %s: %s → %s %s", name, was, now, err or "")
    if bad and notify_changes:
        try:
            from api import notify
            if any(notify.channels().values()):
                notify.deliver("Source monitor", "Data source problem: " + "; ".join(f"{n} {w}→{s} ({e})" for n, w, s, e in bad)[:900])
        except Exception as e:                                                 # noqa: BLE001
            logger.info("[sources] alert not sent: %s", e)
    return s


def status() -> Dict[str, Any]:
    s = _state()
    rows = sorted((s.get("sources") or {}).values(), key=lambda r: ("failing", "degraded", "stale", "ok").index(r["status"]))
    return {"checked_at": s.get("checked_at"), "summary": s.get("summary"), "sources": rows,
            "interval_hours": INTERVAL_S / 3600}


def loop() -> None:
    """Background thread: first check 5 minutes after start, then every 6 hours."""
    time.sleep(300)
    while True:
        try:
            run_checks()
        except Exception as e:                                                 # noqa: BLE001
            logger.warning("[sources] check run failed: %s", e)
        time.sleep(INTERVAL_S)
