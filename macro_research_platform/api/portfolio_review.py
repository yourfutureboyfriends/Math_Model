"""
Model review of the holdings you choose ("My Portfolio").

Each equity holding is run through the full entry model (api/routers/stock.analyze) and
mapped to an action. The model was built to time entries, so for a position already held:
  * Exit / reduce — evidence negative (AVOID) or the long-term trend broken (price below
    its 200-day average with the 50-day below it — Faber 2007's exit condition);
  * Hold / add — BUY: set-up strong and the entry not stretched;
  * Hold — don't add here — strong set-up but extended (WAIT);
  * Hold — risk-off market — strong set-up while the home market is risk-off (BUY_SMALL);
  * Hold — watch — mixed evidence (WATCH).
A trailing stop of 2.5 × ATR(14) below the last price is suggested for every holding.

Short positions mirror this: a strong up-trend (BUY / WAIT / BUY_SMALL) is the risk —
"Cover / reduce short"; negative evidence or a broken trend supports the short — "Hold
short"; mixed evidence — "Hold short — watch". Their stop sits 2.5 × ATR above the price.
Weights are shares of gross exposure.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

ACTIONS = {
    "exit": ("Exit / reduce", "bad"),
    "add": ("Hold / add", "good"),
    "hold_extended": ("Hold — don't add here", "neutral"),
    "hold_riskoff": ("Hold — risk-off market", "neutral"),
    "watch": ("Hold — watch", "neutral"),
    "none": ("No signal (insufficient history)", "neutral"),
    "cover": ("Cover / reduce short", "bad"),
    "hold_short": ("Hold short", "good"),
    "watch_short": ("Hold short — watch", "neutral"),
}


def review_action(verdict: Optional[str], trend_score: Optional[float], short: bool = False) -> str:
    if verdict in (None, "N/A"):
        return "none"
    if short:
        if verdict == "AVOID" or (trend_score is not None and trend_score <= -1):
            return "hold_short"
        return "cover" if verdict in ("BUY", "WAIT", "BUY_SMALL") else "watch_short"
    if verdict == "AVOID" or (trend_score is not None and trend_score <= -1):
        return "exit"
    return {"BUY": "add", "WAIT": "hold_extended", "BUY_SMALL": "hold_riskoff"}.get(verdict, "watch")


async def review(positions: List[Dict[str, Any]], concurrency: int = 4) -> Dict[str, Any]:
    from api.routers.stock import analyze
    by_sym: Dict[str, List[Dict[str, Any]]] = {}
    for p in positions:
        sym = (p.get("symbol") or "").upper()
        if sym:
            by_sym.setdefault(sym, []).append(p)
    sem = asyncio.Semaphore(concurrency)

    async def one(sym: str) -> Dict[str, Any]:
        async with sem:
            try:
                return await analyze(sym, with_history=False)
            except Exception as e:
                return {"symbol": sym, "available": False, "reason": str(e)[:120]}
    results = await asyncio.gather(*(one(s) for s in by_sym))
    rows = []
    for sym, a in zip(by_sym, results):
        qty = sum(float(p.get("quantity") or 0) for p in by_sym[sym])
        cost = sum(float(p.get("quantity") or 0) * float(p.get("avg_cost") or 0) for p in by_sym[sym])
        avg = cost / qty if qty else None
        if not a.get("available"):
            rows.append({"symbol": sym, "quantity": qty, "avg_cost": avg, "available": False,
                         "action": "none", "action_label": "No data", "tone": "neutral",
                         "reason": a.get("reason"), "books": sorted({p.get("book") or "—" for p in by_sym[sym]})})
            continue
        trend = (a.get("components") or {}).get("trend") or {}
        timing = a.get("timing") or {}
        verdict = (a.get("verdict") or {}).get("code")
        short = qty < 0
        act = review_action(verdict, trend.get("score"), short)
        price = a.get("price")
        atr = timing.get("atr14")
        fx = a.get("px_to_usd") or 1.0
        label, tone = ACTIONS[act]
        rows.append({
            "symbol": sym, "name": a.get("name"), "books": sorted({p.get("book") or "—" for p in by_sym[sym]}),
            "side": "Short" if short else "Long",
            "quantity": qty, "avg_cost": round(avg, 4) if avg else None, "price": price, "currency": a.get("currency"),
            "market_value_usd": round(qty * price * fx, 2) if price else None,
            "pnl_pct": round((price / avg - 1) * (-1 if short else 1), 4) if price and avg else None,
            "country": a.get("country"), "market_class": a.get("market_class"), "asset_type": a.get("asset_type"),
            "verdict": verdict, "verdict_label": (a.get("verdict") or {}).get("label"),
            "setup_score": a.get("setup_score"), "timing_state": timing.get("state"),
            "trend": trend.get("evidence"), "above_200d": (trend.get("score") or -1) >= 0.5,
            "trailing_stop": round(price + (2.5 if short else -2.5) * atr, 4) if price and atr else None,
            "stop_distance_pct": round(2.5 * atr / price, 4) if price and atr else None,
            "action": act, "action_label": label, "tone": tone, "available": True,
        })
    gross = sum(abs(r.get("market_value_usd") or 0) for r in rows)
    total = sum(r.get("market_value_usd") or 0 for r in rows)
    for r in rows:
        r["weight"] = round((r.get("market_value_usd") or 0) / gross, 4) if gross else None
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return {"holdings": sorted(rows, key=lambda r: -abs(r.get("market_value_usd") or 0)),
            "total_usd": round(total, 2), "gross_usd": round(gross, 2), "counts": counts}
