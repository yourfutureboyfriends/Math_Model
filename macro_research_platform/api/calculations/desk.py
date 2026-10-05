"""
Role desk: what needs THIS user's attention now.

`build_queue` turns the fund's live state into a prioritised action list for one user,
following the separation of duties the workflow enforces:

  * risk (and admin) approve orders — but never their own (four-eyes);
  * pm (and admin) execute approved orders;
  * limit breaches go to risk and pm; warnings likewise, at lower priority;
  * stale model inputs go to everyone who relies on the models, highest for the
    people who own them (analyst, quant);
  * admin also sees account hygiene (locked accounts, pending password changes).

Pure function — no I/O — so the routing rules are unit-tested.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

PRIORITY_ORDER = {"high": 0, "medium": 1, "info": 2}
PENDING_STATES = ("Proposed", "Under Review")

# Panels each role starts from (sidebar "YOUR DESK" + quick links), most important first.
ROLE_FOCUS: Dict[str, Dict[str, Any]] = {
    "pm": {"title": "Portfolio Manager",
           "panels": ["macro-model", "fund-cockpit", "trade-ideas", "portfolio-positions", "performance-attribution",
                      "master-signal", "regime-playbook", "expected-returns"]},
    "risk": {"title": "Risk Officer",
             "panels": ["fund-cockpit", "cycle-risk", "var-stress", "risk-analytics", "factor-exposure",
                        "correlation-matrix", "risk-indicators", "system-audit"]},
    "analyst": {"title": "Macro Analyst",
                "panels": ["morning-brief", "regime", "cycle-risk", "key-metrics", "nowcast", "economic-calendar",
                           "yield-curve", "regional-macro"]},
    "quant": {"title": "Quant Researcher",
              "panels": ["macro-model", "signal-scorecard", "cycle-risk", "factor-validation", "model-agreement", "stream-agreement",
                         "regime-transition", "data-explorer", "system-health"]},
    "admin": {"title": "Administrator",
              "panels": ["fund-cockpit", "system-audit", "system-health", "data-providers",
                         "master-signal", "trade-ideas"]},
}


def _item(priority: str, kind: str, title: str, detail: str = "", target: Optional[str] = None,
          ref: Any = None) -> Dict[str, Any]:
    return {"priority": priority, "kind": kind, "title": title, "detail": detail,
            "target": target, "ref": ref}


def _order_label(o: Dict[str, Any]) -> str:
    q = o.get("quantity")
    qty = f"{q:g}" if isinstance(q, (int, float)) else str(q)
    return f"#{o.get('id')} {o.get('side')} {qty} {o.get('symbol')}"


def build_queue(role: str, username: str, *, orders: List[Dict[str, Any]],
                limits: Optional[Dict[str, Any]] = None,
                freshness: Optional[Dict[str, Any]] = None,
                users: Optional[List[Dict[str, Any]]] = None,
                cb_moves: Optional[List[Dict[str, Any]]] = None,
                cycle: Optional[Dict[str, Any]] = None,
                today: Optional[date] = None) -> List[Dict[str, Any]]:
    today = today or date.today()
    is_admin = role == "admin"
    q: List[Dict[str, Any]] = []

    # ── Orders (four-eyes routing) ───────────────────────────────────────────
    pending = [o for o in orders if o.get("state") in PENDING_STATES]
    if role == "risk" or is_admin:
        mine_to_review = [o for o in pending if o.get("created_by") != username]
        if mine_to_review:
            q.append(_item("high", "approve", f"{len(mine_to_review)} order(s) awaiting your approval",
                           ", ".join(_order_label(o) for o in mine_to_review[:4]), "fund-cockpit",
                           [o.get("id") for o in mine_to_review]))
    own_pending = [o for o in pending if o.get("created_by") == username]
    if own_pending:
        q.append(_item("info", "waiting", f"{len(own_pending)} of your order(s) awaiting risk approval",
                       ", ".join(_order_label(o) for o in own_pending[:4]), "fund-cockpit",
                       [o.get("id") for o in own_pending]))
    approved = [o for o in orders if o.get("state") == "Approved" and not o.get("executed_trade_id")]
    if approved and (role == "pm" or is_admin):
        q.append(_item("high", "execute", f"{len(approved)} approved order(s) ready to execute",
                       ", ".join(_order_label(o) for o in approved[:4]), "fund-cockpit",
                       [o.get("id") for o in approved]))

    # ── Risk limits ──────────────────────────────────────────────────────────
    if limits and (role in ("risk", "pm") or is_admin):
        for r in limits.get("breaches") or []:
            q.append(_item("high", "breach", f"Limit breach: {r.get('label')}",
                           f"{_fmt(r.get('value'), r.get('unit'))} vs hard {_fmt(r.get('hard'), r.get('unit'))}",
                           "fund-cockpit", r.get("metric")))
        for r in limits.get("warnings") or []:
            q.append(_item("medium", "warning", f"Near limit: {r.get('label')}",
                           f"{_fmt(r.get('value'), r.get('unit'))} vs soft {_fmt(r.get('soft'), r.get('unit'))}",
                           "fund-cockpit", r.get("metric")))

    # ── Data quality (everyone relies on the models; owners get it first) ────
    if freshness and freshness.get("available"):
        owners = role in ("analyst", "quant") or is_admin
        for s in freshness.get("series") or []:
            if s.get("status") == "CRITICAL":
                q.append(_item("high" if owners else "medium", "data",
                               f"Missing data: {s.get('name')}",
                               f"{s.get('periods_behind')} period(s) behind its release calendar "
                               f"(latest {s.get('last_observation_date')})", "system-health", s.get("series_id")))
            elif s.get("status") == "STALE":
                q.append(_item("medium" if owners else "info", "data", f"Late release: {s.get('name')}",
                               f"expected {s.get('expected_period')}, have {s.get('last_observation_date')}",
                               "system-health", s.get("series_id")))
        if role in ("analyst", "quant", "pm") or is_admin:
            soon = today + timedelta(days=3)
            for s in freshness.get("series") or []:
                nxt = s.get("next_expected_release")
                if s.get("frequency") in ("M", "Q", "W") and nxt and today.isoformat() <= nxt <= soon.isoformat():
                    q.append(_item("info", "release", f"{s.get('name')} due ~{nxt}",
                                   "scheduled release — expect the models to update", "economic-calendar",
                                   s.get("series_id")))

    # ── Central-bank moves across developed markets (last 14 days) ──────────
    if cb_moves and (role in ("analyst", "quant", "pm", "risk") or is_admin):
        recent = [m for m in cb_moves if m.get("date", "") >= (today - timedelta(days=14)).isoformat()]
        if recent:
            q.append(_item("info", "cb_move", f"{len(recent)} central-bank move(s) in the last 2 weeks",
                           ", ".join(f"{m['economy']} {'+' if m['bp'] > 0 else ''}{m['bp']}bp → {m['to']}% ({m['date'][5:]})"
                                     for m in recent[:5]), "regional-macro"))

    # ── Systemic-risk warnings (published indicators) ───────────────────────
    if cycle and (role in ("risk", "pm", "analyst", "quant") or is_admin):
        warn = []
        t, a, n = cycle.get("turbulence") or {}, cycle.get("absorption_ratio") or {}, cycle.get("near_term_forward_spread") or {}
        if t.get("turbulent"):
            warn.append(f"turbulence {t.get('avg_20d')} (20d avg) above its 75th percentile")
        if (a.get("standardized_shift") or 0) >= 1:
            warn.append(f"absorption-ratio shift +{a['standardized_shift']}σ (markets tightly coupled)")
        if n.get("value_pp") is not None and n["value_pp"] < 0:
            warn.append(f"near-term forward spread {n['value_pp']:+.2f}pp (policy easing priced)")
        if warn:
            q.append(_item("high" if role in ("risk", "pm") or is_admin else "medium", "systemic",
                           "Systemic-risk warning", "; ".join(warn), "cycle-risk"))

    # ── Account hygiene (admin) ──────────────────────────────────────────────
    if is_admin and users:
        locked = [u["username"] for u in users if u.get("locked")]
        pending_pw = [u["username"] for u in users if u.get("must_change_password") and not u.get("disabled")]
        if locked:
            q.append(_item("medium", "account", f"{len(locked)} locked account(s)", ", ".join(locked)))
        if pending_pw:
            q.append(_item("info", "account", f"{len(pending_pw)} account(s) still on a default/temporary password",
                           ", ".join(pending_pw)))

    q.sort(key=lambda i: PRIORITY_ORDER[i["priority"]])
    return q


def _fmt(v: Any, unit: Optional[str]) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    if unit == "% NAV":
        return f"{v * 100:.1f}% NAV"
    if unit == "days":
        return f"{v:.1f} days"
    return f"{v:,.2f}"
