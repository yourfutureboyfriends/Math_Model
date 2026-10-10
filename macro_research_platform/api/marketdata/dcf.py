"""
Discounted cash flow valuation — free cash flow to the firm (FCFF) at the weighted average
cost of capital, following Damodaran and Koller/Goedhart/Wessels (McKinsey, "Valuation").

  Revenue      grows at g₁ in year 1 (analysts' current-year consensus) and g₂ in years 2–3
               (next-year consensus), then fades linearly to the terminal rate g∞ by year N
  Margin       operating (EBIT) margin moves linearly from today's to a target by year N
  NOPAT        EBIT × (1 − tax). GAAP EBIT already expenses stock-based compensation, so
               SBC is treated as the real cost it is (Damodaran) — never added back
  Reinvestment ΔRevenue ÷ sales-to-capital (capital needed to grow; Damodaran)
  FCFF         NOPAT − reinvestment, discounted at WACC with the mid-year convention
  Terminal     value-driver formula: NOPAT_{N+1} × (1 − g∞ / RONIC) ÷ (WACC − g∞)
               (McKinsey) — growth must be paid for with reinvestment; RONIC = WACC by
               default (new investment earns its cost of capital: no further value creation)
  WACC         cost of equity = risk-free + β × ERP, all market-based (Damodaran):
               · ERP = his latest monthly implied premium for the S&P 500 + the home
                 country's risk premium (over the US's)
               · β bottom-up: the industry's unlevered beta (corrected for cash) relevered
                 at the firm's market D/E — far less noisy than a single regression beta
               · risk-free = 10-year government yield in the cash-flow currency, less the
                 sovereign default spread where the government itself is not default-free
               after-tax cost of debt; market-value equity, book debt
  Growth ∞     = the risk-free rate (Damodaran's default — the same assumption his implied
               ERP is solved with, so the two are consistent)
  Equity       enterprise value − debt (incl. leases if chosen) + cash & short-term
               investments + stakes in other companies − minority interest; per diluted
               share. A captive finance arm (car/equipment loans) is carved out: its debt is
               matched by its loan book, so only the industrial business's debt is subtracted
  Reverse DCF  the initial growth rate g₀ that makes the model value equal today's price

Calibration (Oct 2026, 71 large caps across the US, Europe and Asia, financials excluded):
the old setup (regression beta, fixed 4.2% ERP, g∞ = 2.5%) put the median company 28% below
its price — a systematic bias, since the ERP is implied from the market assuming g∞ = rf.
With these defaults the median gap is about −5%, and 69% of companies land within ±50%.

Checks that come back with the result: terminal growth above the risk-free rate (Damodaran:
no firm can outgrow the economy forever), WACC ≤ terminal growth, terminal value share of
enterprise value, negative NOPAT, currency mismatch between financials and share price.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from api.marketdata.core import NotFound, _f, _info, to_usd

ERP_FALLBACK = 0.042           # used only if Damodaran's monthly implied ERP can't be fetched
ERP_DEFAULT = None             # None → live implied ERP + country risk premium
HIGH_GROWTH_YEARS = 3          # years of analyst-driven growth before the fade (calibrated: see tests)
CYCLICAL = {"Semiconductor", "Semiconductor Equip", "Metals & Mining", "Steel", "Oil/Gas (Integrated)", "Oil/Gas (Production and Exploration)",
            "Oilfield Svcs/Equip.", "Coal & Related Energy", "Chemical (Basic)", "Chemical (Diversified)", "Auto & Truck", "Auto Parts",
            "Shipbuilding & Marine", "Paper/Forest Products", "Precious Metals", "Homebuilding", "Air Transport", "Trucking", "Machinery",
            "Computers/Peripherals", "Building Materials", "Farming/Agriculture"}
# currency → the sovereign whose bond sets its risk-free rate (for the default-spread adjustment)
CCY_SOVEREIGN = {"JPY": "Japan", "GBP": "United Kingdom", "EUR": "Germany", "CAD": "Canada", "AUD": "Australia", "CHF": "Switzerland",
                 "KRW": "Korea", "MXN": "Mexico", "ZAR": "South Africa", "INR": "India", "SEK": "Sweden", "NOK": "Norway",
                 "DKK": "Denmark", "NZD": "New Zealand", "BRL": "Brazil"}
# 10-year government bond yield by currency — the risk-free rate must be in the currency of
# the cash flows (Damodaran). OECD long-term yields via FRED (monthly).
RF_SERIES = {"JPY": "IRLTLT01JPM156N", "EUR": "IRLTLT01DEM156N", "GBP": "IRLTLT01GBM156N", "CAD": "IRLTLT01CAM156N",
             "AUD": "IRLTLT01AUM156N", "CHF": "IRLTLT01CHM156N", "KRW": "IRLTLT01KRM156N", "MXN": "IRLTLT01MXM156N",
             "ZAR": "IRLTLT01ZAM156N", "INR": "INDIRLTLT01STM", "SEK": "IRLTLT01SEM156N", "NOK": "IRLTLT01NOM156N",
             "DKK": "IRLTLT01DKM156N", "NZD": "IRLTLT01NZM156N", "BRL": "IRLTLT01BRM156N"}
FINANCIAL_INDUSTRIES = ("bank", "insurance", "capital markets", "credit services", "asset management", "mortgage")


def _rf_persist(ccy: str, fetch) -> Optional[tuple]:
    """Fetch a government yield, remembering the last good value on disk: a FRED timeout must not
    silently swap in the US rate for another currency's cash flows."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "data" / "processed" / "risk_free_cache.json"
    try:
        saved = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        saved = {}
    v = None
    try:
        v = fetch()
    except Exception:
        v = None
    if v:
        saved[ccy] = [v[0], str(v[1])]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(saved))
        except Exception:
            pass
        return v
    if ccy in saved:
        return (saved[ccy][0], f"{saved[ccy][1]}, last saved — FRED unreachable")
    raise RuntimeError("no yield")


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
            v = _cached(f"rf:{ccy}", 86400, lambda: _rf_persist(ccy, fetch))
            if v:
                rate, note = v[0], ""
                try:
                    from api.providers import damodaran
                    ds = damodaran.country_risk(CCY_SOVEREIGN.get(ccy)).get("default_spread") or 0.0
                    if ds > 0:
                        rate, note = v[0] - ds, f" less {ds:.2%} sovereign default spread"
                except Exception:
                    pass
                return {"rate": round(rate, 4), "source": f"{ccy} 10-year government bond (FRED {sid}, {v[1]}){note}", "currency_matched": True}
        except Exception:
            pass
    us = risk_free("USD")
    return {"rate": us["rate"], "source": f"US 10-year Treasury — no {ccy} government yield available", "currency_matched": False}
CAPTIVE_DEBT_SHARE = 0.9        # share of a captive finance loan book funded by debt (~10:1 leverage)
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
            out["currency"] = "USD"            # the EDGAR parser reads USD-denominated facts only
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
        out["currency"] = i.get("financialCurrency") or i.get("currency")     # Yahoo reports in the filing currency
    out["source"] = src
    # Shares: diluted where available
    out["shares"] = _f(i.get("impliedSharesOutstanding")) or _f(i.get("sharesOutstanding"))
    out["market_cap"] = _f(i.get("marketCap"))
    raw_beta = _f(i.get("beta"))
    out["beta_raw"] = raw_beta
    # Blume-adjusted regression beta (0.67 × raw + 0.33) — shown for reference; the model
    # uses the bottom-up beta below when the industry is known.
    out["beta_regression"] = round(0.67 * raw_beta + 0.33, 3) if raw_beta is not None else None
    out["beta"] = out["beta_regression"]
    out["beta_source"] = "regression beta, Blume-adjusted (Yahoo)"
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
    out["sales_to_capital"] = round(min(5.0, max(0.5, stc)), 2) if stc else None
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
    _market_inputs(s, i, out)
    return out


def _balance_extras(symbol: str) -> Dict[str, Optional[float]]:
    """Non-operating stakes and captive-finance receivables from the latest balance sheet."""
    out: Dict[str, Optional[float]] = {"investments": None, "nc_receivables": None, "receivables": None, "book_equity": None,
                                       "cash_financial": None,
                                       "minority_interest": None}
    try:
        import yfinance as yf
        bs = yf.Ticker(symbol).balance_sheet
        if bs is None or bs.empty:
            return out
        def get(k):                      # latest reported value (the newest column can be blank)
            if k not in bs.index:
                return None
            for c in bs.columns[:2]:
                v = _f(bs.loc[k, c])
                if v is not None and v == v:
                    return v
            return None
        out["investments"] = get("Investments And Advances") or get("Long Term Equity Investment")
        out["nc_receivables"] = get("Non Current Accounts Receivable")
        out["receivables"] = get("Receivables") or get("Accounts Receivable")
        out["book_equity"] = get("Common Stock Equity") or get("Stockholders Equity")
        out["minority_interest"] = get("Minority Interest")
        out["cash_financial"] = get("Cash Financial")              # cash held by the financial-services segment
    except Exception:
        pass
    return out


def _market_inputs(symbol: str, info: Dict[str, Any], out: Dict[str, Any]) -> None:
    """Damodaran market data: implied ERP, country risk, industry beta / margin / sales-to-capital,
    analyst growth path, captive finance and non-operating stakes."""
    from api.providers import damodaran
    erp = damodaran.implied_erp()
    out["erp_mature"] = erp.get("erp") or ERP_FALLBACK
    out["erp_source"] = erp.get("source") or f"fallback {ERP_FALLBACK:.1%} (Damodaran's monthly file unavailable)"
    home, us = damodaran.country_risk(out.get("country")), damodaran.country_risk("United States")
    crp = max(0.0, (home.get("crp") or 0.0) - (us.get("crp") or 0.0))
    out["country_risk_premium"], out["country_rating"] = round(crp, 4), home.get("rating")
    out["erp"] = round(out["erp_mature"] + crp, 4)

    # Captive finance: long-dated receivables funded by debt (car / equipment loans)
    rev = out.get("revenue") or 0
    ex = _balance_extras(symbol)
    fin = 0.0
    ncr, cur = ex.get("nc_receivables") or 0.0, ex.get("receivables") or 0.0
    # Trade credit rarely exceeds ~3 months of sales; receivables above half a year's revenue are
    # a loan book (Toyota, Ford, Deere, Caterpillar finance arms).
    fin_cash = 0.0
    # (customers' trade credit is almost never long-dated, so non-current receivables above ~10% of
    # sales are a loan book on their own — Honda's ¥6.8T sat under the 50% total test)
    if rev and ((ncr + cur) > 0.5 * rev or ncr > 0.1 * rev) and not out.get("is_financial"):
        # The finance arm's assets: its loans (receivables beyond ~1 month of trade credit — a
        # manufacturer's own customers pay in weeks) and its own cash. They are funded ~90% by the
        # arm's debt (captive finance runs about 10:1: Toyota Financial Services, Ford Credit, John
        # Deere Financial); the equity-funded ~10% already earns its keep inside operating income,
        # so offsetting it too would count it twice. Industrial debt = total − that funding, and the
        # arm's cash leaves the cash line with it.
        loans = ncr + max(0.0, cur - rev * 30 / 365)
        fin_cash = min(ex.get("cash_financial") or 0.0, out.get("cash") or 0.0)
        fin = min(out.get("debt") or 0.0, (loans + fin_cash) * CAPTIVE_DEBT_SHARE)
    out["captive_finance_receivables"] = fin or None
    out["debt_total"] = out.get("debt")
    if fin:
        out["debt"] = (out.get("debt") or 0.0) - fin
        if fin_cash:
            out["cash"] = (out.get("cash") or 0.0) - fin_cash
        unit, div = ("T", 1e12) if fin >= 1e12 else ("B", 1e9)
        out["debt_source"] = (f"{out.get('debt_source')}; less {fin / div:,.2f}{unit} of debt funding the captive finance arm "
                              f"(90% of its loans" + (f" and its {fin_cash / div:,.2f}{unit} of cash, removed from cash" if fin_cash else "") + ")")
    out["investments"] = ex.get("investments")
    if out.get("equity_book") is None:
        out["equity_book"] = ex.get("book_equity")
    if out.get("minority_interest") is None:          # Yahoo-sourced (non-US) firms: read it off the balance sheet
        out["minority_interest"] = ex.get("minority_interest")
    # Invested capital on the operating (industrial) balance sheet — after the captive-finance
    # carve-out and with book equity now known for non-US firms — drives sales-to-capital and ROIC.
    eq = out.get("equity_book")
    if eq is not None:
        ic = eq + (out.get("debt") or 0.0) - (out.get("cash") or 0.0)
        out["invested_capital"] = ic
        if rev and ic > 0:
            out["sales_to_capital"] = round(min(5.0, max(0.5, rev / ic)), 2)
            if out.get("ebit"):
                out["roic"] = round(out["ebit"] * (1 - (out.get("tax_effective") or out["tax_marginal"])) / ic, 4)
    out["net_income"] = _f(info.get("netIncomeToCommon"))
    pr = _f(info.get("payoutRatio"))
    out["payout_ratio"] = min(1.0, max(0.0, pr)) if pr is not None else None

    # Industry benchmarks
    ind = damodaran.industry(out.get("industry"), out.get("country"))
    out["industry_benchmark"] = ind
    mcap = out.get("market_cap")
    if mcap and out.get("price_currency") and out.get("currency") and out["price_currency"] != out["currency"]:
        usd, per = to_usd(mcap, out["price_currency"]), to_usd(1.0, out["currency"])
        mcap = usd / per if usd and per else None
    out["market_cap_fin_ccy"] = mcap
    bu = ind.get("unlevered_beta")
    if out.get("is_financial") and ind.get("levered_beta"):
        # banks/insurers: debt is raw material, so use the industry's levered (equity) beta as is
        out["beta"] = round(ind["levered_beta"], 3)
        out["beta_source"] = f"{ind['industry']} average equity beta ({ind['region']}, Damodaran)"
    elif bu and mcap:
        de = (out.get("debt") or 0.0) / mcap
        out["beta"] = round(bu * (1 + (1 - out["tax_marginal"]) * de), 3)
        out["beta_source"] = f"bottom-up: {ind['industry']} unlevered β {bu:.2f} ({ind['region']}, cash-corrected), relevered at D/E {de:.2f}"
    out["sales_to_capital_firm"] = out.get("sales_to_capital")
    stc_ind = ind.get("sales_to_capital")
    if stc_ind:
        firm = out["sales_to_capital_firm"]
        if firm:
            # shrink the firm's ratio halfway toward its industry (one year of book capital is noisy)
            out["sales_to_capital"] = round(min(8.0, max(0.5, (firm + stc_ind) / 2)), 2)
            out["sales_to_capital_source"] = f"average of the firm ({firm:.2f}) and {ind['industry']} ({stc_ind:.2f})"
        else:
            out["sales_to_capital"] = round(min(8.0, max(0.5, stc_ind)), 2)
            out["sales_to_capital_source"] = f"{ind['industry']} average ({stc_ind:.2f}) — no book capital for the firm"
    if not out.get("sales_to_capital"):
        out["sales_to_capital"], out["sales_to_capital_source"] = 1.5, "default 1.5 (no firm or industry data)"

    # Growth path: year 1 = current fiscal year consensus, years 2–3 = next fiscal year consensus
    # Growth is recomputed from the estimate levels: Yahoo's own "growth" column uses a wrong
    # year-ago base for many non-US listings (e.g. +195% for Toyota).
    g1 = g2 = None
    hist = _history(symbol)
    try:
        import yfinance as yf
        re_ = yf.Ticker(symbol).revenue_estimate
        if re_ is not None and not re_.empty:
            e0 = _f(re_.loc["0y", "avg"]) if "0y" in re_.index else None
            e1 = _f(re_.loc["+1y", "avg"]) if "+1y" in re_.index else None
            last_fy = hist["revenues"][0] if hist["revenues"] else None
            if e0 and last_fy and last_fy > 0:
                g1 = e0 / last_fy - 1
            if e1 and e0 and e0 > 0:
                g2 = e1 / e0 - 1
    except Exception:
        pass
    # Normalised margin (Damodaran): a one-off loss year shouldn't be projected forever.
    m_now = out.get("margin")
    med = hist["median_margin"]
    out["margin_history"] = hist["margins"]
    if m_now is not None and med is not None and med > 0 and m_now < 0.5 * med:
        out["margin_normalized"] = round(med, 4)
        out["margin_note"] = (f"TTM operating margin {m_now:.1%} is far below the {len(hist['margins'])}-year median {med:.1%} "
                              "(one-off charges?) — the median is used as today's margin")
    ind_m = (out.get("industry_benchmark") or {}).get("margin")
    ind_name = (out.get("industry_benchmark") or {}).get("industry")
    base = out.get("margin_normalized") or m_now
    out["target_margin_default"], out["target_margin_source"] = base, "today's margin held"
    if base is not None and base <= 0.01 and ind_m and ind_m > 0:
        out["target_margin_default"] = round(ind_m, 4)
        out["target_margin_source"] = f"loss-making today: margin converges to the {ind_name} industry margin {ind_m:.1%} (Damodaran)"
    elif base is not None and med is not None and med > 0 and ind_name in CYCLICAL and base > 1.5 * med:
        out["target_margin_default"] = round(med, 4)
        out["target_margin_source"] = (f"cyclical industry at a peak: margin returns from {base:.1%} to its "
                                       f"{len(hist['margins'][:3])}-year median {med:.1%} by the final year")
    clip = lambda g: round(min(0.40, max(-0.15, g)), 4)
    if g1 is not None or g2 is not None:
        out["growth_y1"] = clip(g1 if g1 is not None else g2)
        out["growth"] = clip(g2 if g2 is not None else g1)
        out["growth_source"] = "analyst consensus revenue growth: this fiscal year (year 1), next fiscal year (years 2–3), then a fade to terminal growth"
    else:
        out["growth_y1"] = out.get("growth")


def _history(symbol: str) -> Dict[str, Any]:
    """Last fiscal years' revenue and operating margin (newest first) from Yahoo."""
    out: Dict[str, Any] = {"revenues": [], "margins": [], "median_margin": None}
    try:
        import yfinance as yf
        inc = yf.Ticker(symbol).income_stmt
        if inc is None or inc.empty or "Total Revenue" not in inc.index:
            return out
        for c in inc.columns:
            rev = _f(inc.loc["Total Revenue", c])
            op = _f(inc.loc["Operating Income", c]) if "Operating Income" in inc.index else None
            if rev and rev == rev and rev > 0:
                out["revenues"].append(rev)
                if op is not None and op == op:
                    out["margins"].append(round(op / rev, 4))
        ms = sorted(out["margins"][:3])
        out["median_margin"] = ms[len(ms) // 2] if ms else None
    except Exception:
        pass
    return out


def wacc(inp: Dict[str, Any], beta: Optional[float] = None, erp: Optional[float] = ERP_DEFAULT, include_leases: bool = False) -> Dict[str, Any]:
    rf = inp.get("risk_free") or 0.04
    b = beta if beta is not None else (inp.get("beta") if inp.get("beta") is not None else 1.0)
    if erp is None:
        erp = inp.get("erp") or ERP_FALLBACK
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
          discount: Optional[float] = None, beta: Optional[float] = None, erp: Optional[float] = ERP_DEFAULT, tax: Optional[float] = None,
          include_leases: bool = False, mid_year: bool = True) -> Dict[str, Any]:
    rev0, ebit0 = inp.get("revenue"), inp.get("ebit")
    if not rev0 or ebit0 is None:
        raise NotFound("A DCF values an operating company from its revenue and profits — this instrument (an ETF, index, "
                       "currency, commodity or crypto asset) has none. Use DES, GP or COMP for it instead.")
    shares = inp.get("shares")
    if not shares or shares <= 0:
        raise NotFound("Share count unavailable.")
    if not 3 <= years <= 30:
        raise NotFound("Use 3–30 projection years.")
    w = wacc(inp, beta, erp, include_leases)
    r = discount if discount is not None else w["wacc"]
    rf = inp.get("risk_free") or 0.04
    g0 = inp["growth"] if growth is None else growth                     # years 2–3 (or 1–3 when set by hand)
    g1 = (inp.get("growth_y1", g0) if growth is None else growth)
    gT = max(0.0, rf) if terminal_growth is None else terminal_growth    # Damodaran: stable growth = risk-free rate
    hg = min(HIGH_GROWTH_YEARS, years - 1)
    # Stable-growth cost of capital (Damodaran): a mature firm's beta drifts toward the market's,
    # so the terminal beta is bounded to 0.8–1.2, and the rate moves linearly from today's WACC
    # to it over the fade years. An explicit discount-rate override keeps one rate throughout.
    if discount is not None:
        rT, beta_T = r, None
    else:
        beta_T = min(1.2, max(0.8, w["beta"]))
        ke_T = rf + beta_T * w["erp"]
        rT = w["weight_equity"] * ke_T + w["weight_debt"] * w["cost_of_debt_after_tax"]
    if rT - gT < 0.005:
        raise NotFound(f"Terminal growth ({gT:.2%}) must be at least 0.5 points below the long-run discount rate ({rT:.2%}) — "
                       "otherwise the terminal value explodes. Lower the terminal growth or raise the discount rate.")
    m0 = inp.get("margin_normalized") or ebit0 / rev0
    mT = (inp.get("target_margin_default") if inp.get("target_margin_default") is not None else m0) if target_margin is None else target_margin
    stc = sales_to_capital or inp["sales_to_capital"]
    t_now = tax if tax is not None else (inp.get("tax_effective") if inp.get("tax_effective") is not None else inp["tax_marginal"])
    t_term = inp["tax_marginal"] if tax is None else tax
    # Default RONIC: half of today's excess return persists (between WACC and current ROIC,
    # capped at 30%). RONIC = WACC (McKinsey's no-moat case) is available as an input.
    roic = inp.get("roic")
    default_ron = min(0.30, rT + 0.5 * (roic - rT)) if roic is not None and roic > rT else rT
    ron = default_ron if ronic is None else ronic
    if ron <= max(0.0, gT):
        raise NotFound(f"Return on new capital ({ron:.2%}) must exceed terminal growth ({gT:.2%}): growing faster than the "
                       "return on reinvestment would need more than 100% of profits reinvested, forever.")

    rows: List[Dict[str, Any]] = []
    rev, pv_sum, cum = rev0, 0.0, 1.0
    for y in range(1, years + 1):
        if y == 1:
            g = g1
        elif y <= hg:
            g = g0
        else:                                                               # linear fade to g∞ by year N
            g = g0 + (gT - g0) * (y - hg) / (years - hg)
        m = m0 + (mT - m0) * (y / years)
        tx = t_now + (t_term - t_now) * (y / years)
        new_rev = rev * (1 + g)
        ebit = new_rev * m
        nopat = ebit * (1 - tx) if ebit > 0 else ebit                       # no tax shield modelled on losses
        reinvest = (new_rev - rev) / stc
        fcff = nopat - reinvest
        r_y = r if y <= hg else r + (rT - r) * (y - hg) / (years - hg)
        df = cum / (1 + r_y) ** (0.5 if mid_year else 1.0)
        cum /= (1 + r_y)
        pv_sum += fcff * df
        rows.append({"year": y, "growth": g, "revenue": new_rev, "margin": m, "ebit": ebit, "tax_rate": tx, "nopat": nopat,
                     "reinvestment": reinvest, "fcff": fcff, "discount_rate": r_y, "discount_factor": df, "pv": fcff * df})
        rev = new_rev
    last = rows[-1]
    nopat_next = last["revenue"] * (1 + gT) * mT * (1 - t_term)
    fcff_next = nopat_next * (1 - gT / ron)
    tv = fcff_next / (rT - gT)
    tv_df = cum * ((1 + rT) ** 0.5 if mid_year else 1.0)                    # mid-year consistent with the flows
    pv_tv = tv * tv_df
    ev = pv_sum + pv_tv
    debt = (inp.get("debt") or 0) + ((inp.get("leases") or 0) if include_leases else 0)
    eq = ev - debt + (inp.get("cash") or 0) + (inp.get("investments") or 0) - (inp.get("minority_interest") or 0)
    equity_negative = eq < 0
    eq_raw = eq
    if equity_negative:
        eq = 0.0           # limited liability: shareholders can't lose more than their stake
    per_share = eq / shares
    price = inp.get("price")
    per_share_fin = per_share
    if inp.get("currency") != inp.get("price_currency"):
        # Reports in one currency, trades in another (or as an ADR): scale by market cap so the
        # value per share is in the trading currency and units (pence, ADR ratios) are right.
        mc = inp.get("market_cap")
        eq_usd, mc_usd = to_usd(eq, inp.get("currency")), to_usd(mc, inp.get("price_currency")) if mc else None
        per_share = price * eq_usd / mc_usd if price and eq_usd is not None and mc_usd else None
        if per_share is None:
            price = None
    checks = []
    if gT > rf + 1e-9:
        checks.append(f"Terminal growth {gT:.1%} is above the risk-free rate {rf:.1%} — no company can outgrow the economy forever (Damodaran).")
    if pv_tv / ev > 0.8 if ev > 0 else False:
        checks.append(f"{pv_tv / ev:.0%} of the value is in the terminal value — the answer depends mostly on the long run.")
    if equity_negative:
        checks.insert(0, f"The operating business is worth less than its debt (equity {eq_raw / 1e6:,.0f}m before the floor): on these "
                         "assumptions the shares are worth only their option value on a turnaround — shown as 0.")
    if inp.get("margin_note"):
        checks.append(inp["margin_note"] + ".")
    if ebit0 <= 0 and not inp.get("margin_normalized"):
        checks.append("Operating income is negative today: the value rests on the margin reaching your target.")
    if ron < rT:
        checks.append("RONIC below WACC means growth destroys value in the terminal period.")
    if inp.get("currency") != inp.get("price_currency"):
        checks.append(f"Financials are in {inp.get('currency')}, the shares trade in {inp.get('price_currency')}: the value is converted "
                      f"at today's exchange rate ({per_share_fin:,.2f} {inp.get('currency')} per reported share)." if price else
                      f"Financials are in {inp.get('currency')} but the shares trade in {inp.get('price_currency')}, and no exchange rate was available.")
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
    nonop = (inp.get("cash") or 0) + (inp.get("investments") or 0)
    if eq > 0 and nonop > 0.35 * eq:
        checks.append(f"Cash and stakes in other companies are {nonop / eq:.0%} of the equity value"
                      + (" — with a captive finance arm, part of them back its loan book rather than being free to shareholders"
                         if inp.get("captive_finance_receivables") else "")
                      + "; markets usually discount cross-holdings and trapped cash, so treat this part of the value with care.")
    roic_now = inp.get("roic")
    bridge = {"enterprise_value": ev, "debt": -debt, "cash": inp.get("cash") or 0, "investments": inp.get("investments") or 0,
              "minority_interest": -(inp.get("minority_interest") or 0), "equity_value": eq,
              "captive_finance_excluded": inp.get("captive_finance_receivables")}
    return {"model": "fcff", "per_share": per_share, "per_share_reporting_ccy": per_share_fin, "bridge": bridge, "equity_negative": equity_negative, "upside": (per_share / price - 1) if price else None, "enterprise_value": ev, "equity_value": eq,
            "pv_explicit": pv_sum, "pv_terminal": pv_tv, "terminal_share": pv_tv / ev if ev > 0 else None, "terminal_value": tv,
            "terminal_fcff": fcff_next, "terminal_reinvestment_rate": gT / ron,
            "implied_ev_ebit_exit": tv / (nopat_next / (1 - t_term)) if nopat_next > 0 else None,
            "assumptions": {"growth": g0, "growth_y1": g1, "high_growth_years": hg, "terminal_growth": gT, "years": years, "margin_now": m0, "target_margin": mT,
                            "sales_to_capital": stc, "ronic": ron, "discount": r, "discount_terminal": rT, "beta_terminal": beta_T, "tax_now": t_now, "tax_terminal": t_term,
                            "mid_year": mid_year, "include_leases": include_leases, "roic_now": roic_now},
            "wacc": w, "net_debt": debt - (inp.get("cash") or 0), "projection": rows, "checks": checks, "price": price}


def implied_discount(inp: Dict[str, Any], **kw) -> Optional[float]:
    """The discount rate at which the model's value equals today's price — the market's required
    return given these cash flows. A gap to the model WACC shows how much risk the market prices in
    (Japanese automakers: ~6% model vs low-teens implied)."""
    kw = {k: v for k, v in kw.items() if k != "discount"}
    def f(r):
        v = value(inp, **{**kw, "discount": r})
        return None if v["per_share"] is None or not v.get("price") else v["per_share"] - v["price"]
    g = kw.get("terminal_growth")
    g = max(0.0, inp.get("risk_free") or 0.04) if g is None else g
    lo, hi = g + 0.0055, 0.30                              # the rate must stay >0.5pt above terminal growth
    try:
        flo, fhi = f(lo), f(hi)
    except NotFound:
        return None
    if flo is None or fhi is None or flo * fhi > 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        try:
            fm = f(mid)
        except NotFound:
            return None
        if fm is None:
            return None
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi, fhi = mid, fm
    return round((lo + hi) / 2, 4)


def reverse_bound(inp: Dict[str, Any], **kw) -> Optional[str]:
    """When reverse() finds no root: 'below' if even −60% growth is worth more than the price,
    'above' if even +150% growth is worth less."""
    try:
        lo, hi = value(inp, growth=-0.6, **kw), value(inp, growth=1.5, **kw)
    except NotFound:
        return None
    if lo["per_share"] is None or hi["per_share"] is None:
        return None
    return "below" if lo["per_share"] > lo["price"] else "above" if hi["per_share"] < hi["price"] else None


def reverse(inp: Dict[str, Any], **kw) -> Optional[float]:
    """Initial revenue growth g₀ at which the model value equals today's price (bisection)."""
    price = inp.get("price")
    if not price:
        return None
    lo, hi = -0.6, 1.5
    def f(g):
        v = value(inp, growth=g, **kw)
        if v["per_share"] is None:
            raise NotFound("no comparable price")
        return v["per_share"] - v["price"]
    try:
        flo, fhi = f(lo), f(hi)
    except NotFound:
        return None
    if flo * fhi > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        try:
            fm = f(mid)
        except NotFound:
            return None
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



# ── Banks and insurers: excess-return model (Damodaran) ──────────────────────
def value_financial(inp: Dict[str, Any], years: int = 10, roe: Optional[float] = None, terminal_roe: Optional[float] = None,
                    payout: Optional[float] = None, terminal_growth: Optional[float] = None, beta: Optional[float] = None,
                    erp: Optional[float] = ERP_DEFAULT, discount: Optional[float] = None, **_ignored) -> Dict[str, Any]:
    """Equity = book value + PV of future excess returns, (ROE − cost of equity) × book value.
    For banks and insurers debt is raw material, not financing, so FCFF and WACC don't apply."""
    bv0, ni = inp.get("equity_book"), inp.get("net_income")
    if not bv0 or bv0 <= 0 or ni is None:
        raise NotFound("Book equity and net income are needed for the excess-return model (not available).")
    shares = inp.get("shares")
    if not shares or shares <= 0:
        raise NotFound("Share count unavailable.")
    if not 3 <= years <= 30:
        raise NotFound("Use 3–30 projection years.")
    rf = inp.get("risk_free") or 0.04
    b = beta if beta is not None else (inp.get("beta") or 1.0)
    e = erp if erp is not None else (inp.get("erp") or ERP_FALLBACK)
    ke = discount if discount is not None else rf + b * e
    roe0 = roe if roe is not None else min(0.40, max(-0.10, ni / bv0))
    # stable ROE: half of today's excess return persists (as for RONIC in the FCFF model)
    roeT = terminal_roe if terminal_roe is not None else (ke + 0.5 * (roe0 - ke) if roe0 > ke else roe0 + 0.5 * (ke - roe0))
    g = max(0.0, min(rf, ke - 0.01)) if terminal_growth is None else terminal_growth
    if ke - g < 0.005:
        raise NotFound(f"Terminal growth ({g:.2%}) must be at least 0.5 points below the cost of equity ({ke:.2%}).")
    if roeT <= g:
        raise NotFound(f"Stable ROE ({roeT:.2%}) must exceed terminal growth ({g:.2%}).")
    p0 = payout if payout is not None else (inp.get("payout_ratio") if inp.get("payout_ratio") is not None else 0.4)
    pT = 1 - g / roeT                                        # payout consistent with stable growth
    rows, bv, pv_sum = [], bv0, 0.0
    for y in range(1, years + 1):
        f = y / years
        r_y = roe0 + (roeT - roe0) * f
        p_y = p0 + (pT - p0) * f
        excess = (r_y - ke) * bv
        df = 1 / (1 + ke) ** y
        pv_sum += excess * df
        ni_y = r_y * bv
        new_bv = bv + ni_y * (1 - p_y)
        rows.append({"year": y, "roe": r_y, "book_value_start": bv, "net_income": ni_y, "payout": p_y, "dividends": ni_y * p_y,
                     "excess_return": excess, "discount_factor": df, "pv": excess * df, "book_growth": new_bv / bv - 1 if bv else None})
        bv = new_bv
    tv = (roeT - ke) * bv / (ke - g)
    pv_tv = tv / (1 + ke) ** years
    eq = bv0 + pv_sum + pv_tv
    equity_negative = eq < 0
    eq = max(0.0, eq)
    per_share_fin = eq / shares
    price, per_share = inp.get("price"), per_share_fin
    if inp.get("currency") != inp.get("price_currency"):
        mc = inp.get("market_cap")
        eq_usd, mc_usd = to_usd(eq, inp.get("currency")), (to_usd(mc, inp.get("price_currency")) if mc else None)
        per_share = price * eq_usd / mc_usd if price and eq_usd is not None and mc_usd else None
    checks = ["Bank / insurer: valued with Damodaran's excess-return model — book equity plus the present value of returns above "
              "the cost of equity — because debt is a raw material for financial firms, not financing."]
    if roe0 < ke:
        checks.append(f"ROE today ({roe0:.1%}) is below the cost of equity ({ke:.1%}): the firm is worth less than its book value "
                      "unless returns improve.")
    if equity_negative:
        checks.insert(0, "The model value is below zero — shown as 0.")
    return {"model": "excess_return", "per_share": per_share, "per_share_reporting_ccy": per_share_fin, "price": price,
            "upside": (per_share / price - 1) if price and per_share is not None else None,
            "equity_value": eq, "book_value": bv0, "pv_excess": pv_sum, "pv_terminal": pv_tv, "terminal_value": tv,
            "terminal_share": pv_tv / eq if eq > 0 else None, "price_to_book_implied": eq / bv0,
            "assumptions": {"years": years, "roe_now": roe0, "roe_terminal": roeT, "payout_now": p0, "payout_terminal": pT,
                            "terminal_growth": g, "cost_of_equity": ke, "beta": b, "erp": e, "risk_free": rf},
            "wacc": {"wacc": ke, "cost_of_equity": ke, "beta": b, "erp": e, "risk_free": rf, "weight_equity": 1.0, "weight_debt": 0.0,
                     "cost_of_debt_after_tax": None},
            "projection": rows, "checks": checks, "equity_negative": equity_negative}


def reverse_financial(inp: Dict[str, Any], **kw) -> Optional[float]:
    """The sustained ROE (held through the projection and in stable growth) that justifies today's price."""
    price = inp.get("price")
    if not price:
        return None
    def f(r):
        v = value_financial(inp, **{**kw, "roe": r, "terminal_roe": r})
        if v["per_share"] is None:
            raise NotFound("no comparable price")
        return v["per_share"] - price
    lo, hi = (inp.get("risk_free") or 0.04) + 0.006, 0.6      # ROE must exceed stable growth (≤ risk-free)
    try:
        flo, fhi = f(lo), f(hi)
    except NotFound:
        return None
    if flo * fhi > 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        try:
            fm = f(mid)
        except NotFound:
            return None
        if (fm > 0) == (fhi > 0):
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sensitivity_financial(inp: Dict[str, Any], base: Dict[str, Any], **kw) -> Dict[str, Any]:
    a = base["assumptions"]
    kes = [round(a["cost_of_equity"] + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    roes = [round(a["roe_terminal"] + d, 4) for d in (-0.04, -0.02, 0, 0.02, 0.04)]
    grid = []
    for k in kes:
        row = []
        for r in roes:
            try:
                row.append(value_financial(inp, **{**kw, "discount": k, "terminal_roe": r})["per_share"])
            except NotFound:
                row.append(None)
        grid.append(row)
    return {"costs_of_equity": kes, "terminal_roes": roes, "per_share": grid}
