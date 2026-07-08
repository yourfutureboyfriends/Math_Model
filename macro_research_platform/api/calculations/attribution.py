"""
Performance attribution math — pure, tested (Phase 5).

Two complementary, real decompositions on the actual book:
  1. Contribution attribution (since inception): each position's / book's dollar P&L and
     its share of total P&L — sums exactly to the portfolio's total unrealized P&L.
  2. Factor attribution (trailing window): the portfolio's period return split into a
     systematic part (Σ factor_loading × realized factor return) and an idiosyncratic
     (selection) residual.

No I/O — enriched positions and realized factor returns are passed in.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional


def position_contributions(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-position dollar P&L and % of total P&L (by absolute magnitude)."""
    rows = []
    total_abs = sum(abs(p["unrealized_pnl"]) for p in positions
                    if isinstance(p.get("unrealized_pnl"), (int, float))) or 0.0
    total_pnl = sum(p["unrealized_pnl"] for p in positions
                    if isinstance(p.get("unrealized_pnl"), (int, float)))
    for p in positions:
        pnl = p.get("unrealized_pnl")
        if not isinstance(pnl, (int, float)):
            continue
        rows.append({
            "symbol": p["symbol"], "book": p.get("book"),
            "pnl": round(pnl, 2),
            "pct_of_pnl": round(pnl / total_pnl, 4) if total_pnl else None,
            "pct_of_abs_pnl": round(abs(pnl) / total_abs, 4) if total_abs else None,
        })
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    return rows


def book_rollup(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-book P&L rollup (contribution by book), sorted by P&L descending."""
    by_book: Dict[str, Dict[str, float]] = {}
    for p in positions:
        pnl = p.get("unrealized_pnl")
        if not isinstance(pnl, (int, float)):
            continue
        b = p.get("book") or "Unassigned"
        d = by_book.setdefault(b, {"pnl": 0.0, "count": 0})
        d["pnl"] += pnl
        d["count"] += 1
    total = sum(d["pnl"] for d in by_book.values())
    rows = [{"book": b, "pnl": round(d["pnl"], 2), "positions": d["count"],
             "pct_of_pnl": round(d["pnl"] / total, 4) if total else None}
            for b, d in by_book.items()]
    rows.sort(key=lambda r: r["pnl"], reverse=True)
    return rows


def factor_attribution(
    portfolio_loadings: Dict[str, float],
    factor_period_returns: Dict[str, float],
    portfolio_period_return: float,
) -> Dict[str, Any]:
    """Split the portfolio's period return into systematic (per-factor) + idiosyncratic.

    systematic_f = loading_f * factor_period_return_f.
    systematic = Σ_f systematic_f. idiosyncratic (selection) = portfolio_return − systematic.
    All returns are fractions over the same trailing window.
    """
    by_factor = {}
    systematic = 0.0
    for f, load in portfolio_loadings.items():
        contrib = load * factor_period_returns.get(f, 0.0)
        by_factor[f] = round(contrib, 5)
        systematic += contrib
    idio = portfolio_period_return - systematic
    return {
        "portfolio_return": round(portfolio_period_return, 5),
        "systematic_return": round(systematic, 5),
        "idiosyncratic_return": round(idio, 5),
        "by_factor": by_factor,
    }


def cumulative_return(returns) -> float:
    """Compound a sequence of period returns into a single cumulative return."""
    import numpy as np
    r = np.asarray(list(returns), dtype=float)
    if r.size == 0:
        return 0.0
    return float(np.prod(1.0 + r) - 1.0)
