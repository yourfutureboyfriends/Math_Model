"""
Discounted cash flow valuation — free cash flow to the firm (FCFF) at the weighted average
cost of capital, following Damodaran and Koller/Goedhart/Wessels (McKinsey, "Valuation").

  Revenue      grows at g₀ in year 1 and fades linearly to the terminal rate g∞ by year N
  Margin       operating (EBIT) margin moves linearly from today's to a target by year N
  NOPAT        EBIT × (1 − tax). GAAP EBIT already expenses stock-based compensation, so
               SBC is treated as the real cost it is (Damodaran) — never added back
  Reinvestment ΔRevenue ÷ sales-to-capital (capital needed to grow; Damodaran)
  FCFF         NOPAT − reinvestment, discounted at WACC with the mid-year convention
  Terminal     value-driver formula: NOPAT_{N+1} × (1 − g∞ / RONIC) ÷ (WACC − g∞)
               (McKinsey) — growth must be paid for with reinvestment; RONIC = WACC by
               default (new investment earns its cost of capital: no further value creation)
  WACC         cost of equity = risk-free + β × ERP (ERP default 4.2%, Damodaran's implied
               ERP for 2026); after-tax cost of debt; market-value equity, book debt
  Equity       enterprise value − debt (incl. leases if chosen) + cash & short-term
               investments − minority interest; per diluted share
  Reverse DCF  the initial growth rate g₀ that makes the model value equal today's price

Checks that come back with the result: terminal growth above the risk-free rate (Damodaran:
no firm can outgrow the economy forever), WACC ≤ terminal growth, terminal value share of
enterprise value, negative NOPAT, currency mismatch between financials and share price.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from api.marketdata.core import NotFound, _f, _info, to_usd

ERP_DEFAULT = 0.042            # Damodaran implied ERP, mid-2026
# 10-year government bond yield by currency — the risk-free rate must be in the currency of
# the cash flows (Damodaran). OECD long-term yields via FRED (monthly).
RF_SERIES = {"JPY": "IRLTLT01JPM156N", "EUR": "IRLTLT01DEM156N", "GBP": "IRLTLT01GBM156N", "CAD": "IRLTLT01CAM156N",
             "AUD": "IRLTLT01AUM156N", "CHF": "IRLTLT01CHM156N", "KRW": "IRLTLT01KRM156N", "MXN": "IRLTLT01MXM156N",
             "ZAR": "IRLTLT01ZAM156N", "INR": "INDIRLTLT01STM", "SEK": "IRLTLT01SEM156N", "NOK": "IRLTLT01NOM156N",
             "DKK": "IRLTLT01DKM156N", "NZD": "IRLTLT01NZM156N", "BRL": "IRLTLT01BRM156N"}
FINANCIAL_INDUSTRIES = ("bank", "insurance", "capital markets", "credit services", "asset management", "mortgage")


def risk_free(currency: Optional[str]) -> Dict[str, Any]:
    """10-year government yield for the cash-flow currency (decimal) with its source."""
    from api.marketdata.core import _cached
    ccy = (currency or "USD").upper()
    if ccy in ("USD", "HKD"):                       # HKD is pegged to the dollar
        try:
            from api.marketdata.core import quote
            return {"rate": round((quote("^TNX")["price"] or 0) / 100, 4), "source": "US 10-year Treasury (^TNX)", "currency_matched": True}
        except Exception:
            return {"rate": 0.04, "source": "default 4% (live rate unavailable)", "currency_matched": True}
    sid = RF_SERIES.get(ccy)
    if sid:
        def fetch():
            from api.providers.fred_provider import FREDProvider
            res = FREDProvider().fetch_series(sid)
            obs = [o for o in (res.data or []) if o.value is not None]
            return (obs[-1].value / 100, obs[-1].date) if obs else None
        try:
            v = _cached(f"rf:{ccy}", 86400, fetch)
            if v:
                return {"rate": round(v[0], 4), "source": f"{ccy} 10-year government bond (FRED {sid}, {v[1]})", "currency_matched": True}
        except Exception:
            pass
    us = risk_free("USD")
    return {"rate": us["rate"], "source": f"US 10-year Treasury — no {ccy} government yield available", "currency_matched": False}
MARGINAL_TAX_US = 0.21
MARGINAL_TAX_OTHER = 0.25


def inputs(symbol: str) -> Dict[str, Any]:
    """Model inputs from SEC filings (US filers) or Yahoo (everyone else), with sources."""
    s = symbol.strip().upper()
    i = _info(s)
    out: Dict[str, Any] = {"symbol": s, "name": i.get("longName") or i.get("shortName"),
                           "currency": i.get("financialCurrency") or i.get("currency"), "price_currency": i.get("currency"),
                           "price": _f(i.get("regularMarketPrice")) or _f(i.get("currentPrice")), "country": i.get("country")}
    src = None
    try:
        from api.providers import sec_edgar
        if sec_edgar.resolve(s):
            st = sec_edgar.statements(s)
            t, b = st["ttm"], st.get("balance") or {}
            out.update({"revenue": t.get("revenue"), "ebit": t.get("operating_income"), "pretax_income": t.get("pretax_income"),
                        "income_tax": t.get("income_tax"), "interest_expense": t.get("interest_expense"), "sbc": t.get("sbc"),
                        "dna": t.get("dna"), "capex": t.get("capex"), "operating_cash_flow": t.get("operating_cash_flow"),
                        "cash": (b.get("cash") or 0) + (b.get("short_term_investments") or 0) if b.get("cash") is not None else None,
                        # Finance leases are debt under GAAP; operating leases are a separate toggle.
                        "debt": ((b.get("long_term_debt") or 0) + (b.get("short_term_debt") or 0) + (b.get("finance_lease") or 0))
                                if (b.get("long_term_debt") is not None or b.get("short_term_debt") is not None) else None,
                        "leases": b.get("operating_lease"), "minority_interest": b.get("minority_interest"), "equity_book": b.get("equity"),
                        "as_of": t.get("as_of")})
            src = "SEC EDGAR (TTM and latest balance sheet, as filed)"
    except Exception:
        pass
    if src is None or out.get("revenue") is None or out.get("ebit") is None:
        rev = _f(i.get("totalRevenue"))
        om = _f(i.get("operatingMargins"))
        out.update({"revenue": rev, "ebit": rev * om if rev and om is not None else None, "pretax_income": None, "income_tax": None,
                    "interest_expense": None, "sbc": None, "dna": None, "capex": None,
                    "operating_cash_flow": _f(i.get("operatingCashflow")), "cash": _f(i.get("totalCash")), "debt": _f(i.get("totalDebt")),
                    "leases": None, "minority_interest": None, "equity_book": None, "as_of": None})
        src = "Yahoo Finance (TTM)"
    out["source"] = src
    # Shares: diluted where available
    out["shares"] = _f(i.get("impliedSharesOutstanding")) or _f(i.get("sharesOutstanding"))
    out["market_cap"] = _f(i.get("marketCap"))
    raw_beta = _f(i.get("beta"))
    out["beta_raw"] = raw_beta
    # Blume-adjusted beta (0.67 × raw + 0.33), Bloomberg's default: raw regression betas are
    # noisy and mean-revert toward 1.
    out["beta"] = round(0.67 * raw_beta + 0.33, 3) if raw_beta is not None else None
    rfi = risk_free(out["currency"])
    out["risk_free"], out["risk_free_source"], out["risk_free_matched"] = rfi["rate"], rfi["source"], rfi["currency_matched"]
    rf = out["risk_free"] or 0.04
    # Debt cross-check: filers tag debt inconsistently — if the filing-based figure is missing
    # or far below Yahoo's total debt, use Yahoo's (and say so).
    y_debt = _f(i.get("totalDebt"))
    if y_debt and (out.get("debt") is None or out["debt"] < 0.25 * y_debt):     # clearly a missing tag
        out["debt"], out["debt_source"] = y_debt, "Yahoo total debt (filing tags incomplete)"
    else:
        out["debt_source"] = src
    ind = (i.get("industry") or "").lower()
    out["industry"] = i.get("industry")
    out["is_financial"] = any(k in ind for k in FINANCIAL_INDUSTRIES) or (i.get("sector") or "") == "Financial Services"
    # Effective tax rate (bounded), marginal rate for the long run
    pt, tx = out.get("pretax_income"), out.get("income_tax")
    eff = tx / pt if pt and tx is not None and pt > 0 else None
    out["tax_effective"] = round(min(0.35, max(0.0, eff)), 4) if eff is not None else None
    us = (out.get("country") or "").lower() in ("united states", "usa", "us")
    out["tax_marginal"] = MARGINAL_TAX_US if us else MARGINAL_TAX_OTHER
    # Pre-tax cost of debt: interest ÷ debt, bounded to [rf, rf + 6%]; else rf + 1.5%
    debt, intr = out.get("debt"), out.get("interest_expense")
    kd = intr / debt if debt and intr and debt > 0 else None
    out["cost_of_debt"] = round(min(rf + 0.06, max(rf, kd)), 4) if kd is not None else round(rf + 0.015, 4)
    # Sales-to-capital: revenue ÷ invested capital (book equity + debt − cash), bounded
    rev, eq = out.get("revenue"), out.get("equity_book")
    ic = (eq or 0) + (debt or 0) - (out.get("cash") or 0) if eq is not None else None
    stc = rev / ic if rev and ic and ic > 0 else None
    out["sales_to_capital"] = round(min(5.0, max(0.5, stc)), 2) if stc else 1.5
    out["invested_capital"] = ic
    # Starting growth: analysts' consensus revenue growth for next fiscal year (then this year),
    # else Yahoo's latest year-on-year — bounded to −10%…30%.
    g, gsrc = None, None
    try:
        import yfinance as yf
        re_ = yf.Ticker(s).revenue_estimate
        if re_ is not None and not re_.empty:
            for per in ("+1y", "0y"):
                if per in re_.index and _f(re_.loc[per, "growth"]) is not None:
                    g, gsrc = _f(re_.loc[per, "growth"]), f"analyst consensus revenue growth ({per})"
                    break
    except Exception:
        pass
    if g is None:
        g, gsrc = _f(i.get("revenueGrowth")), "latest year-on-year revenue growth"
    out["growth"] = round(min(0.30, max(-0.10, g)), 4) if g is not None else 0.05
    out["growth_source"] = gsrc or "default 5%"
    out["margin"] = round(out["ebit"] / rev, 4) if out.get("ebit") is not None and rev else None
    out["roic"] = round(out["ebit"] * (1 - (out["tax_effective"] or out["tax_marginal"])) / ic, 4) if out.get("ebit") and ic and ic > 0 else None
    return out


def wacc(inp: Dict[str, Any], beta: Optional[float] = None, erp: float = ERP_DEFAULT, include_leases: bool = False) -> Dict[str, Any]:
    rf = inp.get("risk_free") or 0.04
    b = beta if beta is not None else (inp.get("beta") if inp.get("beta") is not None else 1.0)
    ke = rf + b * erp
    debt = (inp.get("debt") or 0) + ((inp.get("leases") or 0) if include_leases else 0)
    # Equity at market value; convert to the financial-statement currency if needed
    mcap = inp.get("market_cap")
    if mcap and inp.get("price_currency") and inp.get("currency") and inp["price_currency"] != inp["currency"]:
        usd = to_usd(mcap, inp["price_currency"])
        per_fin = to_usd(1.0, inp["currency"])
        mcap = usd / per_fin if usd and per_fin else None
    E, D = (mcap or 0), debt
    kd_after = inp["cost_of_debt"] * (1 - inp["tax_marginal"])
    w = (E * ke + D * kd_after) / (E + D) if E + D > 0 else ke
    return {"wacc": w, "cost_of_equity": ke, "cost_of_debt_after_tax": kd_after, "beta": b, "erp": erp, "risk_free": rf,
            "weight_equity": E / (E + D) if E + D > 0 else 1.0, "weight_debt": D / (E + D) if E + D > 0 else 0.0}


def value(inp: Dict[str, Any], growth: Optional[float] = None, terminal_growth: Optional[float] = None, years: int = 10,
          target_margin: Optional[float] = None, sales_to_capital: Optional[float] = None, ronic: Optional[float] = None,
          discount: Optional[float] = None, beta: Optional[float] = None, erp: float = ERP_DEFAULT, tax: Optional[float] = None,
          include_leases: bool = False, mid_year: bool = True) -> Dict[str, Any]:
    rev0, ebit0 = inp.get("revenue"), inp.get("ebit")
    if not rev0 or ebit0 is None:
        raise NotFound("Revenue and operating income are needed for a DCF (not available for this instrument).")
    shares = inp.get("shares")
    if not shares or shares <= 0:
        raise NotFound("Share count unavailable.")
    if not 3 <= years <= 20:
        raise NotFound("Use 3–20 projection years.")
    w = wacc(inp, beta, erp, include_leases)
    r = discount if discount is not None else w["wacc"]
    rf = inp.get("risk_free") or 0.04
    g0 = inp["growth"] if growth is None else growth
    gT = min(rf, 0.025) if terminal_growth is None else terminal_growth
    if r <= gT:
        raise NotFound("The discount rate must exceed terminal growth.")
    m0 = ebit0 / rev0
    mT = m0 if target_margin is None else target_margin
    stc = sales_to_capital or inp["sales_to_capital"]
    t_now = tax if tax is not None else (inp.get("tax_effective") if inp.get("tax_effective") is not None else inp["tax_marginal"])
    t_term = inp["tax_marginal"] if tax is None else tax
    # Default RONIC: half of today's excess return persists (between WACC and current ROIC,
    # capped at 30%). RONIC = WACC (McKinsey's no-moat case) is available as an input.
    roic = inp.get("roic")
    default_ron = min(0.30, r + 0.5 * (roic - r)) if roic is not None and roic > r else r
    ron = default_ron if ronic is None else ronic
    if ron <= 0:
        raise NotFound("RONIC must be positive.")

    rows: List[Dict[str, Any]] = []
    rev, pv_sum = rev0, 0.0
    for y in range(1, years + 1):
        frac = (y - 1) / max(1, years - 1)                                  # 0 in year 1 → 1 in year N
        g = g0 + (gT - g0) * frac
        m = m0 + (mT - m0) * (y / years)
        tx = t_now + (t_term - t_now) * (y / years)
        new_rev = rev * (1 + g)
        ebit = new_rev * m
        nopat = ebit * (1 - tx) if ebit > 0 else ebit                       # no tax shield modelled on losses
        reinvest = (new_rev - rev) / stc
        fcff = nopat - reinvest
        t_disc = y - 0.5 if mid_year else y
        df = 1 / (1 + r) ** t_disc
        pv_sum += fcff * df
        rows.append({"year": y, "growth": g, "revenue": new_rev, "margin": m, "ebit": ebit, "tax_rate": tx, "nopat": nopat,
                     "reinvestment": reinvest, "fcff": fcff, "discount_factor": df, "pv": fcff * df})
        rev = new_rev
    last = rows[-1]
    nopat_next = last["revenue"] * (1 + gT) * mT * (1 - t_term)
    fcff_next = nopat_next * (1 - gT / ron)
    tv = fcff_next / (r - gT)
    tv_df = 1 / (1 + r) ** (years - 0.5 if mid_year else years)            # perpetuity method: mid-year consistent
    pv_tv = tv * tv_df
    ev = pv_sum + pv_tv
    debt = (inp.get("debt") or 0) + ((inp.get("leases") or 0) if include_leases else 0)
    eq = ev - debt + (inp.get("cash") or 0) - (inp.get("minority_interest") or 0)
    per_share = eq / shares
    price = inp.get("price") if inp.get("currency") == inp.get("price_currency") else None
    checks = []
    if gT > rf + 1e-9:
        checks.append(f"Terminal growth {gT:.1%} is above the risk-free rate {rf:.1%} — no company can outgrow the economy forever (Damodaran).")
    if pv_tv / ev > 0.8 if ev > 0 else False:
        checks.append(f"{pv_tv / ev:.0%} of the value is in the terminal value — the answer depends mostly on the long run.")
    if ebit0 <= 0:
        checks.append("Operating income is negative today: the value rests on the margin reaching your target.")
    if ron < r:
        checks.append("RONIC below WACC means growth destroys value in the terminal period.")
    if price is None:
        checks.append(f"Financials are in {inp.get('currency')} but the shares trade in {inp.get('price_currency')}: compare value per share in the same currency.")
    if inp.get("is_financial"):
        checks.insert(0, "Financial firm: for banks and insurers debt is raw material, not financing, so an FCFF model is not "
                         "meaningful — use dividend or excess-return (book value × (ROE − cost of equity)) models instead.")
    if w["weight_debt"] > 0.5 and not inp.get("is_financial"):
        checks.append(f"Debt is {w['weight_debt']:.0%} of capital — if it funds a captive finance arm (e.g. car loans), "
                      "value that arm separately; mixing it into FCFF overstates the operating business.")
    if not inp.get("risk_free_matched", True):
        checks.append(f"No government yield in {inp.get('currency')} is available, so the US rate is used — the discount rate "
                      "should be in the currency of the cash flows (adjust it for the inflation difference).")
    if (inp.get("leases") or 0) > 0 and not include_leases:
        checks.append("Operating leases are excluded from debt (enable them for a lease-adjusted value, as Damodaran does).")
    roic_now = inp.get("roic")
    return {"per_share": per_share, "upside": (per_share / price - 1) if price else None, "enterprise_value": ev, "equity_value": eq,
            "pv_explicit": pv_sum, "pv_terminal": pv_tv, "terminal_share": pv_tv / ev if ev > 0 else None, "terminal_value": tv,
            "terminal_fcff": fcff_next, "terminal_reinvestment_rate": gT / ron,
            "implied_ev_ebit_exit": tv / (nopat_next / (1 - t_term)) if nopat_next > 0 else None,
            "assumptions": {"growth": g0, "terminal_growth": gT, "years": years, "margin_now": m0, "target_margin": mT,
                            "sales_to_capital": stc, "ronic": ron, "discount": r, "tax_now": t_now, "tax_terminal": t_term,
                            "mid_year": mid_year, "include_leases": include_leases, "roic_now": roic_now},
            "wacc": w, "net_debt": debt - (inp.get("cash") or 0), "projection": rows, "checks": checks, "price": price}


def reverse(inp: Dict[str, Any], **kw) -> Optional[float]:
    """Initial revenue growth g₀ at which the model value equals today's price (bisection)."""
    price = inp.get("price") if inp.get("currency") == inp.get("price_currency") else None
    if not price:
        return None
    lo, hi = -0.3, 1.0
    f = lambda g: value(inp, growth=g, **kw)["per_share"] - price
    try:
        flo, fhi = f(lo), f(hi)
    except NotFound:
        return None
    if flo * fhi > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (fhi > 0):
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sensitivity(inp: Dict[str, Any], base: Dict[str, Any], **kw) -> Dict[str, Any]:
    a = base["assumptions"]
    rs = [round(a["discount"] + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gs = [round(a["terminal_growth"] + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    grid = []
    for r in rs:
        row = []
        for g in gs:
            try:
                row.append(value(inp, **{**kw, "discount": r, "terminal_growth": g})["per_share"] if r > g else None)
            except NotFound:
                row.append(None)
        grid.append(row)
    ms = [round(a["target_margin"] + d, 4) for d in (-0.05, -0.025, 0, 0.025, 0.05)]
    g0s = [round(a["growth"] + d, 4) for d in (-0.05, -0.025, 0, 0.025, 0.05)]
    grid2 = []
    for m in ms:
        row = []
        for g in g0s:
            try:
                row.append(value(inp, **{**kw, "target_margin": m, "growth": g})["per_share"])
            except NotFound:
                row.append(None)
        grid2.append(row)
    return {"discount_rates": rs, "terminal_growth": gs, "per_share": grid,
            "target_margins": ms, "growth_rates": g0s, "per_share_growth_margin": grid2}
