"""
Fund governance: the operating controls of a written investment plan, kept per fund (its own database).

Built for Moriah Capital Partners' Future Growth Strategy (Oct 2026) and usable by any fund that turns it on
(setting "governance": true):

* Stage           Phase I research & paper portfolio → II small proprietary live → III seed readiness → IV fund.
                  Results are labelled by stage: paper / simulated results are never called a fund track record.
* Instruments     the approved-instruments list: proposed by one person, approved by another (PM or risk); an order
                  in an instrument that is not approved and tradable is blocked.
* Models          the G0–G5 gates (research proposal, data approval, backtest, shadow trading, small live,
                  scale/retire): required evidence per gate, sign-offs by the decision authority, never the model's
                  owner; rejected and retired models stay in the research log. With "require_approved_model", an
                  order must name a model at G3 or later that is not suspended.
* Risk policy     no leverage, no shorting without approval, single-model and single-theme ex-ante risk shares,
                  pause new orders at a 1% daily loss, strategy drawdown review / suspend from the model's high-water
                  mark, order size and price-band checks.
* Controls        execution halt (kill switch) with an incident record and independent sign-off to resume; daily
                  positions reconciliation against the trade ledger — a break opens an incident and halts execution.
* Reporting       the monthly internal pack (returns, risk, attribution, implementation, research changes,
                  validation), the board scorecard, the budget ledger and the milestone roadmap.

Numbers the plan calls illustrative (limits, budgets) are seeded as the fund's starting values and can be changed;
nothing here invents performance, capital or external assets.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from api.portfolio_store import _conn

STAGES = {
    "research": "Phase I — research and paper portfolio (months 0–12)",
    "prop_live": "Phase II — small proprietary live trading (months 12–24)",
    "seed_readiness": "Phase III — seed readiness (months 24–36)",
    "fund": "Phase IV — fund assessment / launch only if viable (months 36–48)",
}
LIVE_STAGES = ("prop_live", "seed_readiness", "fund")

DEFAULT_RISK_POLICY: Dict[str, Any] = {
    "max_model_risk_share": 0.25,      # of total ex-ante portfolio risk (plan: illustrative default)
    "max_theme_risk_share": 0.35,      # one correlated economic theme
    "max_gross_leverage": 1.00,        # no portfolio borrowing in the earliest phase
    "allow_short": False,              # shorting borrows stock: needs separate approval
    "daily_loss_pause": 0.01,          # pause new orders at a 1% daily account loss
    "strategy_dd_review": 0.05,        # review at 5% from the model's high-water mark
    "strategy_dd_suspend": 0.08,       # suspend at 8%
    "max_order_pct_nav": 0.20,         # order-size check (platform default; the plan names the check, not a level)
    "price_band": 0.05,                # order price within ±5% of the last close (platform default)
    "max_price_age_days": 4,           # price-feed freshness: last close no older than this (calendar days)
}

GATES = ["G0", "G1", "G2", "G3", "G4", "G5"]
GATE_INFO = {
    "G0": {"name": "Research proposal", "authority": "Research lead",
           "evidence": ["Economic mechanism", "Target variable", "Trade horizon", "Dataset specification", "Null hypothesis"]},
    "G1": {"name": "Data approval", "authority": "Research lead + independent reviewer",
           "evidence": ["Point-in-time integrity", "Coverage", "Survivorship", "Publication-timing audit"]},
    "G2": {"name": "Backtest", "authority": "Investment committee",
           "evidence": ["Costs and slippage", "Multiple-testing control", "Walk-forward / out-of-sample",
                        "Regime stress tests", "Baseline comparison"]},
    "G3": {"name": "Shadow trading", "authority": "Risk lead",
           "evidence": ["Time-stamped paper orders", "Signal-drift monitoring", "Realistic tradeability",
                        "Maximum loss budget and retirement criterion set"]},
    "G4": {"name": "Small live deployment", "authority": "Investment committee + risk sign-off",
           "evidence": ["Capital source documented", "Broker account", "Limits", "Kill switch tested",
                        "Reconciliations tested"]},
    "G5": {"name": "Scale / retire", "authority": "Investment committee",
           "evidence": ["Net live results", "Adverse scenarios", "Drawdown compliance", "Capital capacity"]},
}
# sign-offs needed to ENTER a gate: each a set of roles; distinct people, never the model's owner
GATE_SIGNOFFS = {"G1": [{"pm", "analyst"}, {"pm", "analyst", "risk", "quant"}], "G2": [{"pm"}], "G3": [{"risk"}],
                 "G4": [{"pm"}, {"risk"}], "G5": [{"pm"}]}
SLEEVES = {"macro_transmission": "Macro transmission", "systematic_trend": "Systematic trend",
           "cross_asset_rv": "Cross-asset relative value", "benchmark": "Benchmark / baseline", "other": "Other"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Create the governance tables (instruments, models, halts, incidents, reconciliations, budget, milestones) in the
    current fund's database.
    """
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS gov_instruments (
            symbol TEXT PRIMARY KEY, name TEXT, asset_class TEXT, theme TEXT, currency TEXT, tradable INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'proposed', note TEXT, proposed_by TEXT, proposed_at TEXT,
            approved_by TEXT, approved_at TEXT);
        CREATE TABLE IF NOT EXISTS gov_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sleeve TEXT, book TEXT, owner TEXT NOT NULL,
            mechanism TEXT, target_variable TEXT, horizon TEXT, dataset TEXT, null_hypothesis TEXT,
            gate TEXT NOT NULL DEFAULT 'G0', status TEXT NOT NULL DEFAULT 'active', version INTEGER DEFAULT 1,
            allocation REAL, max_loss_budget REAL, retirement_criterion TEXT, result_ref TEXT,
            hwm REAL, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS gov_model_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER NOT NULL, ts TEXT, user TEXT, role TEXT,
            action TEXT, gate_from TEXT, gate_to TEXT, evidence TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS gov_model_pnl (
            model_id INTEGER, date TEXT, pnl REAL, PRIMARY KEY (model_id, date));
        CREATE TABLE IF NOT EXISTS gov_halts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, active INTEGER NOT NULL DEFAULT 1, kind TEXT, reason TEXT,
            started_at TEXT, started_by TEXT, ended_at TEXT, ended_by TEXT, resolution TEXT, incident_id INTEGER,
            test INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS gov_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, severity TEXT, description TEXT,
            status TEXT DEFAULT 'open', fix TEXT, fixed_by TEXT, signed_off_by TEXT, signed_off_at TEXT,
            reported_by TEXT);
        CREATE TABLE IF NOT EXISTS gov_reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ok INTEGER, checked INTEGER, breaks TEXT, notes TEXT,
            run_by TEXT);
        CREATE TABLE IF NOT EXISTS gov_budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, category TEXT, amount REAL, currency TEXT,
            outcome TEXT);
        CREATE TABLE IF NOT EXISTS gov_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, category TEXT, amount REAL, currency TEXT,
            description TEXT, recorded_by TEXT, approved_by TEXT, approved_at TEXT);
        CREATE TABLE IF NOT EXISTS gov_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, plan TEXT, period TEXT, output TEXT, owner TEXT, acceptance TEXT,
            status TEXT DEFAULT 'open', evidence TEXT, updated_by TEXT, updated_at TEXT, signed_off_by TEXT,
            sort INTEGER);
        """)
        c.commit()


def _audit(action: str, text: str, user: str, target: str, before: Any = None, after: Any = None) -> None:
    from api import audit_store
    try:
        audit_store.add_decision(action, text, user=user, target=target, before_state=before, after_state=after)
    except Exception:                                                          # noqa: BLE001 — never block a control
        pass


# ── settings ─────────────────────────────────────────────────────────────────
def settings() -> Dict[str, Any]:
    """The fund's governance settings: on / off, stage, risk policy, capital and mandate."""
    from api import fund_store
    st = fund_store.get_settings()
    on = bool(st.get("governance"))
    return {"enabled": on, "stage": st.get("stage") or "research",
            "stage_label": STAGES.get(st.get("stage") or "research") if on or st.get("stage") else "no stage set (governance off)",
            "require_approved_model": bool(st.get("require_approved_model")),
            "risk_policy": {**DEFAULT_RISK_POLICY, **(st.get("risk_policy") or {})},
            "fund_name": st.get("fund_name"), "base_currency": st.get("base_currency") or "USD",
            "capital": st.get("capital"), "capital_basis": st.get("capital_basis"),
            "mandate_text": st.get("mandate_text")}


def results_label(stage: Optional[str] = None, simulated: bool = True) -> str:
    """How performance must be described (the plan: never call backtests or paper trading a fund track record)."""
    stage = stage or settings()["stage"]
    if stage == "research" or simulated:
        return "Simulated / paper results — not a fund track record"
    return "Live proprietary account results — broker-reconciled; not a fund track record of any future fund"


# ── approved instruments ─────────────────────────────────────────────────────
def instruments(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """The approved-instruments list, optionally by status."""
    init_db()
    with _conn() as c:
        q = "SELECT * FROM gov_instruments" + (" WHERE status = ?" if status else "") + " ORDER BY asset_class, symbol"
        return [dict(r) for r in c.execute(q, (status,) if status else ())]


def propose_instrument(symbol: str, user: str, name: str = "", asset_class: str = "", theme: str = "",
                       currency: str = "", tradable: bool = True, note: str = "") -> Dict[str, Any]:
    """Propose an instrument for the approved list (or re-propose it)."""
    init_db()
    sym = symbol.strip().upper()
    with _conn() as c:
        c.execute("INSERT INTO gov_instruments (symbol, name, asset_class, theme, currency, tradable, status, note, "
                  "proposed_by, proposed_at) VALUES (?,?,?,?,?,?,'proposed',?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
                  "name=excluded.name, asset_class=excluded.asset_class, theme=excluded.theme, currency=excluded.currency, "
                  "tradable=excluded.tradable, status='proposed', note=excluded.note, proposed_by=excluded.proposed_by, "
                  "proposed_at=excluded.proposed_at, approved_by=NULL, approved_at=NULL",
                  (sym, name, asset_class, theme, currency, 1 if tradable else 0, note, user, _now()))
        c.commit()
    _audit("instrument_proposed", f"Instrument {sym} proposed for the approved list", user, f"instrument:{sym}")
    return next(i for i in instruments() if i["symbol"] == sym)


def decide_instrument(symbol: str, user: str, approve: bool, note: str = "") -> Dict[str, Any]:
    """Approve or remove an instrument.

    Raises:
        LookupError: not on the list.
        PermissionError: the approver proposed it (four-eyes).
    """
    init_db()
    sym = symbol.strip().upper()
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_instruments WHERE symbol = ?", (sym,)).fetchone()
        if not r:
            raise LookupError(f"{sym} is not on the instruments list")
        if approve and r["proposed_by"] == user:
            raise PermissionError("the approver must be a different person from the proposer")
        c.execute("UPDATE gov_instruments SET status = ?, approved_by = ?, approved_at = ?, note = COALESCE(NULLIF(?, ''), note) "
                  "WHERE symbol = ?", ("approved" if approve else "removed", user, _now(), note, sym))
        c.commit()
    _audit("instrument_approved" if approve else "instrument_removed", f"Instrument {sym} {'approved' if approve else 'removed'}"
           + (f": {note}" if note else ""), user, f"instrument:{sym}")
    return next(i for i in instruments() if i["symbol"] == sym)


def instrument(symbol: str) -> Optional[Dict[str, Any]]:
    """One instrument's entry, or None."""
    init_db()
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_instruments WHERE symbol = ?", (symbol.strip().upper(),)).fetchone()
    return dict(r) if r else None


# ── model registry and gates ─────────────────────────────────────────────────
def _model_row(c, mid: int) -> Optional[Dict[str, Any]]:
    r = c.execute("SELECT * FROM gov_models WHERE id = ?", (mid,)).fetchone()
    return dict(r) if r else None


def get_model(mid: int) -> Dict[str, Any]:
    """One model with its event history.

    Raises:
        LookupError: no such model.
    """
    init_db()
    with _conn() as c:
        m = _model_row(c, mid)
        if not m:
            raise LookupError("model not found")
        m["events"] = [{**dict(e), "evidence": json.loads(e["evidence"] or "null")} for e in
                       c.execute("SELECT * FROM gov_model_events WHERE model_id = ? ORDER BY id", (mid,))]
    m["next_gate"] = _next_gate(m["gate"])
    m["pending_signoffs"] = _signoffs_for(m, m["next_gate"]) if m["next_gate"] else []
    return m


def list_models(include_closed: bool = True) -> List[Dict[str, Any]]:
    """Models in the registry, newest first; `include_closed=False` keeps only active and suspended ones."""
    init_db()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM gov_models ORDER BY id DESC")]
    return [r for r in rows if include_closed or r["status"] in ("active", "suspended")]


def create_model(user: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """G0 — research proposal: mechanism, target variable, horizon, dataset and null hypothesis are all required."""
    init_db()
    req = {"name": "name", "mechanism": "economic mechanism", "target_variable": "target variable",
           "horizon": "trade horizon", "dataset": "dataset specification", "null_hypothesis": "null hypothesis"}
    missing = [label for k, label in req.items() if not str(body.get(k) or "").strip()]
    if missing:
        raise ValueError("G0 needs: " + ", ".join(missing))
    sleeve = body.get("sleeve") or "other"
    if sleeve not in SLEEVES:
        raise ValueError(f"sleeve must be one of {', '.join(SLEEVES)}")
    row = {k: str(body.get(k) or "").strip()[:2000] for k in req}
    row.update(sleeve=sleeve, book=(body.get("book") or SLEEVES[sleeve])[:60], owner=user, gate="G0", status="active",
               created_at=_now(), updated_at=_now())
    with _conn() as c:
        cur = c.execute(f"INSERT INTO gov_models ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", list(row.values()))
        mid = int(cur.lastrowid)
        c.execute("INSERT INTO gov_model_events (model_id, ts, user, action, gate_to, evidence) VALUES (?,?,?,?,?,?)",
                  (mid, _now(), user, "proposed", "G0", json.dumps({k: row[k] for k in req})))
        c.commit()
    _audit("model_proposed", f"Model #{mid} '{row['name']}' proposed (G0, {SLEEVES[sleeve]})", user, f"model:{mid}")
    return get_model(mid)


def _next_gate(g: str) -> Optional[str]:
    i = GATES.index(g) if g in GATES else -1
    return GATES[i + 1] if 0 <= i < len(GATES) - 1 else None


def _signoffs_for(m: Dict[str, Any], gate: Optional[str]) -> List[Dict[str, Any]]:
    """Sign-offs already recorded towards entering `gate` (since the model last moved)."""
    if not gate:
        return []
    with _conn() as c:
        last_move = c.execute("SELECT MAX(id) FROM gov_model_events WHERE model_id = ? AND action IN ('advanced', 'proposed', "
                              "'new_version')", (m["id"],)).fetchone()[0] or 0
        return [dict(r) for r in c.execute("SELECT user, role, ts, note FROM gov_model_events WHERE model_id = ? AND id > ? "
                                           "AND action = 'signoff' AND gate_to = ?", (m["id"], last_move, gate))]


def _auto_evidence(gate: str, m: Dict[str, Any], evidence: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Checks the platform can verify itself; returns (facts, failures)."""
    facts: Dict[str, Any] = {}
    fails: List[str] = []
    if gate == "G2":
        ref = evidence.get("result") or {}
        owner, rid = ref.get("owner"), ref.get("id")
        if not owner or not rid:
            return facts, ["link the Quant Lab backtest result (owner and result id)"]
        from api.quant import store
        r = store.get_result(owner, int(rid))
        if not r:
            return facts, [f"Quant Lab result #{rid} of {owner} not found"]
        res = r.get("result") or {}
        prov = res.get("provenance") or {}
        val = res.get("validation") or {}
        costs = (res.get("costs") or {}).get("total_trading")
        oos = bool(res.get("holdout")) or str(prov.get("record_type") or "").startswith("walk-forward")
        caus = (val.get("causality") or {}).get("passed")
        multi = (val.get("pbo") is not None) or bool(res.get("trials") or res.get("deflated_sharpe"))
        base = bool((res.get("holdout") or {}).get("baseline_holdout") or res.get("baseline"))
        facts = {"result": f"{owner}#{rid} {r.get('label')}", "record_type": prov.get("record_type"),
                 "period": [prov.get("data_first"), prov.get("data_last")], "costs_total": costs,
                 "cost_model": prov.get("costs"), "out_of_sample": oos, "causality_passed": caus,
                 "multiple_testing": multi, "baseline": base, "sharpe": (res.get("metrics") or {}).get("sharpe"),
                 "max_drawdown": (res.get("metrics") or {}).get("max_drawdown"), "code_hash": prov.get("code_hash"),
                 "data_hash": prov.get("data_hash")}
        if costs is None:
            fails.append("the backtest has no trading costs")
        if not oos:
            fails.append("no out-of-sample period (set a holdout or use walk-forward selection)")
        if caus is False:
            fails.append("the look-ahead (causality) check failed")
        if not multi:
            fails.append("no multiple-testing control (PBO / deflated Sharpe) — run the research checks")
        m_ref = json.dumps({"owner": owner, "id": int(rid)})
        with _conn() as c:
            c.execute("UPDATE gov_models SET result_ref = ? WHERE id = ?", (m_ref, m["id"]))
            c.commit()
    elif gate == "G3":
        sh = shadow_report(m["id"])
        facts = {"shadow": {k: sh.get(k) for k in ("deployment_id", "sessions", "live", "backtest", "drift_flags", "reason")}}
        if not sh.get("available"):
            fails.append("no shadow trading yet: deploy the model to a Quant Lab paper trader (it must be at G2)")
        elif sh["sessions"] < sh["min_sessions"]:
            fails.append(f"shadow trading has {sh['sessions']} recorded sessions; {sh['min_sessions']} are needed")
        elif sh.get("drift_flags"):
            fails.append("signal drift: " + "; ".join(sh["drift_flags"]))
        if not m.get("max_loss_budget") or not m.get("retirement_criterion"):
            fails.append("set the model's maximum loss budget and retirement criterion first")
        if not m.get("allocation"):
            fails.append("set the model's risk allocation (capital) first")
    elif gate == "G4":
        st = settings()
        if st["stage"] not in LIVE_STAGES:
            fails.append(f"the fund is in {STAGES[st['stage']]}: no live capital until Phase II gates are met")
        with _conn() as c:
            tested = c.execute("SELECT COUNT(*) FROM gov_halts WHERE test = 1 AND ended_at IS NOT NULL").fetchone()[0]
            recon = c.execute("SELECT COUNT(*) FROM gov_reconciliations WHERE ok = 1 AND ts >= ?",
                              ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),)).fetchone()[0]
        facts = {"kill_switch_tests": tested, "clean_reconciliations_7d": recon}
        if not tested:
            fails.append("the kill switch has not been tested (start and lift a test halt)")
        if not recon:
            fails.append("no clean reconciliation in the last 7 days")
    return facts, fails


def signoff(mid: int, user: str, role: str, evidence: Optional[Dict[str, Any]] = None, note: str = "") -> Dict[str, Any]:
    """Record a sign-off towards the model's next gate; the model advances once every required sign-off is in.
    The model's owner cannot sign off; each sign-off is a different person in the required role."""
    init_db()
    evidence = evidence or {}
    with _conn() as c:
        m = _model_row(c, mid)
    if not m:
        raise LookupError("model not found")
    if m["status"] not in ("active",):
        raise ValueError(f"the model is {m['status']}")
    gate = _next_gate(m["gate"])
    if not gate:
        raise ValueError("the model is at the last gate")
    if user == m["owner"]:
        raise PermissionError("the model's owner cannot approve its own gate")
    have = _signoffs_for(m, gate)
    if user in {s["user"] for s in have}:
        raise PermissionError("you have already signed off this gate: another person must")
    needed = GATE_SIGNOFFS[gate]
    open_slots = [roles for i, roles in enumerate(needed) if i >= len(have)]
    if role not in open_slots[0] and role != "admin":
        raise PermissionError(f"{gate} ({GATE_INFO[gate]['authority']}) needs a sign-off by: {', '.join(sorted(open_slots[0]))}")
    required = GATE_INFO[gate]["evidence"]
    checks = evidence.get("checks") or {}
    missing = [e for e in required if not (checks.get(e) or {}).get("ok")]
    facts, fails = _auto_evidence(gate, m, evidence)
    auto_cover = {"G2": {"Costs and slippage": facts.get("costs_total") is not None,
                         "Multiple-testing control": facts.get("multiple_testing"),
                         "Walk-forward / out-of-sample": facts.get("out_of_sample"),
                         "Baseline comparison": facts.get("baseline")},
                  "G3": {"Time-stamped paper orders": bool((facts.get("shadow") or {}).get("sessions")),
                         "Signal-drift monitoring": (facts.get("shadow") or {}).get("live") is not None},
                  "G4": {"Kill switch tested": bool(facts.get("kill_switch_tests")),
                         "Reconciliations tested": bool(facts.get("clean_reconciliations_7d"))}}.get(gate, {})
    missing = [e for e in missing if not auto_cover.get(e)]
    if fails or missing:
        raise ValueError("; ".join(fails + ([f"evidence not confirmed: {', '.join(missing)}"] if missing else [])))
    with _conn() as c:
        c.execute("INSERT INTO gov_model_events (model_id, ts, user, role, action, gate_from, gate_to, evidence, note) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (mid, _now(), user, role, "signoff", m["gate"], gate,
                                                 json.dumps({"checks": checks, "facts": facts}, default=str), note[:2000]))
        c.commit()
    advanced = len(have) + 1 >= len(needed)
    if advanced:
        with _conn() as c:
            c.execute("UPDATE gov_models SET gate = ?, updated_at = ? WHERE id = ?", (gate, _now(), mid))
            c.execute("INSERT INTO gov_model_events (model_id, ts, user, role, action, gate_from, gate_to) VALUES (?,?,?,?,?,?,?)",
                      (mid, _now(), user, role, "advanced", m["gate"], gate))
            c.commit()
    _audit("model_gate_" + ("advanced" if advanced else "signoff"),
           f"Model #{mid} '{m['name']}': {GATE_INFO[gate]['name']} ({gate}) " + ("approved" if advanced else "signed off")
           + f" by {user} ({role})" + (f": {note}" if note else ""), user, f"model:{mid}", after=facts or None)
    return get_model(mid)


def close_model(mid: int, user: str, role: str, action: str, note: str) -> Dict[str, Any]:
    """Reject (a gate failed — kept in the research log), retire, suspend or reactivate a model."""
    init_db()
    if not note.strip():
        raise ValueError("a reason is required")
    status = {"reject": "rejected", "retire": "retired", "suspend": "suspended", "reactivate": "active"}.get(action)
    if not status:
        raise ValueError("action is reject, retire, suspend or reactivate")
    with _conn() as c:
        m = _model_row(c, mid)
        if not m:
            raise LookupError("model not found")
        if action == "reactivate" and user == m["owner"]:
            raise PermissionError("the owner cannot lift their own model's suspension")
        c.execute("UPDATE gov_models SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), mid))
        c.execute("INSERT INTO gov_model_events (model_id, ts, user, role, action, gate_from, note) VALUES (?,?,?,?,?,?,?)",
                  (mid, _now(), user, role, action, m["gate"], note[:2000]))
        c.commit()
    _audit(f"model_{status}", f"Model #{mid} '{m['name']}' {status} at {m['gate']}: {note}", user, f"model:{mid}")
    return get_model(mid)


def update_model(mid: int, user: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Risk allocation, loss budget, retirement criterion and book (before G3). Any change after G2 is a new version
    and sends the model back to G2 for re-approval (the frozen model is what was tested)."""
    init_db()
    allowed = {"allocation", "max_loss_budget", "retirement_criterion", "book", "mechanism", "dataset", "horizon"}
    ch = {k: v for k, v in fields.items() if k in allowed and v is not None}
    with _conn() as c:
        m = _model_row(c, mid)
        if not m:
            raise LookupError("model not found")
        research_change = {"mechanism", "dataset", "horizon"} & set(ch)
        sets = dict(ch)
        if research_change and GATES.index(m["gate"]) >= 2:
            sets.update(gate="G1", version=(m["version"] or 1) + 1)
        if not sets:
            return get_model(mid)
        sets["updated_at"] = _now()
        c.execute(f"UPDATE gov_models SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", [*sets.values(), mid])
        c.execute("INSERT INTO gov_model_events (model_id, ts, user, action, gate_from, gate_to, evidence) VALUES (?,?,?,?,?,?,?)",
                  (mid, _now(), user, "new_version" if "version" in sets else "updated", m["gate"], sets.get("gate", m["gate"]),
                   json.dumps(ch, default=str)))
        c.commit()
    _audit("model_updated", f"Model #{mid} updated: {sorted(ch)}" + (" — new version, back to G1 for re-approval"
                                                                   if "version" in sets else ""), user, f"model:{mid}")
    return get_model(mid)


def model_for_order(model_id: Optional[int]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """(model, refusal reason) for an order under the fund's rules."""
    st = settings()
    if model_id is None:
        return None, ("this fund requires every order to name an approved model (G3 shadow trading or later)"
                      if st["enabled"] and st["require_approved_model"] else None)
    init_db()
    with _conn() as c:
        m = _model_row(c, int(model_id))
    if not m:
        return None, "model not found"
    if m["status"] != "active":
        return m, f"model #{m['id']} is {m['status']}"
    if GATES.index(m["gate"]) < 3:
        return m, f"model #{m['id']} is at {m['gate']} ({GATE_INFO[m['gate']]['name']}): orders need G3 or later"
    return m, None


def model_for_deployment(model_id: Optional[int]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """A Quant Lab paper deployment in a governed fund is the model's shadow trading: it needs a model whose
    backtest was approved (G2) and that is active. Funds without governance deploy freely."""
    st = settings()
    if not st["enabled"]:
        return None, None
    if model_id is None:
        return None, ("this fund runs paper deployments only for governed models: name the model (approved at G2, "
                      "backtest) — the deployment becomes its shadow-trading record for G3")
    init_db()
    with _conn() as c:
        m = _model_row(c, int(model_id))
    if not m:
        return None, "model not found"
    if m["status"] != "active":
        return m, f"model #{m['id']} is {m['status']}"
    if GATES.index(m["gate"]) < 2:
        return m, f"model #{m['id']} is at {m['gate']}: its backtest must be approved (G2) before shadow trading"
    return m, None


def record_deployment(model_id: int, deployment_id: int, user: str) -> None:
    """Log that a model has started shadow trading through a paper deployment."""
    init_db()
    with _conn() as c:
        c.execute("INSERT INTO gov_model_events (model_id, ts, user, action, gate_from, evidence) VALUES (?,?,?,?,?,?)",
                  (model_id, _now(), user, "shadow_deployed", (_model_row(c, model_id) or {}).get("gate"),
                   json.dumps({"deployment_id": deployment_id})))
        c.commit()
    _audit("model_shadow_deployed", f"Model #{model_id}: paper deployment #{deployment_id} started (shadow trading)",
           user, f"model:{model_id}")


def shadow_report(model_id: int, min_sessions: int = 20) -> Dict[str, Any]:
    """The model's shadow-trading record from its Quant Lab paper deployment(s) in this fund: sessions recorded
    (each time-stamped when locked), live vs backtest return and volatility, and drift flags."""
    from api import funds
    from api.quant import store
    deps = [d for d in store.list_deployments(active_only=False)
            if d.get("model_id") == model_id and (d.get("fund") or "main") == funds.current()]
    if not deps:
        return {"available": False, "reason": "no paper deployment linked to this model in this fund"}
    d = sorted(deps, key=lambda x: x["id"])[-1]
    live = store.live_returns(d["id"])
    rets = [v[0] for _, v in sorted(live.items())]
    n = len(rets)
    bt = d.get("backtest") or {}
    if isinstance(bt, str):
        try:
            bt = json.loads(bt)
        except ValueError:
            bt = {}
    out: Dict[str, Any] = {"available": True, "deployment_id": d["id"], "name": d["name"], "active": bool(d.get("active")),
                           "deployed_at": d.get("deployed_at"), "sessions": n, "min_sessions": min_sessions,
                           "backtest": {k: bt.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown")}}
    if n >= 5:
        mu = sum(rets) / n
        sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
        vol = sd * math.sqrt(252)
        sharpe = (mu / sd * math.sqrt(252)) if sd else None
        eq, peak, mdd = 1.0, 1.0, 0.0
        for r in rets:
            eq *= 1 + r
            peak = max(peak, eq)
            mdd = min(mdd, eq / peak - 1)
        flags = []
        bvol, bsh = bt.get("vol"), bt.get("sharpe")
        if bvol and vol and not (0.5 <= vol / bvol <= 2.0):
            flags.append(f"live volatility {vol:.1%} vs backtest {bvol:.1%} (ratio {vol / bvol:.2f}, outside 0.5–2)")
        if bsh is not None and sharpe is not None and sharpe < bsh - 2 * math.sqrt(252 / n):
            flags.append(f"live Sharpe {sharpe:.2f} below backtest {bsh:.2f} by more than two standard errors")
        out["live"] = {"return": round(eq - 1, 4), "vol": round(vol, 4), "sharpe": round(sharpe, 2) if sharpe is not None else None,
                       "max_drawdown": round(mdd, 4), "first": min(live), "last": max(live)}
        out["drift_flags"] = flags
    out["ready"] = n >= min_sessions and not out.get("drift_flags")
    return out


# ── halts and incidents ──────────────────────────────────────────────────────
def active_halt() -> Optional[Dict[str, Any]]:
    """The active trading halt, or None."""
    init_db()
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_halts WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def open_incident(kind: str, description: str, user: str = "system", severity: str = "high") -> int:
    """Log an operational incident; returns its id."""
    init_db()
    with _conn() as c:
        cur = c.execute("INSERT INTO gov_incidents (ts, kind, severity, description, reported_by) VALUES (?,?,?,?,?)",
                        (_now(), kind, severity, description[:2000], user))
        c.commit()
        iid = int(cur.lastrowid)
    _audit("incident_opened", f"Incident #{iid} ({kind}): {description}", user, f"incident:{iid}")
    return iid


def start_halt(kind: str, reason: str, user: str = "system", test: bool = False) -> Dict[str, Any]:
    """Stop new orders, approvals and executions. Opens an incident unless it is a kill-switch test."""
    init_db()
    cur_h = active_halt()
    if cur_h:
        return cur_h
    iid = None if test else open_incident(kind, reason, user)
    with _conn() as c:
        c.execute("INSERT INTO gov_halts (active, kind, reason, started_at, started_by, incident_id, test) VALUES (1,?,?,?,?,?,?)",
                  (kind, reason[:1000], _now(), user, iid, 1 if test else 0))
        c.commit()
    _audit("execution_halted", f"Execution halted ({'test' if test else kind}): {reason}", user, "controls")
    return active_halt()


def lift_halt(user: str, resolution: str) -> Dict[str, Any]:
    """Resume trading: needs a written resolution; an incident halt needs its incident fixed and signed off by
    someone other than the person who fixed it."""
    h = active_halt()
    if not h:
        raise ValueError("no active halt")
    if not resolution.strip():
        raise ValueError("a written resolution is required")
    if h.get("incident_id"):
        with _conn() as c:
            inc = dict(c.execute("SELECT * FROM gov_incidents WHERE id = ?", (h["incident_id"],)).fetchone())
        if inc["status"] != "signed_off":
            raise ValueError(f"incident #{inc['id']} must be fixed and independently signed off before trading resumes")
    with _conn() as c:
        c.execute("UPDATE gov_halts SET active = 0, ended_at = ?, ended_by = ?, resolution = ? WHERE id = ?",
                  (_now(), user, resolution[:2000], h["id"]))
        c.commit()
    _audit("execution_resumed", f"Execution resumed: {resolution}", user, "controls")
    return {**h, "active": 0, "ended_by": user, "resolution": resolution}


def incidents(open_only: bool = False) -> List[Dict[str, Any]]:
    """Incidents, newest first; `open_only` excludes signed-off ones."""
    init_db()
    with _conn() as c:
        q = "SELECT * FROM gov_incidents" + (" WHERE status != 'signed_off'" if open_only else "") + " ORDER BY id DESC"
        return [dict(r) for r in c.execute(q)]


def fix_incident(iid: int, user: str, fix: str) -> Dict[str, Any]:
    """Record how an incident was fixed and tested.

    Raises:
        ValueError: no description.
    """
    if not fix.strip():
        raise ValueError("describe the fix and how it was tested")
    with _conn() as c:
        c.execute("UPDATE gov_incidents SET status = 'fixed', fix = ?, fixed_by = ? WHERE id = ?", (fix[:2000], user, iid))
        c.commit()
    _audit("incident_fixed", f"Incident #{iid} fixed: {fix}", user, f"incident:{iid}")
    return next(i for i in incidents() if i["id"] == iid)


def signoff_incident(iid: int, user: str) -> Dict[str, Any]:
    """Independently sign off a fixed incident.

    Raises:
        LookupError: no such incident.
        ValueError: not fixed yet.
        PermissionError: the signer fixed it.
    """
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_incidents WHERE id = ?", (iid,)).fetchone()
        if not r:
            raise LookupError("incident not found")
        if r["status"] != "fixed":
            raise ValueError("record the fix first")
        if r["fixed_by"] == user:
            raise PermissionError("independent sign-off: someone other than the person who fixed it")
        c.execute("UPDATE gov_incidents SET status = 'signed_off', signed_off_by = ?, signed_off_at = ? WHERE id = ?",
                  (user, _now(), iid))
        c.commit()
    _audit("incident_signed_off", f"Incident #{iid} signed off", user, f"incident:{iid}")
    return next(i for i in incidents() if i["id"] == iid)


# ── reconciliation ───────────────────────────────────────────────────────────
def reconcile(user: str = "system", halt_on_break: bool = True) -> Dict[str, Any]:
    """Positions against the trade ledger: each position's quantity must equal its last fill's position-after
    (times any split applied since). A break opens an incident and halts execution. Cash comes from the same ledger
    — reconciling it to a broker cash statement needs a broker connection (reported, not assumed)."""
    from api import blotter_store, corporate_actions as ca, portfolio_store
    blotter_store.init_db()
    ca.init_db()
    init_db()
    pos = portfolio_store.list_positions(None)
    with _conn() as c:
        trades = [dict(r) for r in c.execute("SELECT id, ts, book, symbol, position_after FROM trades ORDER BY id")]
        applied = [dict(r) for r in c.execute("SELECT book, symbol, ex_date, ratio, applied_at FROM corporate_actions")]
    last: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for t in trades:
        last[(t["book"], str(t["symbol"]).upper())] = t
    held: Dict[Tuple[str, str], float] = {}
    for p in pos:
        k = (p.get("book") or "Macro", str(p["symbol"]).upper())
        held[k] = held.get(k, 0.0) + float(p["quantity"])
    breaks, unverified = [], []
    for k in sorted(set(held) | set(last)):
        q = held.get(k, 0.0)
        t = last.get(k)
        if not t:
            unverified.append({"book": k[0], "symbol": k[1], "quantity": q,
                               "note": "opening position loaded without fills: no ledger to reconcile against"})
            continue
        f = 1.0
        for a in applied:
            if (a["book"], a["symbol"].upper()) == k and str(a["applied_at"]) > str(t["ts"]):
                f *= float(a["ratio"])
        exp = float(t["position_after"] or 0) * f
        if abs(q - exp) > 1e-6 * max(1.0, abs(exp)):
            breaks.append({"book": k[0], "symbol": k[1], "positions": q, "ledger": exp, "difference": q - exp,
                           "last_fill": t["id"]})
    ok = not breaks
    notes = ("Cash is ledger-derived (capital + realised − costs − cost of holdings); no broker cash statement is "
             "connected, so cash is not independently reconciled.")
    with _conn() as c:
        cur = c.execute("INSERT INTO gov_reconciliations (ts, ok, checked, breaks, notes, run_by) VALUES (?,?,?,?,?,?)",
                        (_now(), 1 if ok else 0, len(set(held) | set(last)), json.dumps(breaks), notes, user))
        c.commit()
        rid = int(cur.lastrowid)
    if not ok and halt_on_break and settings()["enabled"]:
        start_halt("reconciliation", f"Reconciliation #{rid}: {len(breaks)} position break(s) "
                                     + ", ".join(f"{b['symbol']} ({b['book']})" for b in breaks[:5]), user)
    return {"id": rid, "ok": ok, "checked": len(set(held) | set(last)), "breaks": breaks, "unverified": unverified,
            "notes": notes}


def reconciliations(limit: int = 30) -> List[Dict[str, Any]]:
    """The latest position-vs-ledger reconciliations."""
    init_db()
    with _conn() as c:
        return [{**dict(r), "breaks": json.loads(r["breaks"] or "[]")} for r in
                c.execute("SELECT * FROM gov_reconciliations ORDER BY id DESC LIMIT ?", (limit,))]


# ── risk policy checks ───────────────────────────────────────────────────────
def daily_loss(nav_now: Optional[float]) -> Optional[float]:
    """Today's change in NAV against the last snapshot before today (fraction; negative = loss)."""
    from api import fund_store
    rows = [r for r in fund_store.nav_history() if r["date"] < date.today().isoformat()]
    if not rows or not nav_now or not rows[-1].get("nav"):
        return None
    return nav_now / float(rows[-1]["nav"]) - 1


def risk_shares(positions: List[Dict[str, Any]], base: str) -> Dict[str, Any]:
    """Each model book's and each theme's share of ex-ante portfolio risk (Euler contributions, 1y daily
    covariance of base-currency returns). positions: [{symbol, book, market_value}] in base."""
    import numpy as np
    from api.calculations import benchmark as bm
    syms = sorted({p["symbol"] for p in positions if p.get("market_value")})
    if len(syms) == 0:
        return {"available": False}
    R = bm.returns_in_base(syms, base).dropna().tail(252)
    if len(R) < 60:
        return {"available": False, "reason": "under 60 sessions of common history"}
    cols = list(R.columns)
    cov = np.cov(R.to_numpy(), rowvar=False) if len(cols) > 1 else np.array([[float(R.iloc[:, 0].var())]])
    mv = {s: 0.0 for s in cols}
    for p in positions:
        if p["symbol"] in mv:
            mv[p["symbol"]] += float(p["market_value"] or 0)
    w = np.array([mv[s] for s in cols])
    tot = float(w @ cov @ w)
    if tot <= 0:
        return {"available": False}
    contrib = {s: float(w[i] * (cov @ w)[i] / tot) for i, s in enumerate(cols)}
    by_book: Dict[str, float] = {}
    by_theme: Dict[str, float] = {}
    for p in positions:
        s = p["symbol"]
        if s not in contrib or not mv[s]:
            continue
        share = contrib[s] * float(p["market_value"] or 0) / mv[s]
        by_book[p.get("book") or "—"] = by_book.get(p.get("book") or "—", 0.0) + share
        th = (instrument(s) or {}).get("theme") or "unclassified"
        by_theme[th] = by_theme.get(th, 0.0) + share
    return {"available": True, "by_book": by_book, "by_theme": by_theme}


def order_controls(symbol: str, signed_qty: float, price: Optional[float], nav: Optional[float],
                   gross_after: Optional[float], price_date: Optional[str] = None,
                   shares_after: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The fund's pre-trade rules for one order → [{level BLOCK|WARN, rule, message}] (empty when governance is off)."""
    st = settings()
    if not st["enabled"]:
        return []
    pol = st["risk_policy"]
    out: List[Dict[str, Any]] = []
    sym = symbol.strip().upper()
    h = active_halt()
    if h:
        out.append({"level": "BLOCK", "rule": "halt", "message": f"Execution halted ({h['kind']}): {h['reason']}"})
    ins = instrument(sym)
    if not ins or ins["status"] != "approved":
        out.append({"level": "BLOCK", "rule": "approved_instruments",
                    "message": f"{sym} is not on the approved-instruments list" + (f" ({ins['status']})" if ins else "")})
    elif not ins["tradable"]:
        out.append({"level": "BLOCK", "rule": "approved_instruments",
                    "message": f"{sym} is approved as a research / signal series only, not for trading"})
    if signed_qty < 0 and not pol["allow_short"]:
        from api import portfolio_store
        held = sum(float(p["quantity"]) for p in portfolio_store.list_positions(None) if str(p["symbol"]).upper() == sym)
        if held + signed_qty < -1e-9:
            out.append({"level": "BLOCK", "rule": "no_short",
                        "message": f"Short selling (borrowing stock) is not permitted: holding {held:g}, selling {-signed_qty:g}"})
    if gross_after is not None and gross_after > pol["max_gross_leverage"] + 1e-9:
        out.append({"level": "BLOCK", "rule": "no_leverage",
                    "message": f"Gross exposure after the order {gross_after:.1%} of NAV exceeds {pol['max_gross_leverage']:.0%} (no borrowing)"})
    if price and nav and abs(signed_qty) * price > pol["max_order_pct_nav"] * nav:
        out.append({"level": "BLOCK", "rule": "order_size",
                    "message": f"Order notional {abs(signed_qty) * price / nav:.1%} of NAV exceeds the {pol['max_order_pct_nav']:.0%} order limit"})
    if price_date:
        age = (date.today() - date.fromisoformat(price_date[:10])).days
        if age > pol["max_price_age_days"]:
            out.append({"level": "BLOCK", "rule": "price_feed",
                        "message": f"Last price is from {price_date[:10]} ({age} days old): price feed stale"})
    dl = daily_loss(nav)
    if dl is not None and dl <= -pol["daily_loss_pause"]:
        out.append({"level": "BLOCK", "rule": "daily_loss",
                    "message": f"Today's loss {dl:.2%} reached the {pol['daily_loss_pause']:.0%} pause: no new orders today"})
    if shares_after and shares_after.get("available"):
        for b, v in shares_after["by_book"].items():
            if len(shares_after["by_book"]) > 1 and v > pol["max_model_risk_share"]:
                out.append({"level": "WARN", "rule": "model_risk_share",
                            "message": f"Book '{b}' would carry {v:.0%} of ex-ante risk (limit {pol['max_model_risk_share']:.0%}): risk sign-off"})
        for t, v in shares_after["by_theme"].items():
            if len(shares_after["by_theme"]) > 1 and v > pol["max_theme_risk_share"]:
                out.append({"level": "WARN", "rule": "theme_risk_share",
                            "message": f"Theme '{t}' would carry {v:.0%} of ex-ante risk (limit {pol['max_theme_risk_share']:.0%}): risk sign-off"})
    return out


def price_band_check(price: Optional[float], last_close: Optional[float]) -> Optional[Dict[str, Any]]:
    """A BLOCK finding when a fill price is further from the last close than the policy's price band (governed funds
    only), else None.
    """
    st = settings()
    if not st["enabled"] or not price or not last_close:
        return None
    band = st["risk_policy"]["price_band"]
    dev = price / last_close - 1
    if abs(dev) > band:
        return {"level": "BLOCK", "rule": "price_band",
                "message": f"Fill price {price:g} is {dev:+.1%} from the last close {last_close:g} (band ±{band:.0%})"}
    return None


# ── model P&L and strategy drawdown ──────────────────────────────────────────
def model_pnl_today() -> Dict[int, float]:
    """Each active model's P&L to date in base currency: realised in its book plus unrealised of its holdings."""
    from api.handlers.portfolio_analytics import book_in_base
    out = {}
    for m in list_models(include_closed=False):
        if not m.get("book"):
            continue
        bk = book_in_base(m["book"])
        unreal = sum(float(p.get("unrealized_pnl") or 0) for p in bk["positions"])
        with _conn() as c:
            rows = c.execute("SELECT realized_pnl, commission, taxes, usd_per_unit, base_per_usd FROM trades WHERE book = ?",
                             (m["book"],)).fetchall()
        real = 0.0
        for r in rows:
            k = (r["usd_per_unit"] or 1.0) * (r["base_per_usd"] or 1.0)
            real += (float(r["realized_pnl"] or 0) - float(r["commission"] or 0) - float(r["taxes"] or 0)) * k
        out[m["id"]] = real + unreal
    return out


def record_model_pnl() -> List[Dict[str, Any]]:
    """Daily (with the NAV snapshot): record each model's P&L, update its high-water mark, and review / suspend it
    when the drawdown from the high-water mark reaches the policy levels (as a fraction of its allocation)."""
    init_db()
    pol = settings()["risk_policy"]
    today = date.today().isoformat()
    actions = []
    for mid, pnl in model_pnl_today().items():
        with _conn() as c:
            c.execute("INSERT INTO gov_model_pnl (model_id, date, pnl) VALUES (?,?,?) ON CONFLICT(model_id, date) DO UPDATE "
                      "SET pnl = excluded.pnl", (mid, today, pnl))
            m = _model_row(c, mid)
            hwm = max(float(m.get("hwm") or 0.0), pnl)
            c.execute("UPDATE gov_models SET hwm = ? WHERE id = ?", (hwm, mid))
            c.commit()
        alloc = float(m.get("allocation") or 0)
        if alloc <= 0:
            continue
        dd = (hwm - pnl) / alloc
        if dd >= pol["strategy_dd_suspend"] and m["status"] == "active":
            close_model(mid, "system", "risk", "suspend",
                        f"drawdown {dd:.1%} of allocation from the high-water mark ≥ {pol['strategy_dd_suspend']:.0%}")
            actions.append({"model": mid, "action": "suspended", "drawdown": dd})
        elif dd >= pol["strategy_dd_review"]:
            open_incident("strategy_drawdown", f"Model #{mid} '{m['name']}' drawdown {dd:.1%} of allocation: review "
                                               f"(suspends at {pol['strategy_dd_suspend']:.0%})", severity="medium")
            actions.append({"model": mid, "action": "review", "drawdown": dd})
    return actions


# ── budget ───────────────────────────────────────────────────────────────────
def budget(period: Optional[str] = None) -> Dict[str, Any]:
    """Budget lines with spent and remaining per category, the expense ledger, totals and unbudgeted categories."""
    init_db()
    with _conn() as c:
        lines = [dict(r) for r in c.execute("SELECT * FROM gov_budget" + (" WHERE period = ?" if period else "") +
                                            " ORDER BY id", (period,) if period else ())]
        exp = [dict(r) for r in c.execute("SELECT * FROM gov_expenses ORDER BY date DESC, id DESC")]
    spent: Dict[str, float] = {}
    for e in exp:
        spent[e["category"]] = spent.get(e["category"], 0.0) + float(e["amount"] or 0)
    rows = [{**l, "spent": round(spent.get(l["category"], 0.0), 2),
             "remaining": round(float(l["amount"] or 0) - spent.get(l["category"], 0.0), 2)} for l in lines]
    total_b = sum(float(l["amount"] or 0) for l in lines)
    total_s = sum(spent.values())
    return {"lines": rows, "expenses": exp, "total_budget": round(total_b, 2), "total_spent": round(total_s, 2),
            "variance": round(total_b - total_s, 2), "unbudgeted": sorted(set(spent) - {l["category"] for l in lines})}


def add_expense(user: str, d: str, category: str, amount: float, currency: str, description: str) -> Dict[str, Any]:
    """Record an expense against a budget category."""
    init_db()
    if amount <= 0:
        raise ValueError("amount must be positive")
    with _conn() as c:
        c.execute("INSERT INTO gov_expenses (date, category, amount, currency, description, recorded_by) VALUES (?,?,?,?,?,?)",
                  (d, category[:80], amount, currency.upper()[:3], description[:500], user))
        c.commit()
    _audit("expense_recorded", f"Expense {currency} {amount:,.2f} ({category}): {description}", user, "budget")
    return budget()


def approve_expense(eid: int, user: str) -> Dict[str, Any]:
    """Approve an expense (not by the person who recorded it)."""
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_expenses WHERE id = ?", (eid,)).fetchone()
        if not r:
            raise LookupError("expense not found")
        if r["recorded_by"] == user:
            raise PermissionError("spending authority: another person approves the expense")
        c.execute("UPDATE gov_expenses SET approved_by = ?, approved_at = ? WHERE id = ?", (user, _now(), eid))
        c.commit()
    _audit("expense_approved", f"Expense #{eid} approved", user, "budget")
    return budget()


# ── milestones ───────────────────────────────────────────────────────────────
def milestones() -> List[Dict[str, Any]]:
    """The roadmap milestones."""
    init_db()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM gov_milestones ORDER BY (plan != 'First 90 days'), sort, id")]


def update_milestone(mid: int, user: str, status: str, evidence: str = "") -> Dict[str, Any]:
    """Change a milestone's status; `done` needs evidence.

    Raises:
        ValueError: invalid status or missing evidence.
    """
    if status not in ("open", "in_progress", "done", "blocked"):
        raise ValueError("status is open, in_progress, done or blocked")
    if status == "done" and not evidence.strip():
        raise ValueError("record the evidence that meets the acceptance criterion")
    with _conn() as c:
        c.execute("UPDATE gov_milestones SET status = ?, evidence = COALESCE(NULLIF(?, ''), evidence), updated_by = ?, "
                  "updated_at = ? WHERE id = ?", (status, evidence[:2000], user, _now(), mid))
        c.commit()
    _audit("milestone_updated", f"Milestone #{mid} → {status}" + (f": {evidence}" if evidence else ""), user, f"milestone:{mid}")
    return next(m for m in milestones() if m["id"] == mid)


def signoff_milestone(mid: int, user: str) -> Dict[str, Any]:
    """Sign off a completed milestone (not by the person who completed it)."""
    with _conn() as c:
        r = c.execute("SELECT * FROM gov_milestones WHERE id = ?", (mid,)).fetchone()
        if not r:
            raise LookupError("milestone not found")
        if r["status"] != "done":
            raise ValueError("only a completed milestone can be signed off")
        if r["updated_by"] == user:
            raise PermissionError("sign-off by someone other than the person who completed it")
        c.execute("UPDATE gov_milestones SET signed_off_by = ? WHERE id = ?", (user, mid))
        c.commit()
    _audit("milestone_signed_off", f"Milestone #{mid} signed off", user, f"milestone:{mid}")
    return next(m for m in milestones() if m["id"] == mid)


# ── break-even AUM (management fees only) ────────────────────────────────────
def break_even(costs: List[float], fees: List[float], aums: List[float]) -> Dict[str, Any]:
    """Break-even AUM = recurring operating cash cost ÷ management-fee rate (excludes performance fees, tax and fee
    discounts), and fee income / surplus at each AUM for the first cost."""
    return {"thresholds": [{"cost": c, **{f"{f:.3%}": round(c / f, 2) for f in fees}} for c in costs],
            "grid": [{"aum": a, **{f"{f:.3%}": {"income": round(a * f, 2), "surplus": round(a * f - costs[0], 2)}
                                   for f in fees}} for a in aums],
            "formula": "break-even AUM = recurring operating cash cost / annual management-fee rate"}


# ── data-source licence register ─────────────────────────────────────────────
# The plan: "Some public data is free to research but not to redistribute or use commercially without conditions.
# Check each data supplier's licence before publishing outputs or using datasets in a fund." Each source the platform
# uses is listed with its type and the usual position for that type of provider — a starting point, not legal advice;
# every source starts 'unreviewed' until someone in the fund records a decision against the provider's actual terms.
SOURCE_TYPES = {
    "public": "Public-sector statistics: generally reusable with attribution, but individual series can carry "
              "third-party copyright notices (check the series' notes).",
    "commercial_site": "Commercial website / unofficial access: site terms usually allow personal use only; using it "
                       "in a fund, redistributing or publishing outputs normally needs a licence.",
    "academic": "Academic research dataset: usually free with citation; check the authors' stated terms for "
                "commercial use.",
    "association": "Member association / exchange statistics: copyright of the provider; redistribution and commercial "
                   "use usually restricted.",
}
DATA_SOURCES = [
    ("FRED (St. Louis Fed)", "Federal Reserve Bank of St. Louis", "public", "most macro series", "https://fred.stlouisfed.org"),
    ("ALFRED vintages", "Federal Reserve Bank of St. Louis", "public", "point-in-time releases, event dataset", "https://alfred.stlouisfed.org"),
    ("Yahoo Finance prices (via yfinance)", "Yahoo", "commercial_site", "prices, volumes, fund data, quotes", "https://finance.yahoo.com"),
    ("SEC EDGAR (filings, XBRL, 13F)", "US Securities and Exchange Commission", "public", "fundamentals, institutions", "https://www.sec.gov/edgar"),
    ("TreasuryDirect (FedInvest prices, auctions)", "US Treasury", "public", "Treasury board, auctions", "https://www.treasurydirect.gov"),
    ("CFTC Commitments of Traders", "Commodity Futures Trading Commission", "public", "COT positioning", "https://www.cftc.gov"),
    ("Federal Reserve Board data (EBP, GSW curve, FOMC calendar)", "Board of Governors of the Federal Reserve", "public",
     "credit stress, curve, FOMC dates", "https://www.federalreserve.gov"),
    ("NY Fed Staff Nowcast", "Federal Reserve Bank of New York", "public", "GDP nowcast", "https://www.newyorkfed.org"),
    ("Caldara–Iacoviello geopolitical risk index", "Caldara & Iacoviello", "academic", "geopolitical risk", "https://www.matteoiacoviello.com/gpr.htm"),
    ("Shiller CAPE data", "Robert Shiller", "academic", "valuation", "http://www.econ.yale.edu/~shiller/data.htm"),
    ("Kenneth French data library", "Kenneth R. French", "academic", "factor returns", "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"),
    ("AAII sentiment survey", "American Association of Individual Investors", "association", "sentiment", "https://www.aaii.com"),
    ("Cboe put/call ratios", "Cboe Global Markets", "association", "options context", "https://www.cboe.com"),
    ("Nasdaq IPO calendar", "Nasdaq", "commercial_site", "IPO calendar", "https://www.nasdaq.com"),
    ("Economic calendar consensus feed (Forex Factory)", "Forex Factory", "commercial_site", "recent consensus forecasts", "https://www.forexfactory.com"),
]


def data_sources() -> List[Dict[str, Any]]:
    """The data-licence register, seeded with every source the platform uses."""
    init_db()
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS gov_data_sources (
            name TEXT PRIMARY KEY, provider TEXT, type TEXT, feeds TEXT, url TEXT, status TEXT DEFAULT 'unreviewed',
            terms_reference TEXT, note TEXT, reviewed_by TEXT, reviewed_at TEXT)""")
        have = {r[0] for r in c.execute("SELECT name FROM gov_data_sources")}
        for name, prov, typ, feeds, url in DATA_SOURCES:
            if name not in have:
                c.execute("INSERT INTO gov_data_sources (name, provider, type, feeds, url) VALUES (?,?,?,?,?)",
                          (name, prov, typ, feeds, url))
        c.commit()
        rows = [dict(r) for r in c.execute("SELECT * FROM gov_data_sources ORDER BY type, name")]
    for r in rows:
        r["type_note"] = SOURCE_TYPES.get(r["type"])
    return rows


def review_source(name: str, user: str, status: str, terms_reference: str, note: str = "") -> Dict[str, Any]:
    """Record the fund's decision on a source after reading its terms: allowed / restricted / not_allowed."""
    if status not in ("allowed", "restricted", "not_allowed", "unreviewed"):
        raise ValueError("status is allowed, restricted, not_allowed or unreviewed")
    if status != "unreviewed" and not terms_reference.strip():
        raise ValueError("cite the terms you reviewed (URL or document and date)")
    data_sources()
    with _conn() as c:
        if not c.execute("SELECT 1 FROM gov_data_sources WHERE name = ?", (name,)).fetchone():
            raise LookupError("source not found")
        c.execute("UPDATE gov_data_sources SET status = ?, terms_reference = ?, note = ?, reviewed_by = ?, reviewed_at = ? "
                  "WHERE name = ?", (status, terms_reference[:500], note[:1000], user, _now(), name))
        c.commit()
    _audit("data_source_reviewed", f"Data source '{name}': {status} ({terms_reference})", user, f"source:{name}")
    return next(r for r in data_sources() if r["name"] == name)
