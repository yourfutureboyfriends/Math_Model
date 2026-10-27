"""
Discounted cash flow valuation — free cash flow to the firm (FCFF) at the weighted average
cost of capital, following Damodaran and Koller/Goedhart/Wessels (McKinsey, "Valuation").

  Revenue      grows at g₁ in year 1 (analysts' current-year consensus) and g₂ in years 2–3
               (next-year consensus), then fades linearly to the terminal rate g∞ by year N
  Margin       operating (EBIT) margin moves linearly from today's to a target by year N
  NOPAT        EBIT × (1 − tax). GAAP EBIT already expenses stock-based compensation, so
               SBC is treated as the real cost it is (Damodaran) — never added back
  Reinvestment ΔRevenue ÷ sales-to-capital (capital needed to grow; Damodaran) — anchored in the first years on
               the company's actual net capital spending (capex − depreciation, scaled with revenue) and blended
               to the sales-to-capital rule by year 5. A pure ratio rule missed 2026's AI build-outs (Oracle: capex
               $76bn on $72bn of revenue, the ratio implied ~$24bn) and overstated light-asset growth
  FCFF         NOPAT − reinvestment, discounted at WACC with the mid-year convention
  Terminal     value-driver formula: NOPAT_{N+1} × (1 − g∞ / RONIC) ÷ (WACC − g∞)
               (McKinsey) — growth must be paid for with reinvestment; by default half of today's
               excess return on capital persists (top-ROIC firms fade but stay above WACC), and
               cyclical / commodity businesses earn exactly their cost of capital on new investment
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
ERP_DEFAULT = None             # None → the mature-market ERP chosen by ERP_BASIS + the country risk premium
# Mature-market equity risk premium. "standard": Kroll's recommended US ERP (5.0% since Sept 2025, reaffirmed
# Jan and Sept 2026; eurozone 5.0–5.5%) — the valuation profession's reference. "implied": Damodaran's monthly
# implied ERP for the S&P 500, which tracks the market (3.7% in Oct 2026, near a record low after a long rally).
ERP_STANDARD = 0.050
ERP_BASIS = "implied"   # calibrated Oct 2026: implied + g = rf left the median company at value/price 1.01 (58 firms)
# Terminal growth. "gdp": the lower of the risk-free rate and the currency's long-run nominal GDP growth (inflation
# target + potential real growth) — inflation is the floor and nominal GDP the ceiling for a perpetual growth rate
# (Delaware Chancery practice); "rf": Damodaran's stable growth = the risk-free rate.
TERMINAL_RULE = "rf"     # consistent with the implied ERP, which is solved assuming g = rf
# Long-run nominal growth by currency: the central bank's inflation target + a conservative potential real growth
# (OECD / IMF long-run estimates, rounded). Used only as a ceiling under the risk-free rate.
LR_NOMINAL_GROWTH = {"USD": 0.040, "EUR": 0.032, "GBP": 0.035, "JPY": 0.025, "CHF": 0.022, "CAD": 0.037, "AUD": 0.045,
                     "NZD": 0.042, "SEK": 0.035, "NOK": 0.035, "DKK": 0.032, "KRW": 0.038, "CNY": 0.055, "HKD": 0.040,
                     "TWD": 0.035, "SGD": 0.040, "INR": 0.09, "BRL": 0.065, "MXN": 0.055, "ZAR": 0.065}
# A cyclical company at a margin peak returns to its through-cycle margin over this many years (normalising
# cyclical earnings — McKinsey, Damodaran), not over the whole forecast.
CYCLICAL_FADE_YEARS = 3
# Years over which reinvestment moves from the firm's actual net capex (year 1) to the sales-to-capital rule.
REINVEST_ANCHOR_YEARS = 5
# Floor on the cost of equity: where the local risk-free rate is held near zero (Swiss franc,
# at times yen and euro) rf + β·ERP can fall to 2–3%, a return no equity investor accepts, and
# the valuation balloons. 5% nominal is a conservative practitioner floor; the screen says when it binds.
KE_FLOOR = 0.05
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
# 'financials' that don't lend or underwrite — exchanges, data vendors, brokers' platforms — have ordinary operating cash flows
NON_LENDER_FINANCIALS = ("financial data", "stock exchange")
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
    # the issuer's daily 10-year (the Bund for the euro) — OECD's FRED series are monthly averages
    daily = {"EUR": "DE", "GBP": "GB", "JPY": "JP", "CAD": "CA", "AUD": "AU"}.get(ccy)
    if daily:
        try:
            from api.marketdata.curves import curves
            c = curves()["curves"].get(daily)
            p10 = next((p for p in (c or {}).get("points", []) if abs(p["tenor"] - 10) < 1e-6), None)
            if p10:
                rate, note = p10["yield"] / 100, ""
                try:
                    from api.providers import damodaran
                    ds = damodaran.country_risk(CCY_SOVEREIGN.get(ccy)).get("default_spread") or 0.0
                    if ds > 0:
                        rate, note = rate - ds, f" less {ds:.2%} sovereign default spread"
                except Exception:
                    pass
                return {"rate": round(rate, 4), "source": f"{ccy} 10-year government bond ({c['source']}, {c['date']}){note}", "currency_matched": True}
        except Exception:
            pass
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
    if ccy in PEGGED_USD:
        return {"rate": us["rate"], "source": f"US 10-year Treasury ({ccy} is pegged to the dollar)", "currency_matched": True}
    if ccy in LT_INFLATION:
        # Damodaran's inflation-differential method: rf_local = (1 + rf_US) × (1 + π_local) / (1 + π_US) − 1
        rate = (1 + us["rate"]) * (1 + LT_INFLATION[ccy]) / (1 + LT_INFLATION["USD"]) - 1
        return {"rate": round(rate, 4), "source": f"US 10-year Treasury adjusted for expected inflation ({ccy} {LT_INFLATION[ccy]:.1%} vs USD "
                                                  f"{LT_INFLATION['USD']:.1%}; Damodaran's inflation-differential method)", "currency_matched": True}
    return {"rate": us["rate"], "source": f"US 10-year Treasury — no {ccy} government yield available", "currency_matched": False}


PEGGED_USD = {"SAR", "AED", "QAR", "BHD", "OMR", "KWD", "PAB"}
# Long-run expected inflation by currency (central-bank targets / IMF medium-term projections), for
# currencies without a usable government-bond feed.
LT_INFLATION = {"USD": 0.023, "CNY": 0.015, "TWD": 0.015, "SGD": 0.02, "THB": 0.015, "MYR": 0.02, "IDR": 0.03, "PHP": 0.03,
                "VND": 0.035, "ILS": 0.025, "PLN": 0.03, "CZK": 0.025, "HUF": 0.035, "CLP": 0.03, "COP": 0.035, "PEN": 0.025,
                "BRL": 0.035, "MXN": 0.035, "ZAR": 0.045, "INR": 0.04, "KRW": 0.02, "TRY": 0.20, "EGP": 0.12, "NGN": 0.15,
                "ARS": 0.30, "SEK": 0.02, "NOK": 0.02, "DKK": 0.02, "NZD": 0.02, "ISK": 0.025, "RON": 0.03}
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
        # Trailing-twelve-month revenue and operating income summed from the last four quarters. Yahoo's
        # 'operatingMargins' is the latest QUARTER's margin while 'totalRevenue' is TTM — multiplying them put
        # Samsung at a 52% margin (one memory-boom quarter; TTM 37%) and ExxonMobil at 15.9% (TTM 10.7%).
        ttm = _ttm_from_quarters(s)
        rev = ttm["revenue"] if ttm else _f(i.get("totalRevenue"))
        om = _f(i.get("operatingMargins"))
        ebit_y = ttm["ebit"] if ttm else (rev * om if rev and om is not None else None)
        if not ttm and ebit_y is not None:
            out["margin_basis_note"] = "Quarterly statements unavailable: operating margin from Yahoo's latest-quarter figure."
        out.update({"revenue": rev, "ebit": ebit_y, "pretax_income": None, "income_tax": None,
                    "interest_expense": None, "sbc": None, "dna": (ttm or {}).get("dna"), "capex": (ttm or {}).get("capex"),
                    "operating_cash_flow": _f(i.get("operatingCashflow")), "cash": _f(i.get("totalCash")), "debt": _f(i.get("totalDebt")),
                    "leases": None, "minority_interest": None, "equity_book": None, "as_of": None})
        src = "Yahoo Finance (TTM from the last four quarterly statements)" if ttm else "Yahoo Finance (TTM)"
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
    out["is_financial"] = (any(k in ind for k in FINANCIAL_INDUSTRIES) or (i.get("sector") or "") == "Financial Services") \
        and not any(k in ind for k in NON_LENDER_FINANCIALS)
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
    cx, da = out.get("capex"), out.get("dna")
    out["net_capex_to_revenue"] = round((abs(cx) - abs(da)) / rev, 4) if cx is not None and da is not None and rev else None
    out["roic"] = round(out["ebit"] * (1 - (out["tax_effective"] or out["tax_marginal"])) / ic, 4) if out.get("ebit") and ic and ic > 0 else None
    _market_inputs(s, i, out)
    return out


def _ttm_from_quarters(symbol: str) -> Optional[Dict[str, Any]]:
    """TTM revenue and operating income from the last four quarterly income statements (Yahoo), or None when four
    consecutive quarters with both lines aren't available."""
    try:
        import yfinance as yf
        q = yf.Ticker(symbol).quarterly_income_stmt
        if q is None or q.empty or "Total Revenue" not in q.index or "Operating Income" not in q.index:
            return None
        cols = list(q.columns[:4])
        if len(cols) < 4:
            return None
        rev = [_f(q.loc["Total Revenue", c]) for c in cols]
        op = [_f(q.loc["Operating Income", c]) for c in cols]
        if any(v is None or v != v for v in rev + op) or sum(rev) <= 0:
            return None
        out = {"revenue": float(sum(rev)), "ebit": float(sum(op)), "as_of": str(cols[0])[:10]}
        try:                                    # capex and D&A, TTM, from the quarterly cash-flow statements
            cf = yf.Ticker(symbol).quarterly_cashflow
            if cf is not None and not cf.empty:
                cc = list(cf.columns[:4])
                def tot(row):
                    if row not in cf.index or len(cc) < 4:
                        return None
                    v = [_f(cf.loc[row, c]) for c in cc]
                    return None if any(x is None or x != x for x in v) else float(sum(v))
                cap = tot("Capital Expenditure")
                out["capex"] = abs(cap) if cap is not None else None
                out["dna"] = tot("Depreciation And Amortization") or tot("Depreciation Amortization Depletion")
        except Exception:
            pass
        return out
    except Exception:
        return None


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
    out["erp_implied"] = erp.get("erp") or ERP_FALLBACK
    if ERP_BASIS == "implied":
        out["erp_mature"] = out["erp_implied"]
        out["erp_source"] = erp.get("source") or f"fallback {ERP_FALLBACK:.1%} (Damodaran's monthly file unavailable)"
    else:
        out["erp_mature"] = ERP_STANDARD
        out["erp_source"] = (f"Kroll recommended mature-market ERP {ERP_STANDARD:.1%} (the valuation standard; the market-implied ERP "
                             f"is {out['erp_implied']:.1%} — {erp.get('source') or 'Damodaran'})")
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
        # Banks/insurers: debt is raw material, so an equity beta is used as is — the higher of the industry average
        # and the firm's own Blume-adjusted regression beta. Damodaran's regional bank averages are very low (Europe
        # 0.39), which put BNP Paribas's cost of equity at 5% against the 8–12% banks and the EBA report.
        lev, own = ind["levered_beta"], out.get("beta_regression")
        if own is not None and own > lev:
            out["beta"] = round(own, 3)
            out["beta_source"] = (f"the firm's Blume-adjusted regression beta {own:.2f} (above the {ind['industry']} average "
                                  f"{lev:.2f}, {ind['region']}, Damodaran)")
        else:
            out["beta"] = round(lev, 3)
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
            if e0 and last_fy and last_fy > 0 and 0.55 < e0 / last_fy < 1.8:
                g1 = e0 / last_fy - 1
            if e1 and e0 and e0 > 0 and 0.6 < e1 / e0 < 1.7:
                g2 = e1 / e0 - 1
            # an estimate that implies revenue jumps or halves is almost always a different currency or
            # basis from the statements (Petrobras: USD estimates vs BRL accounts) — it is ignored
            if (e0 and last_fy and g1 is None) or (e1 and e0 and g2 is None):
                out["growth_note"] = "Analyst revenue estimates look inconsistent with reported revenue (different currency or basis) — not used."
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
                                       f"{len(hist['margins'][:3])}-year median {med:.1%} over {CYCLICAL_FADE_YEARS} years")
        out["margin_fade_years"] = CYCLICAL_FADE_YEARS
    allm = sorted(hist["margins"])
    long_med = (allm[len(allm) // 2] if len(allm) % 2 else (allm[len(allm) // 2 - 1] + allm[len(allm) // 2]) / 2) if len(allm) >= 3 else None
    # Cyclical = a cyclical industry AND a margin that actually swings (range ≥ 40% of its median over the years
    # reported): Damodaran files Apple under Computers/Peripherals, but a 30–33% margin is a franchise, not a cycle.
    swings = (long_med is not None and long_med > 0 and (allm[-1] - allm[0]) / long_med >= 0.4)
    out["cyclical"] = bool(ind_name in CYCLICAL and (swings or long_med is None))
    if (out["cyclical"] and ind_m and ind_m > 0 and long_med is not None and base is not None and base > 0
            and out["target_margin_source"] == "today's margin held"):
        # A cyclical's margin today is a point on the cycle, not its long run: the target is the through-cycle
        # margin — the average of the firm's own median over the years reported and its industry's (McKinsey,
        # Damodaran: normalise cyclical earnings).
        tgt = round((long_med + ind_m) / 2, 4)
        out["target_margin_default"] = tgt
        out["target_margin_source"] = (f"cyclical industry: margin moves from {base:.1%} to the through-cycle {tgt:.1%} — the average of "
                                       f"its {len(allm)}-year median {long_med:.1%} and the {ind_name} margin {ind_m:.1%}")
        if base > 1.25 * tgt:
            out["margin_fade_years"] = CYCLICAL_FADE_YEARS
    elif (out["cyclical"] and ind_m and ind_m > 0 and out["target_margin_default"] is not None
            and out["target_margin_default"] > 1.5 * ind_m):
        # a few good years of a commodity cycle are not a through-cycle margin: meet the industry halfway
        tgt = round((out["target_margin_default"] + ind_m) / 2, 4)
        out["target_margin_source"] = (f"cyclical industry: margin fades from {out['target_margin_default']:.1%} halfway to the "
                                       f"{ind_name} through-cycle margin {ind_m:.1%} (→ {tgt:.1%})")
        out["target_margin_default"] = tgt
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
    """Cost of capital: CAPM cost of equity (risk-free + β × ERP), after-tax cost of debt and their market-value
    weights, optionally with leases as debt.
    """
    rf = inp.get("risk_free") or 0.04
    b = beta if beta is not None else (inp.get("beta") if inp.get("beta") is not None else 1.0)
    if erp is None:
        erp = inp.get("erp") or ERP_FALLBACK
    ke_model = rf + b * erp
    ke = max(ke_model, KE_FLOOR)
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
    return {"wacc": w, "cost_of_equity": ke, "cost_of_equity_model": ke_model, "ke_floored": ke > ke_model + 1e-12,
            "cost_of_debt_after_tax": kd_after, "beta": b, "erp": erp, "risk_free": rf,
            "weight_equity": E / (E + D) if E + D > 0 else 1.0, "weight_debt": D / (E + D) if E + D > 0 else 0.0}


def value(inp: Dict[str, Any], growth: Optional[float] = None, terminal_growth: Optional[float] = None, years: int = 10,
          target_margin: Optional[float] = None, sales_to_capital: Optional[float] = None, ronic: Optional[float] = None,
          discount: Optional[float] = None, beta: Optional[float] = None, erp: Optional[float] = ERP_DEFAULT, tax: Optional[float] = None,
          include_leases: bool = False, mid_year: bool = True) -> Dict[str, Any]:
    """A discounted cash-flow valuation: revenue growth fading to the terminal rate, margins converging to target,
    reinvestment from sales-to-capital, a terminal value from RONIC, discounted at WACC (mid-year by default).

    Returns:
        The per-share value, the projection, the WACC breakdown and the assumptions used.
    """
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
    gT = terminal_growth if terminal_growth is not None else default_terminal_growth(inp)
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
    cyclical = inp.get("cyclical", (inp.get("industry_benchmark") or {}).get("industry") in CYCLICAL)
    # Commodity and cyclical businesses earn their cost of capital on new investment over a cycle (McKinsey,
    # Damodaran): no excess return in perpetuity. Others keep half of today's excess return (capped at 30%).
    default_ron = rT if cyclical else (min(0.30, rT + 0.5 * (roic - rT)) if roic is not None and roic > rT else rT)
    ron = default_ron if ronic is None else ronic
    if ron <= max(0.0, gT):
        raise NotFound(f"Return on new capital ({ron:.2%}) must exceed terminal growth ({gT:.2%}): growing faster than the "
                       "return on reinvestment would need more than 100% of profits reinvested, forever.")

    # the firm's actual net capital spending per unit of revenue anchors the first years' reinvestment
    anchor = inp.get("net_capex_to_revenue")
    if anchor is not None and anchor < 0:
        anchor = 0.0                                                         # depreciation above capex: not a source of cash
    rows: List[Dict[str, Any]] = []
    rev, pv_sum, cum = rev0, 0.0, 1.0
    for y in range(1, years + 1):
        if y == 1:
            g = g1
        elif y <= hg:
            g = g0
        else:                                                               # linear fade to g∞ by year N
            g = g0 + (gT - g0) * (y - hg) / (years - hg)
        fade = inp.get("margin_fade_years") if target_margin is None else None
        m = m0 + (mT - m0) * min(1.0, y / fade) if fade else m0 + (mT - m0) * (y / years)
        tx = t_now + (t_term - t_now) * (y / years)
        new_rev = rev * (1 + g)
        ebit = new_rev * m
        nopat = ebit * (1 - tx) if ebit > 0 else ebit                       # no tax shield modelled on losses
        reinvest = (new_rev - rev) / stc
        if anchor is not None and y <= REINVEST_ANCHOR_YEARS and sales_to_capital is None:
            w_a = 1 - (y - 1) / REINVEST_ANCHOR_YEARS             # 1 in year 1 → 0.2 in year 5 → the ratio rule after
            reinvest = w_a * anchor * new_rev + (1 - w_a) * reinvest
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
    if w.get("ke_floored"):
        checks.append(f"Cost of equity floored at {KE_FLOOR:.0%}: the local risk-free rate ({rf:.2%}) would give only "
                      f"{w['cost_of_equity_model']:.1%}, a return no equity investor accepts.")
    if ev > 0 and pv_tv > ev:
        checks.append("The next ten years' cash flows are negative in present value (heavy reinvestment): all of the value, and more, "
                      "sits in the terminal value — treat the result as highly uncertain.")
    elif ev > 0 and pv_tv / ev > 0.8:
        checks.append(f"{pv_tv / ev:.0%} of the value is in the terminal value — the answer depends mostly on the long run.")
    if equity_negative:
        checks.insert(0, f"The operating business is worth less than its debt (equity {eq_raw / 1e6:,.0f}m before the floor): on these "
                         "assumptions the shares are worth only their option value on a turnaround — shown as 0.")
    if inp.get("margin_note"):
        checks.append(inp["margin_note"] + ".")
    if inp.get("growth_note"):
        checks.append(inp["growth_note"])
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
                            "sales_to_capital": stc, "net_capex_to_revenue": anchor, "reinvestment_anchor_years": REINVEST_ANCHOR_YEARS if anchor is not None and sales_to_capital is None else None,
                            "ronic": ron, "discount": r, "discount_terminal": rT, "beta_terminal": beta_T, "tax_now": t_now, "tax_terminal": t_term,
                            "mid_year": mid_year, "include_leases": include_leases, "roic_now": roic_now},
            "wacc": w, "net_debt": debt - (inp.get("cash") or 0), "projection": rows, "checks": checks, "price": price}


def default_terminal_growth(inp: Dict[str, Any]) -> float:
    """Perpetual growth: the risk-free rate (Damodaran), capped under TERMINAL_RULE "gdp" at the currency's long-run
    nominal GDP growth — never negative."""
    rf = max(0.0, inp.get("risk_free") or 0.04)
    if TERMINAL_RULE == "gdp":
        cap = LR_NOMINAL_GROWTH.get((inp.get("currency") or "USD").upper())
        if cap is not None:
            return min(rf, cap)
    return rf


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
    """Value per share over a grid of WACC and terminal growth."""
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
    ke_floored = discount is None and rf + b * e < KE_FLOOR
    ke = discount if discount is not None else max(rf + b * e, KE_FLOOR)
    roe0 = roe if roe is not None else min(0.40, max(-0.10, ni / bv0))
    # stable ROE: half of today's excess return persists (as for RONIC in the FCFF model)
    roeT = terminal_roe if terminal_roe is not None else (ke + 0.5 * (roe0 - ke) if roe0 > ke else roe0 + 0.5 * (ke - roe0))
    g = max(0.0, min(default_terminal_growth(inp), ke - 0.01)) if terminal_growth is None else terminal_growth
    if terminal_roe is None and roeT <= g + 0.005:
        roeT = max(ke, g + 0.01)          # a weak franchise reverts to earning its cost of equity, not to shrinking forever
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
    if ke_floored:
        checks.append(f"Cost of equity floored at {KE_FLOOR:.0%}: the local risk-free rate ({rf:.2%}) would give only {rf + b * e:.1%}.")
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
    """Value per share of a bank or insurer (excess-return model) over cost of equity and growth."""
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


# ── Dividend discount model ─────────────────────────────────────────────────
def _dividend_history(symbol: str) -> List[Dict[str, Any]]:
    """Dividends per share by calendar year (complete years only), in the trading currency."""
    from api.marketdata.core import _cached

    def fetch():
        import yfinance as yf
        d = yf.Ticker(symbol).dividends
        if d is None or d.empty:
            return []
        by = d.groupby(d.index.year).sum()
        from datetime import date as _d
        return [{"year": int(y), "dps": float(v)} for y, v in by.items() if int(y) < _d.today().year and v > 0]
    try:
        return _cached(f"divhist:{symbol}", 86400, fetch)
    except Exception:
        return []


def value_ddm(inp: Dict[str, Any], years: int = 10, high_years: int = 5, growth: Optional[float] = None,
              terminal_growth: Optional[float] = None, discount: Optional[float] = None, beta: Optional[float] = None,
              erp: Optional[float] = ERP_DEFAULT, **_ignored) -> Dict[str, Any]:
    """Dividend discount model (Damodaran's two-stage with a transition): value = PV of dividends per share.

    Dividends grow at g for `high_years`, then the rate fades linearly to stable growth by year N; the
    terminal value is D_{N+1} ÷ (kₑ − g∞). For firms that retain a real share of earnings, the payout
    ratio also moves to the stable payout 1 − g∞ ÷ ROE∞ (growth has to be paid for). REITs, utilities
    and any firm already paying out ≥ 90% grow the dividend directly. Works in the trading currency, so
    there is no FX step; it suits banks, insurers, REITs, utilities and mature payers — the firms where
    free cash flow is hard to define or the dividend is the cash flow investors actually receive."""
    s = inp["symbol"]
    i = _info(s)
    price = inp.get("price")
    from api.marketdata.core import div_yield
    dy = div_yield(i)
    dps0 = (dy * price) if dy and price else None
    hist = _dividend_history(s)
    if not dps0 and hist:
        dps0 = hist[-1]["dps"]
    if not dps0 or dps0 <= 0 or not price:
        raise NotFound(f"{s} pays no regular dividend, so a dividend discount model doesn't apply — use the DCF or peer multiples.")
    if not 5 <= years <= 30:
        raise NotFound("Use 5–30 projection years.")
    rf = inp.get("risk_free") or 0.04
    b = beta if beta is not None else (inp.get("beta") or 1.0)
    e = erp if erp is not None else (inp.get("erp") or ERP_FALLBACK)
    ke_model = rf + b * e
    ke = discount if discount is not None else max(ke_model, KE_FLOOR)
    ccy = (inp.get("currency") or "USD").upper()
    infl = LT_INFLATION.get(ccy, 0.02 if ccy in ("EUR", "JPY", "GBP", "CHF", "CAD", "AUD") else LT_INFLATION["USD"])
    g_cap = 0.02 + infl                                   # ≈ 2% real growth plus the currency's inflation
    # stable phase: a mature firm's beta drifts toward the market's (bounded 0.8–1.2, as in the DCF)
    keT = ke if discount is not None else max(KE_FLOOR, rf + min(1.2, max(0.8, b)) * e)
    gT = min(rf, keT - 0.03, g_cap) if terminal_growth is None else terminal_growth
    gT = max(gT, 0.0) if terminal_growth is None else gT
    if keT - gT < 0.005:
        raise NotFound(f"Terminal growth ({gT:.2%}) must be at least 0.5 points below the cost of equity ({keT:.2%}).")
    ind = (inp.get("industry") or "")
    payout = inp.get("payout_ratio")
    ni, bv = inp.get("net_income"), inp.get("equity_book")
    roe = ni / bv if ni is not None and bv and bv > 0 else None
    # dividend growth history (5-year CAGR of complete years)
    cagr = None
    if len(hist) >= 6 and hist[-6]["dps"] > 0:
        cagr = (hist[-1]["dps"] / hist[-6]["dps"]) ** (1 / 5) - 1
    elif len(hist) >= 3 and hist[0]["dps"] > 0:
        n = len(hist) - 1
        cagr = (hist[-1]["dps"] / hist[0]["dps"]) ** (1 / n) - 1
    pass_through = ind.startswith("REIT") or ind.startswith("Utilities") or (payout is not None and payout >= 0.9) or roe is None
    sustainable = roe * (1 - min(1.0, payout or 0.0)) if roe is not None and payout is not None and not pass_through else None
    cands = [x for x in (sustainable, cagr) if x is not None]
    g_src = []
    if growth is not None:
        g1 = growth
        g_src.append("your input")
    elif cands:
        g1 = min(cands)          # the more conservative signal: ROE is often flattered by buybacks, history by one-offs
        if sustainable is not None:
            g_src.append(f"sustainable growth ROE × retention = {roe:.1%} × {1 - payout:.0%} = {sustainable:.1%}")
        if cagr is not None:
            g_src.append(f"5-year dividend growth {cagr:.1%}")
    else:
        g1 = gT
        g_src.append("no history: stable growth from the start")
    g1 = min(0.10 if not pass_through else 0.08, max(-0.05, g1)) if growth is None else g1
    if pass_through and terminal_growth is None:
        gT = min(gT, max(g1, infl))          # a firm paying out everything can't grow its dividend faster forever
    roeT = (keT + 0.5 * (roe - keT) if roe is not None and roe > keT else keT) if roe is not None else None
    pT = (1 - gT / roeT) if roeT and roeT > gT else None
    p0 = min(1.0, payout) if payout else None
    use_payout = not pass_through and p0 and pT and p0 > 0.05
    eps0 = dps0 / p0 if use_payout else None
    rows, pv, d, eps, cum = [], 0.0, dps0, eps0, 1.0
    for y in range(1, years + 1):
        f = 0.0 if y <= high_years else (y - high_years) / (years - high_years)
        g = g1 + (gT - g1) * f
        k_y = ke + (keT - ke) * f
        if use_payout:
            eps = eps * (1 + g)
            p = p0 + (pT - p0) * max(0.0, (y - high_years) / (years - high_years))
            d = eps * p
        else:
            p = None
            d = d * (1 + g)
        cum /= (1 + k_y)
        pv += d * cum
        rows.append({"year": y, "growth": g, "eps": eps, "payout": p, "dividend": d, "cost_of_equity": k_y, "discount_factor": cum, "pv": d * cum})
    d_next = (eps * (1 + gT) * pT) if use_payout else d * (1 + gT)
    tv = d_next / (keT - gT)
    pv_tv = tv * cum
    per_share = pv + pv_tv
    checks = []
    if pv_tv / per_share > 0.75:
        checks.append(f"{pv_tv / per_share:.0%} of the value is in the terminal value — the answer depends mostly on long-run dividend growth.")
    if discount is None and ke_model < KE_FLOOR:
        checks.append(f"Cost of equity floored at {KE_FLOOR:.0%}: the local risk-free rate ({rf:.2%}) would give only {ke_model:.1%}.")
    if payout is not None and payout > 1.0 and not ind.startswith("REIT"):
        checks.append(f"The dividend is {payout:.0%} of earnings — not covered by profits; the model assumes it is sustained.")
    if dy is not None and dy < 0.01:
        checks.append(f"The yield is only {dy:.1%}: most of this company's return comes from retained earnings and buybacks, "
                      "so a dividend model understates it — prefer the DCF.")
    if not inp.get("risk_free_matched", True):
        checks.append(f"No government yield in {ccy}: the US rate is used for the risk-free rate.")
    # reverse DDM: the constant dividend growth today's price implies at the long-run cost of equity (Gordon)
    implied_g = (keT * price - dps0) / (price + dps0)
    return {"model": "ddm", "per_share": per_share, "price": price, "upside": per_share / price - 1, "implied_growth": implied_g,
            "dps": dps0, "dividend_yield": dps0 / price, "pv_dividends": pv, "pv_terminal": pv_tv, "terminal_value": tv,
            "terminal_share": pv_tv / per_share if per_share > 0 else None, "variant": "payout" if use_payout else "dividend_growth",
            "dividend_history": hist[-12:], "dividend_cagr_5y": cagr,
            "assumptions": {"growth": g1, "growth_source": "; ".join(g_src), "high_years": high_years, "years": years, "terminal_growth": gT,
                            "terminal_growth_cap": g_cap, "cost_of_equity": ke, "cost_of_equity_terminal": keT, "cost_of_equity_model": ke_model, "beta": b, "erp": e,
                            "risk_free": rf, "payout_now": payout, "payout_terminal": pT if use_payout else None, "roe_now": roe, "roe_terminal": roeT},
            "projection": rows, "checks": checks}


def sensitivity_ddm(inp: Dict[str, Any], base: Dict[str, Any], **kw) -> Dict[str, Any]:
    """Dividend-discount value over cost of equity and dividend growth."""
    a = base["assumptions"]
    kes = [a["cost_of_equity"] + d for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    gs = [a["terminal_growth"] + d for d in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    grid = []
    for k in kes:
        row = []
        for g in gs:
            try:
                row.append(value_ddm(inp, **{**kw, "discount": k, "terminal_growth": g})["per_share"] if k - g >= 0.005 else None)
            except NotFound:
                row.append(None)
        grid.append(row)
    return {"rows_label": "cost of equity", "cols_label": "stable dividend growth", "rows": kes, "cols": gs, "grid": grid}


# ── Price outlook: from a value today to expected prices over the next 24 months ─────────────
def _realized_vol(symbol: str) -> Optional[float]:
    from api.marketdata.core import _cached

    def fetch():
        import numpy as np
        import yfinance as yf
        c = yf.Ticker(symbol).history(period="1y", auto_adjust=True)["Close"].dropna()
        if len(c) < 60:
            return None
        r = np.diff(np.log(c.values))
        return float(r.std() * math.sqrt(252))
    try:
        return _cached(f"rvol1y:{symbol}", 6 * 3600, fetch)
    except Exception:
        return None


def outlook(symbol: str, price: Optional[float], value: Optional[float], cost_of_equity: Optional[float],
            dividend_yield: Optional[float], half_life_years: float = 3.0, months: int = 24) -> Optional[Dict[str, Any]]:
    """Expected price path. An intrinsic value says where the price should be, not when it gets there, so:

      median log price  ln P_t = ln P₀ + (kₑ − yield)·t + (1 − e^(−λt))·ln(V / P₀)

    The price earns its cost of equity (less the dividend paid out), and the gap to the model value closes
    with a half-life (default 3 years — value spreads mean-revert slowly; Fama-French, Damodaran). Bands are
    lognormal with the stock's 1-year realised volatility: 10th–90th percentile = median × e^(∓1.28 σ√t)."""
    if not price or price <= 0 or cost_of_equity is None:
        return None
    sigma = _realized_vol(symbol) or 0.30
    dy = max(0.0, dividend_yield or 0.0)
    drift = cost_of_equity - dy
    lam = math.log(2) / max(0.25, half_life_years)
    gap = math.log(value / price) if value and value > 0 else 0.0
    i = _info(symbol)
    from datetime import date as _d
    today = _d.today()

    def at(t: float) -> Dict[str, Any]:
        m = math.log(price) + drift * t + (1 - math.exp(-lam * t)) * gap
        sd = sigma * math.sqrt(t) if t > 0 else 0.0
        med = math.exp(m)
        p_up = 0.5 * (1 + math.erf(((m - math.log(price)) / sd) / math.sqrt(2))) if sd else None
        return {"median": med, "p10": med * math.exp(-1.2816 * sd), "p90": med * math.exp(1.2816 * sd),
                "p25": med * math.exp(-0.6745 * sd), "p75": med * math.exp(0.6745 * sd), "prob_above_today": p_up,
                "expected_return": med / price - 1}
    path = []
    for k in range(0, months + 1):
        y, mth = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
        path.append({"date": f"{y}-{mth:02d}", **{kk: round(v, 4) if isinstance(v, float) else v for kk, v in at(k / 12).items()}})
    table = [{"months": k, **at(k / 12)} for k in (1, 3, 6, 12, 18, 24) if k <= months]
    tgt, n = _f(i.get("targetMeanPrice")), i.get("numberOfAnalystOpinions")
    return {"path": path, "horizons": table, "volatility": sigma, "drift": drift, "half_life_years": half_life_years,
            "value": value, "price": price, "cost_of_equity": cost_of_equity, "dividend_yield": dy,
            "gap_closed_12m": 1 - math.exp(-lam), "analyst_target": tgt, "analysts": n,
            "analyst_low": _f(i.get("targetLowPrice")), "analyst_high": _f(i.get("targetHighPrice")),
            "note": "Median = the price earning its cost of equity (net of dividends) while closing the gap to the model value "
                    f"with a {half_life_years:g}-year half-life; bands from 1-year realised volatility ({sigma:.0%}). "
                    "A model-based expectation, not a forecast of short-term moves — over 1–3 months volatility dominates."}
