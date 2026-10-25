"""
Analyst pitch review for the Portfolio Management Committee.

A pitch is a versioned research record for one security: thesis, horizon (1–5 years), catalysts (each dated as
scheduled or estimated), bear / base / bull fair values with probabilities and assumptions, a preferred entry range,
target position size, key financial assumptions and kill criteria. Editing adds a version; earlier versions stay
readable (research versioning). Workflow: draft → submitted → approved | rejected (PMC, four-eyes: never the author)
→ closed. Every transition is written to the append-only audit log.

Kill criteria are checked automatically where the data allow — price below / above a level, drawdown from the
entry price, underperformance against the fund's benchmark since approval, a fundamental metric crossing a threshold,
a catalyst deadline passing — and reported as "manual" otherwise (never guessed).

Fair values are per share in the listing's quote currency (pence for London), the same unit as the price.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from api.portfolio_store import _conn

STATES = ("draft", "submitted", "approved", "rejected", "closed")
KILL_TYPES = ("price_below", "price_above", "drawdown_from_entry", "underperform_benchmark", "metric_below",
              "metric_above", "date_passed", "manual")
METRICS = ("revenue_growth", "operating_margin", "net_margin", "fcf_margin", "roe", "debt_to_equity", "gross_margin")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pitches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, title TEXT, analyst TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT, updated_at TEXT, decided_at TEXT, decided_by TEXT, decision_notes TEXT,
            approved_price REAL, approved_benchmark_level REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pitch_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pitch_id INTEGER NOT NULL, version INTEGER NOT NULL,
            created_at TEXT, author TEXT, payload TEXT NOT NULL, note TEXT, UNIQUE (pitch_id, version))""")
        c.commit()


# ── validation ─────────────────────────────────────────────────────────────
def validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Clean a pitch body; raise ValueError on what would make the record unusable."""
    p = dict(payload or {})
    out: Dict[str, Any] = {"thesis": str(p.get("thesis") or "").strip()[:8000]}
    if len(out["thesis"]) < 20:
        raise ValueError("thesis: state the investment case (at least 20 characters)")
    hz = float(p.get("horizon_years") or 0)
    if not 1 <= hz <= 5:
        raise ValueError("horizon_years must be between 1 and 5")
    out["horizon_years"] = hz
    sc = p.get("scenarios") or {}
    scen = {}
    for k in ("bear", "base", "bull"):
        s = sc.get(k) or {}
        try:
            val, prob = float(s.get("value")), float(s.get("probability"))
        except (TypeError, ValueError):
            raise ValueError(f"scenarios.{k}: value and probability are required numbers")
        if val <= 0 or not 0 <= prob <= 1:
            raise ValueError(f"scenarios.{k}: value > 0 and probability in [0, 1]")
        scen[k] = {"value": val, "probability": prob, "assumptions": str(s.get("assumptions") or "")[:2000]}
    if not scen["bear"]["value"] <= scen["base"]["value"] <= scen["bull"]["value"]:
        raise ValueError("scenarios: bear ≤ base ≤ bull fair values")
    total = sum(s["probability"] for s in scen.values())
    if abs(total - 1) > 0.01:
        raise ValueError(f"scenario probabilities must add up to 1 (they add up to {total:.2f})")
    out["scenarios"] = scen
    er = p.get("entry_range") or {}
    if er.get("low") is not None or er.get("high") is not None:
        lo, hi = float(er.get("low") or 0), float(er.get("high") or 0)
        if not 0 < lo <= hi:
            raise ValueError("entry_range: 0 < low ≤ high")
        out["entry_range"] = {"low": lo, "high": hi}
    if p.get("target_weight") is not None:
        w = float(p["target_weight"])
        if not 0 < w <= 0.25:
            raise ValueError("target_weight is a fraction of NAV in (0, 0.25]")
        out["target_weight"] = w
    cats = []
    for x in (p.get("catalysts") or [])[:20]:
        conf = (x.get("date_confidence") or "estimated").lower()
        if conf not in ("scheduled", "estimated", "undated"):
            raise ValueError("catalysts: date_confidence is scheduled, estimated or undated")
        d = x.get("expected_date")
        if d:
            date.fromisoformat(str(d)[:10])
        cats.append({"event": str(x.get("event") or "")[:300], "expected_date": str(d)[:10] if d else None,
                     "date_confidence": conf, "source": str(x.get("source") or "")[:300]})
    out["catalysts"] = cats
    kills = []
    for x in (p.get("kill_criteria") or [])[:20]:
        t = x.get("type")
        if t not in KILL_TYPES:
            raise ValueError(f"kill_criteria: type must be one of {', '.join(KILL_TYPES)}")
        k = {"type": t, "description": str(x.get("description") or "")[:500]}
        if t in ("price_below", "price_above"):
            k["level"] = float(x["level"])
        elif t in ("drawdown_from_entry", "underperform_benchmark"):
            k["threshold"] = abs(float(x["threshold"]))
        elif t in ("metric_below", "metric_above"):
            if x.get("metric") not in METRICS:
                raise ValueError(f"kill_criteria: metric must be one of {', '.join(METRICS)}")
            k["metric"], k["threshold"] = x["metric"], float(x["threshold"])
        elif t == "date_passed":
            k["date"] = str(date.fromisoformat(str(x["date"])[:10]))
        kills.append(k)
    if not kills:
        raise ValueError("kill_criteria: at least one condition that would end the thesis")
    out["kill_criteria"] = kills
    out["financial_assumptions"] = {str(k)[:60]: v for k, v in (p.get("financial_assumptions") or {}).items()}
    out["risks"] = [str(r)[:500] for r in (p.get("risks") or [])[:20]]
    out["valuation_method"] = str(p.get("valuation_method") or "")[:300]
    return out


def expected_value(payload: Dict[str, Any]) -> float:
    return float(sum(s["value"] * s["probability"] for s in payload["scenarios"].values()))


def valuation_vs_price(payload: Dict[str, Any], price: Optional[float]) -> Dict[str, Any]:
    """Probability-weighted fair value and the upside / downside from `price` (same currency units)."""
    ev = expected_value(payload)
    sc = payload["scenarios"]
    out = {"expected_value": round(ev, 4), "bear": sc["bear"]["value"], "base": sc["base"]["value"],
           "bull": sc["bull"]["value"]}
    if price:
        out.update(price=price, expected_return=round(ev / price - 1, 4),
                   upside_bull=round(sc["bull"]["value"] / price - 1, 4),
                   downside_bear=round(sc["bear"]["value"] / price - 1, 4))
        dn = price - sc["bear"]["value"]
        out["reward_to_risk"] = round((sc["bull"]["value"] - price) / dn, 2) if dn > 0 else None
        hz = payload.get("horizon_years") or 1
        out["annualised_expected_return"] = round((ev / price) ** (1 / hz) - 1, 4) if ev > 0 else None
        er = payload.get("entry_range")
        if er:
            out["in_entry_range"] = er["low"] <= price <= er["high"]
    return out


# ── store ─────────────────────────────────────────────────────────────────
def _row(c, pid: int) -> Optional[Dict[str, Any]]:
    r = c.execute("SELECT * FROM pitches WHERE id = ?", (pid,)).fetchone()
    return dict(r) if r else None


def create(symbol: str, title: str, analyst: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    body = validate(payload)
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    with _conn() as c:
        cur = c.execute("INSERT INTO pitches (symbol, title, analyst, status, current_version, created_at, updated_at) "
                        "VALUES (?, ?, ?, 'draft', 1, ?, ?)", (sym, (title or sym)[:200], analyst, _now(), _now()))
        pid = cur.lastrowid
        c.execute("INSERT INTO pitch_versions (pitch_id, version, created_at, author, payload, note) VALUES (?, 1, ?, ?, ?, ?)",
                  (pid, _now(), analyst, json.dumps(body), "initial"))
        c.commit()
    return get(pid)


def add_version(pid: int, author: str, payload: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    init_db()
    body = validate(payload)
    with _conn() as c:
        p = _row(c, pid)
        if not p:
            raise LookupError("pitch not found")
        if p["status"] in ("closed",):
            raise ValueError("a closed pitch cannot be revised")
        v = p["current_version"] + 1
        c.execute("INSERT INTO pitch_versions (pitch_id, version, created_at, author, payload, note) VALUES (?, ?, ?, ?, ?, ?)",
                  (pid, v, _now(), author, json.dumps(body), (note or "")[:500]))
        # a revision of an approved pitch goes back to the committee
        status = "submitted" if p["status"] in ("approved", "rejected") else p["status"]
        c.execute("UPDATE pitches SET current_version = ?, updated_at = ?, status = ? WHERE id = ?", (v, _now(), status, pid))
        c.commit()
    return get(pid)


def transition(pid: int, user: str, to: str, notes: str = "", price: Optional[float] = None,
               bench_level: Optional[float] = None) -> Dict[str, Any]:
    init_db()
    allowed = {"draft": ("submitted",), "submitted": ("approved", "rejected", "draft"),
               "approved": ("closed",), "rejected": ("draft", "closed"), "closed": ()}
    with _conn() as c:
        p = _row(c, pid)
        if not p:
            raise LookupError("pitch not found")
        if to not in allowed[p["status"]]:
            raise ValueError(f"a {p['status']} pitch cannot become {to}")
        if to in ("approved", "rejected") and user == p["analyst"]:
            raise PermissionError("four-eyes: the committee decision cannot be recorded by the pitch's author")
        if to in ("approved", "rejected"):
            c.execute("UPDATE pitches SET status = ?, decided_at = ?, decided_by = ?, decision_notes = ?, "
                      "approved_price = ?, approved_benchmark_level = ?, updated_at = ? WHERE id = ?",
                      (to, _now(), user, (notes or "")[:2000], price if to == "approved" else None,
                       bench_level if to == "approved" else None, _now(), pid))
        else:
            c.execute("UPDATE pitches SET status = ?, updated_at = ? WHERE id = ?", (to, _now(), pid))
        c.commit()
    return get(pid)


def get(pid: int) -> Dict[str, Any]:
    init_db()
    with _conn() as c:
        p = _row(c, pid)
        if not p:
            raise LookupError("pitch not found")
        vs = [dict(r) for r in c.execute("SELECT * FROM pitch_versions WHERE pitch_id = ? ORDER BY version", (pid,))]
    for v in vs:
        v["payload"] = json.loads(v["payload"])
    p["versions"] = vs
    p["current"] = vs[-1]["payload"] if vs else None
    return p


def list_pitches(status: Optional[str] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    q, args = "SELECT * FROM pitches", []
    cond = []
    if status:
        cond.append("status = ?")
        args.append(status)
    if symbol:
        cond.append("UPPER(symbol) = ?")
        args.append(symbol.upper())
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY updated_at DESC"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(q, args)]
        for r in rows:
            v = c.execute("SELECT payload FROM pitch_versions WHERE pitch_id = ? AND version = ?",
                          (r["id"], r["current_version"])).fetchone()
            r["current"] = json.loads(v["payload"]) if v else None
    return rows


def latest_for(symbol: str) -> Optional[Dict[str, Any]]:
    """The most relevant pitch for a security: approved first, then submitted, then the latest draft."""
    rows = list_pitches(symbol=symbol)
    for st in ("approved", "submitted", "draft"):
        for r in rows:
            if r["status"] == st:
                return r
    return None


# ── kill criteria ─────────────────────────────────────────────────────────
def check_kill_criteria(pitch: Dict[str, Any], price: Optional[float], entry_price: Optional[float],
                        metrics: Optional[Dict[str, Optional[float]]] = None,
                        relative_since_approval: Optional[float] = None,
                        today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Each kill criterion with status triggered / ok / not_evaluable / manual and the observed value."""
    today = today or date.today()
    out = []
    for k in (pitch.get("current") or {}).get("kill_criteria") or []:
        r = {**k, "status": "not_evaluable", "observed": None}
        t = k["type"]
        if t == "price_below" and price is not None:
            r.update(observed=price, status="triggered" if price < k["level"] else "ok")
        elif t == "price_above" and price is not None:
            r.update(observed=price, status="triggered" if price > k["level"] else "ok")
        elif t == "drawdown_from_entry" and price is not None and entry_price:
            dd = price / entry_price - 1
            r.update(observed=round(dd, 4), status="triggered" if dd <= -k["threshold"] else "ok")
        elif t == "underperform_benchmark" and relative_since_approval is not None:
            r.update(observed=round(relative_since_approval, 4),
                     status="triggered" if relative_since_approval <= -k["threshold"] else "ok")
        elif t in ("metric_below", "metric_above") and metrics and metrics.get(k["metric"]) is not None:
            v = float(metrics[k["metric"]])
            hit = v < k["threshold"] if t == "metric_below" else v > k["threshold"]
            r.update(observed=round(v, 4), status="triggered" if hit else "ok")
        elif t == "date_passed":
            r.update(observed=str(today), status="triggered" if today > date.fromisoformat(k["date"]) else "ok")
        elif t == "manual":
            r["status"] = "manual"
        out.append(r)
    return out
