"""
Quant Lab persistence (application DB, own tables):
  * quant_strategies  — saved user strategies (spec JSON)
  * quant_runs        — every distinct spec a user has backtested within a strategy's lineage;
                        the count is the number of trials the Deflated Sharpe corrects for
  * quant_deployments — strategies paper-traded by the Quant Trader (frozen spec + start date)
  * code_runs         — the Code Lab trial registry: every run (successful or not) with code / data /
                        config hashes, engine version, record type, holdout use and headline metrics
  * code_results      — stored Code Lab results (compressed JSON) for reopening and side-by-side comparison;
                        the newest RESULTS_KEEP per user are kept
  * paper_daily       — each deployment's live daily return, written once when the session is final and never
                        recomputed: the paper track record is append-only, like a real one
  * quant_alerts      — paper-trading alerts (an algo below its expected range, a deployment failing)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

_ready = False
RESULTS_KEEP = 50
RESULT_MAX_BYTES = 12_000_000


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS quant_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner TEXT NOT NULL,
                spec TEXT NOT NULL, template TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS quant_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, strategy_id INTEGER,
                spec_hash TEXT NOT NULL, sharpe REAL, ts TEXT);
            CREATE INDEX IF NOT EXISTS ix_quant_runs ON quant_runs(owner, strategy_id, spec_hash);
            CREATE TABLE IF NOT EXISTS quant_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER, name TEXT NOT NULL,
                owner TEXT NOT NULL, spec TEXT NOT NULL, deployed_at TEXT NOT NULL, capital REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, backtest TEXT, created_at TEXT, stopped_at TEXT);
        """)
        c.executescript("""
            CREATE TABLE IF NOT EXISTS code_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, family TEXT NOT NULL,
                code_hash TEXT, data_hash TEXT, config_hash TEXT, engine_version TEXT, record_type TEXT,
                holdout TEXT, universe TEXT, first_date TEXT, last_date TEXT, sharpe REAL, cagr REAL,
                provenance TEXT, ts TEXT);
            CREATE INDEX IF NOT EXISTS ix_code_runs ON code_runs(owner, family);
            CREATE TABLE IF NOT EXISTS code_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, label TEXT NOT NULL, code_hash TEXT,
                engine_version TEXT, record_type TEXT, summary TEXT, body BLOB NOT NULL, code TEXT, ts TEXT);
            CREATE INDEX IF NOT EXISTS ix_code_results ON code_results(owner, id);
            CREATE TABLE IF NOT EXISTS paper_daily (
                deployment_id INTEGER NOT NULL, date TEXT NOT NULL, ret REAL NOT NULL, ret_usd REAL NOT NULL,
                recorded_at TEXT, PRIMARY KEY (deployment_id, date));
            CREATE TABLE IF NOT EXISTS quant_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, deployment_id INTEGER, kind TEXT NOT NULL, day TEXT NOT NULL,
                severity TEXT NOT NULL, message TEXT NOT NULL, ts TEXT, UNIQUE (deployment_id, kind, day));
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(quant_deployments)").fetchall()}
        if "book" not in cols:                      # macro vs fundamental trader (added later; old rows classified on read)
            c.execute("ALTER TABLE quant_deployments ADD COLUMN book TEXT")
    _ready = True


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    for k in ("spec", "backtest"):
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


# ── Strategies ───────────────────────────────────────────────────────────────
def list_strategies(owner: Optional[str] = None) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = (c.execute("SELECT * FROM quant_strategies WHERE owner = ? ORDER BY updated_at DESC", (owner,))
                if owner else c.execute("SELECT * FROM quant_strategies ORDER BY updated_at DESC")).fetchall()
    return [_row(r) for r in rows]


def get_strategy(sid: int) -> Optional[Dict[str, Any]]:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM quant_strategies WHERE id = ?", (sid,)).fetchone()
    return _row(r) if r else None


def save_strategy(owner: str, spec: Dict[str, Any], sid: Optional[int] = None, template: Optional[str] = None) -> Dict[str, Any]:
    init()
    now = _now()
    with _conn() as c:
        if sid is None:
            cur = c.execute("INSERT INTO quant_strategies (name, owner, spec, template, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                            (spec["name"], owner, json.dumps(spec), template, now, now))
            sid = cur.lastrowid
        else:
            c.execute("UPDATE quant_strategies SET name = ?, spec = ?, updated_at = ? WHERE id = ?",
                      (spec["name"], json.dumps(spec), now, sid))
    return get_strategy(sid)


def delete_strategy(sid: int) -> None:
    init()
    with _conn() as c:
        c.execute("DELETE FROM quant_strategies WHERE id = ?", (sid,))


# ── Trials ───────────────────────────────────────────────────────────────────
def record_run(owner: str, strategy_id: Optional[int], spec_hash: str, sharpe: Optional[float]) -> None:
    init()
    with _conn() as c:
        q = "SELECT 1 FROM quant_runs WHERE owner = ? AND spec_hash = ? AND " + \
            ("strategy_id = ?" if strategy_id is not None else "strategy_id IS NULL")
        args = (owner, spec_hash, strategy_id) if strategy_id is not None else (owner, spec_hash)
        if not c.execute(q, args).fetchone():
            c.execute("INSERT INTO quant_runs (owner, strategy_id, spec_hash, sharpe, ts) VALUES (?,?,?,?,?)",
                      (owner, strategy_id, spec_hash, sharpe, _now()))


def trials(owner: str, strategy_id: Optional[int], spec_hash: str) -> Tuple[int, List[float]]:
    """Distinct variants tried in this lineage, counting the current one."""
    init()
    with _conn() as c:
        if strategy_id is not None:
            rows = c.execute("SELECT spec_hash, sharpe FROM quant_runs WHERE owner = ? AND strategy_id = ?", (owner, strategy_id)).fetchall()
        else:
            rows = c.execute("SELECT spec_hash, sharpe FROM quant_runs WHERE owner = ? AND strategy_id IS NULL", (owner,)).fetchall()
    seen = {r["spec_hash"]: r["sharpe"] for r in rows}
    n = len(seen) + (0 if spec_hash in seen else 1)
    return n, [s for s in seen.values() if s is not None]


# ── Deployments (Quant Trader) ───────────────────────────────────────────────
def deploy(owner: str, name: str, spec: Dict[str, Any], deployed_at: str, capital: float,
           strategy_id: Optional[int], backtest_summary: Dict[str, Any], book: Optional[str] = None) -> Dict[str, Any]:
    init()
    with _conn() as c:
        cur = c.execute("INSERT INTO quant_deployments (strategy_id, name, owner, spec, deployed_at, capital, active, backtest, created_at, book)"
                        " VALUES (?,?,?,?,?,?,1,?,?,?)",
                        (strategy_id, name, owner, json.dumps(spec), deployed_at, capital, json.dumps(backtest_summary), _now(), book))
        did = cur.lastrowid
    return get_deployment(did)


def get_deployment(did: int) -> Optional[Dict[str, Any]]:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM quant_deployments WHERE id = ?", (did,)).fetchone()
    return _row(r) if r else None


def list_deployments(active_only: bool = True) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM quant_deployments" + (" WHERE active = 1" if active_only else "") +
                         " ORDER BY id").fetchall()
    return [_row(r) for r in rows]


def stop_deployment(did: int) -> None:
    init()
    with _conn() as c:
        c.execute("UPDATE quant_deployments SET active = 0, stopped_at = ? WHERE id = ?", (_now(), did))


# ── Code Lab trial registry ──────────────────────────────────────────────────
def save_result(owner: str, label: str, result: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None,
                code: Optional[str] = None) -> Dict[str, Any]:
    """Store a Code Lab result (and its analysis) compressed; keep the newest RESULTS_KEEP per user."""
    import zlib
    init()
    body = zlib.compress(json.dumps({"result": result, "analysis": analysis}, default=str).encode(), 6)
    if len(body) > RESULT_MAX_BYTES:
        raise ValueError("Result too large to store.")
    m = result.get("metrics") or {}
    prov = result.get("provenance") or {}
    v = result.get("validation") or {}
    summary = {k: m.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown", "calmar")}
    summary.update(period=[(result.get("dates") or [None])[0], (result.get("dates") or [None])[-1]],
                   trading_costs=(result.get("costs") or {}).get("total_trading"),
                   causality=(v.get("causality") or {}).get("passed"), pbo=(v.get("pbo") or {}).get("pbo"),
                   capacity=(result.get("capacity") or {}).get("capacity"), account=result.get("account_currency"),
                   tickers=len(prov.get("universe") or []))
    with _conn() as c:
        cur = c.execute("INSERT INTO code_results (owner, label, code_hash, engine_version, record_type, summary, body, code, ts) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (owner, label[:120], prov.get("code_hash"), prov.get("engine_version"), prov.get("record_type"),
                         json.dumps(summary, default=str), body, (code or "")[:200_000], _now()))
        rid = cur.lastrowid
        c.execute("DELETE FROM code_results WHERE owner = ? AND id NOT IN (SELECT id FROM code_results WHERE owner = ? "
                  "ORDER BY id DESC LIMIT ?)", (owner, owner, RESULTS_KEEP))
    return {"id": rid, "label": label[:120], "summary": summary}


def list_results(owner: str) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT id, label, code_hash, engine_version, record_type, summary, ts FROM code_results "
                         "WHERE owner = ? ORDER BY id DESC", (owner,)).fetchall()
    return [{**dict(r), "summary": json.loads(r["summary"] or "{}")} for r in rows]


def get_result(owner: str, rid: int) -> Optional[Dict[str, Any]]:
    import zlib
    init()
    with _conn() as c:
        r = c.execute("SELECT id, label, code_hash, engine_version, record_type, summary, body, code, ts FROM code_results "
                      "WHERE owner = ? AND id = ?", (owner, rid)).fetchone()
    if not r:
        return None
    body = json.loads(zlib.decompress(r["body"]).decode())
    return {"id": r["id"], "label": r["label"], "ts": r["ts"], "code": r["code"], "summary": json.loads(r["summary"] or "{}"),
            **body}


def delete_result(owner: str, rid: int) -> bool:
    init()
    with _conn() as c:
        return c.execute("DELETE FROM code_results WHERE owner = ? AND id = ?", (owner, rid)).rowcount > 0


def live_returns(deployment_id: int) -> Dict[str, Tuple[float, float]]:
    """The frozen live record: {date: (return in the account currency, return in USD)}."""
    init()
    with _conn() as c:
        rows = c.execute("SELECT date, ret, ret_usd FROM paper_daily WHERE deployment_id = ? ORDER BY date",
                         (deployment_id,)).fetchall()
    return {r["date"]: (r["ret"], r["ret_usd"]) for r in rows}


def append_live(deployment_id: int, rows: List[Tuple[str, float, float]]) -> None:
    """Record final sessions once; a date already recorded is never overwritten."""
    if not rows:
        return
    init()
    now = _now()
    with _conn() as c:
        c.executemany("INSERT OR IGNORE INTO paper_daily (deployment_id, date, ret, ret_usd, recorded_at) VALUES (?,?,?,?,?)",
                      [(deployment_id, d, float(r), float(ru), now) for d, r, ru in rows])


def raise_alert(deployment_id: Optional[int], kind: str, severity: str, message: str) -> bool:
    """Record an alert once per deployment, kind and day; True if it is new."""
    init()
    day = _now()[:10]
    with _conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO quant_alerts (deployment_id, kind, day, severity, message, ts) VALUES (?,?,?,?,?,?)",
                        (deployment_id, kind, day, severity, message[:500], _now()))
        return cur.rowcount > 0


def recent_alerts(days: int = 7) -> List[Dict[str, Any]]:
    init()
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    with _conn() as c:
        rows = c.execute("SELECT * FROM quant_alerts WHERE day >= ? ORDER BY id DESC LIMIT 50", (since,)).fetchall()
    return [dict(r) for r in rows]


def register_code_run(owner: str, family: str, prov: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Record a Code Lab run and return the family's trial history: how many distinct specifications have been
    tried (code × config), their Sharpe ratios (for the deflated Sharpe) and how often the holdout was seen."""
    import hashlib
    init()
    cfg = hashlib.sha256(json.dumps({"costs": prov.get("costs"), "params": prov.get("params")}, sort_keys=True, default=str)
                         .encode()).hexdigest()[:16]
    with _conn() as c:
        c.execute("INSERT INTO code_runs (owner, family, code_hash, data_hash, config_hash, engine_version, record_type, "
                  "holdout, universe, first_date, last_date, sharpe, cagr, provenance, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (owner, family[:120], prov.get("code_hash"), prov.get("data_hash"), cfg, prov.get("engine_version"),
                   prov.get("record_type"), prov.get("holdout"), json.dumps(prov.get("universe") or [])[:4000],
                   prov.get("data_first"), prov.get("data_last"), metrics.get("sharpe"), metrics.get("cagr"),
                   json.dumps(prov, default=str)[:20000], _now()))
        rows = c.execute("SELECT code_hash, config_hash, sharpe, holdout, ts FROM code_runs WHERE owner = ? AND family = ? "
                         "ORDER BY id", (owner, family[:120])).fetchall()
    distinct: Dict[Tuple[str, str], Optional[float]] = {}
    for r in rows:
        distinct[(r["code_hash"], r["config_hash"])] = r["sharpe"]
    hold = prov.get("holdout")
    views = sum(1 for r in rows if hold and r["holdout"] and r["holdout"] <= (prov.get("data_last") or "9999"))
    return {"family": family, "runs": len(rows), "distinct_trials": len(distinct),
            "trial_sharpes": [s for s in distinct.values() if s is not None],
            "holdout_views": views if hold else 0, "first_run": rows[0]["ts"] if rows else None}
