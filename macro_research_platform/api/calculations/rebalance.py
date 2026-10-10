"""
Regime-aware target portfolio and rebalance orders — pure, tested.

1. Risk budgets: the regime playbook (REGIME_CHARACTERISTICS biases) tilts a liquid
   multi-asset ETF universe. Bias multipliers: overweight/long/high = 1.5,
   neutral/medium = 1.0, underweight/short/low = 0.5.
2. Weights: risk budgeting (each asset's share of portfolio risk ∝ its budget), solved by
   the standard fixed-point iteration w_i ∝ b_i / (Σw)_i on the sample covariance.
3. Sizing: scale to the fund's volatility target, capped by a maximum gross exposure.
4. Orders: target market value per asset vs the book's current holdings → whole-share
   orders, skipping trades below a minimum size, with an estimated transaction cost.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from api.calculations.regime import REGIME_CHARACTERISTICS

UNIVERSE: Dict[str, str] = {
    "SPY": "US equities", "TLT": "Long Treasuries", "TIP": "Inflation-linked bonds",
    "DBC": "Commodities", "GLD": "Gold", "HYG": "High-yield credit",
}

_MULT = {"overweight": 1.5, "long": 1.5, "high": 1.5,
         "neutral": 1.0, "medium": 1.0,
         "underweight": 0.5, "short": 0.5, "low": 0.5}


def regime_budgets(regime: str) -> Dict[str, float]:
    """Risk budget per universe asset (normalized to sum to 1) for a regime.
    Unknown regimes get equal budgets."""
    rc = REGIME_CHARACTERISTICS.get((regime or "").strip().lower())
    if rc is None:
        return {a: 1.0 / len(UNIVERSE) for a in UNIVERSE}
    eq = _MULT.get(rc.equity_bias, 1.0)
    dur = _MULT.get(rc.duration_bias, 1.0)
    com = _MULT.get(rc.commodity_bias, 1.0)
    risk = _MULT.get(rc.risk_appetite, 1.0)
    raw = {
        "SPY": eq,
        "TLT": dur,
        "TIP": com,                       # inflation-linked: follows the inflation/commodity view
        "DBC": com,
        "GLD": (com + (2.0 - risk)) / 2,  # real asset + defensive hedge when risk appetite is low
        "HYG": risk,
    }
    total = sum(raw.values())
    return {a: round(v / total, 6) for a, v in raw.items()}


def risk_budget_weights(cov: np.ndarray, budgets: Sequence[float],
                        iters: int = 500, tol: float = 1e-10) -> np.ndarray:
    """Long-only weights (sum 1) whose risk contributions are proportional to `budgets`."""
    b = np.asarray(budgets, dtype=float)
    b = b / b.sum()
    vol = np.sqrt(np.clip(np.diag(cov), 1e-16, None))
    w = b / vol
    w = w / w.sum()
    for _ in range(iters):
        mrc = cov @ w
        mrc = np.where(mrc <= 1e-16, 1e-16, mrc)
        w_new = b / mrc
        w_new = w_new / w_new.sum()
        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            break
        w = 0.5 * w + 0.5 * w_new          # damping for stable convergence
    return w


def risk_contributions(cov: np.ndarray, w: np.ndarray) -> np.ndarray:
    port = float(w @ cov @ w)
    return (w * (cov @ w)) / port if port > 0 else np.zeros_like(w)


def target_portfolio(regime: str, daily_returns: Dict[str, Sequence[float]],
                     vol_target: float = 0.10, max_gross: float = 1.5) -> Dict:
    """Target weights (% of the sleeve's NAV) for a regime.

    daily_returns: aligned daily returns per universe ticker. Assets without history are
    dropped and their budget redistributed.
    """
    assets = [a for a in UNIVERSE if a in daily_returns and len(daily_returns[a]) > 20]
    if len(assets) < 2:
        return {"available": False, "reason": "insufficient price history for the universe"}
    n = min(len(daily_returns[a]) for a in assets)
    R = np.column_stack([np.asarray(daily_returns[a], dtype=float)[-n:] for a in assets])
    cov = np.cov(R, rowvar=False)
    budgets_all = regime_budgets(regime)
    b = np.array([budgets_all[a] for a in assets])
    w = risk_budget_weights(cov, b)
    unlevered_vol = float(np.sqrt(w @ cov @ w * 252))
    leverage = min(vol_target / unlevered_vol, max_gross) if unlevered_vol > 0 else 0.0
    rc = risk_contributions(cov, w)
    return {
        "available": True,
        "regime": regime,
        "vol_target": vol_target,
        "unlevered_vol": round(unlevered_vol, 4),
        "leverage": round(leverage, 3),
        "expected_vol": round(unlevered_vol * leverage, 4),
        "gross_capped": bool(leverage >= max_gross - 1e-9),
        "observations": int(n),
        "weights": [{"symbol": a, "name": UNIVERSE[a], "budget": round(float(b[i] / b.sum()), 4),
                     "weight": round(float(w[i] * leverage), 4),
                     "risk_share": round(float(rc[i]), 4)}
                    for i, a in enumerate(assets)],
    }


def rebalance_orders(target_weights: Dict[str, float], nav: float, prices: Dict[str, float],
                     current_qty: Dict[str, float], min_trade_pct: float = 0.0025,
                     cost_bps: float = 5.0) -> Dict:
    """Orders that move the book from current holdings to target weights.

    target_weights: {symbol: fraction of nav}. Holdings not in the target are closed.
    Trades smaller than min_trade_pct of NAV are skipped. cost_bps: commission + half-spread
    estimate applied to traded notional.
    """
    orders: List[Dict] = []
    skipped: List[str] = []
    symbols = sorted(set(target_weights) | {s for s, q in current_qty.items() if q})
    turnover = 0.0
    for s in symbols:
        px = prices.get(s)
        if not px or px <= 0:
            skipped.append(s)
            continue
        cur = float(current_qty.get(s, 0.0))
        tgt_qty = round(target_weights.get(s, 0.0) * nav / px)
        delta = tgt_qty - cur
        notional = delta * px
        if abs(notional) < min_trade_pct * nav:
            continue
        turnover += abs(notional)
        orders.append({
            "symbol": s, "side": "BUY" if delta > 0 else "SELL",
            "quantity": int(abs(delta)), "price": round(px, 2),
            "notional": round(abs(notional), 2),
            "current_qty": cur, "target_qty": int(tgt_qty),
            "target_weight": round(target_weights.get(s, 0.0), 4),
            "est_cost": round(abs(notional) * cost_bps / 1e4, 2),
            "action": "EXIT" if s not in target_weights else ("INITIATE" if cur == 0 else "ADJUST"),
        })
    orders.sort(key=lambda o: -o["notional"])
    return {
        "orders": orders,
        "order_count": len(orders),
        "turnover": round(turnover, 2),
        "turnover_pct_nav": round(turnover / nav, 4) if nav else None,
        "est_total_cost": round(sum(o["est_cost"] for o in orders), 2),
        "skipped_no_price": skipped,
    }
