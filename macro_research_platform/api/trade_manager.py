"""
Trade manager — "I'm in this stock: hold, tighten, trim, add or exit?" for one position or the whole book, from
technicals, fundamentals and news (rules and evidence: api/calculations/trade_management.py; the entry side:
api/calculations/stock_timing.py via api/routers/stock.analyze).

    manage(symbol, entry_price, entry_date, side)   one position
    manage_book()                                    every position in the current fund's book
    overlays(symbol)                                 news tone (last 14 days) and insider buying (6 months) —
                                                     also shown with the entry analysis

News tone is the finance word-list score of each headline (api/calculations/news_sentiment); insider activity is
open-market Form 4 trades from SEC EDGAR (US filers only).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import numpy as np

from api.calculations import trade_management as tm

logger = logging.getLogger(__name__)
NEWS_DAYS = 14


async def overlays(symbol: str) -> Dict[str, Any]:
    """Recent news with tone, and insider buying, for a stock (each part optional)."""
    from api.calculations.news_sentiment import score_headline
    from api.marketdata import core, extras

    async def _news():
        try:
            j = await asyncio.wait_for(asyncio.to_thread(core.news, symbol), 25)
        except Exception as e:                                                 # noqa: BLE001 — optional input
            return {"available": False, "reason": str(e)[:120]}
        since = datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS)
        items = []
        for n in j.get("news", []):
            try:
                t = datetime.fromisoformat(str(n.get("time")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if t >= since:
                items.append({"time": n["time"], "title": n.get("title"), "publisher": n.get("publisher"), "url": n.get("url"),
                              "sentiment": round(score_headline(f"{n.get('title') or ''} {n.get('summary') or ''}"), 2)})
        tones = [i["sentiment"] for i in items]
        return {"available": True, "items": items[:12], "count": len(items),
                "avg_tone": round(float(np.mean(tones)), 3) if tones else None, "window_days": NEWS_DAYS}

    async def _insiders():
        try:
            j = await asyncio.wait_for(asyncio.to_thread(extras.insiders, symbol, 40), 30)
        except Exception as e:                                                 # noqa: BLE001 — US filers only
            return {"available": False, "reason": str(e)[:120]}
        return {"available": True, **{k: j.get(k) for k in ("open_market_buys_6m", "open_market_sales_6m", "buyers_6m", "sellers_6m")}}

    news, ins = await asyncio.gather(_news(), _insiders())
    return {"news": news, "insiders": ins}


async def manage(symbol: str, entry_price: float, entry_date: Optional[str], side: int = 1,
                 quantity: Optional[float] = None) -> Dict[str, Any]:
    """Advice for one open position.

    Args:
        symbol: Ticker.
        entry_price: Average entry price (quote currency).
        entry_date: Entry date YYYY-MM-DD; unknown dates are taken as 90 days ago (flagged).
        side: +1 long, −1 short.
        quantity: Shares held, for the money at risk (optional).

    Raises:
        ValueError: no price history, or the entry date is in the future.
    """
    from api.routers.stock import _fetch, analyze
    sym = symbol.strip().upper()
    raw = await asyncio.to_thread(_fetch, sym)
    hist = raw["hist"]
    c, h, l = (hist[k].to_numpy(dtype=float) for k in ("Close", "High", "Low"))
    dates = [str(d)[:10] for d in hist.index]
    assumed = not entry_date
    ed = entry_date or (date.today() - timedelta(days=90)).isoformat()
    if ed > dates[-1]:
        raise ValueError("The entry date is after the latest price.")
    idx = next((k for k, d in enumerate(dates) if d >= ed), len(dates) - 1)
    a, ov = await asyncio.gather(analyze(sym, with_history=False), overlays(sym))
    comps = (a.get("components") or {}) if a.get("available") else {}
    res = tm.manage_position(
        c, h, l, idx, float(entry_price), side, today=date.fromisoformat(dates[-1]),
        target=(a.get("levels") or {}).get("target") if a.get("available") else None,
        entry_verdict=(a.get("verdict") or {}).get("code"), timing_state=(a.get("timing") or {}).get("state"),
        momentum_score=(comps.get("momentum") or {}).get("score"),
        market_ok=(a.get("market") or {}).get("ok"), vix=(a.get("market") or {}).get("vix"),
        revisions=raw.get("revisions"), earnings=raw.get("earnings"),
        news=ov["news"].get("items") if ov["news"].get("available") else None,
        insiders=ov["insiders"] if ov["insiders"].get("available") else None)
    if res.get("available") and quantity:
        res["money_at_risk"] = round(abs(quantity) * abs(res["price"] - res["stop"]), 2)
    return {"symbol": sym, "name": a.get("name", sym), "currency": a.get("currency"), "side": "long" if side > 0 else "short",
            "entry_price": entry_price, "entry_date": dates[idx], "entry_date_assumed": assumed, "quantity": quantity,
            **res, "entry_model": {"verdict": a.get("verdict"), "setup_score": a.get("setup_score"), "timing": (a.get("timing") or {}).get("state")}
            if a.get("available") else None, "news": ov["news"], "insiders": ov["insiders"],
            "method": "Rules and evidence: api/calculations/trade_management.py (exit on a 200-day trend break with a 2.5×ATR "
                      "initial stop; warnings tighten the stop to the chandelier level)."}


async def manage_book() -> Dict[str, Any]:
    """Advice for every position in the current fund's book (three at a time)."""
    from api import portfolio_store
    rows = await asyncio.to_thread(portfolio_store.list_positions, None)
    sem = asyncio.Semaphore(3)

    async def one(p):
        async with sem:
            try:
                q = float(p.get("quantity") or 0)
                return await manage(p["symbol"], float(p.get("avg_cost") or 0), p.get("entry_date"), 1 if q >= 0 else -1, q)
            except Exception as e:                                             # noqa: BLE001 — one name failing is shown, not fatal
                return {"symbol": p.get("symbol"), "available": False, "reason": str(e)[:160]}

    out = await asyncio.gather(*[one(p) for p in rows if p.get("symbol") and float(p.get("avg_cost") or 0) > 0])
    order = {"EXIT": 0, "TRIM": 1, "TIGHTEN": 2, "ADD": 3, "HOLD": 4}
    out.sort(key=lambda r: order.get(r.get("action"), 5))
    return {"positions": out, "count": len(out), "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "summary": {k: sum(1 for r in out if r.get("action") == k) for k in order}}
