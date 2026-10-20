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


_FX_PAIR = re.compile(r"^(?:([A-Z]{3})([A-Z]{3})|([A-Z]{3}))=X$")


def fx_pair(sym: str) -> Optional[tuple]:
    """(base, quote) of a Yahoo FX symbol: EURUSD=X → (EUR, USD); JPY=X → (USD, JPY)."""
    m = _FX_PAIR.match(sym)
    if not m:
        return None
    return (m.group(1), m.group(2)) if m.group(1) else ("USD", m.group(3))


def check_tradable(symbols: Sequence[str]) -> None:
    """Refuse what the Code Lab cannot account for correctly — indices and futures — instead of 'trading' them.
    Stocks and ETFs of any listing are converted to the account currency; crypto (BTC-USD) trades as a spot asset and
    FX pairs (EURUSD=X, JPY=X) as total-return instruments (see load_data)."""
    idx = [s for s in symbols if s.startswith("^")]
    if idx:
        raise ValueError(f"{', '.join(idx[:5])} {'is an index' if len(idx) == 1 else 'are indices'} — not tradable. "
                         "Use data.vix for the VIX, or an ETF that tracks the index.")
    fut = [s for s in symbols if "=" in s and not fx_pair(s)]
    if fut:
        raise ValueError(f"{', '.join(fut[:5])}: futures are not tradable in the Code Lab — Yahoo's continuous contracts are "
                         "not roll-adjusted, so their returns jump at every roll. Use an ETF on the same market.")


TRADABLE_UNIVERSES = {
    "GLOBAL": "every stock in the platform's tradable universe — the largest companies of 40+ markets, one listing per company",
    "US": "US-listed, USD-quoted stocks",
    "DEVELOPED": "developed-market stocks (MSCI market class)",
    "EMERGING": "emerging- and frontier-market stocks (MSCI market class)",
    "AMERICAS": "stocks listed in the Americas", "EUROPE": "stocks listed in Europe",
    "ASIA_PACIFIC": "stocks listed in Asia-Pacific", "MIDDLE_EAST_AFRICA": "stocks listed in the Middle East & Africa",
    "SP500_PIT": "point-in-time S&P 500 members (incl. later-removed names); data.members says who was in it each day",
}
_REGIONS = {"AMERICAS": "Americas", "EUROPE": "Europe", "ASIA_PACIFIC": "Asia-Pacific", "MIDDLE_EAST_AFRICA": "Middle East & Africa"}


def _universe_stocks() -> List[Dict[str, Any]]:
    from api import global_universe
    u = global_universe.load(rebuild_if_stale=False)
    return [r for r in u.get("stocks", []) if (r.get("asset_type") or "Equity") == "Equity"]


def _listing(r: Dict[str, Any]) -> str:
    return r.get("listing_country") or r.get("country") or ""


def _token_rows(tok: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if tok == "GLOBAL":
        return rows
    if tok == "US":
        return [r for r in rows if _listing(r) == "US" and r.get("currency") == "USD"]
    if tok == "DEVELOPED":
        return [r for r in rows if r.get("market_class") == "Developed"]
    if tok == "EMERGING":
        return [r for r in rows if r.get("market_class") in ("Emerging", "Frontier")]
    if tok in _REGIONS:
        return [r for r in rows if r.get("region") == _REGIONS[tok]]
    if len(tok) == 2 and tok.isalpha():
        return [r for r in rows if _listing(r) == tok]
    raise ValueError(f"TRADABLE_UNIVERSE '{tok}' is not known. Use {', '.join(k for k in TRADABLE_UNIVERSES)}, a listing "
                     "country code (JP, GB, HK, DE …) or several joined with '+' (\"JP+HK\").")


def tradable_catalog() -> Dict[str, Any]:
    """What TRADABLE_UNIVERSE and ACCOUNT_CURRENCY accept, with counts (for the editor's reference panel)."""
    from api.quant import instruments, rates
    rows = _universe_stocks()
    named = [{"name": k, "about": v, "count": None if k == "SP500_PIT" else len(_token_rows(k, rows))}
             for k, v in TRADABLE_UNIVERSES.items()]
    countries: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        c = _listing(r)
        x = countries.setdefault(c, {"code": c, "name": r.get("country_name") if r.get("country") == c else None,
                                     "count": 0, "currencies": set()})
        x["count"] += 1
        x["name"] = x["name"] or (r.get("country_name") if r.get("country") == c else None)
        x["currencies"].add(r.get("currency"))
    ctry = sorted(({**v, "currencies": sorted(filter(None, v["currencies"]))} for v in countries.values()),
                  key=lambda v: -v["count"])
    ccys = [{"code": c, **{k: v for k, v in rates.describe(c).items() if k in ("source", "kind", "known", "note", "stale_since")}}
            for c in instruments.ACCOUNT_CURRENCIES]
    return {"universes": named, "countries": ctry, "account_currencies": ccys, "total": len(rows)}


def tradable_universe(name: str) -> List[str]:
    """Symbols of a TRADABLE_UNIVERSE: a named universe, a listing country, a region, or several joined with '+'.
    Today's list: using it for history is retrospective (survivor-selected) and every result says so."""
    spec = codelab.tradable_spec(name)
    if not spec:
        raise ValueError("TRADABLE_UNIVERSE is empty.")
    toks = spec.split("+")
    if "SP500_PIT" in toks:
        raise ValueError("SP500_PIT is point-in-time and cannot be combined with other universes.")
    rows = _universe_stocks()
    picked: Dict[str, Dict[str, Any]] = {}
    for t in toks:
        for r in _token_rows(t, rows):
            picked[str(r["symbol"]).upper()] = r
    rows = sorted(picked.values(), key=lambda r: -(r.get("traded_usd") or 0))
    from api.markets import country_of
    syms = []
    for r in rows:
        x = str(r["symbol"]).upper()
        # US class shares use '-' on Yahoo (BRK.B → BRK-B); real exchange suffixes (.L, .T, .HK) stay
        syms.append(x.replace(".", "-").replace("/", "-") if country_of(x) == "US" else x)
    syms = list(dict.fromkeys(syms))
    if not syms:
        if not _universe_stocks():
            raise ValueError("The tradable universe is not available yet — open Markets → EQS once to build it.")
        raise ValueError(f"TRADABLE_UNIVERSE '{spec}' has no stocks in the tradable universe.")
    valid, rejected = qdata.clean_symbols(syms)
    if rejected:
        raise ValueError("Configured universe has unsupported symbols: " + ", ".join(rejected[:8]))
    if len(valid) > codelab.LARGE_UNIVERSE_LIMIT:
        raise ValueError(f"Configured {spec} universe has {len(valid)} symbols, above the "
                         f"{codelab.LARGE_UNIVERSE_LIMIT}-symbol server limit; no names were silently dropped.")
    return sorted(valid)


def load_data(universe: Sequence[str], start: str, end: Optional[str] = None,
              limit: Optional[int] = qdata.MAX_SYMBOLS, allow_missing: bool = False, account: str = "USD",
              options: Optional[List[Dict[str, Any]]] = None, fundamentals: Optional[Sequence[str]] = None) -> codelab.Data:
    """Raw daily observations for a strategy, in the account currency: `observed` marks real bars; `close` is the
    last observed close carried forward inside each listing's history (a valuation mark); `open` keeps only observed
    opens."""
    from api.quant import rates
    from api.quant import instruments as inst_mod
    account = inst_mod.account_currency(account)
    from api.quant import options as opt_mod
    specs = opt_mod.parse(options) if options else []
    universe = list(dict.fromkeys([str(u).upper() for u in universe] + [o["underlying"] for o in specs if o["underlying"] != "*"]))
    syms, bad = qdata.clean_symbols(universe)
    if bad:
        raise ValueError(f"Invalid ticker(s): {', '.join(bad[:5])}")
    if not syms or (limit is not None and len(syms) > limit):
        raise ValueError(f"UNIVERSE needs 1–{limit} tickers (the current capability limit).")
    check_tradable(syms)
    fx_syms = [x for x in syms if fx_pair(x)]
    syms = [x for x in syms if not fx_pair(x)] or ["SPY"]          # FX pairs are built separately (below)
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
    inst = inst_mod.meta(cols)
    minor = {c for c, i in inst.items() if float(i.get("unit_divisor") or 1.0) != 1.0}
    unit_fixes = _rescale_minor_units(pan, [c for c in cols if c in minor])
    unit_flips = _scrub_unit_flips(pan, cols)
    quote_close = pan["close"][cols].copy()                       # quote units (pence, cents …), before conversion
    quote_open = pan["open"][cols].copy()
    pan, fx_info, usd_per_unit = _to_account_currency(pan, cols, inst, warm, end, account)
    if fx_info.get("dropped_no_fx"):
        if not allow_missing:
            raise ValueError(f"No FX history for {', '.join(fx_info['missing_fx'])} — cannot account for "
                             f"{', '.join(fx_info['dropped_no_fx'][:5])} in {account}.")
        cols = [c for c in cols if c not in fx_info["dropped_no_fx"]]
        missing = list(missing) + fx_info["dropped_no_fx"]
        inst = {c: inst[c] for c in cols}
    raw = pan["close"][cols]
    observed = raw.notna()
    # carry the last observed close forward, but only inside each listing's own history
    rv = raw.to_numpy(float)
    have = np.isfinite(rv)
    last_pos = np.where(have.any(axis=0), len(rv) - 1 - np.argmax(have[::-1], axis=0), len(rv))
    mv = pd.DataFrame(rv).ffill().to_numpy().copy()
    mv[np.arange(len(rv))[:, None] > last_pos[None, :]] = np.nan
    marks = pd.DataFrame(mv, index=raw.index, columns=raw.columns)
    idx = raw.index
    rf = rates.daily(idx, account) if rates.known(account) else None
    vix = _index_series("^VIX", warm)
    micro = _microstructure(cols, inst, idx, quote_close, pan["close"][cols], account, warm, end)
    fund: Dict[str, pd.DataFrame] = {}
    if fundamentals:
        fund, finfo = fundamental_frames(fundamentals, [c for c in cols if inst[c].get("country") == "US"], idx,
                                         marks * usd_per_unit.reindex(idx).to_numpy()[:, None])
        micro["info"]["fundamentals"] = finfo
    share_px, conv = micro.pop("share_px"), micro.pop("conv")
    micro["share_px"] = (share_px * conv).reindex(columns=cols)   # traded share price in the account currency
    opt_frames: Dict[str, pd.DataFrame] = {}
    settle = None
    option_expansion = None
    if fx_syms:
        fxb = _fx_instruments(fx_syms, idx, account, warm, end)
        names = list(fxb["close"].columns)
        marks = pd.concat([marks, fxb["close"]], axis=1)
        observed = pd.concat([observed, fxb["observed"]], axis=1)
        pan = dict(pan)
        for f in ("open", "high", "low", "volume"):
            pan[f] = pd.concat([pan[f][cols], fxb[f if f != "volume" else "volume"]], axis=1)
        for k in ("tick_bps",):
            micro[k] = pd.concat([micro[k], fxb["tick_bps"]], axis=1)
        for k in ("lot_value", "div_yield", "share_px"):
            micro[k] = micro[k].reindex(columns=list(micro[k].columns) + names)
        inst.update(fxb["instruments"])
        cols = cols + names
        micro["info"]["fx_pairs"] = fxb["info"]
    if specs:
        templates = specs
        specs = opt_mod.expand(options, cols)
        option_expansion = {"template_count": len(templates), "loaded_underlyings": len(cols),
                            "generated_series": len(specs), "wildcard": any(o["underlying"] == "*" for o in templates),
                            "availability": "synthetic contracts; actual exchange/broker option listing unverified",
                            "skipped_missing_history": sorted(set(universe) - set(cols))}
        missing_u = [o["underlying"] for o in specs if o["underlying"] not in cols]
        if missing_u:
            raise ValueError(f"No price data for option underlying(s): {', '.join(sorted(set(missing_u)))}.")
        share_open = quote_open.reindex(idx) * (share_px / quote_close.reindex(idx).ffill())
        built = opt_mod.build(specs, idx=idx, observed=observed, share_close=share_px, share_open=share_open,
                              div_yield=micro["div_yield"], conv=conv, volume=pan["volume"][cols], inst=inst, start=warm,
                              usd_per_unit=usd_per_unit)
        oc = built["columns"]
        names = list(oc)
        col = lambda f: pd.DataFrame({n: oc[n][f] for n in names}, index=idx)
        marks = pd.concat([marks, col("close")], axis=1)
        observed = pd.concat([observed, col("observed").astype(bool)], axis=1)
        pan = dict(pan)
        for f, src in (("open", "open"), ("high", "close"), ("low", "close"), ("volume", "volume")):
            pan[f] = pd.concat([pan[f][cols], col(src)], axis=1)
        micro["tick_bps"] = pd.concat([micro["tick_bps"], col("tick_bps")], axis=1)
        micro["lot_value"] = pd.concat([micro["lot_value"], col("lot_value")], axis=1)
        micro["div_yield"] = pd.concat([micro["div_yield"], pd.DataFrame(0.0, index=idx, columns=names)], axis=1)
        settle = pd.concat([pd.DataFrame(np.nan, index=idx, columns=cols), col("settle")], axis=1)
        opt_frames = {f: col(f) for f in ("delta", "elasticity", "notional", "iv", "strike", "dte", "spot", "spot_open")}
        opt_frames["roll"] = col("roll").astype(bool)
        inst.update(built["instruments"])
        cols = cols + names
        micro["info"]["options"] = {n: {k: built["instruments"][n][k] for k in ("underlying", "option_type", "expiry_rule",
                                                                                "moneyness", "target_delta", "vol_source")}
                                    for n in names}
    prov = {"adjustment": ADJUSTMENT, "stale_symbols": stale, "account_currency": account, "fx": fx_info,
            "cash_rate": rates.describe(account),
            "venue_taxes": {c: i["tax_note"] for c, i in inst.items() if i.get("tax_note")},
            "dropped_no_data": sorted(missing) if allow_missing else [],
            "bad_bars_removed": bad_bars,
            "unit_flip_bars_removed": unit_flips,
            "minor_unit_bars_rescaled": unit_fixes,
            "zero_volume_bars_ignored": zero_volume,
            "universe_selection": "user-specified list (if chosen from today's market, results are retrospective / "
                                  "survivor-selected — names that failed or were delisted earlier are absent)",
            "first_observation": {c: str(marks[c].first_valid_index().date()) for c in cols if marks[c].first_valid_index() is not None},
            "market_rules": micro.pop("info"), "option_expansion": option_expansion}
    return codelab.Data(marks, pan["open"][cols], pan["high"][cols].ffill(), pan["low"][cols].ffill(),
                        pan["volume"][cols], rf=rf, vix=vix, observed=observed, rf_known=rf is not None, provenance=prov,
                        instruments=inst, account_currency=account, usd_per_unit=usd_per_unit, settle=settle,
                        options=opt_frames or None, fundamentals=fund or None, **micro)


def _fx_instruments(symbols: List[str], idx: pd.DatetimeIndex, account: str, start: str, end: Optional[str]) -> Dict[str, Any]:
    """FX pairs as total-return instruments: long the base currency against the quote, collateral in the account.
    Daily return = spot return of the pair + (base rate − quote rate) carry + the account's cash rate (the cash used to
    'buy' the instrument stops earning it, so the net is spot + carry). Values in the account currency (a return index).
    Spreads: half a pip-ish — 0.5 bp for majors, 2 bp otherwise."""
    from api.quant import rates
    raw, missing = qdata.panel(symbols, start=start, end=end, fill=False)
    if missing:
        raise ValueError(f"No price history for: {', '.join(missing[:5])}.")
    majors = {"EUR", "USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD"}
    out = {k: {} for k in ("close", "open", "high", "low", "volume", "observed", "tick_bps")}
    inst, info = {}, {}
    acct_rf = rates.daily(idx, account)
    for s in symbols:
        base, quote = fx_pair(s)
        c = raw["close"][s].reindex(idx)
        o = raw["open"][s].reindex(idx)
        ok = c.notna() & (c > 0)
        cc = c.where(ok).ffill()
        spot = cc.pct_change(fill_method=None).fillna(0.0)
        rb = rates.daily(idx, base) if rates.known(base) else pd.Series(0.0, index=idx)
        rq = rates.daily(idx, quote) if rates.known(quote) else pd.Series(0.0, index=idx)
        r = spot + (rb - rq) + acct_rf
        level = (1 + r.where(ok.cumsum() > 0, 0.0)).cumprod() * 100.0
        level = level.where(ok.cumsum() > 0)
        out["close"][s] = level
        out["open"][s] = level.shift(1) * (o / cc.shift(1)).where(o > 0)
        out["high"][s] = level
        out["low"][s] = level
        out["volume"][s] = pd.Series(1e9, index=idx).where(ok)     # FX trades round the clock in size: never volume-limited
        out["observed"][s] = ok
        out["tick_bps"][s] = pd.Series(0.5 if base in majors and quote in majors else 2.0, index=idx)
        inst[s] = {"country": "FX", "quote_currency": account, "currency": account, "unit_divisor": 1.0, "fx_ticker": None,
                   "tax_buy_bps": 0.0, "tax_sell_bps": 0.0, "tax_note": None, "sec_fee": False, "wht": 0.0, "lot_size": 1,
                   "asset_class": "fx", "base": base, "quote": quote, "name": f"{base}/{quote}", "sector": "Currencies",
                   "region": None, "market_class": None}
        info[s] = {"base": base, "quote": quote, "carry": "base − quote short rates" if rates.known(base) and rates.known(quote)
                   else "unknown for " + ", ".join(x for x in (base, quote) if not rates.known(x)) + " (carry 0)"}
    frames = {k: pd.DataFrame(v, index=idx) for k, v in out.items()}
    frames["observed"] = frames["observed"].fillna(False).astype(bool)
    return {**frames, "instruments": inst, "info": info}


def fundamental_frames(names: Sequence[str], tickers: List[str], idx: pd.DatetimeIndex, close_usd: pd.DataFrame
                       ) -> tuple:
    """Point-in-time fundamentals from SEC filings (api/providers/sec_edgar.py): each value from the trading day after
    it was filed, as first filed; ratios on the USD price. US SEC filers only — other listings stay blank."""
    from api.quant.expr import FUNDAMENTALS, _RAW_FUND
    bad = [n for n in names if n not in FUNDAMENTALS]
    if bad:
        raise ValueError(f"Unknown FUNDAMENTALS: {', '.join(bad)}. Available: {', '.join(FUNDAMENTALS)}.")
    info: Dict[str, Any] = {"source": "SEC EDGAR XBRL company facts, as first filed, from the session after filing",
                            "names": list(names), "requested_tickers": len(tickers)}
    if not tickers:
        info["note"] = "No US-listed names in the universe: fundamentals are blank."
        return {n: pd.DataFrame(np.nan, index=idx, columns=close_usd.columns) for n in names}, info
    from api.providers import sec_edgar
    try:
        f = sec_edgar.pit_frame(tickers, idx)
    except Exception as e:                                      # noqa: BLE001 — EDGAR refused or offline
        raise ValueError(f"Fundamentals unavailable from SEC EDGAR: {str(e)[:200]}")
    px = close_usd[tickers]
    mcap = f["shares"] * px
    derived = {"market_cap": mcap, "earnings_yield": f["eps_ttm"] / px, "book_to_price": f["equity"] / mcap,
               "sales_to_price": f["sales_ttm"] / mcap, "fcf_yield": f["fcf_ttm"] / mcap,
               "roe": f["net_income_ttm"] / f["equity"].where(f["equity"] > 0),
               "gross_profitability": f["gross_profit_ttm"] / f["total_assets"],
               "leverage": f["total_liabilities"] / f["total_assets"]}
    out = {}
    for n in names:
        fr = f[_RAW_FUND[n]] if n in _RAW_FUND else derived[n]
        out[n] = fr.replace([np.inf, -np.inf], np.nan).reindex(columns=close_usd.columns)
    info["coverage"] = {n: int(out[n].iloc[-260:].notna().any().sum()) for n in names}
    return out, info


def _microstructure(cols: List[str], inst: Dict[str, Dict[str, Any]], idx: pd.DatetimeIndex, quote_close: pd.DataFrame,
                    acct_close: pd.DataFrame, account: str, start: str, end: Optional[str]) -> Dict[str, Any]:
    """Tick floors, board-lot values, dividend yields (for withholding), FX and short rates per listing currency
    (for hedging). Sets each instrument's lot_size and statutory withholding rate. Anything without data is simply
    not refined — and reported."""
    from api.quant import corpactions, market_rules, rates
    share_px, div_yield, no_corp = corpactions.frames(cols, idx)       # traded price in quote units; ex-date yields
    conv = (acct_close / quote_close).ffill()                          # account units per quote unit, as of each close
    hk = market_rules.hk_lots() if any(i["country"] == "HK" for i in inst.values()) else {}
    tick, lots = {}, {}
    for c in cols:
        i = inst[c]
        i["lot_size"] = market_rules.lot_size(c, i["country"], hk)
        i["wht"] = market_rules.WHT.get(i["country"], 0.15)
        px = share_px[c].to_numpy(float)
        tick[c] = np.clip(market_rules.half_tick_bps(i["country"], px), 0.0, 100.0)
        if i["lot_size"] > 1 or i["country"] == "PH":
            lots[c] = market_rules.lot_frame_value(i["country"], i["lot_size"], px) * px * conv[c].to_numpy(float)
    ccys = sorted({i["currency"] for i in inst.values()} - {account})
    fx_frame, rf_frame = None, None
    if ccys:
        fx, _, _ = _fx_frame(ccys + [account], start, end)
        a = _asof(fx[account], idx) if account in fx else pd.Series(1.0, index=idx)
        fx_frame = pd.DataFrame({c: a / (_asof(fx[c], idx) if c in fx else 1.0) for c in ccys if c in fx or c == "USD"})
        rf_frame = pd.DataFrame({c: rates.daily(idx, c) if rates.known(c) else pd.Series(np.nan, index=idx) for c in ccys})
    info = {"rules": market_rules.describe(), "no_corporate_action_data": no_corp,
            "board_lot_listings": {c: inst[c]["lot_size"] for c in lots},
            "hedgeable_currencies": [c for c in ccys if rf_frame is not None and rf_frame[c].notna().any()]}
    return {"share_px": share_px, "conv": conv,
            "tick_bps": pd.DataFrame(tick, index=idx), "lot_value": pd.DataFrame(lots, index=idx).reindex(columns=cols),
            "div_yield": div_yield, "fx": fx_frame, "rf_ccy": rf_frame, "info": info}


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


def _fx_frame(currencies: Sequence[str], start: str, end: Optional[str]) -> tuple:
    """Clean USD crosses (units of each currency per 1 USD, as observed) for these currencies; USD is 1.
    Returns ({ccy: series}, missing currencies, {ticker: bad prints removed})."""
    from api.markets import fx_ticker
    need = {c: fx_ticker(c) for c in set(currencies) if c != "USD"}
    out: Dict[str, pd.Series] = {}
    bad_n: Dict[str, int] = {}
    missing: List[str] = []
    if need:
        fxp, _ = qdata.panel(sorted(set(need.values())), start=start, end=end, fill=False)
        for c, t in need.items():
            if not fxp or t not in fxp["close"] or fxp["close"][t].dropna().empty:
                missing.append(c)
                continue
            ser = fxp["close"][t]
            bad = _scrub(ser.to_numpy(float), FX_FLIP)
            if bad.any():
                bad_n[t] = int(bad.sum())
            out[c] = ser.mask(bad).dropna()                    # a bad FX print is skipped; the last good rate stands
    return out, sorted(missing), bad_n


def _asof(ser: pd.Series, idx: pd.DatetimeIndex, prev: bool = False) -> pd.Series:
    """FX known at each date's close (or, with prev, at the previous FX close — what is known before an open)."""
    full = ser.reindex(ser.index.union(idx)).ffill()
    return (full.shift(1) if prev else full).reindex(idx)


def _to_account_currency(pan: Dict[str, pd.DataFrame], cols: List[str], inst: Dict[str, Dict[str, Any]], start: str,
                         end: Optional[str], account: str = "USD") -> tuple:
    """Convert local-currency OHLC to the account currency. Minor units first (GBp/100 → GBP), then FX as of the
    bar through USD crosses (local → USD → account): closes, highs and lows at that day's FX closes; opens at the
    *previous* FX closes (known before the open) — a fill never uses a later rate. A listing already in the account
    currency is not converted at all. Volume stays in shares, so traded value = account price × shares.
    Also returns USD per account unit (as of each close) for the USD-calibrated spread model."""
    idx = pan["close"].index
    info: Dict[str, Any] = {"account_currency": account, "pairs": {},
                            "note": f"{account} account; listings in other currencies converted at as-of FX closes "
                                    "(opens at the previous close)"}
    locals_ = {i["currency"] for c, i in inst.items() if c in cols}
    fx, missing, bad_n = _fx_frame(sorted(locals_ | {account}), start, end)
    info["fx_bad_prints_removed"] = bad_n
    if account in missing:
        raise ValueError(f"No FX history for the account currency {account} ({account}=X) — choose another ACCOUNT_CURRENCY.")
    acct = fx.get(account)                                        # account units per 1 USD (None = USD)
    leg = lambda ser, prev: _asof(ser, idx, prev) if ser is not None else pd.Series(1.0, index=idx)
    usd_per_unit = (1.0 / leg(acct, False)).bfill()               # cost-model scale only, never a price
    if missing:
        # a stock whose currency cannot be converted cannot be accounted for: leave it out, and say so
        bad = [c for c, i in inst.items() if i["currency"] in missing]
        info["dropped_no_fx"], info["missing_fx"] = bad, missing
    out = {k: v.copy() for k, v in pan.items()}
    # one conversion factor per currency (not per instrument), applied to whole column blocks at once
    acct_c, acct_o = leg(acct, False).to_numpy(float), leg(acct, True).to_numpy(float)
    factors: Dict[str, tuple] = {}
    conv_cols: Dict[str, List[str]] = {}
    divs: Dict[str, float] = {}
    for c in cols:
        i = inst[c]
        local, div = i["currency"], float(i.get("unit_divisor") or 1.0)
        if local in missing:
            continue
        if local != account:
            if local not in factors:
                lc = fx.get(local)                                # local units per USD (None = USD)
                factors[local] = (acct_c / leg(lc, False).to_numpy(float), acct_o / leg(lc, True).to_numpy(float))
            info["pairs"][c] = {"quote": i["quote_currency"], "unit_divisor": div,
                                "via": "/".join(x for x in (i.get("fx_ticker"), f"{account}=X" if acct is not None else None) if x)}
        if local == account and div == 1.0:
            continue
        conv_cols.setdefault(local, []).append(c)
        divs[c] = div
    ones = np.ones(len(idx))
    for local, cs in conv_cols.items():
        fc, fo = factors.get(local, (ones, ones))
        d = np.array([divs[c] for c in cs])[None, :]
        for f in ("close", "high", "low"):
            out[f][cs] = pan[f][cs].to_numpy(float) / d * fc[:, None]
        out["open"][cs] = pan["open"][cs].to_numpy(float) / d * fo[:, None]
    return out, info, usd_per_unit


def benchmark_series(sym: str, start: str, account: str = "USD") -> Optional[pd.Series]:
    """A benchmark's closes in the account currency (as-of FX closes), so it compares like with like."""
    ser = _index_series(sym, start)
    if ser is None:
        return None
    from api.quant import instruments as inst_mod
    i = inst_mod.meta([sym])[sym]
    local, div = i["currency"], float(i.get("unit_divisor") or 1.0)
    if local == account and div == 1.0:
        return ser
    fx, missing, _ = _fx_frame([local, account], start, None)
    if missing:
        return None
    idx = ser.index
    f = (_asof(fx[account], idx) if account in fx else 1.0) / (_asof(fx[local], idx) if local in fx else 1.0)
    return ser / div * f


def usd_per(account: str, dates: Sequence[str]) -> pd.Series:
    """USD per one unit of the account currency, as of each date (1 for USD)."""
    idx = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    if account == "USD":
        return pd.Series(1.0, index=idx)
    fx, missing, _ = _fx_frame([account], (idx[0] - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), None)
    if missing:
        raise ValueError(f"No FX history for {account}.")
    return 1.0 / _asof(fx[account], idx)


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=np.float32).tobytes()).decode()


def attach_custom(d, names: Optional[Sequence[str]]) -> None:
    """Uploaded custom datasets (api/quant/customdata.py), aligned as of each session, onto the Data object."""
    if names:
        from api.quant import customdata
        d.custom = customdata.frames(names, d.close.index)
        d.provenance["custom_data"] = {n: {k: v for k, v in m.items() if k != "owner"}
                                       for m in customdata.catalog() for n in names if m.get("name") == n}


def data_payload(universe: Sequence[str], start: str, benchmark: str = "SPY", account: str = "USD",
                 options: Optional[List[Dict[str, Any]]] = None, fundamentals: Optional[Sequence[str]] = None,
                 custom: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Compact data for the browser: float32 arrays (base64), row-major dates × tickers, plus the observed
    mask, whether the reference rate is known, instrument metadata and the data provenance."""
    d = load_data(universe, start, account=account, options=options, fundamentals=fundamentals)
    attach_custom(d, custom)
    bm = benchmark_series(benchmark, d.close.index[0].strftime("%Y-%m-%d"), d.account_currency)
    out = {"dates": [x.strftime("%Y-%m-%d") for x in d.close.index], "tickers": d.tickers,
           "rf": _b64(d.rf.to_numpy()), "vix": _b64(d.vix.to_numpy()), "rf_known": d.rf_known,
           "observed": base64.b64encode(np.ascontiguousarray(d.observed.to_numpy(), dtype=np.uint8).tobytes()).decode(),
           "benchmark": _b64(bm.reindex(d.close.index).to_numpy()) if bm is not None else None, "benchmark_symbol": benchmark,
           "provenance": d.provenance, "engine_version": codelab.ENGINE_VERSION,
           "instruments": d.instruments, "account_currency": d.account_currency,
           "usd_per_unit": _b64(d.usd_per_unit.to_numpy()), "micro_cols": {}}
    for f in ("close", "open", "high", "low", "volume"):
        out[f] = _b64(getattr(d, f).to_numpy())
    frames = {k: getattr(d, k) for k in ("tick_bps", "lot_value", "div_yield", "fx", "rf_ccy", "settle", "share_px")}
    frames.update({f"opt_{k}": v.astype(float) for k, v in d.opt.items()})
    frames.update({f"fund_{k}": v for k, v in d.fund.items()})
    frames.update({f"cust_{k}": v for k, v in getattr(d, "custom", {}).items()})
    for k, fr in frames.items():                                                # market rules, options
        if fr is not None:
            out[f"m_{k}"] = _b64(fr.to_numpy())
            out["micro_cols"][k] = [str(c) for c in fr.columns]
    return out


def evaluate_code(code: str, costs: Optional[Dict[str, float]] = None, trusted: bool = False,
                  light: bool = False) -> Dict[str, Any]:
    """Run TRUSTED code (the built-in library) in-process. Refuses anything else."""
    if not trusted:
        raise PermissionError("User code is not executed on the server — it runs in your browser or the deploy sandbox.")
    st = codelab.load_strategy(code)
    d = load_data(st["universe"], st["start"], account=st["account"], options=st["options"], fundamentals=st["fundamentals"])
    attach_custom(d, st.get("custom"))
    bm = benchmark_series(st["benchmark"], d.close.index[0].strftime("%Y-%m-%d"), d.account_currency)
    return codelab.evaluate(st["strategy"], d, st["params"], st["start"], codelab.run_costs(st, costs), bm, st["holdout"],
                            st["code_hash"], signal=None if light else st.get("signal"), on_bar=st.get("on_bar"),
                            setup=st.get("setup"), light=light)


def rf_for(dates: Sequence[str], account: str = "USD") -> pd.Series:
    """The platform reference rate (api/quant/rates.py) for these dates, in the account currency — one source
    for every surface."""
    from api.quant import rates
    return rates.daily(dates, account)


def analyze(dates: List[str], returns: List[float], benchmark: Optional[List[float]] = None, label: str = "Strategy",
            benchmark_label: str = "SPY", mc_years: float = 10.0, mc_paths: int = 2000, max_leverage: float = 2.0,
            dd_limit: float = 0.5, owner: Optional[str] = None, provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deep report + Monte Carlo for a daily return series (numbers only — no code)."""
    from api.quant import deep
    if len(dates) != len(returns) or len(returns) < 250:
        raise ValueError("Need matching dates and at least 250 daily returns.")
    if any((not math.isfinite(x)) or x < -1 or x > 5 for x in returns):
        raise ValueError("Returns must be finite daily fractions (−1 to 5).")
    from api.quant import instruments as inst_mod
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    ret = pd.Series(returns, index=idx, dtype=float)
    account = inst_mod.account_currency((provenance or {}).get("account_currency"))
    rf = rf_for(dates, account)
    rep = deep.report([d for d in dates], list(returns), codelab.TRADING_DAYS,
                      benchmark if benchmark and len(benchmark) == len(returns) else None,
                      label=label, benchmark_label=benchmark_label, ccy=account)
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
        lens_ret = ret
        if account != "USD":                                   # the lens is a USD investor's view: convert first
            u = usd_per(account, dates)
            lens_ret = (1 + ret) * (u / u.shift(1)).fillna(1.0) - 1
        lens = factor_lens(dates, list(lens_ret))
        if lens and account != "USD":
            lens["note"] = f"Returns converted from {account} to USD at as-of FX before the regression. " + lens["note"]
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


def account_session_data(data: codelab.Data, calendar: str) -> codelab.Data:
    """Global research with one explicit account clock: only observed benchmark sessions.
    A foreign exchange holiday remains a non-executable bar, never a filled opening price.
    Trading on weekends/account holidays is deliberately deferred to the next account session.
    This is a daily-bar approximation, not a synchronized intraday execution simulator.
    """
    if calendar not in data.tickers:
        raise ValueError(f"Account calendar instrument {calendar} has no usable data")
    mask = data.observed[calendar] & (data.volume[calendar] > 0)
    idx = data.close.index[mask]
    if len(idx) < 253:
        raise ValueError("Account calendar needs at least 253 observed sessions")
    provenance = {**data.provenance, "account_calendar": calendar,
                  "account_sessions": "observed calendar-instrument dates; other venue orders defer to next account session",
                  "excluded_account_dates": int(len(data.close)-len(idx)),
                  "global_timing": f"daily {data.account_currency} marks; opens use prior FX close, not a verified executable FX fill"}
    return codelab.Data(data.close.loc[idx], data.open.loc[idx], data.high.loc[idx], data.low.loc[idx], data.volume.loc[idx],
                        rf=data.rf.loc[idx], vix=data.vix.loc[idx], observed=data.observed.loc[idx],
                        rf_known=data.rf_known, provenance=provenance, instruments=data.instruments,
                        account_currency=data.account_currency, usd_per_unit=data.usd_per_unit.loc[idx],
                        **{k: (getattr(data, k).loc[idx] if getattr(data, k) is not None else None)
                           for k in ("tick_bps", "lot_value", "div_yield", "fx", "rf_ccy", "settle", "share_px")},
                        options={k: v.loc[idx] for k, v in data.opt.items()} or None,
                        fundamentals={k: v.loc[idx] for k, v in data.fund.items()} or None)
