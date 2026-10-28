"""
Market-based LBO defaults — a complete lbo.run() input set for a listed company, with a source for every number:

  company      SEC filings / Yahoo Finance via the DCF's inputs (revenue, EBIT + D&A, capex, debt, cash, tax, shares)
  entry        today's price plus a take-private premium (30% default — the long-run median US public-to-private
               premium is ≈ 25–40%), as an EV / LTM EBITDA multiple
  exit         the entry multiple (the base case assumes no expansion or compression); the industry's EV/EBITDA
               (Damodaran, by region) is shown as a reference and the downside case exits a turn lower
  credit       base rate by currency (SOFR / SONIA / €STR, FRED), term loan B at base + the ICE BofA single-B spread,
               notes at the 5-year Treasury + the BB/B average spread; leverage sized to keep interest cover ≥ 2.25×
               and equity ≥ 45% of the price
  plan         analyst revenue growth fading to the long-run rate, today's EBITDA margin held, D&A and capex at
               today's share of revenue
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from api.pe import lbo

logger = logging.getLogger(__name__)
BASE_RATE = {"USD": ("SOFR", "SOFR"), "GBP": ("IUDSOIA", "SONIA"), "EUR": ("ECBESTRVOLWGTTRMDRATE", "€STR")}
PREMIUM = 0.30
MIN_COVER = 2.25
MAX_DEBT_SHARE = 0.55


def _last(sid: str) -> Optional[float]:
    try:
        from api.marketdata.insights import _fred
        d = _fred(sid, years=1)
        return float(d[max(d)]) / 100 if d else None
    except Exception as e:
        logger.debug("[pe] FRED %s: %s", sid, e)
        return None


def credit(currency: str = "USD") -> Dict[str, Any]:
    """Today's leveraged-finance pricing inputs (FRED): base rate, single-B / BB / CCC spreads, high-yield yield."""
    from api.marketdata.core import _cached

    def fetch():
        sid, name = BASE_RATE.get((currency or "USD").upper(), BASE_RATE["USD"])
        base = _last(sid)
        if base is None and sid != "SOFR":
            sid, name, base = "SOFR", "SOFR (no local series)", _last("SOFR")
        bb, b, ccc = _last("BAMLH0A1HYBB"), _last("BAMLH0A2HYB"), _last("BAMLH0A3HYC")
        t5, hy = _last("DGS5"), _last("BAMLH0A0HYM2EY")
        return {"currency": (currency or "USD").upper(), "base_rate": base, "base_rate_name": name, "base_rate_series": sid,
                "bb_spread": bb, "b_spread": b, "ccc_spread": ccc, "treasury_5y": t5, "hy_yield": hy,
                "source": "FRED: base rate, ICE BofA US High Yield option-adjusted spreads by rating, 5-year Treasury"}
    return _cached(f"pe:credit:{currency}", 3600, fetch)


def industry_multiple(industry: Optional[str], country: Optional[str]) -> Dict[str, Any]:
    """The industry's EV/EBITDA from Damodaran's regional file."""
    from api.providers import damodaran as d
    name = d._norm_industry(industry)
    if not name:
        return {"industry": None, "ev_ebitda": None}
    region = d._region_files(country)["region"]
    fname = "vebitda.xls" if region == "US" else "vebitdaEurope.xls" if region == "Europe" else "vebitdaGlobal.xls"
    try:
        row = d._table(fname).get(name) or d._table("vebitdaGlobal.xls").get(name) or {}
    except Exception:
        row = {}
    v = d._num(row.get("EV/EBITDA"))
    return {"industry": name, "region": region, "ev_ebitda": v, "firms": d._num(row.get("Number of firms")),
            "source": f"Damodaran {region} EV/EBITDA — {name}"}


def _round_to(x: float, step: float) -> float:
    return round(x / step) * step


def financing(ebitda: float, entry_multiple: float, cr: Dict[str, Any]) -> Dict[str, Any]:
    """Market-sized tranches: TLB + senior notes, leverage capped by interest cover and the equity share."""
    base = cr.get("base_rate") if cr.get("base_rate") is not None else 0.04
    tlb_spread = max(0.0275, _round_to(cr.get("b_spread") or 0.035, 0.0025))
    hy_spread = ((cr.get("bb_spread") or 0.025) + (cr.get("b_spread") or 0.035)) / 2
    notes_coupon = _round_to((cr.get("treasury_5y") or 0.045) + hy_spread, 0.00125)
    blended = 0.7 * (base + tlb_spread) + 0.3 * notes_coupon
    turns = min(6.0, 1 / (MIN_COVER * blended), MAX_DEBT_SHARE * entry_multiple)
    turns = max(1.0, round(turns * 4) / 4)
    return {
        "base_rate": base,
        "tranches": [
            {"name": "Term Loan B", "kind": "tlb", "multiple": round(turns * 0.7, 2), "floating": True, "spread": tlb_spread,
             "floor": 0.0, "amort_pct": 0.01, "tenor": 7, "sweep": True},
            {"name": "Senior notes", "kind": "notes", "multiple": round(turns * 0.3, 2), "floating": False, "coupon": notes_coupon,
             "amort_pct": 0.0, "tenor": 8, "sweep": False},
        ],
        "revolver": {"commitment": round(0.75 * ebitda, 2), "spread": max(0.025, tlb_spread - 0.0025), "commitment_fee": 0.00375,
                     "drawn_at_close": 0.0},
        "notes": (f"Leverage {turns:.2f}× EBITDA — the lower of 6.0×, interest cover ≥ {MIN_COVER}× at a blended "
                  f"{blended:.2%}, and {MAX_DEBT_SHARE:.0%} of the price. TLB at {cr.get('base_rate_name') or 'base'} + "
                  f"{tlb_spread:.2%} (single-B spread); notes {notes_coupon:.2%} (5-year Treasury + BB/B spread)."),
    }


def from_company(symbol: str, premium: float = PREMIUM) -> Dict[str, Any]:
    """A complete LBO input set for a listed company, with the source of each assumption."""
    from api.marketdata import dcf
    d = dcf.inputs(symbol)
    rev, ebit, dna = d.get("revenue"), d.get("ebit"), d.get("dna")
    if not rev or ebit is None or dna is None:
        raise lbo.LboError(f"{symbol}: revenue, operating income or D&A is missing from its filings.")
    if d.get("is_financial"):
        raise lbo.LboError(f"{symbol} is a financial company — an LBO (EBITDA, leverage) does not apply.")
    ebitda = ebit + dna
    if ebitda <= 0:
        raise lbo.LboError(f"{symbol} has negative EBITDA ({ebitda:,.0f}) — not an LBO candidate.")
    price, shares = d.get("price"), d.get("shares")
    debt, cash = float(d.get("debt") or 0), float(d.get("cash") or 0)
    fx = 1.0
    if d.get("market_cap_fin_ccy") and d.get("market_cap"):
        fx = d["market_cap_fin_ccy"] / d["market_cap"]            # price currency → reporting currency
    offer = price * (1 + premium) * fx if price else None
    equity = offer * shares if offer and shares else None
    ev = (equity + debt - cash) if equity else None
    entry_mult = ev / ebitda if ev else 10.0
    ind = industry_multiple(d.get("industry"), d.get("country"))
    exit_mult = entry_mult
    cr = credit(d.get("currency") or "USD")
    fin = financing(ebitda, entry_mult, cr)
    g1, glr = d.get("growth_y1"), d.get("growth")
    g1 = g1 if g1 is not None else (glr if glr is not None else 0.03)
    glr = glr if glr is not None else 0.03
    years = 7
    growth = [round(g1 + (glr - g1) * min(1.0, (y - 1) / 3), 4) for y in range(1, years + 1)]
    margin = ebitda / rev
    tax = d.get("tax_marginal") or d.get("tax_effective") or 0.25
    inp = {**lbo.default_inputs(),
           "name": d.get("name") or symbol, "symbol": d.get("symbol") or symbol.upper(), "currency": d.get("currency"),
           "revenue": rev, "ebitda": ebitda, "cash": cash, "debt": debt, "price": price * fx if price else None, "shares": shares,
           "entry_multiple": round(entry_mult, 2), "exit_multiple": round(exit_mult, 2), "min_cash": round(0.02 * rev, 2),
           **{k: fin[k] for k in ("base_rate", "tranches", "revolver")},
           "years": years, "exit_year": 5, "revenue_growth": growth, "ebitda_margin": round(margin, 4),
           "dna_pct": round(dna / rev, 4), "capex_pct": round(abs(d.get("capex") or 0) / rev, 4) if d.get("capex") is not None else 0.03,
           "nwc_pct": 0.10, "tax_rate": round(tax, 4)}
    sources = {
        "company": f"{d.get('source') or 'filings'} — LTM to {d.get('as_of') or 'latest'}; EBITDA = operating income + D&A",
        "entry": (f"{d.get('symbol')} at {price:,.2f} + {premium:.0%} take-private premium → EV {ev:,.0f} = {entry_mult:.1f}× EBITDA"
                  if ev else "No market price — entry multiple set to 10×"),
        "exit": (f"{exit_mult:.1f}× — the entry multiple (no expansion assumed). Reference: {ind['source']} {ind['ev_ebitda']:.1f}×"
                 + (" — the price is well above the industry, so test a lower exit" if ind['ev_ebitda'] < exit_mult * 0.8 else "")
                 if ind.get("ev_ebitda") else f"{exit_mult:.1f}× — the entry multiple (no industry multiple found)"),
        "financing": fin["notes"], "credit": cr.get("source"),
        "plan": (f"Revenue growth {g1:.1%} (analyst consensus) fading to {glr:.1%} by year 4; EBITDA margin held at {margin:.1%}; "
                 f"D&A {dna / rev:.1%} and capex {abs(d.get('capex') or 0) / rev:.1%} of revenue; working capital 10% of the change in revenue"),
        "tax": f"{tax:.1%} ({'marginal' if d.get('tax_marginal') else 'effective'}); interest deductible to 30% of EBITDA",
    }
    return {"inputs": inp, "sources": sources, "credit": cr, "industry": ind,
            "market": {"price": price, "price_currency": d.get("price_currency"), "shares": shares, "market_cap": d.get("market_cap"),
                       "offer_price": offer, "premium": premium, "net_debt": debt - cash, "ev_at_offer": ev}}
