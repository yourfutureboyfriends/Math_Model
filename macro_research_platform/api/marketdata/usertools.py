"""
Per-user tools for the Markets mode (application DB, own tables):

  * watchlists  [W]     named lists of any instruments
  * alerts      [ALRT]  price above/below, daily move up/down — checked every 5 minutes by
                        the scheduler (and on demand); a triggered alert is shown in the
                        terminal until seen
  * journal     [JRNL]  trades and ideas with thesis, entry/exit and outcome; P&L computed
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_ready = False
_lock = threading.Lock()
ALERT_KINDS = {"above": "Price rises above", "below": "Price falls below", "change_up": "Day's gain exceeds %", "change_down": "Day's loss exceeds %"}
MAX_WATCHLISTS, MAX_SYMBOLS, MAX_ALERTS = 30, 200, 200


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
            CREATE TABLE IF NOT EXISTS mkt_watchlists (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, name TEXT NOT NULL,
                symbols TEXT NOT NULL DEFAULT '[]', created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS mkt_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, symbol TEXT NOT NULL,
                kind TEXT NOT NULL, value REAL NOT NULL, note TEXT, active INTEGER NOT NULL DEFAULT 1, created_at TEXT,
                triggered_at TEXT, triggered_price REAL, seen INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS mkt_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, date TEXT NOT NULL,
                symbol TEXT, side TEXT NOT NULL, quantity REAL, entry REAL, exit REAL, exit_date TEXT, thesis TEXT, outcome TEXT,
                tags TEXT, status TEXT NOT NULL DEFAULT 'open', created_at TEXT, updated_at TEXT);
        """)
    _ready = True


def _clean_symbols(symbols: List[str]) -> List[str]:
    from api.quant.data import clean_symbols
    ok, bad = clean_symbols(symbols)
    if bad:
        raise ValueError(f"Invalid symbol(s): {', '.join(bad[:5])}")
    return ok[:MAX_SYMBOLS]


# ── Watchlists ───────────────────────────────────────────────────────────────
def list_watchlists(owner: str) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM mkt_watchlists WHERE owner = ? ORDER BY id", (owner,)).fetchall()
    out = [{**dict(r), "symbols": json.loads(r["symbols"])} for r in rows]
    if not out:                                   # a starter list so the screen is never empty
        out = [create_watchlist(owner, "My watchlist", ["SPY", "QQQ", "^VIX", "EURUSD=X", "GC=F", "BTC-USD"])]
    return out


def create_watchlist(owner: str, name: str, symbols: List[str]) -> Dict[str, Any]:
    init()
    name = (name or "").strip()[:60] or "Watchlist"
    syms = _clean_symbols(symbols or [])
    with _conn() as c:
        if c.execute("SELECT COUNT(*) FROM mkt_watchlists WHERE owner = ?", (owner,)).fetchone()[0] >= MAX_WATCHLISTS:
            raise ValueError(f"At most {MAX_WATCHLISTS} watchlists.")
        cur = c.execute("INSERT INTO mkt_watchlists (owner, name, symbols, created_at, updated_at) VALUES (?,?,?,?,?)",
                        (owner, name, json.dumps(syms), _now(), _now()))
        wid = cur.lastrowid
    return {"id": wid, "owner": owner, "name": name, "symbols": syms}


def update_watchlist(owner: str, wid: int, name: Optional[str], symbols: Optional[List[str]]) -> Dict[str, Any]:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM mkt_watchlists WHERE id = ? AND owner = ?", (wid, owner)).fetchone()
        if not r:
            raise LookupError("Watchlist not found.")
        new_name = (name.strip()[:60] if name is not None else r["name"]) or r["name"]
        syms = _clean_symbols(symbols) if symbols is not None else json.loads(r["symbols"])
        c.execute("UPDATE mkt_watchlists SET name = ?, symbols = ?, updated_at = ? WHERE id = ?", (new_name, json.dumps(syms), _now(), wid))
    return {"id": wid, "owner": owner, "name": new_name, "symbols": syms}


def delete_watchlist(owner: str, wid: int) -> None:
    init()
    with _conn() as c:
        if not c.execute("DELETE FROM mkt_watchlists WHERE id = ? AND owner = ?", (wid, owner)).rowcount:
            raise LookupError("Watchlist not found.")


def quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    """Last price, day change and a 1-month sparkline for many instruments in one download."""
    import pandas as pd
    import yfinance as yf
    from api.marketdata.core import _cached, _f
    syms = _clean_symbols(symbols)[:100]
    if not syms:
        return []

    def fetch():
        try:
            df = yf.download(syms, period="1mo", interval="1d", auto_adjust=False, group_by="ticker", progress=False, threads=True)
        except Exception as e:
            raise RuntimeError(f"Quotes unavailable: {e}")
        out = []
        for s in syms:
            try:
                c = (df[s] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
            except Exception:
                c = pd.Series(dtype=float)
            if not s.endswith("-USD"):                 # weekend prints (junk on thin FX pairs) — crypto trades 7 days
                c = c[c.index.dayofweek < 5]
            if len(c) == 0:
                out.append({"symbol": s, "price": None})
                continue
            out.append({"symbol": s, "price": float(c.iloc[-1]), "date": c.index[-1].strftime("%Y-%m-%d"),
                        "change_1d": float(c.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None,
                        "change_1m": float(c.iloc[-1] / c.iloc[0] - 1) if len(c) > 1 else None,
                        "spark": [round(float(x), 6) for x in c]})
        return out
    return _cached(f"quotes:{','.join(syms)}", 60, fetch)


# ── Alerts ───────────────────────────────────────────────────────────────────
def list_alerts(owner: str) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM mkt_alerts WHERE owner = ? ORDER BY active DESC, id DESC", (owner,)).fetchall()
    return [{**dict(r), "label": ALERT_KINDS.get(r["kind"], r["kind"])} for r in rows]


def create_alert(owner: str, symbol: str, kind: str, value: float, note: Optional[str] = None) -> Dict[str, Any]:
    init()
    if kind not in ALERT_KINDS:
        raise ValueError(f"kind must be one of {', '.join(ALERT_KINDS)}")
    sym = _clean_symbols([symbol])[0] if symbol else None
    if not sym:
        raise ValueError("Symbol required.")
    if kind in ("change_up", "change_down") and not 0 < value <= 100:
        raise ValueError("Move threshold must be between 0 and 100%.")
    if kind in ("above", "below") and value <= 0:
        raise ValueError("Price level must be positive.")
    if kind in ("above", "below"):       # a level that's already met would fire on the next check
        try:
            px = next((x.get("price") for x in quotes([sym]) if x["symbol"] == sym), None)
        except Exception:
            px = None
        if px is not None and fires(kind, value, px, None):
            raise ValueError(f"{sym} is already {'at or above' if kind == 'above' else 'at or below'} {value:g} "
                             f"(last {px:,.4g}) — the alert would fire immediately.")
    with _conn() as c:
        if c.execute("SELECT COUNT(*) FROM mkt_alerts WHERE owner = ? AND active = 1", (owner,)).fetchone()[0] >= MAX_ALERTS:
            raise ValueError(f"At most {MAX_ALERTS} active alerts.")
        cur = c.execute("INSERT INTO mkt_alerts (owner, symbol, kind, value, note, created_at) VALUES (?,?,?,?,?,?)",
                        (owner, sym, kind, float(value), (note or "")[:200], _now()))
        aid = cur.lastrowid
    return next(a for a in list_alerts(owner) if a["id"] == aid)


def delete_alert(owner: str, aid: int) -> None:
    init()
    with _conn() as c:
        if not c.execute("DELETE FROM mkt_alerts WHERE id = ? AND owner = ?", (aid, owner)).rowcount:
            raise LookupError("Alert not found.")


def mark_seen(owner: str) -> int:
    init()
    with _conn() as c:
        return c.execute("UPDATE mkt_alerts SET seen = 1 WHERE owner = ? AND triggered_at IS NOT NULL AND seen = 0", (owner,)).rowcount


def triggered_unseen(owner: str) -> List[Dict[str, Any]]:
    return [a for a in list_alerts(owner) if a["triggered_at"] and not a["seen"]]


def fires(kind: str, value: float, price: Optional[float], change: Optional[float]) -> bool:
    if kind == "above":
        return price is not None and price >= value
    if kind == "below":
        return price is not None and price <= value
    if kind == "change_up":
        return change is not None and change * 100 >= value
    if kind == "change_down":
        return change is not None and -change * 100 >= value
    return False


def check_alerts() -> Dict[str, Any]:
    """Evaluate every active alert against the latest prices (all users)."""
    init()
    with _lock:
        with _conn() as c:
            active = [dict(r) for r in c.execute("SELECT * FROM mkt_alerts WHERE active = 1").fetchall()]
        if not active:
            return {"checked": 0, "triggered": 0}
        q = {x["symbol"]: x for x in quotes(sorted({a["symbol"] for a in active}))}
        fired = 0
        with _conn() as c:
            for a in active:
                x = q.get(a["symbol"]) or {}
                if fires(a["kind"], a["value"], x.get("price"), x.get("change_1d")):
                    c.execute("UPDATE mkt_alerts SET active = 0, triggered_at = ?, triggered_price = ?, seen = 0 WHERE id = ?",
                              (_now(), x.get("price"), a["id"]))
                    fired += 1
        if fired:
            logger.info("[alerts] %d alert(s) triggered", fired)
        return {"checked": len(active), "triggered": fired}


# ── Journal ──────────────────────────────────────────────────────────────────
SIDES = ("long", "short", "idea")
J_FIELDS = ("date", "symbol", "side", "quantity", "entry", "exit", "exit_date", "thesis", "outcome", "tags", "status")


def _journal_row(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    pnl = pct = None
    if d["entry"] and d["exit"] is not None and d["side"] in ("long", "short"):
        sign = 1 if d["side"] == "long" else -1
        pct = sign * (d["exit"] / d["entry"] - 1)
        pnl = sign * (d["exit"] - d["entry"]) * (d["quantity"] or 0) if d["quantity"] else None
    d["return_pct"], d["pnl"] = pct, pnl
    d["tags"] = [t for t in (d["tags"] or "").split(",") if t]
    return d


def list_journal(owner: str) -> Dict[str, Any]:
    init()
    with _conn() as c:
        rows = [_journal_row(r) for r in c.execute("SELECT * FROM mkt_journal WHERE owner = ? ORDER BY date DESC, id DESC", (owner,)).fetchall()]
    closed = [r for r in rows if r["return_pct"] is not None]
    wins = [r for r in closed if r["return_pct"] > 0]
    stats = {"entries": len(rows), "closed": len(closed), "open": sum(1 for r in rows if r["status"] == "open"),
             "win_rate": len(wins) / len(closed) if closed else None,
             "avg_return": sum(r["return_pct"] for r in closed) / len(closed) if closed else None,
             "avg_win": sum(r["return_pct"] for r in wins) / len(wins) if wins else None,
             "avg_loss": (sum(r["return_pct"] for r in closed if r["return_pct"] <= 0) / max(1, len(closed) - len(wins))) if len(closed) > len(wins) else None,
             "total_pnl": sum(r["pnl"] for r in closed if r["pnl"] is not None) if any(r["pnl"] is not None for r in closed) else None}
    return {"entries": rows, "stats": stats}


def _validate_journal(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: d.get(k) for k in J_FIELDS if k in d}
    if "side" in out and out["side"] not in SIDES:
        raise ValueError("side must be long, short or idea")
    if out.get("symbol"):
        out["symbol"] = _clean_symbols([out["symbol"]])[0]
    for k in ("quantity", "entry", "exit"):
        if out.get(k) in ("", None):
            out[k] = None
        elif k in out:
            out[k] = float(out[k])
            if out[k] < 0:
                raise ValueError(f"{k} cannot be negative")
    for k in ("thesis", "outcome"):
        if k in out and out[k] is not None:
            out[k] = str(out[k])[:4000]
    if "tags" in out:
        t = out["tags"]
        out["tags"] = ",".join(x.strip()[:30] for x in (t if isinstance(t, list) else str(t or "").split(",")) if x.strip())[:300]
    if out.get("status") not in (None, "open", "closed"):
        raise ValueError("status must be open or closed")
    if "exit" in out and out["exit"] is not None and "status" not in out:
        out["status"] = "closed"
    if out.get("exit") is not None and not d.get("exit_date"):     # closing a trade dates it, unless given
        out["exit_date"] = datetime.now().strftime("%Y-%m-%d")
    return out


def create_journal(owner: str, d: Dict[str, Any]) -> Dict[str, Any]:
    init()
    v = _validate_journal(d)
    v.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    v.setdefault("side", "idea")
    v.setdefault("status", "open")
    cols = list(v)
    with _conn() as c:
        cur = c.execute(f"INSERT INTO mkt_journal (owner, {', '.join(cols)}, created_at, updated_at) VALUES (?, {', '.join('?' * len(cols))}, ?, ?)",
                        (owner, *[v[k] for k in cols], _now(), _now()))
        jid = cur.lastrowid
        return _journal_row(c.execute("SELECT * FROM mkt_journal WHERE id = ?", (jid,)).fetchone())


def update_journal(owner: str, jid: int, d: Dict[str, Any]) -> Dict[str, Any]:
    init()
    v = _validate_journal(d)
    if not v:
        raise ValueError("Nothing to update.")
    with _conn() as c:
        if not c.execute("SELECT 1 FROM mkt_journal WHERE id = ? AND owner = ?", (jid, owner)).fetchone():
            raise LookupError("Journal entry not found.")
        c.execute(f"UPDATE mkt_journal SET {', '.join(f'{k} = ?' for k in v)}, updated_at = ? WHERE id = ?", (*v.values(), _now(), jid))
        return _journal_row(c.execute("SELECT * FROM mkt_journal WHERE id = ?", (jid,)).fetchone())


def delete_journal(owner: str, jid: int) -> None:
    init()
    with _conn() as c:
        if not c.execute("DELETE FROM mkt_journal WHERE id = ? AND owner = ?", (jid, owner)).rowcount:
            raise LookupError("Journal entry not found.")
