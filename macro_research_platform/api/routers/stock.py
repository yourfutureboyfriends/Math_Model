"""Stock entry timing: per-stock buy/wait/avoid with entry, stop, target and size, plus a
screener over a watchlist. Method and sources: api/calculations/stock_timing.py."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


# Yahoo's fundamentals endpoints (info, rating changes, earnings) rate-limit an IP quickly:
# one request at a time, spaced, a 10-minute pause after a refusal, and a 24h disk cache
# (fundamentals barely move intraday) so a global screen does not hammer them.
_FUND_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "fundamentals"
_FUND_TTL = 24 * 3600
_yf_lock = threading.Lock()
_yf_state = {"last": 0.0, "paused_until": 0.0}
_YF_SPACING = 0.6


def _yf_call(fn):
    """Run one fundamentals request under the throttle; None while paused or on refusal."""
    if time.time() < _yf_state["paused_until"]:
        return None
    with _yf_lock:
        wait = _yf_state["last"] + _YF_SPACING - time.time()
        if wait > 0:
            time.sleep(wait)
        _yf_state["last"] = time.time()
    try:
        return fn()
    except Exception as e:
        msg = str(e)
        if "Too Many Requests" in msg or "Rate limited" in msg or "Invalid Crumb" in msg or "401" in msg:
            _yf_state["paused_until"] = time.time() + 600
            logger.warning("[stock] Yahoo fundamentals refused (%s) — pausing 10 min, using cached data", msg[:60])
        else:
            logger.debug("[stock] fundamentals call failed: %s", msg[:100])
        return None


def _fund_cache(sym: str) -> Optional[Dict[str, Any]]:
    try:
        d = json.loads((_FUND_DIR / f"{sym.replace('/', '_')}.json").read_text())
        return d
    except Exception:
        return None


def _fetch(sym: str) -> Dict[str, Any]:
    """Prices (10y daily), fundamentals, rating changes and earnings for one symbol."""
    import yfinance as yf
    t = yf.Ticker(sym)
    hist = t.history(period="10y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        raise ValueError("no price history")
    hist = hist.dropna(subset=["Close"])
    cached = _fund_cache(sym)
    if cached and time.time() - cached.get("saved_at", 0) < _FUND_TTL:
        return {"hist": hist, "info": cached.get("info", {}), "revisions": cached.get("revisions", []),
                "earnings": cached.get("earnings", []), "fundamentals_as_of": cached.get("saved_at")}
    info: Dict[str, Any] = {}
    info = _yf_call(lambda: t.info) or {}
    revisions: List[Dict[str, Any]] = []
    try:
        ud = _yf_call(lambda: t.upgrades_downgrades) if info else None
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
        ed = _yf_call(lambda: t.earnings_dates) if info else None
        if ed is not None and not ed.empty:
            for ts, r in ed.iterrows():
                s = r.get("Surprise(%)")
                earnings.append({"date": str(ts)[:10],
                                 "estimate": None if r.get("EPS Estimate") != r.get("EPS Estimate") else r.get("EPS Estimate"),
                                 "reported": None if r.get("Reported EPS") != r.get("Reported EPS") else r.get("Reported EPS"),
                                 "surprise_pct": None if s != s or s is None else float(s)})
    except Exception as e:
        logger.debug("[stock] earnings failed for %s: %s", sym, e)
    if info:
        try:
            _FUND_DIR.mkdir(parents=True, exist_ok=True)
            keep = {k: info.get(k) for k in ("shortName", "longName", "sector", "industry", "currency", "financialCurrency", "quoteType", "exchange",
                                             "fullExchangeName", "recommendationMean", "recommendationKey",
                                             "numberOfAnalystOpinions", "targetMeanPrice", "targetHighPrice",
                                             "targetLowPrice", "returnOnEquity", "profitMargins", "debtToEquity",
                                             "trailingPE", "forwardPE", "priceToBook", "beta", "marketCap")}
            (_FUND_DIR / f"{sym.replace('/', '_')}.json").write_text(json.dumps(
                {"saved_at": time.time(), "info": keep, "revisions": revisions, "earnings": earnings}, default=str))
        except Exception as e:
            logger.debug("[stock] fundamentals cache write failed: %s", e)
    elif cached:                               # refused / paused: last good copy, any age
        return {"hist": hist, "info": cached.get("info", {}), "revisions": cached.get("revisions", []),
                "earnings": cached.get("earnings", []), "fundamentals_as_of": cached.get("saved_at")}
    return {"hist": hist, "info": info, "revisions": revisions, "earnings": earnings,
            "fundamentals_as_of": time.time() if info else None}


async def _market(bench: str = "^GSPC", name: str = "S&P 500") -> Optional[Dict[str, Any]]:
    """Regime of the stock's HOME market (its benchmark index) plus global VIX."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    idx, vix = await asyncio.gather(_fetch_dated_closes_literal(bench), _fetch_dated_closes_literal("^VIX"))
    c = np.array([idx[d] for d in sorted(idx)]) if idx else np.array([])
    vix_last = vix[max(vix)] if vix else None
    return st.market_component(c, vix_last, name) if c.size else None


async def _usd_per_unit(quote_ccy: Optional[str]) -> Optional[float]:
    """USD value of one unit of the quote currency (pence, cents and agorot handled)."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.markets import fx_ticker, minor_unit_factor
    major, div = minor_unit_factor(quote_ccy)
    if major == "USD":
        return 1.0 / div
    fx = await _fetch_dated_closes_literal(fx_ticker(major))
    rate = fx[max(fx)] if fx else None
    return (1.0 / rate) / div if rate else None


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
    from api.markets import COUNTRIES, benchmark_of, classify
    from api.markets import home_country
    cls = classify(sym)
    if cls["asset_type"] == "Equity" and str(info.get("quoteType") or "").upper() == "ETF":
        cls["asset_type"] = "ETF"
    if cls["asset_type"] == "Equity" and cls.get("country"):
        home = home_country(cls["country"], info.get("financialCurrency"))
        if home != cls["country"]:
            listing = cls["country"]
            cls = {**classify(sym, home), "asset_type": "Equity"}
            cls["listing_country"] = listing
    bench = benchmark_of(cls["country"]) if cls.get("country") else "ACWI"
    bench_name = "MSCI ACWI" if bench == "ACWI" else (COUNTRIES.get(cls["country"], {}).get("name", "") + " index")
    if bench == "^GSPC":
        bench_name = "S&P 500"
    quote_ccy = info.get("currency") or cls["home_currency"]
    market, nav, px_to_usd = await asyncio.gather(_market(bench, bench_name), _nav(), _usd_per_unit(quote_ccy))
    setup = st.combine_setup(comps)
    # An index cannot be bought directly: levels yes, position size no.
    lv = st.levels(price, timing, (comps["high_52w"] or {}).get("high_52w"),
                   (comps["analysts"] or {}).get("target_mean"),
                   None if cls["asset_type"] == "Index" else nav, px_to_usd=px_to_usd or 0.0)
    v = st.verdict(setup, timing, market, (lv or {}).get("reward_risk"),
                   target_is_consensus=(lv or {}).get("target_basis") == "consensus price target")
    out: Dict[str, Any] = {
        "symbol": sym, "available": True, "name": info.get("shortName") or info.get("longName") or sym,
        "sector": info.get("sector"), "currency": quote_ccy, "exchange": info.get("fullExchangeName") or info.get("exchange"),
        **cls, "px_to_usd": px_to_usd,
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
    if len(_CACHE) > 400:                    # bounded: drop expired, then oldest entries
        now = time.time()
        for k in [k for k, v in _CACHE.items() if now - v[0] > _TTL]:
            _CACHE.pop(k, None)
        for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: max(0, len(_CACHE) - 300)]:
            _CACHE.pop(k, None)
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
            from api import portfolio_store, stock_ideas as si
            held = await asyncio.to_thread(portfolio_store.list_positions, None)
            syms += [str(p["symbol"]).upper() for p in held if _SYMBOL.match(str(p["symbol"]).upper())]
            syms += si.watchlist_symbols()
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
                "country": r.get("country"), "market_class": r.get("market_class"), "region": r.get("region"),
                "currency": r.get("currency"),
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


@router.get("/api/v1/stock/ideas")
async def stock_ideas():
    """System-generated stock suggestions (S&P 500 screen → full model on the best set-ups).
    Returns the latest list immediately; starts a rebuild in the background when it is older
    than a day or missing."""
    from api import stock_ideas as si
    cur = si.latest()
    stale = (not cur) or (time.time() - _iso_ts(cur.get("as_of")) > 20 * 3600)
    if stale and not si.status()["running"]:
        _spawn(si.build_in_background())
    if not cur:
        return {"available": False, "status": si.status(),
                "reason": "Building the first list — screening the S&P 500 takes about a minute."}
    return {**cur, "status": si.status(), "stale": stale}


@router.post("/api/v1/stock/ideas/refresh")
async def stock_ideas_refresh():
    from api import stock_ideas as si
    if not si.status()["running"]:
        _spawn(si.build_in_background())
    return {"started": True, "status": si.status()}


@router.get("/api/v1/stock/backtest")
async def stock_backtest():
    """Walk-forward backtest of the entry model on the global universe (model vs control
    variants, trade statistics, portfolio curve). Starts the first run when none exists."""
    from api import stock_backtest as sb
    cur = sb.latest()
    if not cur and not sb.status()["running"]:
        _spawn(sb.run_in_background())
    if not cur:
        return {"available": False, "status": sb.status(),
                "reason": "Running the first backtest — downloading ~20 years of prices takes several minutes."}
    return {**cur, "status": sb.status()}


@router.post("/api/v1/stock/backtest/run")
async def stock_backtest_run():
    from api import stock_backtest as sb
    if not sb.status()["running"]:
        _spawn(sb.run_in_background())
    return {"started": True, "status": sb.status()}


_TASKS: set = set()


def _spawn(coro) -> None:
    """Start a background task and keep a reference until it finishes (asyncio only holds
    weak references, so an unreferenced task can be garbage-collected mid-run)."""
    t = asyncio.create_task(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def _iso_ts(s: Optional[str]) -> float:
    try:
        return datetime.fromisoformat(s).timestamp() if s else 0.0
    except ValueError:
        return 0.0


# ── Search & watchlist ───────────────────────────────────────────────────────
_SEARCH_CACHE: Dict[str, tuple] = {}


@router.get("/api/v1/stock/search")
async def stock_search(q: str):
    """Find any listed stock worldwide by name or ticker (Yahoo search), classified by
    market (MSCI class, region, country) and flagged when it is in the screened universe."""
    from api import global_universe as gu
    from api.markets import classify
    query = (q or "").strip()
    if not 1 <= len(query) <= 40:
        raise HTTPException(400, "query must be 1–40 characters")
    key = query.lower()
    hit = _SEARCH_CACHE.get(key)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]

    def _search():
        # Search is a different Yahoo endpoint from fundamentals: its own spacing, and it does
        # not trip or honour the fundamentals pause.
        import yfinance as yf
        try:
            with _yf_lock:
                time.sleep(max(0.0, _yf_state["last"] + _YF_SPACING - time.time()))
                _yf_state["last"] = time.time()
            return yf.Search(query, max_results=12).quotes or []
        except Exception as e:
            logger.debug("[stock] search failed: %s", e)
            return []

    stocks = (await asyncio.to_thread(gu.load, 7, False)).get("stocks", [])
    uni = {s["symbol"] for s in stocks}
    # 1) the screened universe, matched locally (instant, works when Yahoo is throttled)
    ql = gu._fold(key)
    local = [s for s in stocks if s["symbol"].lower() == ql or s["symbol"].lower().startswith(ql + ".")
             or ql in gu._fold(s.get("name") or "")]
    local.sort(key=lambda s: (s["symbol"].lower() != ql, -(s.get("mcap_usd") or 0)))
    rows = [{"symbol": s["symbol"], "name": s.get("name"), "exchange": s.get("exchange"), "type": "EQUITY",
             "sector": s.get("sector"), "in_universe": True, **classify(s["symbol"], s.get("country"))}
            for s in local[:8]]
    seen = {r["symbol"] for r in rows}
    # 2) anything else listed (any exchange Yahoo covers)
    quotes = await asyncio.to_thread(_search)
    for x in quotes:
        if str(x.get("symbol") or "") in seen:
            continue
        if x.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        sym = str(x.get("symbol") or "")
        rows.append({"symbol": sym, "name": x.get("longname") or x.get("shortname") or sym,
                     "exchange": x.get("exchDisp") or x.get("exchange"), "type": x.get("quoteType"),
                     "sector": x.get("sectorDisp") or x.get("sector"), "in_universe": sym in uni, **classify(sym)})
    out = {"query": query, "results": rows}
    if rows:
        _SEARCH_CACHE[key] = (time.time(), out)
    return out


class WatchlistIn(BaseModel):
    symbols: List[str]


def _user(request: Request) -> str:
    from api.core.access import current_user
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Authentication required")
    return u["username"]


@router.get("/api/v1/stock/watchlist")
async def get_watchlist(request: Request):
    from api import stock_ideas as si
    from api.markets import classify
    wl = si._read_json(si.WATCHLIST_FILE, {})
    syms = wl.get(_user(request), [])
    return {"symbols": [{"symbol": s, **classify(s)} for s in syms]}


@router.put("/api/v1/stock/watchlist")
async def put_watchlist(body: WatchlistIn, request: Request):
    """Replace the caller's watchlist (max 100). Watchlist names are always fully analysed in
    the next Stock Ideas build, whatever market they trade in."""
    from api import stock_ideas as si
    user = _user(request)
    syms = list(dict.fromkeys(_norm(s) for s in body.symbols))[:100]
    with si._lock:
        wl = si._read_json(si.WATCHLIST_FILE, {})
        wl[user] = syms
        si.DATA.mkdir(parents=True, exist_ok=True)
        si.WATCHLIST_FILE.write_text(json.dumps(wl))
    return {"symbols": syms}
