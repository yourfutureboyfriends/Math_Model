"""Markets mode endpoints (api/marketdata): universal search, quotes, overview, profiles,
statements, news + SEC filings, movers and the global screener. Read-only market data."""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["markets"])


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


@router.get("/api/v1/mkt/search")
async def mkt_search(q: str = Query(..., min_length=1, max_length=60), limit: int = Query(12, ge=1, le=25)):
    from api.marketdata import core
    return {"query": q, "results": await _run(core.search, q, limit)}


@router.get("/api/v1/mkt/quote/{symbol}")
async def mkt_quote(symbol: str):
    from api.marketdata import core
    return await _run(core.quote, symbol)


@router.get("/api/v1/mkt/overview")
async def mkt_overview():
    from api.marketdata import core
    return await _run(core.overview, timeout=90)


@router.get("/api/v1/mkt/profile/{symbol}")
async def mkt_profile(symbol: str):
    from api.marketdata import core
    return await _run(core.profile, symbol)


@router.get("/api/v1/mkt/statements/{symbol}")
async def mkt_statements(symbol: str):
    from api.marketdata import core
    return await _run(core.statements, symbol, timeout=60)


@router.get("/api/v1/mkt/news/{symbol}")
async def mkt_news(symbol: str):
    from api.marketdata import core
    return await _run(core.news, symbol)


@router.get("/api/v1/mkt/movers")
async def mkt_movers(region: str = "us", kind: str = Query("gainers", pattern="^(gainers|losers|active)$"),
                     count: int = Query(25, ge=5, le=100)):
    from api.marketdata import core
    return await _run(core.movers, region, kind, count)


@router.get("/api/v1/mkt/screen")
async def mkt_screen(regions: str = "us", sector: Optional[str] = None, sort: str = "market_cap", ascending: bool = False,
                     size: int = Query(50, ge=5, le=250), offset: int = Query(0, ge=0, le=5000),
                     market_cap_min: Optional[float] = None, market_cap_max: Optional[float] = None,
                     pe_min: Optional[float] = None, pe_max: Optional[float] = None,
                     dividend_yield_min: Optional[float] = None, change_pct_min: Optional[float] = None,
                     change_pct_max: Optional[float] = None, price_min: Optional[float] = None):
    from api.marketdata import core
    regs: List[str] = [r.strip().lower() for r in regions.split(",") if r.strip()]
    return await _run(core.screen, regs, sector, sort, ascending, size, offset,
                      market_cap_min=market_cap_min, market_cap_max=market_cap_max, pe_min=pe_min, pe_max=pe_max,
                      dividend_yield_min=dividend_yield_min, change_pct_min=change_pct_min,
                      change_pct_max=change_pct_max, price_min=price_min)


@router.get("/api/v1/mkt/meta")
async def mkt_meta():
    from api.marketdata import core
    return {"regions": [{"id": k, "name": v, "currency": core.REGION_CCY[k]} for k, v in core.REGIONS.items()],
            "sectors": core.SECTORS, "sorts": list(core.SORTS), "overview_groups": list(core.OVERVIEW)}


# ── Single-security functions (Bloomberg mnemonics) ──────────────────────────
@router.get("/api/v1/mkt/ern/{symbol}")
async def mkt_earnings(symbol: str):
    from api.marketdata import security
    return await _run(security.earnings, symbol)


@router.get("/api/v1/mkt/anr/{symbol}")
async def mkt_analysts(symbol: str):
    from api.marketdata import security
    return await _run(security.analysts, symbol)


@router.get("/api/v1/mkt/hds/{symbol}")
async def mkt_holders(symbol: str):
    from api.marketdata import security
    return await _run(security.holders, symbol)


@router.get("/api/v1/mkt/dvd/{symbol}")
async def mkt_dividends(symbol: str):
    from api.marketdata import security
    return await _run(security.dividends, symbol)


@router.get("/api/v1/mkt/omon/{symbol}")
async def mkt_options(symbol: str, expiry: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    from api.marketdata import security
    return await _run(security.options, symbol, expiry)


@router.get("/api/v1/mkt/omon/{symbol}/term")
async def mkt_iv_term(symbol: str):
    from api.marketdata import security
    return {"symbol": symbol.upper(), "term": await _run(security.iv_term_structure, symbol, timeout=90)}


@router.get("/api/v1/mkt/rv/{symbol}")
async def mkt_comps(symbol: str):
    from api.marketdata import security
    return await _run(security.comps, symbol, timeout=90)


@router.get("/api/v1/mkt/hp/{symbol}")
async def mkt_history(symbol: str, period: str = "1y", interval: str = "1d"):
    from api.marketdata import security
    return await _run(security.history, symbol, period, interval)


@router.get("/api/v1/mkt/comp")
async def mkt_compare(symbols: str = Query(..., min_length=1), period: str = Query("5y", pattern="^(1mo|3mo|6mo|1y|2y|5y|10y|max|ytd)$")):
    from api.marketdata import security
    return await _run(security.compare, symbols.split(","), period)


@router.get("/api/v1/mkt/beta/{symbol}")
async def mkt_beta(symbol: str, benchmark: str = "^GSPC", period: str = Query("2y", pattern="^(1y|2y|3y|5y|10y)$"),
                   freq: str = Query("W", pattern="^(D|W|M)$")):
    from api.marketdata import security
    return await _run(security.beta, symbol, benchmark, period, freq)


@router.get("/api/v1/mkt/dcf/{symbol}")
async def mkt_dcf(symbol: str, growth: Optional[float] = Query(None, ge=-0.5, le=2.0), years: int = Query(10, ge=3, le=30),
                  terminal_growth: Optional[float] = Query(None, ge=-0.05, le=0.15), target_margin: Optional[float] = Query(None, ge=-1.0, le=0.9),
                  sales_to_capital: Optional[float] = Query(None, gt=0, le=20), ronic: Optional[float] = Query(None, gt=0, le=2.0),
                  discount: Optional[float] = Query(None, gt=0, lt=0.4), beta: Optional[float] = Query(None, ge=-1, le=5),
                  erp: Optional[float] = Query(None, ge=0, le=0.15), include_leases: bool = False, mid_year: bool = True,
                  roe: Optional[float] = Query(None, ge=-0.5, le=1.0), terminal_roe: Optional[float] = Query(None, gt=0, le=1.0),
                  payout: Optional[float] = Query(None, ge=0, le=1.0), model: Optional[str] = Query(None, pattern="^(fcff|excess_return)$")):
    """FCFF discounted at WACC (Damodaran / McKinsey) for operating companies; Damodaran's excess-return
    model for banks and insurers. Reverse DCF and sensitivity grids for both."""
    from api.marketdata import dcf
    inp = await _run(dcf.inputs, symbol, timeout=60)
    use_fin = model == "excess_return" or (model is None and inp.get("is_financial"))
    if use_fin:
        kw = dict(years=years, roe=roe, terminal_roe=terminal_roe, payout=payout, terminal_growth=terminal_growth, beta=beta, erp=erp, discount=discount)
        val = await _run(dcf.value_financial, inp, **kw)
        sens = await _run(dcf.sensitivity_financial, inp, val, **kw)
        implied = await _run(dcf.reverse_financial, inp, **{k: v for k, v in kw.items() if k not in ("roe", "terminal_roe")})
        return {"inputs": inp, "valuation": val, "sensitivity": sens, "market_implied_roe": implied, "model": "excess_return",
                "method": "Excess-return model: equity = book value + PV of (ROE − cost of equity) × book value, with ROE and payout "
                          "converging to stable levels and stable growth ≤ the risk-free rate. Source: Damodaran (NYU Stern)."}
    kw = dict(growth=growth, years=years, terminal_growth=terminal_growth, target_margin=target_margin, sales_to_capital=sales_to_capital,
              ronic=ronic, discount=discount, beta=beta, erp=erp, include_leases=include_leases, mid_year=mid_year)
    val = await _run(dcf.value, inp, **kw)
    sens = await _run(dcf.sensitivity, inp, val, **kw)
    rkw = {k: v for k, v in kw.items() if k != "growth"}
    implied = await _run(dcf.reverse, inp, **rkw)
    bound = await _run(dcf.reverse_bound, inp, **rkw) if implied is None else None
    return {"inputs": inp, "valuation": val, "sensitivity": sens, "market_implied_growth": implied, "market_implied_growth_bound": bound, "model": "fcff",
            "method": "FCFF at WACC with mid-year discounting; terminal value = NOPAT × (1 − g/RONIC) ÷ (WACC − g). "
                      "SBC is expensed (inside GAAP operating income). Inputs from Damodaran's market data (implied ERP, "
                      "industry betas, country risk). Sources: Damodaran (NYU Stern); Koller, Goedhart & Wessels, Valuation (McKinsey)."}


@router.get("/api/v1/mkt/dcf/{symbol}/xlsx")
async def mkt_dcf_excel(symbol: str, growth: Optional[float] = Query(None, ge=-0.5, le=2.0), years: int = Query(10, ge=3, le=30),
                        terminal_growth: Optional[float] = Query(None, ge=-0.05, le=0.15), target_margin: Optional[float] = Query(None, ge=-1.0, le=0.9),
                        sales_to_capital: Optional[float] = Query(None, gt=0, le=20), ronic: Optional[float] = Query(None, gt=0, le=2.0),
                        discount: Optional[float] = Query(None, gt=0, lt=0.4), beta: Optional[float] = Query(None, ge=-1, le=5),
                        erp: Optional[float] = Query(None, ge=0, le=0.15), include_leases: bool = False, mid_year: bool = True):
    """The FCFF model as an Excel workbook with live formulas (edit the inputs in Excel)."""
    from fastapi.responses import Response
    from api.marketdata import dcf, dcf_excel
    inp = await _run(dcf.inputs, symbol, timeout=60)
    if inp.get("is_financial"):
        raise HTTPException(404, "Excel export covers the FCFF model; banks and insurers use the excess-return model on screen.")
    val = await _run(dcf.value, inp, growth=growth, years=years, terminal_growth=terminal_growth, target_margin=target_margin,
                     sales_to_capital=sales_to_capital, ronic=ronic, discount=discount, beta=beta, erp=erp,
                     include_leases=include_leases, mid_year=mid_year)
    data, _ = await asyncio.to_thread(dcf_excel.build, inp, val)
    name = f"DCF_{inp['symbol'].replace('^', '').replace('=', '')}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── Global monitors ──────────────────────────────────────────────────────────
@router.get("/api/v1/mkt/seas/{symbol}")
async def mkt_seasonality(symbol: str, years: int = Query(15, ge=3, le=40)):
    from api.marketdata import analytics
    return await _run(analytics.seasonality, symbol, years)


@router.get("/api/v1/mkt/corr")
async def mkt_correlation(symbols: str, period: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y|10y)$"),
                          freq: str = Query("daily", pattern="^(daily|weekly)$")):
    from api.marketdata import analytics
    return await _run(analytics.correlation, symbols.split(","), period, freq, timeout=90)


@router.get("/api/v1/mkt/rrg")
async def mkt_rrg(universe: str = "us_sectors", tail: int = Query(8, ge=2, le=26), benchmark: Optional[str] = None):
    from api.marketdata import analytics
    return await _run(analytics.rrg, universe, tail, benchmark, timeout=90)


@router.get("/api/v1/mkt/frd")
async def mkt_fx_forwards(base: str = Query("EUR", pattern="^[A-Za-z]{3}$"), quote: str = Query("USD", pattern="^[A-Za-z]{3}$")):
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


@router.get("/api/v1/mkt/fly")
async def mkt_flights(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), radius_nm: int = Query(100, ge=5, le=250)):
    """Live aircraft around a point (adsb.lol)."""
    from api.marketdata import tracking
    return await _run(tracking.flights, lat, lon, radius_nm)


@router.get("/api/v1/mkt/fly/airports")
async def mkt_airports():
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
    from api.marketdata import extras
    return await _run(extras.auctions, kind, limit)


@router.get("/api/v1/mkt/eia")
async def mkt_eia():
    from api.marketdata import extras
    return await _run(extras.energy)


@router.get("/api/v1/mkt/eia/history")
async def mkt_eia_history(weeks: int = Query(520, ge=52, le=1040)):
    from api.marketdata import extras
    return await _run(extras.eia_history, weeks, timeout=90)


@router.get("/api/v1/mkt/ipo")
async def mkt_ipo():
    from api.marketdata import extras
    return await _run(extras.ipo_calendar)


@router.get("/api/v1/mkt/wetr")
async def mkt_weather():
    from api.marketdata import extras
    return await _run(extras.weather, timeout=90)


@router.get("/api/v1/mkt/insd/{symbol}")
async def mkt_insiders(symbol: str, limit: int = Query(40, ge=5, le=100)):
    from api.marketdata import extras
    return await _run(extras.insiders, symbol, limit, timeout=120)


@router.get("/api/v1/mkt/13f")
async def mkt_13f(cik: str = Query("0001067983", pattern=r"^\d{1,10}$")):
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
    rec["market"] = c.lower() if c.lower() in __import__("api.marketdata.core", fromlist=["REGIONS"]).REGIONS else None
    rec["fx_symbol"] = None if rec.get("currency") == "USD" else f"{rec.get('currency')}=X"
    rec["region_name"] = C.REGION_NAMES.get(rec.get("region") or C.region_of(c))
    return rec


@router.get("/api/v1/mkt/wcrs")
async def mkt_fx_matrix(ccys: Optional[str] = None):
    from api.marketdata import monitors
    return await _run(monitors.fx_matrix, ccys.upper().split(",") if ccys else None)


@router.get("/api/v1/mkt/btmm")
async def mkt_money_markets():
    from api.marketdata import monitors
    return await _run(monitors.money_markets, timeout=90)


@router.get("/api/v1/mkt/imap")
async def mkt_heatmap(country: str = Query("US", min_length=2, max_length=2), max_names: int = Query(300, ge=20, le=500)):
    from api.marketdata import monitors
    return await _run(monitors.heatmap, country, max_names, timeout=90)


@router.get("/api/v1/mkt/crypto")
async def mkt_crypto(limit: int = Query(100, ge=10, le=250)):
    from api.marketdata import monitors
    return await _run(monitors.crypto, limit)


@router.get("/api/v1/mkt/futures/{root}")
async def mkt_futures_curve(root: str, n: int = Query(10, ge=3, le=24)):
    from api.marketdata import monitors
    return await _run(monitors.futures_curve, root, n)


@router.get("/api/v1/mkt/futures")
async def mkt_futures_roots():
    from api.marketdata import monitors
    return {"roots": [{"root": k, "name": v[0], "exchange": v[1]} for k, v in monitors.FUTURES.items()]}


@router.get("/api/v1/mkt/news")
async def mkt_news_hub(q: Optional[str] = Query(None, max_length=60), limit: int = Query(60, ge=10, le=200),
                       region: Optional[str] = Query(None, pattern="^(global|americas|europe|mea|apac)$"),
                       country: Optional[str] = Query(None, pattern="^[A-Za-z]{2}$")):
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
    name: Optional[str] = None
    symbols: Optional[List[str]] = None


class AlertIn(BaseModel):
    symbol: str
    kind: str
    value: float
    note: Optional[str] = None


class JournalIn(BaseModel):
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


@router.get("/api/v1/mkt/quotes")
async def mkt_quotes(symbols: str = Query(..., min_length=1)):
    from api.marketdata import usertools
    try:
        return {"quotes": await asyncio.to_thread(usertools.quotes, symbols.split(","))}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/mkt/watchlists")
async def mkt_watchlists(request: Request):
    from api.marketdata import usertools
    return {"watchlists": await _user_op(usertools.list_watchlists, _owner(request))}


@router.post("/api/v1/mkt/watchlists")
async def mkt_watchlist_create(body: WatchlistIn, request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.create_watchlist, _owner(request), body.name or "Watchlist", body.symbols or [])


@router.put("/api/v1/mkt/watchlists/{wid}")
async def mkt_watchlist_update(wid: int, body: WatchlistIn, request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.update_watchlist, _owner(request), wid, body.name, body.symbols)


@router.delete("/api/v1/mkt/watchlists/{wid}")
async def mkt_watchlist_delete(wid: int, request: Request):
    from api.marketdata import usertools
    await _user_op(usertools.delete_watchlist, _owner(request), wid)
    return {"deleted": wid}


@router.get("/api/v1/mkt/alerts")
async def mkt_alerts(request: Request):
    from api.marketdata import usertools
    return {"alerts": await _user_op(usertools.list_alerts, _owner(request)), "kinds": usertools.ALERT_KINDS}


@router.get("/api/v1/mkt/alerts/triggered")
async def mkt_alerts_triggered(request: Request):
    from api.marketdata import usertools
    return {"alerts": await _user_op(usertools.triggered_unseen, _owner(request))}


@router.post("/api/v1/mkt/alerts")
async def mkt_alert_create(body: AlertIn, request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.create_alert, _owner(request), body.symbol, body.kind, body.value, body.note)


@router.post("/api/v1/mkt/alerts/seen")
async def mkt_alerts_seen(request: Request):
    from api.marketdata import usertools
    return {"marked": await _user_op(usertools.mark_seen, _owner(request))}


@router.post("/api/v1/mkt/alerts/check")
async def mkt_alerts_check(request: Request):
    from api.marketdata import usertools
    _owner(request)
    try:
        return await asyncio.to_thread(usertools.check_alerts)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.delete("/api/v1/mkt/alerts/{aid}")
async def mkt_alert_delete(aid: int, request: Request):
    from api.marketdata import usertools
    await _user_op(usertools.delete_alert, _owner(request), aid)
    return {"deleted": aid}


@router.get("/api/v1/mkt/journal")
async def mkt_journal(request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.list_journal, _owner(request))


@router.post("/api/v1/mkt/journal")
async def mkt_journal_create(body: JournalIn, request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.create_journal, _owner(request), body.model_dump(exclude_none=True))


@router.put("/api/v1/mkt/journal/{jid}")
async def mkt_journal_update(jid: int, body: JournalIn, request: Request):
    from api.marketdata import usertools
    return await _user_op(usertools.update_journal, _owner(request), jid, body.model_dump(exclude_unset=True))


@router.delete("/api/v1/mkt/journal/{jid}")
async def mkt_journal_delete(jid: int, request: Request):
    from api.marketdata import usertools
    await _user_op(usertools.delete_journal, _owner(request), jid)
    return {"deleted": jid}


@router.get("/api/v1/mkt/map")
async def mkt_world_map():
    from api.marketdata import monitors
    return await _run(monitors.world_map_markets, timeout=90)
