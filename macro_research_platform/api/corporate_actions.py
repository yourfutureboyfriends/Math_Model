"""
Corporate actions on held positions: stock splits (and reverse splits / share consolidations).

On the ex-date a split multiplies the shares held by the ratio and divides the average cost by it: the position's
value and cost basis do not change. The USD-per-currency-unit rate at cost is per unit of the quote currency, not per
share, so it stays as it is.

Splits come from Yahoo (free). One is applied to a position automatically (the daily job) when the position was opened
before the ex-date and nothing was traded in that name on or after it — then the book is unambiguously in pre-split
shares. When there was a trade on or after the ex-date the book may already be partly in post-split shares: that
split is listed for review and only applied by a person (POST /api/v1/corporate-actions/apply).

Every application is recorded (once per book, symbol and ex-date) and audit-logged; trades in the blotter are never
rewritten — analytics that need history in today's share units scale earlier fills with `split_factor_after`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from api.portfolio_store import _conn

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Create the corporate-actions table (one row per applied split, unique per book, symbol, ex-date and kind)."""
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS corporate_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, book TEXT NOT NULL, symbol TEXT NOT NULL, ex_date TEXT NOT NULL,
            kind TEXT NOT NULL, ratio REAL NOT NULL, quantity_before REAL, quantity_after REAL,
            avg_cost_before REAL, avg_cost_after REAL, applied_at TEXT, applied_by TEXT, how TEXT,
            UNIQUE(book, symbol, ex_date, kind))""")
        c.commit()


def splits(symbol: str) -> List[Dict[str, Any]]:
    """[{ex_date, ratio}] from Yahoo, oldest first (ratio 4 = 4-for-1; 0.1 = 1-for-10 consolidation)."""
    from api.marketdata.core import _cached

    def fetch():
        import yfinance as yf
        s = yf.Ticker(symbol).splits
        if s is None or len(s) == 0:
            return []
        return [{"ex_date": d.strftime("%Y-%m-%d"), "ratio": float(r)} for d, r in s.items() if r and float(r) > 0]
    try:
        return _cached(f"splits:{symbol.upper()}", 12 * 3600, fetch) or []
    except Exception as e:                                                    # noqa: BLE001 — reported as none known
        logger.info("[corp-actions] splits %s: %s", symbol, e)
        return []


def split_factor_after(symbol: str, ts: str, known: Optional[List[Dict[str, Any]]] = None) -> float:
    """Shares today per share at `ts`: the product of the ratios of splits with ex-date after that date."""
    f = 1.0
    for s in (known if known is not None else splits(symbol)):
        if s["ex_date"] > str(ts)[:10]:
            f *= s["ratio"]
    return f


def _applied(c) -> set:
    return {(r["book"], r["symbol"], r["ex_date"]) for r in c.execute("SELECT book, symbol, ex_date FROM corporate_actions")}


def pending(today: Optional[str] = None) -> List[Dict[str, Any]]:
    """Splits with an ex-date after a position was opened (up to today) not yet applied to it."""
    from api import portfolio_store
    init_db()
    today = today or date.today().isoformat()
    pos = portfolio_store.list_positions(None)
    with _conn() as c:
        done = _applied(c)
        trades = [dict(r) for r in c.execute("SELECT ts, book, symbol FROM trades")] if c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='trades'").fetchone() else []
    out, seen = [], set()
    for p in pos:
        sym, book = str(p["symbol"]).upper(), p.get("book") or "Macro"
        entry = str(p.get("entry_date") or p.get("created_at") or "")[:10]
        for s in splits(sym):
            key = (book, sym, s["ex_date"])
            if not (entry and entry < s["ex_date"] <= today) or key in done or key in seen:
                continue
            seen.add(key)
            later = [t for t in trades if t["book"] == book and str(t["symbol"]).upper() == sym
                     and str(t["ts"])[:10] >= s["ex_date"]]
            out.append({"position_id": p["id"], "book": book, "symbol": sym, "ex_date": s["ex_date"],
                        "ratio": s["ratio"], "kind": "split" if s["ratio"] >= 1 else "consolidation",
                        "quantity": float(p["quantity"]), "avg_cost": float(p["avg_cost"]), "entry_date": entry,
                        "needs_review": bool(later),
                        "reason": (f"{len(later)} trade(s) in {sym} on or after the ex-date: the book may already be "
                                   "partly in post-split shares — check before applying") if later else None})
    return out


def apply(book: str, symbol: str, ex_date: str, ratio: float, user: str, how: str = "manual") -> Dict[str, Any]:
    """Apply one split to the position in (book, symbol): shares × ratio, average cost ÷ ratio. Once only."""
    from api import audit_store
    init_db()
    if not ratio or ratio <= 0:
        raise ValueError("the split ratio must be positive")
    symbol = symbol.upper()
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        if (book, symbol, ex_date) in _applied(c):
            c.rollback()
            raise ValueError(f"the {ex_date} split of {symbol} is already applied in {book}")
        rows = c.execute("SELECT * FROM positions WHERE book = ? AND UPPER(symbol) = ?", (book, symbol)).fetchall()
        if not rows:
            c.rollback()
            raise LookupError(f"no {symbol} position in {book}")
        q0 = sum(float(r["quantity"]) for r in rows)
        a0 = sum(float(r["quantity"]) * float(r["avg_cost"]) for r in rows) / q0 if q0 else 0.0
        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            c.execute("UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
                      (float(r["quantity"]) * ratio, round(float(r["avg_cost"]) / ratio, 6), now, r["id"]))
        rec = {"book": book, "symbol": symbol, "ex_date": ex_date, "kind": "split" if ratio >= 1 else "consolidation",
               "ratio": ratio, "quantity_before": q0, "quantity_after": q0 * ratio, "avg_cost_before": round(a0, 6),
               "avg_cost_after": round(a0 / ratio, 6), "applied_at": now, "applied_by": user, "how": how}
        c.execute(f"INSERT INTO corporate_actions ({', '.join(rec)}) VALUES ({', '.join('?' * len(rec))})", list(rec.values()))
        c.commit()
    audit_store.add_decision("corporate_action_applied",
                             f"{rec['kind'].title()} {ratio:g}:1 of {symbol} (ex {ex_date}) applied in {book}: "
                             f"{q0:g} → {q0 * ratio:g} shares, average cost {a0:.4f} → {a0 / ratio:.4f}",
                             user=user, target=f"position:{book}:{symbol}", before_state={"quantity": q0, "avg_cost": a0},
                             after_state=rec)
    return rec


def applied() -> List[Dict[str, Any]]:
    """Corporate actions already applied to the books, newest first."""
    init_db()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM corporate_actions ORDER BY ex_date DESC, id DESC")]


def apply_pending_automatically(user: str = "system") -> Dict[str, Any]:
    """The daily job: apply every unambiguous pending split; leave the rest for review."""
    done, review = [], []
    for p in pending():
        if p["needs_review"]:
            review.append(p)
            continue
        try:
            done.append(apply(p["book"], p["symbol"], p["ex_date"], p["ratio"], user, how="automatic"))
        except (ValueError, LookupError) as e:
            logger.info("[corp-actions] %s %s: %s", p["symbol"], p["ex_date"], e)
    return {"applied": done, "needs_review": review}
