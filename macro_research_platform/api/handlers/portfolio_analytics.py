"""
Portfolio analytics endpoints' data layer: Brinson attribution and tracking error versus a benchmark on the actual
book, liquidity-adjusted VaR, FIFO lots, transaction-cost analysis of fills and trade-idea P&L. Pure maths in
api/calculations/portfolio_analytics.py.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Dict, List, Optional

from api.calculations import portfolio_analytics as pa

logger = logging.getLogger(__name__)

# S&P 500 sectors (Yahoo names) → SPDR sector ETF; the benchmark is SPY with its current sector weights
SECTOR_ETF = {"Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Cyclical": "XLY",
              "Communication Services": "XLC", "Industrials": "XLI", "Consumer Defensive": "XLP", "Energy": "XLE",
              "Utilities": "XLU", "Real Estate": "XLRE", "Basic Materials": "XLB"}
_SPY_SECTOR_KEYS = {"technology": "Technology", "financial_services": "Financial Services", "healthcare": "Healthcare",
                    "consumer_cyclical": "Consumer Cyclical", "communication_services": "Communication Services",
                    "industrials": "Industrials", "consumer_defensive": "Consumer Defensive", "energy": "Energy",
                    "utilities": "Utilities", "realestate": "Real Estate", "basic_materials": "Basic Materials"}
_INFO_CACHE: Dict[str, Any] = {}


def _bars(sym: str, period: str = "1y") -> Dict[str, Dict[str, float]]:
    from api.market_bars import bars
    try:
        b = bars(sym, "1d", period)
    except Exception as e:
        logger.info("[pa] bars %s: %s", sym, e)
        return {}
    return {x["t"]: x for x in b["bars"]}


def _sector_of(sym: str) -> str:
    if sym in _INFO_CACHE:
        return _INFO_CACHE[sym]
    sec = "Other"
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
        qt = (info.get("quoteType") or "").upper()
        if sym in ("SPY", "VOO", "IVV"):
            sec = "Benchmark (S&P 500)"
        elif qt == "ETF":
            sec = f"Off-benchmark: {info.get('category') or 'ETF'}"
        else:
            sec = info.get("sector") or "Other"
    except Exception as e:
        logger.debug("[pa] sector %s: %s", sym, e)
    _INFO_CACHE[sym] = sec
    return sec


def _spy_sector_weights() -> Dict[str, float]:
    import yfinance as yf
    sw = yf.Ticker("SPY").funds_data.sector_weightings or {}
    w = {_SPY_SECTOR_KEYS[k]: float(v) for k, v in sw.items() if k in _SPY_SECTOR_KEYS}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()} if tot else {}


def _book(book: Optional[str]):
    from api import blotter_store, portfolio_store, fund_store
    blotter_store.init_db()                          # a new fund has no trades table until its first fill
    pos = portfolio_store.list_positions(book)
    with portfolio_store._conn() as c:
        q = "SELECT ts, book, symbol, side, quantity, price, commission, source FROM trades"
        rows = c.execute(q + (" WHERE book = ?" if book else ""), ((book,) if book else ())).fetchall()
    trades = _split_adjusted([dict(r) for r in rows])
    st = fund_store.get_settings()
    return pos, trades, float(st.get("capital") or 0), float(st.get("realized_pnl") or 0)


def _split_adjusted(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each fill with its split factor (shares today per share then), against split-adjusted price history."""
    from api import corporate_actions as ca
    known = {s: ca.splits(s) for s in {str(t["symbol"]).upper() for t in trades}}
    for t in trades:
        t["split_factor"] = ca.split_factor_after(str(t["symbol"]).upper(), t["ts"], known[str(t["symbol"]).upper()])
    return trades


def _daily_rets(px: Dict[str, Dict[str, float]], days: List[str]) -> Dict[str, float]:
    out = {}
    for i in range(1, len(days)):
        a, b = px.get(days[i - 1]), px.get(days[i])
        if a and b and a["c"]:
            out[days[i]] = b["c"] / a["c"] - 1
    return out


def brinson(book: Optional[str] = None, benchmark: str = "SPY", max_days: int = 252) -> Dict[str, Any]:
    """Brinson–Fachler attribution against an S&P-style benchmark (sector ETFs as segments, local units) on the
    holdings actually held, Carino-linked over up to `max_days` sessions. For a composite benchmark in the fund's
    base currency use brinson_base.
    """
    pos, trades, capital, realized = _book(book)
    if not pos and not trades:
        return {"available": False, "reason": "No positions or trades in this book."}
    syms = sorted({str(p["symbol"]).upper() for p in pos} | {str(t["symbol"]).upper() for t in trades})
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(syms, ex.map(_bars, syms)))
        sectors = dict(zip(syms, ex.map(_sector_of, syms)))
        etf_px = dict(zip(SECTOR_ETF.values(), ex.map(_bars, SECTOR_ETF.values())))
    bench_px = _bars(benchmark)
    if not bench_px:
        return {"available": False, "reason": f"No price history for the benchmark {benchmark}."}
    try:
        bw = _spy_sector_weights()
    except Exception as e:
        return {"available": False, "reason": f"Benchmark sector weights unavailable ({type(e).__name__})."}
    days_all = sorted(bench_px)
    first = min([str(p.get("entry_date") or "9999")[:10] for p in pos] + [str(t["ts"])[:10] for t in trades])
    days = [d for d in days_all if d >= first][-max_days - 1:]
    if len(days) < 3:
        return {"available": False, "reason": "Fewer than three sessions since the first holding."}
    hold = pa.holdings_by_day(pos, trades, days)
    sym_r = {s: _daily_rets(px[s], days) for s in syms}
    etf_r = {sec: _daily_rets(etf_px[e], days) for sec, e in SECTOR_ETF.items()}
    bench_r = _daily_rets(bench_px, days)
    # cost basis for the NAV path: avg cost of today's positions (trades are reflected in holdings)
    cost = {str(p["symbol"]).upper(): float(p.get("avg_cost") or 0) for p in pos}
    daily_eff, rp_list, rb_list, used = [], [], [], []
    last_day = days[-1]
    for i in range(1, len(days)):
        d0, d = days[i - 1], days[i]
        h = hold[d0]                                   # held over the session d0 → d
        if not h or d not in bench_r:
            continue
        mv = {s: q * px[s][d0]["c"] for s, q in h.items() if d0 in px[s]}
        unreal = sum(q * (px[s][d0]["c"] - cost.get(s, px[s][d0]["c"])) for s, q in h.items() if d0 in px[s])
        nav = capital + realized + unreal
        if nav <= 0:
            continue
        pw, contrib = {}, {}
        for s, v in mv.items():
            sec = sectors[s]
            pw[sec] = pw.get(sec, 0) + v / nav
            contrib[sec] = contrib.get(sec, 0) + v / nav * sym_r[s].get(d, 0.0)
        pr = {sec: contrib[sec] / pw[sec] for sec in pw if abs(pw[sec]) > 1e-12}
        pw["Cash"] = 1 - sum(pw.values())
        pr["Cash"] = 0.0
        # benchmark weights at the start of this session, backed out from today's by each sector's move since
        bw_d = pa.backed_out_weights(bw, {sec: (etf_px[SECTOR_ETF[sec]].get(d0) or {}).get("c") for sec in bw},
                                     {sec: (etf_px[SECTOR_ETF[sec]].get(last_day) or {}).get("c") for sec in bw})
        brr = {sec: etf_r[sec].get(d, 0.0) for sec in bw}
        for sec in pw:                                  # segments outside the benchmark's sectors
            if sec not in brr:
                brr[sec] = bench_r[d] if sec.startswith("Benchmark") else 0.0
        daily_eff.append(pa.brinson_day(pw, pr, bw_d, brr))
        rp_list.append(sum(pw[s] * pr.get(s, 0) for s in pw))
        rb_list.append(sum(bw_d[s] * brr[s] for s in bw_d))
        used.append(d)
    if not daily_eff:
        return {"available": False, "reason": "No sessions with holdings and prices."}
    linked = pa.carino_link(daily_eff, rp_list, rb_list)
    R = math.prod(1 + r for r in rp_list) - 1
    B = math.prod(1 + b for b in rb_list) - 1
    rows = sorted(({"sector": s, **{k: round(v * 1e4, 1) for k, v in e.items()},
                    "total_bps": round(sum(e.values()) * 1e4, 1)} for s, e in linked.items()
                   if any(abs(v) > 1e-9 for v in e.values())), key=lambda r: -abs(r["total_bps"]))
    tot = {k: round(sum(e[k] for e in linked.values()) * 1e4, 1) for k in ("allocation", "selection", "interaction")}
    te = pa.ex_post_tracking_error(rp_list, rb_list)
    return {"available": True, "book": book or "Firm", "benchmark": benchmark,
            "period": {"start": used[0], "end": used[-1], "sessions": len(used)},
            "portfolio_return": round(R, 5), "benchmark_return": round(B, 5), "active_return_bps": round((R - B) * 1e4, 1),
            "effects_bps": tot, "by_sector": rows,
            "ex_post_tracking_error": round(te, 4) if te is not None else None,
            "information_ratio": (round((R - B) / te * math.sqrt(252 / len(used)), 2)
                                  if te and len(used) >= 20 else None),
            "method": ("Brinson–Fachler per session on the holdings actually held (rebuilt from positions and trades), "
                       "returns on NAV including cash; Carino-linked so effects sum to the geometric active return. "
                       f"Benchmark: {benchmark} sector weights (Yahoo, backed out to each day) and SPDR sector ETF returns."),
            "limitations": ("Benchmark sector weights each day are backed out from today's by each sector ETF's price "
                            "change since (exact for a cap-weighted index without reconstitution); holdings outside the "
                            "benchmark's sectors (ETFs, the benchmark itself) are their own segments; cash earns 0.")}


# MSCI World sectors (Yahoo / Morningstar sector names) → an MSCI World sector UCITS ETF (London); the segment
# return of the benchmark in each sector. No Xtrackers MSCI World real-estate ETF exists, so real estate uses iShares
# Developed Markets Property Yield (FTSE EPRA Nareit Developed Dividend+), labelled as a proxy.
WORLD_SECTOR_ETF = {"Technology": "XDWT.L", "Financial Services": "XDWF.L", "Healthcare": "XDWH.L",
                    "Consumer Cyclical": "XDWC.L", "Consumer Defensive": "XDWS.L", "Energy": "XDWE.L",
                    "Industrials": "XDWI.L", "Basic Materials": "XDWM.L", "Utilities": "XDWU.L",
                    "Communication Services": "XWTS.L", "Real Estate": "IWDP.L"}


def _proxy_sector_weights(sym: str) -> Dict[str, float]:
    """A fund's sector weights as Yahoo reports them (Morningstar sectors), normalised to 1."""
    from api.marketdata.core import _cached

    def fetch():
        import yfinance as yf
        return yf.Ticker(sym).funds_data.sector_weightings or {}
    sw = _cached(f"pa:sectorw:{sym}", 24 * 3600, fetch) or {}
    w = {_SPY_SECTOR_KEYS[k]: float(v) for k, v in sw.items() if k in _SPY_SECTOR_KEYS and v}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()} if tot else {}


def benchmark_sector_weights(code: str) -> Dict[str, Any]:
    """The composite benchmark's sector weights: each leg's proxy ETF weights × the leg's weight."""
    from api.calculations import benchmark as bm
    out: Dict[str, float] = {}
    legs = {}
    for leg in bm.BENCHMARKS[code]["legs"]:
        w = _proxy_sector_weights(leg["proxy"])
        if not w:
            raise ValueError(f"no sector weights for {leg['proxy']}")
        legs[leg["proxy"]] = {k: round(v, 4) for k, v in w.items()}
        for k, v in w.items():
            out[k] = out.get(k, 0.0) + leg["weight"] * v
    return {"weights": out, "legs": legs}


def brinson_base(book: Optional[str] = None, code: str = "BIFS", max_days: int = 252) -> Dict[str, Any]:
    """Brinson–Fachler attribution in the fund's base currency against a composite benchmark (e.g. BIFS): returns of
    holdings and of the benchmark's sector segments all converted to the base currency each day (local return and
    currency together), sector weights of the benchmark from its proxy ETFs, Carino-linked. The benchmark's own
    return is the real blend; the gap between it and the sum of its sector segments is reported, not hidden."""
    import pandas as pd
    from api.calculations import benchmark as bm
    pos, trades, _, _ = _book(book)
    if not pos and not trades:
        return {"available": False, "reason": "No positions or trades in this book."}
    bk = book_in_base(book)
    base = bk["base"]
    bser = bm.series(code, base)
    bench_r_s = bser["returns"]
    if bench_r_s.empty:
        return {"available": False, "reason": f"No history for the {code} benchmark."}
    try:
        bwi = benchmark_sector_weights(code)
    except Exception as e:                                                     # noqa: BLE001
        return {"available": False, "reason": f"Benchmark sector weights unavailable ({e})."}
    bw = bwi["weights"]
    syms = sorted({str(p["symbol"]).upper() for p in pos} | {str(t["symbol"]).upper() for t in trades})

    def _px(s):
        try:
            return bm.in_base(s, base)
        except Exception:                                                     # noqa: BLE001 — reported as unpriced
            return pd.Series(dtype=float)
    seg_syms = sorted(set(WORLD_SECTOR_ETF.values()))
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(syms, ex.map(_px, syms)))
        sectors = dict(zip(syms, ex.map(_sector_of, syms)))
        seg_px = dict(zip(seg_syms, ex.map(_px, seg_syms)))
    unpriced = [s for s in syms if px[s].empty]
    days_all = [d.strftime("%Y-%m-%d") for d in bench_r_s.index]
    first = min([str(p.get("entry_date") or "9999")[:10] for p in pos] + [str(t["ts"])[:10] for t in trades])
    prior = [d for d in days_all if d < first]
    days = ([prior[-1]] if prior else []) + [d for d in days_all if d >= first]
    days = days[-max_days - 1:]
    if len(days) < 3:
        return {"available": False, "reason": f"Fewer than three sessions since the first holding with the benchmark "
                                              f"available (it starts {bser['start']})."}
    P = {s: {k.strftime("%Y-%m-%d"): float(v) for k, v in px[s].items()} for s in syms}
    SP = {e: {k.strftime("%Y-%m-%d"): float(v) for k, v in seg_px[e].items()} for e in seg_syms}

    def at(series: Dict[str, float], d: str) -> Optional[float]:
        if d in series:
            return series[d]
        earlier = [k for k in series if k <= d]                               # holiday on that listing: last close
        return series[max(earlier)] if earlier else None
    bench_r = {d.strftime("%Y-%m-%d"): float(v) for d, v in bench_r_s.items()}
    hold = pa.holdings_by_day(pos, trades, days)
    cost_unit = {}                                                             # base-currency cost per share today
    for p in bk["positions"]:
        q = float(p.get("quantity") or 0)
        if q and p.get("cost_basis") is not None:
            cost_unit[p["symbol"]] = float(p["cost_basis"]) / q
    unreal_today = sum(float(p.get("unrealized_pnl") or 0) for p in bk["positions"])
    nav_ex_unreal = bk["nav"] - unreal_today                                   # capital + realised − costs, in base
    daily_eff, rp_list, rb_seg, rb_act, used = [], [], [], [], []
    for i in range(1, len(days)):
        d0, d = days[i - 1], days[i]
        h = hold.get(d0) or {}
        if d not in bench_r:
            continue
        mv, ret = {}, {}
        for s, q in h.items():
            a, b = at(P[s], d0), at(P[s], d)
            if a and b:
                mv[s], ret[s] = q * a, b / a - 1
        unreal = sum(mv[s] - q * cost_unit.get(s, mv[s] / q) for s, q in h.items() if s in mv)
        nav = nav_ex_unreal + unreal
        if nav <= 0:
            continue
        pw, contrib = {}, {}
        for s, v in mv.items():
            sec = sectors[s]
            pw[sec] = pw.get(sec, 0) + v / nav
            contrib[sec] = contrib.get(sec, 0) + v / nav * ret[s]
        pr = {sec: contrib[sec] / pw[sec] for sec in pw if abs(pw[sec]) > 1e-12}
        pw["Cash"], pr["Cash"] = 1 - sum(pw.values()), 0.0
        # the proxies' reported sector weights, held fixed: backing them out to each day (as for the S&P version)
        # tracked both legs' real returns worse over 1m–1y — the reported weights lag, and the equal-weighted leg is
        # rebalanced back to equal weights each quarter
        seg_then = {sec: at(SP[WORLD_SECTOR_ETF[sec]], d0) for sec in bw}
        bw_d = dict(bw)
        brr = {}
        for sec in bw:
            a, b = seg_then[sec], at(SP[WORLD_SECTOR_ETF[sec]], d)
            brr[sec] = b / a - 1 if a and b else bench_r[d]
        brr["Cash"] = 0.0
        for sec in pw:                                  # off-benchmark segments (ETFs, other): vs the benchmark itself
            brr.setdefault(sec, bench_r[d])
        daily_eff.append(pa.brinson_day(pw, pr, bw_d, brr))
        rp_list.append(sum(pw[s] * pr.get(s, 0) for s in pw))
        rb_seg.append(sum(bw_d[s] * brr[s] for s in bw_d))
        rb_act.append(bench_r[d])
        used.append(d)
    if not daily_eff:
        return {"available": False, "reason": "No sessions with holdings and prices."}
    linked = pa.carino_link(daily_eff, rp_list, rb_seg)
    R = math.prod(1 + r for r in rp_list) - 1
    Bs = math.prod(1 + b for b in rb_seg) - 1
    Ba = math.prod(1 + b for b in rb_act) - 1
    rows = sorted(({"sector": s, **{k: round(v * 1e4, 1) for k, v in e.items()},
                    "total_bps": round(sum(e.values()) * 1e4, 1),
                    "benchmark_weight": round(bw.get(s, 0.0), 4)} for s, e in linked.items()
                   if any(abs(v) > 1e-9 for v in e.values())), key=lambda r: -abs(r["total_bps"]))
    tot = {k: round(sum(e[k] for e in linked.values()) * 1e4, 1) for k in ("allocation", "selection", "interaction")}
    te = pa.ex_post_tracking_error(rp_list, rb_act)
    return {"available": True, "book": book or "Firm", "benchmark": code, "benchmark_label": bm.BENCHMARKS[code]["label"],
            "currency": base, "period": {"start": used[0], "end": used[-1], "sessions": len(used)},
            "portfolio_return": round(R, 5), "benchmark_return": round(Ba, 5),
            "benchmark_segments_return": round(Bs, 5),
            "active_return_bps": round((R - Ba) * 1e4, 1),
            "effects_bps": tot, "benchmark_construction_bps": round((Bs - Ba) * 1e4, 1),
            "by_sector": rows, "benchmark_sector_weights": {k: round(v, 4) for k, v in sorted(bw.items(), key=lambda x: -x[1])},
            "benchmark_leg_sector_weights": bwi["legs"], "sector_proxies": WORLD_SECTOR_ETF,
            "unpriced": unpriced,
            "ex_post_tracking_error": round(te, 4) if te is not None else None,
            "information_ratio": (round((R - Ba) / te * math.sqrt(252 / len(used)), 2) if te and len(used) >= 20 else None),
            "method": (f"Brinson–Fachler per session in {base} (each holding's and each benchmark sector's local return "
                       "and currency move together), on the holdings actually held (rebuilt from positions and "
                       "trades, split-adjusted), NAV including cash; Carino-linked. Benchmark sector weights: "
                       + " + ".join(f"{leg['weight']:.0%} × {leg['proxy']}" for leg in bm.BENCHMARKS[code]["legs"])
                       + " sector weights as reported (Yahoo/Morningstar), held fixed; sector segment returns from "
                       "MSCI World sector ETFs. Active return = allocation + selection + interaction + benchmark "
                       "construction."),
            "limitations": ("Sectors are Morningstar's (as Yahoo reports them), close to but not exactly GICS. Segment "
                            "returns are cap-weighted MSCI World sectors, so the equal-weighted half's within-sector "
                            "return differs: that gap is the 'benchmark construction' term (the benchmark return used "
                            "for active return is the real blend). Real estate is proxied by a developed-markets "
                            "property ETF. Cash earns 0; realised P&L is held at today's total over the period.")}


def book_in_base(book: Optional[str] = None) -> Dict[str, Any]:
    """The book in the fund's base currency: per position market value (today's FX) and cost (FX paid), NAV =
    capital + realised − costs + unrealised, all in base. Prices are the last daily closes."""
    from api import blotter_store, fund_store, portfolio_store
    from api.calculations import fx_accounting as fa
    from api.calculations.blotter import blotter_totals
    st = fund_store.get_settings()
    base = st.get("base_currency") or "USD"
    pos = portfolio_store.list_positions(book)
    rows = []
    for p in pos:
        sym = str(p["symbol"]).upper()
        b = _bars(sym, "1mo")
        last = b[sorted(b)[-1]]["c"] if b else None
        ccy, usd = _usd_per_unit(sym)
        q = fa.convert_position({**p, "symbol": sym, "current_price": last, "currency": ccy}, base, usd)
        rows.append(q)
    tot = blotter_totals(blotter_store.list_trades(book=book))
    unreal = sum(r.get("unrealized_pnl") or 0 for r in rows)
    nav = float(st.get("capital") or 0) + tot["realized_pnl"] + float(st.get("realized_pnl") or 0) - tot["commissions"] + unreal
    return {"base": base, "positions": rows, "nav": nav, "capital": float(st.get("capital") or 0),
            "benchmark": st.get("benchmark") or "SPY"}


def tracking_error(book: Optional[str] = None, benchmark: Optional[str] = None) -> Dict[str, Any]:
    """Ex-ante tracking error against the fund's benchmark, in the fund's base currency: holdings' daily returns in
    base currency (local return and currency together), weights = base-currency market value / NAV, the benchmark
    as its own return series (e.g. the BIFS 50/50 blend), 1-year daily covariance. Euler contributions per name."""
    import numpy as np
    import pandas as pd
    from api.calculations import benchmark as bm
    bk = book_in_base(book)
    code = (benchmark or bk["benchmark"] or "SPY").upper()
    if code not in bm.BENCHMARKS:
        return _tracking_error_vs_ticker(book, code)
    pos = [p for p in bk["positions"] if p.get("market_value") is not None]
    if not pos:
        return {"available": False, "reason": "No priced positions."}
    base, nav = bk["base"], bk["nav"]
    syms = sorted({p["symbol"] for p in pos})
    R = bm.returns_in_base(syms, base)
    b = bm.series(code, base)["returns"].rename("__BENCH__")
    frame = pd.concat([R, b], axis=1).dropna().tail(252)
    if len(frame) < 60:
        return {"available": False, "reason": f"Under 60 common sessions of history with the benchmark "
                                              f"(it starts {bm.series(code, base)['start']})."}
    cols = list(frame.columns)
    cov = np.cov(frame.to_numpy(), rowvar=False)
    mv = {s: 0.0 for s in syms}
    for p in pos:
        mv[p["symbol"]] += float(p["market_value"])
    w = np.array([mv.get(c, 0.0) / nav if c != "__BENCH__" else 0.0 for c in cols])
    active = w - np.array([1.0 if c == "__BENCH__" else 0.0 for c in cols])
    te = pa.ex_ante_tracking_error(active, cov)
    sig = cov @ active
    var = float(active @ sig)
    contrib = {("benchmark" if c == "__BENCH__" else c): round(float(active[i] * sig[i] / var), 3) if var > 0 else None
               for i, c in enumerate(cols)}
    k = cols.index("__BENCH__")
    beta = float(w @ cov[:, k] / cov[k, k])
    vol = float(np.sqrt(max(w @ cov @ w, 0.0)) * np.sqrt(252))
    return {"available": True, "benchmark": code, "benchmark_label": bm.BENCHMARKS[code]["label"], "currency": base,
            "as_of": str(frame.index[-1].date()), "sessions": int(len(frame)),
            "ex_ante_tracking_error": round(te, 4), "portfolio_beta": round(beta, 3),
            "portfolio_volatility": round(vol, 4), "nav": round(nav, 2), "invested": round(float(w.sum()), 4),
            "cash_weight": round(1 - float(w.sum()), 4),
            "weights": {c: round(float(w[i]), 4) for i, c in enumerate(cols) if c != "__BENCH__"},
            "te_contribution": contrib,
            "note": ("Returns in " + base + " (local return and currency move); benchmark from accumulating UCITS ETF "
                     "proxies, rebalanced daily. Cash counts as an active underweight of the benchmark.")}


def _tracking_error_vs_ticker(book: Optional[str] = None, benchmark: str = "SPY") -> Dict[str, Any]:
    """Ex-ante TE: active weights (holdings on NAV minus 100% benchmark) on a 1-year daily covariance."""
    import numpy as np
    pos, _, capital, realized = _book(book)
    if not pos:
        return {"available": False, "reason": "No positions."}
    syms = sorted({str(p["symbol"]).upper() for p in pos})
    allsyms = syms + ([benchmark] if benchmark not in syms else [])
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(allsyms, ex.map(_bars, allsyms)))
    days = sorted(set.intersection(*[set(px[s]) for s in allsyms if px[s]]))[-253:]
    if len(days) < 60:
        return {"available": False, "reason": "Under 60 common sessions of history."}
    R = np.array([[px[s][days[i]]["c"] / px[s][days[i - 1]]["c"] - 1 for s in allsyms] for i in range(1, len(days))])
    cov = np.cov(R, rowvar=False)
    qty = {str(p["symbol"]).upper(): 0.0 for p in pos}
    cost = {}
    for p in pos:
        s = str(p["symbol"]).upper()
        qty[s] += float(p["quantity"])
        cost[s] = float(p.get("avg_cost") or 0)
    last = days[-1]
    mv = {s: qty[s] * px[s][last]["c"] for s in syms}
    nav = capital + realized + sum(qty[s] * (px[s][last]["c"] - cost[s]) for s in syms)
    w = np.array([mv.get(s, 0) / nav for s in allsyms])
    b = np.array([1.0 if s == benchmark else 0.0 for s in allsyms])
    active = w - b
    te = pa.ex_ante_tracking_error(active, cov)
    # contribution of each active weight to TE (Euler)
    sig = cov @ active
    var = float(active @ sig)
    contrib = {s: round(float(active[i] * sig[i] / var), 3) if var > 0 else None for i, s in enumerate(allsyms)}
    beta = float(w @ cov[:, allsyms.index(benchmark)] / cov[allsyms.index(benchmark), allsyms.index(benchmark)])
    return {"available": True, "benchmark": benchmark, "as_of": last, "ex_ante_tracking_error": round(te, 4),
            "portfolio_beta": round(beta, 3), "nav": round(nav, 2), "invested_net": round(float(w.sum()), 4),
            "active_weights": {s: round(float(active[i]), 4) for i, s in enumerate(allsyms)},
            "te_contribution": contrib,
            "note": ("A book mostly in cash has an ex-ante TE close to the benchmark's own volatility: the active "
                     "position is −100% benchmark plus the holdings.")}


def liquidity(book: Optional[str] = None, participation: float = 0.20) -> Dict[str, Any]:
    """Liquidity of each holding: days to exit at `participation` of 20-day average volume, the estimated spread
    (Abdi–Ranaldo, Corwin–Schultz fallback) and the cost of exiting, with the totals that feed liquidity-adjusted
    VaR.
    """
    from api import portfolio_store
    pos = portfolio_store.list_positions(book)
    if not pos:
        return {"available": False, "reason": "No positions."}
    rows, total_cost, total_mv = [], 0.0, 0.0
    for p in pos:
        s = str(p["symbol"]).upper()
        b = _bars(s, "3mo")
        days = sorted(b)[-21:]
        if not days:
            rows.append({"symbol": s, "available": False})
            continue
        adv = sum(b[d]["v"] for d in days[-20:]) / len(days[-20:]) if days else None
        hi, lo, cl = [b[d]["h"] for d in days], [b[d]["l"] for d in days], [b[d]["c"] for d in days]
        ar = pa.abdi_ranaldo_spread(cl, hi, lo)
        cs = pa.corwin_schultz_spread(hi, lo, cl)
        spread = ar if ar is not None else cs          # Abdi–Ranaldo (lower bias); Corwin–Schultz as fallback
        price = b[days[-1]]["c"]
        prof = pa.liquidity_profile(float(p["quantity"]), price, adv or None, spread, participation)
        mv = abs(float(p["quantity"]) * price)
        total_mv += mv
        total_cost += prof["liquidity_cost"] or 0.0
        rows.append({"symbol": s, "book": p.get("book"), "quantity": p["quantity"], "market_value": round(mv, 2),
                     "adv_shares_20d": round(adv) if adv else None, **prof,
                     "spread_estimates_bps": {"abdi_ranaldo": round(ar * 1e4, 1) if ar is not None else None,
                                              "corwin_schultz": round(cs * 1e4, 1) if cs is not None else None}})
    worst = max((r.get("days_to_liquidate") or 0 for r in rows), default=0)
    return {"available": True, "participation_rate": participation, "positions": rows,
            "liquidity_cost_total": round(total_cost, 2), "gross_market_value": round(total_mv, 2),
            "max_days_to_liquidate": round(worst, 2),
            "method": (f"Days to liquidate = |quantity| ÷ ({participation:.0%} × 20-day average volume). Liquidity "
                       "cost = half the estimated spread × market value — Abdi & Ranaldo (2017) close/high/low estimator, Corwin–"
                       "Schultz (2012, overnight-adjusted) shown alongside; LVaR = VaR + this cost.")}


def lots(book: Optional[str] = None) -> Dict[str, Any]:
    """Open FIFO tax lots per position, in today's share units after splits; positions loaded without fills appear as
    one opening lot.
    """
    pos, trades, _, _ = _book(book)
    out = {}
    for p in pos:
        s = str(p["symbol"]).upper()
        mine = [t for t in trades if str(t["symbol"]).upper() == s]
        traded = sum(float(t["quantity"]) * (t.get("split_factor") or 1.0)
                     * (1 if str(t["side"]).upper() in ("BUY", "COVER") else -1) for t in mine)
        opening = float(p["quantity"]) - traded
        fills = ([{"date": p.get("entry_date") or "", "side": "BUY" if opening > 0 else "SELL",
                   "quantity": abs(opening), "price": float(p.get("avg_cost") or 0), "source": "opening position"}]
                 if abs(opening) > 1e-9 else [])
        fills += [{"date": str(t["ts"])[:10], "side": t["side"], "quantity": t["quantity"] * (t.get("split_factor") or 1.0),
                   "price": t["price"] / (t.get("split_factor") or 1.0), "source": t.get("source") or "trade"}
                  for t in mine]                     # in today's share units after any split
        out[s] = pa.fifo_lots(fills)
    today = date.today()
    for s, ls in out.items():
        for l in ls:
            try:
                held = (today - date.fromisoformat(l["date"])).days
            except ValueError:
                held = None
            l["holding_days"] = held
            l["term"] = None if held is None else ("long-term" if held > 365 else "short-term")
    return {"available": bool(out), "lots": out, "method": "FIFO; positions loaded without fills appear as one "
                                                          "opening lot at their average cost and entry date. Fills before "
                                                          "a split are shown in today's share units."}


_FX_CACHE: Dict[str, Any] = {}


def _usd_per_unit(sym: str):
    """(currency, USD per one unit of the price's currency) — minor units (GBp, ZAc) handled."""
    from api.markets import classify, minor_unit_factor, fx_ticker
    if (classify(sym).get("home_currency") or "USD") == "USD":
        return "USD", 1.0                    # US listings: no lookup
    ccy = None
    try:                                     # the quote currency Yahoo reports (GBp for London, not GBP)
        from api.market_bars import bars
        ccy = bars(sym, "1d", "2y").get("currency")
    except Exception:
        pass
    ccy = ccy or classify(sym).get("home_currency") or "USD"
    major, div = minor_unit_factor(ccy)
    if major == "USD":
        return ccy, 1.0 / div
    if major not in _FX_CACHE:
        b = _bars(fx_ticker(major), "1mo")
        _FX_CACHE[major] = b[sorted(b)[-1]]["c"] if b else None
    per_usd = _FX_CACHE[major]
    return ccy, (1.0 / per_usd / div) if per_usd else None


def tca(limit: int = 200) -> Dict[str, Any]:
    """Fills of the fund blotter and the paper traders, against the decision price, the fill session's typical
    price and close."""
    from api import blotter_store, portfolio_store
    blotter_store.init_db()                          # a new fund has no trades table until its first fill
    fills = []
    with portfolio_store._conn() as c:
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        fund_fills = _split_adjusted([dict(r) for r in c.execute(
            "SELECT ts, symbol, side, quantity, price, source FROM trades ORDER BY ts DESC LIMIT ?", (limit,))])
        for r in fund_fills:                         # in today's share units (price history is split-adjusted)
            k = r["split_factor"] or 1.0
            fills.append({"book": "Fund", "symbol": r["symbol"], "side": r["side"], "shares": r["quantity"] * k,
                          "fill_date": str(r["ts"])[:10], "fill_price": r["price"] / k, "decision_date": str(r["ts"])[:10],
                          "arrival": None})
        if "auto_orders" in tabs:
            for r in c.execute("SELECT symbol, created_date, signal_price, fill_date, fill_price, shares FROM auto_orders "
                               "WHERE fill_price IS NOT NULL AND fill_date IS NOT NULL ORDER BY fill_date DESC LIMIT ?", (limit,)):
                fills.append({"book": "Technical trader", "symbol": r["symbol"], "side": "BUY" if (r["shares"] or 0) >= 0 else "SELL",
                              "shares": abs(r["shares"] or 0), "fill_date": r["fill_date"], "fill_price": r["fill_price"],
                              "decision_date": r["created_date"], "arrival": r["signal_price"]})
        if "macro_trader_orders" in tabs:
            for r in c.execute("SELECT symbol, shares, placed_on, fill_date, fill_price FROM macro_trader_orders "
                               "WHERE fill_price IS NOT NULL AND fill_date IS NOT NULL ORDER BY fill_date DESC LIMIT ?", (limit,)):
                fills.append({"book": "Macro trader", "symbol": r["symbol"], "side": "BUY" if (r["shares"] or 0) >= 0 else "SELL",
                              "shares": abs(r["shares"] or 0), "fill_date": r["fill_date"], "fill_price": r["fill_price"],
                              "decision_date": r["placed_on"], "arrival": None})
    if not fills:
        return {"available": False, "reason": "No fills recorded yet."}
    syms = sorted({f["symbol"] for f in fills})
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(syms, ex.map(lambda s: _bars(s, "2y"), syms)))
    rows = []
    for f in fills:
        b = px.get(f["symbol"]) or {}
        fd = str(f["fill_date"])[:10]
        bar = b.get(fd)
        arrival = f["arrival"]
        if arrival is None:                          # decision close (the order was placed on that session's close)
            prior = [d for d in sorted(b) if d <= str(f["decision_date"])[:10]]
            arrival = b[prior[-1]]["c"] if prior else None
        sign = 1 if str(f["side"]).upper() in ("BUY", "COVER") else -1
        r = pa.tca_row(sign, float(f["shares"] or 0), float(f["fill_price"]), arrival,
                       bar["h"] if bar else None, bar["l"] if bar else None, bar["c"] if bar else None)
        ccy, usd = _usd_per_unit(f["symbol"])
        r["currency"] = ccy
        r["shortfall_local"] = r.pop("shortfall_usd")
        r["shortfall_usd"] = round(r["shortfall_local"] * usd, 2) if r["shortfall_local"] is not None and usd else None
        rows.append({**{k: f[k] for k in ("book", "symbol", "side", "shares", "fill_date", "fill_price", "decision_date")},
                     "arrival": round(arrival, 4) if arrival else None, **r})
    by_book = {}
    for r in rows:
        g = by_book.setdefault(r["book"], {"fills": 0, "shortfall_usd": 0.0, "bps": []})
        g["fills"] += 1
        g["shortfall_usd"] += r["shortfall_usd"] or 0
        if r["vs_arrival_bps"] is not None:
            g["bps"].append(r["vs_arrival_bps"])
    summary = {k: {"fills": v["fills"], "shortfall_usd": round(v["shortfall_usd"], 2),
                   "avg_vs_arrival_bps": round(sum(v["bps"]) / len(v["bps"]), 1) if v["bps"] else None,
                   "median_vs_arrival_bps": round(sorted(v["bps"])[len(v["bps"]) // 2], 1) if v["bps"] else None}
               for k, v in by_book.items()}
    return {"available": True, "fills": rows[:limit], "by_book": summary,
            "method": ("Positive bps = cost. Arrival = the price when the order was decided (signal price, else that "
                       "session's close); VWAP proxy = the fill session's (high+low+close)/3 — no intraday volume "
                       "is available free. Shortfall is in the listing's currency, converted to USD at the latest rate.")}


def idea_tracking() -> Dict[str, Any]:
    """Mark-to-market of every trade idea since it was created (both idea tables)."""
    from api import portfolio_store
    ideas = []
    with portfolio_store._conn() as c:
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "trade_ideas" in tabs:
            for r in c.execute("SELECT id, ticker, direction, entry_level, stop_loss, target_1, status, created_at, regime "
                               "FROM trade_ideas"):
                ideas.append({"source": "Signal ideas", "id": r["id"], "symbol": r["ticker"], "direction": r["direction"],
                              "entry": r["entry_level"], "stop": r["stop_loss"], "target": r["target_1"],
                              "status": r["status"], "created": str(r["created_at"])[:10], "regime": r["regime"]})
        if "pm_trade_ideas" in tabs:
            for r in c.execute("SELECT id, symbol, direction, state, created_at, conviction FROM pm_trade_ideas"):
                ideas.append({"source": "PM ideas", "id": r["id"], "symbol": r["symbol"], "direction": r["direction"],
                              "entry": None, "stop": None, "target": None, "status": r["state"],
                              "created": str(r["created_at"])[:10], "conviction": r["conviction"]})
    if not ideas:
        return {"available": False, "reason": "No trade ideas recorded."}
    syms = sorted({i["symbol"] for i in ideas if i["symbol"]})
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(syms, ex.map(lambda s: _bars(s, "2y"), syms)))
    out = []
    for i in ideas:
        b = px.get(i["symbol"]) or {}
        days = [d for d in sorted(b) if d >= i["created"]]
        prior = [d for d in sorted(b) if d <= i["created"]]
        market = b[prior[-1]]["c"] if prior else (b[days[0]]["c"] if days else None)   # close on the day it was proposed
        entry, adjusted = i["entry"], False
        if entry is None:
            entry = market
        elif market and abs(entry / market - 1) > 0.05:
            # a stated entry more than 5% from the market when the idea was made could not have been traded there;
            # its stop and target were set around that level, so they are dropped too
            entry, adjusted = market, True
            i["stop"] = i["target"] = None
        i["entry_vs_market_pct"] = round((i["entry"] / market - 1) * 100, 1) if i["entry"] and market else None
        i["entry_adjusted"] = adjusted
        path = [(d, b[d]["h"], b[d]["l"], b[d]["c"]) for d in days if d > i["created"]]
        res = pa.idea_pnl(i["direction"], entry, path, i["stop"], i["target"]) if entry and path else \
            {"return": None, "status": "no sessions yet"}
        out.append({**i, "entry_used": round(entry, 4) if entry else None, "sessions": len(path), **res})
    done = [o for o in out if o.get("return") is not None]
    return {"available": True, "ideas": out,
            "summary": {"ideas": len(out), "with_prices": len(done),
                        "hit_rate": round(sum(o["return"] > 0 for o in done) / len(done), 3) if done else None,
                        "average_return": round(sum(o["return"] for o in done) / len(done), 4) if done else None},
            "method": ("Return from the idea's entry level (or the close on the day it was proposed, also used when the "
                       "stated entry was more than 5% away from that close) to the last close, "
                       "or to its stop / first target if the daily range touched one first (stop assumed first on a "
                       "day that touched both).")}


_ETF_TOPIC = {"SPY": "S&P 500", "VOO": "S&P 500", "IVV": "S&P 500", "QQQ": "Nasdaq", "DIA": "Dow", "IWM": "Russell 2000",
              "GLD": "gold", "IAU": "gold", "SLV": "silver", "USO": "oil", "TLT": "Treasury", "IEF": "Treasury",
              "HYG": "high yield", "LQD": "corporate bond", "EFA": "European stocks", "EEM": "emerging markets",
              "FXI": "China stocks", "EWJ": "Japan stocks", "UUP": "dollar", "VIXY": "volatility"}


def _etf_topic(sym: str) -> str:
    if sym in _ETF_TOPIC:
        return _ETF_TOPIC[sym]
    try:
        import re as _re
        import yfinance as yf
        name = (yf.Ticker(sym).info or {}).get("longName") or sym
        name = _re.sub(r"\b(SPDR|iShares|Vanguard|Invesco|Select Sector|ETF|Trust|Fund|Index|Shares|Core|MSCI)\b", " ", name)
        return " ".join(name.split()[:3]) or sym
    except Exception:
        return sym


def holding_news(book: Optional[str] = None, per_holding: int = 6) -> Dict[str, Any]:
    """Recent headlines tagged to each holding (company-specific search, filtered to stories naming it), with a
    finance-lexicon tone per headline and the latest SEC filings."""
    from api import portfolio_store
    from api.marketdata.core import news
    from api.calculations.news_sentiment import score_headline
    pos = portfolio_store.list_positions(book)
    syms = sorted({str(p["symbol"]).upper() for p in pos})
    if not syms:
        return {"available": False, "reason": "No positions."}

    def one(s):
        if _sector_of(s).startswith(("Off-benchmark", "Benchmark")):      # an ETF: news about what it tracks
            q = _etf_topic(s)
            try:
                from api.marketdata.monitors import news_hub
                items = []
                for qq in (q, "Wall Street") if q in ("S&P 500", "Nasdaq", "Dow", "Russell 2000") else (q,):
                    items = news_hub(q=qq, limit=per_holding).get("items") or []
                    if items:
                        q = qq
                        break
            except Exception as e:
                return s, {"headlines": [], "filings": [], "error": str(e)[:120], "topic": q}
            heads = [{"title": i.get("title"), "publisher": i.get("source"), "time": i.get("time"), "url": i.get("link") or i.get("url"),
                      "tone": round(score_headline(i.get("title") or ""), 2)} for i in items[:per_holding]]
            return s, {"headlines": heads, "filings": [], "topic": q}
        try:
            n = news(s)
        except Exception as e:
            return s, {"headlines": [], "filings": [], "error": str(e)[:120]}
        heads = [{**{k: h.get(k) for k in ("title", "publisher", "time", "url")},
                  "tone": round(score_headline(h.get("title") or ""), 2)} for h in (n.get("news") or [])[:per_holding]]
        return s, {"headlines": heads, "filings": (n.get("filings") or [])[:3]}
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = dict(ex.map(one, syms))
    side = {}
    for p in pos:
        side[str(p["symbol"]).upper()] = "short" if float(p["quantity"]) < 0 else "long"
    for s, v in out.items():
        tones = [h["tone"] for h in v["headlines"]]
        v["side"] = side.get(s)
        v["average_tone"] = round(sum(tones) / len(tones), 2) if tones else None
        # tone against the position: negative news on a long, positive on a short
        v["against_position"] = (v["average_tone"] is not None and
                                 ((side.get(s) == "long" and v["average_tone"] < -0.15) or
                                  (side.get(s) == "short" and v["average_tone"] > 0.15)))
    return {"available": True, "holdings": out,
            "method": "Yahoo Finance search and company sources, kept when the story names the company or ticker; "
                      "tone = finance word-list score of the headline (−1 to +1); SEC filings from EDGAR."}


# Yahoo sector → the Sector Allocation table's names
_DASH_SECTOR = {"Technology": "Technology", "Financial Services": "Financials", "Healthcare": "Healthcare",
                "Consumer Cyclical": "Consumer", "Communication Services": "Communication", "Industrials": "Industrials",
                "Consumer Defensive": "Consumer Staples", "Energy": "Energy", "Utilities": "Utilities",
                "Real Estate": "Real Estate", "Basic Materials": "Materials"}
_ETF_SECTOR = {e: s for s, e in SECTOR_ETF.items()}


def sector_exposure(book: Optional[str] = None) -> Dict[str, Any]:
    """Net exposure by sector as a share of NAV, looking through SPY (its sector weights) and the SPDR sector ETFs;
    other ETFs (gold, bonds…) are reported as non-equity."""
    pos, _, capital, realized = _book(book)
    if not pos:
        return {"available": False, "reason": "No positions."}
    syms = sorted({str(p["symbol"]).upper() for p in pos})
    with ThreadPoolExecutor(max_workers=6) as ex:
        px = dict(zip(syms, ex.map(lambda s: _bars(s, "1mo"), syms)))
    last = {s: px[s][sorted(px[s])[-1]]["c"] for s in syms if px[s]}
    unreal = sum(float(p["quantity"]) * (last.get(str(p["symbol"]).upper(), 0) - float(p.get("avg_cost") or 0))
                 for p in pos if str(p["symbol"]).upper() in last)
    nav = capital + realized + unreal
    spy_w = None
    out: Dict[str, float] = {}
    for p in pos:
        s = str(p["symbol"]).upper()
        if s not in last or nav <= 0:
            continue
        w = float(p["quantity"]) * last[s] / nav
        if s in ("SPY", "VOO", "IVV"):
            spy_w = spy_w or _spy_sector_weights()
            for sec, sw in spy_w.items():
                k = _DASH_SECTOR.get(sec, sec)
                out[k] = out.get(k, 0) + w * sw
            continue
        if s in _ETF_SECTOR:
            k = _DASH_SECTOR.get(_ETF_SECTOR[s], _ETF_SECTOR[s])
        else:
            sec = _sector_of(s)
            k = _DASH_SECTOR.get(sec, "Non-equity" if sec.startswith("Off-benchmark") else sec)
        out[k] = out.get(k, 0) + w
    return {"available": True, "nav": round(nav, 2),
            "net_weight": {k: round(v, 5) for k, v in sorted(out.items(), key=lambda kv: -abs(kv[1]))},
            "method": "Net market value ÷ NAV by sector; SPY split by its current sector weights, SPDR sector ETFs "
                      "assigned to their sector, other ETFs shown as non-equity."}
