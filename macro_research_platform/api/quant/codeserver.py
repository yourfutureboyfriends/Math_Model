"""
Server side of the Code Lab: market data for strategies (also shipped to the browser), trusted runs
of the built-in strategy library, and analysis (deep report + Monte Carlo) of any return series.
User-written code is never executed here — the browser runs it in Pyodide, and deployment runs it in
api/quant/sandbox.py.
"""
from __future__ import annotations

import base64
import re
import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from api.quant import codelab
from api.quant import data as qdata

WARMUP_DAYS = 800                    # history before START so 1–3-year lookbacks are ready


def _index_series(sym: str, start: str) -> Optional[pd.Series]:
    pan, _ = qdata.panel([sym], start=start)
    return pan["close"][sym] if pan and sym in pan["close"] else None


_FOREIGN = re.compile(r"\.[A-Z]{1,3}$")                 # Yahoo exchange suffix: VOD.L, 7203.T, SHOP.TO
ADJUSTMENT = "Yahoo Finance daily bars, auto_adjust=True (splits and dividends folded into prices: total return)"


def check_tradable(symbols: Sequence[str]) -> None:
    """The Code Lab account is in USD and models US-listed instruments only. Refuse what it cannot account
    for correctly, instead of mixing currencies or 'trading' an index."""
    idx = [s for s in symbols if s.startswith("^")]
    if idx:
        raise ValueError(f"{', '.join(idx[:5])} {'is an index' if len(idx) == 1 else 'are indices'} — not tradable. "
                         "Use data.vix for the VIX, or an ETF that tracks the index.")
    fx = [s for s in symbols if "=" in s]
    if fx:
        raise ValueError(f"{', '.join(fx[:5])}: FX and futures quotes are not tradable in the Code Lab (no contract, "
                         "margin or currency accounting yet).")
    foreign = [s for s in symbols if _FOREIGN.search(s)]
    if foreign:
        raise ValueError(f"{', '.join(foreign[:5])}: non-US listings trade in other currencies (and GBp in pence). The "
                         "Code Lab account is USD-only until FX conversion is supported — use the US-listed ADR or ETF.")


TRADABLE_UNIVERSES = {"US": "US-listed, USD-quoted stocks in the platform's tradable universe (Markets screener)"}


def tradable_universe(name: str) -> List[str]:
    """Symbols of a named tradable universe, most traded first. Today's list: using it for history is
    retrospective (survivor-selected) and every result says so."""
    from api import global_universe
    name = (name or "").upper()
    if name not in TRADABLE_UNIVERSES:
        raise ValueError(f"TRADABLE_UNIVERSE must be one of: {', '.join(TRADABLE_UNIVERSES)} (the Code Lab account is USD-only).")
    u = global_universe.load(rebuild_if_stale=False)
    rows = [r for r in u.get("stocks", []) if r.get("country") == "US" and r.get("currency") == "USD"
            and (r.get("asset_type") or "Equity") == "Equity"]
    rows.sort(key=lambda r: -(r.get("traded_usd") or 0))
    syms = [str(r["symbol"]).upper().replace(".", "-").replace("/", "-") for r in rows]
    syms = [x for x in dict.fromkeys(syms) if not _FOREIGN.search(x)]
    if not syms:
        raise ValueError("The tradable universe is not available yet — open Markets → EQS once to build it.")
    return syms[:codelab.LARGE_UNIVERSE_LIMIT]


def load_data(universe: Sequence[str], start: str, end: Optional[str] = None,
              limit: Optional[int] = qdata.MAX_SYMBOLS, allow_missing: bool = False) -> codelab.Data:
    """Raw daily observations for a strategy: `observed` marks real bars; `close` is the last observed close
    carried forward inside each listing's history (a valuation mark); `open` keeps only observed opens."""
    from api.quant import rates
    syms, bad = qdata.clean_symbols(universe)
    if bad:
        raise ValueError(f"Invalid ticker(s): {', '.join(bad[:5])}")
    if not syms or (limit is not None and len(syms) > limit):
        raise ValueError(f"UNIVERSE needs 1–{limit} tickers (the current capability limit).")
    check_tradable(syms)
    warm = (pd.Timestamp(start) - pd.Timedelta(days=int(WARMUP_DAYS * 1.45))).strftime("%Y-%m-%d")
    pan, missing = qdata.panel(syms, start=warm, end=end, fill=False)
    stale = list(getattr(qdata.LAST_REPORT, "stale", []) or [])
    if not pan:
        raise ValueError("No price data could be loaded for this UNIVERSE.")
    if missing and not allow_missing:
        raise ValueError(f"No price data for: {', '.join(missing[:8])} — nothing is dropped silently; remove them "
                         "or try again.")
    cols = [s for s in syms if s in pan["close"].columns]
    raw = pan["close"][cols]
    observed = raw.notna()
    # carry the last observed close forward, but only inside each listing's own history
    marks = raw.ffill()
    for c in cols:
        last = raw[c].last_valid_index()
        if last is not None:
            marks.loc[marks.index > last, c] = np.nan
    idx = raw.index
    rf = rates.daily(idx) if rates.known() else None
    vix = _index_series("^VIX", warm)
    prov = {"adjustment": ADJUSTMENT, "stale_symbols": stale, "account_currency": "USD",
            "dropped_no_data": sorted(missing) if allow_missing else [],
            "universe_selection": "user-specified list (if chosen from today's market, results are retrospective / "
                                  "survivor-selected — names that failed or were delisted earlier are absent)",
            "first_observation": {c: str(raw[c].first_valid_index().date()) for c in cols if raw[c].first_valid_index() is not None}}
    return codelab.Data(marks, pan["open"][cols], pan["high"][cols].ffill(), pan["low"][cols].ffill(),
                        pan["volume"][cols], rf=rf, vix=vix, observed=observed, rf_known=rf is not None, provenance=prov)


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode()


def data_payload(universe: Sequence[str], start: str, benchmark: str = "SPY") -> Dict[str, Any]:
    """Compact data for the browser: float32 arrays (base64), row-major dates × tickers, plus the observed
    mask, whether the reference rate is known and the data provenance."""
    d = load_data(universe, start)
    bm = _index_series(benchmark, d.close.index[0].strftime("%Y-%m-%d"))
    out = {"dates": [x.strftime("%Y-%m-%d") for x in d.close.index], "tickers": d.tickers,
           "rf": _b64(d.rf.to_numpy()), "vix": _b64(d.vix.to_numpy()), "rf_known": d.rf_known,
           "observed": base64.b64encode(np.ascontiguousarray(d.observed.to_numpy(), dtype=np.uint8).tobytes()).decode(),
           "benchmark": _b64(bm.reindex(d.close.index).to_numpy()) if bm is not None else None, "benchmark_symbol": benchmark,
           "provenance": d.provenance, "engine_version": codelab.ENGINE_VERSION}
    for f in ("close", "open", "high", "low", "volume"):
        out[f] = _b64(getattr(d, f).to_numpy())
    return out


def evaluate_code(code: str, costs: Optional[Dict[str, float]] = None, trusted: bool = False) -> Dict[str, Any]:
    """Run TRUSTED code (the built-in library) in-process. Refuses anything else."""
    if not trusted:
        raise PermissionError("User code is not executed on the server — it runs in your browser or the deploy sandbox.")
    st = codelab.load_strategy(code)
    d = load_data(st["universe"], st["start"])
    bm = _index_series(st["benchmark"], d.close.index[0].strftime("%Y-%m-%d"))
    return codelab.evaluate(st["strategy"], d, st["params"], st["start"], costs, bm, st["holdout"], st["code_hash"])


def rf_for(dates: Sequence[str]) -> pd.Series:
    """The platform reference rate (api/quant/rates.py) for these dates — one source for every surface."""
    from api.quant import rates
    return rates.daily(dates)


def analyze(dates: List[str], returns: List[float], benchmark: Optional[List[float]] = None, label: str = "Strategy",
            benchmark_label: str = "SPY", mc_years: float = 10.0, mc_paths: int = 2000, max_leverage: float = 2.0,
            dd_limit: float = 0.5, owner: Optional[str] = None, provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deep report + Monte Carlo for a daily return series (numbers only — no code)."""
    from api.quant import deep
    if len(dates) != len(returns) or len(returns) < 250:
        raise ValueError("Need matching dates and at least 250 daily returns.")
    if any((not math.isfinite(x)) or x < -1 or x > 5 for x in returns):
        raise ValueError("Returns must be finite daily fractions (−1 to 5).")
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    ret = pd.Series(returns, index=idx, dtype=float)
    rf = rf_for(dates)
    rep = deep.report([d for d in dates], list(returns), codelab.TRADING_DAYS,
                      benchmark if benchmark and len(benchmark) == len(returns) else None,
                      label=label, benchmark_label=benchmark_label)
    mc = codelab.monte_carlo(ret, rf, years=mc_years, paths=mc_paths, max_leverage=max_leverage, dd_limit=dd_limit)
    registry = None
    if owner and provenance:
        from api.quant import robust, store
        reg = store.register_code_run(owner, label or "Strategy", provenance, codelab.metrics(ret, rf))
        ex = ret.to_numpy() - rf.to_numpy()
        n = max(reg["distinct_trials"], 1)
        dsr = robust.deflated_sharpe(ex, n, [s / math.sqrt(252) for s in reg["trial_sharpes"]] if len(reg["trial_sharpes"]) >= 2 else None)
        reg["deflated_sharpe"] = dsr.get("dsr")
        reg.pop("trial_sharpes", None)
        hold = provenance.get("holdout")
        reg["record_label"] = (provenance.get("record_type") or "") + (
            "" if not hold else (" · holdout from " + hold + (" (first look — untouched)" if reg["holdout_views"] <= 1
                                                             else f" (viewed {reg['holdout_views']} times — no longer untouched)")))
        registry = reg
    try:
        lens = factor_lens(dates, list(returns))
    except Exception:                                          # noqa: BLE001 — analysis works without it
        lens = None
    return {"deep": rep, "monte_carlo": mc, "metrics": codelab.metrics(ret, rf), "factor_lens": lens, "registry": registry}


# ── Factor lens (Two Sigma-style) ───────────────────────────────────────────
# ETF proxies for the Two Sigma Factor Lens: core macro (equity, rates, credit, commodities),
# secondary macro (emerging markets, dollar, inflation) and equity styles (long-short vs the market).
FACTORS: Dict[str, Any] = {
    "Equity": ("SPY", None), "Interest rates": ("IEF", None), "Credit": ("HYG", "IEF"), "Commodities": ("DBC", None),
    "Emerging markets": ("EEM", "SPY"), "US dollar": ("UUP", None), "Inflation": ("TIP", "IEF"),
    "Momentum": ("MTUM", "SPY"), "Value": ("VLUE", "SPY"), "Quality": ("QUAL", "SPY"), "Low risk": ("USMV", "SPY"),
    "Small cap": ("IWM", "SPY"),
}


def factor_lens(dates: List[str], returns: List[float]) -> Optional[Dict[str, Any]]:
    """Weekly regression of excess returns on factor proxies: exposures, t-stats, how much of the return each
    factor explains, and the alpha left over. (Two Sigma's lens orthogonalises factors; with ETF proxies we
    keep them raw and report their correlation-adjusted fit, R².)"""
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    syms = sorted({s for a, b in FACTORS.values() for s in (a, b) if s})
    pan, _ = qdata.panel(syms, start=(idx[0] - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    if not pan:
        return None
    px = pan["close"]
    rf = rf_for(dates)
    strat = (1 + pd.Series(returns, index=idx)).cumprod()
    wk = lambda s: s.resample("W-FRI").last().pct_change(fill_method=None)
    y = wk(strat) - rf.resample("W-FRI").sum()
    X = {}
    for name, (a, b) in FACTORS.items():
        if a not in px:
            continue
        fa = wk(px[a].reindex(idx).ffill())
        X[name] = fa - (wk(px[b].reindex(idx).ffill()) if b and b in px else rf.resample("W-FRI").sum())
    X = pd.DataFrame(X)
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(df) < 104:
        return None
    Y, F = df["y"].to_numpy(), df.drop(columns="y")
    A = np.column_stack([np.ones(len(F)), F.to_numpy()])
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = Y - A @ coef
    n, k = A.shape
    s2 = resid @ resid / (n - k)
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    r2 = 1 - (resid @ resid) / (((Y - Y.mean()) ** 2).sum())
    means = F.mean().to_numpy()
    rows = [{"factor": f, "beta": round(float(coef[i + 1]), 3), "t": round(float(coef[i + 1] / se[i + 1]), 2),
             "contribution": round(float(coef[i + 1] * means[i] * 52), 4)} for i, f in enumerate(F.columns)]
    return {"start": str(df.index[0].date()), "end": str(df.index[-1].date()), "weeks": int(n), "r2": round(float(r2), 3),
            "alpha": round(float(coef[0] * 52), 4), "alpha_t": round(float(coef[0] / se[0]), 2),
            "factors": sorted(rows, key=lambda r: -abs(r["t"])),
            "note": "Weekly excess returns regressed on ETF factor proxies (Two Sigma Factor Lens categories). Alpha is the "
                    "annual return the factors do not explain; |t| above 2 is statistically meaningful. Style factors are "
                    "ETF minus SPY; proxies start 2013 (MTUM, VLUE, QUAL, USMV), so the fit covers that window."}
