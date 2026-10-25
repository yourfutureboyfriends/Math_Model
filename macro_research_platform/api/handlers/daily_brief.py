"""
Data-driven parts of the Daily Brief: overnight moves (with their size in standard deviations), what changed since
the previous brief, today's US releases with consensus, earnings of holdings and large caps, positioning extremes
(CFTC, AAII, put/call), and priorities ranked from those facts — each with its own implication instead of a generic
"Action required".
"""
from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OVERNIGHT = [("S&P 500 futures", "ES=F", "pct"), ("Nasdaq futures", "NQ=F", "pct"), ("Nikkei 225", "^N225", "pct"),
             ("Hang Seng", "^HSI", "pct"), ("Euro Stoxx 50", "^STOXX50E", "pct"), ("DAX", "^GDAXI", "pct"),
             ("FTSE 100", "^FTSE", "pct"), ("US 10Y yield", "^TNX", "bp"), ("EUR/USD", "EURUSD=X", "pct"),
             ("USD/JPY", "USDJPY=X", "pct"), ("Gold", "GC=F", "pct"), ("WTI crude", "CL=F", "pct"),
             ("Bitcoin", "BTC-USD", "pct")]


def _move(name: str, tick: str, kind: str) -> Optional[Dict[str, Any]]:
    from api.market_bars import bars
    try:
        b = bars(tick, "1d", "6mo")["bars"]
    except Exception:
        return None
    if len(b) < 25:
        return None
    c = [x["c"] for x in b]
    if kind == "bp":                                  # ^TNX is the yield in percent
        ch = (c[-1] - c[-2]) * 100
        hist = [(c[i] - c[i - 1]) * 100 for i in range(len(c) - 60, len(c) - 1)]
    else:
        ch = (c[-1] / c[-2] - 1) * 100
        hist = [(c[i] / c[i - 1] - 1) * 100 for i in range(len(c) - 60, len(c) - 1)]
    mu = sum(hist) / len(hist)
    sd = math.sqrt(sum((h - mu) ** 2 for h in hist) / (len(hist) - 1)) if len(hist) > 2 else None
    return {"name": name, "ticker": tick, "unit": kind, "last": round(c[-1], 4), "change": round(ch, 2),
            "sigma": round(ch / sd, 1) if sd else None, "as_of": b[-1]["t"]}


def overnight_moves() -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(lambda x: _move(*x), OVERNIGHT))
    return [r for r in rows if r]


# ── what changed since the previous brief ─────────────────────────────────────
def _conn():
    # the brief's day-over-day market snapshot is shared by every fund: always the main database
    import sqlite3
    from api.core.app_db import app_db_path
    conn = sqlite3.connect(app_db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS brief_snapshots (date TEXT PRIMARY KEY, recorded_at TEXT, state TEXT)")
    return conn


def snapshot_and_diff(state: Dict[str, Any]) -> Dict[str, Any]:
    """Store today's key readings (latest of the day wins) and diff them against the previous day's."""
    today = date.today().isoformat()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO brief_snapshots (date, recorded_at, state) VALUES (?,?,?)",
                  (today, datetime.now().isoformat(timespec="seconds"), json.dumps(state, default=str)))
        c.commit()
        r = c.execute("SELECT date, state FROM brief_snapshots WHERE date < ? ORDER BY date DESC LIMIT 1", (today,)).fetchone()
    if not r:
        return {"since": None, "changes": [], "note": "First brief recorded — changes appear from the next day."}
    prev = json.loads(r["state"])
    changes = []
    for k, label, fmt, thresh in (("regime", "Regime", None, None), ("composite", "Composite signal", "{:+.2f}", 0.02),
                                  ("growth", "Growth signal", "{:+.2f}", 0.03), ("inflation", "Inflation signal", "{:+.2f}", 0.03),
                                  ("liquidity", "Liquidity signal", "{:+.2f}", 0.03), ("risk", "Risk appetite", "{:+.2f}", 0.03),
                                  ("recession", "Recession probability", "{:+.1%}", 0.01), ("vix", "VIX", "{:+.1f}", 1.0),
                                  ("ten_year", "10Y yield", "{:+.2f}pp", 0.05), ("conviction", "Conviction", None, None)):
        a, b = prev.get(k), state.get(k)
        if a is None or b is None:
            continue
        if fmt is None:
            if a != b:
                changes.append({"item": label, "from": a, "to": b, "text": f"{label}: {a} → {b}"})
        elif abs(b - a) >= thresh:
            changes.append({"item": label, "from": a, "to": b, "delta": b - a,
                            "text": f"{label} {fmt.format(b - a)} (now {b:.2f})" if "%" not in fmt
                            else f"{label} {fmt.format(b - a)} (now {b:.1%})"})
    return {"since": r["date"], "changes": changes}


# ── calendar, earnings, positioning ──────────────────────────────────────────
def todays_releases() -> List[Dict[str, Any]]:
    from api.econ_calendar import get_calendar
    from zoneinfo import ZoneInfo
    cal = get_calendar()
    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date().isoformat()
    out = []
    for r in cal.get("upcoming") or []:
        if datetime.fromisoformat(r["release_datetime"]).astimezone(et).date().isoformat() == today:
            out.append({"time_et": r.get("time_et"), "event": r["event_name"], "importance": r["importance"],
                        "forecast": r.get("forecast"), "forecast_label": r.get("forecast_label"),
                        "previous": r.get("previous"), "watch": r.get("affected_assets")})
    return out


def earnings_this_week(holdings: List[str]) -> Dict[str, Any]:
    from api.marketdata.monitors import earnings_calendar
    try:
        cal = earnings_calendar(None, 7, 50.0, 0, 250)
    except Exception as e:
        return {"available": False, "reason": str(e)[:120], "holdings": [], "large_caps": []}
    rows = cal.get("rows") or []
    held = set(h.upper() for h in holdings)
    mine = [r for r in rows if str(r["symbol"]).upper() in held]
    big = sorted(rows, key=lambda r: -(r.get("market_cap") or 0))[:8]
    trim = lambda r: {k: r.get(k) for k in ("symbol", "company", "datetime", "timing", "eps_estimate", "market_cap")}
    return {"available": True, "holdings": [trim(r) for r in mine], "large_caps": [trim(r) for r in big]}


def positioning() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from api.cot import fetch_cot
        cot = fetch_cot()
        out["cot_extremes"] = [{"market": c["name"], "cot_index": c["cot_index"], "signal": c["contrarian_signal"],
                                "report_date": c["report_date"]} for c in cot.get("contracts", []) if c.get("extreme")]
    except Exception as e:
        out["cot_extremes"] = []
        logger.info("[brief] COT unavailable: %s", e)
    from api.marketdata import freedata
    for k, fn in (("aaii", freedata.aaii_sentiment), ("put_call", freedata.cboe_put_call)):
        try:
            v = fn()
            out[k] = {kk: vv for kk, vv in v.items() if kk not in ("history",)}
        except Exception as e:
            out[k] = None
            logger.info("[brief] %s unavailable: %s", k, e)
    return out


def priorities(moves, diff, releases, earnings, pos) -> List[Dict[str, Any]]:
    """Ranked, each with a specific implication. Score = how unusual or consequential the fact is."""
    items = []
    for r in releases:
        if r["importance"] in ("HIGH", "MEDIUM"):
            fc = f"consensus {r['forecast']} ({r['forecast_label']})" if r.get("forecast") else "no consensus in the free feed"
            items.append((3 if r["importance"] == "HIGH" else 2,
                          {"type": "release", "title": f"{r['event']} at {r['time_et']} ET — {fc}",
                           "implication": f"Previous {r.get('previous') or '—'}; most exposed: {', '.join(r.get('watch') or []) or '—'}",
                           "severity": "HIGH" if r["importance"] == "HIGH" else "MEDIUM"}))
    for m in moves:
        if m.get("sigma") is not None and abs(m["sigma"]) >= 1.5:
            unit = "bp" if m["unit"] == "bp" else "%"
            items.append((abs(m["sigma"]),
                          {"type": "move", "title": f"{m['name']} {m['change']:+.2f}{unit} ({m['sigma']:+.1f}σ, {m['as_of']})",
                           "implication": "Largest move vs its own last 60 sessions" if abs(m["sigma"]) >= 2.5
                           else "Unusual move vs its last 60 sessions",
                           "severity": "HIGH" if abs(m["sigma"]) >= 2.5 else "MEDIUM"}))
    for c in diff.get("changes") or []:
        big = c["item"] in ("Regime", "Conviction") or abs(c.get("delta") or 0) >= 0.05
        items.append((2.5 if big else 1.2, {"type": "change", "title": f"Since {diff['since']}: {c['text']}",
                                            "implication": "Model reading changed — review positioning against it" if big
                                            else "Drift in a model input", "severity": "MEDIUM" if big else "LOW"}))
    for e in (earnings or {}).get("holdings") or []:
        items.append((2.8, {"type": "earnings", "title": f"Holding {e['symbol']} reports {str(e['datetime'])[:10]} ({e.get('timing') or 'time n/a'})",
                            "implication": f"EPS estimate {e.get('eps_estimate') if e.get('eps_estimate') is not None else '—'}; "
                                           "gap risk on the position", "severity": "HIGH"}))
    soon = (date.today() + timedelta(days=2)).isoformat()
    for e in ((earnings or {}).get("large_caps") or [])[:4]:
        if str(e.get("datetime"))[:10] <= soon:
            cap = e.get("market_cap") or 0
            items.append((1.4, {"type": "earnings", "title": f"{e['company']} ({e['symbol']}) reports {str(e['datetime'])[:10]} "
                                                          f"{(e.get('timing') or '').lower()}",
                                "implication": f"${cap / 1e9:,.0f}bn market cap — index-level earnings risk"
                                               + (f"; EPS estimate {e['eps_estimate']}" if e.get("eps_estimate") is not None else ""),
                                "severity": "LOW"}))
    for x in (pos or {}).get("cot_extremes") or []:
        items.append((1.6, {"type": "positioning", "title": f"CFTC {x['market']}: speculators at a 3-year extreme (index {x['cot_index']})",
                            "implication": f"Contrarian read: {x['signal'].replace('_', ' ').lower()} (report {x['report_date']})",
                            "severity": "MEDIUM"}))
    items.sort(key=lambda t: -t[0])
    return [dict(p, priority=i + 1) for i, (_, p) in enumerate(items)]
