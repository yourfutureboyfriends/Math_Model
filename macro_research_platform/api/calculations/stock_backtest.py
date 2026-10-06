"""
Walk-forward backtest of the stock entry model (api/calculations/stock_timing.py).

Replays the live rules day by day on each stock's own history, no look-ahead:

  signal  — close of day i: price set-up ≥ BUY_SETUP and entry not extended (timing >
            EXTENDED_TIMING); label BUY when the home market is risk-on (index above its
            200-day average, VIX < 25), else BUY_SMALL. Same formulas as the live model.
  entry   — next day's open (i+1).
  stop    — entry − 2.5 × ATR(14) of the signal day; target — 2R (entry + 2 × risk), the
            live model's objective when there is no consensus target (no point-in-time
            consensus history exists, so the backtest always uses 2R).
  exit    — stop (a gap through it fills at the open), target, or a 63-day time stop at the
            close. When the stop and the target are both touched on one day the stop is
            assumed first (conservative). One trade per stock at a time.
  costs   — round-trip, by MSCI market class (commission + half-spread + impact).

Variants isolate what each rule contributes:
  model        — the live rules: BUY at full risk, BUY_SMALL at half risk
  regime_gate  — BUY only (skip BUY_SMALL)
  setup_only   — the set-up without the entry-timing filter
  control      — no signal: enter whenever flat, same stop/target/time exits — the
                 return of the exit rules alone on the same stocks and dates

Only the price components can be tested: there is no point-in-time history of analyst
ratings, targets, earnings surprises or quality metrics, so the backtest measures the
trend / momentum / 52-week-high set-up, the pullback entry and the regime gate.

Portfolio: each trade risks 0.5% of NAV to its stop (BUY_SMALL 0.25%), capped at 10% of
NAV per name and 100% gross; daily returns are local-currency (FX not included).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from api.calculations.stock_timing import BUY_SETUP, EXTENDED_TIMING, signal_frame

STOP_ATR = 2.5
TARGET_R = 2.0
MAX_HOLD = 63
WARMUP = 260
MIN_RISK = 0.005          # stop at least 0.5% below entry: a smaller ATR means stale or suspended prices
COST_BY_CLASS = {"Developed": 0.0010, "Emerging": 0.0025, "Frontier": 0.0060, "Standalone": 0.0060}
RISK_PER_TRADE = 0.005
MAX_POSITION = 0.10
MAX_GROSS = 1.0
VARIANTS = ("model", "regime_gate", "setup_only", "control")


@dataclass
class Trade:
    symbol: str
    variant: str
    label: str              # BUY / BUY_SMALL / CONTROL
    entry_i: int            # index into the stock's own arrays
    exit_i: int
    entry_date: str
    exit_date: str
    entry: float
    stop: float
    target: float
    exit: float
    reason: str             # stop / target / time
    setup: float
    timing: float
    cost: float
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def risk(self) -> float:
        return self.entry - self.stop

    @property
    def r(self) -> float:
        """R-multiple net of costs."""
        return (self.exit - self.entry - self.cost * self.entry) / self.risk

    @property
    def ret(self) -> float:
        return self.exit / self.entry - 1 - self.cost

    @property
    def days(self) -> int:
        return self.exit_i - self.entry_i + 1


# ── Data hygiene ─────────────────────────────────────────────────────────────
def clean_ohlc(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray):
    """Repair the usual free-data faults: missing O/H/L (filled from the close), H < L,
    O/C outside the H-L range, and one-day spikes that revert the next day (bad ticks)."""
    o, h, l, c = (np.array(x, dtype=float) for x in (o, h, l, c))
    for x in (o, h, l):
        bad = ~np.isfinite(x) | (x <= 0)
        x[bad] = c[bad]
    for i in range(1, c.size - 1):
        a, b, n = c[i - 1], c[i], c[i + 1]
        if a > 0 and n > 0 and (b / a > 1.8 or b / a < 0.45) and 0.8 < n / a < 1.25:
            c[i] = o[i] = h[i] = l[i] = a
    hi = np.maximum.reduce([h, l, o, c])
    lo = np.minimum.reduce([h, l, o, c])
    return o, hi, lo, c


# ── Trades ───────────────────────────────────────────────────────────────────
def _exit(o, h, l, c, start: int, stop: float, target: float, max_hold: int):
    """Walk forward from the entry day; returns (exit index, exit price, reason)."""
    last = min(c.size - 1, start + max_hold - 1)
    for j in range(start, last + 1):
        if j > start and o[j] <= stop:
            return j, o[j], "stop"
        if l[j] <= stop:
            return j, stop, "stop"
        if j > start and o[j] >= target:
            return j, o[j], "target"
        if h[j] >= target:
            return j, target, "target"
    return last, c[last], "time" if last == start + max_hold - 1 else "open"


def simulate(symbol: str, dates: Sequence[str], o, h, l, c, regime_ok: Optional[np.ndarray] = None,
             market_class: str = "Developed", variants: Iterable[str] = VARIANTS,
             control_every: int = 21, max_hold: int = MAX_HOLD) -> List[Trade]:
    """All trades for one stock under each variant. `regime_ok[i]` is the home-market regime
    on day i (True / False / NaN = unknown → treated as risk-on, as the live model does)."""
    o, h, l, c = clean_ohlc(o, h, l, c)
    n = c.size
    if n < WARMUP + 2:
        return []
    with np.errstate(divide="ignore", invalid="ignore"):
        f = signal_frame(c, h, l)
    setup, timing, atr = f["setup"].to_numpy(), f["timing"].to_numpy(), f["atr"].to_numpy()
    reg = np.ones(n, dtype=bool) if regime_ok is None else \
        np.where(np.isnan(regime_ok.astype(float)), True, regime_ok.astype(float) > 0.5)
    valid = np.isfinite(setup) & np.isfinite(timing) & np.isfinite(atr) & (atr > 0)
    valid[:WARMUP] = False
    strong = valid & (setup >= BUY_SETUP)
    entry_ok = timing > EXTENDED_TIMING
    signal = {
        "model": strong & entry_ok,
        "regime_gate": strong & entry_ok & reg,
        "setup_only": strong,
    }
    cost = COST_BY_CLASS.get(market_class, 0.0025)
    out: List[Trade] = []
    for v in variants:
        i = WARMUP
        last_entry = -10 ** 9
        while i < n - 1:
            if v == "control":
                fire = valid[i] and i - last_entry >= control_every
            else:
                fire = bool(signal[v][i])
            if not fire:
                i += 1
                continue
            e = i + 1
            entry = o[e]
            stop = entry - STOP_ATR * atr[i]
            if not (entry > 0 and stop > 0 and (entry - stop) / entry >= MIN_RISK):
                i += 1
                continue
            target = entry + TARGET_R * (entry - stop)
            j, px, why = _exit(o, h, l, c, e, stop, target, max_hold)
            if why == "open":                    # still running at the end of the data
                break
            label = "CONTROL" if v == "control" else ("BUY" if reg[i] else "BUY_SMALL")
            out.append(Trade(symbol, v, label, e, j, str(dates[e]), str(dates[j]), float(entry), float(stop),
                             float(target), float(px), why, float(setup[i]), float(timing[i]), cost,
                             {"market_class": market_class}))
            last_entry = e
            i = j                              # flat after the exit; the exit day's close can signal again
    return out


# ── Trade statistics ─────────────────────────────────────────────────────────
def trade_stats(trades: Sequence[Trade]) -> Dict[str, Any]:
    if not trades:
        return {"trades": 0}
    r = np.array([t.r for t in trades])
    ret = np.array([t.ret for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    pf = float(wins.sum() / -losses.sum()) if losses.size and losses.sum() < 0 else None
    reasons = {k: sum(1 for t in trades if t.reason == k) / len(trades) for k in ("target", "stop", "time")}
    return {
        "trades": int(r.size),
        "hit_rate": round(float((r > 0).mean()), 3),
        "avg_r": round(float(r.mean()), 3),
        "median_r": round(float(np.median(r)), 3),
        "t_stat": round(float(r.mean() / (r.std(ddof=1) / math.sqrt(r.size))), 2) if r.size > 2 and r.std() > 0 else None,
        "avg_return": round(float(ret.mean()), 4),
        "avg_win_r": round(float(wins.mean()), 3) if wins.size else None,
        "avg_loss_r": round(float(losses.mean()), 3) if losses.size else None,
        "profit_factor": round(pf, 2) if pf is not None else None,
        "avg_days": round(float(np.mean([t.days for t in trades])), 1),
        "exit_mix": {k: round(v, 3) for k, v in reasons.items()},
    }


def diff_test(a: Sequence[Trade], b: Sequence[Trade]) -> Optional[Dict[str, Any]]:
    """Welch t-test of mean R, a vs b. Trades overlap in time, so this overstates
    significance somewhat; the yearly breakdown is the robustness check."""
    ra, rb = np.array([t.r for t in a]), np.array([t.r for t in b])
    if ra.size < 10 or rb.size < 10:
        return None
    se = math.sqrt(ra.var(ddof=1) / ra.size + rb.var(ddof=1) / rb.size)
    d = float(ra.mean() - rb.mean())
    return {"diff_r": round(d, 3), "t_stat": round(d / se, 2) if se > 0 else None}


def group_stats(trades: Sequence[Trade], key) -> List[Dict[str, Any]]:
    groups: Dict[Any, List[Trade]] = {}
    for t in trades:
        groups.setdefault(key(t), []).append(t)
    rows = [{"group": g, **trade_stats(ts)} for g, ts in groups.items() if g is not None]
    return sorted(rows, key=lambda r: str(r["group"]))


def setup_bucket(t: Trade) -> str:
    s = t.setup
    return "0.35–0.50" if s < 0.5 else "0.50–0.70" if s < 0.7 else "≥ 0.70"


# ── Portfolio ────────────────────────────────────────────────────────────────
def portfolio(trades: Sequence[Trade], closes: Dict[str, np.ndarray], dates: Dict[str, Sequence[str]],
              calendar: Sequence[str], risk_per_trade: float = RISK_PER_TRADE,
              max_position: float = MAX_POSITION, max_gross: float = MAX_GROSS) -> Dict[str, Any]:
    """Daily NAV of trading every signal at fixed fractional risk. Trades are taken in
    entry-date order while gross exposure is below `max_gross` — on a crowded day the
    strongest set-ups first, as the live list ranks them (control trades in a fixed random
    order, so the control stays signal-free); a skipped trade is counted."""
    cal_idx = {d: k for k, d in enumerate(calendar)}
    T = len(calendar)
    ret = np.zeros(T)
    gross = np.zeros(T)
    active: List[tuple] = []          # (exit_date, weight)
    taken = skipped = 0
    import zlib

    def rank(t: Trade):
        tie = (zlib.crc32(f"{t.symbol}{t.entry_date}".encode()) / 2 ** 32) if t.variant == "control" else -t.setup
        return (t.entry_date, tie, t.symbol)
    for t in sorted(trades, key=rank):
        active = [(d, w) for d, w in active if d >= t.entry_date]
        risk = risk_per_trade * (0.5 if t.label == "BUY_SMALL" else 1.0)
        w = min(max_position, risk / (t.risk / t.entry))
        if sum(w0 for _, w0 in active) + w > max_gross + 1e-9:
            skipped += 1
            continue
        taken += 1
        active.append((t.exit_date, w))
        c, ds = closes[t.symbol], dates[t.symbol]
        for j in range(t.entry_i, t.exit_i + 1):
            k = cal_idx.get(str(ds[j]))
            if k is None:
                continue
            prev = t.entry if j == t.entry_i else c[j - 1]
            px = t.exit if j == t.exit_i else c[j]
            r = px / prev - 1
            if j == t.entry_i:
                r -= t.cost
            ret[k] += w * r
            gross[k] += w
    nav = np.cumprod(1 + ret)
    return {"ret": ret, "nav": nav, "gross": gross, "taken": taken, "skipped": skipped}


def span_years(calendar: Sequence[str]) -> float:
    from datetime import date
    d0, d1 = date.fromisoformat(str(calendar[0])[:10]), date.fromisoformat(str(calendar[-1])[:10])
    return max((d1 - d0).days / 365.25, 1 / 365.25)


def perf(ret: np.ndarray, calendar: Sequence[str], periods: Optional[float] = None) -> Dict[str, Any]:
    """CAGR, volatility, Sharpe (zero risk-free rate), max drawdown and calendar-year returns.
    The calendar is the union of many markets' trading days (~300 a year, not 252), so the
    annualisation uses the actual date span."""
    if ret.size < 2:
        return {}
    nav = np.cumprod(1 + ret)
    yrs = span_years(calendar) if periods is None else ret.size / periods
    periods = ret.size / yrs
    cagr = nav[-1] ** (1 / yrs) - 1 if nav[-1] > 0 else -1.0
    vol = float(ret.std(ddof=1) * math.sqrt(periods))
    peak = np.maximum.accumulate(nav)
    dd = nav / peak - 1
    years: Dict[str, float] = {}
    for y in sorted({d[:4] for d in calendar}):
        m = np.array([d[:4] == y for d in calendar])
        years[y] = round(float(np.prod(1 + ret[m]) - 1), 4)
    return {"cagr": round(float(cagr), 4), "vol": round(vol, 4),
            "sharpe": round(float(ret.mean() * periods / vol), 2) if vol > 0 else None,
            "max_drawdown": round(float(dd.min()), 4), "total_return": round(float(nav[-1] - 1), 4),
            "years": years}


def equal_weight(closes: Dict[str, np.ndarray], dates: Dict[str, Sequence[str]], calendar: Sequence[str],
                 start_after: int = WARMUP) -> np.ndarray:
    """Daily-rebalanced equal-weight return of every stock with data that day (after its
    warm-up) — the same universe the signals trade, so it shares any survivorship bias."""
    cal_idx = {d: k for k, d in enumerate(calendar)}
    s = np.zeros(len(calendar))
    n = np.zeros(len(calendar))
    for sym, c in closes.items():
        ds = dates[sym]
        for j in range(max(1, start_after), c.size):
            k = cal_idx.get(str(ds[j]))
            if k is not None and c[j - 1] > 0:
                r = c[j] / c[j - 1] - 1
                if abs(r) < 0.8:
                    s[k] += r
                    n[k] += 1
    return np.where(n > 0, s / np.maximum(n, 1), 0.0)


def downsample(calendar: Sequence[str], series: Dict[str, np.ndarray], step: int = 5) -> List[Dict[str, Any]]:
    """Weekly points for the chart (always keeps the last day)."""
    idx = list(range(0, len(calendar), step))
    if idx and idx[-1] != len(calendar) - 1:
        idx.append(len(calendar) - 1)
    return [{"date": calendar[k], **{name: round(float(v[k]), 4) for name, v in series.items()}} for k in idx]
