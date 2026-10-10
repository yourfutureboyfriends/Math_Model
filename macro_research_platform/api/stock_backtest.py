"""
Stock entry-model backtest — data and orchestration (engine: api/calculations/stock_backtest.py).

Sample: the largest ~20% of every market in the global universe (at least 3 per market), so
all MSCI classes and regions are represented. History from 2004 (Yahoo, split/dividend
adjusted), each stock's home index for the regime gate, VIX for risk appetite. Prices are
cached for a month; results in data/processed/stock_backtest.json.

Survivorship: the sample is TODAY's largest stocks, which flatters any long-only test (the
2005 constituents that later failed are missing). The variants share that bias, so the
honest comparison is model vs control on the same stocks and dates — not the absolute CAGR.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from api.calculations import stock_backtest as bt

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
RESULT_FILE = DATA / "stock_backtest.json"
PRICE_CACHE = DATA / "backtest" / "prices.pkl"
START = "2004-01-01"
SAMPLE_FRACTION = 0.2
SAMPLE_MIN = 3
PRICE_MAX_AGE_DAYS = 30
_state = {"running": False, "started": None, "error": None, "stage": None}


def sample(universe: Dict[str, Any], fraction: float = SAMPLE_FRACTION, minimum: int = SAMPLE_MIN) -> List[Dict]:
    """Largest `fraction` of each market by USD market cap (at least `minimum`)."""
    by_c: Dict[str, List[Dict]] = {}
    for s in universe.get("stocks", []):
        by_c.setdefault(s["country"], []).append(s)
    out = []
    for c, xs in by_c.items():
        xs = sorted(xs, key=lambda s: -(s.get("mcap_usd") or 0))
        out.extend(xs[: max(minimum, math.ceil(len(xs) * fraction))])
    return out


def _download(symbols: List[str]):
    import pandas as pd
    import yfinance as yf
    frames = []
    for k in range(0, len(symbols), 80):
        part = symbols[k:k + 80]
        for attempt in range(3):
            try:
                df = yf.download(part, start=START, interval="1d", auto_adjust=True, group_by="ticker",
                                 threads=True, progress=False)
                frames.append(df)
                break
            except Exception as e:
                logger.warning("[backtest] download %d-%d failed (%s), retrying", k, k + len(part), e)
                time.sleep(5 * (attempt + 1))
        _state["stage"] = f"downloading prices {min(k + 80, len(symbols))}/{len(symbols)}"
        time.sleep(1.0)
    return pd.concat(frames, axis=1) if frames else None


def _prices(symbols: List[str]):
    """{symbol: DataFrame[Open, High, Low, Close]} from the cache, refreshed monthly."""
    import pandas as pd
    cached: Dict[str, Any] = {}
    try:
        if time.time() - PRICE_CACHE.stat().st_mtime < PRICE_MAX_AGE_DAYS * 86400:
            cached = pd.read_pickle(PRICE_CACHE)
    except Exception:
        cached = {}
    missing = [s for s in symbols if s not in cached]
    if missing:
        df = _download(missing)
        if df is not None:
            for s in missing:
                try:
                    sub = df[s][["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
                except Exception:
                    continue
                if len(sub) > bt.WARMUP + 50:
                    cached[s] = sub
        PRICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(cached, PRICE_CACHE)
    return cached


def _regime(stock_index, idx_close, vix_close) -> np.ndarray:
    """1 = home index above its 200-day average and VIX < 25 on that date, 0 = not,
    NaN = no index history yet (the live model treats unknown as risk-on)."""
    if idx_close is None or len(idx_close) < 200:
        return np.full(len(stock_index), np.nan)
    sma = idx_close.rolling(200).mean()
    up = (idx_close > sma).astype(float).where(sma.notna())
    up = up.reindex(stock_index, method="ffill")
    calm = 1.0
    if vix_close is not None:
        calm = (vix_close.reindex(stock_index, method="ffill") < 25).astype(float)
    return (up * calm).where(up.notna()).to_numpy(dtype=float)


def run() -> Dict[str, Any]:
    from api import global_universe as gu
    t0 = time.time()
    _state["stage"] = "loading universe"
    names = sample(gu.load(rebuild_if_stale=False))
    if not names:
        raise RuntimeError("global universe unavailable")
    meta = {s["symbol"]: s for s in names}
    benches = sorted({s.get("benchmark") for s in names if s.get("benchmark")})
    px = _prices(sorted(meta) + benches + ["^VIX"])
    vix = px["^VIX"]["Close"] if "^VIX" in px else None

    _state["stage"] = "simulating"
    trades: List[bt.Trade] = []
    closes: Dict[str, np.ndarray] = {}
    dates: Dict[str, List[str]] = {}
    for sym, m in meta.items():
        df = px.get(sym)
        if df is None:
            continue
        ds = [d.strftime("%Y-%m-%d") for d in df.index]
        bench = px.get(m.get("benchmark"))
        reg = _regime(df.index, bench["Close"] if bench is not None else None, vix)
        o, h, l, c = bt.clean_ohlc(*(df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close")))
        ts = bt.simulate(sym, ds, o, h, l, c, reg, m.get("market_class", "Developed"))
        for t in ts:
            t.meta.update(country=m["country"], region=m.get("region"))
        trades.extend(ts)
        closes[sym], dates[sym] = c, ds
    if not trades:
        raise RuntimeError("no price history downloaded")

    _state["stage"] = "portfolio"
    calendar = sorted({d for ds in dates.values() for d in ds[bt.WARMUP:]})
    by_v = {v: [t for t in trades if t.variant == v] for v in bt.VARIANTS}
    curves, perfs, ports = {}, {}, {}
    for v in bt.VARIANTS:
        p = bt.portfolio(by_v[v], closes, dates, calendar)
        ports[v] = p
        perfs[v] = {**bt.perf(p["ret"], calendar), "avg_gross": round(float(p["gross"].mean()), 3),
                    "taken": p["taken"], "skipped": p["skipped"]}
        curves[v] = p["nav"]
    ew = bt.equal_weight(closes, dates, calendar)
    perfs["equal_weight"] = bt.perf(ew, calendar)
    curves["equal_weight"] = np.cumprod(1 + ew)

    model = by_v["model"]
    mid = calendar[len(calendar) // 2]
    result = {
        "available": True,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
        "build_seconds": round(time.time() - t0, 1),
        "sample": {"stocks": len(closes), "markets": len({meta[s]["country"] for s in closes}),
                   "by_class": _count(meta[s].get("market_class") for s in closes),
                   "start": calendar[0], "end": calendar[-1], "years": round(bt.span_years(calendar), 1)},
        "rules": {"setup": bt.BUY_SETUP, "timing": bt.EXTENDED_TIMING, "stop_atr": bt.STOP_ATR,
                  "target_r": bt.TARGET_R, "max_hold": bt.MAX_HOLD, "costs": bt.COST_BY_CLASS,
                  "risk_per_trade": bt.RISK_PER_TRADE, "max_position": bt.MAX_POSITION, "max_gross": bt.MAX_GROSS},
        "variants": {v: {"trades": bt.trade_stats(by_v[v]), "portfolio": perfs[v]} for v in bt.VARIANTS},
        "equal_weight": perfs["equal_weight"],
        "tests": {
            "model_vs_control": bt.diff_test(model, by_v["control"]),
            "timing_filter": bt.diff_test(model, by_v["setup_only"]),
            "buy_vs_buy_small": bt.diff_test([t for t in model if t.label == "BUY"],
                                             [t for t in model if t.label == "BUY_SMALL"]),
        },
        "breakdown": {
            "label": bt.group_stats(model, lambda t: t.label),
            "market_class": bt.group_stats(model, lambda t: t.meta.get("market_class")),
            "region": bt.group_stats(model, lambda t: t.meta.get("region")),
            "setup": bt.group_stats(model, bt.setup_bucket),
            "year": bt.group_stats(model, lambda t: t.entry_date[:4]),
            "half": bt.group_stats(model, lambda t: "first half" if t.entry_date < mid else "second half"),
            "control_year": bt.group_stats(by_v["control"], lambda t: t.entry_date[:4]),
        },
        "curve": bt.downsample(calendar, curves),
    }
    result["findings"] = findings(result)
    DATA.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(result))
    logger.info("[backtest] %d stocks, %d model trades in %.0fs", len(closes), len(model), time.time() - t0)
    return result


def _count(xs) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for x in xs:
        out[x or "n/a"] = out.get(x or "n/a", 0) + 1
    return out


def findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    """Plain-language conclusions, each tied to the statistic that supports it."""
    out: List[Dict[str, str]] = []
    v, t = r["variants"], r["tests"]
    m, ctl = v["model"]["trades"], v["control"]["trades"]
    mc = t.get("model_vs_control")
    if mc and mc.get("t_stat") is not None:
        edge, tv = mc["diff_r"], mc["t_stat"]
        sig = abs(tv) >= 2
        out.append({"tone": "good" if edge > 0 and sig else "bad" if edge < 0 and sig else "neutral",
                    "title": "Signal vs no signal",
                    "text": f"Model trades average {m['avg_r']:+.2f}R vs {ctl['avg_r']:+.2f}R for unconditional entries with "
                            f"the same exits ({edge:+.2f}R, t = {tv:.1f}) — "
                            + ("a statistically meaningful edge." if edge > 0 and sig else
                               "the signal does worse than random entry." if edge < 0 and sig else
                               "a small edge, only marginally significant." if edge > 0 and tv >= 1.65 else
                               "not distinguishable from random entry.")
                            + (" The control is profitable too: the sample is today's survivors, so any long entry"
                               " with these exits made money." if ctl.get("avg_r", 0) > 0.1 else "")})
    tf = t.get("timing_filter")
    if tf and tf.get("t_stat") is not None:
        out.append({"tone": "good" if tf["diff_r"] > 0 and tf["t_stat"] >= 2 else "bad" if tf["diff_r"] < 0 and tf["t_stat"] <= -2 else "neutral",
                    "title": "Pullback entry filter",
                    "text": f"Waiting for a non-extended entry changes the average trade by {tf['diff_r']:+.2f}R "
                            f"(t = {tf['t_stat']:.1f}) vs buying every strong set-up."})
    bb = t.get("buy_vs_buy_small")
    if bb and bb.get("t_stat") is not None:
        pm, pg = v["model"]["portfolio"], v["regime_gate"]["portfolio"]
        safer = (pg.get("sharpe") or 0) > (pm.get("sharpe") or 0) and pg.get("max_drawdown", -1) > pm.get("max_drawdown", -1)
        trade_word = ("risk-on trades did better" if bb["diff_r"] > 0 and bb["t_stat"] >= 2 else
                      "risk-off entries did slightly better per trade" if bb["diff_r"] < 0 and bb["t_stat"] <= -2 else
                      "no difference per trade")
        out.append({"tone": "good" if safer else "bad" if bb["t_stat"] <= -2 else "neutral",
                    "title": "Market regime gate",
                    "text": f"BUY vs BUY_SMALL: {bb['diff_r']:+.2f}R (t = {bb['t_stat']:.1f}) — {trade_word}. "
                            f"Skipping risk-off signals: Sharpe {pg.get('sharpe')} vs {pm.get('sharpe')}, drawdown "
                            f"{pg.get('max_drawdown', 0):.0%} vs {pm.get('max_drawdown', 0):.0%}"
                            + (" — the gate earns its keep as risk control, not as alpha." if safer else ".")})
    sb = {g["group"]: g for g in r["breakdown"]["setup"]}
    if len(sb) == 3 and all(sb[k]["trades"] >= 30 for k in sb):
        lo, hi = sb["0.35–0.50"]["avg_r"], sb["≥ 0.70"]["avg_r"]
        out.append({"tone": "good" if hi > lo else "neutral", "title": "Score monotonicity",
                    "text": f"Set-up ≥ 0.70 averages {hi:+.2f}R vs {lo:+.2f}R for 0.35–0.50 — "
                            + ("stronger scores do better, as they should." if hi > lo else
                               "a higher score does not mean a better trade; the threshold matters more than the level.")})
    yrs = [g for g in r["breakdown"]["year"] if g["trades"] >= 20]
    if yrs:
        pos = sum(1 for g in yrs if g["avg_r"] > 0)
        worst = min(yrs, key=lambda g: g["avg_r"])
        out.append({"tone": "good" if pos / len(yrs) >= 0.7 else "neutral", "title": "Consistency",
                    "text": f"Average trade positive in {pos} of {len(yrs)} years; worst {worst['group']} ({worst['avg_r']:+.2f}R)."})
    mp, cp, ew = v["model"]["portfolio"], v["control"]["portfolio"], r["equal_weight"]
    if mp.get("sharpe") is not None and ew.get("sharpe") is not None:
        out.append({"tone": "good" if mp["sharpe"] > max(ew["sharpe"], cp.get("sharpe") or 0) else "neutral", "title": "Portfolio",
                    "text": f"Trading every signal: {mp['cagr']:+.1%} a year, Sharpe {mp['sharpe']:.2f}, max drawdown "
                            f"{mp['max_drawdown']:.0%} at {mp['avg_gross']:.0%} average exposure. Control {cp.get('cagr', 0):+.1%} "
                            f"(Sharpe {cp.get('sharpe')}, drawdown {cp.get('max_drawdown', 0):.0%}); equal-weight hold of the same "
                            f"stocks {ew['cagr']:+.1%} (Sharpe {ew['sharpe']:.2f}, drawdown {ew['max_drawdown']:.0%})."})
    return out


def latest() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(RESULT_FILE.read_text())
    except Exception:
        return None


async def run_in_background() -> None:
    if _state["running"]:
        return
    _state.update(running=True, started=time.time(), error=None, stage="starting")
    try:
        await asyncio.to_thread(run)
    except Exception as e:
        logger.error("[backtest] failed: %s", e, exc_info=True)
        _state["error"] = str(e)[:200]
    finally:
        _state.update(running=False, stage=None)


def status() -> Dict[str, Any]:
    return {"running": _state["running"], "stage": _state["stage"], "error": _state["error"],
            "running_for_s": round(time.time() - _state["started"]) if _state["running"] else None}
