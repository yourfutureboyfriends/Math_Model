"""
Portfolio-level backtest of the auto (paper) book — the same daily cycle as
api/auto_trader.run, replayed over ~20 years on the global sample:

  1. exits on open positions (stop — a gap through it fills at the open —, target, time stop;
     stop first when both are touched in one bar), as in calculations.stock_backtest._exit;
  2. orders from the previous close fill at today's open (cancelled if it opens through the
     stop); size = risk_per_trade × risk scale × equity / risk, within name / gross caps;
  3. mark to market at the close;
  4. new signals at the close (set-up ≥ BUY_SETUP, entry not extended, home market risk-on,
     frontier excluded), strongest set-ups first, sector cap, open slots only.

Risk scale = Grossman-Zhou drawdown multiplier × volatility-target multiplier, each switchable
for ablation. A control book runs the same machinery on randomly chosen stocks (no signal).
Returns are local-currency, i.e. currency-hedged (FX not modelled).

All inputs are calendar-aligned T×N arrays; NaN = no session for that stock that day.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from api.calculations.stock_backtest import COST_BY_CLASS, MIN_RISK, STOP_ATR
from api.calculations.stock_timing import BUY_SETUP, EXTENDED_TIMING


@dataclass
class Rules:
    risk_per_trade: float = 0.005
    max_position: float = 0.10
    max_gross: float = 1.0
    max_positions: int = 15
    max_per_sector: int = 3
    max_drawdown: float = 0.15
    vol_target: float = 0.12
    target_r: float = 2.0
    max_hold: int = 63
    exclude_frontier: bool = True
    drawdown_control: bool = True
    vol_targeting: bool = True
    regime_gate: bool = True
    peak_window: Optional[int] = None     # drawdown measured from the rolling N-day peak (None = all-time)
    random_entries: bool = False          # control: no signal, random stocks …
    random_rate: float = 0.5              # … at this many new picks per day (set to the model's rate)
    seed: int = 7


@dataclass
class Panel:
    dates: List[str]
    symbols: List[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    setup: np.ndarray
    timing: np.ndarray
    atr: np.ndarray
    regime: np.ndarray                    # 1 risk-on, 0 risk-off, NaN unknown (treated as on)
    market_class: List[str]
    sector: List[str]
    country: List[str] = field(default_factory=list)


def drawdown_multiplier(equity: float, peak: float, max_dd: float) -> float:
    if peak <= 0 or max_dd <= 0:
        return 1.0
    return min(1.0, max(0.0, (equity / peak - (1 - max_dd)) / max_dd))


def vol_multiplier(equity_hist: Sequence[float], target: float, window: int = 20) -> float:
    e = np.asarray(equity_hist[-(window + 1):], dtype=float)
    if e.size < 11:
        return 1.0
    r = np.diff(e) / e[:-1]
    vol = float(r.std(ddof=1) * math.sqrt(252))
    return 1.0 if vol <= 0 else min(1.0, target / vol)


def run(p: Panel, rules: Rules, start: int = 260, capital: float = 1.0) -> Dict[str, Any]:
    T, N = p.close.shape
    rng = np.random.default_rng(rules.seed)
    cost_side = np.array([COST_BY_CLASS.get(c, 0.0025) / 2 for c in p.market_class])
    frontier = np.array([c == "Frontier" for c in p.market_class])
    sectors = list(p.sector)
    last_close = np.full(N, np.nan)
    cash = capital
    pos: Dict[int, Dict[str, float]] = {}          # stock index → position
    pending: Dict[int, Dict[str, float]] = {}
    equity_hist: List[float] = []
    trades: List[Dict[str, Any]] = []
    gross_hist, npos_hist, scale_hist = [], [], []
    peak = capital

    for t in range(start, T):
        has = np.isfinite(p.close[t])
        last_close = np.where(has, p.close[t], last_close)

        # 1. exits
        for i in list(pos):
            if not has[i]:
                continue
            q = pos[i]
            q["held"] += 1
            o, h, l, c = p.open[t, i], p.high[t, i], p.low[t, i], p.close[t, i]
            px = why = None
            if q["held"] > 1 and o <= q["stop"]:
                px, why = o, "stop"
            elif l <= q["stop"]:
                px, why = q["stop"], "stop"
            elif q["held"] > 1 and o >= q["target"]:
                px, why = o, "target"
            elif h >= q["target"]:
                px, why = q["target"], "target"
            elif q["held"] >= rules.max_hold:
                px, why = c, "time"
            if why:
                proceeds = q["shares"] * px
                cost = proceeds * cost_side[i]
                cash += proceeds - cost
                pnl = proceeds - cost - q["basis"]
                trades.append({"i": i, "entry_t": q["entry_t"], "exit_t": t, "reason": why, "pnl": pnl,
                               "r": pnl / (q["shares"] * q["risk"]), "setup": q["setup"], "ret": pnl / q["basis"]})
                del pos[i]

        # equity before fills (sizing base), multipliers from history up to yesterday
        mv = sum(q["shares"] * last_close[i] for i, q in pos.items())
        equity = cash + mv
        if rules.peak_window:
            peak = max([capital if len(equity_hist) < rules.peak_window else 0.0] + equity_hist[-rules.peak_window:])
        dd_m = drawdown_multiplier(equity, max(peak, equity), rules.max_drawdown) if rules.drawdown_control else 1.0
        vol_m = vol_multiplier(equity_hist + [equity], rules.vol_target) if rules.vol_targeting else 1.0
        scale = dd_m * vol_m

        # 2. fills at the open
        for i in list(pending):
            od = pending[i]
            if not has[i]:
                od["wait"] += 1
                if od["wait"] > 5:
                    del pending[i]
                continue
            del pending[i]
            o = p.open[t, i]
            if not np.isfinite(o) or o <= od["signal_stop"] or scale <= 0:
                continue
            risk = od["risk"]
            invested = sum(q["shares"] * last_close[k] for k, q in pos.items())
            by_risk = rules.risk_per_trade * scale * equity / risk
            by_name = rules.max_position * equity / o
            by_gross = max(0.0, rules.max_gross * equity - invested) / o
            shares = math.floor(min(by_risk, by_name, by_gross) * 1e6) / 1e6   # fractional (capital = 1)
            if shares <= 0:
                continue
            notional = shares * o
            cost = notional * cost_side[i]
            cash -= notional + cost
            q = {"shares": shares, "entry": o, "stop": o - risk, "target": o + rules.target_r * risk, "risk": risk,
                 "basis": notional + cost, "entry_t": t, "held": 1, "setup": od["setup"]}
            # same-session stop / target (no gap check on the entry bar)
            h, l, c = p.high[t, i], p.low[t, i], p.close[t, i]
            px = why = None
            if l <= q["stop"]:
                px, why = q["stop"], "stop"
            elif h >= q["target"]:
                px, why = q["target"], "target"
            if why:
                proceeds = shares * px
                xc = proceeds * cost_side[i]
                cash += proceeds - xc
                pnl = proceeds - xc - q["basis"]
                trades.append({"i": i, "entry_t": t, "exit_t": t, "reason": why, "pnl": pnl,
                               "r": pnl / (shares * risk), "setup": od["setup"], "ret": pnl / q["basis"]})
            else:
                pos[i] = q

        # 3. mark at the close
        mv = sum(q["shares"] * last_close[i] for i, q in pos.items())
        equity = cash + mv
        peak = max(peak, equity)
        equity_hist.append(equity)
        if rules.peak_window:
            peak = max(equity_hist[-rules.peak_window:])
        gross_hist.append(mv / equity if equity > 0 else 0.0)
        npos_hist.append(len(pos))
        scale_hist.append(scale)

        # 4. signals at the close → orders for the next open
        dd_now = drawdown_multiplier(equity, peak, rules.max_drawdown) if rules.drawdown_control else 1.0
        slots = rules.max_positions - len(pos) - len(pending)
        if slots <= 0 or dd_now <= 0:
            continue
        atr = p.atr[t]
        ok = has & np.isfinite(atr) & (atr > 0) & np.isfinite(p.setup[t]) & np.isfinite(p.timing[t])
        ok &= (STOP_ATR * atr) / np.where(has, p.close[t], np.inf) >= MIN_RISK
        if rules.exclude_frontier:
            ok &= ~frontier
        for i in list(pos) + list(pending):
            ok[i] = False
        if rules.random_entries:
            cand = np.flatnonzero(ok)
            rng.shuffle(cand)
            cand = cand[: min(int(slots), int(rng.poisson(rules.random_rate)))]
        else:
            sig = ok & (p.setup[t] >= BUY_SETUP) & (p.timing[t] > EXTENDED_TIMING)
            if rules.regime_gate:
                sig &= ~(p.regime[t] == 0)
            cand = np.flatnonzero(sig)
            cand = cand[np.argsort(-p.setup[t, cand])]
        counts: Dict[str, int] = {}
        for k in list(pos) + list(pending):
            counts[sectors[k]] = counts.get(sectors[k], 0) + 1
        for i in cand:
            if slots <= 0:
                break
            sec = sectors[i]
            if sec != "Unknown" and counts.get(sec, 0) >= rules.max_per_sector:
                continue
            risk = STOP_ATR * float(atr[i])
            pending[int(i)] = {"risk": risk, "signal_stop": float(p.close[t, i]) - risk,
                               "setup": float(p.setup[t, i]), "wait": 0}
            counts[sec] = counts.get(sec, 0) + 1
            slots -= 1

    eq = np.array(equity_hist)
    n_orders = len(trades) + len(pos)
    return {"equity": eq, "orders_per_day": n_orders / max(1, T - start), "dates": p.dates[start:], "trades": trades,
            "gross": np.array(gross_hist), "positions": np.array(npos_hist), "scale": np.array(scale_hist)}


# ── Statistics ───────────────────────────────────────────────────────────────
def perf(equity: np.ndarray, dates: Sequence[str]) -> Dict[str, Any]:
    from datetime import date
    r = np.diff(equity) / equity[:-1]
    yrs = max((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25, 1 / 365.25)
    per = r.size / yrs
    vol = float(r.std(ddof=1) * math.sqrt(per)) if r.size > 2 else 0.0
    cagr = float((equity[-1] / equity[0]) ** (1 / yrs) - 1)
    dd = equity / np.maximum.accumulate(equity) - 1
    downside = r[r < 0]
    sortino = float(r.mean() * per / (downside.std(ddof=1) * math.sqrt(per))) if downside.size > 2 else None
    years: Dict[str, float] = {}
    for y in sorted({d[:4] for d in dates[1:]}):
        m = np.array([d[:4] == y for d in dates[1:]])
        years[y] = round(float(np.prod(1 + r[m]) - 1), 4)
    return {"cagr": round(cagr, 4), "vol": round(vol, 4), "sharpe": round(float(r.mean() * per / vol), 3) if vol > 0 else None,
            "sortino": round(sortino, 3) if sortino else None, "max_drawdown": round(float(dd.min()), 4),
            "calmar": round(cagr / abs(float(dd.min())), 3) if dd.min() < 0 else None,
            "years": years, "periods_per_year": round(per, 1)}


def trade_stats(trades: Sequence[Dict[str, Any]], periods_per_year: float, years: float) -> Dict[str, Any]:
    if not trades:
        return {"trades": 0}
    r = np.array([t["r"] for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    return {"trades": int(r.size), "per_year": round(r.size / years, 1),
            "hit_rate": round(float((r > 0).mean()), 3), "avg_r": round(float(r.mean()), 3),
            "std_r": round(float(r.std(ddof=1)), 3) if r.size > 1 else None,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
            "avg_days": round(float(np.mean([t["exit_t"] - t["entry_t"] + 1 for t in trades])), 1),
            "exit_mix": {k: round(sum(1 for t in trades if t["reason"] == k) / len(trades), 3) for k in ("target", "stop", "time")}}


def deflated_sharpe(returns: np.ndarray, trial_sharpes: Sequence[float]) -> Dict[str, Any]:
    """Bailey & López de Prado (2014). Per-period Sharpe of `returns` against the expected
    maximum Sharpe of `len(trial_sharpes)` independent trials with their observed variance
    (False Strategy Theorem), adjusted for skewness and kurtosis. Returns the probability that
    the true Sharpe exceeds that benchmark (> 0.95 = significant after the search)."""
    from scipy.stats import kurtosis, norm, skew
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 30 or r.std(ddof=1) == 0:
        return {}
    sr = r.mean() / r.std(ddof=1)
    trials = np.asarray([x for x in trial_sharpes if x is not None and np.isfinite(x)], dtype=float)
    k = max(len(trials), 1)
    var_sr = float(trials.var(ddof=1)) if trials.size > 1 else 0.0
    g = 0.5772156649
    sr0 = math.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1 / k) + g * norm.ppf(1 - 1 / (k * math.e))) if k > 1 else 0.0
    sk, ku = float(skew(r)), float(kurtosis(r, fisher=False))
    denom = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
    psr0 = float(norm.cdf((sr - 0.0) * math.sqrt(n - 1) / denom))
    dsr = float(norm.cdf((sr - sr0) * math.sqrt(n - 1) / denom))
    return {"sharpe_per_period": round(float(sr), 5), "benchmark_sharpe_per_period": round(sr0, 5), "trials": k,
            "skew": round(sk, 3), "kurtosis": round(ku, 3), "psr_vs_zero": round(psr0, 4), "dsr": round(dsr, 4)}


def bootstrap_range(daily_returns: np.ndarray, horizon_days: int, n: int = 2000, block: int = 21,
                    seed: int = 11) -> Dict[str, float]:
    """Distribution of the cumulative return over `horizon_days` from the backtest's daily
    returns (stationary block bootstrap keeps volatility clustering) — the range live results
    should fall in if the strategy is unchanged."""
    r = np.asarray(daily_returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < block * 2 or horizon_days < 1:
        return {}
    rng = np.random.default_rng(seed)
    outs = np.empty(n)
    for k in range(n):
        acc, need = [], horizon_days
        while need > 0:
            s = int(rng.integers(0, r.size - block))
            take = min(block, need)
            acc.append(r[s:s + take])
            need -= take
        outs[k] = float(np.prod(1 + np.concatenate(acc)) - 1)
    return {f"p{q}": round(float(np.percentile(outs, q)), 4) for q in (5, 25, 50, 75, 95)}
