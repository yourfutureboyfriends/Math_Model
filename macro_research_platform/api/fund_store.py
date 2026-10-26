"""
Fund store — SQLite persistence for fund settings, risk limits and the daily NAV record.

Shares the positions database (see portfolio_store). The NAV history is the fund's
track record: one row per calendar day, written by the daily snapshot job or on demand.
Nothing here is back-filled or estimated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.portfolio_store import _conn

DEFAULT_SETTINGS: Dict[str, Any] = {
    "fund_name": "Macro Fund",
    "capital": 10_000_000.0,        # committed capital in base currency
    "base_currency": "USD",
    "inception_date": None,         # set on first snapshot if empty
    "vol_target": 0.10,             # annualized volatility target for the rebalance engine
    "risk_free_rate": None,         # decimal; None = use the live 3M T-bill
    "realized_pnl": 0.0,            # booked P&L from closed trades (no blotter yet)
    "cost_bps": 5.0,                # transaction-cost estimate for orders
    "min_trade_pct": 0.0025,        # skip orders smaller than this fraction of NAV
    "benchmark": "SPY",             # BIFS = 50% MSCI World + 50% MSCI World Equal Weighted, in the base currency
    "brand": None,                  # the fund's look: {accent_dark, accent_light, bg_dark, band, secondary, tagline}
    "mandate": None,                # pre-trade mandate (api/handlers/pretrade_feasibility.DEFAULT_MANDATE overrides)
    # governance (api/governance.py): stage, approved-model rule, risk policy, the written mandate
    "governance": False,
    "stage": None,                  # research | prop_live | seed_readiness | fund
    "require_approved_model": False,
    "risk_policy": None,            # overrides of governance.DEFAULT_RISK_POLICY
    "capital_basis": None,          # what "capital" is, e.g. "paper notional (no external capital)"
    "mandate_text": None,
}


def init_db() -> None:
    with _conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS fund_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS risk_limits (metric TEXT PRIMARY KEY, soft REAL, hard REAL)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nav_history (
                date TEXT PRIMARY KEY,
                nav REAL NOT NULL,
                gross REAL, net REAL,
                unrealized_pnl REAL, realized_pnl REAL,
                var95_1d REAL,
                regime TEXT,
                positions INTEGER,
                recorded_at TEXT
            )
            """
        )
        # positions at each snapshot (base currency): monthly attribution by sleeve / instrument needs month-end books
        conn.execute("""CREATE TABLE IF NOT EXISTS fund_position_snapshots (
            date TEXT NOT NULL, book TEXT, symbol TEXT NOT NULL, quantity REAL, price REAL, market_value REAL,
            unrealized_pnl REAL, currency TEXT, PRIMARY KEY (date, book, symbol))""")
        # each snapshot's currency: a NAV recorded in USD must not be read as GBP after the base currency changes.
        # Rows from before this column existed were taken in the base currency of that time — the current one, since
        # the base could not be changed before multi-currency accounting (and its migration) arrived together.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(nav_history)")}
        if "currency" not in cols:
            try:
                conn.execute("ALTER TABLE nav_history ADD COLUMN currency TEXT")
                row = conn.execute("SELECT value FROM fund_settings WHERE key = 'base_currency'").fetchone()
                cur = json.loads(row["value"]) if row else DEFAULT_SETTINGS["base_currency"]
                conn.execute("UPDATE nav_history SET currency = ? WHERE currency IS NULL", (cur,))
            except Exception as e:                                             # another process added it first
                if "duplicate column" not in str(e):
                    raise
        conn.commit()


def get_settings() -> Dict[str, Any]:
    init_db()
    out = dict(DEFAULT_SETTINGS)
    with _conn() as conn:
        for row in conn.execute("SELECT key, value FROM fund_settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except ValueError:
                pass
    return out


def update_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    allowed = {k: v for k, v in changes.items() if k in DEFAULT_SETTINGS}
    with _conn() as conn:
        for k, v in allowed.items():
            conn.execute("INSERT INTO fund_settings(key, value) VALUES(?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, json.dumps(v)))
        conn.commit()
    return get_settings()


def get_limit_overrides() -> Dict[str, Dict[str, float]]:
    init_db()
    with _conn() as conn:
        return {r["metric"]: {"soft": r["soft"], "hard": r["hard"]}
                for r in conn.execute("SELECT metric, soft, hard FROM risk_limits")}


def set_limit_overrides(limits: Dict[str, Dict[str, float]]) -> None:
    init_db()
    with _conn() as conn:
        for metric, v in limits.items():
            conn.execute("INSERT INTO risk_limits(metric, soft, hard) VALUES(?, ?, ?) "
                         "ON CONFLICT(metric) DO UPDATE SET soft = excluded.soft, hard = excluded.hard",
                         (metric, float(v["soft"]), float(v["hard"])))
        conn.commit()


def record_nav(row: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert today's NAV snapshot (one row per date), in the fund's base currency (recorded on the row)."""
    init_db()
    row = {**row, "recorded_at": datetime.now(timezone.utc).isoformat(),
           "currency": row.get("currency") or get_settings().get("base_currency") or "USD"}
    cols = ["date", "nav", "gross", "net", "unrealized_pnl", "realized_pnl",
            "var95_1d", "regime", "positions", "recorded_at", "currency"]
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO nav_history({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
            "ON CONFLICT(date) DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in cols[1:]),
            [row.get(c) for c in cols])
        conn.commit()
    return row


def record_positions(day: str, positions: List[Dict[str, Any]], currency: str) -> int:
    """Replace the day's position snapshot (values in the base currency)."""
    init_db()
    agg: Dict[tuple, Dict[str, Any]] = {}
    for p in positions:
        k = (p.get("book") or "Macro", str(p["symbol"]).upper())
        g = agg.setdefault(k, {"quantity": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0, "price": p.get("current_price")})
        g["quantity"] += float(p.get("quantity") or 0)
        g["market_value"] += float(p.get("market_value") or 0)
        g["unrealized_pnl"] += float(p.get("unrealized_pnl") or 0)
    with _conn() as conn:
        conn.execute("DELETE FROM fund_position_snapshots WHERE date = ?", (day,))
        conn.executemany("INSERT INTO fund_position_snapshots (date, book, symbol, quantity, price, market_value, unrealized_pnl, "
                         "currency) VALUES (?,?,?,?,?,?,?,?)",
                         [(day, b, s, g["quantity"], g["price"], round(g["market_value"], 2), round(g["unrealized_pnl"], 2),
                           currency) for (b, s), g in agg.items()])
        conn.commit()
    return len(agg)


def position_snapshot(on_or_before: str, currency: Optional[str] = None) -> Dict[str, Any]:
    """The last position snapshot on or before a date: {date, rows}."""
    init_db()
    with _conn() as conn:
        r = conn.execute("SELECT MAX(date) AS d FROM fund_position_snapshots WHERE date <= ?"
                         + (" AND currency = ?" if currency else ""),
                         (on_or_before, currency) if currency else (on_or_before,)).fetchone()
        if not r or not r["d"]:
            return {"date": None, "rows": []}
        rows = [dict(x) for x in conn.execute("SELECT * FROM fund_position_snapshots WHERE date = ?", (r["d"],))]
    return {"date": r["d"], "rows": rows}


def nav_history(limit: Optional[int] = None, currency: Optional[str] = "current") -> List[Dict[str, Any]]:
    """The track record in one currency: by default the fund's current base currency, from the last change of base
    currency on (a series in another currency is never mixed in or relabelled). currency=None: every row."""
    init_db()
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM nav_history ORDER BY date")]
    if currency:
        cur = (get_settings().get("base_currency") or "USD") if currency == "current" else currency.upper()
        last_other = max((i for i, r in enumerate(rows) if (r.get("currency") or cur) != cur), default=-1)
        rows = rows[last_other + 1:]                  # the current series: after the last row in another currency
    return rows[-limit:] if limit else rows


def nav_series() -> List[Dict[str, Any]]:
    """The NAV record split into its runs by currency: [{currency, start, end, snapshots, current}]."""
    rows = nav_history(currency=None)
    cur = get_settings().get("base_currency") or "USD"
    runs: List[Dict[str, Any]] = []
    for r in rows:
        c = r.get("currency") or cur
        if runs and runs[-1]["currency"] == c:
            runs[-1]["end"], runs[-1]["snapshots"] = r["date"], runs[-1]["snapshots"] + 1
        else:
            runs.append({"currency": c, "start": r["date"], "end": r["date"], "snapshots": 1})
    for i, run in enumerate(runs):
        run["current"] = i == len(runs) - 1 and run["currency"] == cur
    return runs
