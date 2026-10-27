"""
Trade manager — "I'm in this stock: hold, tighten, trim, add or exit?" for one position or the whole book, from
technicals, fundamentals and news (rules and evidence: api/calculations/trade_management.py; the entry side:
api/calculations/stock_timing.py via api/routers/stock.analyze).

    entry_check(symbol, price, side, date)        where to get in, and whether a given entry price is good
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


FILL_SESSIONS = 20


def _touch_probability(price: float, level: float, daily_vol: float, sessions: int = FILL_SESSIONS) -> float:
    """Chance the price trades at `level` within `sessions` days: the reflection principle for a driftless
    random walk, P(min ≤ L) = 2·Φ(ln(L/P) / (σ√T)) for a level below the price (mirrored above)."""
    from statistics import NormalDist
    if daily_vol <= 0:
        return 1.0 if level == price else 0.0
    z = -abs(np.log(level / price)) / (daily_vol * np.sqrt(sessions))
    return float(min(1.0, 2 * NormalDist().cdf(z)))


def _zone(price: float, sma20: float, a: float, timing_score: float) -> tuple:
    """The entry model's buy zone (stock_timing.levels): around the 20-day average when the price is stretched,
    else from max(20-day average, price − 1 ATR) up to the price."""
    from api.calculations.stock_timing import EXTENDED_TIMING
    lo, hi = (sma20 - 0.5 * a, sma20 + 0.5 * a) if timing_score <= EXTENDED_TIMING else (max(sma20, price - a), price)
    return min(lo, hi), max(lo, hi)


async def entry_check(symbol: str, price: Optional[float] = None, side: int = 1, date_: Optional[str] = None,
                      held: bool = False) -> Dict[str, Any]:
    """Where to get in, and whether a given entry price is a good one.

    Args:
        symbol: Ticker.
        price: Your entry price (planned or paid); None for the recommendation only.
        side: +1 long, −1 short.
        date_: The date you bought (YYYY-MM-DD) — the price is then judged against what the model said that day.
        held: True when the price was already paid (no fill estimate, even without a date).

    Returns:
        {recommended: the model's entry zone, stop, target, reward:risk and verdict today;
         your_price: grade (good / fair / poor) with reasons, reward:risk at your price, chance of a fill;
         at_entry_date: the model's zone and verdict on the day you bought (no hindsight)}.
    """
    from api.calculations import stock_timing as st
    from api.routers.stock import _fetch, analyze
    sym = symbol.strip().upper()
    a, raw = await asyncio.gather(analyze(sym, with_history=False), asyncio.to_thread(_fetch, sym))
    if not a.get("available"):
        raise ValueError(a.get("reason") or f"No data for {sym}")
    hist = raw["hist"]
    c, h, l = (hist[k].to_numpy(dtype=float) for k in ("Close", "High", "Low"))
    dates = [str(d)[:10] for d in hist.index]
    px_now = float(c[-1])
    atr14 = (a.get("timing") or {}).get("atr14") or st.atr(h, l, c) or 0.0
    lv, v = a.get("levels") or {}, a.get("verdict") or {}
    daily_vol = float(np.std(np.diff(np.log(c[-64:])), ddof=1)) if len(c) > 65 else 0.02
    rec = {"verdict": v, "price": round(px_now, 4), "as_of": dates[-1], "currency": a.get("currency"),
           **{k: lv.get(k) for k in ("entry_low", "entry_high", "entry", "stop", "target", "target_basis", "reward_risk", "shares", "pct_nav")},
           "setup_score": a.get("setup_score"), "timing": (a.get("timing") or {}).get("state"),
           "note": ("The entry model is long-only: for a short, the levels mirror a 2.5×ATR stop and a 2R objective."
                    if side < 0 else None)}
    if side > 0 and lv.get("entry_high") is not None and lv["entry_high"] < px_now:
        rec["fill_probability_at_zone_top"] = round(_touch_probability(px_now, lv["entry_high"], daily_vol), 2)
    out: Dict[str, Any] = {"symbol": sym, "name": a.get("name", sym), "side": "long" if side > 0 else "short", "recommended": rec}

    if price:
        reasons, score = [], 0
        stop_u = price - side * 2.5 * atr14                 # the entry model's 2.5×ATR(14) stop, from your price
        tgt = lv.get("target") if side > 0 and lv.get("target") else price + side * 2 * abs(price - stop_u)
        rr = (side * (tgt - price)) / abs(price - stop_u) if abs(price - stop_u) > 0 else None
        lo, hi = lv.get("entry_low"), lv.get("entry_high")
        where = None
        if side > 0 and lo is not None and hi is not None:
            if price < lo:
                where = "below"
                reasons.append(f"Below the model's zone {lo:,.2f}–{hi:,.2f}: " + ("you hold it cheaper than the model would buy it today."
                               if held or date_ else "a better price than it asks for, if it fills."))
                score += 1
            elif price <= hi * 1.005:                         # within half a percent of the top counts as inside
                where = "inside"
                reasons.append(f"Inside the model's zone {lo:,.2f}–{hi:,.2f}.")
                score += 1
            else:
                where = "above"
                over = price / hi - 1
                reasons.append(f"{over:.1%} above the top of the model's zone ({hi:,.2f}) — paying up for a stretched price.")
                score -= 1 if over < 0.03 else 2
        if rr is not None:
            if rr >= 2:
                score += 1; reasons.append(f"Reward:risk {rr:.1f} at your price (target {tgt:,.2f}, stop {stop_u:,.2f}).")
            elif rr >= 1.5:
                reasons.append(f"Reward:risk {rr:.1f} — acceptable (the model wants ≥ 1.5).")
            else:
                score -= 1; reasons.append(f"Reward:risk only {rr:.1f} at your price (target {tgt:,.2f}, stop {stop_u:,.2f}) — below the 1.5 the model needs.")
        code = v.get("code")
        if side > 0:
            if code in ("BUY", "BUY_SMALL"):
                score += 1; reasons.append(f"The model says {v.get('label', code).lower()} today.")
            elif code == "WAIT":
                reasons.append(f"The model says wait: {v.get('detail', '')}")
            elif code in ("AVOID", "WATCH"):
                score -= 2 if code == "AVOID" else 1; reasons.append(f"The model says {v.get('label', code).lower()} — the trend / fundamentals don't support buying.")
        else:
            trend = (a.get("components") or {}).get("trend") or {}
            if (trend.get("score") or 0) > 0:
                score -= 2; reasons.append("Shorting against an up-trend (price above its long-term average).")
            else:
                score += 1; reasons.append("The trend supports a short (price below its long-term average).")
        fill = None
        if not date_ and not held:                          # a planned order: will a limit at this price fill?
            if (side > 0 and price < px_now) or (side < 0 and price > px_now):
                fill = round(_touch_probability(px_now, price, daily_vol), 2)
                reasons.append(f"About a {fill:.0%} chance a limit order there fills within {FILL_SESSIONS} sessions "
                               f"(today {px_now:,.2f}, {daily_vol * np.sqrt(252):.0%} annual volatility).")
                if fill < 0.25:
                    score -= 1
            else:
                reasons.append(f"At or through today's price {px_now:,.2f}: it would fill now.")
        elif held and not date_:
            reasons.append("Add the date you bought to judge the price against what the model said that day.")
        grade = "good" if score >= 2 else "fair" if score >= 0 else "poor"
        out["your_price"] = {"price": price, "grade": grade, "score": score, "zone_position": where,
                             "reward_risk": None if rr is None else round(rr, 2), "stop": round(stop_u, 4), "target": round(tgt, 4),
                             "fill_probability": fill, "reasons": reasons,
                             "label": {"good": "Good entry", "fair": "Acceptable entry", "poor": "Poor entry"}[grade]}

    if price and date_ and date_ <= dates[-1]:
        idx = next((k for k, d in enumerate(dates) if d >= date_), len(dates) - 1)
        f = st.signal_frame(c[: idx + 1], h[: idx + 1], l[: idx + 1]).iloc[-1]
        then_px, setup, timing, a_then = float(c[idx]), f["setup"], f["timing"], f["atr"]
        s20 = float(np.mean(c[max(0, idx - 19): idx + 1]))
        then = {"date": dates[idx], "close": round(then_px, 4),
                "setup": None if setup != setup else round(float(setup), 3), "timing": None if timing != timing else round(float(timing), 3)}
        if a_then == a_then and timing == timing:
            lo_t, hi_t = _zone(then_px, s20, float(a_then), float(timing))
            then.update({"entry_low": round(lo_t, 4), "entry_high": round(hi_t, 4)})
            buy_then = setup == setup and setup >= st.BUY_SETUP
            call = ("BUY" if buy_then and timing > st.EXTENDED_TIMING else "WAIT (stretched)" if buy_then else
                    "WATCH" if setup == setup and setup >= 0 else "AVOID")
            then["model_said"] = call
            yp = out.get("your_price")
            if yp and side > 0:                       # a past purchase is judged on the call that day, not today's
                adj = {"BUY": 1, "WAIT (stretched)": -1, "WATCH": -1, "AVOID": -2}[call]
                yp["score"] += adj
                yp["reasons"].insert(0, f"On the day you bought ({dates[idx]}) the model said {call}"
                                     + (" — a well-timed entry." if adj > 0 else " — the evidence wasn't there yet." if call == "WATCH"
                                        else " — the price was stretched then." if call.startswith("WAIT") else " — it argued against buying."))
                yp["grade"] = "good" if yp["score"] >= 2 else "fair" if yp["score"] >= 0 else "poor"
                yp["label"] = {"good": "Good entry", "fair": "Acceptable entry", "poor": "Poor entry"}[yp["grade"]]
            where_then = ("inside it." if lo_t <= price <= hi_t else "below it (well bought)." if price < lo_t
                          else f"{price / hi_t - 1:.1%} above it.")
            zone_txt = f", zone {lo_t:,.2f}–{hi_t:,.2f}: you paid {price:,.2f} — {where_then}" if side > 0 else "."
            then["verdict"] = (f"On {dates[idx]} the price-only model said {call}{zone_txt}"
                               " (Trend, momentum and the 52-week high only — no point-in-time fundamentals.)")
        out["at_entry_date"] = then
    return out


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
