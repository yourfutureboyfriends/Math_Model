"""
The monthly internal reporting pack and the board-level scorecard (api/governance.py holds the controls).

Monthly pack, as the plan lists it: returns (monthly and cumulative net return, account cash flows, trading costs,
realised / unrealised P&L), risk (drawdown, volatility, gross / net exposure, limit exceptions), attribution (P&L by
strategy sleeve, instrument and market regime), implementation (signal-to-fill delay, slippage, rejected orders,
outages), research changes (model versions, promotions, retirements) and validation (reconciliations, sign-offs,
calculation conventions). Every figure comes from the fund's own ledger and NAV record; what cannot be computed is
said, not estimated. Paper / simulated results carry that label.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from api.portfolio_store import _conn


def _month_bounds(month: str):
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start.isoformat(), end.isoformat()


def _flows() -> Dict[str, float]:
    """Capital changes by date (from the audit log of fund-settings changes) — the account's cash flows."""
    out: Dict[str, float] = {}
    with _conn() as c:
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "decision_log" not in tabs:
            return out
        for r in c.execute("SELECT ts, before_state, after_state FROM decision_log WHERE action = 'fund_settings_update' ORDER BY id"):
            try:
                b, a = json.loads(r["before_state"] or "{}"), json.loads(r["after_state"] or "{}")
            except ValueError:
                continue
            if b.get("capital") is not None and a.get("capital") is not None and a["capital"] != b["capital"]:
                if (a.get("base_currency") or "USD") == (b.get("base_currency") or "USD"):
                    d = str(r["ts"])[:10]
                    out[d] = out.get(d, 0.0) + float(a["capital"]) - float(b["capital"])
    return out


def _daily_returns(rows: List[Dict[str, Any]], flows: Dict[str, float]) -> List[Dict[str, Any]]:
    """Flow-adjusted daily returns of the NAV record: r = (NAV_t − flow_t) / NAV_{t−1} − 1."""
    out = []
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        if not a.get("nav"):
            continue
        f = sum(v for d, v in flows.items() if a["date"] < d <= b["date"])
        out.append({"date": b["date"], "r": (float(b["nav"]) - f) / float(a["nav"]) - 1, "flow": f,
                    "regime": a.get("regime")})
    return out


def _to_base(t: Dict[str, Any], v: float) -> float:
    return v * (t.get("usd_per_unit") or 1.0) * (t.get("base_per_usd") or 1.0)


def monthly_report(month: Optional[str] = None) -> Dict[str, Any]:
    from api import fund_store, governance as gov, trade_lifecycle as tl, blotter_store
    blotter_store.init_db()
    gov.init_db()
    month = month or date.today().strftime("%Y-%m")
    m0, m1 = _month_bounds(month)
    st = gov.settings()
    base = st["base_currency"]
    nav = fund_store.nav_history()
    flows = _flows()
    rets = _daily_returns(nav, flows)
    in_m = [r for r in rets if m0 <= r["date"] < m1]
    upto = [r for r in rets if r["date"] < m1]
    month_ret = math.prod(1 + r["r"] for r in in_m) - 1 if in_m else None
    cum_ret = math.prod(1 + r["r"] for r in upto) - 1 if upto else None
    nav_m = [r for r in nav if m0 <= r["date"] < m1]
    # drawdown and volatility on the flow-adjusted index up to month end
    idx, peak, mdd = 1.0, 1.0, 0.0
    for r in upto:
        idx *= 1 + r["r"]
        peak = max(peak, idx)
        mdd = min(mdd, idx / peak - 1)
    vol = None
    if len(in_m) >= 5:
        mu = sum(r["r"] for r in in_m) / len(in_m)
        vol = math.sqrt(sum((r["r"] - mu) ** 2 for r in in_m) / (len(in_m) - 1)) * math.sqrt(252)
    with _conn() as c:
        trades = [dict(r) for r in c.execute("SELECT * FROM trades WHERE ts >= ? AND ts < ? ORDER BY id", (m0, m1))]
        logs = [dict(r) for r in c.execute("SELECT ts, user, action, target, rationale FROM decision_log WHERE ts >= ? AND ts < ? "
                                           "ORDER BY id", (m0, m1))] if c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='decision_log'").fetchone() else []
        events = [dict(r) for r in c.execute("SELECT e.*, m.name FROM gov_model_events e JOIN gov_models m ON m.id = e.model_id "
                                             "WHERE e.ts >= ? AND e.ts < ? ORDER BY e.id", (m0, m1))]
        recs = [dict(r) for r in c.execute("SELECT * FROM gov_reconciliations WHERE ts >= ? AND ts < ? ORDER BY id", (m0, m1))]
        incs = [dict(r) for r in c.execute("SELECT * FROM gov_incidents WHERE ts >= ? AND ts < ? ORDER BY id", (m0, m1))]
        halts = [dict(r) for r in c.execute("SELECT * FROM gov_halts WHERE started_at >= ? AND started_at < ? ORDER BY id", (m0, m1))]
    costs_comm = sum(_to_base(t, float(t.get("commission") or 0)) for t in trades)
    costs_tax = sum(_to_base(t, float(t.get("taxes") or 0)) for t in trades)
    realised = sum(_to_base(t, float(t.get("realized_pnl") or 0)) for t in trades)
    by_book: Dict[str, Dict[str, float]] = {}
    by_sym: Dict[str, Dict[str, float]] = {}
    for t in trades:
        for key, agg in ((t["book"], by_book), (str(t["symbol"]).upper(), by_sym)):
            g = agg.setdefault(key, {"realised": 0.0, "costs": 0.0, "fills": 0})
            g["realised"] += _to_base(t, float(t.get("realized_pnl") or 0))
            g["costs"] += _to_base(t, float(t.get("commission") or 0) + float(t.get("taxes") or 0))
            g["fills"] += 1
    current_month = month == date.today().strftime("%Y-%m")
    unreal_by_book, unreal_by_sym, unreal_total = {}, {}, None
    if current_month:
        from api.handlers.portfolio_analytics import book_in_base
        bk = book_in_base(None)
        unreal_total = 0.0
        for p in bk["positions"]:
            u = float(p.get("unrealized_pnl") or 0)
            unreal_total += u
            unreal_by_book[p.get("book") or "—"] = unreal_by_book.get(p.get("book") or "—", 0.0) + u
            unreal_by_sym[p["symbol"]] = unreal_by_sym.get(p["symbol"], 0.0) + u
    elif nav_m:
        unreal_total = nav_m[-1].get("unrealized_pnl")
    by_regime: Dict[str, Dict[str, float]] = {}
    for r in in_m:
        g = by_regime.setdefault(r["regime"] or "unrecorded", {"days": 0, "return": 1.0})
        g["days"] += 1
        g["return"] *= 1 + r["r"]
    # implementation: lifecycle rows filled this month
    lc = tl.lifecycle(limit=500)["orders"]
    filled = [o for o in lc if o.get("fill") and m0 <= str(o["fill"]["ts"])[:10] < m1]
    delays = []
    for o in filled:
        start = (o.get("assessment") or {}).get("ts") or o.get("created_at")
        try:
            delays.append((datetime.fromisoformat(str(o["fill"]["ts"]).replace("Z", "+00:00")) -
                           datetime.fromisoformat(str(start).replace("Z", "+00:00"))).total_seconds() / 3600)
        except (TypeError, ValueError):
            pass
    slip = [o["tca"]["actual"]["execution_bps"] for o in filled if o.get("tca") and o["tca"]["actual"]["execution_bps"] is not None]
    rejected = [l for l in logs if l["action"] == "order_rejected"]
    not_filled = [l for l in logs if l["action"] == "order_not_filled"]
    exceptions = [l for l in logs if l["action"] in ("order_created", "order_approved") and
                  ("WARN" in (l["rationale"] or "") or "BLOCK" in (l["rationale"] or ""))]
    sim = any(str((o.get("fill") or {}).get("source") or "").startswith("simulated") for o in filled) or st["stage"] == "research"
    r2 = lambda v: round(v, 2) if v is not None else None
    return {
        "fund": st["fund_name"], "month": month, "currency": base, "stage": st["stage_label"],
        "label": gov.results_label(st["stage"], simulated=sim),
        "returns": {"month_return": r2(month_ret * 100) if month_ret is not None else None,
                    "cumulative_return": r2(cum_ret * 100) if cum_ret is not None else None,
                    "series_start": nav[0]["date"] if nav else None, "sessions_in_month": len(in_m),
                    "nav_start": nav_m[0]["nav"] if nav_m else None, "nav_end": nav_m[-1]["nav"] if nav_m else None,
                    "cash_flows": {d: v for d, v in flows.items() if m0 <= d < m1},
                    "trading_costs": {"commission": r2(costs_comm), "taxes": r2(costs_tax), "total": r2(costs_comm + costs_tax)},
                    "realised_pnl": r2(realised), "unrealised_pnl": r2(unreal_total) if unreal_total is not None else None,
                    "unit": "% (returns), base currency (amounts)"},
        "risk": {"max_drawdown_to_date": r2(mdd * 100), "volatility_ann": r2(vol * 100) if vol is not None else None,
                 "gross": nav_m[-1].get("gross") if nav_m else None, "net": nav_m[-1].get("net") if nav_m else None,
                 "var95_1d": nav_m[-1].get("var95_1d") if nav_m else None,
                 "limit_exceptions": [{"ts": l["ts"], "text": l["rationale"]} for l in exceptions],
                 "incidents": [{"id": i["id"], "kind": i["kind"], "status": i["status"], "description": i["description"]} for i in incs],
                 "halts": [{"kind": h["kind"], "reason": h["reason"], "started": h["started_at"], "ended": h["ended_at"],
                            "test": bool(h["test"])} for h in halts],
                 "scenarios": "Stress scenarios (equity crash, FX gap, rate shock, correlations → 1, data outage, liquidity "
                              "withdrawal): run in the Scenario Analysis panel and attach to the pack."},
        "attribution": {"by_sleeve": {k: {**{a: r2(b) for a, b in v.items()}, "unrealised_now": r2(unreal_by_book.get(k))}
                                      for k, v in (by_book or {k: {"realised": 0.0, "costs": 0.0, "fills": 0} for k in unreal_by_book}).items()},
                        "by_instrument": {k: {**{a: r2(b) for a, b in v.items()}, "unrealised_now": r2(unreal_by_sym.get(k))}
                                          for k, v in (by_sym or {k: {"realised": 0.0, "costs": 0.0, "fills": 0} for k in unreal_by_sym}).items()},
                        "by_regime": {k: {"days": v["days"], "return_pct": r2((v["return"] - 1) * 100)} for k, v in by_regime.items()},
                        "note": ("Realised P&L and costs from this month's fills; unrealised by sleeve / instrument is shown "
                                 "for the current month only (positions are not stored at past month-ends). Regime = the "
                                 "model regime recorded with each day's NAV snapshot.")},
        "implementation": {"fills": len(filled),
                           "signal_to_fill_hours_median": r2(sorted(delays)[len(delays) // 2]) if delays else None,
                           "slippage_bps_avg": r2(sum(slip) / len(slip)) if slip else None,
                           "rejected_orders": len(rejected), "not_filled": len(not_filled),
                           "outages": [i for i in incs if i["kind"] in ("price_feed", "data_outage")],
                           "note": "Delay = pre-trade assessment (or order) → fill. Slippage = reference price → fill."},
        "research_changes": [{"ts": e["ts"], "model": f"#{e['model_id']} {e['name']}", "action": e["action"],
                              "gate": e.get("gate_to") or e.get("gate_from"), "by": e["user"], "note": e.get("note")} for e in events],
        "validation": {"reconciliations": len(recs), "clean": sum(1 for r in recs if r["ok"]),
                       "breaks": sum(len(json.loads(r["breaks"] or "[]")) for r in recs),
                       "incidents_signed_off": sum(1 for i in incs if i["status"] == "signed_off"),
                       "conventions": (f"Returns: daily, flow-adjusted (capital changes as cash flows), geometrically "
                                       f"linked, net of all booked costs, in {base}. NAV marked at the daily close. "
                                       "Positions reconciled to the fills ledger; no broker statement is connected.")},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def scorecard() -> Dict[str, Any]:
    """The board-level scorecard: what the platform can measure, and what must be entered by the team."""
    from api import governance as gov, trade_lifecycle as tl
    gov.init_db()
    models = gov.list_models()
    approved = [m for m in models if gov.GATES.index(m["gate"]) >= 2 and m["status"] != "rejected"]
    rejected = [m for m in models if m["status"] == "rejected"]
    recs = gov.reconciliations(90)
    lc = tl.lifecycle(limit=500)["summary"]
    incs = gov.incidents()
    with _conn() as c:
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        breaches = c.execute("SELECT COUNT(*) FROM decision_log WHERE action IN ('order_created','order_approved') AND "
                             "(rationale LIKE '%BLOCK%' OR rationale LIKE '%WARN%')").fetchone()[0] if "decision_log" in tabs else 0
    ms = gov.milestones()
    b = gov.budget()
    from api import fund_store
    nav = fund_store.nav_history()
    peak, mdd = 0.0, 0.0
    for r in nav:
        peak = max(peak, float(r["nav"] or 0))
        if peak:
            mdd = min(mdd, float(r["nav"]) / peak - 1)
    return {
        "research": {"models": len(models), "approved_g2_plus": len(approved), "rejected": len(rejected),
                     "approved_to_rejected": f"{len(approved)}:{len(rejected)}",
                     "out_of_sample_robust": sum(1 for m in approved if m.get("result_ref")),
                     "point_in_time_completeness": "enter at G1 (data approval evidence per model)"},
        "trading_and_risk": {"reconciliations_90d": len(recs),
                             "reconciliation_rate": round(sum(1 for r in recs if r["ok"]) / len(recs), 3) if recs else None,
                             "cost_vs_estimate_bps": (round(lc["avg_shortfall_bps"] - lc["avg_estimated_bps"], 2)
                                                      if lc["avg_shortfall_bps"] is not None and lc["avg_estimated_bps"] is not None else None),
                             "max_drawdown_pct": round(mdd * 100, 2), "limit_exceptions": breaches},
        "organisation": {"milestones": len(ms), "with_owner": sum(1 for m in ms if m.get("owner")),
                         "done": sum(1 for m in ms if m["status"] == "done"),
                         "signed_off": sum(1 for m in ms if m.get("signed_off_by")),
                         "incidents_open": sum(1 for i in incs if i["status"] != "signed_off"),
                         "kill_switch_tests": sum(1 for h in _halts() if h["test"]),
                         "budget": {"total": b["total_budget"], "spent": b["total_spent"], "variance": b["variance"]}},
        "commercial": {"note": "Qualified diligence discussions, an independently verified record and committed eligible "
                               "seed capital are not tracked by the platform: record them in the milestones."},
        "label": gov.results_label(),
    }


def _halts() -> List[Dict[str, Any]]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM gov_halts")]
