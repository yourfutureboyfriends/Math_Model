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
    """Upsert today's NAV snapshot (one row per date)."""
    init_db()
    row = {**row, "recorded_at": datetime.now(timezone.utc).isoformat()}
    cols = ["date", "nav", "gross", "net", "unrealized_pnl", "realized_pnl",
            "var95_1d", "regime", "positions", "recorded_at"]
    with _conn() as conn:
        conn.execute(
            f"INSERT INTO nav_history({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
            "ON CONFLICT(date) DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in cols[1:]),
            [row.get(c) for c in cols])
        conn.commit()
    return row


def nav_history(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM nav_history ORDER BY date")]
    return rows[-limit:] if limit else rows
