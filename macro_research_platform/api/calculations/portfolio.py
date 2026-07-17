"""
Portfolio position math — pure, documented, unit-tested functions.

No I/O: given raw position records and a price map, compute market value, unrealized
P&L, weights, and book/firm aggregates. Kept separate from persistence so the
calculations can be tested with known-answer checks.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional


def market_value(quantity: float, price: float) -> float:
    """Position market value = quantity * current price. Units: account currency."""
    return round(quantity * price, 2)


def unrealized_pnl(quantity: float, avg_cost: float, price: float) -> float:
    """Unrealized P&L = (price - avg_cost) * quantity. Positive = gain.

    For a short (negative quantity), a price fall yields a positive P&L, which this
    formula handles naturally.
    """
    return round((price - avg_cost) * quantity, 2)


def unrealized_pnl_pct(avg_cost: float, price: float) -> Optional[float]:
    """Unrealized return as a fraction: price/avg_cost - 1. None if avg_cost is 0."""
    if not avg_cost:
        return None
    return round(price / avg_cost - 1.0, 6)


def enrich_position(pos: Dict[str, Any], price: Optional[float]) -> Dict[str, Any]:
    """Return the position with current_price/market_value/unrealized_pnl filled in.

    If no price is available the market-value fields are None (never a fake number).
    """
    qty = float(pos.get("quantity") or 0.0)
    avg_cost = float(pos.get("avg_cost") or 0.0)
    out = dict(pos)
    if price is None:
        out.update({
            "current_price": None, "market_value": None,
            "unrealized_pnl": None, "unrealized_pnl_pct": None,
            "price_available": False,
        })
        return out
    out.update({
        "current_price": round(float(price), 4),
        "market_value": market_value(qty, price),
        "unrealized_pnl": unrealized_pnl(qty, avg_cost, price),
        "unrealized_pnl_pct": unrealized_pnl_pct(avg_cost, price),
        "price_available": True,
    })
    return out


def _gross(mv: Optional[float]) -> float:
    return abs(mv) if isinstance(mv, (int, float)) else 0.0


def add_weights(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add weight_pct to each position as its share of total GROSS market value.

    Gross (sum of |market value|) is used so longs and shorts both contribute to the
    denominator, matching how a risk desk sizes exposure.
    """
    total_gross = sum(_gross(p.get("market_value")) for p in positions)
    for p in positions:
        mv = p.get("market_value")
        p["weight_pct"] = round(_gross(mv) / total_gross, 6) if total_gross else None
    return positions


def portfolio_summary(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate long/short/gross/net exposure and total P&L across positions."""
    long_mv = sum(p["market_value"] for p in positions
                  if isinstance(p.get("market_value"), (int, float)) and p["market_value"] > 0)
    short_mv = sum(p["market_value"] for p in positions
                   if isinstance(p.get("market_value"), (int, float)) and p["market_value"] < 0)
    total_pnl = sum(p["unrealized_pnl"] for p in positions
                    if isinstance(p.get("unrealized_pnl"), (int, float)))
    priced = sum(1 for p in positions if p.get("price_available"))
    return {
        "position_count": len(positions),
        "priced_count": priced,
        "unpriced_count": len(positions) - priced,
        "long_market_value": round(long_mv, 2),
        "short_market_value": round(short_mv, 2),
        "gross_exposure": round(long_mv - short_mv, 2),   # long + |short|
        "net_exposure": round(long_mv + short_mv, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
    }


def books_breakdown(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-book aggregate (gross/net/pnl), plus positions are already tagged by book."""
    by_book: Dict[str, List[Dict[str, Any]]] = {}
    for p in positions:
        by_book.setdefault(p.get("book") or "Unassigned", []).append(p)
    rows = []
    for book, ps in sorted(by_book.items()):
        s = portfolio_summary(ps)
        rows.append({"book": book, **s})
    return rows
