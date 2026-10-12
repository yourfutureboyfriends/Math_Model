"""
Code Lab engine — one file, numpy + pandas only, so the *same* code runs on the server and in the
browser (Pyodide). A strategy is plain Python:

    UNIVERSE = ["SPY", "TLT", "GLD"]          # tickers (≤ 80)
    START = "2005-01-01"                      # optional
    PARAMS = {"lookback": [126, 252]}         # optional: grid for walk-forward optimisation

    def strategy(data, lookback=252):
        # data.close / open / high / low / volume: DataFrames (dates × tickers), adjusted prices
        # data.rf: daily T-bill rate (Series); data.vix: VIX close (Series)
        # return target weights (dates × tickers): +long / −short, fraction of capital.
        # A row decided with data up to that day's close is traded at the next day's open.
        ...

Costs (all charged, all configurable — defaults are research-calibrated):
  commission     per side, bps of traded notional (default 0.35 bp ≈ $0.0035/share at $100)
  spread         half the bid-ask spread per asset and day from its volatility and dollar volume
                 (see half_spread_bps), never below half a cent
  market impact  square-root law calibrated on $1.7tn of live institutional trades (Frazzini,
                 Israel & Moskowitz 2018, US): 11.2 bp × √(% of 63-day dollar volume traded)
  SEC fee        0.278 bp on sales (Section 31 rate)
  borrow         annual fee on short notional (default 0.30% general collateral)
  financing      cash earns the T-bill rate; borrowing (gross long > 100%) pays T-bill + spread (default 1.0%)
Returns are total returns (Yahoo adjusted prices include dividends). Weights drift with prices
between trades; a no-trade band skips small rebalances.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

TRADING_DAYS = 252
DEFAULT_COSTS: Dict[str, float] = {
    "capital": 1_000_000.0,
    "commission_bps": 0.35,
    "spread_mult": 1.0,
    "impact_coef_bps": 11.21,
    "sec_fee_bps": 0.278,
    "borrow_fee": 0.003,
    "financing_spread": 0.010,
    "no_trade_band": 0.0025,
    "max_gross": 4.0,
}


class Data:
    """What a strategy sees. All frames share one date index; prices are split/dividend adjusted."""

    def __init__(self, close, open_, high, low, volume, rf=None, vix=None):
        self.close, self.open, self.high, self.low, self.volume = close, open_, high, low, volume
        idx = close.index
        self.rf = (rf.reindex(idx).ffill().fillna(0.0) if rf is not None else pd.Series(0.0, index=idx))
        self.vix = vix.reindex(idx).ffill() if vix is not None else pd.Series(np.nan, index=idx)
        self.tickers = list(close.columns)

    def returns(self) -> pd.DataFrame:
        return self.close.pct_change(fill_method=None)


# ── Helpers for strategy code ───────────────────────────────────────────────
def ewma_vol(close: pd.DataFrame, halflife: int = 42) -> pd.DataFrame:
    """Annualised exponentially weighted volatility of daily returns."""
    r = close.pct_change(fill_method=None)
    return r.ewm(halflife=halflife, min_periods=max(20, halflife)).std() * math.sqrt(TRADING_DAYS)


def momentum(close: pd.DataFrame, n: int, skip: int = 0) -> pd.DataFrame:
    return close.shift(skip) / close.shift(n) - 1


def hold_monthly(weights: pd.DataFrame) -> pd.DataFrame:
    """Keep each month-end's weights for the following month (trade once a month)."""
    return _hold(weights, "M")


def hold_weekly(weights: pd.DataFrame) -> pd.DataFrame:
    return _hold(weights, "W")


def _hold(weights: pd.DataFrame, freq: str) -> pd.DataFrame:
    w = weights.copy()
    s = w.index.to_series()
    last = (s.groupby(w.index.to_period(freq)).transform("max") == s).to_numpy()
    w.loc[~last] = np.nan
    return w.ffill()


def normalize_gross(weights: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
    g = weights.abs().sum(axis=1).replace(0, np.nan)
    return weights.div(g, axis=0).mul(gross).fillna(0.0)


def vol_target(weights: pd.DataFrame, close: pd.DataFrame, target: float = 0.10, lookback: int = 63,
               max_leverage: float = 2.0) -> pd.DataFrame:
    """Scale the whole book so its trailing realised volatility hits `target` (no look-ahead)."""
    r = close.pct_change(fill_method=None).fillna(0.0)
    port = (weights.shift(1).fillna(0.0) * r).sum(axis=1)
    vol = port.rolling(lookback, min_periods=max(20, lookback // 2)).std() * math.sqrt(TRADING_DAYS)
    scale = (target / vol).clip(upper=max_leverage).fillna(1.0)
    return weights.mul(scale, axis=0)


# ── Transaction-cost inputs ─────────────────────────────────────────────────
def half_spread_bps(close: pd.DataFrame, volume: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    """Half the bid-ask spread in bps from liquidity and volatility, lagged one day:
         max(half a cent, 25.5 × daily vol (bp) × dollar volume^−0.43)
    calibrated to typical US quoted spreads — ≈0.1 bp for SPY ($30bn/day), ≈2–3 bp for a $50m/day
    mid-cap, ≈15 bp for a $2m/day small cap; wider in volatile markets. (Range-based estimators such as
    Corwin–Schultz or Abdi–Ranaldo are swamped by volatility for liquid names — they put SPY near 10 bp.)
    Adjusted prices are below the traded price in early years, so the half-cent floor is conservative."""
    r = close.pct_change(fill_method=None)
    vol_bp = r.rolling(window, min_periods=20).std() * 1e4
    dv = (close * volume).rolling(window, min_periods=10).mean()
    model = 25.5 * vol_bp * dv.where(dv > 0) ** -0.43
    tick = 0.005 / close * 1e4
    hs = np.maximum(model, tick).shift(1)
    return hs.clip(lower=0.05, upper=100.0).fillna(5.0)


def dollar_volume(close: pd.DataFrame, volume: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    return (close * volume).rolling(window, min_periods=10).mean().shift(1)


# ── Backtest ────────────────────────────────────────────────────────────────
def backtest(weights: pd.DataFrame, data: Data, costs: Optional[Dict[str, float]] = None,
             start: Optional[str] = None) -> Dict[str, Any]:
    """Simulate target weights with full costs. Weights at row t trade at the open of t+1."""
    cfg = {**DEFAULT_COSTS, **(costs or {})}
    close, open_ = data.close, data.open.where(data.open > 0, data.close)
    w = weights.reindex(index=close.index, columns=close.columns).astype(float)
    w = w.where(close.notna(), 0.0).fillna(0.0)
    g = w.abs().sum(axis=1)
    w = w.mul((cfg["max_gross"] / g).clip(upper=1.0).fillna(1.0), axis=0)
    hs = half_spread_bps(close, data.volume).to_numpy() * cfg["spread_mult"] / 1e4
    adv = dollar_volume(close, data.volume).to_numpy()
    C, O, W = close.to_numpy(float), open_.to_numpy(float), w.to_numpy()
    rf = data.rf.to_numpy(float)
    T, N = C.shape
    first = 0
    if start:
        first = int(np.searchsorted(close.index.values, np.datetime64(pd.Timestamp(start))))
    first = max(first, 1)
    Wn = np.nan_to_num(W)
    new_decision = np.r_[True, np.any(np.abs(np.diff(Wn, axis=0)) > 1e-12, axis=1)]   # row t differs from t−1
    nav = 1.0
    hold = np.zeros(N)                     # current weights (fraction of NAV) after the last trade/drift
    out = {k: np.zeros(T) for k in ("ret", "gross", "commission", "spread", "impact", "fees", "borrow", "financing",
                                     "turnover", "long", "short")}
    band = cfg["no_trade_band"]
    for t in range(first, T):
        c0, o1, c1 = C[t - 1], O[t], C[t]
        ok0 = np.isfinite(c0) & np.isfinite(o1) & (c0 > 0)
        ovn = np.where(ok0, o1 / np.where(ok0, c0, 1) - 1, 0.0)
        ok1 = np.isfinite(c1) & np.isfinite(o1) & (o1 > 0)
        intr = np.where(ok1, c1 / np.where(ok1, o1, 1) - 1, 0.0)
        # overnight on the old book
        r_ovn = float(hold @ ovn)
        hold = hold * (1 + ovn) / (1 + r_ovn) if abs(1 + r_ovn) > 1e-12 else hold
        nav_open = nav * (1 + r_ovn)
        target = W[t - 1]                                      # decided at yesterday's close
        delta = target - hold
        # trade only on a new decision (or the first day); between decisions positions drift
        trade = (np.abs(delta) > band) & (new_decision[t - 1] or t == first)
        delta = np.where(trade & ok1, delta, 0.0)
        tv = np.abs(delta)
        comm = cfg["commission_bps"] / 1e4 * tv.sum()
        spr = float(np.nansum(tv * np.nan_to_num(hs[t], nan=5e-4)))
        dv = adv[t]
        frac = np.where(np.isfinite(dv) & (dv > 0), tv * nav_open * cfg["capital"] / np.where(np.isfinite(dv) & (dv > 0), dv, 1), 0.0)
        imp = float((tv * cfg["impact_coef_bps"] / 1e4 * np.sqrt(100 * frac)).sum())
        fee = cfg["sec_fee_bps"] / 1e4 * float(np.clip(-delta, 0, None).sum())
        hold = hold + delta
        r_int = float(hold @ intr)
        long_, short_ = float(hold[hold > 0].sum()), float(-hold[hold < 0].sum())
        cash = 1.0 - float(hold.sum())                         # short proceeds sit in cash
        rf_d = rf[t] if np.isfinite(rf[t]) else 0.0
        fin = cash * rf_d if cash >= 0 else cash * (rf_d + cfg["financing_spread"] / TRADING_DAYS)
        bor = short_ * cfg["borrow_fee"] / TRADING_DAYS
        cost = comm + spr + imp + fee
        day = (1 + r_ovn) * (1 + r_int - cost + fin - bor) - 1
        gross_day = (1 + r_ovn) * (1 + r_int + cash * rf_d) - 1          # before costs, fees and the financing spread
        nav *= 1 + day
        hold = hold * (1 + intr) / (1 + r_int) if abs(1 + r_int) > 1e-12 else hold
        o = out
        o["ret"][t], o["gross"][t] = day, gross_day
        o["commission"][t], o["spread"][t], o["impact"][t], o["fees"][t] = comm, spr, imp, fee
        o["borrow"][t], o["financing"][t] = bor, fin
        o["turnover"][t], o["long"][t], o["short"][t] = tv.sum(), long_, short_
        if nav <= 0:
            out["ret"][t] = -1.0
            break
    idx = close.index[first:]
    res = {k: pd.Series(v[first:], index=idx) for k, v in out.items()}
    res["weights_last"] = {k: round(float(v), 4) for k, v in zip(close.columns, W[-1]) if abs(v) > 1e-4}
    return res


# ── Statistics ──────────────────────────────────────────────────────────────
def metrics(ret: pd.Series, rf: Optional[pd.Series] = None) -> Dict[str, Optional[float]]:
    r = ret.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / TRADING_DAYS
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    sd = float(ex.std())
    dd = eq / eq.cummax() - 1
    down = ex[ex < 0]
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1.0
    return {"cagr": round(cagr, 4), "vol": round(float(r.std() * math.sqrt(TRADING_DAYS)), 4),
            "sharpe": round(float(ex.mean() / sd * math.sqrt(TRADING_DAYS)), 3) if sd > 0 else None,
            "sortino": round(float(ex.mean() / down.std() * math.sqrt(TRADING_DAYS)), 3) if len(down) > 5 and down.std() > 0 else None,
            "max_drawdown": round(float(dd.min()), 4),
            "calmar": round(cagr / abs(float(dd.min())), 3) if dd.min() < 0 else None,
            "log_growth": round(float(np.log1p(r.clip(lower=-0.999)).mean() * TRADING_DAYS), 4),
            "hit_rate": round(float((r > 0).mean()), 3), "years": round(yrs, 1),
            "total_return": round(float(eq.iloc[-1] - 1), 4)}


def cost_summary(res: Dict[str, Any]) -> Dict[str, float]:
    """Average annual drag of each cost item (fraction of NAV per year)."""
    n = max(len(res["ret"]), 1)
    yr = TRADING_DAYS / n
    out = {k: round(float(res[k].sum()) * yr, 5) for k in ("commission", "spread", "impact", "fees", "borrow")}
    out["financing_net"] = round(float(res["financing"].sum()) * yr, 5)
    out["turnover"] = round(float(res["turnover"].sum()) * yr, 2)
    out["avg_long"] = round(float(res["long"].mean()), 3)
    out["avg_short"] = round(float(res["short"].mean()), 3)
    out["total_trading"] = round(sum(out[k] for k in ("commission", "spread", "impact", "fees")), 5)
    return out


# ── Walk-forward optimisation ───────────────────────────────────────────────
def grid(params: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    combos: List[Dict[str, Any]] = [{}]
    for k, vals in (params or {}).items():
        combos = [{**c, k: v} for c in combos for v in vals]
    return combos


def walk_forward(run: Callable[[Dict[str, Any]], pd.Series], params: Dict[str, Sequence[Any]],
                 warmup_years: int = 5, objective: str = "log_growth") -> Dict[str, Any]:
    """Each January, pick the parameter set with the best `objective` on all data before it (net of
    costs) and trade it for the year — the stitched record is out-of-sample. `run(p)` returns daily
    net returns for parameters p over the full history."""
    combos = grid(params)
    if len(combos) > 48:
        raise ValueError(f"{len(combos)} parameter combinations — keep the grid to 48 or fewer.")
    series = [run(p) for p in combos]
    idx = series[0].index
    years = sorted(set(idx.year))
    start_year = years[0] + warmup_years
    oos = pd.Series(np.nan, index=idx)
    chosen = []
    for y in years:
        if y < start_year:
            continue
        past = idx < pd.Timestamp(f"{y}-01-01")
        scores = []
        for s in series:
            m = metrics(s[past])
            scores.append(m.get(objective) if m.get(objective) is not None else -1e9)
        best = int(np.argmax(scores))
        cur = (idx >= pd.Timestamp(f"{y}-01-01")) & (idx < pd.Timestamp(f"{y + 1}-01-01"))
        oos[cur] = series[best][cur]
        chosen.append({"year": y, "params": combos[best], "trailing": round(float(scores[best]), 4)})
    full = [metrics(s[idx >= pd.Timestamp(f"{start_year}-01-01")]) for s in series]
    in_best = int(np.argmax([f.get(objective) or -1e9 for f in full]))
    return {"oos": oos.dropna(), "chosen": chosen, "combos": combos,
            "in_sample_best": {"params": combos[in_best], **full[in_best]},
            "all": [{"params": c, **f} for c, f in zip(combos, full)]}


# ── Monte Carlo ─────────────────────────────────────────────────────────────
def _stationary_bootstrap_idx(n: int, length: int, paths: int, mean_block: int, rng) -> np.ndarray:
    """Politis & Romano (1994): blocks of geometric length (mean `mean_block`), random starts, wrapping."""
    idx = np.empty((paths, length), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, paths)
    new_block = rng.random((paths, length)) < 1.0 / mean_block
    starts = rng.integers(0, n, (paths, length))
    for t in range(1, length):
        idx[:, t] = np.where(new_block[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def monte_carlo(ret: pd.Series, rf: Optional[pd.Series] = None, years: float = 10.0, paths: int = 2000,
                mean_block: int = 21, seed: int = 7, leverage_grid: Sequence[float] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0),
                financing_spread: float = 0.01, dd_limit: float = 0.5, dd_prob: float = 0.05,
                max_leverage: float = 2.0) -> Dict[str, Any]:
    """Resample the strategy's daily (net) returns in blocks to simulate `paths` futures of `years`.
    Also scales the excess return by leverage L (financing at T-bill + spread above 1×) to find the
    growth-optimal (Kelly) leverage and the largest leverage keeping P(drawdown > dd_limit) ≤ dd_prob."""
    r = ret.dropna().to_numpy(float)
    rfv = (rf.reindex(ret.dropna().index).fillna(0.0).to_numpy(float) if rf is not None else np.zeros_like(r))
    if r.size < 250:
        raise ValueError("Need at least a year of returns for a Monte Carlo.")
    rng = np.random.default_rng(seed)
    H = int(round(years * TRADING_DAYS))
    paths = int(min(max(paths, 200), 5000))
    idx = _stationary_bootstrap_idx(r.size, H, paths, mean_block, rng)
    ex = r - rfv

    def sim(L: float):
        rr = rfv[idx] + L * ex[idx] - (max(L - 1, 0) * financing_spread / TRADING_DAYS)
        rr = np.clip(rr, -0.99, None)
        logw = np.cumsum(np.log1p(rr), axis=1)
        dd = logw - np.maximum.accumulate(logw, axis=1)
        return logw, 1 - np.exp(dd.min(axis=1))
    logw, mdd = sim(1.0)
    term = np.exp(logw[:, -1])
    cagr = term ** (1 / years) - 1
    step = max(1, H // 120)
    pts = list(range(step - 1, H, step))
    if pts[-1] != H - 1:
        pts.append(H - 1)
    q = np.percentile(np.exp(logw[:, pts]), [5, 25, 50, 75, 95], axis=0)
    fan = [{"year": round((t + 1) / TRADING_DAYS, 2), "p5": round(float(q[0, i]), 4), "p25": round(float(q[1, i]), 4),
            "p50": round(float(q[2, i]), 4), "p75": round(float(q[3, i]), 4), "p95": round(float(q[4, i]), 4)} for i, t in enumerate(pts)]
    hist_edges = np.linspace(np.percentile(cagr, 0.5), np.percentile(cagr, 99.5), 31)
    counts, edges = np.histogram(np.clip(cagr, hist_edges[0], hist_edges[-1]), bins=hist_edges)
    lev = []
    for L in leverage_grid:
        lw, md = sim(float(L))
        g = lw[:, -1] / years
        lev.append({"leverage": L, "median_cagr": round(float(np.expm1(np.median(g))), 4),
                    "p5_cagr": round(float(np.expm1(np.percentile(g, 5))), 4),
                    "p_dd": round(float((md > dd_limit).mean()), 4), "median_max_dd": round(float(np.median(md)), 4),
                    "p_loss": round(float((lw[:, -1] < 0).mean()), 4)})
    mu, var = float(ex.mean()), float(ex.var())
    kelly = mu / var if var > 0 else None
    safe = [x["leverage"] for x in lev if x["p_dd"] <= dd_prob and x["leverage"] <= max_leverage]
    best_g = max(lev, key=lambda x: x["median_cagr"])
    if kelly is None or kelly <= 0:
        rec = 0.0                                                # no positive excess return to lever
    else:
        rec = max(safe) if safe else min(leverage_grid)
        rec = min(rec, max(0.25, math.floor(kelly / 2 * 4) / 4))   # never above half-Kelly (estimation error)
    return {
        "years": years, "paths": paths, "mean_block_days": mean_block, "based_on_days": int(r.size),
        "fan": fan,
        "cagr_pct": {p: round(float(np.percentile(cagr, p)), 4) for p in (5, 25, 50, 75, 95)},
        "max_dd_pct": {p: round(float(np.percentile(mdd, p)), 4) for p in (5, 50, 95)},
        "p_loss": round(float((term < 1).mean()), 4),
        "p_dd": {f"{int(x * 100)}": round(float((mdd > x).mean()), 4) for x in (0.1, 0.2, 0.3, 0.5)},
        "hist": [{"cagr": round(float((edges[i] + edges[i + 1]) / 2), 4), "count": int(counts[i])} for i in range(len(counts))],
        "leverage": lev, "kelly_full": None if kelly is None else round(kelly, 2),
        "growth_optimal_leverage": best_g["leverage"], "recommended_leverage": rec,
        "rule": f"Largest leverage with P(drawdown > {dd_limit:.0%}) ≤ {dd_prob:.0%}, capped at {max_leverage}× and at half-Kelly.",
    }


# ── Running user code ───────────────────────────────────────────────────────
def load_strategy(code: str, namespace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute strategy source and return its UNIVERSE / START / PARAMS / strategy. (The server never
    calls this on user code outside the sandbox; the browser runs it in Pyodide.)"""
    ns: Dict[str, Any] = {"np": np, "pd": pd, "math": math, "ewma_vol": ewma_vol, "momentum": momentum,
                          "hold_monthly": hold_monthly, "hold_weekly": hold_weekly, "normalize_gross": normalize_gross,
                          "vol_target": vol_target}
    if namespace:
        ns.update(namespace)
    exec(compile(code, "<strategy>", "exec"), ns)                    # noqa: S102 — see docstring
    fn = ns.get("strategy")
    if not callable(fn):
        raise ValueError("Define a function strategy(data, **params) that returns target weights.")
    uni = ns.get("UNIVERSE")
    if not isinstance(uni, (list, tuple)) or not uni or len(uni) > 80:
        raise ValueError("Set UNIVERSE to a list of 1–80 tickers.")
    return {"strategy": fn, "universe": [str(u).upper() for u in uni], "start": str(ns.get("START") or "2005-01-01")[:10],
            "params": ns.get("PARAMS") or {}, "benchmark": str(ns.get("BENCHMARK") or "SPY").upper()}


def run_weights(fn: Callable, data: Data, params: Dict[str, Any]) -> pd.DataFrame:
    w = fn(data, **params)
    if isinstance(w, pd.Series):
        w = w.to_frame()
    if not isinstance(w, pd.DataFrame):
        raise ValueError("strategy() must return a DataFrame of weights (dates × tickers).")
    unknown = [c for c in w.columns if c not in data.close.columns]
    if unknown:
        raise ValueError(f"Weights for tickers not in UNIVERSE: {', '.join(map(str, unknown[:5]))}")
    w = w.replace([np.inf, -np.inf], np.nan)
    return w


def evaluate(fn: Callable, data: Data, params: Dict[str, Sequence[Any]], start: str,
             costs: Optional[Dict[str, float]] = None, benchmark: Optional[pd.Series] = None) -> Dict[str, Any]:
    """Backtest (walk-forward if PARAMS has more than one combination). Returns everything the UI shows
    except the Monte Carlo and the deep analysis, which run on the resulting daily returns."""
    combos = grid(params)
    cache: Dict[str, Dict[str, Any]] = {}

    def full(p):
        key = repr(sorted(p.items()))
        if key not in cache:
            cache[key] = backtest(run_weights(fn, data, p), data, costs, start)
        return cache[key]
    if len(combos) > 1:
        wf = walk_forward(lambda p: full(p)["ret"], params)
        ret = wf["oos"]
        # cost series of the chosen parameter set each year
        parts = {k: [] for k in ("commission", "spread", "impact", "fees", "borrow", "financing", "turnover", "long", "short", "gross")}
        for ch in wf["chosen"]:
            r = full(ch["params"])
            m = r["ret"].index.year == ch["year"]
            for k in parts:
                parts[k].append(r[k][m])
        res = {k: pd.concat(v) if v else pd.Series(dtype=float) for k, v in parts.items()}
        res["ret"] = ret
        res["weights_last"] = full(wf["chosen"][-1]["params"])["weights_last"] if wf["chosen"] else {}
        opt = {"walk_forward": True, "chosen": wf["chosen"], "in_sample_best": wf["in_sample_best"], "grid": wf["all"],
               "oos_start": str(ret.index[0].date()) if len(ret) else None}
    else:
        res = full(combos[0])
        opt = {"walk_forward": False, "params": combos[0]}
    ret = res["ret"]
    out = {"metrics": metrics(ret, data.rf), "metrics_gross": metrics(res["gross"], data.rf), "costs": cost_summary(res),
           "optimisation": opt, "weights_last": res["weights_last"],
           "dates": [d.strftime("%Y-%m-%d") for d in ret.index], "returns": [round(float(x), 7) for x in ret.values],
           "gross": [round(float(x), 7) for x in res["gross"].reindex(ret.index).fillna(0).values]}
    if benchmark is not None:
        b = benchmark.reindex(ret.index).pct_change(fill_method=None).fillna(0.0)
        out["benchmark"] = [round(float(x), 7) for x in b.values]
        out["benchmark_metrics"] = metrics(b, data.rf)
    return out
