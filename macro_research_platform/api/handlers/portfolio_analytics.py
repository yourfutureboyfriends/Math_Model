"""
Portfolio analytics endpoints' data layer: Brinson attribution and tracking error versus a benchmark on the actual
book, liquidity-adjusted VaR, FIFO lots, transaction-cost analysis of fills and trade-idea P&L. Pure maths in
api/calculations/portfolio_analytics.py.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
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
    from api import portfolio_store, fund_store
    pos = portfolio_store.list_positions(book)
    with portfolio_store._conn() as c:
        q = "SELECT ts, book, symbol, side, quantity, price, commission, source FROM trades"
        rows = c.execute(q + (" WHERE book = ?" if book else ""), ((book,) if book else ())).fetchall()
    trades = [dict(r) for r in rows]
    st = fund_store.get_settings()
    return pos, trades, float(st.get("capital") or 0), float(st.get("realized_pnl") or 0)


def _daily_rets(px: Dict[str, Dict[str, float]], days: List[str]) -> Dict[str, float]:
    out = {}
    for i in range(1, len(days)):
        a, b = px.get(days[i - 1]), px.get(days[i])
        if a and b and a["c"]:
            out[days[i]] = b["c"] / a["c"] - 1
    return out


def brinson(book: Optional[str] = None, benchmark: str = "SPY", max_days: int = 252) -> Dict[str, Any]:
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


def tracking_error(book: Optional[str] = None, benchmark: str = "SPY") -> Dict[str, Any]:
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
        spread = pa.corwin_schultz_spread([b[d]["h"] for d in days], [b[d]["l"] for d in days])
        price = b[days[-1]]["c"]
        prof = pa.liquidity_profile(float(p["quantity"]), price, adv or None, spread, participation)
        mv = abs(float(p["quantity"]) * price)
        total_mv += mv
        total_cost += prof["liquidity_cost"] or 0.0
        rows.append({"symbol": s, "book": p.get("book"), "quantity": p["quantity"], "market_value": round(mv, 2),
                     "adv_shares_20d": round(adv) if adv else None, **prof})
    worst = max((r.get("days_to_liquidate") or 0 for r in rows), default=0)
    return {"available": True, "participation_rate": participation, "positions": rows,
            "liquidity_cost_total": round(total_cost, 2), "gross_market_value": round(total_mv, 2),
            "max_days_to_liquidate": round(worst, 2),
            "method": (f"Days to liquidate = |quantity| ÷ ({participation:.0%} × 20-day average volume). Liquidity "
                       "cost = half the Corwin–Schultz high/low spread estimate × market value; LVaR = VaR + this cost.")}


def lots(book: Optional[str] = None) -> Dict[str, Any]:
    pos, trades, _, _ = _book(book)
    out = {}
    for p in pos:
        s = str(p["symbol"]).upper()
        mine = [t for t in trades if str(t["symbol"]).upper() == s]
        traded = sum(float(t["quantity"]) * (1 if str(t["side"]).upper() in ("BUY", "COVER") else -1) for t in mine)
        opening = float(p["quantity"]) - traded
        fills = ([{"date": p.get("entry_date") or "", "side": "BUY" if opening > 0 else "SELL",
                   "quantity": abs(opening), "price": float(p.get("avg_cost") or 0), "source": "opening position"}]
                 if abs(opening) > 1e-9 else [])
        fills += [{"date": str(t["ts"])[:10], "side": t["side"], "quantity": t["quantity"], "price": t["price"],
                   "source": t.get("source") or "trade"} for t in mine]
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
                                                          "opening lot at their average cost and entry date."}


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
    from api import portfolio_store
    fills = []
    with portfolio_store._conn() as c:
        tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for r in c.execute("SELECT ts, symbol, side, quantity, price, source FROM trades ORDER BY ts DESC LIMIT ?", (limit,)):
            fills.append({"book": "Fund", "symbol": r["symbol"], "side": r["side"], "shares": r["quantity"],
                          "fill_date": str(r["ts"])[:10], "fill_price": r["price"], "decision_date": str(r["ts"])[:10],
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
