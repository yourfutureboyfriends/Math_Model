"""
Stock ideas — the system proposes stocks instead of waiting to be asked.

A two-stage funnel, as quant equity desks run screens:
  1. Price screen over the whole S&P 500 (one bulk download): the price-based part of the
     entry model — trend, volatility-scaled 12-1 momentum, 52-week-high proximity and entry
     timing (api/calculations/stock_timing.py). Cheap, so it covers ~500 names.
  2. Full analysis of the best candidates: earnings drift, sell-side consensus / revisions,
     quality, levels and size (api/routers/stock.analyze).

Then: BUY verdicts become "Buy now" ideas, strong set-ups that are stretched become the
"Buy on pullback" list; at most MAX_PER_SECTOR names per GICS sector so the list is not one
crowded theme. Every run is logged with prices, so past suggestions get a track record
against the S&P 500 (did the ideas actually work?).
"""
from __future__ import annotations

import asyncio
import io
import json
import math
import logging
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from api.calculations import stock_timing as st

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
UNIVERSE_FILE = DATA / "sp500_universe.json"
STATE_FILE = DATA / "stock_ideas.json"
LOG_FILE = DATA / "stock_ideas_log.json"
STAGE2_CANDIDATES = 40
MAX_PER_SECTOR = 3
MAX_BUY = 12
MAX_PULLBACK = 10
_lock = threading.Lock()
_building = {"running": False, "started": None, "error": None}

# Fallback if the constituent list cannot be fetched: large caps across sectors.
FALLBACK = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "NVDA": "Information Technology",
    "AVGO": "Information Technology", "ORCL": "Information Technology", "CRM": "Information Technology",
    "AMD": "Information Technology", "ADBE": "Information Technology", "CSCO": "Information Technology",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary", "GOOGL": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "JPM": "Financials", "V": "Financials", "MA": "Financials",
    "BAC": "Financials", "GS": "Financials", "UNH": "Health Care", "LLY": "Health Care", "JNJ": "Health Care",
    "MRK": "Health Care", "ABBV": "Health Care", "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples", "COST": "Consumer Staples",
    "WMT": "Consumer Staples", "CAT": "Industrials", "GE": "Industrials", "RTX": "Industrials",
    "LIN": "Materials", "NEE": "Utilities", "PLD": "Real Estate",
}


# ── Pure helpers (tested) ────────────────────────────────────────────────────
def price_snapshot(c: np.ndarray, h: np.ndarray, l: np.ndarray) -> Optional[Dict[str, Any]]:
    """Stage-1 score from prices alone (same components and weights as the full model)."""
    comps = {"trend": st.trend_component(c), "momentum": st.momentum_component(c),
             "high_52w": st.high52_component(c)}
    if not all(comps.values()):
        return None
    setup = st.combine_setup(comps)
    if setup is None or not np.isfinite(setup):
        return None
    timing = st.timing_component(c, h, l)
    return {"price_setup": setup, "timing": timing["score"] if timing else None,
            "timing_state": timing["state"] if timing else None,
            "return_12_1": comps["momentum"]["return_12_1"], "ratio_52w": comps["high_52w"]["ratio"],
            "above_200d": comps["trend"]["score"] >= 0.5}


def diversify(rows: List[Dict[str, Any]], key: str, limit: int, per_sector: int = MAX_PER_SECTOR) -> List[Dict]:
    """Best rows by `key` (desc) with at most `per_sector` per sector."""
    out, used = [], {}
    for r in sorted(rows, key=lambda r: -(r.get(key) or -9)):
        s = r.get("sector") or "Other"
        if used.get(s, 0) >= per_sector:
            continue
        used[s] = used.get(s, 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    return out


def rationale(full: Dict[str, Any]) -> Dict[str, List[str]]:
    """Specific reasons FOR the idea and the risks AGAINST it, from the full analysis."""
    c = full.get("components") or {}
    pros: List[str] = []
    cons: List[str] = []
    if (c.get("trend") or {}).get("score", 0) >= 1:
        pros.append("Uptrend (above 50/200-day)")
    m = c.get("momentum")
    if m and m.get("return_12_1") is not None:
        (pros if m["return_12_1"] > 0 else cons).append(f"12-1M {m['return_12_1']:+.0%}")
    h = c.get("high_52w")
    if h and h.get("ratio", 0) >= 0.95:
        pros.append(f"{h['ratio']:.0%} of 52-wk high")
    e = c.get("earnings")
    if e and e.get("surprise_pct") is not None and e.get("days_since", 999) <= 90:
        (pros if e["surprise_pct"] > 0 else cons).append(f"EPS surprise {e['surprise_pct']:+.0f}%")
    if e and e.get("next_date"):
        try:
            days = (date.fromisoformat(e["next_date"]) - date.today()).days
            if 0 <= days <= 14:
                cons.append(f"Earnings in {days}d")
        except ValueError:
            pass
    a = c.get("analysts")
    if a:
        up = a.get("upside")
        if up is not None:
            (pros if up >= 0.05 else cons).append(f"Target {up:+.0%}")
        if a.get("upgrades"):
            pros.append(f"{a['upgrades']} upgrade{'s' if a['upgrades'] > 1 else ''} (90d)")
        if a.get("downgrades"):
            cons.append(f"{a['downgrades']} downgrade{'s' if a['downgrades'] > 1 else ''} (90d)")
        if (a.get("target_raises") or 0) > (a.get("target_cuts") or 0):
            pros.append(f"{a['target_raises']} target raises")
        elif (a.get("target_cuts") or 0) > (a.get("target_raises") or 0):
            cons.append(f"{a['target_cuts']} target cuts")
    q = c.get("quality")
    if q:
        if q.get("score", 0) >= 0.5:
            pros.append("High quality")
        elif q.get("score", 0) < 0:
            cons.append("Weak profitability / high leverage")
    t = full.get("timing") or {}
    if t.get("state") == "pullback":
        pros.append("On a pullback")
    elif t.get("state") == "extended":
        cons.append("Price stretched")
    return {"pros": pros, "cons": cons}


def diff_runs(prev: Optional[Dict], cur: Dict) -> Dict[str, List[str]]:
    p = {r["symbol"] for r in (prev or {}).get("buy", [])}
    c = {r["symbol"] for r in cur.get("buy", [])}
    return {"new": sorted(c - p), "dropped": sorted(p - c)} if prev else {"new": sorted(c), "dropped": []}


def track_record(log: List[Dict[str, Any]], prices: Dict[str, float], spx_now: Optional[float],
                 min_age_days: int = 5, usd_now: Optional[Dict[str, Optional[float]]] = None) -> Dict[str, Any]:
    """Return since each logged BUY idea vs the S&P 500 over the same period. Only ideas at
    least `min_age_days` old count; each symbol counts once per run."""
    today = date.today()
    rows = []
    for run in log:
        d = date.fromisoformat(run["date"])
        if (today - d).days < min_age_days or not run.get("spx"):
            continue
        for idea in run.get("buy", []):
            p0, p1 = idea.get("price"), prices.get(idea["symbol"])
            if p0 and p1 and spx_now:
                r = usd_return(p0, idea.get("usd"), p1, (usd_now or {}).get(idea["symbol"]))
                b = spx_now / run["spx"] - 1
                rows.append({"date": run["date"], "symbol": idea["symbol"], "return": round(r, 4),
                             "spx_return": round(b, 4), "excess": round(r - b, 4)})
    if not rows:
        return {"ideas": 0, "message": f"Track record starts once ideas are {min_age_days}+ days old."}
    ex = np.array([r["excess"] for r in rows])
    return {"ideas": len(rows), "avg_return": round(float(np.mean([r["return"] for r in rows])), 4),
            "avg_excess": round(float(ex.mean()), 4), "beat_spx": round(float((ex > 0).mean()), 3),
            "since": min(r["date"] for r in rows), "recent": sorted(rows, key=lambda r: r["date"])[-15:]}


# ── Data ─────────────────────────────────────────────────────────────────────
def load_universe(max_age_days: int = 7) -> Dict[str, str]:
    """{symbol: GICS sector} for the S&P 500 (Wikipedia's constituent table, cached a week)."""
    try:
        if UNIVERSE_FILE.exists():
            cached = json.loads(UNIVERSE_FILE.read_text())
            if time.time() - cached.get("saved_at", 0) < max_age_days * 86400 and cached.get("symbols"):
                return cached["symbols"]
    except Exception:
        pass
    try:
        import pandas as pd
        import requests
        html = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                            headers={"User-Agent": "Mozilla/5.0 (macro-terminal research)"}, timeout=20).text
        tb = pd.read_html(io.StringIO(html))[0]
        syms = {str(s).replace(".", "-"): str(sec) for s, sec in zip(tb["Symbol"], tb["GICS Sector"])}
        if len(syms) > 400:
            DATA.mkdir(parents=True, exist_ok=True)
            UNIVERSE_FILE.write_text(json.dumps({"saved_at": time.time(), "symbols": syms}))
            return syms
    except Exception as e:
        logger.warning("[ideas] S&P 500 list unavailable: %s", e)
    try:
        return json.loads(UNIVERSE_FILE.read_text())["symbols"]
    except Exception:
        return dict(FALLBACK)


def _bulk_prices(symbols: List[str]):
    import yfinance as yf
    return yf.download(symbols + ["^GSPC"], period="2y", interval="1d", auto_adjust=True,
                       group_by="ticker", threads=True, progress=False)


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


# ── Build ────────────────────────────────────────────────────────────────────
WATCHLIST_FILE = DATA / "stock_watchlists.json"
# Stage-2 slots per MSCI class (and at most STAGE2_PER_COUNTRY per country), so the full
# model looks at the strongest set-ups across markets rather than only the largest market.
STAGE2_QUOTA = {"Developed": 50, "Emerging": 34, "Frontier": 4, "Standalone": 3, "Unclassified": 6}
STAGE2_PER_COUNTRY = 7
LIST_PER_COUNTRY = 6
LIST_PER_SECTOR = 5
LIST_MAX = 60


def watchlist_symbols() -> List[str]:
    wl = _read_json(WATCHLIST_FILE, {})
    return sorted({s for syms in wl.values() for s in syms})


def _chunks(xs: List[str], n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _download(symbols: List[str]):
    """Daily OHLC for many symbols, in chunks (Yahoo bulk endpoint)."""
    import pandas as pd
    import yfinance as yf
    frames = []
    for part in _chunks(symbols, 400):
        try:
            frames.append(yf.download(part, period="2y", interval="1d", auto_adjust=True,
                                      group_by="ticker", threads=True, progress=False))
        except Exception as e:
            logger.warning("[ideas] download chunk failed: %s", e)
    return pd.concat(frames, axis=1) if frames else None


def cap_by(rows: List[Dict], key: str, limit: int, caps: Dict[str, int]) -> List[Dict]:
    """Best rows by `key` with at most caps[field] rows sharing each value of `field`."""
    out, used = [], {f: {} for f in caps}
    for r in sorted(rows, key=lambda r: -(r.get(key) or -9)):
        # A missing value (e.g. no sector while fundamentals are unavailable) is not a group:
        # capping all of them together as "Other" cut most non-US ideas.
        if any(r.get(f) and used[f].get(r[f], 0) >= n for f, n in caps.items()):
            continue
        for f in caps:
            if r.get(f):
                used[f][r[f]] = used[f].get(r[f], 0) + 1
        out.append(r)
        if len(out) >= limit:
            break
    return out


def usd_return(p0: float, fx0: Optional[float], p1: float, fx1: Optional[float]) -> float:
    """Return in USD from local prices and USD-per-unit rates at both dates."""
    if fx0 and fx1:
        return (p1 * fx1) / (p0 * fx0) - 1
    return p1 / p0 - 1


async def build_ideas() -> Dict[str, Any]:
    from api import global_universe as gu
    from api.markets import classify, minor_unit_factor
    from api.routers.stock import analyze
    t0 = time.time()
    uni = await asyncio.to_thread(gu.load)
    meta = {s["symbol"]: s for s in uni.get("stocks", [])}
    if not meta:                                         # fall back to the S&P 500
        meta = {s: {"symbol": s, "sector": sec, **classify(s, "US")} for s, sec in (await asyncio.to_thread(load_universe)).items()}
    watch = await asyncio.to_thread(watchlist_symbols)
    for w in watch:
        meta.setdefault(w, {"symbol": w, **classify(w)})
    fx = uni.get("fx") or {}
    try:
        fx = await asyncio.to_thread(gu.fx_rates)        # today's rates for the USD track record
    except Exception:
        pass
    syms = sorted(meta)
    df = await asyncio.to_thread(_download, syms + ["ACWI"])
    snaps, last_px = [], {}
    for s in syms:
        try:
            sub = df[s].dropna(subset=["Close"])
        except Exception:
            continue
        if len(sub) < 260:
            continue
        c, h, l = (sub[k].to_numpy(dtype=float) for k in ("Close", "High", "Low"))
        last_px[s] = float(c[-1])
        snap = price_snapshot(c, h, l)
        if snap:
            m = meta[s]
            snaps.append({"symbol": s, "name": m.get("name"), "sector": m.get("sector"),
                          "country": m.get("country"), "country_name": m.get("country_name"),
                          "market_class": m.get("market_class"), "region": m.get("region"),
                          "currency": m.get("currency"), "mcap_usd": m.get("mcap_usd"),
                          "price": round(float(c[-1]), 4), **snap})
    try:
        acwi = df["ACWI"]["Close"].dropna()
        bench_now = float(acwi.iloc[-1])
    except Exception:
        acwi, bench_now = None, None

    # Stage 2: strongest price set-ups per MSCI class, capped per country; plus the watchlist.
    strong = [r for r in snaps if (r["price_setup"] or -9) >= st.BUY_SETUP]
    cands: List[Dict] = []
    for cls, quota in STAGE2_QUOTA.items():
        cands += cap_by([r for r in strong if (r.get("market_class") or "Unclassified") == cls],
                        "price_setup", quota, {"country": STAGE2_PER_COUNTRY})
    have = {r["symbol"] for r in cands}
    cands += [r for r in snaps if r["symbol"] in watch and r["symbol"] not in have][:20]
    sem = asyncio.Semaphore(6)

    async def full(r):
        async with sem:
            a = await analyze(r["symbol"], with_history=False)
        return r, a

    results = await asyncio.gather(*[full(r) for r in cands])
    enriched = []
    for r, a in results:
        if not a.get("available"):
            continue
        lv = a.get("levels") or {}
        why = rationale(a)
        enriched.append({
            "symbol": r["symbol"],
            # analyze() falls back to the ticker when fundamentals are unavailable; the
            # universe (screener) has the company name.
            "name": a.get("name") if a.get("name") and a.get("name") != r["symbol"] else (r.get("name") or r["symbol"]),
            "sector": a.get("sector") or r.get("sector"),
            "country": a.get("country"), "country_name": a.get("country_name"), "market_class": a.get("market_class"),
            "region": a.get("region"), "currency": a.get("currency"), "exchange": a.get("exchange"),
            "mcap_usd": r.get("mcap_usd"), "price": a["price"], "px_to_usd": a.get("px_to_usd"),
            "setup_score": a["setup_score"], "timing_score": (a.get("timing") or {}).get("score"),
            "timing_state": (a.get("timing") or {}).get("state"),
            "verdict": a["verdict"]["code"], "verdict_label": a["verdict"]["label"],
            "market_ok": (a.get("market") or {}).get("ok"),
            "rationale": why["pros"], "risks": why["cons"], "watchlist": r["symbol"] in watch,
            "entry_low": lv.get("entry_low"), "entry_high": lv.get("entry_high"), "stop": lv.get("stop"),
            "target": lv.get("target"), "target_basis": lv.get("target_basis"), "reward_risk": lv.get("reward_risk"),
            "shares": lv.get("shares"), "pct_nav": lv.get("pct_nav"), "notional_usd": lv.get("notional"),
            "upside": ((a.get("components") or {}).get("analysts") or {}).get("upside"),
        })
    caps = {"country": LIST_PER_COUNTRY, "sector": LIST_PER_SECTOR}
    buy = cap_by([e for e in enriched if e["verdict"] == "BUY"], "setup_score", LIST_MAX, caps)
    pullback = cap_by([e for e in enriched if e["verdict"] in ("WAIT", "BUY_SMALL")], "setup_score", LIST_MAX, caps)
    watch_rows = [e for e in enriched if e["watchlist"]]
    market = st.market_component(acwi.to_numpy(dtype=float), None, "MSCI ACWI") if acwi is not None else None

    prev = _read_json(STATE_FILE, None)
    if prev and prev.get("date") != date.today().isoformat():
        prev_buy, prev_date = [b["symbol"] for b in prev.get("buy", [])], prev.get("date")
    else:
        prev_buy, prev_date = (prev or {}).get("previous_buy"), (prev or {}).get("previous_date")
    state = {
        "available": True, "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "date": date.today().isoformat(), "universe": "Global (MSCI DM + EM + frontier)",
        "universe_size": len(syms), "screened": len(snaps), "stage2": len(enriched),
        "build_seconds": round(time.time() - t0, 1), "market": market,
        "stage2_verdicts": {v: sum(1 for e in enriched if e["verdict"] == v) for v in sorted({e["verdict"] for e in enriched})},
        "fundamentals_coverage": round(sum(1 for e in enriched if e.get("upside") is not None) / len(enriched), 3) if enriched else None,
        "buy": buy, "pullback": pullback, "watchlist": watch_rows,
        "by_class": _group_stats(snaps, "market_class"), "by_region": _group_stats(snaps, "region"),
        "by_country": _group_stats(snaps, "country", name_field="country_name"),
        "sector_counts": _sector_counts([x for x in snaps if x.get("sector")]),
        "breadth_above_200d": round(float(np.mean([x["above_200d"] for x in snaps])), 3) if snaps else None,
        "previous_buy": prev_buy, "previous_date": prev_date,
    }
    state["changes"] = diff_runs({"buy": [{"symbol": x} for x in prev_buy]} if prev_buy is not None else None, state)
    # Track record in USD vs MSCI ACWI (log once per day; latest run of the day wins).
    # Today's USD-per-unit, from each idea's own quote currency (recorded when suggested).
    # A symbol with no known currency gets None (local-currency return), never a rate of
    # 1.0 against a stored yen rate.
    ccy_of = {s_: (meta.get(s_) or {}).get("currency") for s_ in last_px}
    for run in _read_json(LOG_FILE, []):
        for i in run.get("buy", []):
            if i.get("ccy") and not ccy_of.get(i["symbol"]):
                ccy_of[i["symbol"]] = i["ccy"]
    for e in enriched:
        ccy_of[e["symbol"]] = e.get("currency") or ccy_of.get(e["symbol"])
    usd_now = {}
    for s_, p in last_px.items():
        q = ccy_of.get(s_)
        if not q:
            usd_now[s_] = None
            continue
        major, div = minor_unit_factor(q)
        rate = 1.0 if major == "USD" else fx.get(major)
        usd_now[s_] = (1.0 / rate) / div if rate else None
    log = _read_json(LOG_FILE, [])
    log = [r for r in log if r.get("date") != state["date"]] + [{
        "date": state["date"], "spx": bench_now, "benchmark": "ACWI",
        "buy": [{"symbol": b["symbol"], "price": b["price"], "usd": b.get("px_to_usd"), "ccy": b.get("currency")} for b in buy]}]
    state["track_record"] = track_record(log, last_px, bench_now, usd_now=usd_now)
    with _lock:
        DATA.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, default=str))
        LOG_FILE.write_text(json.dumps(log[-400:], default=str))
    logger.info("[ideas] %d screened, %d analysed, %d buy / %d pullback in %.0fs",
                len(snaps), len(enriched), len(buy), len(pullback), time.time() - t0)
    return state


def _group_stats(snaps: List[Dict], field: str, name_field: Optional[str] = None) -> List[Dict[str, Any]]:
    by: Dict[str, List[Dict]] = {}
    for x in snaps:
        by.setdefault(x.get(field) or "Other", []).append(x)
    def fin(x) -> bool:
        return isinstance(x, (int, float)) and math.isfinite(x)
    out = []
    for k, v in by.items():
        setups = [x["price_setup"] for x in v if fin(x.get("price_setup"))]
        out.append({"key": k, "name": (v[0].get(name_field) if name_field else k) or k, "names": len(v),
                    "above_200d": round(float(np.mean([bool(x["above_200d"]) for x in v])), 3),
                    "strong": sum(1 for x in setups if x >= st.BUY_SETUP),
                    "avg_setup": round(float(np.mean(setups)), 3) if setups else None})
    return sorted(out, key=lambda r: -(r["avg_setup"] if r["avg_setup"] is not None else -9))


def _sector_counts(snaps: List[Dict]) -> List[Dict[str, Any]]:
    by: Dict[str, List[float]] = {}
    for s in snaps:
        by.setdefault(s.get("sector") or "Other", []).append(s["price_setup"] or 0)
    return sorted([{"sector": k, "names": len(v), "strong": sum(1 for x in v if x >= st.BUY_SETUP),
                    "avg_setup": round(float(np.mean(v)), 3)} for k, v in by.items()],
                  key=lambda r: -r["avg_setup"])


def latest() -> Optional[Dict[str, Any]]:
    return _read_json(STATE_FILE, None)


async def build_in_background() -> None:
    if _building["running"]:
        return
    _building.update(running=True, started=time.time(), error=None)
    try:
        await build_ideas()
    except Exception as e:
        logger.error("[ideas] build failed: %s", e, exc_info=True)
        _building["error"] = str(e)[:200]
    finally:
        _building["running"] = False


def status() -> Dict[str, Any]:
    return {"running": _building["running"],
            "running_for_s": round(time.time() - _building["started"]) if _building["running"] else None,
            "error": _building["error"]}
