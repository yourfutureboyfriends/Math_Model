"""Markets mode endpoints (api/marketdata): universal search, quotes, overview, profiles,
statements, news + SEC filings, movers and the global screener. Read-only market data."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

router = APIRouter(tags=["markets"])
logger = logging.getLogger(__name__)


async def _run(fn, *a, timeout: float = 45, **k):
    from api.marketdata import core
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a, **k), timeout=timeout)
    except core.NotFound as e:
        raise HTTPException(404, str(e))
    except core.Upstream as e:
        raise HTTPException(503, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, "The data provider is slow to respond — try again.")
    except HTTPException:
        raise
    except Exception as e:                         # a provider returned something unexpected: say so, don't 500 blank
        import logging
        logging.getLogger(__name__).exception("[mkt] %s failed", getattr(fn, "__name__", fn))
        raise HTTPException(502, f"The data provider returned something unexpected ({type(e).__name__}) — try again shortly.")


@router.get("/api/v1/mkt/tv")
async def mkt_tv_live():
    """Live business/news channels (official YouTube streams) with their home countries."""
    from api.marketdata import tv
    return await _run(tv.live, timeout=90)


@router.get("/api/v1/mkt/tv/clips")
async def mkt_tv_clips(country: Optional[str] = Query(None, pattern=r"^[A-Za-z]{2}$"), limit: int = Query(24, ge=1, le=60)):
    """Recent economy clips from those channels — for a country, the ones about it."""
    from api.marketdata import tv
    return await _run(tv.clips, country, limit, timeout=90)


@router.get("/api/v1/mkt/gc")
async def mkt_yield_curves():
    """GC: official daily government curves (US, DE, euro AAA, UK, JP, CA, AU) with 1W/1M changes."""
    from api.marketdata import curves
    return await _run(curves.curves, timeout=120)


@router.get("/api/v1/mkt/search")
async def mkt_search(q: str = Query(..., min_length=1, max_length=60), limit: int = Query(12, ge=1, le=25)):
    """Search securities by ticker or name across exchanges (Yahoo); up to `limit` results."""
    from api.marketdata import core
    return {"query": q, "results": await _run(core.search, q, limit)}


@router.get("/api/v1/mkt/quote/{symbol}")
async def mkt_quote(symbol: str):
    """Latest quote for a symbol: price, change, bid / ask when available, market state and the quote time (delayed for
    some venues).
    """
    from api.marketdata import core
    return await _run(core.quote, symbol)


@router.get("/api/v1/mkt/overview")
async def mkt_overview():
    """Market overview: major indices, rates, FX, commodities and crypto with daily changes."""
    from api.marketdata import core
    return await _run(core.overview, timeout=90)


@router.get("/api/v1/mkt/profile/{symbol}")
async def mkt_profile(symbol: str):
    """Company profile (DES): description, sector, industry, country, employees, key statistics."""
    from api.marketdata import core
    return await _run(core.profile, symbol)


@router.get("/api/v1/mkt/statements/{symbol}")
async def mkt_statements(symbol: str):
    """Financial statements (FA): annual and quarterly income statement, balance sheet and cash flow."""
    from api.marketdata import core
    return await _run(core.statements, symbol, timeout=60)


@router.get("/api/v1/mkt/news/{symbol}")
async def mkt_news(symbol: str):
    """Recent news headlines for a symbol with source and time."""
    from api.marketdata import core
    return await _run(core.news, symbol)


@router.get("/api/v1/mkt/movers")
async def mkt_movers(region: str = "us", kind: str = Query("gainers", pattern="^(gainers|losers|active)$"),
                     count: int = Query(25, ge=5, le=100)):
    """Top gainers, losers or most active names in a region."""
    from api.marketdata import core
    return await _run(core.movers, region, kind, count)


@router.get("/api/v1/mkt/screen")
async def mkt_screen(regions: str = "us", sector: Optional[str] = None, sort: str = "market_cap", ascending: bool = False,
                     size: int = Query(50, ge=5, le=250), offset: int = Query(0, ge=0, le=5000),
                     market_cap_min: Optional[float] = None, market_cap_max: Optional[float] = None,
                     pe_min: Optional[float] = None, pe_max: Optional[float] = None,
                     dividend_yield_min: Optional[float] = None, change_pct_min: Optional[float] = None,
                     change_pct_max: Optional[float] = None, price_min: Optional[float] = None, include_adrs: bool = False):
    """Equity screener (EQS): filter a region's stocks by sector, market cap, P/E, dividend yield, price and daily
    change, sorted and paged.
    """
    from api.marketdata import core
    regs: List[str] = [r.strip().lower() for r in regions.split(",") if r.strip()]
    return await _run(core.screen, regs, sector, sort, ascending, size, offset, include_adrs,
                      market_cap_min=market_cap_min, market_cap_max=market_cap_max, pe_min=pe_min, pe_max=pe_max,
                      dividend_yield_min=dividend_yield_min, change_pct_min=change_pct_min,
                      change_pct_max=change_pct_max, price_min=price_min)


@router.get("/api/v1/mkt/meta")
async def mkt_meta():
    """Reference lists for the Markets UI: regions with currencies, sectors, screener sort keys and overview groups."""
    from api.marketdata import core
    return {"regions": [{"id": k, "name": v, "currency": core.REGION_CCY[k]} for k, v in core.REGIONS.items()],
            "sectors": core.SECTORS, "sorts": list(core.SORTS), "overview_groups": list(core.OVERVIEW)}


# ── Single-security functions (Bloomberg mnemonics) ──────────────────────────
@router.get("/api/v1/mkt/ern/{symbol}")
async def mkt_earnings(symbol: str):
    """Earnings history and estimates (ERN): reported vs estimated EPS, surprises, next date."""
    from api.marketdata import security
    return await _run(security.earnings, symbol)


@router.get("/api/v1/mkt/anr/{symbol}")
async def mkt_analysts(symbol: str):
    """Analyst recommendations and price targets (ANR): Yahoo's consensus, plus — for US listings — Benzinga's rating
    actions with the named analyst, and FMP's grade consensus and price-target trend. Extra sources are best-effort."""
    from api.marketdata import security
    from api.providers import benzinga as bz, fmp

    async def extra(fn, *a):
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *a), 25)
        except Exception as e:                                   # a missing extra source never breaks the screen
            logger.info("[anr] %s %s: %s", getattr(fn, "__name__", fn), symbol, e)
            return None
    us = "." not in symbol and not any(c in symbol for c in "=^")
    base, actions, fm = await asyncio.gather(_run(security.analysts, symbol),
                                             extra(bz.ratings, symbol, 365, 60) if us and bz.available() else asyncio.sleep(0),
                                             extra(fmp.analyst_view, symbol) if us and fmp.available() else asyncio.sleep(0))
    return {**base, "analyst_actions": actions, "fmp": fm}


@router.get("/api/v1/mkt/hds/{symbol}")
async def mkt_holders(symbol: str):
    """Major institutional and fund holders (HDS)."""
    from api.marketdata import security
    return await _run(security.holders, symbol)


@router.get("/api/v1/mkt/dvd/{symbol}")
async def mkt_dividends(symbol: str):
    """Dividend history and yield (DVD)."""
    from api.marketdata import security
    return await _run(security.dividends, symbol)


@router.get("/api/v1/mkt/omon/{symbol}")
async def mkt_options(symbol: str, expiry: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """Option chain for an expiry (OMON): calls and puts with bid / ask, volume, open interest and implied volatility.
    """
    from api.marketdata import security
    return await _run(security.options, symbol, expiry)


@router.get("/api/v1/mkt/omon/{symbol}/term")
async def mkt_iv_term(symbol: str):
    """Implied-volatility term structure across expiries (at-the-money)."""
    from api.marketdata import security
    return {"symbol": symbol.upper(), "term": await _run(security.iv_term_structure, symbol, timeout=90)}


@router.get("/api/v1/mkt/rv/{symbol}")
async def mkt_comps(symbol: str):
    """Relative valuation against peers (RV): multiples and growth side by side."""
    from api.marketdata import security
    return await _run(security.comps, symbol, timeout=90)


@router.get("/api/v1/mkt/hp/{symbol}")
async def mkt_history(symbol: str, period: str = "1y", interval: str = "1d"):
    """Price history (HP) for a period and interval."""
    from api.marketdata import security
    return await _run(security.history, symbol, period, interval)


@router.get("/api/v1/mkt/comp")
async def mkt_compare(symbols: str = Query(..., min_length=1), period: str = Query("5y", pattern="^(1mo|3mo|6mo|1y|2y|5y|10y|max|ytd)$")):
    """Total-return comparison of several symbols over a period (COMP), rebased to 100."""
    from api.marketdata import security
    return await _run(security.compare, symbols.split(","), period)


@router.get("/api/v1/mkt/beta/{symbol}")
async def mkt_beta(symbol: str, benchmark: Optional[str] = None, period: str = Query("2y", pattern="^(1y|2y|3y|5y|10y)$"),
                   freq: str = Query("W", pattern="^(D|W|M)$")):
    """Beta of a symbol against a benchmark (BETA) from daily, weekly or monthly returns, with R² and the regression."""
    from api.marketdata import security
    return await _run(security.beta, symbol, benchmark, period, freq)


@router.get("/api/v1/mkt/dcf/{symbol}")
async def mkt_dcf(symbol: str, growth: Optional[float] = Query(None, ge=-0.5, le=2.0), years: Optional[int] = Query(None, ge=3, le=30),
                  terminal_growth: Optional[float] = Query(None, ge=-0.05, le=0.15), target_margin: Optional[float] = Query(None, ge=-1.0, le=0.9),
                  sales_to_capital: Optional[float] = Query(None, gt=0, le=20), ronic: Optional[float] = Query(None, gt=0, le=2.0),
                  discount: Optional[float] = Query(None, gt=0, lt=0.4), beta: Optional[float] = Query(None, ge=-1, le=5),
                  erp: Optional[float] = Query(None, ge=0, le=0.15), include_leases: bool = False, mid_year: bool = True,
                  roe: Optional[float] = Query(None, ge=-0.5, le=1.0), terminal_roe: Optional[float] = Query(None, gt=0, le=1.0),
                  payout: Optional[float] = Query(None, ge=0, le=1.0), model: Optional[str] = Query(None, pattern="^(fcff|excess_return|ddm)$"),
                  half_life: float = Query(3.0, ge=0.25, le=20),
                  method: Optional[str] = Query(None, pattern="^(three_stage|two_stage)$"),
                  ke_method: Optional[str] = Query(None, pattern="^(capm|building_block)$"),
                  fade_years: Optional[int] = Query(None, ge=0, le=40)):
    """Valuation (FCFF / excess return / DDM) plus a 24-month price outlook built on it."""
    from api.marketdata import dcf
    from api.marketdata.core import _info, div_yield
    res = await _dcf_core(symbol, growth, years, terminal_growth, target_margin, sales_to_capital, ronic, discount, beta, erp,
                          include_leases, mid_year, roe, terminal_roe, payout, model, method, ke_method, fade_years)
    v = res["valuation"]
    ke = (v.get("wacc") or {}).get("cost_of_equity") or (v.get("assumptions") or {}).get("cost_of_equity")
    try:
        dy = div_yield(_info(res["inputs"]["symbol"]))
    except Exception:
        dy = None
    value = None if v.get("equity_negative") else v.get("per_share")
    res["outlook"] = await _run(dcf.outlook, res["inputs"]["symbol"], v.get("price") or res["inputs"].get("price"), value, ke, dy, half_life, timeout=30)
    # Morningstar-style margin of safety: an uncertainty rating (realised volatility, terminal-value weight) and the
    # prices relative to fair value at which the stock is a buy or a sell
    try:
        sigma = await _run(dcf._realized_vol, res["inputs"]["symbol"], timeout=20)
    except HTTPException:
        sigma = None
    u = dcf.uncertainty(sigma, v.get("terminal_share"))
    if value:
        u.update(buy_price=value * u["buy_below"], sell_price=value * u["sell_above"])
    res["uncertainty"] = u
    return res


async def _dcf_core(symbol: str, growth: Optional[float] = Query(None, ge=-0.5, le=2.0), years: Optional[int] = Query(None, ge=3, le=30),
                  terminal_growth: Optional[float] = Query(None, ge=-0.05, le=0.15), target_margin: Optional[float] = Query(None, ge=-1.0, le=0.9),
                  sales_to_capital: Optional[float] = Query(None, gt=0, le=20), ronic: Optional[float] = Query(None, gt=0, le=2.0),
                  discount: Optional[float] = Query(None, gt=0, lt=0.4), beta: Optional[float] = Query(None, ge=-1, le=5),
                  erp: Optional[float] = Query(None, ge=0, le=0.15), include_leases: bool = False, mid_year: bool = True,
                  roe: Optional[float] = Query(None, ge=-0.5, le=1.0), terminal_roe: Optional[float] = Query(None, gt=0, le=1.0),
                  payout: Optional[float] = Query(None, ge=0, le=1.0), model: Optional[str] = Query(None, pattern="^(fcff|excess_return|ddm)$"),
                  method: Optional[str] = None, ke_method: Optional[str] = None, fade_years: Optional[int] = None):
    """FCFF discounted at WACC (Damodaran / McKinsey) for operating companies; Damodaran's excess-return
    model for banks and insurers; a dividend discount model for dividend payers (and as the fallback where
    a DCF can't be built). Reverse DCF and sensitivity grids for all three."""
    from api.marketdata import dcf
    inp = await _run(dcf.inputs, symbol, timeout=60)
    ind = inp.get("industry") or ""
    # the dividend model runs alongside whenever the company pays one
    ddm_kw = dict(growth=growth if model == "ddm" else None, terminal_growth=terminal_growth if model == "ddm" else None,
                  discount=discount if model == "ddm" else None, beta=beta, erp=erp)
    ddm = ddm_err = None
    try:
        ddm = await _run(dcf.value_ddm, inp, **ddm_kw)
    except HTTPException as e:
        ddm_err = e.detail
    suits_ddm = ind.startswith("REIT") or ind.startswith("Utilities")
    recommended = "excess_return" if inp.get("is_financial") else ("ddm" if suits_ddm and ddm else "fcff")

    def ddm_response(reason: Optional[str] = None):
        sens = dcf.sensitivity_ddm(inp, ddm, **ddm_kw)
        return {"inputs": inp, "valuation": ddm, "sensitivity": sens, "model": "ddm", "ddm": ddm, "recommended": recommended,
                "fallback_reason": reason,
                "method": "Dividend discount model (Damodaran): dividends grow at the lower of sustainable growth (ROE × retention) and "
                          "their 5-year history, fade to stable growth (≤ the risk-free rate, ≤ 2% real + inflation, ≥ 3 points under the "
                          "cost of equity) and are discounted at the cost of equity, whose beta drifts to 0.8–1.2 as the firm matures."}
    chosen = model or recommended
    if chosen == "ddm":
        if not ddm:
            raise HTTPException(404, ddm_err or "No dividend model available.")
        return ddm_response()
    try:
        if chosen == "excess_return":
            kw = dict(years=years or 10, roe=roe, terminal_roe=terminal_roe, payout=payout, terminal_growth=terminal_growth, beta=beta, erp=erp, discount=discount)
            val = await _run(dcf.value_financial, inp, **kw)
            sens = await _run(dcf.sensitivity_financial, inp, val, **kw)
            implied = await _run(dcf.reverse_financial, inp, **{k: v for k, v in kw.items() if k not in ("roe", "terminal_roe")})
            return {"inputs": inp, "valuation": val, "sensitivity": sens, "market_implied_roe": implied, "model": "excess_return",
                    "ddm": ddm, "recommended": recommended,
                    "method": "Excess-return model: equity = book value + PV of (ROE − cost of equity) × book value, with ROE and payout "
                              "converging to stable levels and stable growth ≤ the risk-free rate. Source: Damodaran (NYU Stern)."}
        kw = dict(growth=growth, years=years, terminal_growth=terminal_growth, target_margin=target_margin, sales_to_capital=sales_to_capital,
                  ronic=ronic, discount=discount, beta=beta, erp=erp, include_leases=include_leases, mid_year=mid_year,
                  method=method, ke_method=ke_method, fade_years=fade_years)
        val = await _run(dcf.value, inp, **kw)
    except HTTPException as e:
        if chosen == "excess_return" and model is None and not inp.get("is_bank_like", False):
            try:    # a 'financial' that isn't a lender (exchanges, data vendors, crypto brokers) can be valued on cash flow
                kw = dict(growth=growth, years=years, terminal_growth=terminal_growth, target_margin=target_margin, sales_to_capital=sales_to_capital,
                          ronic=ronic, discount=discount, beta=beta, erp=erp, include_leases=include_leases, mid_year=mid_year,
                          method=method, ke_method=ke_method, fade_years=fade_years)
                val = await _run(dcf.value, inp, **kw)
                sens = await _run(dcf.sensitivity, inp, val, **kw)
                return {"inputs": inp, "valuation": val, "sensitivity": sens, "model": "fcff", "ddm": ddm, "recommended": "fcff",
                        "fallback_reason": f"The excess-return model can't run ({e.detail}) — valued on free cash flow instead.",
                        "method": "FCFF at WACC (Damodaran / McKinsey)."}
            except HTTPException:
                pass
        if ddm and model is None:          # the cash-flow model can't run on these numbers: value the dividend instead
            return ddm_response(f"Using the dividend model: the {'excess-return' if chosen == 'excess_return' else 'cash-flow'} model can't run ({e.detail}).")
        raise
    if model is None and ddm and val.get("equity_negative") and (ddm.get("dividend_yield") or 0) >= 0.015:
        return ddm_response("Using the dividend model: the cash-flow model leaves nothing for shareholders on these numbers (debt exceeds the operating value) — "
                            "the dividend actually paid is the better guide.")
    sens = await _run(dcf.sensitivity, inp, val, **kw)
    rkw = {k: v for k, v in kw.items() if k != "growth"}
    implied = await _run(dcf.reverse, inp, **rkw)
    bound = await _run(dcf.reverse_bound, inp, **rkw) if implied is None else None
    implied_r = await _run(dcf.implied_discount, inp, **kw)
    return {"inputs": inp, "valuation": val, "sensitivity": sens, "market_implied_growth": implied, "market_implied_growth_bound": bound,
            "market_implied_discount": implied_r, "model": "fcff", "ddm": ddm, "recommended": recommended,
            "method": ("Three-stage FCFF at WACC (Morningstar's structure): an explicit forecast, a fade stage whose length is set by "
                       "how persistently the firm has out-earned its cost of capital (its moat), and a perpetuity in which new investment "
                       "earns the cost of capital. " if val.get("method") == "three_stage" else
                       "Two-stage FCFF at WACC (Damodaran): terminal value = NOPAT × (1 − g/RONIC) ÷ (WACC − g). ")
                      + "Mid-year discounting; SBC is expensed (inside GAAP operating income). Market inputs from Damodaran (implied ERP, "
                      "industry betas, country risk). Sources: Morningstar Equity Research Methodology; Damodaran (NYU Stern); "
                      "Koller, Goedhart & Wessels, Valuation (McKinsey)."}


@router.get("/api/v1/mkt/dcf/{symbol}/xlsx")
async def mkt_dcf_excel(symbol: str, growth: Optional[float] = Query(None, ge=-0.5, le=2.0), years: Optional[int] = Query(None, ge=3, le=30),
                        terminal_growth: Optional[float] = Query(None, ge=-0.05, le=0.15), target_margin: Optional[float] = Query(None, ge=-1.0, le=0.9),
                        sales_to_capital: Optional[float] = Query(None, gt=0, le=20), ronic: Optional[float] = Query(None, gt=0, le=2.0),
                        discount: Optional[float] = Query(None, gt=0, lt=0.4), beta: Optional[float] = Query(None, ge=-1, le=5),
                        erp: Optional[float] = Query(None, ge=0, le=0.15), include_leases: bool = False, mid_year: bool = True,
                        method: Optional[str] = Query(None, pattern="^(three_stage|two_stage)$"),
                        ke_method: Optional[str] = Query(None, pattern="^(capm|building_block)$"),
                        fade_years: Optional[int] = Query(None, ge=0, le=40)):
    """The FCFF model as an Excel workbook with live formulas (edit the inputs in Excel)."""
    from fastapi.responses import Response
    from api.marketdata import dcf, dcf_excel
    inp = await _run(dcf.inputs, symbol, timeout=60)
    if inp.get("is_financial"):
        raise HTTPException(404, "Excel export covers the FCFF model; banks and insurers use the excess-return model on screen.")
    val = await _run(dcf.value, inp, growth=growth, years=years, terminal_growth=terminal_growth, target_margin=target_margin,
                     sales_to_capital=sales_to_capital, ronic=ronic, discount=discount, beta=beta, erp=erp,
                     include_leases=include_leases, mid_year=mid_year, method=method, ke_method=ke_method, fade_years=fade_years)
    data, _ = await asyncio.to_thread(dcf_excel.build, inp, val)
    name = f"DCF_{inp['symbol'].replace('^', '').replace('=', '')}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── Global monitors ──────────────────────────────────────────────────────────
@router.get("/api/v1/mkt/seas/{symbol}")
async def mkt_seasonality(symbol: str, years: int = Query(15, ge=3, le=40)):
    """Average return by calendar month over the last `years` years (SEAS), with the hit rate."""
    from api.marketdata import analytics
    return await _run(analytics.seasonality, symbol, years)


@router.get("/api/v1/mkt/corr")
async def mkt_correlation(symbols: str, period: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y|10y)$"),
                          freq: str = Query("daily", pattern="^(daily|weekly)$")):
    """Correlation matrix of several symbols (CORR) from daily or weekly returns."""
    from api.marketdata import analytics
    return await _run(analytics.correlation, symbols.split(","), period, freq, timeout=90)


@router.get("/api/v1/mkt/rrg")
async def mkt_rrg(universe: str = "us_sectors", tail: int = Query(8, ge=2, le=26), benchmark: Optional[str] = None):
    """Relative rotation graph (RRG): relative strength and its momentum against a benchmark, with a `tail` of weekly
    points.
    """
    from api.marketdata import analytics
    return await _run(analytics.rrg, universe, tail, benchmark, timeout=90)


@router.get("/api/v1/mkt/frd")
async def mkt_fx_forwards(base: str = Query("EUR", pattern="^[A-Za-z]{3}$"), quote: str = Query("USD", pattern="^[A-Za-z]{3}$")):
    """FX forward points and outright forwards (FRD) from interest-rate differentials (covered interest parity)."""
    from api.marketdata import analytics
    return await _run(analytics.fx_forwards, base, quote)


@router.get("/api/v1/mkt/si/{symbol}")
async def mkt_short_selling(symbol: str, days: int = Query(60, ge=10, le=120)):
    """Short interest (official, twice monthly) and FINRA daily short-sale volume."""
    from api.marketdata import shorts
    return await _run(shorts.short_selling, symbol, days, timeout=120)


@router.get("/api/v1/mkt/splc/{symbol}")
async def mkt_supply_chain(symbol: str):
    """Suppliers and competitors from SEC 10-K full-text search."""
    from api.marketdata import supply
    return await _run(supply.supply_chain, symbol, timeout=120)


@router.get("/api/v1/mkt/eco/global")
async def mkt_eco_global(days_back: int = Query(7, ge=0, le=365), countries: Optional[str] = None,
                         min_impact: str = Query("Low", pattern="^(Low|Medium|High)$")):
    """Global economic calendar with consensus, actual (US: as first published) and surprise."""
    from api.marketdata import econ
    return await _run(econ.calendar, days_back, countries.upper().split(",") if countries else None, min_impact, timeout=120)


@router.get("/api/v1/mkt/ecst")
async def mkt_surprise_index(start: str = Query("2010-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """Model-based US economic surprise index (ALFRED first releases)."""
    from api.marketdata import econ
    return await _run(econ.surprise_index, start, timeout=180)


@router.get("/api/v1/mkt/ship/chokepoints")
async def mkt_chokepoints():
    """IMF PortWatch: daily transits through 28 maritime chokepoints."""
    from api.marketdata import tracking
    return await _run(tracking.chokepoints, timeout=120)


@router.get("/api/v1/mkt/ship/vessels")
async def mkt_vessels(lat_min: float = Query(..., ge=-90, le=90), lon_min: float = Query(..., ge=-180, le=180),
                      lat_max: float = Query(..., ge=-90, le=90), lon_max: float = Query(..., ge=-180, le=180)):
    """Live AIS positions (aisstream.io with a key, else Digitraffic Baltic)."""
    from api.marketdata import tracking
    return await _run(tracking.vessels, lat_min, lon_min, lat_max, lon_max, timeout=60)


@router.get("/api/v1/mkt/ship/vessel/{query}")
async def mkt_vessel(query: str):
    """Vessel identity, flag/name history, owners and recent port calls (Global Fishing Watch)."""
    from api.marketdata import tracking
    return await _run(tracking.vessel_info, query, timeout=60)


@router.get("/api/v1/mkt/ship/world")
async def mkt_ships_world():
    """Every vessel the live AIS collector has heard in the last hour, worldwide (compact rows)."""
    from fastapi import Response
    from api.marketdata import tracking
    body = await _run(tracking.world_vessels_json, timeout=60)
    return Response(content=body, media_type="application/json")


@router.get("/api/v1/mkt/ship/notable")
async def mkt_ships_notable():
    """Ships worth following: sanctioned, military, gas carriers, giants, dangerous cargo, tankers in hot zones."""
    from api.marketdata import tracking
    return await _run(tracking.notable_ships, timeout=90)


@router.get("/api/v1/mkt/ship/live/{mmsi}")
async def mkt_ship_live(mmsi: int):
    """One vessel from the live picture: position, identity, dimensions, ETA, flag and 8-hour track."""
    from api.marketdata import tracking
    return await _run(tracking.vessel_live, mmsi)


@router.get("/api/v1/mkt/ship/ports")
async def mkt_ship_ports():
    """Ships at anchor / moored / moving near 55 major ports, from the live AIS picture."""
    from api.marketdata import tracking
    return await _run(tracking.port_congestion, timeout=60)


@router.get("/api/v1/mkt/fly/world")
async def mkt_flights_world():
    """Every aircraft with a position worldwide (OpenSky) plus live military (adsb.lol), compact rows."""
    from api.marketdata import airtraffic
    return await _run(airtraffic.world, timeout=90)


@router.get("/api/v1/mkt/fly/area")
async def mkt_flights_area(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), radius_nm: int = Query(120, ge=5, le=250)):
    """Live, detailed aircraft around a point (adsb.fi; adsb.lol fallback)."""
    from api.marketdata import airtraffic
    return await _run(airtraffic.area, lat, lon, radius_nm, timeout=45)


@router.get("/api/v1/mkt/fly/notable")
async def mkt_flights_notable():
    """Flights worth watching: emergencies, VIP/government, military, unusual aircraft, cargo."""
    from api.marketdata import airtraffic
    return await _run(airtraffic.notable_flights, timeout=90)


@router.get("/api/v1/mkt/fly/flight/{hex_id}")
async def mkt_flight(hex_id: str, callsign: Optional[str] = Query(None, max_length=10)):
    """One aircraft: route, airframe and photo (adsbdb), track flown (OpenSky), live state (adsb.fi)."""
    from api.marketdata import airtraffic
    return await _run(airtraffic.detail, hex_id, callsign, timeout=45)


@router.get("/api/v1/mkt/photos")
async def mkt_photos(kind: str = Query(..., pattern="^(ship|aircraft)$"), imo: Optional[str] = Query(None, max_length=12),
                     name: Optional[str] = Query(None, max_length=60), hex_id: Optional[str] = Query(None, max_length=8),
                     registration: Optional[str] = Query(None, max_length=12)):
    """Photos of a vessel (by IMO) or an aircraft (airframe / registration), with credit lines."""
    from api.marketdata import photos
    if kind == "ship":
        return await _run(photos.ship, imo, name, timeout=40)
    return await _run(photos.aircraft, hex_id or "", registration, timeout=40)


@router.get("/api/v1/mkt/flow/{layer}")
async def mkt_flow(layer: str):
    """Money flows: tic (cross-border portfolio flows), bis (bank lending), etf (fund creations and money flow),
    crypto (stablecoin supply), liquidity (Fed net liquidity)."""
    from api.marketdata import flows
    fn = {"tic": flows.tic, "bis": flows.bis, "etf": flows.etf, "crypto": flows.crypto, "liquidity": flows.liquidity}.get(layer)
    if not fn:
        raise HTTPException(404, "Unknown flow layer")
    return await _run(fn, timeout=120)


@router.get("/api/v1/mkt/flow/tic/{iso}")
async def mkt_flow_tic_country(iso: str):
    """Monthly cross-border securities flows between the US and one country (TIC)."""
    from api.marketdata import flows
    return await _run(flows.tic_country, iso[:2])


@router.get("/api/v1/mkt/edge/{layer}")
async def mkt_edge(layer: str):
    """Edge data: cot (CFTC positioning), pred (prediction markets), nowcasts, trade (PortWatch), ports, board (signal
    board).
    """
    from api.marketdata import edge
    fn = {"cot": edge.cot, "pred": edge.predictions, "nowcasts": edge.nowcasts, "trade": edge.trade, "ports": edge.ports_trade, "board": edge.board}.get(layer)
    if not fn:
        raise HTTPException(404, "Unknown edge layer")
    return await _run(fn, timeout=180)


@router.get("/api/v1/mkt/pred/browse")
async def mkt_pred_browse(q: str = "", venue: str = "", category: str = "", sort: str = "volume",
                          offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), active: bool = True, sports: bool = False):
    """Prediction markets (Kalshi + Polymarket): search / filter / sort every open event."""
    from api.marketdata import predmarkets
    return await _run(predmarkets.browse, q, venue, category, sort, offset, limit, active, sports, timeout=120)


@router.get("/api/v1/mkt/pred/event/{venue}/{event_id}")
async def mkt_pred_event(venue: str, event_id: str):
    """A prediction-market event with its markets and prices (Polymarket / Kalshi)."""
    from api.marketdata import predmarkets
    return await _run(predmarkets.event, venue, event_id, timeout=120)


@router.get("/api/v1/mkt/pred/history/{venue}/{market_id}")
async def mkt_pred_history(venue: str, market_id: str, series: str = "", span: str = "1m"):
    """Price history of a prediction market over a span."""
    from api.marketdata import predmarkets
    return await _run(predmarkets.history, venue, market_id, series or None, span, timeout=45)


@router.get("/api/v1/mkt/pred/book/{venue}/{market_id}")
async def mkt_pred_book(venue: str, market_id: str):
    """Order book of a prediction market."""
    from api.marketdata import predmarkets
    return await _run(predmarkets.orderbook, venue, market_id, timeout=30)


@router.get("/api/v1/mkt/cf/text")
async def mkt_filing_text(url: str = Query(..., max_length=400)):
    """An SEC filing (and an 8-K's press release) as plain text."""
    from api.marketdata import research
    return await _run(research.filing_text, url, timeout=90)


@router.get("/api/v1/mkt/cf/{symbol}")
async def mkt_filings(symbol: str, limit: int = Query(120, ge=10, le=400)):
    """A company's SEC filings with 8-K items decoded and each filing day's price reaction."""
    from api.marketdata import research
    return await _run(research.filings, symbol, limit, timeout=90)


@router.get("/api/v1/mkt/tech/{symbol}")
async def mkt_technicals(symbol: str):
    """Technical analysis: indicators, vote summary, trend, levels, and how each signal has worked on this stock."""
    from api.marketdata import toolkit
    return await _run(toolkit.technicals, symbol, timeout=90)


@router.get("/api/v1/mkt/sprd")
async def mkt_spread(a: str = Query(..., min_length=1, max_length=20), b: str = Query(..., min_length=1, max_length=20),
                     years: int = Query(5, ge=1, le=10), entry: float = Query(2.0, ge=0.5, le=4.0), exit: float = Query(0.5, ge=0.0, le=2.0)):
    """Pairs / spread analysis with cointegration, half-life and an out-of-sample z-score backtest."""
    from api.marketdata import toolkit
    return await _run(toolkit.spread, a, b, years, entry, exit, timeout=120)


@router.get("/api/v1/mkt/cbrt")
async def mkt_central_banks():
    """Policy rates of ~40 central banks (BIS)."""
    from api.marketdata import toolkit
    return await _run(toolkit.central_banks, timeout=120)


@router.get("/api/v1/mkt/ecos/search")
async def mkt_fred_search(q: str = Query(..., min_length=2, max_length=120)):
    """Search FRED series by text (ECOS)."""
    from api.marketdata import toolkit
    return await _run(toolkit.fred_search, q, timeout=45)


@router.get("/api/v1/mkt/ecos/series/{sid}")
async def mkt_fred_series(sid: str):
    """A FRED series with its metadata and history (ECOS)."""
    from api.marketdata import toolkit
    return await _run(toolkit.fred_series, sid, timeout=90)


# ── Bridgewater research frameworks ─────────────────────────────────────────
@router.get("/api/v1/mkt/bw/envr")
async def mkt_bw_environments():
    """All Weather environments: how each asset class did in each growth/inflation environment since 1950."""
    from api.marketdata import bridgewater
    return await _run(bridgewater.environments, timeout=180)


@router.get("/api/v1/mkt/bw/awp")
async def mkt_bw_all_weather(target_vol: float = Query(0.10, ge=0.03, le=0.25)):
    """All Weather construction (equal risk per environment), backtested vs 60/40."""
    from api.marketdata import bridgewater
    return await _run(bridgewater.all_weather, round(target_vol, 3), 2.0, timeout=180)


@router.get("/api/v1/mkt/bw/dcyc")
async def mkt_bw_debt_cycles():
    """Debt-cycle positions of ~40 economies (BIS) and the US monetary-policy stage."""
    from api.marketdata import bridgewater
    return await _run(bridgewater.debt_cycles, timeout=180)


@router.get("/api/v1/mkt/bw/hgrl")
async def mkt_bw_holy_grail(symbols: str = Query("SPY,EFA,EEM,TLT,IEF,TIP,LQD,HYG,GLD,DBC", max_length=600), years: int = Query(3, ge=1, le=10)):
    """Dalio's Holy Grail: how many independent bets a set of instruments really is."""
    from api.marketdata import bridgewater
    return await _run(bridgewater.holy_grail, symbols.split(","), years, timeout=90)


@router.get("/api/v1/mkt/bw/wpwr")
async def mkt_bw_world_order():
    """Changing World Order: the eight measures of national power."""
    from api.marketdata import bridgewater
    return await _run(bridgewater.world_order, timeout=180)


# ── Fixed income / FX ───────────────────────────────────────────────────────
@router.get("/api/v1/mkt/ilbe")
async def mkt_breakevens():
    """Inflation breakevens (ILBE): nominal minus real Treasury yields across tenors."""
    from api.marketdata import fixed_income
    return await _run(fixed_income.breakevens, timeout=90)


@router.get("/api/v1/mkt/tsy")
async def mkt_treasuries():
    """US Treasury board (TSY): bills, notes and bonds with prices and yields from TreasuryDirect."""
    from api.marketdata import fixed_income
    return await _run(fixed_income.treasuries, timeout=120)


@router.get("/api/v1/mkt/yas")
async def mkt_bond_calc(coupon: float = Query(..., ge=0, le=0.5), maturity: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                        price: Optional[float] = Query(None, gt=0, lt=1000), ytm: Optional[float] = Query(None, gt=-0.05, lt=1.0),
                        settle: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), freq: int = Query(2, ge=1, le=12)):
    """Bond calculator (YAS): price from yield or yield from price, with accrued interest, duration and convexity.

    Give either `price` or `ytm`; 422 when neither is given.
    """
    from api.marketdata import fixed_income
    if price is None and ytm is None:
        raise HTTPException(422, "Give a price or a yield.")
    return await _run(fixed_income.bond_calc, coupon, maturity, price, ytm, settle, freq, timeout=20)


@router.get("/api/v1/mkt/fxca")
async def mkt_fx_carry():
    """FX carry (FXCA): interest-rate differentials against the dollar and the carry-to-volatility ratio."""
    from api.marketdata import fixed_income
    return await _run(fixed_income.fx_carry, timeout=120)


# ── Corporate ────────────────────────────────────────────────────────────────
@router.get("/api/v1/mkt/cacs")
async def mkt_actions_calendar(days: int = Query(14, ge=1, le=30)):
    """Corporate actions coming up in the next `days` (CACS): splits, dividends, spin-offs."""
    from api.marketdata import corporate
    return await _run(corporate.actions_calendar, days, timeout=90)


@router.get("/api/v1/mkt/cacs/{symbol}")
async def mkt_actions(symbol: str):
    """A company's corporate actions (CACS)."""
    from api.marketdata import corporate
    return await _run(corporate.actions, symbol, timeout=60)


@router.get("/api/v1/mkt/mgmt/{symbol}")
async def mkt_management(symbol: str):
    """Officers and directors (MGMT)."""
    from api.marketdata import corporate
    return await _run(corporate.management, symbol, timeout=90)


@router.get("/api/v1/mkt/pgeo/{symbol}")
async def mkt_segments(symbol: str):
    """Revenue by segment and geography (PGEO) from SEC filings where reported."""
    from api.marketdata import corporate
    return await _run(corporate.segments, symbol, timeout=120)


@router.get("/api/v1/mkt/ddis/{symbol}")
async def mkt_debt(symbol: str):
    """Debt maturity profile (DDIS) from SEC filings."""
    from api.marketdata import corporate
    return await _run(corporate.debt_maturities, symbol, timeout=90)


@router.get("/api/v1/mkt/ma")
async def mkt_deals():
    """Recent M&A deals (MA) from SEC merger filings."""
    from api.marketdata import corporate
    return await _run(corporate.deals, timeout=180)


# ── Funds / indices ──────────────────────────────────────────────────────────
@router.get("/api/v1/mkt/memb/{code}")
async def mkt_members(code: str):
    """Constituents of an index (MEMB)."""
    from api.marketdata import funds
    return await _run(funds.index_members, code, timeout=90)


@router.get("/api/v1/mkt/fsrc")
async def mkt_fund_screener():
    """ETF screener (FSRC): size, cost, performance and category."""
    from api.marketdata import funds
    return await _run(funds.etf_screener, timeout=180)


@router.get("/api/v1/mkt/fsrc/compare")
async def mkt_fund_compare(a: str = Query(..., max_length=15), b: str = Query(..., max_length=15)):
    """Two ETFs side by side: cost, holdings overlap, performance."""
    from api.marketdata import funds
    return await _run(funds.etf_compare, a, b, timeout=90)


# ── Workbench ────────────────────────────────────────────────────────────────
@router.get("/api/v1/mkt/g")
async def mkt_formula_chart(e: List[str] = Query(..., max_length=6), period: str = Query("5y", pattern="^(1y|2y|5y|10y|20y|max)$")):
    """Formula charts over instruments and FRED series."""
    from api.marketdata import workbench
    return await _run(workbench.formula_chart, e, period, timeout=120)


@router.get("/api/v1/mkt/bdp")
async def mkt_data_grid(symbols: str = Query(..., max_length=1500), fields: str = Query("", max_length=600)):
    """Data grid (BDP): current fields for many symbols at once."""
    from api.marketdata import workbench
    return await _run(workbench.data_grid, symbols.split(","), [f for f in fields.split(",") if f], timeout=120)


@router.get("/api/v1/mkt/bdh")
async def mkt_history_grid(symbols: str = Query(..., max_length=800), period: str = "1y", interval: str = "1d",
                           field: str = Query("close", pattern="^(close|return|volume)$")):
    """History grid (BDH): close, return or volume for many symbols on common dates."""
    from api.marketdata import workbench
    return await _run(workbench.history_grid, symbols.split(","), period, interval, field, timeout=120)


@router.get("/api/v1/mkt/ovdv/{symbol}")
async def mkt_vol_surface(symbol: str):
    """Implied-volatility surface (OVDV) across strikes and expiries."""
    from api.marketdata import workbench
    return await _run(workbench.vol_surface, symbol, timeout=120)


@router.get("/api/v1/mkt/cdr")
async def mkt_exchanges():
    """Exchange calendar (CDR): trading hours, holidays and whether each venue is open now."""
    from api.marketdata import workbench
    return await _run(workbench.exchanges, timeout=20)


@router.get("/api/v1/mkt/cred")
async def mkt_credit():
    """Credit spreads (ICE BofA OAS) by rating and region."""
    from api.marketdata import research
    return await _run(research.credit, timeout=90)


@router.get("/api/v1/mkt/fac/{symbol}")
async def mkt_factors(symbol: str, years: int = Query(5, ge=2, le=20)):
    """Fama–French 5 + momentum exposures of one stock (full period and rolling one-year)."""
    from api.marketdata import research
    return await _run(research.factor_exposure, symbol, years, timeout=120)


@router.post("/api/v1/mkt/port/risk")
async def mkt_portfolio_risk(body: Dict[str, Any] = Body(...)):
    """Portfolio risk for a list of holdings [{symbol, quantity}]: exposures, VaR, risk shares, factors, stress tests.
    """
    from api.marketdata import research
    rows = body.get("holdings") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise HTTPException(422, "Send {'holdings': [{'symbol': 'AAPL', 'quantity': 10}, …]}")
    return await _run(research.portfolio_risk, rows, timeout=240)


@router.get("/api/v1/mkt/pred/related")
async def mkt_pred_related(q: str = Query(..., min_length=2, max_length=300), limit: int = Query(6, ge=1, le=20)):
    """Prediction markets related to a screen: comma-separated terms (company, country, 'fed', 'oil'…)."""
    from api.marketdata import predmarkets
    return await _run(predmarkets.related, q.split(","), limit, timeout=120)


@router.get("/api/v1/mkt/etfarb")
async def mkt_etf_premium():
    """ETF premiums / discounts to NAV across ~50 liquid ETFs."""
    from api.marketdata import etfarb
    return await _run(etfarb.snapshot, timeout=120)


@router.get("/api/v1/mkt/pred/arb")
async def mkt_pred_arb(kalshi_fee: float = Query(0.07, ge=0, le=0.2), poly_fee: float = Query(0.0, ge=0, le=0.1),
                       min_edge: float = Query(-0.03, ge=-0.5, le=0.5)):
    """Cross-venue arbitrage: the same yes/no question on Polymarket and Kalshi, priced at executable asks after fees.
    """
    from api.marketdata import predarb
    return await _run(predarb.scan, kalshi_fee, poly_fee, min_edge, timeout=180)


@router.get("/api/v1/mkt/pred/arb/check")
async def mkt_pred_arb_check(poly: str = Query(..., min_length=3, max_length=300), kalshi: str = Query(..., min_length=3, max_length=120),
                             kalshi_fee: float = Query(0.07, ge=0, le=0.2), poly_fee: float = Query(0.0, ge=0, le=0.1)):
    """Arbitrage check for a pair you choose: a Polymarket question (URL, slug or token id) and a Kalshi market ticker.
    """
    from api.marketdata import predarb

    def run():
        try:
            return predarb.check(poly, kalshi, kalshi_fee, poly_fee)
        except ValueError as e:
            return {"error": str(e)}
    out = await _run(run, timeout=60)
    if isinstance(out, dict) and out.get("error") and len(out) == 1:
        raise HTTPException(400, out["error"])
    return out


@router.get("/api/v1/mkt/pred/{layer}")
async def mkt_pred_layer(layer: str, sports: bool = False):
    """movers / cross (same question on both venues) / macro (Fed odds vs futures and macro markets)."""
    from api.marketdata import predmarkets
    if layer == "movers":
        return await _run(predmarkets.movers, 5000, sports, timeout=120)
    fn = {"cross": predmarkets.cross_venue, "macro": predmarkets.macro}.get(layer)
    if not fn:
        raise HTTPException(404, "Unknown prediction-market layer")
    return await _run(fn, timeout=150)


@router.get("/api/v1/mkt/ins/{layer}")
async def mkt_insights(layer: str):
    """Market internals: vol (volatility complex), breadth (S&P 500), impm (earnings implied moves), uoa (unusual
    options), risk (regime).
    """
    from api.marketdata import insights
    fn = {"vol": insights.vol, "breadth": insights.breadth, "impm": insights.implied_moves, "uoa": insights.uoa, "risk": insights.risk}.get(layer)
    if not fn:
        raise HTTPException(404, "Unknown layer")
    return await _run(fn, timeout=240)


@router.get("/api/v1/mkt/fly")
async def mkt_flights(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), radius_nm: int = Query(100, ge=5, le=250)):
    """Live aircraft around a point (same as /fly/area)."""
    from api.marketdata import airtraffic
    return await _run(airtraffic.area, lat, lon, radius_nm, timeout=45)


@router.get("/api/v1/mkt/fly/airports")
async def mkt_airports():
    """Airports tracked by the flight monitor, with coordinates."""
    from api.marketdata import tracking
    return {"airports": [{"code": k, "name": v[0], "lat": v[1], "lon": v[2]} for k, v in tracking.AIRPORTS.items()]}


@router.get("/api/v1/mkt/quakes")
async def mkt_quakes(min_mag: float = Query(4.5, ge=4.5, le=9)):
    """USGS earthquakes (past week) with distance to the nearest major port and chokepoint."""
    from api.marketdata import tracking
    return await _run(tracking.earthquakes, min_mag)


@router.get("/api/v1/mkt/wirp")
async def mkt_wirp():
    """Fed rate-move probabilities from fed funds futures (FedWatch method)."""
    from api.marketdata import extras
    return await _run(extras.wirp, timeout=90)


@router.get("/api/v1/mkt/auct")
async def mkt_auctions(kind: str = Query("Note", pattern="^(Bill|Note|Bond|TIPS|FRN)$"), limit: int = Query(40, ge=5, le=100)):
    """US Treasury auction results (AUCT) for a security type: bid-to-cover, tails, allotments."""
    from api.marketdata import extras
    return await _run(extras.auctions, kind, limit)


@router.get("/api/v1/mkt/eia")
async def mkt_eia():
    """Weekly US energy inventories (EIA): crude, gasoline and distillates against seasonal norms."""
    from api.marketdata import extras
    return await _run(extras.energy)


@router.get("/api/v1/mkt/eia/history")
async def mkt_eia_history(weeks: int = Query(520, ge=52, le=1040)):
    """History of the weekly EIA inventory series."""
    from api.marketdata import extras
    return await _run(extras.eia_history, weeks, timeout=90)


@router.get("/api/v1/mkt/ipo")
async def mkt_ipo():
    """IPO calendar (Nasdaq)."""
    from api.marketdata import extras
    return await _run(extras.ipo_calendar)


@router.get("/api/v1/mkt/wetr")
async def mkt_weather():
    """Weather for energy and agriculture regions (WETR): temperature anomalies and degree days."""
    from api.marketdata import extras
    return await _run(extras.weather, timeout=90)


@router.get("/api/v1/mkt/insd/{symbol}")
async def mkt_insiders(symbol: str, limit: int = Query(40, ge=5, le=100)):
    """Insider transactions (INSD) from SEC Form 4 filings."""
    from api.marketdata import extras
    return await _run(extras.insiders, symbol, limit, timeout=120)


@router.get("/api/v1/mkt/13f")
async def mkt_13f(cik: str = Query("0001067983", pattern=r"^\d{1,10}$")):
    """An institution's 13F holdings by CIK (default Berkshire Hathaway), with changes from the prior filing."""
    from api.marketdata import extras
    return await _run(extras.thirteen_f, cik, timeout=120)


@router.get("/api/v1/mkt/fund/{symbol}")
async def mkt_fund(symbol: str):
    """ETF / mutual fund: top holdings, sector weights, asset mix, expense ratio, assets."""
    from api.marketdata import security
    return await _run(security.fund_holdings, symbol)


@router.get("/api/v1/mkt/tape/{symbol}")
async def mkt_tape(symbol: str):
    """Intraday prints (1-minute bars), VWAP, tick-rule buy/sell volume and volume profile."""
    from api.marketdata import core
    return await _run(core.tape, symbol)


@router.get("/api/v1/mkt/map/world")
async def mkt_world_map():
    """Every country: markets (ETF, index, currency, 10y yield), IMF economy, sovereign risk."""
    from api.marketdata import countries
    return await _run(countries.world_data, timeout=120)


@router.get("/api/v1/mkt/evts")
async def mkt_earnings_calendar(start: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), days: int = Query(7, ge=1, le=31),
                                min_cap_bn: float = Query(0, ge=0), offset: int = Query(0, ge=0), limit: int = Query(100, ge=10, le=250)):
    """Earnings calendar (EVTS) over `days` from `start`, filtered by market cap, with each company placed in a country
    and region.
    """
    from api.marketdata import monitors
    from api.marketdata.countries import country_of_symbol, region_of
    out = await _run(monitors.earnings_calendar, start, days, min_cap_bn, offset, limit)
    for r in out.get("rows", []):                       # place each company in a country and region
        # OTC lines of foreign companies carry their home country when it is known, else none
        c = r.get("country") or (None if r.get("otc_foreign") else country_of_symbol(r.get("symbol") or ""))
        r["country"], r["region"] = c or None, region_of(c) if c else None
    return out


@router.get("/api/v1/mkt/regions")
async def mkt_regions():
    """Regions, their countries and their screener markets."""
    from api.marketdata import countries as C
    return {"regions": [{"id": k, "name": v, "markets": C.REGION_MARKETS[k],
                         "countries": sorted(c["iso2"] for c in C.COUNTRIES if C.region_of(c["iso2"]) == k)} for k, v in C.REGION_NAMES.items()],
            "names": {c["iso2"]: c["name"] for c in C.COUNTRIES}}


@router.get("/api/v1/mkt/region/{region}")
async def mkt_region(region: str):
    """Country matrix for a region: index, currency, 10y yield, IMF macro, sovereign risk."""
    from api.marketdata import countries as C
    if region not in C.REGION_NAMES and region != "global":
        raise HTTPException(404, "Region: global, americas, europe, mea or apac.")
    w = await _run(C.world_data, timeout=120)
    rows = [{"iso2": k, **v} for k, v in w["countries"].items() if region == "global" or v.get("region") == region]
    rows.sort(key=lambda r: -(r.get("gdp_usd_bn") or 0))          # largest economies first
    return {"region": region, "name": C.REGION_NAMES.get(region, "Global"), "markets": C.REGION_MARKETS.get(region, list(C.REGION_MARKETS["americas"][:1])),
            "countries": rows, "sources": w["sources"], "year": w["year"]}


@router.get("/api/v1/mkt/country/{iso2}")
async def mkt_country(iso2: str):
    """One country: markets, economy, risk, plus its index / currency / screener market for the page."""
    from api.marketdata import countries as C
    c = iso2.upper()
    if c not in C.BY_ISO2:
        raise HTTPException(404, f"Unknown country code '{iso2}'.")
    w = await _run(C.world_data, timeout=120)
    rec = {"iso2": c, **w["countries"].get(c, {"name": C.BY_ISO2[c]["name"]})}
    rec["market"] = c.lower() if c.lower() in _regions() else None
    rec["fx_symbol"] = None if rec.get("currency") == "USD" else f"{rec.get('currency')}=X"
    rec["region_name"] = C.REGION_NAMES.get(rec.get("region") or C.region_of(c))
    return rec


@router.get("/api/v1/mkt/wcrs")
async def mkt_fx_matrix(ccys: Optional[str] = None):
    """Cross-currency matrix (WCRS): spot rates and daily changes among the given currencies."""
    from api.marketdata import monitors
    return await _run(monitors.fx_matrix, ccys.upper().split(",") if ccys else None)


@router.get("/api/v1/mkt/btmm")
async def mkt_money_markets():
    """Money-market rates (BTMM): policy rates, overnight rates, bills and the front of the curve."""
    from api.marketdata import monitors
    return await _run(monitors.money_markets, timeout=90)


@router.get("/api/v1/mkt/imap")
async def mkt_heatmap(country: str = Query("US", min_length=2, max_length=2), max_names: int = Query(300, ge=20, le=500)):
    """Equity heatmap (IMAP) of a country's largest companies by sector and daily change."""
    from api.marketdata import monitors
    return await _run(monitors.heatmap, country, max_names, timeout=90)


@router.get("/api/v1/mkt/crypto")
async def mkt_crypto(limit: int = Query(100, ge=10, le=250)):
    """Crypto market: the largest coins by market cap with price and changes."""
    from api.marketdata import monitors
    return await _run(monitors.crypto, limit)


@router.get("/api/v1/mkt/futures/{root}")
async def mkt_futures_curve(root: str, n: int = Query(60, ge=3, le=80)):
    """Futures curve of a contract root (contango / backwardation) up to `n` expiries."""
    from api.marketdata import monitors
    return await _run(monitors.futures_curve, root, n)


@router.get("/api/v1/mkt/futures")
async def mkt_futures_roots():
    """Futures contracts available for curves."""
    from api.marketdata import monitors
    return {"roots": [{"root": k, "name": v[0], "exchange": v[1]} for k, v in monitors.FUTURES.items()]}


@router.get("/api/v1/mkt/news")
async def mkt_news_hub(q: Optional[str] = Query(None, max_length=60), limit: int = Query(60, ge=10, le=200),
                       region: Optional[str] = Query(None, pattern="^(global|americas|europe|mea|apac)$"),
                       country: Optional[str] = Query(None, pattern="^[A-Za-z]{2}$")):
    """News hub: headlines by query, region or country, with sources and times."""
    from api.marketdata import monitors
    return await _run(monitors.news_hub, q, limit, region, country, timeout=60)


# ── Your tools: watchlists, alerts, journal (per signed-in user) ─────────────
from fastapi import Request
from pydantic import BaseModel


def _owner(request: Request) -> str:
    from api.core.access import require_roles
    return require_roles(request, {"pm", "quant", "analyst", "risk", "viewer", "trader"})["username"]


async def _user_op(fn, *a):
    try:
        return await asyncio.to_thread(fn, *a)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


class WatchlistIn(BaseModel):
    """A watchlist: name and symbols."""
    name: Optional[str] = None
    symbols: Optional[List[str]] = None
    shared: Optional[bool] = None


class NoteIn(BaseModel):
    """A team note: the panel or symbol it belongs to and the text."""
    target: str
    text: str


class AlertIn(BaseModel):
    """A price alert: symbol, condition (above / below / percent move) and level."""
    symbol: str
    kind: str
    value: float
    note: Optional[str] = None


class JournalIn(BaseModel):
    """A journal entry: title, body, tags and optional symbol."""
    date: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[float] = None
    entry: Optional[float] = None
    exit: Optional[float] = None
    exit_date: Optional[str] = None
    thesis: Optional[str] = None
    outcome: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


# ── Futu OpenAPI (read-only; needs FutuOpenD running and logged in on this computer) ──────────────────────────────
async def _futu(fn, *a):
    from api.providers import futu_provider as fp
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a), 20)
    except fp.FutuUnavailable as e:
        raise HTTPException(503, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, "FutuOpenD did not answer within 20 s.")


# ── Interactive Brokers TWS (market data only; needs TWS / IB Gateway running with the API enabled) ────────────────
async def _ibkr(fn, *a, timeout: float = 45):
    from api.providers import ibkr_tws as it
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a), timeout)
    except it.IbkrUnavailable as e:
        raise HTTPException(503, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, "TWS did not answer in time.")


@router.get("/api/v1/mkt/actions")
async def mkt_actions(days: int = Query(3, ge=1, le=30)):
    """Analyst & company actions (ACTN): market-wide rating changes — upgrades, downgrades, initiations, target changes —
    and company guidance changes, from Benzinga."""
    from api.providers import benzinga as bz
    if not bz.available():
        raise HTTPException(503, "BENZINGA_API_KEY is not set.")
    try:
        ratings, guidance = await asyncio.gather(asyncio.to_thread(bz.ratings, None, days, 500), asyncio.to_thread(bz.guidance, max(days, 14), 200))
    except bz.BenzingaError as e:
        raise HTTPException(503, str(e))
    return {"ratings": ratings, "guidance": guidance, "days": days,
            "counts": {"upgrades": sum(1 for r in ratings if (r["action"] or "").startswith("Upgrade")),
                       "downgrades": sum(1 for r in ratings if (r["action"] or "").startswith("Downgrade")),
                       "initiations": sum(1 for r in ratings if (r["action"] or "").startswith("Initiat")),
                       "target_raised": sum(1 for r in ratings if (r["pt_change"] or 0) > 0),
                       "target_cut": sum(1 for r in ratings if (r["pt_change"] or 0) < 0),
                       "guidance_raised": sum(1 for g in guidance if g["direction"] == "raised"),
                       "guidance_lowered": sum(1 for g in guidance if g["direction"] == "lowered")},
            "source": "Benzinga (analyst ratings, guidance)"}


@router.get("/api/v1/mkt/ibkr/status")
async def mkt_ibkr_status():
    """Whether TWS / IB Gateway is reachable through the socket API (read-only)."""
    from api.providers import ibkr_tws as it
    return await asyncio.to_thread(it.status)


@router.get("/api/v1/mkt/ibkr/quotes")
async def mkt_ibkr_quotes(symbols: str = Query(..., min_length=1)):
    """IBKR quotes for comma-separated Yahoo-style symbols: real-time where subscribed, delayed otherwise (flagged)."""
    from api.providers import ibkr_tws as it
    return {"rows": await _ibkr(it.quotes, symbols.split(",")), "source": "Interactive Brokers (TWS API)"}


@router.get("/api/v1/mkt/ibkr/history/{symbol}")
async def mkt_ibkr_history(symbol: str, duration: str = Query("1 Y", pattern=r"^\d{1,3} [DWMY]$"),
                           bar: str = Query("1 day", pattern=r"^(1 day|1 week|1 hour|30 mins|5 mins)$")):
    """Historical bars from IBKR for a stock listing."""
    from api.providers import ibkr_tws as it
    return await _ibkr(it.history, symbol, duration, bar, timeout=90)


@router.get("/api/v1/mkt/futu/status")
async def mkt_futu_status():
    """Whether FutuOpenD is running and logged in, and the account's quote entitlements."""
    from api.providers import futu_provider as fp
    return await asyncio.to_thread(fp.status)


@router.get("/api/v1/mkt/futu/snapshot")
async def mkt_futu_snapshot(symbols: str = Query(..., min_length=1)):
    """Real-time snapshots (HK, US, SH, SZ, SG) for comma-separated Yahoo-style symbols."""
    from api.providers import futu_provider as fp
    return {"rows": await _futu(fp.snapshot, symbols.split(",")), "source": "Futu OpenAPI"}


@router.get("/api/v1/mkt/futu/{kind}/{symbol}")
async def mkt_futu_detail(kind: str, symbol: str):
    """Order book, ticks, capital flow or (Hong Kong) broker queue for one symbol."""
    from api.providers import futu_provider as fp
    fn = {"book": fp.order_book, "ticks": fp.ticks, "flow": fp.capital_flow, "brokers": fp.broker_queue}.get(kind)
    if not fn:
        raise HTTPException(404, "kind must be book, ticks, flow or brokers")
    return await _futu(fn, symbol)


@router.get("/api/v1/futu/positions/manage")
async def futu_positions_manage():
    """Hold / tighten / trim / exit / add advice for each position in the Futu account (read-only)."""
    from api import trade_manager
    from api.providers import futu_provider as fp
    try:
        return await trade_manager.manage_futu()
    except fp.FutuUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/futu/positions")
async def futu_positions():
    """Futu account positions — query only; trading is never unlocked and no order is ever sent."""
    from api.providers import futu_provider as fp
    return await _futu(fp.positions)


@router.get("/api/v1/mkt/quotes")
async def mkt_quotes(symbols: str = Query(..., min_length=1)):
    """Quotes for several symbols in one call (watchlists and tiles)."""
    from api.marketdata import usertools
    try:
        return {"quotes": await asyncio.to_thread(usertools.quotes, symbols.split(","))}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/mkt/watchlists")
async def mkt_watchlists(request: Request):
    """Your watchlists."""
    from api.marketdata import usertools
    return {"watchlists": await _user_op(usertools.list_watchlists, _owner(request))}


@router.post("/api/v1/mkt/watchlists")
async def mkt_watchlist_create(body: WatchlistIn, request: Request):
    """Create a watchlist."""
    from api.marketdata import usertools
    return await _user_op(usertools.create_watchlist, _owner(request), body.name or "Watchlist", body.symbols or [])


@router.put("/api/v1/mkt/watchlists/{wid}")
async def mkt_watchlist_update(wid: int, body: WatchlistIn, request: Request):
    """Rename a watchlist or change its symbols."""
    from api.marketdata import usertools
    return await _user_op(usertools.update_watchlist, _owner(request), wid, body.name, body.symbols, body.shared)


@router.delete("/api/v1/mkt/watchlists/{wid}")
async def mkt_watchlist_delete(wid: int, request: Request):
    """Delete a watchlist."""
    from api.marketdata import usertools
    await _user_op(usertools.delete_watchlist, _owner(request), wid)
    return {"deleted": wid}


@router.get("/api/v1/mkt/notes")
async def mkt_notes(target: str, request: Request):
    """Team notes for a panel or symbol (shared desk notes)."""
    from api.marketdata import usertools
    _owner(request)
    return {"notes": await _user_op(usertools.list_notes, target)}


@router.post("/api/v1/mkt/notes")
async def mkt_note_add(body: NoteIn, request: Request):
    """Add a note."""
    from api.marketdata import usertools
    return await _user_op(usertools.add_note, _owner(request), body.target, body.text)


@router.delete("/api/v1/mkt/notes/{nid}")
async def mkt_note_delete(nid: int, request: Request):
    """Delete a note (its author or an administrator)."""
    from api.marketdata import usertools
    await _user_op(usertools.delete_note, _owner(request), nid)
    return {"deleted": nid}


@router.get("/api/v1/mkt/alerts")
async def mkt_alerts(request: Request):
    """Your price alerts."""
    from api.marketdata import usertools
    from api.marketdata import field_alerts
    from api.notify import channels
    return {"alerts": await _user_op(usertools.list_alerts, _owner(request)), "kinds": usertools.ALERT_KINDS,
            "fields": field_alerts.describe(), "delivery": {"in_app": True, "browser": True, **channels()}}


@router.get("/api/v1/mkt/alerts/triggered")
async def mkt_alerts_triggered(request: Request):
    """Alerts that have triggered and not yet been seen."""
    from api.marketdata import usertools
    return {"alerts": await _user_op(usertools.triggered_unseen, _owner(request))}


@router.post("/api/v1/mkt/alerts")
async def mkt_alert_create(body: AlertIn, request: Request):
    """Create a price alert (checked every five minutes by the scheduler)."""
    from api.marketdata import usertools
    return await _user_op(usertools.create_alert, _owner(request), body.symbol, body.kind, body.value, body.note)


@router.post("/api/v1/mkt/alerts/seen")
async def mkt_alerts_seen(request: Request):
    """Mark triggered alerts as seen."""
    from api.marketdata import usertools
    return {"marked": await _user_op(usertools.mark_seen, _owner(request))}


@router.post("/api/v1/mkt/alerts/check")
async def mkt_alerts_check(request: Request):
    """Check your alerts now instead of waiting for the scheduler."""
    from api.marketdata import usertools
    _owner(request)
    try:
        return await asyncio.to_thread(usertools.check_alerts)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.delete("/api/v1/mkt/alerts/{aid}")
async def mkt_alert_delete(aid: int, request: Request):
    """Delete an alert."""
    from api.marketdata import usertools
    await _user_op(usertools.delete_alert, _owner(request), aid)
    return {"deleted": aid}


@router.get("/api/v1/mkt/journal")
async def mkt_journal(request: Request):
    """Your trading journal entries."""
    from api.marketdata import usertools
    return await _user_op(usertools.list_journal, _owner(request))


@router.post("/api/v1/mkt/journal")
async def mkt_journal_create(body: JournalIn, request: Request):
    """Add a journal entry."""
    from api.marketdata import usertools
    return await _user_op(usertools.create_journal, _owner(request), body.model_dump(exclude_none=True))


@router.put("/api/v1/mkt/journal/{jid}")
async def mkt_journal_update(jid: int, body: JournalIn, request: Request):
    """Edit a journal entry."""
    from api.marketdata import usertools
    return await _user_op(usertools.update_journal, _owner(request), jid, body.model_dump(exclude_unset=True))


@router.delete("/api/v1/mkt/journal/{jid}")
async def mkt_journal_delete(jid: int, request: Request):
    """Delete a journal entry."""
    from api.marketdata import usertools
    await _user_op(usertools.delete_journal, _owner(request), jid)
    return {"deleted": jid}


@router.get("/api/v1/mkt/map")
async def mkt_world_map_markets():
    """World market map: each country's main index and daily change."""
    from api.marketdata import monitors
    return await _run(monitors.world_map_markets, timeout=90)


def _regions():
    from api.marketdata.core import REGIONS
    return REGIONS
