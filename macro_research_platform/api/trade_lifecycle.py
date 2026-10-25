"""
One view of a trade from idea to fill: analyst pitch → pre-trade assessment → order (four-eyes approval) → fill, with
transaction-cost analysis of the fill against the assessment's own estimate.

Each pre-trade assessment is stored (per fund) with its decision price and estimated costs. An order carries the
assessment (and pitch) it was based on — given on the ticket, or the latest assessment of the same name and side in the
last three days, marked as linked automatically.

TCA, in bps of the order's notional (positive = cost):
  decision → execution reference   market move between the assessment and execution (delay; not a cost estimate)
  reference → fill                 execution cost: spread + impact (estimated: half-spread + staged impact)
  commission + taxes               explicit costs (estimated: the assessment's commission and tax rates)
  implementation shortfall         decision → fill + explicit costs
A simulated fill is priced by the same cost model as the estimate, so its execution cost matches by construction:
the comparison only becomes informative with broker (paper or live) fills, and every row says which it is.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.portfolio_store import _conn


def init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pretrade_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user TEXT, symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity REAL, decision_price REAL, price_currency TEXT, price_time TEXT, market_state TEXT,
            notional_base REAL, base_currency TEXT, half_spread_bps REAL, half_spread_basis TEXT, impact_bps REAL,
            commission_bps REAL, taxes_bps REAL, fx_bps REAL, total_bps REAL, verdict TEXT, pitch_id INTEGER,
            flags TEXT)""")
        c.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_assessment(r: Dict[str, Any], user: str, pitch_id: Optional[int] = None) -> int:
    """Store a pre-trade assessment's decision price and cost estimate; returns its id."""
    init_db()
    c_ = r.get("costs") or {}
    row = {"ts": _now(), "user": user, "symbol": r["symbol"], "side": (r.get("side") or "").upper(),
           "quantity": (r.get("size") or {}).get("quantity"), "decision_price": (r.get("price") or {}).get("last"),
           "price_currency": (r.get("price") or {}).get("currency"), "price_time": (r.get("price") or {}).get("quote_time"),
           "market_state": (r.get("price") or {}).get("market_state"),
           "notional_base": (r.get("size") or {}).get("notional_base"), "base_currency": r.get("base_currency"),
           "half_spread_bps": (c_.get("half_spread_bps") or {}).get("value"),
           "half_spread_basis": (c_.get("half_spread_bps") or {}).get("basis"),
           "impact_bps": (c_.get("impact_bps") or {}).get("staged_at_cap"),
           "commission_bps": (c_.get("commission_bps") or {}).get("value"),
           "taxes_bps": (c_.get("taxes_bps") or {}).get("value"),
           "fx_bps": (c_.get("fx_conversion_bps") or {}).get("value"), "total_bps": c_.get("total_bps"),
           "verdict": (r.get("assessment") or {}).get("verdict"), "pitch_id": pitch_id,
           "flags": json.dumps([f.get("message") for f in (r.get("flags") or [])][:20])}
    with _conn() as c:
        cur = c.execute(f"INSERT INTO pretrade_assessments ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                        list(row.values()))
        c.commit()
        return int(cur.lastrowid)


def get_assessment(aid: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as c:
        r = c.execute("SELECT * FROM pretrade_assessments WHERE id = ?", (aid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["flags"] = json.loads(d.get("flags") or "[]")
    return d


def latest_assessment(symbol: str, side: str, within_days: int = 3) -> Optional[Dict[str, Any]]:
    init_db()
    since = (datetime.now(timezone.utc) - timedelta(days=within_days)).isoformat()
    with _conn() as c:
        r = c.execute("SELECT id FROM pretrade_assessments WHERE UPPER(symbol) = ? AND side = ? AND ts >= ? "
                      "ORDER BY id DESC LIMIT 1", (symbol.upper(), side.upper(), since)).fetchone()
    return get_assessment(r["id"]) if r else None


def tca(side: str, quantity: float, assessment: Optional[Dict[str, Any]], trade: Dict[str, Any]) -> Dict[str, Any]:
    """Estimate vs actual for one fill (bps of notional at the fill price; positive = cost)."""
    sign = 1 if str(side).upper() in ("BUY", "COVER") else -1
    fill = float(trade["price"])
    q = float(trade.get("quantity") or quantity or 0)
    notional = abs(q * fill)
    ref = trade.get("reference_price")
    arrival = (assessment or {}).get("decision_price")
    explicit = ((float(trade.get("commission") or 0) + float(trade.get("taxes") or 0)) / notional * 1e4) if notional else None
    simulated = str(trade.get("source") or "").startswith("simulated")
    out: Dict[str, Any] = {
        "fill_price": fill, "reference_price": ref, "decision_price": arrival, "notional_local": round(notional, 2),
        "fill_source": trade.get("source"), "simulated": simulated,
        "actual": {"delay_bps": round(sign * (ref / arrival - 1) * 1e4, 2) if ref and arrival else None,
                   "execution_bps": round(sign * (fill / ref - 1) * 1e4, 2) if ref else None,
                   "explicit_bps": round(explicit, 2) if explicit is not None else None,
                   "implementation_shortfall_bps": (round(sign * (fill / arrival - 1) * 1e4 + (explicit or 0), 2)
                                                    if arrival else None)},
    }
    if assessment:
        est_exec = (assessment.get("half_spread_bps") or 0) + (assessment.get("impact_bps") or 0)
        est_expl = (assessment.get("commission_bps") or 0) + (assessment.get("taxes_bps") or 0)
        out["estimate"] = {"execution_bps": round(est_exec, 2), "explicit_bps": round(est_expl, 2),
                           "fx_bps": assessment.get("fx_bps"), "total_bps": assessment.get("total_bps"),
                           "half_spread_basis": assessment.get("half_spread_basis")}
        a = out["actual"]
        out["actual_minus_estimate_bps"] = {
            "execution": round(a["execution_bps"] - est_exec, 2) if a["execution_bps"] is not None else None,
            "explicit": round(a["explicit_bps"] - est_expl, 2) if a["explicit_bps"] is not None else None}
        if simulated:
            out["note"] = ("Simulated fill: priced by the same cost model as the estimate, so the execution cost "
                           "matches by construction — compare with broker fills for a real test of the model.")
        if assessment.get("fx_bps"):
            out.setdefault("note_fx", "The FX conversion estimate is not charged on fills in this book (no FX "
                                      "trade is booked); it stays an estimate.")
    else:
        out["note"] = "No pre-trade assessment linked to this order: only the actual costs are shown."
    return out


def lifecycle(symbol: Optional[str] = None, pitch_id: Optional[int] = None, limit: int = 100) -> Dict[str, Any]:
    """Orders (newest first) with their pitch, pre-trade assessment, approval trail, fill and TCA."""
    from api import blotter_store, pitches, portfolio_store
    blotter_store.init_db()
    init_db()
    orders = [o for o in portfolio_store.list_trade_ideas(None) if o.get("side") and o.get("quantity")]
    if symbol:
        orders = [o for o in orders if str(o["symbol"]).upper() == symbol.upper()]
    if pitch_id is not None:
        orders = [o for o in orders if o.get("pitch_id") == pitch_id]
    orders = sorted(orders, key=lambda o: o.get("id") or 0, reverse=True)[:limit]
    with _conn() as c:
        trades = {r["id"]: dict(r) for r in c.execute("SELECT * FROM trades")}
    pitch_cache: Dict[int, Any] = {}
    rows, est, act = [], [], []
    for o in orders:
        a = get_assessment(o["assessment_id"]) if o.get("assessment_id") else None
        pid = o.get("pitch_id") or (a or {}).get("pitch_id")
        if pid and pid not in pitch_cache:
            try:
                p = pitches.get(pid)
                pitch_cache[pid] = {"id": pid, "title": p.get("title"), "status": p.get("status"),
                                    "analyst": p.get("analyst"), "decided_by": p.get("decided_by")}
            except Exception:                                                  # noqa: BLE001 — pitch deleted / other fund
                pitch_cache[pid] = {"id": pid, "missing": True}
        t = trades.get(o.get("executed_trade_id")) if o.get("executed_trade_id") else None
        hist = o.get("state_history")
        if isinstance(hist, str):
            try:
                hist = json.loads(hist)
            except ValueError:
                hist = []
        row = {"order_id": o["id"], "symbol": o["symbol"], "side": o["side"], "quantity": o["quantity"],
               "book": o.get("book"), "state": o.get("state"), "created_by": o.get("created_by"),
               "created_at": o.get("created_at"), "approved_by": o.get("approved_by"),
               "approval_note": o.get("approval_note"), "history": hist or [],
               "pitch": pitch_cache.get(pid) if pid else None,
               "assessment": ({k: a[k] for k in ("id", "ts", "user", "decision_price", "price_currency", "market_state",
                                                "total_bps", "verdict", "half_spread_basis")} | {"link": o.get("assessment_link")}
                              if a else None),
               "fill": ({k: t.get(k) for k in ("id", "ts", "price", "quantity", "commission", "taxes", "source", "currency")}
                        if t else None)}
        if t:
            row["tca"] = tca(o["side"], o["quantity"], a, t)
            if a and row["tca"]["actual"]["implementation_shortfall_bps"] is not None and a.get("total_bps") is not None:
                est.append(a["total_bps"] - (a.get("fx_bps") or 0))
                act.append(row["tca"]["actual"]["implementation_shortfall_bps"])
        rows.append(row)
    summary = {"orders": len(rows), "executed": sum(1 for r in rows if r["fill"]),
               "with_assessment": sum(1 for r in rows if r["assessment"]),
               "with_pitch": sum(1 for r in rows if r["pitch"]),
               "compared": len(act),
               "avg_estimated_bps": round(sum(est) / len(est), 2) if est else None,
               "avg_shortfall_bps": round(sum(act) / len(act), 2) if act else None}
    return {"orders": rows, "summary": summary,
            "method": ("Shortfall = decision price (the assessment's) → fill, plus commission and taxes, in bps of "
                       "notional; positive = cost. The estimate excludes the FX conversion assumption, which fills "
                       "here do not charge.")}
