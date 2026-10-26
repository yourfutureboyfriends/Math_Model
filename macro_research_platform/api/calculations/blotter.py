"""
Trade blotter accounting — pure, tested.

Average-cost position accounting per (book, symbol):
  * a fill in the SAME direction as the position adds to it at a quantity-weighted average
    cost;
  * a fill in the OPPOSITE direction closes up to the open quantity, realizing
    (fill_price − avg_cost) × closed_qty × sign(position), and any remainder flips the
    position at the fill price.

Cash (the fund has no external cash flows yet):
    cash = capital − Σ (avg_cost × qty) over open positions + realized P&L − commissions
so NAV = cash + Σ market value = capital + realized + unrealized − commissions, consistent
with positions entered manually before the blotter existed.
"""
from __future__ import annotations

from typing import Dict, Iterable, Tuple


def apply_fill(qty: float, avg_cost: float, fill_qty: float, fill_price: float) -> Tuple[float, float, float]:
    """Apply a signed fill (+buy / −sell) to a position (qty, avg_cost).

    Returns (new_qty, new_avg_cost, realized_pnl). new_avg_cost is 0 when flat.
    """
    if fill_qty == 0:
        return qty, avg_cost, 0.0
    if qty == 0 or (qty > 0) == (fill_qty > 0):
        new_qty = qty + fill_qty
        new_avg = (qty * avg_cost + fill_qty * fill_price) / new_qty
        return new_qty, new_avg, 0.0
    closed = min(abs(qty), abs(fill_qty))
    sign = 1.0 if qty > 0 else -1.0
    realized = (fill_price - avg_cost) * closed * sign
    new_qty = qty + fill_qty
    if abs(new_qty) < 1e-12:
        return 0.0, 0.0, realized
    if (new_qty > 0) == (qty > 0):          # partial close: cost basis unchanged
        return new_qty, avg_cost, realized
    return new_qty, fill_price, realized   # flipped: remainder opened at the fill price


def commission(notional: float, cost_bps: float) -> float:
    """Commission on a fill: |notional| × cost_bps / 10,000, rounded to cents."""
    return round(abs(notional) * cost_bps / 1e4, 2)


def cash_balance(capital: float, positions: Iterable[Dict], realized_pnl: float,
                 commissions: float) -> float:
    """capital − cost basis of open positions + realized P&L − commissions, all in the fund's base currency.
    Positions carry `cost_basis` in base currency once enriched (quantity × avg cost × FX at cost); a raw row
    without it is taken at face value (a base-currency listing)."""
    basis = sum(float(p["cost_basis"]) if p.get("cost_basis") is not None
                else float(p.get("quantity") or 0) * float(p.get("avg_cost") or 0) for p in positions)
    return round(capital - basis + realized_pnl - commissions, 2)


def to_base(amount: float, t: Dict) -> float:
    """A blotter amount (in the listing's currency) in the fund's base currency, at the fill's own rates; rows booked
    before rates were recorded are taken at face value."""
    u, b = t.get("usd_per_unit"), t.get("base_per_usd")
    return float(amount or 0) * (float(u) * float(b) if u and b else 1.0)


def side_to_signed(side: str, quantity: float) -> float:
    """Signed quantity for a side: BUY / LONG / COVER → +|q|, SELL / SHORT → −|q|.

    Raises:
        ValueError: an unknown side.
    """
    s = (side or "").upper()
    if s in ("BUY", "LONG", "COVER"):
        return abs(quantity)
    if s in ("SELL", "SHORT"):
        return -abs(quantity)
    raise ValueError(f"unknown side '{side}'")


def blotter_totals(trades: Iterable[Dict]) -> Dict[str, float]:
    """Totals over blotter rows in the fund's base currency, each row converted at its own fill rates: realised P&L,
    commissions plus taxes, traded notional and the number of trades.
    """
    realized = comm = gross = 0.0
    n = 0
    for t in trades:                      # each row converted at its own fill rates (pence, yen … → base)
        realized += to_base(float(t.get("realized_pnl") or 0), t)
        comm += to_base(float(t.get("commission") or 0) + float(t.get("taxes") or 0), t)
        gross += abs(to_base(float(t.get("quantity") or 0) * float(t.get("price") or 0), t))
        n += 1
    return {"realized_pnl": round(realized, 2), "commissions": round(comm, 2),
            "traded_notional": round(gross, 2), "trades": n}

