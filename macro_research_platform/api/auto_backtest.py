"""
Auto-book backtest service (engine: api/calculations/auto_backtest.py) and the live-vs-
backtest comparison.

Runs the auto book's current rules over the stock backtest's global sample (~630 stocks,
2005→today, prices cached), plus ablations — no volatility targeting, no drawdown control,
neither, no regime gate — and a signal-free control that buys random stocks at the same
rate. Reports:
  * performance, trade statistics and yearly returns per variant;
  * the Deflated Sharpe Ratio of the live rules given every variant tried here and in the
    stock-level backtest (Bailey & López de Prado, 2014);
  * an expectation for live results: post-publication decay of 26–58% of backtested
    returns (McLean & Pontiff, 2016);
  * live vs backtest: where the paper book's return since inception falls in the
    backtest's bootstrapped range for the same horizon, and its trade statistics against
    the backtest's.
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

from api.calculations import auto_backtest as ab

logger = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
RESULT_FILE = DATA / "auto_backtest.json"
_state = {"running": False, "started": None, "error": None, "stage": None}
DECAY = (0.26, 0.58)          # McLean & Pontiff (2016): out-of-sample / post-publication
VARIANTS = [
    ("live", "Live rules", {}),
    ("no_vol_target", "Without volatility targeting", {"vol_targeting": False}),
    ("no_drawdown_control", "Without drawdown control", {"drawdown_control": False}),
    ("no_overlays", "Without either overlay", {"vol_targeting": False, "drawdown_control": False}),
    ("no_regime_gate", "Without the regime gate", {"regime_gate": False}),
    ("alltime_peak", "Drawdown from the all-time peak", {"peak_window": None}),
    ("drawdown_25", "25% drawdown limit", {"max_drawdown": 0.25}),
    ("control", "Control: random stocks, same rules", {"random_entries": True}),
]


def build_panel():
    """Calendar-aligned arrays for the stock backtest's sample (cached prices)."""
    import pandas as pd
    from api import global_universe as gu
    from api import stock_backtest as sb
    from api.calculations.stock_backtest import clean_ohlc
    from api.calculations.stock_timing import signal_frame

    names = sb.sample(gu.load(rebuild_if_stale=False))
    meta = {s["symbol"]: s for s in names}
    benches = sorted({s.get("benchmark") for s in names if s.get("benchmark")})
    px = sb._prices(sorted(meta) + benches + ["^VIX"])
    vix = px["^VIX"]["Close"] if "^VIX" in px else None
    cols: Dict[str, Dict[str, Any]] = {}
    for sym, m in meta.items():
        df = px.get(sym)
        if df is None:
            continue
        o, h, l, c = clean_ohlc(*(df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close")))
        with np.errstate(divide="ignore", invalid="ignore"):
            f = signal_frame(c, h, l)
        bench = px.get(m.get("benchmark"))
        reg = sb._regime(df.index, bench["Close"] if bench is not None else None, vix)
        cols[sym] = {"idx": df.index, "o": o, "h": h, "l": l, "c": c, "setup": f["setup"].to_numpy(),
                     "timing": f["timing"].to_numpy(), "atr": f["atr"].to_numpy(), "regime": reg}
    syms = sorted(cols)
    cal = sorted(set().union(*(set(cols[s]["idx"]) for s in syms)))
    cal_index = pd.DatetimeIndex(cal)

    def mat(key):
        out = np.full((len(cal), len(syms)), np.nan, dtype=float)
        for j, s in enumerate(syms):
            ser = pd.Series(cols[s][key], index=cols[s]["idx"])
            out[:, j] = ser.reindex(cal_index).to_numpy(dtype=float)
        return out
    panel = ab.Panel(
        dates=[d.strftime("%Y-%m-%d") for d in cal], symbols=syms,
        open=mat("o"), high=mat("h"), low=mat("l"), close=mat("c"), setup=mat("setup"),
        timing=mat("timing"), atr=mat("atr"), regime=mat("regime"),
        market_class=[meta[s].get("market_class") or "Developed" for s in syms],
        sector=[meta[s].get("sector") or "Unknown" for s in syms],
        country=[meta[s].get("country") or "" for s in syms])
    return panel


def _rules_from_settings(s: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("risk_per_trade", "max_position", "max_gross", "max_positions", "max_per_sector", "max_drawdown",
            "vol_target", "target_r", "max_hold", "exclude_frontier")
    out = {k: s[k] for k in keys if k in s}
    out["peak_window"] = int(s.get("peak_days") or 0) or None
    return out


def run() -> Dict[str, Any]:
    from api import auto_trader, stock_backtest as sb
    t0 = time.time()
    _state["stage"] = "loading prices"
    panel = build_panel()
    settings = auto_trader.get_settings()
    base = _rules_from_settings(settings)
    results: Dict[str, Dict[str, Any]] = {}
    live_rate = 0.5
    for key, label, override in VARIANTS:
        _state["stage"] = f"simulating: {label}"
        rules = ab.Rules(**{**base, **override, **({"random_rate": live_rate} if key == "control" else {})})
        out = ab.run(panel, rules)
        if key == "live":
            live_rate = out["orders_per_day"]
        results[key] = {"label": label, "out": out}

    _state["stage"] = "statistics"
    first = results["live"]["out"]["dates"]
    yrs = (datetime.fromisoformat(first[-1]) - datetime.fromisoformat(first[0])).days / 365.25
    variants, curves, trial_sharpes = [], {}, []
    for key, v in results.items():
        o = v["out"]
        pf = ab.perf(o["equity"], o["dates"])
        ts = ab.trade_stats(o["trades"], pf["periods_per_year"], yrs)
        r = np.diff(o["equity"]) / o["equity"][:-1]
        if r.std() > 0:
            trial_sharpes.append(float(r.mean() / r.std(ddof=1)))
        variants.append({"key": key, "label": v["label"], "performance": pf, "trades": ts,
                         "avg_gross": round(float(o["gross"].mean()), 3), "avg_positions": round(float(o["positions"].mean()), 1),
                         "avg_risk_scale": round(float(o["scale"].mean()), 3)})
        curves[key] = o["equity"] / o["equity"][0]
    # Trials from the stock-level backtest count too (the search spans both).
    try:
        sbres = sb.latest() or {}
        per = 252.0
        for vv in (sbres.get("variants") or {}).values():
            s_ann = (vv.get("portfolio") or {}).get("sharpe")
            if s_ann is not None:
                trial_sharpes.append(s_ann / math.sqrt(per))
    except Exception:
        pass
    live = results["live"]["out"]
    live_r = np.diff(live["equity"]) / live["equity"][:-1]
    dsr = ab.deflated_sharpe(live_r, trial_sharpes)
    lp = next(v for v in variants if v["key"] == "live")["performance"]
    expectation = {"cagr_range": [round(lp["cagr"] * (1 - DECAY[1]), 4), round(lp["cagr"] * (1 - DECAY[0]), 4)],
                   "sharpe_range": [round(lp["sharpe"] * (1 - DECAY[1]), 3), round(lp["sharpe"] * (1 - DECAY[0]), 3)]
                   if lp.get("sharpe") else None,
                   "basis": "McLean & Pontiff (2016): returns 26% lower out of sample, 58% lower after publication"}
    step = 5
    dates = live["dates"]
    curve = [{"date": dates[k], **{key: round(float(c[k]), 4) for key, c in curves.items()}}
             for k in range(0, len(dates), step)]
    out = {"available": True, "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
           "build_seconds": round(time.time() - t0, 1),
           "sample": {"stocks": len(panel.symbols), "start": dates[0], "end": dates[-1], "years": round(yrs, 1)},
           "rules": base, "variants": variants, "deflated_sharpe": dsr, "expectation": expectation,
           "curve": curve, "live_daily_returns": [round(float(x), 6) for x in live_r[-2520:]],
           "live_trade_r": [round(float(t["r"]), 4) for t in live["trades"]][-5000:]}
    out["findings"] = findings(out)
    DATA.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(out))
    logger.info("[auto-backtest] done in %.0fs", time.time() - t0)
    return out


def findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    v = {x["key"]: x for x in r["variants"]}
    out: List[Dict[str, str]] = []
    L, C = v["live"], v["control"]

    def s(x):
        return x["performance"].get("sharpe")
    if s(L) is not None and s(C) is not None:
        gap = s(L) - s(C)
        verdict = ("stock selection adds value on top of the risk rules." if gap > 0.1 else
                   "stock selection does worse than random — the edge is in the risk rules." if gap < -0.1 else
                   "about the same: most of the edge comes from the risk rules (stops, regime gate, sizing), "
                   "not from which stocks are picked.")
        out.append({"tone": "good" if gap > 0.1 else "bad" if gap < -0.1 else "neutral", "title": "Signal vs random stocks",
                    "text": f"Live rules Sharpe {s(L):.2f} ({L['performance']['cagr']:+.1%} a year) vs {s(C):.2f} "
                            f"({C['performance']['cagr']:+.1%}) for random stocks under the same rules — {verdict}"})
    for key, what in (("no_vol_target", "Volatility targeting"), ("no_drawdown_control", "Drawdown control"),
                      ("no_regime_gate", "The regime gate"), ("alltime_peak", "Rolling-peak drawdown control")):
        if key in v and s(v[key]) is not None and s(L) is not None:
            dd_l, dd_x = L["performance"]["max_drawdown"], v[key]["performance"]["max_drawdown"]
            better = s(L) >= s(v[key]) and dd_l >= dd_x
            worse = s(L) < s(v[key]) and dd_l < dd_x
            out.append({"tone": "good" if better else "bad" if worse else "neutral", "title": what,
                        "text": f"With it: Sharpe {s(L):.2f}, max drawdown {dd_l:.0%}. Without: Sharpe {s(v[key]):.2f}, "
                                f"max drawdown {dd_x:.0%}."})
    d = r.get("deflated_sharpe") or {}
    if d.get("dsr") is not None:
        out.append({"tone": "good" if d["dsr"] >= 0.95 else "neutral" if d["dsr"] >= 0.5 else "bad",
                    "title": "Deflated Sharpe ratio",
                    "text": f"Probability the live rules' true Sharpe beats the best of {d['trials']} trials by luck: "
                            f"{d['dsr']:.0%} (≥ 95% is significant after the search; vs zero: {d['psr_vs_zero']:.0%})."})
    e = r.get("expectation") or {}
    if e.get("cagr_range"):
        lo, hi = e["cagr_range"]
        out.append({"tone": "neutral", "title": "What to expect live",
                    "text": f"Backtests overstate live results: plan for roughly {lo:+.1%} to {hi:+.1%} a year, not the "
                            f"backtest's {L['performance']['cagr']:+.1%} ({e['basis']})."})
    return out


def latest() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(RESULT_FILE.read_text())
    except Exception:
        return None


def live_vs_backtest(bt: Dict[str, Any], live: Dict[str, Any]) -> Dict[str, Any]:
    """Where the paper book stands relative to what the backtest says is normal."""
    nav = live.get("nav") or []
    days = max(0, len(nav) - 1)
    cap = (live.get("settings") or {}).get("capital") or 1
    live_ret = live["equity"] / cap - 1 if live.get("equity") else None
    rng = ab.bootstrap_range(np.array(bt.get("live_daily_returns") or []), days) if days >= 5 else {}
    pctile = None
    if rng and live_ret is not None:
        qs = [(5, rng["p5"]), (25, rng["p25"]), (50, rng["p50"]), (75, rng["p75"]), (95, rng["p95"])]
        pctile = "below the 5th percentile" if live_ret < qs[0][1] else "above the 95th percentile" if live_ret > qs[-1][1] \
            else next(f"between the {a}th and {b}th percentiles" for (a, x), (b, y) in zip(qs, qs[1:]) if x <= live_ret <= y)
    bt_r = np.array(bt.get("live_trade_r") or [])
    closed = [p["r_multiple"] for p in live.get("closed") or [] if p.get("r_multiple") is not None]
    trade_cmp = None
    if bt_r.size > 30:
        mu, sd = float(bt_r.mean()), float(bt_r.std(ddof=1))
        trade_cmp = {"backtest_avg_r": round(mu, 3), "backtest_hit_rate": round(float((bt_r > 0).mean()), 3),
                     "live_trades": len(closed), "live_avg_r": round(float(np.mean(closed)), 3) if closed else None,
                     "live_hit_rate": round(float(np.mean([x > 0 for x in closed])), 3) if closed else None,
                     "z": round((float(np.mean(closed)) - mu) / (sd / math.sqrt(len(closed))), 2) if len(closed) >= 5 else None}
    status = "too early" if days < 5 else ("in line" if pctile and "between" in pctile else "outside the normal range")
    return {"days": days, "live_return": round(live_ret, 4) if live_ret is not None else None,
            "backtest_range": rng, "where": pctile, "status": status, "trades": trade_cmp}


async def run_in_background() -> None:
    if _state["running"]:
        return
    _state.update(running=True, started=time.time(), error=None, stage="starting")
    try:
        await asyncio.to_thread(run)
    except Exception as e:
        logger.error("[auto-backtest] failed: %s", e, exc_info=True)
        _state["error"] = str(e)[:200]
    finally:
        _state.update(running=False, stage=None)


def status() -> Dict[str, Any]:
    return {"running": _state["running"], "stage": _state["stage"], "error": _state["error"],
            "running_for_s": round(time.time() - _state["started"]) if _state["running"] else None}
