"""
Server side of the Code Lab: market data for strategies (also shipped to the browser), trusted runs
of the built-in strategy library, and analysis (deep report + Monte Carlo) of any return series.
User-written code is never executed here — the browser runs it in Pyodide, and deployment runs it in
api/quant/sandbox.py.
"""
from __future__ import annotations

import base64
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


def load_data(universe: Sequence[str], start: str, end: Optional[str] = None) -> codelab.Data:
    syms, bad = qdata.clean_symbols(universe)
    if bad:
        raise ValueError(f"Invalid ticker(s): {', '.join(bad[:5])}")
    if not syms or len(syms) > qdata.MAX_SYMBOLS:
        raise ValueError(f"UNIVERSE needs 1–{qdata.MAX_SYMBOLS} tickers.")
    warm = (pd.Timestamp(start) - pd.Timedelta(days=int(WARMUP_DAYS * 1.45))).strftime("%Y-%m-%d")
    pan, missing = qdata.panel(syms, start=warm, end=end)
    if not pan:
        raise ValueError("No price data could be loaded for this UNIVERSE.")
    if missing:
        raise ValueError(f"No price data for: {', '.join(missing[:8])}")
    irx = _index_series("^IRX", warm)
    rf = (irx / 100 / codelab.TRADING_DAYS) if irx is not None else None          # 13-week bill, daily
    vix = _index_series("^VIX", warm)
    cols = [s for s in syms if s in pan["close"].columns]
    return codelab.Data(pan["close"][cols], pan["open"][cols], pan["high"][cols], pan["low"][cols],
                        pan["volume"][cols], rf=rf, vix=vix)


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode()


def data_payload(universe: Sequence[str], start: str, benchmark: str = "SPY") -> Dict[str, Any]:
    """Compact data for the browser: float32 arrays (base64), row-major dates × tickers."""
    d = load_data(universe, start)
    bm = _index_series(benchmark, d.close.index[0].strftime("%Y-%m-%d"))
    out = {"dates": [x.strftime("%Y-%m-%d") for x in d.close.index], "tickers": d.tickers,
           "rf": _b64(d.rf.to_numpy()), "vix": _b64(d.vix.to_numpy()),
           "benchmark": _b64(bm.reindex(d.close.index).to_numpy()) if bm is not None else None, "benchmark_symbol": benchmark}
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
    return codelab.evaluate(st["strategy"], d, st["params"], st["start"], costs, bm)


def rf_for(dates: Sequence[str]) -> pd.Series:
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    irx = _index_series("^IRX", (idx[0] - pd.Timedelta(days=30)).strftime("%Y-%m-%d"))
    if irx is None:
        return pd.Series(0.0, index=idx)
    return (irx / 100 / codelab.TRADING_DAYS).reindex(idx, method="ffill").fillna(0.0)


def analyze(dates: List[str], returns: List[float], benchmark: Optional[List[float]] = None, label: str = "Strategy",
            benchmark_label: str = "SPY", mc_years: float = 10.0, mc_paths: int = 2000, max_leverage: float = 2.0,
            dd_limit: float = 0.5) -> Dict[str, Any]:
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
    try:
        lens = factor_lens(dates, list(returns))
    except Exception:                                          # noqa: BLE001 — analysis works without it
        lens = None
    return {"deep": rep, "monte_carlo": mc, "metrics": codelab.metrics(ret, rf), "factor_lens": lens}


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
