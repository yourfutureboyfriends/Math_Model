"""Stock entry timing: per-stock buy/wait/avoid with entry, stop, target and size, plus a
screener over a watchlist. Method and sources: api/calculations/stock_timing.py."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException

from api.calculations import stock_timing as st

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stock"])

_CACHE: Dict[str, tuple] = {}
_TTL = 30 * 60
_SYMBOL = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")
# Large caps across sectors; the screener also adds every symbol held in the book.
DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "JPM", "V",
                    "MA", "UNH", "LLY", "JNJ", "MRK", "ABBV", "XOM", "CVX", "PG", "KO", "PEP",
                    "COST", "WMT", "HD", "ORCL", "CRM", "AMD", "NFLX", "BAC", "ADBE"]


def _norm(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not _SYMBOL.match(s):
        raise HTTPException(400, f"invalid symbol: {sym!r}")
    return s


def _fetch(sym: str) -> Dict[str, Any]:
    """Prices (10y daily), fundamentals, rating changes and earnings for one symbol."""
    import yfinance as yf
    t = yf.Ticker(sym)
    hist = t.history(period="10y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        raise ValueError("no price history")
    hist = hist.dropna(subset=["Close"])
    info: Dict[str, Any] = {}
    try:
        info = t.info or {}
    except Exception as e:
        logger.debug("[stock] info failed for %s: %s", sym, e)
    revisions: List[Dict[str, Any]] = []
    try:
        ud = t.upgrades_downgrades
        if ud is not None and not ud.empty:
            for ts, r in ud.head(60).iterrows():
                cur, prior = r.get("currentPriceTarget"), r.get("priorPriceTarget")
                cur = float(cur) if cur == cur and cur else None
                prior = float(prior) if prior == prior and prior else None
                act = str(r.get("Action") or "").lower()
                revisions.append({
                    "date": str(ts)[:10], "firm": str(r.get("Firm") or ""),
                    "to_grade": str(r.get("ToGrade") or ""), "from_grade": str(r.get("FromGrade") or ""),
                    "action": act, "target": cur, "prior_target": prior,
                    "target_change": (cur - prior) if cur and prior else None})
    except Exception as e:
        logger.debug("[stock] rating changes failed for %s: %s", sym, e)
    earnings: List[Dict[str, Any]] = []
    try:
        ed = t.earnings_dates
        if ed is not None and not ed.empty:
            for ts, r in ed.iterrows():
                s = r.get("Surprise(%)")
                earnings.append({"date": str(ts)[:10],
                                 "estimate": None if r.get("EPS Estimate") != r.get("EPS Estimate") else r.get("EPS Estimate"),
                                 "reported": None if r.get("Reported EPS") != r.get("Reported EPS") else r.get("Reported EPS"),
                                 "surprise_pct": None if s != s or s is None else float(s)})
    except Exception as e:
        logger.debug("[stock] earnings failed for %s: %s", sym, e)
    return {"hist": hist, "info": info, "revisions": revisions, "earnings": earnings}


async def _market() -> Dict[str, Any]:
    from api.handlers.market_handler import _fetch_dated_closes_literal
    spx, vix = await asyncio.gather(_fetch_dated_closes_literal("^GSPC"), _fetch_dated_closes_literal("^VIX"))
    spx_c = np.array([spx[d] for d in sorted(spx)]) if spx else np.array([])
    vix_last = vix[max(vix)] if vix else None
    return st.market_component(spx_c, vix_last) if spx_c.size else None


async def _nav() -> Optional[float]:
    try:
        from api import fund_store
        s = await asyncio.to_thread(fund_store.get_settings)
        return float(s.get("capital") or 0) or None
    except Exception:
        return None


async def analyze(sym: str, with_history: bool = True) -> Dict[str, Any]:
    key = f"{sym}:{int(with_history)}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        raw = await asyncio.to_thread(_fetch, sym)
    except Exception as e:
        return {"symbol": sym, "available": False, "reason": f"no data for {sym}: {str(e)[:80]}"}
    hist = raw["hist"]
    c = hist["Close"].to_numpy(dtype=float)
    h = hist["High"].to_numpy(dtype=float)
    l = hist["Low"].to_numpy(dtype=float)
    dates = [str(d)[:10] for d in hist.index]
    today = date.today()
    price = float(c[-1])
    info = raw["info"]
    comps = {
        "trend": st.trend_component(c),
        "momentum": st.momentum_component(c),
        "high_52w": st.high52_component(c),
        "earnings": st.earnings_component(raw["earnings"], today),
        "analysts": st.analyst_component(info, raw["revisions"], price, today),
        "quality": st.quality_component(info),
    }
    timing = st.timing_component(c, h, l)
    market, nav = await asyncio.gather(_market(), _nav())
    setup = st.combine_setup(comps)
    lv = st.levels(price, timing, (comps["high_52w"] or {}).get("high_52w"),
                   (comps["analysts"] or {}).get("target_mean"), nav)
    v = st.verdict(setup, timing, market, (lv or {}).get("reward_risk"))
    out: Dict[str, Any] = {
        "symbol": sym, "available": True, "name": info.get("shortName") or info.get("longName") or sym,
        "sector": info.get("sector"), "currency": info.get("currency"),
        "price": round(price, 2), "as_of": dates[-1],
        "setup_score": setup, "timing": timing, "market": market, "verdict": v,
        "components": comps, "weights": st.SETUP_WEIGHTS, "levels": lv,
        "revisions": raw["revisions"][:12],
        "earnings": [e for e in raw["earnings"]][:6],
        "valuation": {k: info.get(k) for k in ("trailingPE", "forwardPE", "priceToBook", "beta", "marketCap")},
    }
    if with_history:
        sig = st.price_signal_history(c, h, l)
        out["backtest"] = {"period": f"{dates[260] if len(dates) > 260 else dates[0]} → {dates[-1]}",
                           "rules": "price-only part of the set-up (trend, momentum, 52-week high) ≥ "
                                    f"{st.BUY_SETUP} and entry not extended; analyst, earnings and quality "
                                    "inputs have no point-in-time history here and are excluded",
                           **st.evaluate_signal(c, sig)}
        s = hist["Close"]
        s50, s200 = s.rolling(50).mean(), s.rolling(200).mean()
        tail = slice(max(0, len(c) - 252), len(c))
        out["chart"] = [{"date": dates[i], "close": round(float(c[i]), 2),
                         "sma50": None if s50.iloc[i] != s50.iloc[i] else round(float(s50.iloc[i]), 2),
                         "sma200": None if s200.iloc[i] != s200.iloc[i] else round(float(s200.iloc[i]), 2),
                         "buy": bool(sig[i])} for i in range(tail.start, tail.stop)]
    out["methodology"] = st.__doc__.strip()
    _CACHE[key] = (time.time(), out)
    return out


@router.get("/api/v1/stock/timing")
async def stock_timing(symbol: str):
    """Buy / wait / avoid for one stock, with the evidence, levels, size and a historical test."""
    return await analyze(_norm(symbol), with_history=True)


@router.get("/api/v1/stock/screen")
async def stock_screen(symbols: Optional[str] = None):
    """The same model over a watchlist (default large caps + book holdings), ranked."""
    if symbols:
        syms = [_norm(s) for s in symbols.split(",") if s.strip()][:60]
    else:
        syms = list(DEFAULT_UNIVERSE)
        try:
            from api import portfolio_store
            held = await asyncio.to_thread(portfolio_store.list_positions, None)
            syms += [str(p["symbol"]).upper() for p in held if _SYMBOL.match(str(p["symbol"]).upper())]
        except Exception:
            pass
        syms = list(dict.fromkeys(syms))
    sem = asyncio.Semaphore(5)

    async def one(s):
        async with sem:
            r = await analyze(s, with_history=False)
        if not r.get("available"):
            return {"symbol": s, "available": False, "reason": r.get("reason")}
        comps = r["components"]
        return {"symbol": s, "available": True, "name": r["name"], "sector": r["sector"], "price": r["price"],
                "setup_score": r["setup_score"], "timing_score": (r["timing"] or {}).get("score"),
                "timing_state": (r["timing"] or {}).get("state"), "verdict": r["verdict"]["code"],
                "verdict_label": r["verdict"]["label"],
                "upside": (comps.get("analysts") or {}).get("upside"),
                "momentum": (comps.get("momentum") or {}).get("return_12_1"),
                "reward_risk": (r["levels"] or {}).get("reward_risk")}

    rows = await asyncio.gather(*[one(s) for s in syms])
    order = {"BUY": 0, "WAIT": 1, "BUY_SMALL": 2, "WATCH": 3, "AVOID": 4, "N/A": 5}
    ok = sorted([r for r in rows if r["available"]],
                key=lambda r: (order.get(r["verdict"], 9), -(r["setup_score"] or -9)))
    return {"available": bool(ok), "as_of": datetime.now().isoformat(timespec="minutes"),
            "rows": ok, "unavailable": [r for r in rows if not r["available"]],
            "counts": {k: sum(1 for r in ok if r["verdict"] == k) for k in order}}
