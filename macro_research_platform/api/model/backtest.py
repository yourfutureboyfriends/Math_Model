"""
Walk-forward backtest of the systematic macro model.

At every month-end t the whole model is re-estimated on data available at t (factors,
regime models, conditional means, covariance, Black–Litterman, optimiser) and the
resulting weights are held over month t+1. Costs are charged on turnover from the drifted
prior weights. Benchmarks use the same months: 60/40 (US equity / intermediate Treasuries),
equal weight, and inverse-volatility risk parity across the same available assets.

Forecast skill: the growth/inflation direction probabilities are scored against the
realised regime with the Brier score and the Brier skill score vs the training base rate.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from api.model.core import QUADRANT_OF, ModelParams, decide, realized_regimes


def _stats(r: pd.Series) -> Dict[str, Optional[float]]:
    r = r.dropna()
    if len(r) < 12:
        return {"months": len(r)}
    growth = (1 + r).cumprod()
    years = len(r) / 12
    cagr = growth.iloc[-1] ** (1 / years) - 1
    vol = r.std() * math.sqrt(12)
    dd = (growth / growth.cummax() - 1).min()
    downside = r[r < 0].std() * math.sqrt(12)
    return {"months": len(r), "cagr": round(float(cagr), 4), "vol": round(float(vol), 4),
            "sharpe": round(float(r.mean() * 12 / vol), 2) if vol > 0 else None,
            "sortino": round(float(r.mean() * 12 / downside), 2) if downside > 0 else None,
            "max_drawdown": round(float(dd), 4),
            "calmar": round(float(cagr / abs(dd)), 2) if dd < 0 else None,
            "hit_rate": round(float((r > 0).mean()), 3)}


def run_backtest(panel: pd.DataFrame, rets: pd.DataFrame, blocks: Dict[str, str], env_class: Dict[str, str],
                 p: ModelParams, start: Optional[str] = None) -> Dict:
    months = list(rets.index)
    first = pd.Timestamp(start) if start else None
    rows, weights_log, fc = [], [], []
    w_prev = pd.Series(dtype=float)
    ws_prev = pd.Series(dtype=float)
    for t, t_next in zip(months[:-1], months[1:]):
        if first is not None and t < first:
            continue
        d = decide(panel, rets, blocks, env_class, t, p)
        if d is None:
            continue
        w = pd.Series(d.weights, index=d.assets)
        r_next = rets.loc[t_next, d.assets].fillna(0.0)
        # turnover vs the previous weights after they drifted through month t
        if not w_prev.empty:
            r_t = rets.loc[t].reindex(w_prev.index).fillna(0.0)
            drifted = w_prev * (1 + r_t) / (1 + float((w_prev * r_t).sum()))
        else:
            drifted = pd.Series(dtype=float)
        all_idx = w.index.union(drifted.index)
        turnover = float((w.reindex(all_idx, fill_value=0) - drifted.reindex(all_idx, fill_value=0)).abs().sum())
        gross = float((w * r_next).sum())
        net = gross - turnover * p.cost_bps / 1e4
        ws = pd.Series(d.strategic, index=d.assets)
        s_turn = float((ws.reindex(all_idx, fill_value=0) - ws_prev.reindex(all_idx, fill_value=0)).abs().sum()) \
            if not ws_prev.empty else float(ws.abs().sum())
        strat = float((ws * r_next).sum()) - s_turn * p.cost_bps / 1e4
        # benchmarks on the same assets/month
        avail = [a for a in d.assets if not math.isnan(rets.loc[t_next, a])]
        hist = rets.loc[:t, avail].tail(36)
        iv = 1 / hist.std().replace(0, np.nan)
        iv = (iv / iv.sum()).fillna(0)
        bench_6040 = (0.6 * rets.loc[t_next, "US equity"] + 0.4 * rets.loc[t_next, "Intermediate Treasuries"]
                      if {"US equity", "Intermediate Treasuries"} <= set(avail) else np.nan)
        rows.append({"month": t_next, "model": net, "strategic": strat, "model_gross": gross, "turnover": turnover,
                     "cash": d.cash, "equal_weight": float(rets.loc[t_next, avail].mean()),
                     "risk_parity": float((iv * rets.loc[t_next, avail]).sum()), "sixty_forty": bench_6040,
                     "top_regime": max(d.regime_probs, key=d.regime_probs.get)})
        weights_log.append({"month": t_next.strftime("%Y-%m"), **{a: round(float(x), 4) for a, x in w.items()},
                            "Cash": round(d.cash, 4)})
        fc.append({"month": t_next, "p_g": d.p_growth_up["probability"], "base_g": d.p_growth_up["base_rate"],
                   "p_i": d.p_inflation_up["probability"], "base_i": d.p_inflation_up["base_rate"],
                   "probs": d.regime_probs})
        w_prev, ws_prev = w, ws
    if not rows:
        return {"available": False, "reason": "not enough history to run the model"}
    df = pd.DataFrame(rows).set_index("month")

    # Forecast skill vs realised direction (labels from the final factor history)
    last = decide(panel, rets, blocks, env_class, months[-1], p)
    skill = {}
    if last is not None:
        labels = realized_regimes(last.growth, last.inflation, p.momentum_months)
        dg = (last.growth - last.growth.shift(p.momentum_months)) > 0
        di = (last.inflation - last.inflation.shift(p.momentum_months)) > 0
        f = pd.DataFrame(fc).set_index("month")
        f = f[f.index.isin(dg.index)]
        if len(f) > 24:
            yg, yi = dg.reindex(f.index).astype(float), di.reindex(f.index).astype(float)
            def _brier(pcol, base, y):
                bs = float(((f[pcol] - y) ** 2).mean())
                ref = float(((f[base] - y) ** 2).mean())
                return {"brier": round(bs, 4), "brier_base_rate": round(ref, 4),
                        "skill": round(1 - bs / ref, 3) if ref > 0 else None,
                        "accuracy": round(float(((f[pcol] > 0.5) == (y > 0.5)).mean()), 3)}
            lab = labels.reindex(f.index)
            hit = np.mean([max(pr, key=pr.get) == l for pr, l in zip(f["probs"], lab) if isinstance(l, str)])
            skill = {"growth_direction": _brier("p_g", "base_g", yg),
                     "inflation_direction": _brier("p_i", "base_i", yi),
                     "top_regime_hit_rate": round(float(hit), 3), "months_scored": len(f)}

    curve = (1 + df[["model", "strategic", "sixty_forty", "risk_parity", "equal_weight"]].fillna(0)).cumprod()
    # Does the tactical tilt add value? Paired test on monthly return differences
    # (Sharpe-matched comparison would also be reasonable; this is the simple, transparent one).
    diff = (df["model"] - df["strategic"]).dropna()
    t_stat = float(diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff)))) if len(diff) > 12 and diff.std() > 0 else None
    tilt = {"mean_monthly_diff": round(float(diff.mean()), 5), "annualised_diff": round(float(diff.mean() * 12), 4),
            "t_stat": round(t_stat, 2) if t_stat is not None else None,
            "significant_5pct": bool(t_stat is not None and abs(t_stat) >= 1.96),
            "tracking_error": round(float(diff.std() * math.sqrt(12)), 4),
            "information_ratio": round(float(diff.mean() * 12 / (diff.std() * math.sqrt(12))), 2) if diff.std() > 0 else None}
    return {
        "available": True,
        "start": df.index[0].strftime("%Y-%m"), "end": df.index[-1].strftime("%Y-%m"),
        "stats": {"Tactical (net of costs)": _stats(df["model"]), "Strategic (net of costs)": _stats(df["strategic"]),
                  "60/40": _stats(df["sixty_forty"]),
                  "Risk parity (inverse vol)": _stats(df["risk_parity"]), "Equal weight": _stats(df["equal_weight"])},
        "tactical_vs_strategic": tilt,
        "avg_turnover_monthly": round(float(df["turnover"].mean()), 3),
        "avg_cash": round(float(df["cash"].mean()), 3),
        "forecast_skill": skill,
        "equity_curve": [{"month": m.strftime("%Y-%m"), **{k: round(float(v), 4) for k, v in row.items()}}
                         for m, row in curve.iterrows()],
        "weights": weights_log[-60:],
        "returns_are": "monthly excess returns over 3-month T-bills",
    }
