"""
Auto portfolio — a systematic PAPER book that trades the stock entry model by itself.

Never places real orders: it is a self-contained simulation with its own virtual capital,
kept apart from the fund's positions, NAV and blotter (nothing here touches a broker).

Rules — the live model with the variant the backtest supported (api/stock_backtest.py):
  * Entries: today's Stock Ideas with verdict BUY (set-up strong, entry not extended, home
    market risk-on — risk-off BUY_SMALL signals are skipped; skipping them gave the best
    Sharpe and the shallowest drawdown), frontier markets excluded (no edge in the test),
    strongest set-ups first, up to `max_positions`.
  * Fill: an order created after the close fills at the NEXT session's open (as in the
    backtest); cancelled if that open is already through the stop.
  * Size: `risk_per_trade` of equity at risk to the stop, capped at `max_position` of equity
    per name and `max_gross` overall; FX-converted to USD.
  * Exits: the backtest's rules exactly (calculations.stock_backtest._exit) — stop at the
    signal's distance below entry (a gap through it fills at the open), 2R target, 63-day
    time stop; stop assumed first when both are touched in one bar.
  * Costs: half the class round-trip (stock_backtest.COST_BY_CLASS) per side.
  * Risk scaling (applied to every new position's risk):
      - drawdown control, Grossman & Zhou (1993): risk ∝ the surplus over a floor at
        (1 − max_drawdown) × peak equity — full size at the peak, zero at the limit. The
        peak is the rolling `peak_days` high (re-arms after a recovery period): in the
        backtest the all-time peak held risk at ~56% of normal for years after a drawdown
        (Sharpe 0.80) vs ~72% and Sharpe 1.06 with a one-year peak, same 15% limit;
      - volatility targeting, Moreira & Muir (2017), Harvey et al. (2018): × min(1,
        vol_target / the book's realised 20-day volatility), so size falls when markets are
        turbulent (when left-tail losses cluster).
  * Diversification: at most `max_per_sector` names per sector.

Runs after each US close (scheduler) or on demand; every action is logged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from api.calculations import stock_backtest as bt

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "capital": 1_000_000.0,        # virtual USD
    "max_positions": 15,
    "risk_per_trade": 0.005,
    "max_position": 0.10,
    "max_gross": 1.0,
    "max_drawdown": 0.15,
    "vol_target": 0.12,
    "max_per_sector": 3,
    "peak_days": 252,
    "exclude_frontier": True,
    "max_hold": bt.MAX_HOLD,
    "target_r": bt.TARGET_R,
}
IDEAS_MAX_AGE_H = 36
_lock = threading.Lock()
_run_lock = asyncio.Lock()


# ── Storage (application DB, own tables) ─────────────────────────────────────
def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


_SCHEMA = """
CREATE TABLE IF NOT EXISTS auto_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auto_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, name TEXT, created_at TEXT NOT NULL,
    created_date TEXT NOT NULL, status TEXT NOT NULL, signal_price REAL, signal_stop REAL, risk REAL,
    currency TEXT, market_class TEXT, country TEXT, sector TEXT, setup REAL, fill_date TEXT, fill_price REAL,
    shares REAL, note TEXT);
CREATE TABLE IF NOT EXISTS auto_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, symbol TEXT NOT NULL, name TEXT,
    currency TEXT, market_class TEXT, country TEXT, sector TEXT, setup REAL, shares REAL NOT NULL,
    entry_date TEXT NOT NULL, entry_price REAL NOT NULL, stop REAL NOT NULL, target REAL NOT NULL,
    fx_entry REAL NOT NULL, cost_usd REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open',
    exit_date TEXT, exit_price REAL, exit_reason TEXT, fx_exit REAL, pnl_usd REAL, r_multiple REAL);
CREATE TABLE IF NOT EXISTS auto_cash (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS auto_nav (date TEXT PRIMARY KEY, equity REAL, cash REAL, invested REAL, positions INTEGER);
CREATE TABLE IF NOT EXISTS auto_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT, message TEXT);
"""
_ready: set = set()


def _db() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = _conn()
    path = app_db_path()
    if path not in _ready:
        with _lock:
            c.executescript(_SCHEMA)
            _ready.add(path)
    return c


def get_settings() -> Dict[str, Any]:
    with _db() as c:
        rows = {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key, value FROM auto_settings")}
    return {**DEFAULTS, **{k: v for k, v in rows.items() if k in DEFAULTS}}


def update_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    clean = validate_settings(changes)
    with _db() as c:
        for k, v in clean.items():
            c.execute("INSERT INTO auto_settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (k, json.dumps(v)))
    return get_settings()


def validate_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    bounds = {"capital": (1_000, 1e9), "max_positions": (1, 50), "risk_per_trade": (0.0005, 0.03),
              "max_position": (0.01, 0.5), "max_gross": (0.1, 1.0), "max_drawdown": (0.02, 0.6),
              "max_hold": (5, 252), "target_r": (0.5, 10), "vol_target": (0.02, 0.5),
              "max_per_sector": (1, 50), "peak_days": (20, 5000)}
    out: Dict[str, Any] = {}
    for k, v in changes.items():
        if k not in DEFAULTS or v is None:
            continue
        if k in ("enabled", "exclude_frontier"):
            out[k] = bool(v)
        else:
            lo, hi = bounds[k]
            v = float(v)
            if not (lo <= v <= hi):
                raise ValueError(f"{k} must be between {lo} and {hi}")
            out[k] = int(v) if k in ("max_positions", "max_hold", "max_per_sector", "peak_days") else v
    return out


def _log(c: sqlite3.Connection, message: str, level: str = "info") -> None:
    c.execute("INSERT INTO auto_log(ts, level, message) VALUES(?, ?, ?)", (_now(), level, message))
    (logger.warning if level == "warn" else logger.info)("[auto] %s", message)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cash(c: sqlite3.Connection, capital: float) -> float:
    r = c.execute("SELECT cash FROM auto_cash WHERE id = 1").fetchone()
    if r is None:
        c.execute("INSERT INTO auto_cash(id, cash) VALUES(1, ?)", (capital,))
        return capital
    return float(r["cash"])


def _set_cash(c: sqlite3.Connection, cash: float) -> None:
    c.execute("INSERT INTO auto_cash(id, cash) VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET cash=excluded.cash", (cash,))


def reset(capital: Optional[float] = None) -> None:
    """Wipe the paper book and start again with `capital` (or the configured capital)."""
    if capital is not None:
        update_settings({"capital": capital})
    cap = get_settings()["capital"]
    with _db() as c:
        for t in ("auto_orders", "auto_positions", "auto_nav"):
            c.execute(f"DELETE FROM {t}")
        _set_cash(c, cap)
        _log(c, f"Book reset with ${cap:,.0f} virtual capital")


# ── Pure rules (tested) ──────────────────────────────────────────────────────
def signal_risk(idea: Dict[str, Any]) -> Optional[float]:
    """Risk per share = 2.5 × ATR(14), recovered exactly from the idea's levels (its stop is
    2.5 × ATR below the midpoint of the entry zone) — the same distance the backtest uses.
    Falls back to price − stop when the zone is missing."""
    lo, hi, stop, price = idea.get("entry_low"), idea.get("entry_high"), idea.get("stop"), idea.get("price")
    if all(isinstance(x, (int, float)) for x in (lo, hi, stop)) and (lo + hi) / 2 > stop:
        return (lo + hi) / 2 - stop
    if isinstance(price, (int, float)) and isinstance(stop, (int, float)) and price > stop:
        return price - stop
    return None


def candidate_orders(ideas: Sequence[Dict[str, Any]], held: set, pending: set, slots: int,
                     exclude_frontier: bool = True, sector_counts: Optional[Dict[str, int]] = None,
                     max_per_sector: int = 99) -> List[Dict[str, Any]]:
    """Ideas the book should buy next session, strongest set-ups first, at most
    `max_per_sector` names per sector including those already held or pending."""
    counts = dict(sector_counts or {})
    ranked = []
    for i in ideas:
        sym = i.get("symbol")
        price, stop = i.get("price"), i.get("stop")
        if not sym or sym in held or sym in pending or i.get("verdict") != "BUY":
            continue
        if exclude_frontier and i.get("market_class") == "Frontier":
            continue
        if not (isinstance(price, (int, float)) and isinstance(stop, (int, float)) and 0 < stop < price):
            continue
        if (price - stop) / price < bt.MIN_RISK:
            continue
        ranked.append(i)
    ranked.sort(key=lambda i: -(i.get("setup_score") or 0))
    out = []
    for i in ranked:
        if len(out) >= max(0, slots):
            break
        sec = i.get("sector") or "Unknown"
        if counts.get(sec, 0) >= max_per_sector:
            continue
        counts[sec] = counts.get(sec, 0) + 1
        out.append(i)
    return out


def drawdown_multiplier(equity: float, peak: float, max_drawdown: float) -> float:
    """Grossman-Zhou: risk scales with the surplus over the floor (1 − max_dd)·peak —
    1 at the peak, 0 at the drawdown limit."""
    if peak <= 0 or max_drawdown <= 0:
        return 1.0
    return float(min(1.0, max(0.0, (equity / peak - (1 - max_drawdown)) / max_drawdown)))


def vol_multiplier(equity_series: Sequence[float], vol_target: float, window: int = 20) -> Tuple[float, Optional[float]]:
    """(scale, realised vol): min(1, target / realised annualised vol of the book's daily
    equity over `window` days); 1 until there are 10 observations."""
    e = np.asarray([x for x in equity_series if x and x > 0], dtype=float)[-(window + 1):]
    if e.size < 11:
        return 1.0, None
    r = np.diff(e) / e[:-1]
    vol = float(r.std(ddof=1) * math.sqrt(252))
    if vol <= 0:
        return 1.0, vol
    return float(min(1.0, vol_target / vol)), vol


def size_shares(equity: float, gross_usd: float, entry: float, risk: float, usd_per_unit: float,
                settings: Dict[str, Any], risk_scale: float = 1.0) -> int:
    """Shares so that `risk_per_trade` × `risk_scale` of equity is at risk to the stop, within
    the per-name and gross caps."""
    if equity <= 0 or entry <= 0 or risk <= 0 or usd_per_unit <= 0 or risk_scale <= 0:
        return 0
    by_risk = settings["risk_per_trade"] * risk_scale * equity / (risk * usd_per_unit)
    by_name = settings["max_position"] * equity / (entry * usd_per_unit)
    room = max(0.0, settings["max_gross"] * equity - gross_usd)
    by_gross = room / (entry * usd_per_unit)
    return int(max(0, math.floor(min(by_risk, by_name, by_gross))))


def check_exit(bars: Dict[str, np.ndarray], dates: Sequence[str], entry_date: str, stop: float,
               target: float, max_hold: int) -> Optional[Tuple[str, float, str]]:
    """(exit date, price, reason) under the backtested rules, or None while still open.
    Bars from the entry session on (the entry filled at that session's open)."""
    idx = [k for k, d in enumerate(dates) if d >= entry_date]
    if not idx:
        return None
    k0 = idx[0]
    o, h, l, c = (np.asarray(bars[x][k0:], dtype=float) for x in ("Open", "High", "Low", "Close"))
    j, px, why = bt._exit(o, h, l, c, 0, stop, target, max_hold)
    if why == "open":
        return None
    return dates[k0 + j], float(px), why


# ── Market data ──────────────────────────────────────────────────────────────
def _bars(symbols: List[str]) -> Dict[str, Tuple[List[str], Dict[str, np.ndarray]]]:
    """Raw (unadjusted) daily OHLC for the last ~6 months — fills and stops are in traded prices."""
    if not symbols:
        return {}
    import yfinance as yf
    df = yf.download(sorted(set(symbols)), period="6mo", interval="1d", auto_adjust=False,
                     group_by="ticker", threads=True, progress=False)
    out = {}
    for s in set(symbols):
        try:
            sub = df[s][["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
        except Exception:
            continue
        if sub.empty:
            continue
        o, h, l, c = bt.clean_ohlc(*(sub[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close")))
        out[s] = ([d.strftime("%Y-%m-%d") for d in sub.index], {"Open": o, "High": h, "Low": l, "Close": c})
    return out


async def _fx(ccy: Optional[str]) -> Optional[float]:
    from api.routers.stock import _usd_per_unit
    return await _usd_per_unit(ccy or "USD")


def _cost(market_class: Optional[str], notional_usd: float) -> float:
    return abs(notional_usd) * bt.COST_BY_CLASS.get(market_class or "", 0.0025) / 2


# ── The run ──────────────────────────────────────────────────────────────────
async def run(force: bool = False, today: Optional[str] = None) -> Dict[str, Any]:
    """One trading cycle: fill pending orders, process exits, mark, place new orders."""
    async with _run_lock:
        s = await asyncio.to_thread(get_settings)
        if not s["enabled"] and not force:
            return {"ran": False, "reason": "auto trading is disabled"}
        today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = {"filled": [], "cancelled": [], "exited": [], "ordered": [], "paused": False}

        with _db() as c:
            pending = [dict(r) for r in c.execute("SELECT * FROM auto_orders WHERE status='pending'")]
            open_pos = [dict(r) for r in c.execute("SELECT * FROM auto_positions WHERE status='open'")]
        syms = [p["symbol"] for p in open_pos] + [o["symbol"] for o in pending]
        bars = await asyncio.to_thread(_bars, syms) if syms else {}
        ccys = {x.get("currency") for x in open_pos + pending}
        fx = {k: await _fx(k) for k in ccys}

        with _db() as c:
            cash = _cash(c, s["capital"])

            # 1. Exits on open positions (before fills: a new fill cannot exit the same run).
            for p in open_pos:
                b = bars.get(p["symbol"])
                if not b:
                    continue
                ex = check_exit(b[1], b[0], p["entry_date"], p["stop"], p["target"], int(s["max_hold"]))
                if not ex:
                    continue
                d, px, why = ex
                rate = fx.get(p["currency"]) or p["fx_entry"]
                proceeds = p["shares"] * px * rate
                cost = _cost(p["market_class"], proceeds)
                cash += proceeds - cost
                pnl = proceeds - cost - (p["shares"] * p["entry_price"] * p["fx_entry"] + p["cost_usd"])
                risk_usd = p["shares"] * (p["entry_price"] - p["stop"]) * p["fx_entry"]
                c.execute("""UPDATE auto_positions SET status='closed', exit_date=?, exit_price=?, exit_reason=?,
                             fx_exit=?, pnl_usd=?, r_multiple=?, cost_usd=cost_usd+? WHERE id=?""",
                          (d, px, why, rate, pnl, pnl / risk_usd if risk_usd > 0 else None, cost, p["id"]))
                summary["exited"].append(p["symbol"])
                _log(c, f"EXIT {p['symbol']} {p['shares']:g} @ {px:,.2f} ({why}) — P&L ${pnl:+,.0f}")

            # 2. Mark-to-market equity (positions still open).
            still = [dict(r) for r in c.execute("SELECT * FROM auto_positions WHERE status='open'")]

            def _mark(p) -> float:
                b = bars.get(p["symbol"])
                last = float(b[1]["Close"][-1]) if b else p["entry_price"]
                return p["shares"] * last * (fx.get(p["currency"]) or p["fx_entry"])
            invested = sum(_mark(p) for p in still)
            equity = cash + invested

            # Risk scaling: Grossman-Zhou drawdown control × volatility targeting.
            history = [r["equity"] for r in c.execute("SELECT equity FROM auto_nav WHERE date < ? ORDER BY date", (today,))]
            recent = history[-int(s["peak_days"]):]
            peak = max([equity] + recent + ([s["capital"]] if len(history) < int(s["peak_days"]) else []))
            dd_mult = drawdown_multiplier(equity, peak, s["max_drawdown"])
            vol_mult, book_vol = vol_multiplier(history + [equity], s["vol_target"])
            risk_scale = dd_mult * vol_mult
            summary.update(risk_scale=round(risk_scale, 3), drawdown_multiplier=round(dd_mult, 3),
                           vol_multiplier=round(vol_mult, 3), book_vol=round(book_vol, 4) if book_vol else None)
            if risk_scale < 1:
                _log(c, f"Risk scaled to {risk_scale:.0%} (drawdown control {dd_mult:.0%}"
                        f"{f', volatility target {vol_mult:.0%} at {book_vol:.0%} realised' if book_vol else ''})")

            # 3. Fill pending orders at the next session's open.
            for o in pending:
                b = bars.get(o["symbol"])
                after = [k for k, d in enumerate(b[0]) if d > o["created_date"]] if b else []
                if not after:
                    if (date.fromisoformat(today) - date.fromisoformat(o["created_date"])).days > 6:
                        c.execute("UPDATE auto_orders SET status='cancelled', note=? WHERE id=?", ("no price data", o["id"]))
                        summary["cancelled"].append(o["symbol"])
                        _log(c, f"CANCEL {o['symbol']}: no new session within 6 days", "warn")
                    continue
                k = after[0]
                d, op = b[0][k], float(b[1]["Open"][k])
                if op <= o["signal_stop"]:
                    c.execute("UPDATE auto_orders SET status='cancelled', note=? WHERE id=?",
                              (f"opened {op:,.2f}, through the stop {o['signal_stop']:,.2f}", o["id"]))
                    summary["cancelled"].append(o["symbol"])
                    _log(c, f"CANCEL {o['symbol']}: gapped below the stop at the open")
                    continue
                rate = fx.get(o["currency"])
                if not rate:
                    _log(c, f"HOLD {o['symbol']}: no FX rate for {o['currency']}", "warn")
                    continue
                risk = o["risk"]
                shares = size_shares(equity, invested, op, risk, rate, s, risk_scale)
                if shares < 1:
                    c.execute("UPDATE auto_orders SET status='cancelled', note=? WHERE id=?", ("no room within limits", o["id"]))
                    summary["cancelled"].append(o["symbol"])
                    _log(c, f"CANCEL {o['symbol']}: no room within the position / gross limits")
                    continue
                notional = shares * op * rate
                cost = _cost(o["market_class"], notional)
                cash -= notional + cost
                invested += notional
                stop, target = op - risk, op + s["target_r"] * risk
                c.execute("UPDATE auto_orders SET status='filled', fill_date=?, fill_price=?, shares=? WHERE id=?",
                          (d, op, shares, o["id"]))
                c.execute("""INSERT INTO auto_positions(order_id, symbol, name, currency, market_class, country, sector,
                             setup, shares, entry_date, entry_price, stop, target, fx_entry, cost_usd)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (o["id"], o["symbol"], o["name"], o["currency"], o["market_class"], o["country"], o["sector"],
                           o["setup"], shares, d, op, stop, target, rate, cost))
                summary["filled"].append(o["symbol"])
                _log(c, f"BUY {o['symbol']} {shares:g} @ {op:,.2f} {o['currency']} — stop {stop:,.2f}, target {target:,.2f}")
                # The fill session's own bar can already hit the stop or target.
                ex = check_exit(b[1], b[0], d, stop, target, int(s["max_hold"]))
                if ex:
                    pos_id = c.execute("SELECT id FROM auto_positions WHERE order_id=?", (o["id"],)).fetchone()["id"]
                    xd, px, why = ex
                    proceeds = shares * px * rate
                    xc = _cost(o["market_class"], proceeds)
                    cash += proceeds - xc
                    invested -= notional
                    pnl = proceeds - xc - (notional + cost)
                    rk = shares * risk * rate
                    c.execute("""UPDATE auto_positions SET status='closed', exit_date=?, exit_price=?, exit_reason=?,
                                 fx_exit=?, pnl_usd=?, r_multiple=?, cost_usd=cost_usd+? WHERE id=?""",
                              (xd, px, why, rate, pnl, pnl / rk if rk > 0 else None, xc, pos_id))
                    summary["exited"].append(o["symbol"])
                    _log(c, f"EXIT {o['symbol']} same session @ {px:,.2f} ({why}) — P&L ${pnl:+,.0f}")
            equity = cash + invested
            _set_cash(c, cash)

            # 4. At the drawdown limit the surplus is gone: no new entries.
            peak = max(peak, equity)
            dd = equity / peak - 1 if peak > 0 else 0.0
            paused = drawdown_multiplier(equity, peak, s["max_drawdown"]) <= 0
            summary["paused"] = paused
            if paused:
                _log(c, f"PAUSED: drawdown {dd:.1%} at the {s['max_drawdown']:.0%} limit — no new entries", "warn")

            # 5. New orders from today's ideas (filled at the next open).
            n_open = c.execute("SELECT COUNT(*) FROM auto_positions WHERE status='open'").fetchone()[0]
            n_pend = c.execute("SELECT COUNT(*) FROM auto_orders WHERE status='pending'").fetchone()[0]
            ideas_state = _ideas()
            if not paused and ideas_state.get("fresh"):
                held = {r["symbol"] for r in c.execute("SELECT symbol FROM auto_positions WHERE status='open'")}
                pend = {r["symbol"] for r in c.execute("SELECT symbol FROM auto_orders WHERE status='pending'")}
                sectors: Dict[str, int] = {}
                for r in c.execute("""SELECT sector FROM auto_positions WHERE status='open'
                                      UNION ALL SELECT sector FROM auto_orders WHERE status='pending'"""):
                    sectors[r["sector"] or "Unknown"] = sectors.get(r["sector"] or "Unknown", 0) + 1
                for i in candidate_orders(ideas_state["buy"], held, pend, s["max_positions"] - n_open - n_pend,
                                          s["exclude_frontier"], sectors, int(s["max_per_sector"])):
                    c.execute("""INSERT INTO auto_orders(symbol, name, created_at, created_date, status, signal_price,
                                 signal_stop, risk, currency, market_class, country, sector, setup)
                                 VALUES(?,?,?,?, 'pending', ?,?,?,?,?,?,?,?)""",
                              (i["symbol"], i.get("name"), _now(), today, i["price"], i["price"] - signal_risk(i),
                               signal_risk(i),
                               i.get("currency") or "USD", i.get("market_class"), i.get("country"), i.get("sector"),
                               i.get("setup_score")))
                    summary["ordered"].append(i["symbol"])
                    _log(c, f"ORDER {i['symbol']} for the next open (set-up {i.get('setup_score')}, "
                            f"signal {i['price']:,.2f}, stop {i['stop']:,.2f})")
            elif not ideas_state.get("fresh"):
                _log(c, f"No new orders: stock ideas are not fresh ({ideas_state.get('as_of') or 'none yet'})")

            n_open = c.execute("SELECT COUNT(*) FROM auto_positions WHERE status='open'").fetchone()[0]
            c.execute("""INSERT INTO auto_nav(date, equity, cash, invested, positions) VALUES(?,?,?,?,?)
                         ON CONFLICT(date) DO UPDATE SET equity=excluded.equity, cash=excluded.cash,
                         invested=excluded.invested, positions=excluded.positions""",
                      (today, equity, cash, invested, n_open))
            _log(c, f"Run complete: equity ${equity:,.0f}, {n_open} open, "
                    f"{len(summary['filled'])} filled, {len(summary['exited'])} exited, {len(summary['ordered'])} ordered")
        return {"ran": True, **summary, "equity": round(equity, 2)}


def _ideas() -> Dict[str, Any]:
    from api import stock_ideas as si
    cur = si.latest() or {}
    as_of = cur.get("as_of")
    fresh = False
    if as_of:
        try:
            ts = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            fresh = datetime.now(timezone.utc) - ts < timedelta(hours=IDEAS_MAX_AGE_H)
        except ValueError:
            pass
    return {"fresh": fresh, "as_of": as_of, "buy": cur.get("buy") or []}


async def close_position(pos_id: int, user: str) -> Dict[str, Any]:
    """Manual close at the latest close price."""
    async with _run_lock:
        with _db() as c:
            p = c.execute("SELECT * FROM auto_positions WHERE id=? AND status='open'", (pos_id,)).fetchone()
        if not p:
            raise KeyError(pos_id)
        p = dict(p)
        b = (await asyncio.to_thread(_bars, [p["symbol"]])).get(p["symbol"])
        if not b:
            raise RuntimeError(f"no price for {p['symbol']}")
        px, d = float(b[1]["Close"][-1]), b[0][-1]
        rate = await _fx(p["currency"]) or p["fx_entry"]
        with _db() as c:
            s = get_settings()
            cash = _cash(c, s["capital"])
            proceeds = p["shares"] * px * rate
            cost = _cost(p["market_class"], proceeds)
            pnl = proceeds - cost - (p["shares"] * p["entry_price"] * p["fx_entry"] + p["cost_usd"])
            risk_usd = p["shares"] * (p["entry_price"] - p["stop"]) * p["fx_entry"]
            _set_cash(c, cash + proceeds - cost)
            c.execute("""UPDATE auto_positions SET status='closed', exit_date=?, exit_price=?, exit_reason='manual',
                         fx_exit=?, pnl_usd=?, r_multiple=?, cost_usd=cost_usd+? WHERE id=?""",
                      (d, px, rate, pnl, pnl / risk_usd if risk_usd > 0 else None, cost, pos_id))
            _log(c, f"MANUAL EXIT {p['symbol']} @ {px:,.2f} by {user} — P&L ${pnl:+,.0f}")
        return {"closed": p["symbol"], "price": px, "pnl_usd": round(pnl, 2)}


# ── Status ───────────────────────────────────────────────────────────────────
async def status() -> Dict[str, Any]:
    s = await asyncio.to_thread(get_settings)
    with _db() as c:
        cash = _cash(c, s["capital"])
        open_pos = [dict(r) for r in c.execute("SELECT * FROM auto_positions WHERE status='open' ORDER BY entry_date")]
        closed = [dict(r) for r in c.execute("SELECT * FROM auto_positions WHERE status='closed' ORDER BY exit_date DESC, id DESC")]
        pending = [dict(r) for r in c.execute("SELECT * FROM auto_orders WHERE status='pending' ORDER BY id")]
        nav = [dict(r) for r in c.execute("SELECT * FROM auto_nav ORDER BY date")]
        log = [dict(r) for r in c.execute("SELECT ts, level, message FROM auto_log ORDER BY id DESC LIMIT 40")]
    bars = await asyncio.to_thread(_bars, [p["symbol"] for p in open_pos]) if open_pos else {}
    invested = 0.0
    for p in open_pos:
        b = bars.get(p["symbol"])
        last = float(b[1]["Close"][-1]) if b else None
        rate = await _fx(p["currency"]) if p["currency"] else 1.0
        rate = rate or p["fx_entry"]
        mv = p["shares"] * (last if last is not None else p["entry_price"]) * rate
        invested += mv
        basis = p["shares"] * p["entry_price"] * p["fx_entry"]
        risk_usd = p["shares"] * (p["entry_price"] - p["stop"]) * p["fx_entry"]
        p.update(last=last, last_date=b[0][-1] if b else None, market_value_usd=round(mv, 2),
                 unrealized_usd=round(mv - basis - p["cost_usd"], 2),
                 open_r=round((mv - basis - p["cost_usd"]) / risk_usd, 2) if risk_usd > 0 else None,
                 days_held=len([d for d in (b[0] if b else []) if d >= p["entry_date"]]))
    equity = cash + invested
    rs = [p["r_multiple"] for p in closed if p["r_multiple"] is not None]
    eqs = [n["equity"] for n in nav]
    peak = max([equity] + eqs[-int(s["peak_days"]):] + ([s["capital"]] if len(eqs) < int(s["peak_days"]) else []))
    dd_mult = drawdown_multiplier(equity, peak, s["max_drawdown"])
    vol_mult, book_vol = vol_multiplier([n["equity"] for n in nav] + [equity], s["vol_target"])
    stats = {
        "closed_trades": len(closed),
        "hit_rate": round(sum(1 for r in rs if r > 0) / len(rs), 3) if rs else None,
        "avg_r": round(float(np.mean(rs)), 3) if rs else None,
        "realized_usd": round(sum(p["pnl_usd"] or 0 for p in closed), 2),
        "unrealized_usd": round(sum(p["unrealized_usd"] for p in open_pos), 2),
        "total_return": round(equity / s["capital"] - 1, 4) if s["capital"] else None,
        "drawdown": round(equity / peak - 1, 4) if peak else None,
    }
    return {
        "mode": "paper (simulated — never routes real orders)",
        "settings": s, "equity": round(equity, 2), "cash": round(cash, 2), "invested": round(invested, 2),
        "gross": round(invested / equity, 4) if equity else None,
        "paused": dd_mult <= 0,
        "risk": {"scale": round(dd_mult * vol_mult, 3), "drawdown_multiplier": round(dd_mult, 3),
                 "vol_multiplier": round(vol_mult, 3), "book_vol": round(book_vol, 4) if book_vol else None,
                 "effective_risk_per_trade": round(s["risk_per_trade"] * dd_mult * vol_mult, 5)},
        "positions": open_pos, "pending": pending, "closed": closed[:100], "nav": nav,
        "stats": stats, "log": log, "ideas": {k: v for k, v in _ideas().items() if k != "buy"},
        "last_run": next((l["ts"] for l in log if l["message"].startswith("Run complete")), None),
    }
