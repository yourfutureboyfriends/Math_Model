"""
Performance analytics for research results — one definition for every system compared.

Returns   total, CAGR (= annualised return), monthly and yearly returns, equity curve
Risk      volatility, Sharpe and Sortino (over the T-bill rate), max drawdown, Calmar, longest drawdown (sessions),
          VaR / CVaR 95% (daily), worst month, skew, kurtosis, risk concentration (share of P&L from the top 5 names)
Trading   trades, win rate, profit factor, average win / loss ($ and R), expectancy, trades per year, average holding
          (sessions), turnover (premium traded ÷ average NAV per year), capital utilisation (average and peak
          max-loss ÷ NAV), costs by kind (commissions, entry / exit spreads, assignment) as % of capital per year
Options   P&L and risk-adjusted results by strategy, exit reason, days to expiry, premium-to-risk, implied-vol class,
          vol regime at entry (VIX bucket), assignments; average and peak portfolio Greeks
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

PPY = 252


def _r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def returns_metrics(ret: np.ndarray, dates: Sequence[pd.Timestamp], rf_annual: np.ndarray) -> Dict[str, Any]:
    r = np.nan_to_num(np.asarray(ret, float))
    if len(r) < 20:
        return {"days": int(len(r))}
    ex = r - np.asarray(rf_annual, float)[:len(r)] / PPY
    eq = np.cumprod(1 + r)
    yrs = max((pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25, 1 / 365.25)
    cagr = eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 else -1.0
    vol = r.std(ddof=1) * math.sqrt(PPY)
    exv = ex.std(ddof=1) * math.sqrt(PPY)
    down = ex[ex < 0]
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    dd = eq / peak - 1
    longest, cur = 0, 0
    for u in dd < 0:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    s = pd.Series(r, index=pd.DatetimeIndex(dates))
    monthly = (1 + s).groupby(s.index.to_period("M")).prod() - 1
    yearly = (1 + s).groupby(s.index.year).prod() - 1
    var = np.percentile(r, 5)
    cvar = r[r <= var].mean() if (r <= var).any() else var
    m3 = ((r - r.mean()) ** 3).mean() / (r.std() ** 3) if r.std() > 0 else 0.0
    m4 = ((r - r.mean()) ** 4).mean() / (r.std() ** 4) if r.std() > 0 else 0.0
    mdd = dd.min()
    return {"total_return": _r(eq[-1] - 1), "cagr": _r(cagr), "vol": _r(vol),
            "sharpe": _r(ex.mean() * PPY / exv, 3) if exv > 0 else None,
            "sortino": _r(ex.mean() * PPY / (down.std(ddof=1) * math.sqrt(PPY)), 3) if down.size > 2 and down.std() > 0 else None,
            "max_drawdown": _r(mdd), "calmar": _r(cagr / abs(mdd), 3) if mdd < 0 else None,
            "longest_drawdown_days": int(longest), "var95_daily": _r(var, 5), "cvar95_daily": _r(cvar, 5),
            "worst_month": _r(monthly.min()), "best_month": _r(monthly.max()), "skew": _r(m3, 2), "kurtosis": _r(m4, 2),
            "positive_months": _r((monthly > 0).mean(), 3), "years": _r(yrs, 1),
            "monthly": {str(k): _r(v) for k, v in monthly.items()}, "yearly": {str(k): _r(v) for k, v in yearly.items()}}


def trade_metrics(trades: List[Dict[str, Any]], capital: float, years: float, avg_nav: Optional[float] = None,
                  risk_used: Optional[np.ndarray] = None, costs: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    if not trades:
        return {"trades": 0}
    df = pd.DataFrame(trades)
    p = df["pnl"].astype(float)
    w, l = p[p > 0], p[p <= 0]
    avg_nav = avg_nav or capital
    prem = (df["premium"] * df["contracts"] * 100).sum()
    by_name = df.groupby("ticker")["pnl"].sum().abs().sort_values(ascending=False)
    out = {"trades": int(len(df)), "win_rate": _r((p > 0).mean(), 3), "avg_win": _r(w.mean(), 2) if len(w) else None,
           "avg_loss": _r(l.mean(), 2) if len(l) else None,
           "profit_factor": _r(w.sum() / -l.sum(), 3) if len(l) and l.sum() < 0 else None,
           "expectancy": _r(p.mean(), 2), "expectancy_r": _r(df["r"].mean(), 4),
           "avg_win_r": _r(df.loc[p > 0, "r"].mean(), 3) if len(w) else None,
           "avg_loss_r": _r(df.loc[p <= 0, "r"].mean(), 3) if len(l) else None,
           "trades_per_year": _r(len(df) / max(years, 1e-9), 1), "avg_holding_days": _r(df["days"].mean(), 1),
           "turnover": _r(prem / avg_nav / max(years, 1e-9), 3),
           "assignments": int(df["assigned"].sum()), "assignment_rate": _r(df["assigned"].mean(), 4),
           "top5_pnl_share": _r(by_name.head(5).sum() / by_name.sum(), 3) if by_name.sum() > 0 else None,
           "underlyings": int(df["ticker"].nunique())}
    if risk_used is not None and len(risk_used):
        out["capital_utilisation_avg"] = _r(float(np.mean(risk_used)), 3)
        out["capital_utilisation_peak"] = _r(float(np.max(risk_used)), 3)
    if costs:
        tot = sum(costs.values())
        out["costs"] = {k: _r(v, 2) for k, v in costs.items()}
        out["costs_pct_capital_per_year"] = _r(tot / capital / max(years, 1e-9), 4)
        gross = p.sum() + tot
        out["costs_share_of_gross"] = _r(tot / gross, 3) if gross > 0 else None
    return out


def _bucket(df: pd.DataFrame, col: str, fn=None) -> List[Dict[str, Any]]:
    if col not in df or not len(df):
        return []
    key = df[col].map(fn) if fn else df[col]
    rows = []
    for k, g in df.groupby(key):
        if len(g) < 3:
            continue
        rows.append({"group": str(k), "trades": int(len(g)), "pnl": _r(g["pnl"].sum(), 2), "win_rate": _r((g["pnl"] > 0).mean(), 3),
                     "expectancy_r": _r(g["r"].mean(), 4), "r_t_stat": _r(g["r"].mean() / (g["r"].std() / math.sqrt(len(g))), 2)
                     if len(g) > 2 and g["r"].std() > 0 else None})
    return rows


def option_breakdowns(trades: List[Dict[str, Any]], vix_at: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    if vix_at:
        df["vix_entry"] = df["entry"].map(vix_at)
    dte_b = lambda d: "≤20" if d <= 20 else "21–35" if d <= 35 else "36–50" if d <= 50 else "51–70" if d <= 70 else ">70"
    ptr_b = lambda x: "<0.15" if x < 0.15 else "0.15–0.3" if x < 0.3 else "0.3–0.5" if x < 0.5 else "0.5–1" if x < 1 else "≥1"
    vix_b = lambda v: "unknown" if v is None or not np.isfinite(v) else "<15" if v < 0.15 else "15–20" if v < 0.2 else "20–30" if v < 0.3 else "≥30"
    out = {"by_strategy": _bucket(df, "strategy"), "by_exit": _bucket(df, "reason"), "by_dte": _bucket(df, "dte", dte_b),
           "by_premium_to_risk": _bucket(df, "premium_to_risk", ptr_b), "by_iv_class": _bucket(df, "iv_class"),
           "by_sector": sorted(_bucket(df, "sector"), key=lambda r: -(r["trades"])),
           "by_year": _bucket(df, "entry", lambda d: str(d)[:4]),
           "expiration_distribution": [{"dte": k, "trades": int(v)} for k, v in df["dte"].map(dte_b).value_counts().sort_index().items()],
           "holding_distribution": [{"days": k, "trades": int(v)} for k, v in
                                    df["days"].map(lambda d: "≤5" if d <= 5 else "6–10" if d <= 10 else "11–20" if d <= 20 else "21–40" if d <= 40 else ">40").value_counts().sort_index().items()]}
    if "vix_entry" in df:
        out["by_vol_regime"] = _bucket(df, "vix_entry", vix_b)
    return out


def drawdown_series(ret: np.ndarray) -> np.ndarray:
    eq = np.cumprod(1 + np.nan_to_num(np.asarray(ret, float)))
    return eq / np.maximum.accumulate(eq) - 1


def segment(ret: np.ndarray, dates: pd.DatetimeIndex, rf: np.ndarray, a: str, b: Optional[str]) -> Dict[str, Any]:
    m = (dates >= pd.Timestamp(a)) & ((dates <= pd.Timestamp(b)) if b else True)
    if m.sum() < 20:
        return {"days": int(m.sum())}
    out = returns_metrics(ret[m], dates[m], rf[m])
    out.pop("monthly", None)
    return out


def thin(dates: pd.DatetimeIndex, *series: np.ndarray, max_points: int = 600) -> Dict[str, Any]:
    step = max(1, len(dates) // max_points)
    keep = np.r_[np.arange(0, len(dates), step), len(dates) - 1] if len(dates) else np.array([], int)
    keep = np.unique(keep)
    return {"dates": [str(dates[i].date()) for i in keep],
            "series": [[_r(float(s[i]), 5) for i in keep] for s in series]}
