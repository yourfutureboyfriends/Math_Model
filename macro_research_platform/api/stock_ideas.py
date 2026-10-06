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
                 min_age_days: int = 5) -> Dict[str, Any]:
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
                r = p1 / p0 - 1
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
async def build_ideas() -> Dict[str, Any]:
    from api.routers.stock import analyze
    t0 = time.time()
    universe = await asyncio.to_thread(load_universe)
    syms = sorted(universe)
    df = await asyncio.to_thread(_bulk_prices, syms)
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
            snaps.append({"symbol": s, "sector": universe.get(s), "price": round(float(c[-1]), 2), **snap})
    try:
        spx = df["^GSPC"]["Close"].dropna()
        spx_now = float(spx.iloc[-1])
    except Exception:
        spx_now = None
    # Stage 2: full model on the strongest price set-ups (sector-capped so one hot sector
    # cannot take every slot).
    cands = diversify([r for r in snaps if (r["price_setup"] or -9) >= st.BUY_SETUP],
                      "price_setup", STAGE2_CANDIDATES, per_sector=8)
    sem = asyncio.Semaphore(5)

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
        enriched.append({
            "symbol": r["symbol"], "name": a.get("name"), "sector": r["sector"], "price": a["price"],
            "setup_score": a["setup_score"], "timing_score": (a.get("timing") or {}).get("score"),
            "timing_state": (a.get("timing") or {}).get("state"),
            "verdict": a["verdict"]["code"], "verdict_label": a["verdict"]["label"],
            **{"rationale": (rr := rationale(a))["pros"], "risks": rr["cons"]},
            "entry_low": lv.get("entry_low"), "entry_high": lv.get("entry_high"), "stop": lv.get("stop"),
            "target": lv.get("target"), "target_basis": lv.get("target_basis"), "reward_risk": lv.get("reward_risk"),
            "shares": lv.get("shares"), "pct_nav": lv.get("pct_nav"),
            "upside": ((a.get("components") or {}).get("analysts") or {}).get("upside"),
        })
    buy = diversify([e for e in enriched if e["verdict"] == "BUY"], "setup_score", MAX_BUY)
    pullback = diversify([e for e in enriched if e["verdict"] == "WAIT"], "setup_score", MAX_PULLBACK)
    market = st.market_component(df["^GSPC"]["Close"].dropna().to_numpy(dtype=float), None) if spx_now else None
    prev = _read_json(STATE_FILE, None)
    # "What changed" compares with the previous trading day's list (a same-day rebuild keeps
    # comparing with that day, not with this morning's run).
    if prev and prev.get("date") != date.today().isoformat():
        prev_buy = [b["symbol"] for b in prev.get("buy", [])]
        prev_date = prev.get("date")
    else:
        prev_buy = (prev or {}).get("previous_buy")
        prev_date = (prev or {}).get("previous_date")
    state = {
        "available": True, "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "date": date.today().isoformat(), "universe": "S&P 500", "universe_size": len(syms),
        "screened": len(snaps), "stage2": len(enriched), "build_seconds": round(time.time() - t0, 1),
        "market": market, "buy": buy, "pullback": pullback,
        "sector_counts": _sector_counts(snaps),
        # Market breadth: share of the index above its 200-day average.
        "breadth_above_200d": round(float(np.mean([s_["above_200d"] for s_ in snaps])), 3) if snaps else None,
        "previous_buy": prev_buy, "previous_date": prev_date,
    }
    state["changes"] = diff_runs({"buy": [{"symbol": x} for x in prev_buy]} if prev_buy is not None else None, state)
    # Log once per day (latest run of the day wins) for the track record.
    log = _read_json(LOG_FILE, [])
    log = [r for r in log if r.get("date") != state["date"]] + [{
        "date": state["date"], "spx": spx_now,
        "buy": [{"symbol": b["symbol"], "price": b["price"]} for b in buy]}]
    state["track_record"] = track_record(log, last_px, spx_now)
    with _lock:
        DATA.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, default=str))
        LOG_FILE.write_text(json.dumps(log[-400:], default=str))
    logger.info("[ideas] %d screened, %d analysed, %d buy / %d pullback in %.0fs",
                len(snaps), len(enriched), len(buy), len(pullback), time.time() - t0)
    return state


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
