"""
Positions and tiers, per fund: who does what in each organisation, and what the platform lets them do there.

A position (e.g. "Head of Trading") belongs to one fund and has
  tier          1 Leadership · 2 Function heads · 3 Members · 4 Observers / trainees
  base_role     the platform role it acts as in that fund: pm | risk | analyst | quant | viewer (read-only)
  capabilities  the actions it may take (checked by the endpoints below, on top of the role)
  panels        its workspace: the panels shown first on My Desk and in the sidebar

A person is assigned a position per fund — one can be Head of Trading at BIFS and Quant lead at Moriah. In a fund where
a person holds a position, their role and capabilities there come from it; without one, their account role applies
(unchanged behaviour). Platform administrators keep full access everywhere.

Templates: Moriah Capital Partners from its plan's organisation table (managing partner / operations, head of research,
quant engineering & execution, risk & controls, finance / independent assurance) plus analyst and advisor seats; BIFS
as a student investment society (chair, head of trading, CIO / PMC, head of risk, sector heads, analysts, quant,
treasurer, trainees, alumni advisors). Both are starting points the fund edits.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from api.portfolio_store import _conn

TIERS = {1: "Leadership", 2: "Function heads", 3: "Members", 4: "Observers & trainees"}
BASE_ROLES = ("pm", "risk", "analyst", "quant", "viewer")

CAPABILITIES: Dict[str, str] = {
    "view_book": "See the book, NAV, risk and reports",
    "pretrade_desk": "Run pre-trade feasibility assessments",
    "propose_orders": "Raise order tickets",
    "approve_orders": "Approve orders (four-eyes, risk)",
    "execute_orders": "Execute approved orders",
    "pitch_submit": "Write and submit analyst pitches",
    "pitch_decide": "Record PMC / investment-committee decisions on pitches",
    "model_propose": "Propose research models (G0)",
    "model_signoff_research": "Sign off research gates (G1 data approval)",
    "model_signoff_ic": "Sign off investment-committee gates (G2 backtest, G4, G5)",
    "model_signoff_risk": "Sign off risk gates (G3 shadow trading, G4)",
    "quant_deploy": "Deploy strategies to paper traders",
    "instruments_approve": "Approve instruments for trading",
    "halt_trading": "Halt execution (kill switch)",
    "resume_trading": "Resume trading after a halt",
    "incidents_signoff": "Independently sign off incidents",
    "reconcile": "Run reconciliations",
    "budget_record": "Record expenses",
    "budget_approve": "Approve expenses (spending authority)",
    "milestones_signoff": "Sign off milestones",
    "data_licences_review": "Record data-licence decisions",
    "fund_settings": "Change fund settings, mandate and limits",
    "manage_positions": "Create positions and assign people",
}

ALL_CAPS = set(CAPABILITIES)
# what each platform role may do when the person holds no position in the fund (today's behaviour)
ROLE_DEFAULT_CAPS: Dict[str, Set[str]] = {
    "admin": ALL_CAPS,
    "pm": {"view_book", "pretrade_desk", "propose_orders", "execute_orders", "pitch_submit", "pitch_decide", "model_propose",
           "model_signoff_research", "model_signoff_ic", "quant_deploy", "instruments_approve", "halt_trading",
           "incidents_signoff", "reconcile", "budget_record", "budget_approve", "milestones_signoff", "data_licences_review"},
    "risk": {"view_book", "pretrade_desk", "approve_orders", "model_signoff_research", "model_signoff_risk", "instruments_approve",
             "halt_trading", "resume_trading", "incidents_signoff", "reconcile", "budget_record", "milestones_signoff",
             "data_licences_review", "fund_settings"},
    "analyst": {"view_book", "pretrade_desk", "propose_orders", "pitch_submit", "model_propose", "model_signoff_research",
                "reconcile", "budget_record"},
    "quant": {"view_book", "pretrade_desk", "propose_orders", "model_propose", "model_signoff_research", "quant_deploy",
              "reconcile", "budget_record"},
    "viewer": {"view_book"},
}

_W = {  # workspaces (panel ids)
    "lead": ["fund-governance", "fund-cockpit", "my-desk", "performance-attribution", "trade-lifecycle", "pitch-review"],
    "trading": ["pretrade-desk", "trade-lifecycle", "trade-workflow", "portfolio-positions", "fund-cockpit", "pitch-review"],
    "research": ["event-dataset", "macro-model", "economic-calendar", "stock-ideas", "pitch-review", "fund-governance"],
    "quant": ["quant-lab", "strategy-lab", "event-dataset", "signal-scorecard", "factor-validation", "fund-governance"],
    "risk": ["fund-governance", "fund-cockpit", "var-stress", "risk-analytics", "factor-exposure", "trade-lifecycle"],
    "finance": ["fund-governance", "fund-cockpit", "performance-attribution", "trade-lifecycle"],
    "analyst": ["stock-ideas", "pitch-review", "equity-research", "economic-calendar", "event-dataset"],
    "observer": ["fund-governance", "fund-cockpit", "macro-model", "event-dataset"],
}

T = Dict[str, Any]


def _p(key: str, title: str, tier: int, base: str, caps: Set[str], panels: List[str], desc: str, seats: int = 1) -> T:
    return {"key": key, "title": title, "tier": tier, "base_role": base, "capabilities": sorted(caps),
            "panels": panels, "description": desc, "seats": seats}


VIEW = {"view_book"}
TEMPLATES: Dict[str, List[T]] = {
    "moriah": [
        _p("managing_partner", "Managing Partner / Operations", 1, "pm",
           ALL_CAPS - {"approve_orders", "resume_trading", "model_signoff_risk"}, _W["lead"],
           "Strategy, budget, investor communications, legal and vendor co-ordination; chairs the investment committee."),
        _p("head_of_research", "Head of Research", 2, "analyst",
           VIEW | {"pretrade_desk", "pitch_submit", "pitch_decide", "model_propose", "model_signoff_research", "model_signoff_ic",
                   "data_licences_review", "budget_record", "milestones_signoff"}, _W["research"],
           "Economic hypothesis selection, data and research quality control; research lead at G0–G1, IC member."),
        _p("quant_engineering", "Quant Engineering & Execution Lead", 2, "quant",
           VIEW | {"pretrade_desk", "propose_orders", "model_propose", "quant_deploy", "reconcile", "budget_record"},
           _W["quant"], "Infrastructure, model deployment, broker interfaces, audit logs."),
        _p("risk_controls", "Risk & Controls Lead", 2, "risk",
           VIEW | {"pretrade_desk", "approve_orders", "model_signoff_risk", "instruments_approve", "halt_trading", "resume_trading",
                   "incidents_signoff", "reconcile", "milestones_signoff", "fund_settings"}, _W["risk"],
           "Limits, reconciliations, model-approval challenge and incident handling — independent of strategy builders."),
        _p("finance_assurance", "Finance & Independent Assurance", 3, "viewer",
           VIEW | {"budget_record", "budget_approve", "reconcile", "incidents_signoff"}, _W["finance"],
           "Accounts, expenses, tax co-ordination and later NAV / audit support (outsourced as needed)."),
        _p("research_analyst", "Research Analyst", 3, "analyst",
           VIEW | {"pretrade_desk", "pitch_submit", "model_propose", "budget_record"}, _W["analyst"],
           "Event datasets, hypotheses and research notes under the head of research.", seats=3),
        _p("advisor", "Advisor / Observer", 4, "viewer", VIEW, _W["observer"],
           "Independent review and challenge; read-only.", seats=3),
    ],
    "bifs": [
        _p("chair", "Fund Chair / President", 1, "pm",
           VIEW | {"pitch_decide", "fund_settings", "manage_positions", "budget_approve", "milestones_signoff", "halt_trading",
                   "data_licences_review", "instruments_approve"}, _W["lead"],
           "Leads the society's fund; chairs the Portfolio Management Committee (PMC)."),
        _p("head_of_trading", "Head of Trading", 1, "pm",
           VIEW | {"pretrade_desk", "propose_orders", "execute_orders", "pitch_decide", "halt_trading", "reconcile",
                   "instruments_approve", "manage_positions", "milestones_signoff"}, _W["trading"],
           "Implementation of PMC-approved trades: pre-trade feasibility, execution, TCA and the trade record."),
        _p("cio", "Chief Investment Officer (PMC)", 1, "pm",
           VIEW | {"pretrade_desk", "pitch_decide", "model_signoff_ic", "instruments_approve", "milestones_signoff"},
           _W["lead"], "Owns the investment process and the PMC agenda; votes on pitches."),
        _p("pmc_member", "PMC Member", 2, "pm", VIEW | {"pitch_decide", "pretrade_desk"}, ["pitch-review", "fund-cockpit", "performance-attribution"],
           "Votes on analyst pitches (four-eyes: never on their own).", seats=4),
        _p("head_of_risk", "Head of Risk", 2, "risk",
           VIEW | {"pretrade_desk", "approve_orders", "halt_trading", "resume_trading", "incidents_signoff", "reconcile",
                   "fund_settings", "model_signoff_risk"}, _W["risk"],
           "Mandate compliance, limits, tracking error against the benchmark and order approval."),
        _p("sector_head", "Sector Head", 2, "analyst",
           VIEW | {"pretrade_desk", "pitch_submit", "propose_orders", "model_signoff_research"}, _W["analyst"],
           "Leads a sector team (e.g. Technology, Healthcare, Financials), reviews analysts' pitches.", seats=8),
        _p("treasurer", "Treasurer", 2, "viewer", VIEW | {"budget_record", "budget_approve", "reconcile"}, _W["finance"],
           "Society finances and expenses; reconciliation review."),
        _p("equity_analyst", "Equity Research Analyst", 3, "analyst", VIEW | {"pretrade_desk", "pitch_submit"},
           _W["analyst"], "Researches and pitches stocks within a sector team.", seats=20),
        _p("quant_analyst", "Quantitative Analyst", 3, "quant", VIEW | {"model_propose", "quant_deploy", "pretrade_desk"},
           _W["quant"], "Screens, factor and risk analysis, backtests for the fund.", seats=6),
        _p("trainee", "Trainee Analyst", 4, "viewer", VIEW, ["stock-ideas", "pitch-review", "event-dataset", "fund-cockpit"],
           "Learning seat: reads everything, drafts with a sector head.", seats=30),
        _p("alumni_advisor", "Alumni Advisor", 4, "viewer", VIEW, _W["observer"], "Read-only mentor seat.", seats=10),
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS fund_positions (
            key TEXT PRIMARY KEY, title TEXT NOT NULL, tier INTEGER NOT NULL, base_role TEXT NOT NULL,
            capabilities TEXT, panels TEXT, description TEXT, seats INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS fund_assignments (
            username TEXT PRIMARY KEY, position_key TEXT NOT NULL, assigned_by TEXT, assigned_at TEXT);
        """)
        c.commit()


def seed(template: str) -> int:
    """Add the template's positions that the fund doesn't have yet. Returns how many were added."""
    init_db()
    added = 0
    with _conn() as c:
        have = {r[0] for r in c.execute("SELECT key FROM fund_positions")}
        for p in TEMPLATES[template]:
            if p["key"] in have:
                continue
            c.execute("INSERT INTO fund_positions (key, title, tier, base_role, capabilities, panels, description, seats, created_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (p["key"], p["title"], p["tier"], p["base_role"], json.dumps(p["capabilities"]),
                                                    json.dumps(p["panels"]), p["description"], p["seats"], _now()))
            added += 1
        c.commit()
    _bust()
    return added


def _row(r) -> T:
    d = dict(r)
    d["capabilities"] = json.loads(d.get("capabilities") or "[]")
    d["panels"] = json.loads(d.get("panels") or "[]")
    return d


def list_positions() -> List[T]:
    init_db()
    with _conn() as c:
        rows = [_row(r) for r in c.execute("SELECT * FROM fund_positions ORDER BY tier, title")]
        held: Dict[str, List[str]] = {}
        for a in c.execute("SELECT username, position_key FROM fund_assignments"):
            held.setdefault(a["position_key"], []).append(a["username"])
    for p in rows:
        p["holders"] = sorted(held.get(p["key"], []))
        p["tier_label"] = TIERS.get(p["tier"])
    return rows


def upsert_position(p: Dict[str, Any], user: str) -> T:
    init_db()
    key = str(p.get("key") or "").strip().lower()
    if not key or not key.replace("_", "").isalnum() or len(key) > 40:
        raise ValueError("key: letters, digits and _ (≤40)")
    if int(p.get("tier") or 0) not in TIERS:
        raise ValueError("tier is 1–4")
    if p.get("base_role") not in BASE_ROLES:
        raise ValueError(f"base_role is one of {', '.join(BASE_ROLES)}")
    caps = [c for c in (p.get("capabilities") or []) if c in CAPABILITIES]
    if p["base_role"] == "viewer":
        caps = [c for c in caps if c in {"view_book", "budget_record", "budget_approve", "reconcile", "incidents_signoff",
                                         "data_licences_review", "milestones_signoff"}]
    title = str(p.get("title") or "").strip()[:80]
    if not title:
        raise ValueError("a title is required")
    with _conn() as c:
        c.execute("INSERT INTO fund_positions (key, title, tier, base_role, capabilities, panels, description, seats, created_at) "
                  "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET title=excluded.title, tier=excluded.tier, "
                  "base_role=excluded.base_role, capabilities=excluded.capabilities, panels=excluded.panels, "
                  "description=excluded.description, seats=excluded.seats",
                  (key, title, int(p["tier"]), p["base_role"], json.dumps(sorted(set(caps))),
                   json.dumps([str(x)[:40] for x in (p.get("panels") or [])][:12]), str(p.get("description") or "")[:500],
                   int(p.get("seats") or 1), _now()))
        c.commit()
    _bust()
    _audit("position_saved", f"Position '{title}' (tier {p['tier']}, acts as {p['base_role']}) saved", user, f"position:{key}")
    return next(x for x in list_positions() if x["key"] == key)


def delete_position(key: str, user: str) -> None:
    init_db()
    with _conn() as c:
        if c.execute("SELECT 1 FROM fund_assignments WHERE position_key = ?", (key,)).fetchone():
            raise ValueError("unassign the people in this position first")
        c.execute("DELETE FROM fund_positions WHERE key = ?", (key,))
        c.commit()
    _bust()
    _audit("position_deleted", f"Position '{key}' removed", user, f"position:{key}")


def assign(username: str, key: Optional[str], user: str) -> Optional[T]:
    """Give a person a position in this fund (None removes it). One position per person per fund."""
    init_db()
    with _conn() as c:
        if key is None:
            c.execute("DELETE FROM fund_assignments WHERE username = ?", (username,))
        else:
            p = c.execute("SELECT * FROM fund_positions WHERE key = ?", (key,)).fetchone()
            if not p:
                raise LookupError("position not found")
            n = c.execute("SELECT COUNT(*) FROM fund_assignments WHERE position_key = ? AND username != ?", (key, username)).fetchone()[0]
            if p["seats"] and n >= p["seats"]:
                raise ValueError(f"all {p['seats']} seat(s) of '{p['title']}' are filled")
            c.execute("INSERT INTO fund_assignments (username, position_key, assigned_by, assigned_at) VALUES (?,?,?,?) "
                      "ON CONFLICT(username) DO UPDATE SET position_key=excluded.position_key, assigned_by=excluded.assigned_by, "
                      "assigned_at=excluded.assigned_at", (username, key, user, _now()))
        c.commit()
    _bust()
    _audit("position_assigned", f"{username} → {key or '(no position)'}", user, f"user:{username}")
    return position_of(username)


_CACHE: Dict[tuple, tuple] = {}


def _bust() -> None:
    _CACHE.clear()


def position_of(username: str) -> Optional[T]:
    """The person's position in the current fund (cached 10 s — read on every request)."""
    from api import funds
    k = (funds.current(), username)
    hit = _CACHE.get(k)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    try:
        init_db()
        with _conn() as c:
            r = c.execute("SELECT p.* FROM fund_assignments a JOIN fund_positions p ON p.key = a.position_key "
                          "WHERE a.username = ?", (username,)).fetchone()
        v = _row(r) if r else None
    except Exception:                                                          # noqa: BLE001 — no positions table yet
        v = None
    _CACHE[k] = (time.time(), v)
    return v


def capabilities_for(user: Optional[Dict[str, Any]]) -> Set[str]:
    if not user:
        return set()
    if user.get("platform_role", user.get("role")) == "admin":
        return set(ALL_CAPS)
    pos = user.get("position")
    if pos:
        return set(pos["capabilities"])
    return set(ROLE_DEFAULT_CAPS.get(user.get("role"), set()))


def require(request, cap: str) -> Dict[str, Any]:
    """403 unless the signed-in user's position (or role) in this fund grants `cap`."""
    from fastapi import HTTPException
    from api.core.access import current_user
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Authentication required")
    if cap not in capabilities_for(u):
        where = f"your position ({u['position']['title']})" if u.get("position") else f"your role ({u.get('role')})"
        raise HTTPException(403, f"{where} does not include: {CAPABILITIES.get(cap, cap)}")
    return u


def apply_to_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """The request's identity in the current fund: role and capabilities from the person's position there."""
    if not user or user.get("role") == "admin":
        return user
    pos = position_of(user["username"])
    if not pos:
        return user
    return {**user, "platform_role": user["role"], "role": pos["base_role"], "position": pos}


def me(user: Dict[str, Any]) -> Dict[str, Any]:
    from api import funds
    pos = user.get("position")
    caps = capabilities_for(user)
    return {"fund": funds.current(), "username": user["username"], "role": user.get("role"),
            "platform_role": user.get("platform_role", user.get("role")),
            "position": {k: pos[k] for k in ("key", "title", "tier", "description", "panels")} | {"tier_label": TIERS.get(pos["tier"])}
            if pos else None,
            "capabilities": {k: (k in caps) for k in CAPABILITIES}, "capability_labels": CAPABILITIES,
            "read_only": user.get("role") == "viewer"}


def _audit(action: str, text: str, user: str, target: str) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=user, target=target)
    except Exception:                                                          # noqa: BLE001
        pass
