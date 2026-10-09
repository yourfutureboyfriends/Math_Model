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
