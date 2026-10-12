"""
Code Lab engine — one file, numpy + pandas only, so the *same* code runs on the server and in the
browser (Pyodide). A strategy is plain Python:

    UNIVERSE = ["SPY", "TLT", "GLD"]          # tickers (≤ UNIVERSE_LIMIT), one quote currency (USD)
    START = "2005-01-01"                      # optional
    PARAMS = {"lookback": [126, 252]}         # optional: grid for walk-forward optimisation
    HOLDOUT = "2023-01-01"                    # optional: data from here never takes part in selection

    def strategy(data, lookback=252):
        # data.close / open / high / low / volume: DataFrames (dates × tickers), adjusted prices
        # data.rf: daily T-bill rate (Series); data.vix: VIX close (Series)
        # return target weights (dates × tickers): +long / −short, fraction of NAV.
        # A row with values is a decision taken at that day's close and traded at the next observed
        # open; a row left blank (all NaN) means "no decision — hold and let positions drift".
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
Accounting: one self-financing account — units and cash, NAV = Σ units × mark + cash, costs settle
into cash. Fills only at observed opens of assets that traded; unfillable orders stay pending; stale
marks are flagged; ended listings settle at their last close. Returns are total returns (Yahoo
adjusted prices include dividends). Units and assumptions: COST_SCHEMA.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

ENGINE_VERSION = "2026.10-ledger.1"
UNIVERSE_LIMIT = 80                   # one capability limit, shared by the loader, the sandbox and the UI
LARGE_UNIVERSE_LIMIT = 1000           # TRADABLE_UNIVERSE strategies (server job, sandboxed) — one global cross-section
TRADING_DAYS = 252
COST_SCHEMA_VERSION = "2026.10"
COST_SCHEMA: Dict[str, Dict[str, str]] = {
    "capital": {"unit": "account currency (USD)", "meaning": "starting capital; impact depends on size"},
    "commission_bps": {"unit": "bp per side of traded notional", "meaning": "broker commission"},
    "spread_mult": {"unit": "multiplier (×), not bp", "meaning": "scales the modelled half-spread"},
    "impact_coef_bps": {"unit": "bp × √(% of 63-day dollar volume)", "meaning": "square-root market impact"},
    "sec_fee_bps": {"unit": "bp of sale notional", "meaning": "SEC Section 31 fee"},
    "borrow_fee": {"unit": "annual decimal rate on short market value", "meaning": "stock-borrow fee"},
    "financing_spread": {"unit": "annual decimal rate over the bill rate", "meaning": "margin interest on negative cash"},
    "cash_spread": {"unit": "annual decimal rate under the bill rate", "meaning": "positive cash earns bill − this (0 = full T-bill)"},
    "no_trade_band": {"unit": "fraction of NAV", "meaning": "skip adjustments smaller than this to positions that stay open (entries and exits always trade)"},
    "max_gross": {"unit": "multiple of NAV", "meaning": "cap on gross target exposure"},
    "delist_haircut": {"unit": "fraction", "meaning": "loss applied when a held listing ends (settled at last close × (1 − this))"},
}
DEFAULT_COSTS: Dict[str, float] = {
    "capital": 1_000_000.0,
    "commission_bps": 0.35,
    "spread_mult": 1.0,
    "impact_coef_bps": 11.21,
    "sec_fee_bps": 0.278,
    "borrow_fee": 0.003,
    "financing_spread": 0.010,
    "cash_spread": 0.0,
    "no_trade_band": 0.0025,
    "max_gross": 4.0,
    "delist_haircut": 0.0,
}


class Data:
    """What a strategy sees. All frames share one date index; prices are split/dividend adjusted
    (total return). `close` is the *valuation mark*: the last observed close, carried forward inside each
    listing's history; `observed` says which days really have a bar. `open` holds only observed opens —
    it is the execution price, and NaN means no fill is possible that day."""

    def __init__(self, close, open_, high, low, volume, rf=None, vix=None, observed=None, rf_known=None,
                 provenance: Optional[Dict[str, Any]] = None):
        self.close, self.high, self.low = close, high, low
        idx = close.index
        self.observed = (observed.reindex(index=idx, columns=close.columns).fillna(False).astype(bool)
                         if observed is not None else close.notna())
        self.open = open_.reindex(index=idx, columns=close.columns).where(lambda x: x > 0)
        self.volume = volume.reindex(index=idx, columns=close.columns)
        self.rf_known = (rf is not None) if rf_known is None else bool(rf_known)
        self.rf = rf.reindex(idx).ffill().fillna(0.0) if rf is not None else pd.Series(0.0, index=idx)
        self.vix = vix.reindex(idx).ffill() if vix is not None else pd.Series(np.nan, index=idx)
        self.tickers = list(close.columns)
        self.provenance = dict(provenance or {})

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
    """Decide once a month, on the first trading day observed in each month (knowable that day — no future
    rows needed), traded at the next open. Other rows are left blank (NaN) = no decision: hold and drift."""
    return _hold(weights, "M")


def hold_weekly(weights: pd.DataFrame) -> pd.DataFrame:
    """As hold_monthly, on the first trading day observed in each week."""
    return _hold(weights, "W")


def _hold(weights: pd.DataFrame, freq: str) -> pd.DataFrame:
    w = weights.copy()
    per = w.index.to_period(freq)
    first = np.r_[True, np.asarray(per[1:] != per[:-1])] if len(per) else np.zeros(0, bool)
    w.loc[~first] = np.nan
    return w


def decision_mask(weights: pd.DataFrame) -> np.ndarray:
    """Which rows are decisions. Rows left entirely blank (NaN) mean "no new decision"; any row with a value is
    a decision to rebalance to it — even if it equals the previous target. A frame with no blank rows is a
    decision every day."""
    blank = weights.isna().all(axis=1).to_numpy()
    return ~blank


def normalize_gross(weights: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
    blank = weights.isna().all(axis=1)
    g = weights.abs().sum(axis=1).replace(0, np.nan)
    out = weights.div(g, axis=0).mul(gross).fillna(0.0)
    out.loc[blank] = np.nan                                 # keep "no decision" rows blank
    return out


def vol_target(weights: pd.DataFrame, close: pd.DataFrame, target: float = 0.10, lookback: int = 63,
               max_leverage: float = 2.0) -> pd.DataFrame:
    """Scale the book so its trailing realised volatility hits `target` (no look-ahead). Volatility is measured
    on the positions actually held (the latest decision carried forward)."""
    r = close.pct_change(fill_method=None).fillna(0.0)
    held = weights.ffill().fillna(0.0)
    port = (held.shift(1).fillna(0.0) * r).sum(axis=1)
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
             start: Optional[str] = None, decisions: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Simulate target weights as one self-financing account.

    Ledger: holdings in units and a cash balance; NAV = Σ units × mark + cash every day. A decision row
    decided at the close of day t places orders filled at the observed OPEN of t+1, only where that open
    exists and the asset traded (volume > 0); orders that cannot fill stay pending until filled or
    replaced by the next decision. Trading costs, fees, borrow and interest settle into cash. Marks are the
    last observed close (stale days are counted, never treated as tradable). A position whose listing ends
    is settled at its last observed close × (1 − delist_haircut). Returns are NAV changes."""
    cfg = {**DEFAULT_COSTS, **(costs or {})}
    close = data.close
    idx, cols = close.index, list(close.columns)
    w = weights.reindex(index=idx, columns=cols).astype(float)
    D = decision_mask(w) if decisions is None else np.asarray(decisions, bool)
    W = w.fillna(0.0).to_numpy()
    g = np.abs(W).sum(axis=1)
    W = W * np.where(g > cfg["max_gross"], cfg["max_gross"] / np.where(g > 0, g, 1.0), 1.0)[:, None]
    M = close.to_numpy(float)
    OBS = data.observed.to_numpy(bool) & np.isfinite(M)
    O = data.open.to_numpy(float)
    V = np.nan_to_num(data.volume.to_numpy(float))
    hs = half_spread_bps(close, data.volume).to_numpy() * cfg["spread_mult"] / 1e4
    adv = dollar_volume(close, data.volume).to_numpy()
    rf = data.rf.to_numpy(float)
    T, N = M.shape
    last_obs = np.array([np.flatnonzero(OBS[:, j]).max() if OBS[:, j].any() else -1 for j in range(N)])
    first = int(np.searchsorted(idx.values, np.datetime64(pd.Timestamp(start)))) if start else 0
    first = max(first, 1)
    last_dec = np.where(D, np.arange(T), -1)
    last_dec = np.maximum.accumulate(last_dec)
    band, cap = cfg["no_trade_band"], cfg["capital"]
    units = np.zeros(N)
    cash = 1.0
    mark = np.where(OBS[first - 1], M[first - 1], np.nan)
    target: Optional[np.ndarray] = None
    pending = np.zeros(N, bool)
    nav_prev = 1.0
    keys = ("ret", "gross", "commission", "spread", "impact", "fees", "borrow", "financing", "turnover", "long", "short",
            "cash", "nav", "unfilled", "stale_held")
    out = {k: np.zeros(T) for k in keys}
    events: List[Dict[str, Any]] = []
    for t in range(first, T):
        # 1) the decision taken at yesterday's close becomes today's orders
        if D[t - 1] or (t == first and last_dec[t - 1] >= 0):
            target = W[t - 1] if D[t - 1] else W[last_dec[t - 1]]
            pending = np.ones(N, bool)
        # 2) listings that ended: settle at the last observed close (documented policy)
        ended = np.flatnonzero((units != 0) & (t > last_obs) & (last_obs >= 0))
        for j in ended:
            value = units[j] * M[last_obs[j], j] * (1 - cfg["delist_haircut"])
            cash += value
            events.append({"date": str(idx[t].date()), "ticker": cols[j], "event": "listing ended — settled at last close",
                           "value": round(float(value), 6)})
            units[j] = 0.0
            pending[j] = False
        # 3) the opening market: only observed opens of assets that traded are executable
        exe = np.isfinite(O[t]) & (O[t] > 0) & OBS[t] & (V[t] > 0)
        mark_open = np.where(exe, O[t], mark)
        held_val = np.where(units != 0, units * np.nan_to_num(mark_open), 0.0)
        nav_open = float(held_val.sum() + cash)
        comm = spr = imp = fee = turn = 0.0
        if nav_open <= 0:
            out["ret"][t] = -1.0
            events.append({"date": str(idx[t].date()), "ticker": None, "event": "insolvent: NAV ≤ 0, simulation stopped"})
            for k in keys:
                out[k][t + 1:] = np.nan
            break
        if target is not None and pending.any():
            px = np.where(exe, O[t], np.nan)
            dv = adv[t]
            okdv = np.isfinite(dv) & (dv > 0)

            def order(nav_eff):
                want = target * nav_eff / np.where(exe, O[t], 1.0)
                dl = np.where(pending & exe, want - units, 0.0)
                nt = np.abs(dl) * np.nan_to_num(px)
                # the band suppresses small *adjustments* to positions held and kept; opening a new position or
                # closing one always trades (otherwise a 700-name book of 0.14% positions could never be bought)
                sm = (nt <= band * nav_open) & (units != 0) & (target != 0)
                dl, nt = np.where(sm, 0.0, dl), np.where(sm, 0.0, nt)
                c_ = cfg["commission_bps"] / 1e4 * nt.sum()
                s_ = float((nt * np.nan_to_num(hs[t], nan=5e-4)).sum())
                fr = np.where(okdv, nt * cap / np.where(okdv, dv, 1.0), 0.0)
                i_ = float((nt * cfg["impact_coef_bps"] / 1e4 * np.sqrt(100 * fr)).sum())
                f_ = cfg["sec_fee_bps"] / 1e4 * float(nt[dl < 0].sum())
                return dl, nt, c_, s_, i_, f_
            # size orders against NAV *after* this rebalance's costs, so fees come out of what is bought rather
            # than leaving an unintended margin loan (fixed point; converges in a few steps for realistic costs)
            nav_eff = nav_open
            for _ in range(30):
                delta, notional, comm, spr, imp, fee = order(nav_eff)
                nxt = nav_open - (comm + spr + imp + fee)
                if abs(nxt - nav_eff) < 1e-13:
                    break
                nav_eff = nxt
            pending &= ~exe                                    # executable orders are done (filled or within band)
            if notional.any():
                units = units + delta
                cash -= float(np.nansum(delta * px)) + comm + spr + imp + fee
                turn = float(notional.sum() / nav_open)
            # orders still open: assets whose target differs from what is held and cannot trade today
            cur_w = np.where(units != 0, units * np.nan_to_num(mark_open), 0.0) / nav_open
            out["unfilled"][t] = float((pending & (np.abs(target - cur_w) > band)).sum())
        # 4) the close: observed closes update marks; others stay stale
        mark = np.where(OBS[t], M[t], mark)
        out["stale_held"][t] = float(((units != 0) & ~OBS[t]).sum())
        mv = np.where(units != 0, units * np.nan_to_num(mark), 0.0)
        short_mv = float(-mv[mv < 0].sum())
        # 5) one trading day of interest on cash and borrow on shorts
        rf_d = rf[t] if np.isfinite(rf[t]) else 0.0
        fin = cash * (rf_d - cfg["cash_spread"] / TRADING_DAYS) if cash >= 0 else cash * (rf_d + cfg["financing_spread"] / TRADING_DAYS)
        spread_part = (cash * cfg["financing_spread"] / TRADING_DAYS if cash < 0 else -cash * cfg["cash_spread"] / TRADING_DAYS)
        bor = short_mv * cfg["borrow_fee"] / TRADING_DAYS
        cash += fin - bor
        nav = float(mv.sum() + cash)
        trading = comm + spr + imp + fee
        out["ret"][t] = nav / nav_prev - 1
        out["gross"][t] = (nav + trading + bor - spread_part) / nav_prev - 1   # before costs, borrow and rate spreads
        for k, v in (("commission", comm), ("spread", spr), ("impact", imp), ("fees", fee), ("borrow", bor), ("financing", fin)):
            out[k][t] = v / nav_prev
        out["turnover"][t] = turn
        out["long"][t] = float(mv[mv > 0].sum() / nav) if nav > 0 else np.nan
        out["short"][t] = short_mv / nav if nav > 0 else np.nan
        out["cash"][t], out["nav"][t] = cash, nav
        nav_prev = nav
    sl = slice(first, T)
    res: Dict[str, Any] = {k: pd.Series(v[sl], index=idx[sl]).dropna() for k, v in out.items()}
    ld = int(last_dec[-1]) if len(last_dec) and last_dec[-1] >= 0 else None
    res["weights_last"] = ({c: round(float(x), 4) for c, x in zip(cols, W[ld]) if abs(x) > 1e-4} if ld is not None else {})
    navf = float(out["nav"][T - 1]) if T else 1.0
    held = np.where(units != 0, units * np.nan_to_num(mark), 0.0)
    res["holdings_last"] = {c: round(float(x / navf), 4) for c, x in zip(cols, held) if navf > 0 and abs(x / navf) > 1e-4}
    res["ledger"] = {"units": {c: float(u) for c, u in zip(cols, units) if u}, "cash": float(cash), "nav": navf,
                     "securities": float(held.sum()), "reconciles": bool(abs(held.sum() + cash - navf) < 1e-9)}
    res["events"] = events[-200:]
    res["execution"] = {"unfilled_order_days": int((out["unfilled"][sl] > 0).sum()),
                        "stale_position_days": int(out["stale_held"][sl].sum()), "listings_ended": len(events),
                        "rf_known": bool(data.rf_known)}
    return res


# ── Statistics (one definition, mirrored exactly by api/quant/robust.py) ────
def years_between(first: pd.Timestamp, last: pd.Timestamp) -> float:
    """Calendar years spanned by a return series (first to last return date), at least one day."""
    return max((pd.Timestamp(last) - pd.Timestamp(first)).days, 1) / 365.25


def metrics(ret: pd.Series, rf: Optional[pd.Series] = None) -> Dict[str, Optional[float]]:
    """Return statistics. Sharpe and Sortino use returns above the reference rate (`rf`, daily, decimal);
    std with ddof=1, annualised by √252. Max drawdown includes the starting capital. CAGR uses calendar years."""
    r = ret.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    yrs = years_between(r.index[0], r.index[-1])
    ex = r - (rf.reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    sd = float(ex.std(ddof=1))
    peak = np.maximum.accumulate(np.r_[1.0, eq.to_numpy()])[1:]
    dd = eq.to_numpy() / peak - 1
    down = ex[ex < 0]
    mdd = float(dd.min())
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if eq.iloc[-1] > 0 else -1.0
    return {"cagr": round(cagr, 4), "vol": round(float(r.std(ddof=1) * math.sqrt(TRADING_DAYS)), 4),
            "sharpe": round(float(ex.mean() / sd * math.sqrt(TRADING_DAYS)), 3) if sd > 0 else None,
            "sortino": round(float(ex.mean() / down.std(ddof=1) * math.sqrt(TRADING_DAYS)), 3) if len(down) > 5 and down.std(ddof=1) > 0 else None,
            "max_drawdown": round(mdd, 4),
            "calmar": round(cagr / abs(mdd), 3) if mdd < 0 else None,
            "log_growth": round(float(np.log1p(r.clip(lower=-0.999)).mean() * TRADING_DAYS), 4),
            "hit_rate": round(float((r > 0).mean()), 3), "years": round(yrs, 1),
            "total_return": round(float(eq.iloc[-1] - 1), 4),
            "cash_rate": round(float((r - ex).mean() * TRADING_DAYS), 4)}


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


def select_walk_forward(series: List[pd.Series], combos: List[Dict[str, Any]], warmup_years: int = 5,
                        objective: str = "log_growth", rf: Optional[pd.Series] = None) -> List[Dict[str, Any]]:
    """For each calendar year after the warm-up, the parameter set with the best `objective` on returns
    strictly before 1 January of that year. Standalone return paths are used only for this scoring (they
    depend only on data up to the scoring date); the account itself is simulated once, continuously."""
    idx = series[0].index
    years = sorted(set(idx.year))
    if not years:
        return []
    out = []
    for y in years:
        if y < years[0] + warmup_years:
            continue
        cut = pd.Timestamp(f"{y}-01-01")
        scores = []
        for s in series:
            m = metrics(s[s.index < cut], rf)
            v = m.get(objective)
            scores.append(v if v is not None else -1e9)
        b = int(np.argmax(scores))
        out.append({"year": y, "params": combos[b], "trailing": round(float(scores[b]), 4)})
    return out


def walk_forward(run: Callable[[Dict[str, Any]], pd.Series], params: Dict[str, Sequence[Any]],
                 warmup_years: int = 5, objective: str = "log_growth") -> Dict[str, Any]:
    """Selection only (kept for callers that combine return streams, not accounts)."""
    combos = grid(params)
    series = [run(p) for p in combos]
    chosen = select_walk_forward(series, combos, warmup_years, objective)
    return {"chosen": chosen, "combos": combos}


def _standing(W: pd.DataFrame, D: np.ndarray) -> pd.DataFrame:
    """The target in force on each day: the latest decision carried forward (zeros before the first)."""
    Wt = W.copy()
    Wt.loc[~np.asarray(D, bool)] = np.nan
    return Wt.ffill().fillna(0.0)


def continuous_walk_forward(weight_sets: List[pd.DataFrame], chosen: List[Dict[str, Any]], combos: List[Dict[str, Any]],
                            idx: pd.DatetimeIndex) -> tuple:
    """One target/decision schedule following the chosen parameters year by year. On the first trading day
    of a year whose choice differs from the last one, a decision to the new set's standing target is forced,
    so the account trades from what it holds to what the new set wants — and pays for it."""
    key = [repr(sorted(c.items())) for c in combos]
    cols = weight_sets[0].columns
    Wc = pd.DataFrame(np.nan, index=idx, columns=cols)
    Dc = np.zeros(len(idx), bool)
    prev = None
    switches = []
    for ch in chosen:
        j = key.index(repr(sorted(ch["params"].items())))
        Wj = weight_sets[j].reindex(index=idx, columns=cols)
        Dj = decision_mask(Wj)
        rows = np.flatnonzero(idx.year == ch["year"])
        if not len(rows):
            continue
        Wc.iloc[rows] = Wj.iloc[rows].to_numpy()
        Dc[rows] = Dj[rows]
        if prev != j:
            r0 = rows[0]
            Wc.iloc[r0] = _standing(Wj, Dj).iloc[r0].to_numpy()
            Dc[r0] = True
            if prev is not None:
                switches.append({"date": str(idx[r0].date()), "to": ch["params"]})
        prev = j
    return Wc, Dc, switches


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
    sharpe_ex = float(ex.mean() / ex.std(ddof=1) * math.sqrt(TRADING_DAYS)) if ex.std(ddof=1) > 0 else 0.0
    weak = False
    if kelly is None or kelly <= 0:
        rec = 0.0                                                # no positive excess return to lever
    else:
        rec = max(safe) if safe else min(leverage_grid)
        rec = min(rec, max(0.25, math.floor(kelly / 2 * 4) / 4))   # never above half-Kelly (estimation error)
        if sharpe_ex < 0.3:                                      # Kelly on a near-zero edge is mostly noise
            rec, weak = min(rec, 1.0), True
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
        "rule": (f"Largest leverage with P(drawdown > {dd_limit:.0%}) ≤ {dd_prob:.0%}, capped at {max_leverage}× and at half-Kelly"
                 + ("; capped at 1× because the excess-return Sharpe is below 0.3 — too weak an edge to lever." if weak else ".")),
        "sharpe_excess": round(sharpe_ex, 3),
    }


# ── Running user code ───────────────────────────────────────────────────────
def load_strategy(code: str, namespace: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute strategy source and return its UNIVERSE / START / PARAMS / HOLDOUT / strategy. (The server
    never calls this on user code outside the sandbox; the browser runs it in Pyodide.)"""
    import hashlib
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
    if not isinstance(uni, (list, tuple)) or not uni or len(uni) > UNIVERSE_LIMIT:
        raise ValueError(f"Set UNIVERSE to a list of 1–{UNIVERSE_LIMIT} tickers (the current capability limit).")
    holdout = ns.get("HOLDOUT")
    tradable = ns.get("TRADABLE_UNIVERSE")
    return {"strategy": fn, "tradable": str(tradable).upper() if tradable else None, "universe": [str(u).upper() for u in uni], "start": str(ns.get("START") or "2005-01-01")[:10],
            "params": ns.get("PARAMS") or {}, "benchmark": str(ns.get("BENCHMARK") or "SPY").upper(),
            "holdout": str(holdout)[:10] if holdout else None,
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16]}


def run_weights(fn: Callable, data: Data, params: Dict[str, Any]) -> pd.DataFrame:
    w = fn(data, **params)
    if isinstance(w, pd.Series):
        w = w.to_frame()
    if not isinstance(w, pd.DataFrame):
        raise ValueError("strategy() must return a DataFrame of weights (dates × tickers).")
    unknown = [c for c in w.columns if c not in data.close.columns]
    if unknown:
        raise ValueError(f"Weights for tickers not in UNIVERSE: {', '.join(map(str, unknown[:5]))}")
    if not w.index.equals(data.close.index):
        w = w.reindex(data.close.index)
    return w.replace([np.inf, -np.inf], np.nan)


def _data_hash(data: Data) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(np.round(np.nan_to_num(data.close.to_numpy(float)), 6)).tobytes())
    h.update(",".join(data.tickers).encode())
    h.update(str(data.close.index[0]).encode() + str(data.close.index[-1]).encode())
    return h.hexdigest()[:16]


def _segment(ret: pd.Series, rf: pd.Series, a: Optional[str], b: Optional[str]) -> Dict[str, Any]:
    s = ret
    if a:
        s = s[s.index >= pd.Timestamp(a)]
    if b:
        s = s[s.index < pd.Timestamp(b)]
    return metrics(s, rf)


def evaluate(fn: Callable, data: Data, params: Dict[str, Sequence[Any]], start: str,
             costs: Optional[Dict[str, float]] = None, benchmark: Optional[pd.Series] = None,
             holdout: Optional[str] = None, code_hash: Optional[str] = None) -> Dict[str, Any]:
    """Backtest as one account (walk-forward when PARAMS has several combinations). Also returns the
    universe-matched equal-weight baseline under the same costs, the benchmark, segment statistics for an
    untouched holdout (if HOLDOUT is set) and a provenance record."""
    combos = grid(params)
    if len(combos) > 48:
        raise ValueError(f"{len(combos)} parameter combinations — keep the grid to 48 or fewer.")
    weight_sets = [run_weights(fn, data, p) for p in combos]
    if len(combos) > 1:
        # holdout years never take part in selection
        sel_end = pd.Timestamp(holdout) if holdout else None
        standalone = []
        for Wp in weight_sets:
            r = backtest(Wp, data, costs, start)["ret"]
            standalone.append(r[r.index < sel_end] if sel_end is not None else r)
        chosen = select_walk_forward(standalone, combos, rf=data.rf)
        if holdout:                                            # keep the last pre-holdout choice through the holdout
            last = chosen[-1] if chosen else None
            for y in sorted(set(data.close.index.year)):
                if pd.Timestamp(f"{y}-01-01") >= sel_end and last and all(c["year"] != y for c in chosen):
                    chosen.append({"year": y, "params": last["params"], "trailing": None})
        if not chosen:
            raise ValueError("Not enough history for walk-forward selection (needs more than the 5-year warm-up).")
        Wc, Dc, switches = continuous_walk_forward(weight_sets, chosen, combos, data.close.index)
        oos_start = str(pd.Timestamp(f"{chosen[0]['year']}-01-01").date())
        res = backtest(Wc, data, costs, oos_start, decisions=Dc)
        full_ins = [metrics(backtest(Wp, data, costs, oos_start)["ret"], data.rf) for Wp in weight_sets]
        ins_obj = [f.get("log_growth") if f.get("log_growth") is not None else -1e9 for f in full_ins]
        b = int(np.argmax(ins_obj))
        opt = {"walk_forward": True, "chosen": chosen, "switches": switches, "oos_start": oos_start,
               "in_sample_best": {"params": combos[b], **full_ins[b]},
               "grid": [{"params": c, **f} for c, f in zip(combos, full_ins)],
               "note": "One continuous account: switching parameter sets trades from current holdings to the new "
                       "targets and pays those costs."}
    else:
        res = backtest(weight_sets[0], data, costs, start)
        opt = {"walk_forward": False, "params": combos[0]}
    ret = res["ret"]
    first_day = str(ret.index[0].date()) if len(ret) else start
    # universe-matched baseline: equal weight of every listed name, rebalanced monthly, same costs and start
    listed = data.observed.astype(float).where(data.observed)
    ew = hold_monthly(listed.div(listed.sum(axis=1), axis=0).fillna(0.0))
    base = backtest(ew, data, costs, first_day)["ret"]
    out = {"metrics": metrics(ret, data.rf), "metrics_gross": metrics(res["gross"], data.rf), "costs": cost_summary(res),
           "optimisation": opt, "weights_last": res["weights_last"], "holdings_last": res["holdings_last"],
           "ledger": res["ledger"], "execution": res["execution"], "events": res["events"][-50:],
           "baseline_equal_weight": metrics(base.reindex(ret.index).fillna(0.0), data.rf),
           "dates": [d.strftime("%Y-%m-%d") for d in ret.index], "returns": [round(float(x), 8) for x in ret.values],
           "gross": [round(float(x), 8) for x in res["gross"].reindex(ret.index).fillna(0).values],
           "baseline_returns": [round(float(x), 8) for x in base.reindex(ret.index).fillna(0).values]}
    if benchmark is not None:
        bm = benchmark.reindex(ret.index).pct_change(fill_method=None).fillna(0.0)
        out["benchmark"] = [round(float(x), 8) for x in bm.values]
        out["benchmark_metrics"] = metrics(bm, data.rf)
        out["benchmark_definition"] = ("frictionless total return (adjusted close), 100% invested from the first "
                                       "record day; no costs, no cash")
    if holdout:
        out["holdout"] = {"start": holdout, "in_sample": _segment(ret, data.rf, None, holdout),
                          "holdout": _segment(ret, data.rf, holdout, None),
                          "baseline_holdout": _segment(base.reindex(ret.index).fillna(0.0), data.rf, holdout, None)}
    out["provenance"] = {"engine_version": ENGINE_VERSION, "cost_schema_version": COST_SCHEMA_VERSION,
                         "costs": {**DEFAULT_COSTS, **(costs or {})}, "params": params, "universe": data.tickers,
                         "data_first": str(data.close.index[0].date()), "data_last": str(data.close.index[-1].date()),
                         "data_hash": _data_hash(data), "code_hash": code_hash, "rf_known": data.rf_known,
                         "record_type": ("walk-forward (selection out-of-sample)" if opt["walk_forward"] else
                                         "exploratory backtest (single specification, full history)"),
                         **data.provenance}
    return out
