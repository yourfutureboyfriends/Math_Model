"""
Knowledge scanner: the recession models feed themselves new evidence — under a validation gate.

Each month a fixed registry of free leading indicators (FRED) is fetched and every candidate is tested the same way
the headline was: walk-forward from 1985, refit each January on months whose outcome window and NBER lag had closed,
recalibrated on its own earlier forecasts. A candidate is *proposed* only when adding it to the base model improves
the Brier score significantly after allowing for every candidate in the registry (year-block bootstrap, Bonferroni).
Nothing is adopted automatically: a person approves a proposal, which then joins the ML challenger's inputs (and is
re-tested there) — the continuous-training-with-validation-gates pattern from Google's ML-systems work (Sculley et
al., "Hidden Technical Debt in Machine Learning Systems"; TFX), with human control of what the model learns from.

Transformations are fixed in the registry (chosen from the literature before testing, not searched), and every value
is the one known at the time: last month's figure for monthly series, last month's average for weekly ones.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# series id → (label, transform, why). Transforms: lvl = level; d6 = 6-month change; g6 = 6-month log growth ×200
# (annualised %); avg3 = 3-month average level.
REGISTRY: Dict[str, tuple] = {
    "NFCI": ("Chicago Fed financial conditions (NFCI)", "lvl", "broad financial stress beyond credit spreads"),
    "ICSA": ("Initial jobless claims", "g6", "the earliest weekly labour-market signal"),
    "PERMIT": ("Building permits", "g6", "housing leads the cycle (Leamer, 'Housing is the business cycle')"),
    "UMCSENT": ("Consumer sentiment (Michigan)", "d6", "household expectations"),
    "AWHMAN": ("Average weekly hours, manufacturing", "d6", "firms cut hours before heads"),
    "HOUST": ("Housing starts", "g6", "residential investment"),
    "T10Y2Y": ("10Y–2Y Treasury spread", "lvl", "the market's favourite curve measure"),
    "WTISPLC": ("WTI oil price", "g6", "oil shocks preceded several recessions (Hamilton)"),
    "M2REAL": ("Real M2", "g6", "real money growth"),
    "INDPRO": ("Industrial production", "g6", "coincident activity"),
    "CFNAI": ("Chicago Fed National Activity Index", "avg3", "85-indicator activity summary"),
    "TOTALSA": ("Light vehicle sales", "g6", "durable consumption"),
}
BASE_SPEC = ["ts", "ebp", "pay6"]          # the headline's core, one probit (fast enough to screen many candidates)
ALPHA = 0.05
_ready = False


def _monthly_known(series_id: str, transform: str) -> Dict[str, float]:
    """The candidate's value known at each month m (from data through m−1)."""
    import pandas as pd
    from api.models_ml.recession_ensemble import _fred
    s = _fred().get_series(series_id).dropna()
    s.index = pd.to_datetime(s.index)
    m = s.resample("MS").mean()
    if transform == "g6":
        v = np.log(m.where(m > 0)).diff(6) * 200
    elif transform == "d6":
        v = m.diff(6)
    elif transform == "avg3":
        v = m.rolling(3).mean()
    else:
        v = m
    v = v.shift(1).dropna()                                           # one-month publication lag
    return {d.strftime("%Y-%m"): float(x) for d, x in v.items() if np.isfinite(x)}


def _walk_forward_brier(rows: List[Dict[str, Any]], cols: List[str], start_year: int = 1985):
    """Recalibrated walk-forward probabilities of one probit on `cols` (same protocol as the headline)."""
    from api.models_ml import recession_ensemble as R
    from api.models_ml.recession_challenger import _cutoff
    by = {r["month"]: r for r in rows}
    months = sorted(by)
    raw, ys, tm = [], [], []
    for yr in range(start_year, int(months[-1][:4]) + 1):
        cut = _cutoff(yr)
        tr = [by[m] for m in months if m < cut and by[m]["y"] is not None]
        te = [by[m] for m in months if m[:4] == str(yr) and by[m]["y"] is not None]
        if not te or sum(r["y"] for r in tr) < 3:
            continue
        b = R.probit_fit(R._design(tr, cols), np.array([r["y"] for r in tr], float))
        if b is None:
            continue
        raw += [R.probit_prob(b, [r[c] for c in cols]) for r in te]
        ys += [r["y"] for r in te]
        tm += [r["month"] for r in te]
    cal = []
    for i, m in enumerate(tm):
        known = [j for j in range(i) if tm[j] < _cutoff(int(m[:4]))]
        coef = R.learned_platt([raw[j] for j in known], [ys[j] for j in known]) if known else None
        cal.append(R.platt_apply(coef, raw[i]))
    return np.array(cal), np.array(ys), tm


def block_bootstrap_p(d: np.ndarray, tm: List[str], n: int = 3000, seed: int = 0) -> float:
    """P(mean improvement ≤ 0) under a moving-block (3-year) bootstrap — recession episodes span many months."""
    years = sorted({m[:4] for m in tm})
    idx = {y: [i for i, m in enumerate(tm) if m[:4] == y] for y in years}
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n):
        pick: List[str] = []
        while len(pick) < len(years):
            s0 = int(rng.integers(0, max(1, len(years) - 2)))
            pick += years[s0:s0 + 3]
        boot.append(float(d[[i for y in pick[:len(years)] for i in idx[y]]].mean()))
    return float((np.array(boot) <= 0).mean())


def screen(fetch: Optional[Callable[[str, str], Dict[str, float]]] = None,
           registry: Optional[Dict[str, tuple]] = None) -> Dict[str, Any]:
    """Test every registry candidate as an addition to the base model; record and return the results."""
    from api.models_ml import recession_ensemble as R
    fetch = fetch or _monthly_known
    registry = registry or REGISTRY
    data, _ = R._inputs()
    if not data:
        return {"available": False, "reason": "base inputs unavailable"}
    base_rows = [r for r in data["rows"] if all(r.get(c) is not None for c in BASE_SPEC)]
    bar = ALPHA / len(registry)
    results = []
    for sid, (label, tf, why) in registry.items():
        try:
            vals = fetch(sid, tf)
        except Exception as e:                                             # noqa: BLE001 — record, carry on
            results.append({"series": sid, "label": label, "status": "unavailable", "reason": str(e)[:120]})
            continue
        rows = [{**r, "cand": vals[r["month"]]} for r in base_rows if r["month"] in vals]
        if len(rows) < 300 or sum(1 for r in rows if r["y"] == 1) < 30:
            results.append({"series": sid, "label": label, "status": "too little history", "from": rows[0]["month"] if rows else None})
            continue
        pb, y, tm = _walk_forward_brier(rows, BASE_SPEC)
        pc, y2, tm2 = _walk_forward_brier(rows, BASE_SPEC + ["cand"])
        if tm != tm2 or not len(tm):
            results.append({"series": sid, "label": label, "status": "could not compare"})
            continue
        d = (pb - y) ** 2 - (pc - y) ** 2
        recent = np.array([m >= "2005-01" for m in tm])
        p = block_bootstrap_p(d, tm)
        results.append({"series": sid, "label": label, "transform": tf, "why": why, "from": tm[0], "to": tm[-1],
                        "brier_base": round(float(np.mean((pb - y) ** 2)), 4), "brier_with": round(float(np.mean((pc - y) ** 2)), 4),
                        "brier_gain": round(float(d.mean()), 5),
                        "brier_gain_since_2005": round(float(d[recent].mean()), 5) if recent.any() else None,
                        "p_no_gain": round(p, 4), "status": "proposed" if (p < bar and d.mean() > 0 and
                                                                       (not recent.any() or d[recent].mean() >= 0)) else "not significant"})
    run = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "candidates": len(registry), "bar": bar,
           "results": sorted(results, key=lambda r: r.get("p_no_gain", 2))}
    _store(run)
    return {"available": True, **run}


# ── storage and approvals ─────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS knowledge_scans (run_at TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS knowledge_approvals (series TEXT PRIMARY KEY, transform TEXT NOT NULL, "
                  "approved_by TEXT NOT NULL, approved_at TEXT NOT NULL, note TEXT)")
    _ready = True


def _store(run: Dict[str, Any]) -> None:
    import json
    _init()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO knowledge_scans (run_at, payload) VALUES (?, ?)", (run["run_at"], json.dumps(run)))


def latest_scan() -> Optional[Dict[str, Any]]:
    import json
    _init()
    with _conn() as c:
        r = c.execute("SELECT payload FROM knowledge_scans ORDER BY run_at DESC LIMIT 1").fetchone()
    return json.loads(r["payload"]) if r else None


def approved() -> List[Dict[str, Any]]:
    _init()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM knowledge_approvals ORDER BY approved_at")]


def approve(series: str, user: str, note: str = "") -> Dict[str, Any]:
    """A person adds a proposed indicator to the challenger's inputs. Only a currently proposed one can be approved."""
    scan = latest_scan() or {}
    hit = next((r for r in scan.get("results", []) if r.get("series") == series), None)
    if not hit:
        raise LookupError(f"{series} is not in the latest scan")
    if hit.get("status") != "proposed":
        raise ValueError(f"{series} did not pass the validation gate ({hit.get('status')})")
    _init()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO knowledge_approvals (series, transform, approved_by, approved_at, note) VALUES (?,?,?,?,?)",
                  (series, hit["transform"], user, datetime.now(timezone.utc).isoformat(timespec="seconds"), note[:500]))
    return {"approved": series, "by": user}


def revoke(series: str) -> Dict[str, Any]:
    _init()
    with _conn() as c:
        n = c.execute("DELETE FROM knowledge_approvals WHERE series = ?", (series,)).rowcount
    if not n:
        raise LookupError(f"{series} is not approved")
    return {"revoked": series}
