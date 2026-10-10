"""
Macro Trader — a PAPER book that follows the systematic macro model (api/model): growth and
inflation factors → regime probabilities → Black–Litterman expected returns → a
volatility-targeted allocation across 10 asset-class ETFs (SPY, EFA, EEM, TLT, IEF, TIP,
LQD, HYG, GLD, DBC). Kept apart from the Quant Trader, the auto stock book and the fund.

Cycle (after each US close, or on demand):
  1. fill orders placed at the previous close at the next session's OPEN (cost per side);
  2. mark the book to the latest close (one NAV row per trading day);
  3. read the model's target weights (tactical by default) and rebalance — placing orders
     for the next open — when the month has changed since the last rebalance, the most
     likely regime has changed, or any position has drifted more than `drift_threshold`
     from its target. Uninvested weight stays in cash (0% interest — conservative).
Never places real orders.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {"enabled": True, "capital": 1_000_000.0, "portfolio": "tactical",
                            "drift_threshold": 0.05, "cost_bps": 5.0}
ETFS = ["SPY", "EFA", "EEM", "TLT", "IEF", "TIP", "LQD", "HYG", "GLD", "DBC"]
_lock = threading.Lock()
_ready = False


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db() -> sqlite3.Connection:
    global _ready
    c = _conn()
    if not _ready:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS macro_trader_state (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS macro_trader_positions (symbol TEXT PRIMARY KEY, shares REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS macro_trader_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, shares REAL, placed_on TEXT,
                status TEXT, fill_date TEXT, fill_price REAL, cost REAL, reason TEXT);
            CREATE TABLE IF NOT EXISTS macro_trader_nav (date TEXT PRIMARY KEY, nav REAL, cash REAL, gross REAL);
            CREATE TABLE IF NOT EXISTS macro_trader_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, message TEXT);
        """)
        _ready = True
    return c


def _get(c, k, default=None):
    r = c.execute("SELECT v FROM macro_trader_state WHERE k = ?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def _put(c, k, v) -> None:
    c.execute("INSERT INTO macro_trader_state (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, json.dumps(v)))


def _log(c, msg: str, level: str = "info") -> None:
    c.execute("INSERT INTO macro_trader_log (ts, level, message) VALUES (?,?,?)", (_now(), level, msg))


def get_settings() -> Dict[str, Any]:
    with _db() as c:
        return {**DEFAULTS, **(_get(c, "settings", {}) or {})}


def update_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    s = get_settings()
    for k, v in changes.items():
        if k not in DEFAULTS or k == "capital":
            continue
        if k == "portfolio" and v not in ("tactical", "strategic"):
            raise ValueError("portfolio must be 'tactical' or 'strategic'")
        if k == "drift_threshold" and not 0.01 <= float(v) <= 0.5:
            raise ValueError("drift threshold must be 1%–50%")
        if k == "cost_bps" and not 0 <= float(v) <= 100:
            raise ValueError("cost must be 0–100 bp")
        s[k] = v if k in ("enabled", "portfolio") else float(v)
    with _db() as c:
        _put(c, "settings", s)
        _log(c, "Settings: " + ", ".join(f"{k} → {v}" for k, v in changes.items()))
    return s


def reset(capital: Optional[float] = None) -> None:
    with _lock, _db() as c:
        s = {**get_settings()}
        if capital is not None:
            if not 10_000 <= capital <= 1_000_000_000:
                raise ValueError("capital must be $10k–$1bn")
            s["capital"] = float(capital)
        for t in ("macro_trader_positions", "macro_trader_orders", "macro_trader_nav"):
            c.execute(f"DELETE FROM {t}")
        _put(c, "settings", s)
        _put(c, "cash", s["capital"])
        for k in ("last_rebalance", "last_regime", "started"):
            c.execute("DELETE FROM macro_trader_state WHERE k = ?", (k,))
        _log(c, f"Book reset with ${s['capital']:,.0f}")


def _bars() -> Dict[str, Any]:
    from api.quant import data as qdata
    got, _ = qdata.load(ETFS)
    return got


async def _targets(which: str) -> Dict[str, Any]:
    from api.model.engine import run_model
    res = await run_model(None, user="system")
    p = (res.get("portfolios") or {}).get(which) or {}
    etfs = p.get("etfs") or {}
    w = {etfs[a]: float(x) for a, x in (p.get("weights") or {}).items() if a in etfs}
    return {"weights": w, "cash": p.get("cash"), "regime": (res.get("regime") or {}).get("most_likely"),
            "as_of": res.get("as_of"), "expected_vol": p.get("expected_vol"),
            "expected_excess_return": p.get("expected_excess_return")}


async def run(force: bool = False) -> Dict[str, Any]:
    s = get_settings()
    if not s["enabled"] and not force:
        return {"ran": False, "reason": "disabled"}
    tg = await _targets(s["portfolio"])
    import asyncio
    bars = await asyncio.to_thread(_bars)
    return await asyncio.to_thread(_cycle, s, tg, bars)


def _cycle(s: Dict[str, Any], tg: Dict[str, Any], bars: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ran": True, "filled": 0, "orders": 0, "rebalanced": False}
    cost_rate = s["cost_bps"] / 1e4
    with _lock, _db() as c:
        if _get(c, "cash") is None:
            _put(c, "cash", s["capital"])
            _put(c, "started", None)
            _log(c, f"Book opened with ${s['capital']:,.0f}")
        cash = float(_get(c, "cash"))
        # 1) fills at the next open after the order's date
        for o in c.execute("SELECT * FROM macro_trader_orders WHERE status = 'pending'").fetchall():
            b = bars.get(o["symbol"])
            if b is None:
                continue
            after = b[b.index > o["placed_on"]]
            if after.empty or not math.isfinite(after["Open"].iloc[0]):
                continue
            px = float(after["Open"].iloc[0])
            d = after.index[0].strftime("%Y-%m-%d")
            notional = o["shares"] * px
            cost = abs(notional) * cost_rate
            cash -= notional + cost
            r = c.execute("SELECT shares FROM macro_trader_positions WHERE symbol = ?", (o["symbol"],)).fetchone()
            sh = (r["shares"] if r else 0.0) + o["shares"]
            if abs(sh) < 1e-6:
                c.execute("DELETE FROM macro_trader_positions WHERE symbol = ?", (o["symbol"],))
            else:
                c.execute("INSERT INTO macro_trader_positions (symbol, shares) VALUES (?, ?) ON CONFLICT(symbol) DO UPDATE SET shares = excluded.shares",
                          (o["symbol"], sh))
            c.execute("UPDATE macro_trader_orders SET status = 'filled', fill_date = ?, fill_price = ?, cost = ? WHERE id = ?",
                      (d, px, cost, o["id"]))
            out["filled"] += 1
            if _get(c, "started") is None:
                _put(c, "started", d)
        _put(c, "cash", cash)
        # 2) mark to market at the latest common close
        pos = {r["symbol"]: r["shares"] for r in c.execute("SELECT * FROM macro_trader_positions").fetchall()}
        last_dates = [b.index.max() for b in bars.values()]
        if not last_dates:
            _log(c, "No price data — cycle skipped", "warning")
            return {**out, "ran": False, "reason": "no prices"}
        asof = min(last_dates)
        px = {sym: float(b["Close"][b.index <= asof].iloc[-1]) for sym, b in bars.items() if (b.index <= asof).any()}
        mv = {sym: sh * px[sym] for sym, sh in pos.items() if sym in px}
        nav = cash + sum(mv.values())
        d = asof.strftime("%Y-%m-%d")
        c.execute("INSERT INTO macro_trader_nav (date, nav, cash, gross) VALUES (?,?,?,?) ON CONFLICT(date) DO UPDATE SET nav = excluded.nav, cash = excluded.cash, gross = excluded.gross",
                  (d, nav, cash, sum(abs(v) for v in mv.values())))
        # 3) rebalance decision
        cur_w = {sym: v / nav for sym, v in mv.items()} if nav > 0 else {}
        target = tg["weights"]
        drift = max([abs(target.get(k, 0) - cur_w.get(k, 0)) for k in set(target) | set(cur_w)] or [0])
        last = _get(c, "last_rebalance")
        reasons = []
        if not pos and not c.execute("SELECT 1 FROM macro_trader_orders WHERE status = 'pending'").fetchone():
            reasons.append("initial allocation")
        if last and last[:7] != d[:7]:
            reasons.append("monthly rebalance")
        if tg["regime"] and _get(c, "last_regime") and tg["regime"] != _get(c, "last_regime"):
            reasons.append(f"regime change → {tg['regime']}")
        if drift > s["drift_threshold"]:
            reasons.append(f"drift {drift:.1%} > {s['drift_threshold']:.0%}")
        pending = c.execute("SELECT 1 FROM macro_trader_orders WHERE status = 'pending'").fetchone()
        if reasons and not pending:
            c.execute("UPDATE macro_trader_orders SET status = 'cancelled' WHERE status = 'pending'")
            for sym in sorted(set(target) | set(pos)):
                if sym not in px:
                    continue
                want = target.get(sym, 0.0) * nav / px[sym]
                delta = want - pos.get(sym, 0.0)
                if abs(delta * px[sym]) < max(500.0, nav * 0.002):      # skip dust trades
                    continue
                c.execute("INSERT INTO macro_trader_orders (symbol, shares, placed_on, status, reason) VALUES (?,?,?,?,?)",
                          (sym, round(delta, 4), d, "pending", "; ".join(reasons)))
                out["orders"] += 1
            _put(c, "last_rebalance", d)
            _put(c, "last_regime", tg["regime"])
            out["rebalanced"] = True
            _log(c, f"Rebalance ({'; '.join(reasons)}): {out['orders']} orders for the next open; model regime {tg['regime']}")
        elif out["filled"]:
            _log(c, f"Filled {out['filled']} orders at the open")
        out.update(nav=round(nav, 2), as_of=d)
    return out


async def status() -> Dict[str, Any]:
    import asyncio
    s = get_settings()
    try:
        tg = await _targets(s["portfolio"])
    except Exception as e:
        tg = {"weights": {}, "regime": None, "error": str(e)[:200]}
    bars = await asyncio.to_thread(_bars)
    with _db() as c:
        cash = float(_get(c, "cash", s["capital"]) or s["capital"])
        pos = {r["symbol"]: r["shares"] for r in c.execute("SELECT * FROM macro_trader_positions").fetchall()}
        navs = [dict(r) for r in c.execute("SELECT * FROM macro_trader_nav ORDER BY date").fetchall()]
        orders = [dict(r) for r in c.execute("SELECT * FROM macro_trader_orders ORDER BY id DESC LIMIT 40").fetchall()]
        log = [dict(r) for r in c.execute("SELECT * FROM macro_trader_log ORDER BY id DESC LIMIT 30").fetchall()]
        started, last_reb = _get(c, "started"), _get(c, "last_rebalance")
    px = {sym: float(b["Close"].iloc[-1]) for sym, b in bars.items()}
    mv = {sym: sh * px.get(sym, float("nan")) for sym, sh in pos.items()}
    nav = cash + sum(v for v in mv.values() if math.isfinite(v))
    rows = []
    for sym in sorted(set(pos) | set(tg.get("weights") or {}), key=lambda x: ETFS.index(x) if x in ETFS else 99):
        v = mv.get(sym, 0.0)
        rows.append({"symbol": sym, "shares": round(pos.get(sym, 0.0), 2), "price": px.get(sym),
                     "value": round(v, 2), "weight": round(v / nav, 4) if nav else None,
                     "target": (tg.get("weights") or {}).get(sym, 0.0)})
    perf = None
    if len(navs) >= 3:
        from api.quant import robust
        eq = np.array([n["nav"] for n in navs])
        r = eq[1:] / eq[:-1] - 1
        perf = robust.metrics(r, [n["date"] for n in navs[1:]]) if r.size >= 2 else None
    return {"settings": s, "nav": round(nav, 2), "cash": round(cash, 2), "capital": s["capital"],
            "return": round(nav / s["capital"] - 1, 4), "started": started, "last_rebalance": last_reb,
            "positions": rows, "model": {k: tg.get(k) for k in ("regime", "as_of", "cash", "expected_vol", "expected_excess_return", "error")},
            "nav_history": [{"date": n["date"], "nav": round(n["nav"], 2)} for n in navs][-750:],
            "performance": perf, "orders": orders, "log": log}
