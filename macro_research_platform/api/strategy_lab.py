"""
Strategy Lab — research-backed systematic models backtested on the same footing, combined,
and shown with today's positions (engine: api/calculations/strategies.py).

Models
  * Trend (long/short) and Trend (long-only) on 13 cross-asset ETFs — Hurst, Ooi & Pedersen
    (2017); Moskowitz, Ooi & Pedersen (2012).
  * Sector momentum (top 3 SPDR sectors, with and without a market trend filter) —
    Moskowitz & Grinblatt (1999).
  * Low volatility (least volatile 20% of the global stock sample) — Ang et al. (2006);
    Frazzini & Pedersen (2014).
  * Residual momentum (top 30 of the global sample) — Blitz, Huij & Martens (2011).
  * Auto book — the live auto-trader's rules (api/calculations/auto_backtest.py).
Then an equal-risk-contribution mix of the five primary streams, walk-forward.

Every variant counts as a trial in the Deflated Sharpe Ratio (with the stock- and
auto-backtest trials). Costs: 5 bp per side for ETFs, half the class round-trip for stocks.
Stock returns are local-currency (hedged); the sample is today's large caps (survivorship).
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
from api.calculations import strategies as sg

logger = logging.getLogger(__name__)
DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
RESULT_FILE = DATA / "strategy_lab.json"
ETF_CACHE = DATA / "backtest" / "etf_prices.pkl"
_state = {"running": False, "started": None, "error": None, "stage": None}

TREND_ETFS = {"SPY": "US equities", "QQQ": "Nasdaq 100", "IWM": "US small caps", "EFA": "Developed ex-US",
              "EEM": "Emerging markets", "IEF": "7-10y Treasuries", "TLT": "20y+ Treasuries", "TIP": "TIPS",
              "LQD": "Investment-grade credit", "GLD": "Gold", "DBC": "Commodities", "UUP": "US dollar",
              "VNQ": "US real estate"}
SECTOR_ETFS = {"XLB": "Materials", "XLE": "Energy", "XLF": "Financials", "XLI": "Industrials",
               "XLK": "Technology", "XLP": "Staples", "XLU": "Utilities", "XLV": "Health care",
               "XLY": "Discretionary", "XLRE": "Real estate", "XLC": "Communication"}
ETF_COST_BPS = 5.0
PRIMARY = ("trend", "sector_momentum", "low_vol", "residual_momentum", "auto_book")
LABELS = {
    "trend": "Cross-asset trend (long/short)", "trend_long_only": "Cross-asset trend (long-only)",
    "sector_momentum": "Sector momentum (with market filter)", "sector_momentum_raw": "Sector momentum (no filter)",
    "low_vol": "Low volatility", "residual_momentum": "Residual momentum", "auto_book": "Auto book (live rules)",
    "combined": "Combined — equal risk contribution",
}
CITES = {
    "trend": "Hurst, Ooi & Pedersen (2017); Moskowitz, Ooi & Pedersen (2012)",
    "sector_momentum": "Moskowitz & Grinblatt (1999); Faber (2007) filter",
    "low_vol": "Ang, Hodrick, Xing & Zhang (2006); Frazzini & Pedersen (2014)",
    "residual_momentum": "Blitz, Huij & Martens (2011)",
    "auto_book": "This platform's entry model + risk rules",
    "combined": "Maillard, Roncalli & Teiletche (2010)",
}


def _etf_prices():
    import pandas as pd
    import yfinance as yf
    try:
        if time.time() - ETF_CACHE.stat().st_mtime < 7 * 86400:
            return pd.read_pickle(ETF_CACHE)
    except Exception:
        pass
    syms = sorted(set(TREND_ETFS) | set(SECTOR_ETFS))
    df = yf.download(syms, period="max", interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False)
    closes = pd.DataFrame({s: df[s]["Close"] for s in syms if s in df.columns.get_level_values(0)})
    ETF_CACHE.parent.mkdir(parents=True, exist_ok=True)
    closes.to_pickle(ETF_CACHE)
    return closes


def _panel_from(df, cols):
    sub = df[[c for c in cols if c in df.columns]].dropna(how="all")
    sub = sub[sub.index >= "2004-01-01"]
    return [d.strftime("%Y-%m-%d") for d in sub.index], list(sub.columns), sub.ffill().to_numpy(dtype=float)


def _stock_monthly(panel: ab.Panel, bench_closes: Dict[str, Any], meta: Dict[str, Dict]) -> Dict[str, Any]:
    """Month-end closes of the stocks and of each stock's home index (for residual momentum)."""
    import pandas as pd
    dates = pd.DatetimeIndex(panel.dates)
    close = pd.DataFrame(panel.close, index=dates, columns=panel.symbols).ffill()
    ends = sg.month_ends(panel.dates)
    px_m = close.iloc[ends].to_numpy(dtype=float)
    idx_cols = []
    for s in panel.symbols:
        b = bench_closes.get((meta.get(s) or {}).get("benchmark"))
        idx_cols.append(b.reindex(dates, method="ffill").iloc[ends].to_numpy(dtype=float) if b is not None
                        else np.full(len(ends), np.nan))
    return {"ends": ends, "px_m": px_m, "idx_m": np.column_stack(idx_cols)}


def _stats(name: str, res: Dict[str, Any]) -> Dict[str, Any]:
    eq = np.concatenate([[1.0], res["equity"]])
    dates = [res["dates"][0]] + list(res["dates"])
    pf = ab.perf(eq, dates)
    return {"key": name, "label": LABELS.get(name, name), "citation": CITES.get(name.split("_raw")[0].replace("_long_only", ""), ""),
            "performance": pf, "turnover_annual": round(res["turnover"], 2) if res.get("turnover") else None}


def run() -> Dict[str, Any]:
    from api import auto_backtest as abs_, auto_trader, global_universe as gu, stock_backtest as sb
    t0 = time.time()
    results: Dict[str, Dict[str, Any]] = {}

    _state["stage"] = "ETF prices"
    etf = _etf_prices()
    d_t, cols_t, px_t = _panel_from(etf, list(TREND_ETFS))
    results["trend"] = sg.run_monthly(px_t, d_t, lambda t: sg.trend_weights(px_t, t), ETF_COST_BPS)
    results["trend_long_only"] = sg.run_monthly(px_t, d_t, lambda t: sg.trend_weights(px_t, t, long_only=True), ETF_COST_BPS)
    d_s, cols_s, px_s = _panel_from(etf, list(SECTOR_ETFS) + ["SPY"])
    mcol = cols_s.index("SPY")
    results["sector_momentum"] = sg.run_monthly(px_s, d_s, lambda t: sg.sector_momentum_weights(px_s, t, 3, mcol), ETF_COST_BPS)
    results["sector_momentum_raw"] = sg.run_monthly(
        px_s, d_s, lambda t: sg.sector_momentum_weights(px_s, t, 3, None) * np.array([c != "SPY" for c in cols_s]), ETF_COST_BPS)

    _state["stage"] = "stock sample"
    panel = abs_.build_panel()
    names = sb.sample(gu.load(rebuild_if_stale=False))
    meta = {s["symbol"]: s for s in names}
    px = sb._prices(sorted({s.get("benchmark") for s in names if s.get("benchmark")}))
    bench = {k: v["Close"] for k, v in px.items()}
    close = np.where(np.isfinite(panel.close), panel.close, np.nan)
    import pandas as pd
    close_ff = pd.DataFrame(close).ffill().to_numpy()
    stock_cost = np.array([ab.COST_BY_CLASS.get(c, 0.0025) / 2 * 1e4 for c in panel.market_class])
    # Frontier / standalone listings look "low volatility" because they barely trade; the
    # evidence is on liquid markets, so both stock models use developed + emerging only.
    liquid = np.array([c in ("Developed", "Emerging") for c in panel.market_class])
    close_liq = np.where(liquid, close_ff, np.nan)
    results["low_vol"] = sg.run_monthly(close_ff, panel.dates, lambda t: sg.low_vol_weights(close_liq, t), stock_cost)
    mon = _stock_monthly(panel, bench, meta)
    pos = {e: k for k, e in enumerate(mon["ends"])}
    results["residual_momentum"] = sg.run_monthly(
        close_ff, panel.dates,
        lambda t: sg.top_equal(np.where(liquid, sg.residual_momentum_scores(mon["px_m"], mon["idx_m"], pos[t]), np.nan), 30)
        if t in pos else np.zeros(close.shape[1]),
        stock_cost, start=800)

    _state["stage"] = "auto book"
    rules = ab.Rules(**abs_._rules_from_settings(auto_trader.get_settings()))
    auto = ab.run(panel, rules)
    eq = auto["equity"]
    results["auto_book"] = {"dates": auto["dates"][1:], "returns": np.diff(eq) / eq[:-1],
                            "equity": eq[1:] / eq[0], "turnover": None, "last_weights": None}

    _state["stage"] = "combining"
    common = sorted(set.intersection(*(set(results[k]["dates"]) for k in PRIMARY)))
    aligned = {}
    for k in PRIMARY:
        m = dict(zip(results[k]["dates"], results[k]["returns"]))
        aligned[k] = np.array([m[d] for d in common])
    combo = sg.combine_erc(aligned)
    combo_dates = common[252:]
    results["combined"] = {"dates": combo_dates, "returns": combo["returns"],
                           "equity": np.cumprod(1 + combo["returns"]), "turnover": None, "last_weights": None}

    _state["stage"] = "statistics"
    strategies = [_stats(k, v) for k, v in results.items()]
    # Same-period comparison (the combination's window) for the primary streams.
    same = {}
    for k in list(PRIMARY) + ["combined"]:
        m = dict(zip(results[k]["dates"], results[k]["returns"]))
        r = np.array([m[d] for d in combo_dates])
        same[k] = ab.perf(np.concatenate([[1.0], np.cumprod(1 + r)]), [combo_dates[0]] + combo_dates)
    trials = []
    for k, v in results.items():
        r = v["returns"]
        if r.std() > 0:
            trials.append(float(r.mean() / r.std(ddof=1)))
    prior = abs_.latest() or {}
    for v in prior.get("variants") or []:
        s = (v.get("performance") or {}).get("sharpe")
        if s is not None:
            trials.append(s / math.sqrt(252))
    for s in strategies:
        s["deflated_sharpe"] = ab.deflated_sharpe(results[s["key"]]["returns"], trials).get("dsr")
    corr = sg.correlation({k: aligned[k][252:] for k in PRIMARY})

    curve, step = [], 5
    eqs = {k: np.cumprod(1 + np.array([dict(zip(results[k]["dates"], results[k]["returns"]))[d] for d in combo_dates]))
           for k in list(PRIMARY) + ["combined"]}
    for i in range(0, len(combo_dates), step):
        curve.append({"date": combo_dates[i], **{k: round(float(eqs[k][i]), 4) for k in eqs}})

    out = {"available": True, "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
           "build_seconds": round(time.time() - t0, 1), "strategies": strategies, "same_period": same,
           "window": {"start": combo_dates[0], "end": combo_dates[-1]}, "correlation": corr,
           "combined_weights": combo["weights"], "combined_avg_weights": combo["avg_weights"],
           "trials": len(trials), "curve": curve,
           "positions": current_positions(results, cols_t, cols_s, panel, meta),
           "labels": LABELS, "citations": CITES}
    out["findings"] = findings(out)
    DATA.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(out, default=float))
    logger.info("[strategy-lab] done in %.0fs", time.time() - t0)
    return out


def current_positions(results, cols_t, cols_s, panel, meta) -> Dict[str, List[Dict[str, Any]]]:
    """The latest rebalance's target weights, per model."""
    out: Dict[str, List[Dict[str, Any]]] = {}

    def rows(key, cols, names=None, top=15):
        lw = results[key].get("last_weights")
        if not lw:
            return []
        d, w = lw
        items = [(c, float(x)) for c, x in zip(cols, w) if abs(x) > 1e-6]
        items.sort(key=lambda kv: -abs(kv[1]))
        return [{"symbol": c, "name": (names or {}).get(c) or (meta.get(c) or {}).get("name"),
                 "weight": round(x, 4), "side": "Long" if x > 0 else "Short", "as_of": d,
                 "country": (meta.get(c) or {}).get("country")} for c, x in items[:top]]
    out["trend"] = rows("trend", cols_t, TREND_ETFS, 20)
    out["sector_momentum"] = rows("sector_momentum", cols_s, SECTOR_ETFS)
    out["low_vol"] = rows("low_vol", panel.symbols)
    out["residual_momentum"] = rows("residual_momentum", panel.symbols, top=30)
    return out


def findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    sp = r["same_period"]
    out = []
    best_single = max((k for k in PRIMARY), key=lambda k: sp[k].get("sharpe") or -9)
    c, b = sp["combined"], sp[best_single]
    out.append({"tone": "good" if (c.get("sharpe") or 0) > (b.get("sharpe") or 0) else "neutral",
                "title": "Diversification",
                "text": f"Combining the five streams by equal risk: Sharpe {c.get('sharpe')}, max drawdown {c['max_drawdown']:.0%} — "
                        f"vs the best single model ({LABELS[best_single]}) at Sharpe {b.get('sharpe')}, drawdown {b['max_drawdown']:.0%}."})
    corr = r["correlation"]
    pairs = [(a, bb, corr[a][bb]) for i, a in enumerate(PRIMARY) for bb in PRIMARY[i + 1:]]
    lo = min(pairs, key=lambda p: p[2])
    out.append({"tone": "good" if lo[2] < 0.3 else "neutral", "title": "Least correlated pair",
                "text": f"{LABELS[lo[0]]} and {LABELS[lo[1]]}: correlation {lo[2]:+.2f} — the pairing that does most for a combined book."})
    tr = sp.get("trend") or {}
    yrs = tr.get("years") or {}
    for y in ("2008", "2022"):
        if y in yrs:
            spy = None
            out.append({"tone": "good" if yrs[y] > 0 else "neutral", "title": f"Trend in {y}",
                        "text": f"Cross-asset trend returned {yrs[y]:+.1%} in {y} — the crisis-alpha property (Hurst et al. 2017)."})
            break
    for s in r["strategies"]:
        if s["key"] in PRIMARY and s.get("deflated_sharpe") is not None and s["deflated_sharpe"] < 0.5:
            out.append({"tone": "bad", "title": f"{s['label']}: not significant",
                        "text": f"Deflated Sharpe {s['deflated_sharpe']:.0%} after {r['trials']} trials — could be luck; size it small."})
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
        logger.error("[strategy-lab] failed: %s", e, exc_info=True)
        _state["error"] = str(e)[:200]
    finally:
        _state.update(running=False, stage=None)


def status() -> Dict[str, Any]:
    return {"running": _state["running"], "stage": _state["stage"], "error": _state["error"],
            "running_for_s": round(time.time() - _state["started"]) if _state["running"] else None}
