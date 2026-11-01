"""
Comparables for an LBO: where the entry and exit multiples sit against the market.

  trading comps    listed peers' EV/EBITDA today (api/marketdata/security.comps — same industry, by region);
                   multiples above 40× or at / below zero are listed but left out of the statistics (n/m)
  precedents       control transactions the team records in the fund's own database — target, acquirer, date, EV,
                   EBITDA, currency and a source for each (no free source publishes deal multiples; this is the
                   firm's own comps book)
  industry         Damodaran's EV/EBITDA for the industry and region (api/pe/market.industry_multiple)

`benchmark()` sets the deal's entry and exit multiples against all three: quartiles, medians, and where the deal sits.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional

MAX_MULTIPLE = 40.0
_ready: set = set()


def _quartiles(xs: List[float]) -> Optional[Dict[str, float]]:
    xs = sorted(xs)
    if not xs:
        return None
    def q(p):
        k = (len(xs) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
    return {"low": xs[0], "q1": q(0.25), "median": median(xs), "q3": q(0.75), "high": xs[-1], "n": len(xs)}


def _usable(v: Any) -> bool:
    return isinstance(v, (int, float)) and 0 < v <= MAX_MULTIPLE


# ── Trading comps ────────────────────────────────────────────────────────────────────────────────────────────────
def trading(symbol: str) -> Dict[str, Any]:
    """Listed peers' EV/EBITDA and its distribution (the subject excluded from the statistics)."""
    from api.marketdata import security
    c = security.comps(symbol)
    rows = c.get("rows") or []
    subject = next((r for r in rows if r.get("subject")), None)
    peers = [{"symbol": r.get("symbol"), "name": r.get("name"), "region": r.get("region"), "country": r.get("country"),
              "market_cap_usd": r.get("market_cap_usd"), "ev_ebitda": r.get("ev_ebitda"), "operating_margin": r.get("operating_margin"),
              "revenue_growth": r.get("revenue_growth"), "usable": _usable(r.get("ev_ebitda"))}
             for r in rows if not r.get("subject")]
    by_region: Dict[str, List[float]] = {}
    for p in peers:
        if p["usable"]:
            by_region.setdefault(p["region"] or "Other", []).append(p["ev_ebitda"])
    return {"industry": c.get("industry"), "subject": ({"symbol": subject.get("symbol"), "ev_ebitda": subject.get("ev_ebitda")} if subject else None),
            "peers": peers, "stats": _quartiles([p["ev_ebitda"] for p in peers if p["usable"]]),
            "by_region": {k: _quartiles(v) for k, v in by_region.items()},
            "excluded": [p["symbol"] for p in peers if not p["usable"]],
            "source": f"{c.get('source') or 'Yahoo Finance'} — listed peers in {c.get('industry')}; above {MAX_MULTIPLE:.0f}× or ≤ 0 treated as n/m"}


# ── Precedent transactions (the fund's own comps book) ───────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    from api import funds
    path = funds.db_path()
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    if path not in _ready:
        c.execute("""CREATE TABLE IF NOT EXISTS pe_precedents (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
            target TEXT NOT NULL, acquirer TEXT, sector TEXT, region TEXT, currency TEXT, ev REAL NOT NULL, ebitda REAL NOT NULL,
            deal_type TEXT, source TEXT NOT NULL, notes TEXT, added_by TEXT, created_at TEXT)""")
        _ready.add(path)
    return c


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    d["ev_ebitda"] = d["ev"] / d["ebitda"] if d.get("ebitda") else None
    return d


def list_precedents(sector: Optional[str] = None) -> List[Dict[str, Any]]:
    """The fund's precedent transactions, newest first; `sector` filters by a case-insensitive match."""
    with _conn() as c:
        rows = [_row(r) for r in c.execute("SELECT * FROM pe_precedents ORDER BY date DESC, id DESC")]
    if sector:
        s = sector.lower()
        rows = [r for r in rows if r.get("sector") and (s in r["sector"].lower() or r["sector"].lower() in s)]
    return rows


def add_precedent(who: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """Record a transaction. EV and EBITDA must be positive and a source (filing, press release, report) is required."""
    target = (d.get("target") or "").strip()
    source = (d.get("source") or "").strip()
    date = (d.get("date") or "").strip()[:10]
    try:
        ev, ebitda = float(d.get("ev")), float(d.get("ebitda"))
        datetime.fromisoformat(date)
    except (TypeError, ValueError):
        raise ValueError("A precedent needs a date (YYYY-MM-DD) and numeric EV and EBITDA.")
    if not target:
        raise ValueError("The target's name is required.")
    if not source:
        raise ValueError("A source is required (filing, press release, broker or report) — every multiple must be traceable.")
    if ev <= 0 or ebitda <= 0:
        raise ValueError("EV and EBITDA must be positive (an EV/EBITDA multiple needs positive EBITDA).")
    with _conn() as c:
        cur = c.execute("INSERT INTO pe_precedents (date, target, acquirer, sector, region, currency, ev, ebitda, deal_type, source, "
                        "notes, added_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (date, target[:120], (d.get("acquirer") or "")[:120] or None, (d.get("sector") or "")[:80] or None,
                         (d.get("region") or "")[:40] or None, (d.get("currency") or "")[:3].upper() or None, ev, ebitda,
                         (d.get("deal_type") or "")[:40] or None, source[:300], (d.get("notes") or "")[:2000] or None, who,
                         datetime.now(timezone.utc).isoformat(timespec="seconds")))
        return _row(c.execute("SELECT * FROM pe_precedents WHERE id = ?", (cur.lastrowid,)).fetchone())


def delete_precedent(pid: int) -> None:
    with _conn() as c:
        if c.execute("DELETE FROM pe_precedents WHERE id = ?", (pid,)).rowcount == 0:
            raise LookupError("No such precedent.")


# ── Benchmark ────────────────────────────────────────────────────────────────────────────────────────────────────
def _position(v: Optional[float], st: Optional[Dict[str, float]]) -> Optional[str]:
    if v is None or not st:
        return None
    if v < st["q1"]:
        return "below the lower quartile"
    if v > st["q3"]:
        return "above the upper quartile"
    return "within the interquartile range"


def benchmark(entry_multiple: Optional[float], exit_multiple: Optional[float], symbol: Optional[str] = None,
              sector: Optional[str] = None, industry_ev_ebitda: Optional[float] = None) -> Dict[str, Any]:
    """The deal's entry and exit multiples against trading comps, the fund's precedents and the industry."""
    tr = None
    if symbol:
        try:
            tr = trading(symbol)
        except Exception as e:                            # no industry / screener unavailable: precedents still work
            tr = {"error": str(e)}
    sec = sector or (tr or {}).get("industry")
    prec = list_precedents(sec) if sec else list_precedents()
    pst = _quartiles([p["ev_ebitda"] for p in prec if _usable(p["ev_ebitda"])])
    tst = (tr or {}).get("stats")
    notes = []
    if entry_multiple and pst:
        notes.append(f"Entry {entry_multiple:.1f}× is {_position(entry_multiple, pst)} of {pst['n']} precedent deals (median {pst['median']:.1f}×).")
    if entry_multiple and tst:
        prem = entry_multiple / tst["median"] - 1
        notes.append(f"Entry is {prem:+.0%} vs the trading-comps median {tst['median']:.1f}× — buyouts typically pay a control premium over trading levels.")
    if exit_multiple and tst:
        notes.append(f"Exit {exit_multiple:.1f}× is {_position(exit_multiple, tst)} of trading comps; an exit above the median "
                     "assumes the market re-rates the business.")
    if exit_multiple and industry_ev_ebitda:
        notes.append(f"Industry EV/EBITDA (Damodaran) {industry_ev_ebitda:.1f}× — exit {exit_multiple / industry_ev_ebitda - 1:+.0%} vs it.")
    if not prec:
        notes.append("No precedent transactions recorded for this sector yet — add the deals you track under Precedents.")
    return {"trading": tr, "precedents": prec, "precedent_stats": pst, "sector": sec, "industry_ev_ebitda": industry_ev_ebitda,
            "entry": {"multiple": entry_multiple, "vs_precedents": _position(entry_multiple, pst), "vs_trading": _position(entry_multiple, tst)},
            "exit": {"multiple": exit_multiple, "vs_trading": _position(exit_multiple, tst), "vs_precedents": _position(exit_multiple, pst)},
            "notes": notes}
