"""
Deep backtest analysis — one report for every automated book (Quant Lab algos in the Macro / Fundamental /
Technical traders, the macro model book, the stock entry book). Input: a return series (daily or monthly),
optionally a benchmark on the same dates and a trade list.

  summary      return / risk / ratio statistics incl. Ulcer index, tail ratio, VaR & CVaR, streaks
  calendar     monthly returns by year (+ the benchmark's year)
  drawdowns    the five worst drawdowns with dates, depth, time to trough and to recovery; underwater curve
  distribution histogram of monthly returns vs the benchmark
  rolling      12-month return, volatility, Sharpe, beta and correlation
  benchmark    alpha, beta, up / down capture, tracking error, information ratio, months beating
  regimes      by growth/inflation environment (Bridgewater), by VIX level, by the benchmark's trend, in crises
  robustness   block-bootstrap ranges for 1/3/5 years (chance of a loss), max-drawdown range, first vs second half,
               year-by-year Sharpe, probabilistic Sharpe and the minimum track record length
  trades       R-multiples, win rate, payoff, profit factor, expectancy, streaks, by exit / holding period / year / group
"""
from __future__ import annotations

import itertools
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CRISES = [("Global financial crisis", "2008-09-01", "2009-03-09"), ("Euro debt crisis", "2011-07-22", "2011-10-03"),
          ("China deval / oil crash", "2015-08-10", "2016-02-11"), ("Volmageddon", "2018-01-26", "2018-02-08"),
          ("Q4 2018 sell-off", "2018-09-20", "2018-12-24"), ("Covid crash", "2020-02-19", "2020-03-23"),
          ("2022 rate shock", "2022-01-03", "2022-10-12"), ("Yen carry unwind", "2024-07-16", "2024-08-05")]


def _r(x, d=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), d)


def _cash(idx: pd.DatetimeIndex, ppy: float) -> pd.Series:
    """T-bill return per period (daily rate scaled to the sampling frequency); 0 where unknown."""
    from api.quant import rates
    try:
        return rates.daily(idx) * (252 / ppy) if len(idx) else pd.Series(dtype=float)
    except Exception:                                    # noqa: BLE001
        return pd.Series(0.0, index=idx)


def _stats(r: pd.Series, ppy: float) -> Dict[str, Any]:
    """Sharpe and Sortino are on returns above T-bills (the cash an investor could hold instead)."""
    r = r.dropna()
    if len(r) < 3:
        return {}
    ex = r - _cash(r.index, ppy).to_numpy()
    ex_down = ex[ex < 0].std() * math.sqrt(ppy) if (ex < 0).sum() > 2 else None
    eq = (1 + r).cumprod()
    yrs = len(r) / ppy
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 and yrs > 0 else None
    vol = r.std() * math.sqrt(ppy)
    down = r[r < 0].std() * math.sqrt(ppy) if (r < 0).sum() > 2 else None
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    ulcer = float(np.sqrt((dd ** 2).mean()))
    q05, q95 = r.quantile(0.05), r.quantile(0.95)
    cvar = r[r <= q05].mean()
    wins, losses = r[r > 0], r[r < 0]
    streak = lambda sign: max((len(list(g)) for k, g in itertools.groupby(np.sign(r.values)) if k == sign), default=0)
    return {"total_return": _r(eq.iloc[-1] - 1), "cagr": _r(cagr), "vol": _r(vol),
            "sharpe": _r(ex.mean() / ex.std() * math.sqrt(ppy)) if ex.std() > 0 else None,
            "sortino": _r(ex.mean() * ppy / ex_down) if ex_down else None, "cash_rate": _r(float((r - ex).mean() * ppy)), "calmar": _r(cagr / -mdd) if cagr is not None and mdd < 0 else None,
            "max_drawdown": _r(mdd), "avg_drawdown": _r(float(dd[dd < 0].mean())) if (dd < 0).any() else 0.0, "ulcer_index": _r(ulcer),
            "ulcer_performance": _r(cagr / ulcer) if cagr is not None and ulcer > 0 else None,
            "skew": _r(float(r.skew()), 2), "excess_kurtosis": _r(float(r.kurt()), 2),
            "var95": _r(-q05), "cvar95": _r(-cvar), "tail_ratio": _r(q95 / -q05) if q05 < 0 else None,
            "gain_pain": _r(wins.sum() / -losses.sum()) if losses.sum() < 0 else None,
            "pct_positive": _r((r > 0).mean(), 3), "best": _r(r.max()), "worst": _r(r.min()),
            "avg_win": _r(wins.mean()) if len(wins) else None, "avg_loss": _r(losses.mean()) if len(losses) else None,
            "longest_win_streak": streak(1), "longest_loss_streak": streak(-1), "periods": int(len(r)), "years": _r(yrs, 1)}


def _to_monthly(r: pd.Series, ppy: float) -> pd.Series:
    if ppy <= 13:
        return r
    return (1 + r).resample("ME").prod() - 1


def _drawdowns(r: pd.Series, top: int = 5) -> List[Dict[str, Any]]:
    eq = (1 + r.fillna(0)).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1
    out, in_dd, start = [], False, None
    for d, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, d
        elif v >= 0 and in_dd:
            seg = dd[start:d]
            out.append((start, seg.idxmin(), d, float(seg.min())))
            in_dd = False
    if in_dd:
        seg = dd[start:]
        out.append((start, seg.idxmin(), None, float(seg.min())))
    out.sort(key=lambda x: x[3])
    res = []
    for s, t, e, depth in out[:top]:
        res.append({"start": s.strftime("%Y-%m-%d"), "trough": t.strftime("%Y-%m-%d"), "recovered": e.strftime("%Y-%m-%d") if e is not None else None,
                    "depth": _r(depth), "days_to_trough": int((t - s).days), "days_to_recover": int((e - t).days) if e is not None else None,
                    "total_days": int(((e if e is not None else dd.index[-1]) - s).days)})
    return res


def _psr(r: pd.Series, sr_benchmark: float = 0.0) -> Optional[float]:
    """Probabilistic Sharpe ratio (Bailey & López de Prado 2012): P(true per-period Sharpe > benchmark)."""
    r = r.dropna()
    n = len(r)
    if n < 10 or r.std() == 0:
        return None
    sr = r.mean() / r.std()
    g3, g4 = float(r.skew()), float(r.kurt()) + 3
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / den
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _min_trl(r: pd.Series, ppy: float, conf: float = 0.95) -> Optional[float]:
    """Minimum track record length (years) to be `conf` sure the Sharpe is above zero."""
    r = r.dropna()
    if len(r) < 10 or r.std() == 0:
        return None
    sr = r.mean() / r.std()
    if sr <= 0:
        return None
    g3, g4 = float(r.skew()), float(r.kurt()) + 3
    z = 1.6448536 if conf == 0.95 else 2.326
    n = 1 + (1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) * (z / sr) ** 2
    return n / ppy


def _bootstrap(r: pd.Series, ppy: float, horizons=(1, 3, 5), n: int = 2000, block: Optional[int] = None, seed: int = 7) -> Dict[str, Any]:
    x = r.dropna().values
    if len(x) < 24:
        return {}
    rng = np.random.default_rng(seed)
    b = block or (21 if ppy > 13 else 3)
    out = {}
    for h in horizons:
        m = int(round(h * ppy))
        if m < 2:
            continue
        starts = rng.integers(0, max(1, len(x) - b), size=(n, math.ceil(m / b)))
        rets = np.empty(n)
        for k in range(n):
            seq = np.concatenate([x[s:s + b] for s in starts[k]])[:m]
            rets[k] = np.prod(1 + seq) ** (1 / h) - 1
        out[f"{h}y"] = {"p5": _r(np.percentile(rets, 5)), "p25": _r(np.percentile(rets, 25)), "p50": _r(np.percentile(rets, 50)),
                        "p75": _r(np.percentile(rets, 75)), "p95": _r(np.percentile(rets, 95)), "prob_loss": _r((rets < 0).mean(), 3)}
    # max drawdown over a full-length resample
    starts = rng.integers(0, max(1, len(x) - b), size=(500, math.ceil(len(x) / b)))
    mdds = []
    for k in range(500):
        seq = np.concatenate([x[s:s + b] for s in starts[k]])[:len(x)]
        eq = np.cumprod(1 + seq)
        mdds.append(float((eq / np.maximum.accumulate(eq) - 1).min()))
    out["max_drawdown"] = {"p50": _r(np.percentile(mdds, 50)), "p95_worst": _r(np.percentile(mdds, 5))}
    return out


def _benchmark(r: pd.Series, b: pd.Series, ppy: float) -> Dict[str, Any]:
    df = pd.concat([r.rename("s"), b.rename("b")], axis=1).dropna()
    if len(df) < 12:
        return {}
    cov = np.cov(df["s"], df["b"])
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else None
    alpha = (df["s"].mean() - (beta or 0) * df["b"].mean()) * ppy if beta is not None else None
    up, dn = df[df["b"] > 0], df[df["b"] < 0]
    active = df["s"] - df["b"]
    te = active.std() * math.sqrt(ppy)
    m = _to_monthly(df["s"], ppy), _to_monthly(df["b"], ppy)
    yr_s, yr_b = (1 + df["s"]).groupby(df.index.year).prod() - 1, (1 + df["b"]).groupby(df.index.year).prod() - 1
    rel = (yr_s - yr_b)
    return {"alpha": _r(alpha), "beta": _r(beta, 3), "correlation": _r(df["s"].corr(df["b"]), 3),
            "up_capture": _r(up["s"].mean() / up["b"].mean(), 3) if len(up) > 5 and up["b"].mean() != 0 else None,
            "down_capture": _r(dn["s"].mean() / dn["b"].mean(), 3) if len(dn) > 5 and dn["b"].mean() != 0 else None,
            "tracking_error": _r(te), "information_ratio": _r(active.mean() * ppy / te) if te > 0 else None,
            "pct_months_beating": _r(float((m[0] > m[1]).mean()), 3),
            "best_relative_year": {"year": int(rel.idxmax()), "diff": _r(rel.max())} if len(rel) else None,
            "worst_relative_year": {"year": int(rel.idxmin()), "diff": _r(rel.min())} if len(rel) else None}


def _regimes(rm: pd.Series, bm: Optional[pd.Series]) -> Dict[str, Any]:
    """Annualised return / Sharpe of the monthly series in each environment."""
    def block(mask_by: Dict[str, pd.Series]) -> List[Dict[str, Any]]:
        rows = []
        for name, idx in mask_by.items():
            x = rm[rm.index.isin(idx)].dropna()
            if len(x) < 6:
                continue
            y = bm[bm.index.isin(idx)].dropna() if bm is not None else None
            rows.append({"regime": name, "months": int(len(x)), "return": _r(x.mean() * 12),
                         "sharpe": _r(x.mean() / x.std() * math.sqrt(12)) if x.std() > 0 else None, "hit": _r((x > 0).mean(), 3),
                         "benchmark_return": _r(y.mean() * 12) if y is not None and len(y) else None})
        return rows
    out: Dict[str, Any] = {}
    try:
        from api.marketdata.bridgewater import SHORT, _quadrants
        q = _quadrants()
        out["environment"] = block({SHORT[(g, i)]: q[(q["g"] == g) & (q["i"] == i)].index for (g, i) in SHORT})
    except Exception as e:
        logger.info("[deep] quadrants: %s", e)
    try:
        from api.marketdata.bridgewater import _fred_monthly
        vix = _fred_monthly("VIXCLS", 40)
        out["volatility"] = block({"Calm (VIX < 15)": vix[vix < 15].index, "Normal (15–25)": vix[(vix >= 15) & (vix <= 25)].index,
                                   "Stressed (VIX > 25)": vix[vix > 25].index})
    except Exception as e:
        logger.info("[deep] vix: %s", e)
    if bm is not None and len(bm.dropna()) > 12:
        lvl = (1 + bm.fillna(0)).cumprod()
        up = lvl > lvl.rolling(10).mean()
        out["market_trend"] = block({"Benchmark above its 10-month average": up[up].index, "Benchmark below it": up[~up & lvl.rolling(10).mean().notna()].index})
    return out


def _crises(r: pd.Series, b: Optional[pd.Series]) -> List[Dict[str, Any]]:
    rows = []
    for name, a, z in CRISES:
        A, Z = pd.Timestamp(a), pd.Timestamp(z)
        x = r[(r.index > A) & (r.index <= Z + pd.Timedelta(days=31 if len(r) < 2000 else 0))]
        if r.index[0] > A or len(x) == 0:
            continue
        y = b[(b.index > A) & (b.index <= Z + pd.Timedelta(days=31 if len(r) < 2000 else 0))] if b is not None else None
        rows.append({"episode": name, "start": a, "end": z, "return": _r(float(np.prod(1 + x.fillna(0)) - 1)),
                     "benchmark": _r(float(np.prod(1 + y.fillna(0)) - 1)) if y is not None and len(y) else None})
    return rows


def _trades(trades: List[Dict[str, Any]], group_key: Optional[str]) -> Dict[str, Any]:
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    val = "r" if "r" in df and df["r"].notna().any() else "ret"
    x = df[val].astype(float)
    w, l = x[x > 0], x[x <= 0]
    seq = np.sign(x.values)
    max_losses = max((len(list(g)) for k, g in itertools.groupby(seq) if k < 0), default=0)
    edges = np.array([-3, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5]) if val == "r" else np.array([-0.3, -0.2, -0.1, -0.05, 0, 0.05, 0.1, 0.2, 0.3, 0.5])
    hist, _ = np.histogram(x.clip(edges[0], edges[-1]), bins=edges)

    def by(col, fn=None):
        if col not in df:
            return []
        g = df.groupby(df[col].map(fn) if fn else df[col])[val]
        return [{"group": str(k), "trades": int(len(v)), "win_rate": _r((v > 0).mean(), 3), "avg": _r(v.mean(), 3), "total": _r(v.sum(), 2)}
                for k, v in g if len(v) >= 5]
    hold = None
    if "days" in df:
        hold = by("days", lambda d: "1–5 days" if d <= 5 else "6–10" if d <= 10 else "11–20" if d <= 20 else "21–40" if d <= 40 else "41+")
    res = {"unit": "R" if val == "r" else "return", "trades": int(len(x)), "win_rate": _r((x > 0).mean(), 3),
           "avg_win": _r(w.mean(), 3) if len(w) else None, "avg_loss": _r(l.mean(), 3) if len(l) else None,
           "payoff_ratio": _r(w.mean() / -l.mean(), 2) if len(w) and len(l) and l.mean() < 0 else None,
           "profit_factor": _r(w.sum() / -l.sum(), 2) if len(l) and l.sum() < 0 else None, "expectancy": _r(x.mean(), 3),
           "t_stat": _r(x.mean() / (x.std() / math.sqrt(len(x))), 2) if x.std() > 0 else None, "max_consecutive_losses": int(max_losses),
           "histogram": [{"bin": f"{edges[i]:g} to {edges[i + 1]:g}", "count": int(hist[i])} for i in range(len(hist))],
           "by_exit": by("reason"), "by_holding": hold or [], "by_year": by("entry_date", lambda d: str(d)[:4]) if "entry_date" in df else [],
           "best": df.nlargest(5, val).to_dict("records"), "worst": df.nsmallest(5, val).to_dict("records")}
    if group_key and group_key in df:
        res["by_group"] = by(group_key)
        res["group_name"] = group_key
    return res


def report(dates: Sequence[str], returns: Sequence[float], ppy: float = 252, benchmark: Optional[Sequence[float]] = None,
           trades: Optional[List[Dict[str, Any]]] = None, label: str = "Strategy", benchmark_label: str = "Benchmark",
           trade_group: Optional[str] = None) -> Dict[str, Any]:
    idx = pd.to_datetime(list(dates))
    # periods per year from the dates themselves: a global calendar (Gulf markets trade on Sundays) has more than 252
    # sessions a year, a weekly-sampled curve ~52 — assuming the nominal figure would misstate CAGR and volatility
    span_years = (idx[-1] - idx[0]).days / 365.25 if len(idx) > 1 else 0
    if span_years > 0.5:
        actual = (len(idx) - 1) / span_years
        if abs(actual / ppy - 1) > 0.05:
            ppy = actual
    r = pd.Series(np.asarray(returns, float), index=idx).replace([np.inf, -np.inf], np.nan)
    b = pd.Series(np.asarray(benchmark, float), index=idx).replace([np.inf, -np.inf], np.nan) if benchmark is not None else None
    rm = _to_monthly(r.fillna(0), ppy)
    if b is not None:
        bm = _to_monthly(b.fillna(0), ppy)
        if ppy > 13:                       # months with no benchmark data at all stay blank, not 0%
            have = b.notna().resample("ME").sum()
            bm = bm.where(have.reindex(bm.index).fillna(0) > 0)
        else:
            bm = b.copy()
    else:
        bm = None
    # calendar
    cal = []
    for y, g in rm.groupby(rm.index.year):
        row = {"year": int(y), "months": {int(d.month): _r(v) for d, v in g.items()}, "total": _r(float(np.prod(1 + g) - 1))}
        if bm is not None:
            gb = bm[bm.index.year == y]
            row["benchmark"] = _r(float(np.prod(1 + gb) - 1)) if len(gb) and gb.notna().all() else None
        cal.append(row)
    # rolling 12 months (monthly)
    roll = []
    if len(rm) > 13:
        r12 = (1 + rm).rolling(12).apply(np.prod, raw=True) - 1
        v12 = rm.rolling(12).std() * math.sqrt(12)
        exm = rm - _cash(rm.index, 12).to_numpy() if ppy > 13 else rm - _cash(rm.index, ppy).to_numpy()
        s12 = exm.rolling(12).mean() / exm.rolling(12).std() * math.sqrt(12)
        if bm is not None:
            cv = rm.rolling(24).cov(bm)
            beta24 = cv / bm.rolling(24).var()
            corr24 = rm.rolling(24).corr(bm)
        for d in rm.index[11:]:
            roll.append({"date": d.strftime("%Y-%m"), "return_12m": _r(r12.get(d)), "vol_12m": _r(v12.get(d)), "sharpe_12m": _r(s12.get(d), 2),
                         **({"beta_24m": _r(beta24.get(d), 2), "corr_24m": _r(corr24.get(d), 2)} if bm is not None else {})})
    # underwater (thinned)
    eq = (1 + r.fillna(0)).cumprod()
    dd = eq / eq.cummax() - 1
    step = max(1, len(dd) // 600)
    underwater = [{"date": d.strftime("%Y-%m-%d"), "drawdown": _r(v), "equity": _r(eq.loc[d])} for k, (d, v) in enumerate(dd.items()) if k % step == 0 or k == len(dd) - 1]
    if b is not None:
        eqb = (1 + b.fillna(0)).cumprod()
        ddb = eqb / eqb.cummax() - 1
        for u in underwater:
            d = pd.Timestamp(u["date"])
            u["benchmark_drawdown"] = _r(ddb.get(d))
            u["benchmark_equity"] = _r(eqb.get(d))
    # distribution of monthly returns
    edges = np.linspace(-0.2, 0.2, 17)
    hs, _ = np.histogram(rm.clip(-0.2, 0.2), bins=edges)
    hb, _ = np.histogram(bm.dropna().clip(-0.2, 0.2), bins=edges) if bm is not None else (None, None)
    dist = [{"bin": f"{edges[i] * 100:.1f}%", "strategy": int(hs[i]), **({"benchmark": int(hb[i])} if hb is not None else {})} for i in range(len(hs))]
    # stability
    half = len(r) // 2
    years = []
    for y, g in r.groupby(r.index.year):
        if len(g) >= (ppy / 2 if ppy > 13 else 6):
            ge = g - _cash(g.index, ppy).to_numpy()
            years.append({"year": int(y), "return": _r(float(np.prod(1 + g.fillna(0)) - 1)),
                          "sharpe": _r(ge.mean() / ge.std() * math.sqrt(ppy), 2) if ge.std() > 0 else None})
    sh = [y["sharpe"] for y in years if y["sharpe"] is not None]
    robust = {"bootstrap": _bootstrap(r, ppy), "first_half": _stats(r.iloc[:half], ppy), "second_half": _stats(r.iloc[half:], ppy),
              "by_year": years, "pct_years_positive_sharpe": _r(float(np.mean([s > 0 for s in sh])), 3) if sh else None,
              "sharpe_dispersion": _r(float(np.std(sh)), 2) if len(sh) > 2 else None,
              "psr": _r(_psr(r - _cash(r.index, ppy).to_numpy()), 3),
              "min_track_record_years": _r(_min_trl(r - _cash(r.index, ppy).to_numpy(), ppy), 1)}
    out = {"label": label, "benchmark_label": benchmark_label if b is not None else None, "frequency": "daily" if ppy >= 200 else "weekly" if ppy >= 40 else "monthly",
           "start": idx[0].strftime("%Y-%m-%d"), "end": idx[-1].strftime("%Y-%m-%d"),
           "summary": _stats(r, ppy), "benchmark_summary": _stats(b, ppy) if b is not None else None,
           "calendar": cal, "drawdowns": _drawdowns(r), "benchmark_drawdowns": _drawdowns(b) if b is not None else None,
           "underwater": underwater, "distribution": dist, "rolling": roll,
           "relative": _benchmark(r, b, ppy) if b is not None else None,
           "regimes": _regimes(rm, bm), "crises": _crises(rm if ppy <= 13 else r, (bm if ppy <= 13 else b) if b is not None else None),
           "robustness": robust, "trades": _trades(trades or [], trade_group) if trades else None,
           "notes": ["Statistics are before taxes; Sharpe uses a zero risk-free rate (returns are already after costs where the book charges them).",
                     "Bootstrap: 2,000 paths of resampled blocks of the book's own returns (1-month blocks for daily data) — the spread of "
                     "outcomes the same strategy could have produced, not a forecast.",
                     "Minimum track record = years of data needed to be 95% confident the true Sharpe is above zero (Bailey & López de Prado)."]}
    return out
