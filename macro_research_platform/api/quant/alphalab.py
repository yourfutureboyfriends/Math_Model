"""
Stock Signal Lab — which stock-level signals actually predicted returns in the S&P 500, a composite of the ones
that work, and today's ranked ideas.

Every month-end since 2014, for the stocks that were index members at the time (point-in-time membership, removed
names included where prices exist), seven documented signals are scored and compared with the next month's total
return:

  momentum      12-month return skipping the last month (Jegadeesh & Titman 1993)
  reversal      minus the last month's return (Jegadeesh 1990; short-term overreaction)
  low_vol       minus 12-month daily volatility (Ang, Hodrick, Xing & Zhang 2006; Frazzini & Pedersen)
  value         trailing earnings ÷ price (Basu 1977; Fama & French)
  profitability gross profit ÷ total assets (Novy-Marx 2013)
  investment    minus 1-year total-asset growth (Cooper, Gulen & Schill 2008; Fama–French CMA)
  earnings      change in trailing EPS at the latest filing ÷ price, for 90 days after it — post-earnings drift
                (Bernard & Thomas 1989)

Fundamentals are SEC figures as first filed, usable from the day after filing, restated for later stock splits so
they match split-adjusted prices. Each signal's rank IC (Spearman correlation with next month's return), its
t-statistic, hit rate, decay over 1–12 months, and top-minus-bottom quintile returns are reported. The composite
weights each signal by its own trailing 36-month mean IC, only when positive, using only months already realised —
so the composite's record is out-of-sample. Costs: 10 bp per unit of turnover each way for these large caps.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "alphalab"
TTL = 20 * 3600
START = "2014-01-01"
COST_BP = 10.0
SIGNALS = {
    "momentum": "Momentum (12-1 month)", "reversal": "Short-term reversal (1 month)", "low_vol": "Low volatility",
    "value": "Value (earnings yield)", "profitability": "Profitability (gross profit / assets)",
    "investment": "Low asset growth", "earnings": "Earnings surprise (post-earnings drift)",
    "high52": "Near 52-week high", "resid_mom": "Residual momentum", "industry_mom": "Industry momentum",
}
# Pre-registered composite: the combination the literature argues for (value + quality + momentum + 52-week high),
# equal weights, fixed before looking at this sample — nothing in it is fitted here.
FIXED = ("value", "profitability", "momentum", "high52")


# ── data ─────────────────────────────────────────────────────────────────────
def _splits(tickers: List[str]) -> Dict[str, pd.Series]:
    """Stock splits per ticker (date → ratio) from Yahoo, cached a week in one file."""
    path = CACHE / "splits.json"
    try:
        if time.time() - path.stat().st_mtime < 7 * 86400:
            raw = json.loads(path.read_text())
            if set(tickers) <= set(raw):
                return {t: pd.Series({pd.Timestamp(d): r for d, r in v.items()}, dtype=float) for t, v in raw.items()}
    except Exception:
        pass
    import yfinance as yf
    out: Dict[str, Dict[str, float]] = {}
    for i in range(0, len(tickers), 150):
        part = tickers[i:i + 150]
        try:
            df = yf.download(part, period="max", interval="1d", auto_adjust=False, actions=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as e:                                  # noqa: BLE001 — a failed batch = no splits known
            logger.warning("[alphalab] splits batch %s: %s", i, e)
            continue
        for t in part:
            try:
                sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                sp = sub["Stock Splits"].dropna()
                sp = sp[sp > 0]
                out[t] = {str(pd.Timestamp(d).tz_localize(None).date()): float(r) for d, r in sp.items() if r != 1}
            except Exception:                                   # noqa: BLE001
                out[t] = {}
        time.sleep(0.5)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return {t: pd.Series({pd.Timestamp(d): r for d, r in v.items()}, dtype=float) for t, v in out.items()}


def _factor_after(splits: pd.Series, when: pd.Timestamp) -> float:
    """Product of split ratios after a date: as-filed per-share figures ÷ this = today's share basis."""
    if splits is None or splits.empty:
        return 1.0
    s = splits[splits.index > when]
    return float(np.prod(s.values)) if len(s) else 1.0


def _events(tickers: List[str]) -> Dict[str, Dict[str, List[Tuple[pd.Timestamp, float]]]]:
    """Point-in-time SEC events per ticker: {field: [(usable date = filed + 1 day, value)]}."""
    from api.providers import sec_edgar
    out = {}
    for t in tickers:
        try:
            ev = sec_edgar.pit_events(t)
        except Exception as e:                                  # noqa: BLE001 — a ticker without filings is skipped
            logger.debug("[alphalab] %s: %s", t, e)
            continue
        out[t] = {k: [(pd.Timestamp(d) + pd.Timedelta(days=1), float(v)) for d, v in vals] for k, vals in ev.items()}
    return out


def _asof(ev: List[Tuple[pd.Timestamp, float]], dates: pd.DatetimeIndex, max_age: int = 400) -> Tuple[np.ndarray, np.ndarray]:
    """Latest value usable on each date and the date it became usable (NaN / NaT when none or older than max_age)."""
    vals = np.full(len(dates), np.nan)
    when = np.full(len(dates), np.datetime64("NaT"), dtype="datetime64[ns]")
    if not ev:
        return vals, when
    ds = pd.DatetimeIndex([d for d, _ in ev])
    vs = np.array([v for _, v in ev])
    pos = ds.searchsorted(dates, side="right") - 1
    ok = pos >= 0
    vals[ok] = vs[pos[ok]]
    when[ok] = ds.values[pos[ok]]
    age = (dates.values - when).astype("timedelta64[D]").astype(float)
    stale = ~(age <= max_age)
    vals[stale] = np.nan
    return vals, when


def build_signals(start: str = START) -> Dict[str, Any]:
    """Month-end signal panels, next-month returns and membership for the point-in-time S&P 500 universe."""
    from api.quant import data as qdata, membership
    tickers, info = membership.universe_since(start)
    px, missing = qdata.panel(tickers, start=(pd.Timestamp(start) - pd.DateOffset(months=14)).strftime("%Y-%m-%d"))
    close = px["close"]
    tickers = list(close.columns)
    daily_ret = close.pct_change(fill_method=None)
    me = close.resample("ME").last().index
    me = me[me >= pd.Timestamp(start)]
    me = pd.DatetimeIndex([close.index[close.index <= d][-1] for d in me])        # last trading day of each month
    loc = close.index.get_indexer(me)

    def back(n):
        return close.iloc[np.maximum(loc - n, 0)].to_numpy()
    c0 = close.iloc[loc].to_numpy()
    sig: Dict[str, np.ndarray] = {}
    sig["momentum"] = back(21) / back(252) - 1
    sig["reversal"] = -(c0 / back(21) - 1)
    vol = daily_ret.rolling(252, min_periods=200).std().iloc[loc].to_numpy()
    sig["low_vol"] = -vol
    hi = close.rolling(252, min_periods=200).max().iloc[loc].to_numpy()
    sig["high52"] = c0 / hi                                                  # George & Hwang (2004)
    # residual momentum: 12-1 month return net of beta × the equal-weight market's (Blitz, Huij & Martens 2011)
    mkt = daily_ret.mean(axis=1)
    cov = daily_ret.rolling(252, min_periods=200).cov(mkt)
    beta = (cov.div(mkt.rolling(252, min_periods=200).var(), axis=0)).iloc[loc].to_numpy()
    mcum = (1 + mkt).cumprod()
    m_mom = (mcum.iloc[np.maximum(loc - 21, 0)].to_numpy() / mcum.iloc[np.maximum(loc - 252, 0)].to_numpy() - 1)[:, None]
    sig["resid_mom"] = sig["momentum"] - beta * m_mom
    # forward 1, 3, 6, 12-month returns (for IC decay); the 1-month one is the target
    fwd = {}
    for h in (1, 3, 6, 12):
        nxt = np.minimum(np.arange(len(me)) + h, len(me) - 1)
        f = close.iloc[loc[nxt]].to_numpy() / c0 - 1
        f[np.arange(len(me)) + h >= len(me)] = np.nan
        fwd[h] = f
    # fundamentals, point in time, on today's share basis
    ev = _events(tickers)
    splits = _splits(tickers)
    shape = (len(me), len(tickers))
    eps, eps_prev_val, eps_when = np.full(shape, np.nan), np.full(shape, np.nan), np.full(shape, np.datetime64("NaT"), dtype="datetime64[ns]")
    gp, ta, ta_1y = np.full(shape, np.nan), np.full(shape, np.nan), np.full(shape, np.nan)
    for j, t in enumerate(tickers):
        e = ev.get(t) or {}
        sp = splits.get(t)
        adj = lambda pts: [(d, v / _factor_after(sp, d)) for d, v in pts]
        if e.get("eps_ttm"):
            pts = adj(e["eps_ttm"])
            eps[:, j], eps_when[:, j] = _asof(pts, me)
            # the trailing EPS before the latest filing (for the surprise)
            prev = [(pts[k][0], pts[k - 1][1]) for k in range(1, len(pts))]
            eps_prev_val[:, j], _ = _asof(prev, me)
        if e.get("gross_profit_ttm"):
            gp[:, j], _ = _asof(e["gross_profit_ttm"], me)
        if e.get("total_assets"):
            ta[:, j], _ = _asof(e["total_assets"], me)
            ta_1y[:, j], _ = _asof(e["total_assets"], me - pd.DateOffset(years=1), max_age=500)
    sig["value"] = eps / c0
    sig["profitability"] = np.where(ta > 0, gp / ta, np.nan)
    sig["investment"] = np.where(ta_1y > 0, -(ta / ta_1y - 1), np.nan)
    fresh = (me.values[:, None] - eps_when).astype("timedelta64[D]").astype(float) <= 90
    sig["earnings"] = np.where(fresh, (eps - eps_prev_val) / c0, np.nan)
    # industry momentum: the median 12-1 momentum of the stock's sector (Moskowitz & Grinblatt 1999); sector from
    # today's index file, so names that have left the index have none
    try:
        from api.marketdata import funds
        sector = {str(m["symbol"]).replace(".", "-"): m.get("sector") for m in funds.index_members("SPX")["members"]}
    except Exception:                                           # noqa: BLE001
        sector = {}
    secs = np.array([sector.get(t) for t in tickers], dtype=object)
    ind = np.full(shape, np.nan)
    for sname in {x for x in secs if x}:
        cols = secs == sname
        med = np.nanmedian(np.where(np.isfinite(sig["momentum"][:, cols]), sig["momentum"][:, cols], np.nan), axis=1)
        ind[:, cols] = med[:, None]
    sig["industry_mom"] = ind
    members = membership.members_frame(me, tickers).to_numpy()
    for k in sig:
        sig[k] = np.where(members & np.isfinite(sig[k]), sig[k], np.nan)
    return {"dates": me, "tickers": tickers, "signals": sig, "fwd": fwd, "members": members, "close": c0,
            "vol": vol, "missing_prices": missing, "membership_info": {k: v for k, v in info.items() if k != "unparseable"}}


# ── evaluation ───────────────────────────────────────────────────────────────
def _rank(a: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile ranks per row (NaN kept)."""
    return pd.DataFrame(a).rank(axis=1, pct=True).to_numpy()


def _ic_series(s: np.ndarray, f: np.ndarray) -> np.ndarray:
    rs, rf = _rank(np.where(np.isfinite(f), s, np.nan)), _rank(np.where(np.isfinite(s), f, np.nan))
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        m = np.isfinite(rs[i]) & np.isfinite(rf[i])
        if m.sum() >= 50:
            out[i] = np.corrcoef(rs[i][m], rf[i][m])[0, 1]
    return out


def _quintiles(s: np.ndarray, f: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Equal-weight next-month return of each quintile per month, and the top quintile's membership (for turnover)."""
    r = _rank(s)
    q = np.full((len(s), 5), np.nan)
    top = np.zeros(s.shape, dtype=bool)
    for i in range(len(s)):
        m = np.isfinite(r[i]) & np.isfinite(f[i])
        if m.sum() < 50:
            continue
        bucket = np.minimum((r[i][m] * 5).astype(int), 4)
        for b in range(5):
            q[i, b] = f[i][m][bucket == b].mean()
        top[i] = np.isfinite(r[i]) & (r[i] > 0.8)
    turnover = np.full(len(s), np.nan)
    for i in range(1, len(s)):
        a, b = top[i - 1], top[i]
        if a.sum() and b.sum():
            turnover[i] = 1 - (a & b).sum() / max(b.sum(), 1)          # share of the book replaced
    return q, top, turnover


def _stats(monthly: pd.Series) -> Dict[str, Optional[float]]:
    x = monthly.dropna()
    if len(x) < 12:
        return {"ann_return": None, "ann_vol": None, "sharpe": None, "max_drawdown": None, "months": len(x)}
    curve = (1 + x).cumprod()
    return {"ann_return": float(curve.iloc[-1] ** (12 / len(x)) - 1), "ann_vol": float(x.std() * math.sqrt(12)),
            "sharpe": float(x.mean() / x.std() * math.sqrt(12)) if x.std() > 0 else None,
            "max_drawdown": float((curve / curve.cummax() - 1).min()), "months": int(len(x))}


def _evaluate(name: str, s: np.ndarray, d: Dict[str, Any]) -> Dict[str, Any]:
    dates = d["dates"]
    ic = _ic_series(s, d["fwd"][1])
    ics = pd.Series(ic, index=dates).dropna()
    q, top, turn = _quintiles(s, d["fwd"][1])
    ls = pd.Series(q[:, 4] - q[:, 0], index=dates)
    long_only = pd.Series(q[:, 4], index=dates) - pd.Series(np.nan_to_num(turn), index=dates) * 2 * COST_BP / 1e4
    universe = pd.Series(np.nanmean(np.where(d["members"], d["fwd"][1], np.nan), axis=1), index=dates)
    decay = {}
    for h in (1, 3, 6, 12):
        x = pd.Series(_ic_series(s, d["fwd"][h]), index=dates).dropna()
        decay[f"{h}m"] = float(x.mean()) if len(x) else None
    by_year = ics.groupby(ics.index.year).mean()
    return {
        "id": name, "name": SIGNALS.get(name, name), "months": int(len(ics)),
        "ic_mean": float(ics.mean()) if len(ics) else None,
        "ic_t": float(ics.mean() / ics.std() * math.sqrt(len(ics))) if len(ics) > 2 and ics.std() > 0 else None,
        "ic_hit_rate": float((ics > 0).mean()) if len(ics) else None,
        "ic_last_36m": float(ics.iloc[-36:].mean()) if len(ics) >= 12 else None,
        "ic_by_year": {int(y): round(float(v), 4) for y, v in by_year.items()},
        "decay": decay,
        "quintile_returns_ann": [float(np.nanmean(q[:, b]) * 12) if np.isfinite(q[:, b]).any() else None for b in range(5)],
        "long_short": _stats(ls), "top_quintile_net": _stats(long_only), "universe": _stats(universe),
        "excess_vs_universe_ann": float(((long_only - universe).dropna().mean()) * 12) if long_only.notna().any() else None,
        "turnover_monthly": float(np.nanmean(turn)) if np.isfinite(turn).any() else None,
        "_ic": ic, "_ls": ls, "_top": long_only, "_universe": universe,
    }


def _zscore(a: np.ndarray) -> np.ndarray:
    """Cross-sectional z-scores of ranks (robust to outliers)."""
    r = _rank(a)
    return (r - 0.5) * math.sqrt(12)


def _composite(d: Dict[str, Any], evals: Dict[str, Dict[str, Any]], window: int = 36) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """Each month, weight each signal by its trailing mean IC over realised months (positive only) — no look-ahead."""
    names = list(evals)
    ic = np.vstack([evals[n]["_ic"] for n in names]).T                    # months × signals
    z = {n: _zscore(d["signals"][n]) for n in names}
    comp = np.full(d["signals"][names[0]].shape, np.nan)
    weights_log = []
    for i in range(len(d["dates"])):
        past = ic[max(0, i - window):max(0, i - 1)]                       # month i-1's IC needs month i's return: exclude
        if len(past) < 12:
            continue
        mu = np.nan_to_num(np.nanmean(past, axis=0))
        sd = np.nanstd(past, axis=0)
        n_ = np.sum(np.isfinite(past), axis=0)
        t_ = np.where(sd > 0, mu / sd * np.sqrt(np.maximum(n_, 1)), 0)
        w = np.where(t_ > 1.0, mu, 0.0)                                  # only signals that have earned it lately
        if w.sum() <= 0:
            continue
        w = w / w.sum()
        stack = np.stack([np.nan_to_num(z[n][i], nan=0.0) * w[k] for k, n in enumerate(names)])
        avail = np.stack([np.isfinite(z[n][i]) * w[k] for k, n in enumerate(names)]).sum(axis=0)
        comp[i] = np.where(avail >= 0.5, stack.sum(axis=0) / np.where(avail > 0, avail, 1), np.nan)
        weights_log.append({"month": d["dates"][i].strftime("%Y-%m"), **{n: round(float(w[k]), 3) for k, n in enumerate(names)}})
    return comp, weights_log


def _borrow_fees(symbols: List[str]) -> Dict[str, Optional[float]]:
    try:
        from api.marketdata.bbgextra import borrow_table
        t = borrow_table("usa.txt")["rows"]
        return {s: (t.get(s.replace("-", " ")) or t.get(s.replace("-", ".")) or {}).get("fee") for s in symbols}
    except Exception:                                           # noqa: BLE001
        return {}


def _edge_verdict(e: Dict[str, Any]) -> Dict[str, Any]:
    """A plain verdict on whether the ideas list carries a measurable edge — so a weak result is never dressed up."""
    t, ex = e.get("ic_t"), e.get("excess_vs_universe_ann")
    if t is not None and t >= 2 and (ex or 0) > 0:
        return {"level": "significant", "text": f"The composite's rank IC is statistically significant (t = {t:.1f}) and its top fifth beat the index by {ex:.1%} a year after costs."}
    if t is not None and t >= 1 and (ex or 0) > 0:
        return {"level": "weak", "text": f"Some evidence (t = {t:.1f}, {ex:+.1%} a year vs the index) but not statistically significant — size small or use as a tie-breaker."}
    return {"level": "none", "text": "No reliable edge in this universe over this period: treat the list as a screen for further research, not a trading signal."}


def run(start: str = START) -> Dict[str, Any]:
    t0 = time.time()
    d = build_signals(start)
    evals = {n: _evaluate(n, d["signals"][n], d) for n in SIGNALS}
    comp_adaptive, wlog = _composite(d, evals)
    ae = _evaluate("adaptive", comp_adaptive, d)
    ae["name"] = "Adaptive composite (signals with trailing t > 1)"
    z = [_zscore(d["signals"][n]) for n in FIXED]
    zs = np.stack(z)
    cnt = np.isfinite(zs).sum(axis=0)
    comp_fixed = np.where(cnt >= 3, np.nansum(zs, axis=0) / np.maximum(cnt, 1), np.nan)
    fe = _evaluate("fixed", comp_fixed, d)
    fe["name"] = "Pre-registered composite (value + profitability + momentum + 52w high)"
    # the composite used for today's ideas: whichever has the better out-of-sample rank IC t-statistic
    ce, comp = (fe, comp_fixed) if (fe["ic_t"] or -9) >= (ae["ic_t"] or -9) else (ae, comp_adaptive)
    # today's ideas: the latest month with signals, ranked by the composite
    i = len(d["dates"]) - 1
    while i > 0 and not np.isfinite(comp[i]).any():
        i -= 1
    tickers = d["tickers"]
    zrow = {n: _zscore(d["signals"][n])[i] for n in SIGNALS}
    order = [j for j in np.argsort(-np.nan_to_num(comp[i], nan=-9e9)) if np.isfinite(comp[i][j])]
    from api.marketdata import funds
    try:
        meta = {str(m["symbol"]).replace(".", "-"): m for m in funds.index_members("SPX")["members"]}
    except Exception:                                           # noqa: BLE001
        meta = {}

    def idea(j, side):
        v = d["vol"][i][j] * math.sqrt(252) if np.isfinite(d["vol"][i][j]) else None
        return {"symbol": tickers[j], "name": (meta.get(tickers[j]) or {}).get("name"), "sector": (meta.get(tickers[j]) or {}).get("sector"),
                "score": round(float(comp[i][j]), 3), "side": side, "vol": round(v, 4) if v else None,
                "signals": {n: (round(float(zrow[n][j]), 2) if np.isfinite(zrow[n][j]) else None) for n in SIGNALS}}
    longs = [idea(j, "long") for j in order[:25]]
    shorts = [idea(j, "short") for j in order[::-1][:25]]
    fees = _borrow_fees([x["symbol"] for x in shorts])
    for x in shorts:
        x["borrow_fee"] = fees.get(x["symbol"])
    # risk-scaled sizing: inverse volatility within each book, capped at 8% of the book
    for book in (longs, shorts):
        inv = np.array([1 / x["vol"] if x["vol"] else 0 for x in book])
        w = inv / inv.sum() if inv.sum() else inv
        w = np.minimum(w, 0.08)
        w = w / w.sum() if w.sum() else w
        for x, wt in zip(book, w):
            x["weight"] = round(float(wt), 4)
    curves = pd.DataFrame({"composite_top_quintile": ce["_top"], "universe_equal_weight": ce["_universe"],
                           "composite_long_short": ce["_ls"]}).dropna(how="all")
    curve_rows = [{"month": m.strftime("%Y-%m"), **{k: (round(float(v), 4) if pd.notna(v) else None) for k, v in r.items()}}
                  for m, r in ((1 + curves.fillna(0)).cumprod()).iterrows()]
    strip = lambda e: {k: v for k, v in e.items() if not k.startswith("_")}
    result = {
        "as_of": d["dates"][i].strftime("%Y-%m-%d"), "start": d["dates"][0].strftime("%Y-%m"), "universe": len(tickers),
        "signals": [strip(evals[n]) for n in SIGNALS], "composite": strip(ce), "composites": [strip(fe), strip(ae)],
        "ideas_from": ce["id"], "edge": _edge_verdict(ce), "composite_weights": wlog[-24:],
        "current_weights": wlog[-1] if wlog else None, "curve": curve_rows, "longs": longs, "shorts": shorts,
        "missing_prices": len(d["missing_prices"]), "seconds": round(time.time() - t0, 1),
        "method": __doc__.strip().split("\n\n", 1)[1],
        "caveats": ["Index members without free price history (mostly acquired or bankrupt names) are left out — a mild "
                    "survivorship effect, reported here as the count of missing price histories.",
                    "Next-month returns are measured close to close at month-end; real trading after the signal adds slippage "
                    "beyond the 10 bp per unit of turnover charged.",
                    "Short positions also pay borrow (shown per name from IBKR's stock-loan file) — not deducted from the backtest.",
                    "This is research, not a recommendation: size and approve positions through the fund's own process."],
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "result.json").write_text(json.dumps(result, default=str))
    return result


def result(force: bool = False) -> Dict[str, Any]:
    """The last saved run if it is less than TTL old, else a fresh run (several minutes on a cold cache)."""
    path = CACHE / "result.json"
    if not force:
        try:
            if time.time() - path.stat().st_mtime < TTL:
                return json.loads(path.read_text())
        except Exception:
            pass
    return run()


# ── background builds: a cold run takes minutes, so requests never wait on it ──
import threading as _threading

_state: Dict[str, Any] = {"running": False, "started": None, "error": None}
_lock = _threading.Lock()


def _bg() -> None:
    try:
        run()
        _state["error"] = None
    except Exception as e:                                      # noqa: BLE001 — reported to the caller
        logger.exception("[alphalab] run failed")
        _state["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        _state["running"] = False


def start_background() -> None:
    with _lock:
        if _state["running"]:
            return
        _state.update(running=True, started=time.time(), error=None)
        _threading.Thread(target=_bg, name="alphalab", daemon=True).start()


def status_or_result(refresh: bool = False) -> Dict[str, Any]:
    """The saved result (refreshing it in the background when older than TTL or on request), or the build status."""
    path = CACHE / "result.json"
    saved = None
    try:
        saved = json.loads(path.read_text())
        age = time.time() - path.stat().st_mtime
    except Exception:
        age = None
    if refresh or age is None or age > TTL:
        start_background()
    if saved is not None:
        return {**saved, "refreshing": bool(_state["running"]), "age_hours": round(age / 3600, 1) if age is not None else None}
    return {"status": "computing" if _state["running"] else "failed", "error": _state["error"],
            "started_seconds_ago": round(time.time() - _state["started"]) if _state["started"] else None,
            "note": "The first build scores seven signals over ~740 stocks and 12 years — a few minutes; this page refreshes itself."}
