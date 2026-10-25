"""
Pre-trade feasibility assessment for the Head of Trading: how to implement an order the Portfolio Management
Committee has approved (it never replaces that approval, and never places an order).

For one proposed order (symbol, side, quantity or base-currency amount) it gathers, with every input labelled
observed / estimated / assumption / unavailable:

  security       venue, country, currency, developed-market check, the analyst pitch and its PMC status
  price          last price, bid / ask, market state and the quote's timestamp (delayed / closed flagged)
  size           quantity, amount in local and base currency, weight before → after
  liquidity      20/30-session average volume and traded value, participation, sessions needed at the cap
  costs          spread (observed when the market is open, else a model estimate), market impact (square-root model
                 estimate), commission (fund setting), transfer taxes (statutory), FX conversion (assumption)
  technicals     RSI, moving averages, MACD, Bollinger, ATR, volatility, volume anomaly, levels, relative strength
                 against the fund's benchmark, drawdowns (api/calculations/technicals.py)
  events         next earnings, ex-dividend, the currency's high / medium-impact releases and central-bank decision
                 in the execution window, exchange holidays and the next session
  mandate        long-only, developed-market listing, max position, max sector, min cash, max participation and
                 days to execute (fund setting "mandate")
  valuation      probability-weighted fair value from the pitch, expected return, reward / risk, entry range,
                 kill criteria

→ flags (block / warn / info) and an execution suggestion (one session, staged over N sessions at a participation
cap, wait for an event, limit range). Estimated spreads and impact are never shown as observed market data.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

# MSCI's 23 developed markets (MSCI World countries). Constituency itself is licensed: a developed-market listing is
# checked, membership of the index is not verifiable with free data.
DEVELOPED = {"US", "CA", "GB", "IE", "FR", "DE", "NL", "BE", "LU", "CH", "AT", "SE", "NO", "DK", "FI", "ES", "PT", "IT",
             "JP", "AU", "NZ", "HK", "SG", "IL"}

DEFAULT_MANDATE = {"long_only": True, "developed_markets_only": True, "max_position_pct": 0.10, "max_sector_pct": 0.35,
                   "min_cash_pct": 0.01, "max_participation": 0.10, "max_days_to_execute": 5,
                   "fx_conversion_bps": 5.0}

SUFFIX_MIC = {"L": "XLON", "DE": "XETR", "F": "XETR", "PA": "XPAR", "AS": "XAMS", "MC": "XMAD", "SW": "XSWX",
              "T": "XJPX", "HK": "XHKG", "AX": "XASX", "TO": "XTSE", "V": "XTSE", "SI": "XSES", "NZ": "XNZE"}

# Yahoo's profile sector names → GICS (the platform's universe uses GICS), so the sector cap compares like with like
YAHOO_TO_GICS = {"Healthcare": "Health Care", "Technology": "Information Technology",
                 "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
                 "Financial Services": "Financials", "Basic Materials": "Materials"}

IMPACT_BP = 11.2          # bp × √(% of average daily traded value), Frazzini-Israel-Moskowitz (2018) — Code Lab's model


def _flag(flags: List[Dict[str, Any]], level: str, area: str, msg: str) -> None:
    flags.append({"level": level, "area": area, "message": msg})


def _bars_frame(sym: str, period: str = "5y") -> pd.DataFrame:
    from api.market_bars import bars
    b = bars(sym, "1d", period)
    df = pd.DataFrame(b["bars"])
    if df.empty:
        return df
    df.index = pd.to_datetime(df["t"])
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})[["open", "high", "low", "close", "volume"]]
    df.attrs["currency"] = b.get("currency")
    return df


def _mic(sym: str, country: str) -> Optional[str]:
    if "." in sym:
        return SUFFIX_MIC.get(sym.rsplit(".", 1)[1].upper())
    return "XNYS" if country == "US" else None


def assess(symbol: str, side: str, quantity: Optional[float] = None, amount_base: Optional[float] = None,
           participation: Optional[float] = None, pitch_id: Optional[int] = None) -> Dict[str, Any]:
    from api import fund_store, pitches
    from api.calculations import benchmark as bm, fx_accounting as fa, technicals
    from api.handlers.portfolio_analytics import book_in_base
    from api.markets import classify, minor_unit_factor
    from api.marketdata import core, security
    from api.quant.instruments import TAXES

    sym = symbol.strip().upper()
    side = side.strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side is BUY or SELL")
    st = fund_store.get_settings()
    base = st.get("base_currency") or "USD"
    mandate = {**DEFAULT_MANDATE, **(st.get("mandate") or {})}
    cap = float(participation or mandate["max_participation"])
    flags: List[Dict[str, Any]] = []
    out: Dict[str, Any] = {"symbol": sym, "side": side, "base_currency": base, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "disclaimer": "Decision support for implementing a PMC-approved investment. It does not "
                                         "approve trades and places no orders."}

    # ── security and price ────────────────────────────────────────────────
    q = core.quote(sym)
    cls = classify(sym)
    country = (cls.get("country") or "US").upper()
    ccy = q.get("currency") or "USD"
    major, div = minor_unit_factor(ccy)
    price = q.get("price")
    if not price:
        raise ValueError(f"No price for {sym}.")
    qt = q.get("quote_time")
    age_min = round((datetime.now(timezone.utc).timestamp() - qt) / 60) if qt else None
    out["security"] = {"name": q.get("name"), "exchange": q.get("exchange"), "mic": _mic(sym, country), "country": country,
                       "currency": ccy, "market_cap": q.get("market_cap"), "type": q.get("type"),
                       "developed_market_listing": country in DEVELOPED,
                       "msci_world_membership": "not verifiable with free data (constituents are licensed)"}
    out["price"] = {"last": price, "bid": q.get("bid"), "ask": q.get("ask"), "previous_close": q.get("previous_close"),
                    "market_state": q.get("market_state"), "quote_time": datetime.fromtimestamp(qt, timezone.utc).isoformat() if qt else None,
                    "age_minutes": age_min, "delay_minutes": q.get("delay_minutes"), "source": "Yahoo Finance quote",
                    "currency": ccy}
    state = {"PRE": "pre-market", "PREPRE": "pre-market", "POST": "after hours", "POSTPOST": "closed",
             "CLOSED": "closed"}.get(str(q.get("market_state") or "CLOSED").upper(), str(q.get("market_state")).lower())
    if q.get("market_state") not in ("REGULAR",):
        _flag(flags, "info", "price", f"Market {state}: the price is the last close / last trade, not live.")

    # ── size ──────────────────────────────────────────────────────────────
    rate = fa.usd_per_unit(ccy)
    bpu = fa.base_per_usd(base)
    if major == base.upper():
        to_base = 1.0 / div
    elif rate and bpu:
        to_base = rate * bpu
    else:
        raise ValueError(f"No FX rate to convert {ccy} into {base}.")
    if quantity is None:
        if not amount_base or amount_base <= 0:
            raise ValueError("give a quantity or an amount in the base currency")
        quantity = math.floor(amount_base / (price * to_base))
    quantity = abs(float(quantity))
    if quantity <= 0:
        raise ValueError("the amount buys less than one share")
    notional_local = quantity * price
    notional_base = notional_local * to_base
    book = book_in_base()
    nav = book["nav"] or 0.0
    held = sum(float(p["quantity"]) for p in book["positions"] if str(p["symbol"]).upper() == sym)
    held_mv = sum(float(p.get("market_value") or 0) for p in book["positions"] if str(p["symbol"]).upper() == sym)
    signed = quantity if side == "BUY" else -quantity
    after_mv = held_mv + signed * price * to_base
    invested = sum(float(p.get("market_value") or 0) for p in book["positions"])
    cash_before = nav - invested
    out["size"] = {"quantity": quantity, "notional_local": round(notional_local, 2), "notional_base": round(notional_base, 2),
                   "fx_to_base": to_base, "nav": round(nav, 2), "held_quantity": held,
                   "weight_before": round(held_mv / nav, 4) if nav else None, "weight_after": round(after_mv / nav, 4) if nav else None,
                   "cash_before": round(cash_before, 2), "cash_after_est": round(cash_before - signed * price * to_base, 2),
                   "cash_weight_after": round((cash_before - signed * price * to_base) / nav, 4) if nav else None}

    # ── liquidity ─────────────────────────────────────────────────────────
    bars = _bars_frame(sym)
    liq: Dict[str, Any] = {"available": False}
    if len(bars) >= 30:
        v20, v30 = bars["volume"].tail(20), bars["volume"].tail(30)
        tv20 = (bars["close"] * bars["volume"]).tail(20) * to_base
        tv30 = (bars["close"] * bars["volume"]).tail(30) * to_base
        adv20 = float(v20.mean())
        part = quantity / adv20 if adv20 else None
        sessions = math.ceil(quantity / (cap * adv20)) if adv20 else None
        liq = {"available": True, "adv20_shares": round(adv20), "adv20_median_shares": round(float(v20.median())),
               "adv30_shares": round(float(v30.mean())), "adtv20_base": round(float(tv20.mean()), 0),
               "adtv30_base": round(float(tv30.mean()), 0), "order_pct_adv20": round(part, 4) if part is not None else None,
               "participation_cap": cap, "sessions_at_cap": sessions, "source": "daily volume (Yahoo), observed"}
        if part is not None and part > cap:
            _flag(flags, "warn", "liquidity", f"The order is {part:.0%} of 20-day average volume: stage it over {sessions} sessions at ≤{cap:.0%} participation.")
        if sessions and sessions > mandate["max_days_to_execute"]:
            _flag(flags, "block", "liquidity", f"{sessions} sessions at {cap:.0%} participation exceeds the mandate's {mandate['max_days_to_execute']}-day limit — reduce the size.")
    else:
        _flag(flags, "warn", "liquidity", "Under 30 sessions of volume history: liquidity cannot be assessed.")
    out["liquidity"] = liq

    # ── costs (bps of notional) ────────────────────────────────────────────
    costs: Dict[str, Any] = {}
    bid, ask = q.get("bid"), q.get("ask")
    spread_obs = (ask - bid) / ((ask + bid) / 2) * 1e4 / 2 if bid and ask and ask > bid else None
    model_half = None
    if len(bars) >= 63:
        from api.quant.codelab import half_spread_bps
        usd_scale = pd.Series(rate or 1.0, index=bars.index)
        # the same column label on both frames (the model aligns them by column)
        hs = half_spread_bps(bars[["close"]].set_axis([sym], axis=1), bars[["volume"]].set_axis([sym], axis=1),
                             usd_per_unit=usd_scale)
        model_half = float(hs.iloc[-1, 0]) if pd.notna(hs.iloc[-1, 0]) else None
    live = q.get("market_state") == "REGULAR" and spread_obs is not None
    costs["half_spread_bps"] = {"value": round(spread_obs if live else (model_half if model_half is not None else (spread_obs or 0)), 2),
                                "basis": "observed bid/ask (market open)" if live else
                                ("model estimate (volatility and traded value; market closed)" if model_half is not None
                                 else "last quoted bid/ask while closed (not live)"),
                                "observed_last_quote_bps": round(spread_obs, 2) if spread_obs is not None else None,
                                "model_bps": round(model_half, 2) if model_half is not None else None}
    if liq.get("available"):
        day_pct = min(liq["order_pct_adv20"], cap) * 100
        one_day_pct = liq["order_pct_adv20"] * 100
        costs["impact_bps"] = {"staged_at_cap": round(IMPACT_BP * math.sqrt(day_pct), 2),
                               "single_session": round(IMPACT_BP * math.sqrt(one_day_pct), 2),
                               "basis": f"model estimate: {IMPACT_BP} bp × √(% of daily volume), Frazzini-Israel-Moskowitz (2018)"}
    costs["commission_bps"] = {"value": float(st.get("cost_bps") or 0), "basis": "fund setting (assumption)"}
    buy_bps, sell_bps, why = TAXES.get(country, (0.0, 0.0, None))
    tax = buy_bps if side == "BUY" else sell_bps
    costs["taxes_bps"] = {"value": tax, "basis": why or "no transfer tax for this market", "statutory": True}
    fxc = float(mandate["fx_conversion_bps"]) if major != base.upper() else 0.0
    costs["fx_conversion_bps"] = {"value": fxc, "basis": (f"{major}→{base} conversion, assumption (fund setting)" if fxc else "same currency as the fund")}
    total = (costs["half_spread_bps"]["value"] + (costs.get("impact_bps") or {}).get("staged_at_cap", 0)
             + costs["commission_bps"]["value"] + tax + fxc)
    costs["total_bps"] = round(total, 2)
    costs["total_base"] = round(notional_base * total / 1e4, 2)
    costs["note"] = "Spread and impact are estimates unless marked observed; taxes are statutory rates; commission and FX costs are the fund's assumptions."
    out["costs"] = costs
    if total > 75:
        _flag(flags, "warn", "costs", f"Estimated one-way cost of {total:.0f} bp is high — consider limit orders and staging.")

    # ── technicals (benchmark-relative in the base currency) ────────────────
    tech: Dict[str, Any] = {"available": False}
    if len(bars) >= 30:
        try:
            bcode = st.get("benchmark") or "SPY"
            bser = bm.series(bcode, base)["returns"] if bcode in bm.BENCHMARKS else None
            bench_level = (1 + bser).cumprod() if bser is not None else None
            px_base = bm.in_base(sym, base)
            tech = technicals.snapshot(bars, bench_level, px_base)
            tech["benchmark"] = bcode
        except Exception:                                                     # noqa: BLE001
            tech = technicals.snapshot(bars)
    out["technicals"] = tech
    if tech.get("available"):
        if tech.get("rsi14") is not None and (tech["rsi14"] >= 75 or tech["rsi14"] <= 25):
            _flag(flags, "info", "technicals", f"RSI(14) {tech['rsi14']:.0f}: stretched — favour limit orders / staging over market orders.")
        if tech.get("unusual_volume"):
            _flag(flags, "info", "technicals", f"Unusual volume today (z = {tech['volume_z']}): check the news before trading.")
        atrp = tech.get("atr14_pct")
        if atrp:
            tech["suggested_limit_range"] = {"low": round(price * (1 - 0.5 * atrp), 4), "high": round(price * (1 + 0.5 * atrp), 4),
                                             "basis": "last price ± ½ ATR(14)"}

    # ── events in the execution window ────────────────────────────────────
    sessions = (liq.get("sessions_at_cap") or 1) if liq.get("available") else 1
    window_end = date.today() + timedelta(days=max(7, int(sessions * 1.5) + 3))
    ev: Dict[str, Any] = {"window_end": str(window_end)}
    try:
        e = security.earnings(sym)
        up = [x for x in (e.get("upcoming") or []) if x.get("date")]
        if up:
            d = up[0]["date"]
            ev["next_earnings"] = {"date": d, "eps_estimate": up[0].get("eps_estimate"),
                                   "confidence": "as listed by Yahoo (company-confirmed dates are not distinguished — check investor relations)"}
            dd = (date.fromisoformat(d[:10]) - date.today()).days
            if 0 <= dd <= sessions + 2:
                _flag(flags, "warn", "events", f"Earnings on {d} fall inside the execution window — decide whether to trade before, or wait for the results.")
            elif 0 <= dd <= 14:
                _flag(flags, "info", "events", f"Earnings in {dd} days ({d}): a position opened now carries the results risk.")
        ev["earnings_beat_rate"] = e.get("beat_rate")
    except Exception as ex:                                                   # noqa: BLE001
        ev["next_earnings"] = {"unavailable": str(ex)[:120]}
    try:
        dv = security.dividends(sym)
        xd = dv.get("ex_dividend_date")
        if xd:
            xdd = datetime.fromtimestamp(xd, timezone.utc).date()
            ev["ex_dividend"] = {"date": str(xdd), "upcoming": xdd >= date.today(), "dividend_yield": dv.get("dividend_yield")}
            if date.today() <= xdd <= window_end:
                _flag(flags, "info", "events", f"Ex-dividend on {xdd}: buying before it carries the dividend (price drops by it on the day).")
    except Exception:                                                         # noqa: BLE001
        pass
    try:
        from api.marketdata import econ
        rel = [x for x in (econ.calendar(14, None, "Medium").get("events") or [])
               if (x.get("country") or "").upper() in (major, base.upper()) and str(x.get("date", ""))[:10] >= str(date.today())
               and str(x.get("date", ""))[:10] <= str(window_end)]
        ev["macro_releases"] = [{"date": str(x.get("date"))[:16], "currency": x.get("country"), "title": x.get("title"),
                                 "impact": x.get("impact"), "forecast": x.get("forecast")} for x in rel][:12]
        from api.handlers import cb_decisions
        cbs = [b for b in (cb_decisions.next_decisions().get("banks") or []) if b.get("currency") in (major, base.upper())]
        ev["central_banks"] = [{"bank": b.get("bank"), "currency": b.get("currency"), "date": b.get("date"),
                                "consensus": b.get("consensus"), "note": b.get("note")} for b in cbs]
        for b in cbs:
            if b.get("date") and str(date.today()) <= b["date"] <= str(window_end):
                _flag(flags, "info", "events", f"{b['bank']} decision on {b['date']} inside the execution window.")
    except Exception:                                                         # noqa: BLE001
        ev.setdefault("macro_releases", [])
    try:
        from api.marketdata import workbench
        mic = out["security"]["mic"]
        exs = {x["code"]: x for x in workbench.exchanges().get("exchanges") or []}
        x = exs.get(mic) if mic else None
        if x:
            hol = [h for h in x.get("holidays") or [] if h["date"] <= str(window_end)]
            ev["exchange"] = {"mic": mic, "status": x.get("status"), "sessions": x.get("sessions"), "local_time": x.get("local_time"),
                              "next_open_utc": x.get("next_open_utc"), "holidays_in_window": hol}
            if hol:
                _flag(flags, "info", "events", f"Exchange holiday in the window: {', '.join(h['date'] + ' ' + h['name'] for h in hol)}.")
        else:
            ev["exchange"] = {"mic": mic, "note": "hours and holidays not modelled for this venue"}
    except Exception:                                                         # noqa: BLE001
        pass
    out["events"] = ev

    # ── mandate ───────────────────────────────────────────────────────────
    man = []
    def rule(name, ok, detail, level="block"):
        man.append({"rule": name, "passed": bool(ok), "detail": detail})
        if not ok:
            _flag(flags, level, "mandate", f"{name}: {detail}")
    if mandate["long_only"]:
        rule("Long-only", not (side == "SELL" and quantity > held + 1e-9),
             f"selling {quantity:g} with {held:g} held would go short" if side == "SELL" and quantity > held else "no short position")
    if mandate["developed_markets_only"]:
        rule("Developed-market listing", country in DEVELOPED, f"{country} listing" + ("" if country in DEVELOPED else " is outside MSCI's developed markets"))
    wa = out["size"]["weight_after"]
    if wa is not None:
        rule("Max position", wa <= mandate["max_position_pct"] + 1e-9, f"weight after {wa:.2%} vs limit {mandate['max_position_pct']:.0%}")
    caw = out["size"]["cash_weight_after"]
    if caw is not None:
        rule("Min cash", caw >= mandate["min_cash_pct"] - 1e-9, f"cash after {caw:.2%} vs minimum {mandate['min_cash_pct']:.0%}")
    try:
        from api.quant import instruments

        def sector_of(x: str) -> Optional[str]:
            sc = (instruments.meta([x]).get(x) or {}).get("sector")
            if not sc:
                try:
                    sc = (core.profile(x) or {}).get("sector")          # non-US listings: the company profile
                except Exception:                                     # noqa: BLE001
                    sc = None
            return YAHOO_TO_GICS.get(sc, sc) if sc else None
        sect = sector_of(sym)
        if sect and nav:
            sec_mv = sum(float(p.get("market_value") or 0) for p in book["positions"]
                         if sector_of(str(p["symbol"]).upper()) == sect)
            sec_after = (sec_mv + signed * price * to_base) / nav
            rule("Max sector", sec_after <= mandate["max_sector_pct"] + 1e-9, f"{sect} after {sec_after:.2%} vs limit {mandate['max_sector_pct']:.0%}", "warn")
            out["size"]["sector"] = sect
            out["size"]["sector_weight_after"] = round(sec_after, 4)
    except Exception:                                                         # noqa: BLE001
        pass
    out["mandate"] = {"limits": mandate, "checks": man}

    # ── pitch and valuation ───────────────────────────────────────────────
    p = pitches.get(pitch_id) if pitch_id else pitches.latest_for(sym)
    if p:
        cur = p.get("current") or {}
        val = pitches.valuation_vs_price(cur, price)
        try:
            ratios = (core.statements(sym) or {}).get("ratios") or {}
        except Exception:                                                     # noqa: BLE001
            ratios = {}
        entry = None
        for bp in book["positions"]:
            if str(bp["symbol"]).upper() == sym:
                entry = float(bp.get("avg_cost") or 0) or None
        rel = None
        if p.get("approved_price") and tech.get("relative_strength_vs_benchmark") is not None:
            rel = None                                                         # needs the approval-date benchmark level
        kills = pitches.check_kill_criteria(p, price, entry, {k: ratios.get(k) for k in pitches.METRICS}, rel)
        out["pitch"] = {"id": p["id"], "status": p["status"], "analyst": p["analyst"], "version": p["current_version"],
                        "decided_by": p.get("decided_by"), "decided_at": p.get("decided_at"),
                        "horizon_years": cur.get("horizon_years"), "target_weight": cur.get("target_weight"),
                        "entry_range": cur.get("entry_range"), "valuation": val, "kill_criteria": kills,
                        "catalysts": cur.get("catalysts")}
        if p["status"] != "approved" and side == "BUY":
            _flag(flags, "block", "approval", f"Pitch #{p['id']} is {p['status']}, not PMC-approved.")
        if any(k["status"] == "triggered" for k in kills):
            _flag(flags, "block" if side == "BUY" else "warn", "thesis",
                  "Kill criteria triggered: " + "; ".join(k.get("description") or k["type"] for k in kills if k["status"] == "triggered"))
        if val.get("in_entry_range") is False and side == "BUY":
            er = cur.get("entry_range")
            _flag(flags, "warn", "valuation", f"Price {price:g} is outside the pitch's entry range {er['low']:g}–{er['high']:g}: use a limit order or wait.")
        if cur.get("target_weight") and wa is not None and wa > cur["target_weight"] * 1.05:
            _flag(flags, "warn", "size", f"Weight after {wa:.2%} exceeds the approved target {cur['target_weight']:.2%}.")
    elif side == "BUY":
        out["pitch"] = None
        _flag(flags, "warn", "approval", "No pitch on file for this security: PMC approval cannot be confirmed here.")

    # ── suggestion ────────────────────────────────────────────────────────
    blocks = [f for f in flags if f["level"] == "block"]
    warns = [f for f in flags if f["level"] == "warn"]
    steps = []
    if blocks:
        verdict = "do not proceed as proposed"
    elif warns:
        verdict = "proceed with care"
    else:
        verdict = "feasible"
    if liq.get("available"):
        s = liq["sessions_at_cap"] or 1
        steps.append(f"Work the order over {s} session{'s' if s > 1 else ''} at ≤{cap:.0%} of volume" if s > 1 else
                     "Executable in one session within the participation cap")
    lr = (tech or {}).get("suggested_limit_range")
    if lr:
        steps.append(f"Limit range {lr['low']:g}–{lr['high']:g} {ccy} ({lr['basis']})")
    if any(f["area"] == "events" and f["level"] == "warn" for f in flags):
        steps.append("Decide on the event first (trade before, or wait for it)")
    out["flags"] = flags
    out["assessment"] = {"verdict": verdict, "blocking": len(blocks), "warnings": len(warns), "suggested_execution": steps}
    return out
