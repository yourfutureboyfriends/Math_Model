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
    # non-US listings are supported: converted to the USD account at as-of FX marks (see load_data)


TRADABLE_UNIVERSES = {
    "US": "US-listed, USD-quoted stocks in the platform's tradable universe (Markets screener)",
    "GLOBAL": "every stock in the platform's tradable universe — the largest companies of 40+ markets, one listing per "
              "company — converted to the USD account at as-of FX",
    "DEVELOPED": "the tradable universe's developed-market stocks (MSCI market class), in USD",
    "EMERGING": "the tradable universe's emerging- and frontier-market stocks (MSCI market class), in USD",
}


def tradable_universe(name: str) -> List[str]:
    """Symbols of a named tradable universe. Today's list: using it for history is retrospective
    (survivor-selected) and every result says so."""
    from api import global_universe
    name = (name or "").upper()
    if name not in TRADABLE_UNIVERSES:
        raise ValueError(f"TRADABLE_UNIVERSE must be one of: {', '.join(TRADABLE_UNIVERSES)}.")
    u = global_universe.load(rebuild_if_stale=False)
    rows = [r for r in u.get("stocks", []) if (r.get("asset_type") or "Equity") == "Equity"]
    if name == "US":
        rows = [r for r in rows if (r.get("listing_country") or r.get("country")) == "US" and r.get("currency") == "USD"]
    elif name == "DEVELOPED":
        rows = [r for r in rows if r.get("market_class") == "Developed"]
    elif name == "EMERGING":
        rows = [r for r in rows if r.get("market_class") in ("Emerging", "Frontier")]
    rows.sort(key=lambda r: -(r.get("traded_usd") or 0))
    from api.markets import country_of
    syms = []
    for r in rows:
        x = str(r["symbol"]).upper()
        # US class shares use '-' on Yahoo (BRK.B → BRK-B); real exchange suffixes (.L, .T, .HK) stay
        syms.append(x.replace(".", "-").replace("/", "-") if country_of(x) == "US" else x)
    syms = list(dict.fromkeys(syms))
    if not syms:
        raise ValueError("The tradable universe is not available yet — open Markets → EQS once to build it.")
    valid, rejected = qdata.clean_symbols(syms)
    if rejected:
        raise ValueError("Configured universe has unsupported symbols: " + ", ".join(rejected[:8]))
    if len(valid) > codelab.LARGE_UNIVERSE_LIMIT:
        raise ValueError(f"Configured {name} universe has {len(valid)} symbols, above the "
                         f"{codelab.LARGE_UNIVERSE_LIMIT}-symbol server limit; no names were silently dropped.")
    return sorted(valid)


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
    # Data validation, once for every strategy: a non-positive or non-finite price is a bad bar, not an
    # observation — it is removed (never valued or traded) and counted in the provenance. A bar with zero
    # volume is not a trade either (vendors fill non-trading days with junk prints, e.g. Saudi Thursdays in 2011):
    # it is treated as no observation, so the mark stays at the last real close and nothing fills.
    vol0 = pan["volume"][cols].eq(0) & pan["close"][cols].notna()
    zero_volume = {c: int(n) for c, n in vol0.sum().items() if n}
    if vol0.any().any():
        for f in ("close", "open", "high", "low"):
            pan[f] = pan[f].copy()
            pan[f][cols] = pan[f][cols].mask(vol0)
    bad_bars = {}
    for f in ("close", "open", "high", "low"):
        frame = pan[f][cols]
        bad = ~np.isfinite(frame) | (frame <= 0)
        bad &= frame.notna()
        if bad.any().any():
            pan[f] = pan[f].copy()
            pan[f][cols] = frame.mask(bad)
            if f == "close":
                bad_bars = {c: int(n) for c, n in bad.sum().items() if n}
    from api.quant import instruments as inst_mod
    inst = inst_mod.meta(cols)
    minor = {c for c, i in inst.items() if float(i.get("unit_divisor") or 1.0) != 1.0}
    unit_fixes = _rescale_minor_units(pan, [c for c in cols if c in minor])
    unit_flips = _scrub_unit_flips(pan, cols)
    pan, fx_info = _to_account_currency(pan, cols, inst, warm, end)
    if fx_info.get("dropped_no_fx"):
        if not allow_missing:
            raise ValueError(f"No FX history for {', '.join(fx_info['missing_fx'])} — cannot account for "
                             f"{', '.join(fx_info['dropped_no_fx'][:5])} in USD.")
        cols = [c for c in cols if c not in fx_info["dropped_no_fx"]]
        missing = list(missing) + fx_info["dropped_no_fx"]
        inst = {c: inst[c] for c in cols}
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
    prov = {"adjustment": ADJUSTMENT, "stale_symbols": stale, "account_currency": "USD", "fx": fx_info,
            "venue_taxes": {c: i["tax_note"] for c, i in inst.items() if i.get("tax_note")},
            "dropped_no_data": sorted(missing) if allow_missing else [],
            "bad_bars_removed": bad_bars,
            "unit_flip_bars_removed": unit_flips,
            "minor_unit_bars_rescaled": unit_fixes,
            "zero_volume_bars_ignored": zero_volume,
            "universe_selection": "user-specified list (if chosen from today's market, results are retrospective / "
                                  "survivor-selected — names that failed or were delisted earlier are absent)",
            "first_observation": {c: str(raw[c].first_valid_index().date()) for c in cols if raw[c].first_valid_index() is not None}}
    return codelab.Data(marks, pan["open"][cols], pan["high"][cols].ffill(), pan["low"][cols].ffill(),
                        pan["volume"][cols], rf=rf, vix=vix, observed=observed, rf_known=rf is not None, provenance=prov,
                        instruments=inst)


FLIP = 4.0          # a close more than 4× / less than ¼ of the last accepted close is a unit/scale error
CONFIRM = 5         # …unless this many consecutive bars agree on the new level (a genuine redenomination)
MAX_LEVEL_SHIFT = 1000.0   # no redenomination or unadjusted split moves a price by more than this


def _scrub(x: np.ndarray, flip: float, confirm: int = CONFIRM, max_shift: float = MAX_LEVEL_SHIFT) -> np.ndarray:
    """Causal bad-print filter for one price series: True where a value is off by more than `flip`× from the
    last accepted value. A new level is accepted once `confirm` consecutive values agree with each other (and the
    shift is below `max_shift`×). Each value is judged only against values before it."""
    bad = np.zeros(len(x), bool)
    last = np.nan
    run: List[int] = []
    lim = np.log(flip)
    for i, v in enumerate(x):
        if not np.isfinite(v) or v <= 0:
            continue
        if not np.isfinite(last) or abs(np.log(v / last)) <= lim:
            last, run = v, []
            continue
        run.append(i)
        same = all(abs(np.log(x[j] / x[run[0]])) <= np.log(1.5) for j in run)
        if len(run) >= confirm and same and abs(np.log(v / last)) <= np.log(max_shift):
            last, run = v, []
            continue
        bad[i] = True
    return bad


def _scrub_unit_flips(pan: Dict[str, pd.DataFrame], cols: List[str]) -> Dict[str, int]:
    """Remove bars whose price is off by a scale factor (Yahoo mixes ILS/ILA agorot for Tel Aviv, 10×/100×
    errors elsewhere), causally (see _scrub). Opens far from the last accepted close are dropped too. Only
    columns with a suspicious move are examined. Returns {ticker: bars removed}."""
    close = pan["close"]
    removed: Dict[str, int] = {}
    lr = np.log(close[cols].where(close[cols] > 0)).diff().abs()
    lim = np.log(FLIP)
    for c in [c for c in cols if (lr[c] > lim).any()]:
        x = close[c].to_numpy(float)
        bad = _scrub(x, FLIP)
        o = pan["open"][c].to_numpy(float)
        acc = pd.Series(np.where(bad, np.nan, x)).ffill().shift(1).to_numpy()
        bad_open = np.isfinite(o) & np.isfinite(acc) & (o > 0) & (np.abs(np.log(np.where(o > 0, o, 1) / np.where(acc > 0, acc, 1))) > lim)
        n = int(bad.sum() + (bad_open & ~bad).sum())
        if n:
            removed[c] = n
            for f in ("close", "high", "low"):
                pan[f].loc[pan[f].index[bad], c] = np.nan
            pan["open"].loc[pan["open"].index[bad | bad_open], c] = np.nan
    return removed


def _rescale_minor_units(pan: Dict[str, pd.DataFrame], cols: List[str]) -> Dict[str, int]:
    """Instruments quoted in minor units (GBp, ZAc, ILA) sometimes arrive in the major unit for a stretch (Tel
    Aviv agorot vs shekels): a bar exactly ~100× or ~1/100 of the last accepted close is rescaled by 100 rather
    than dropped or accepted as a new level. Causal: compared with the last accepted close only."""
    fixed: Dict[str, int] = {}
    for c in cols:
        x = pan["close"][c].to_numpy(float)
        factor = np.ones(len(x))
        last = np.nan
        for i, v in enumerate(x):
            if not np.isfinite(v) or v <= 0:
                continue
            if np.isfinite(last):
                q = v / last
                if 70 <= q <= 140:
                    factor[i] = 0.01
                elif 1 / 140 <= q <= 1 / 70:
                    factor[i] = 100.0
            last = v * factor[i]
        n = int((factor != 1).sum())
        if n:
            fixed[c] = n
            for f in ("close", "open", "high", "low"):
                pan[f].loc[:, c] = pan[f][c].to_numpy(float) * factor
    return fixed


FX_FLIP = 2.0       # an exchange rate moving more than 2× in a day is a bad print (CLP=X, TWD=X glitches)


def _to_account_currency(pan: Dict[str, pd.DataFrame], cols: List[str], inst: Dict[str, Dict[str, Any]], start: str,
                         end: Optional[str]) -> tuple:
    """Convert local-currency OHLC to USD. Minor units first (GBp/100 → GBP), then FX as of the bar: closes,
    highs and lows at that day's FX close; opens at the *previous* FX close (known before the open) — a fill
    never uses a later rate. Volume stays in shares, so dollar volume = USD price × shares."""
    foreign = {c: i for c, i in inst.items() if i["currency"] != "USD"}
    info = {"note": "USD account; non-USD listings converted at as-of FX closes (opens at the previous close)",
            "pairs": {}}
    if not foreign:
        return pan, info
    tickers = sorted({i["fx_ticker"] for i in foreign.values() if i.get("fx_ticker")})
    fxp, missing = qdata.panel(tickers, start=start, end=end, fill=False)
    if missing:
        # a stock whose currency cannot be converted cannot be accounted for in USD: leave it out, and say so
        bad = [c for c, i in foreign.items() if i.get("fx_ticker") in missing]
        info["dropped_no_fx"] = bad
        info["missing_fx"] = sorted(set(i["currency"] for c, i in foreign.items() if c in bad))
        foreign = {c: i for c, i in foreign.items() if c not in bad}
    idx = pan["close"].index
    out = {k: v.copy() for k, v in pan.items()}
    fx_bad: Dict[str, int] = {}
    clean: Dict[str, pd.Series] = {}
    for t in tickers:
        if t not in fxp["close"]:
            continue
        ser = fxp["close"][t]
        bad = _scrub(ser.to_numpy(float), FX_FLIP)
        if bad.any():
            fx_bad[t] = int(bad.sum())
        clean[t] = ser.mask(bad)                                  # a bad FX print is skipped; the last good rate stands
    info["fx_bad_prints_removed"] = fx_bad
    for c, i in foreign.items():
        fx = clean[i["fx_ticker"]]                                # units of local currency per 1 USD
        fx = fx.reindex(fx.index.union(idx)).ffill()
        fx_close = fx.reindex(idx)
        fx_prev = fx.shift(1).reindex(idx)
        div = float(i["unit_divisor"])
        for f in ("close", "high", "low"):
            out[f][c] = pan[f][c] / div / fx_close
        out["open"][c] = pan["open"][c] / div / fx_prev
        info["pairs"][c] = {"quote": i["quote_currency"], "unit_divisor": div, "fx": i["fx_ticker"]}
    return out, info


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
