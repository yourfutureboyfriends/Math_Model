"""Portfolio analytics on the actual book: Brinson attribution, tracking error, liquidity-adjusted VaR, lots, TCA,
trade-idea P&L (api/handlers/portfolio_analytics.py)."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Query

from api.utils.cache import ttl_cache

router = APIRouter()


async def _run(fn, *a, timeout: float = 120):
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a), timeout=timeout)
    except asyncio.TimeoutError:
        return {"available": False, "reason": "Timed out fetching prices — try again."}
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/api/v1/portfolio/analytics/brinson")
@ttl_cache(900)
async def pa_brinson(book: Optional[str] = None,
                     benchmark: Optional[str] = Query(None, pattern=r"^[A-Za-z0-9^._\-]{1,12}$"),
                     days: int = Query(252, ge=5, le=756)):
    """Brinson–Fachler attribution on the holdings actually held, Carino-linked. Default: the fund's own benchmark
    — a composite (BIFS, MSCI World) in the fund's base currency; SPY or another ticker: S&P sector ETFs, local."""
    from api import fund_store
    from api.calculations.benchmark import BENCHMARKS
    from api.handlers import portfolio_analytics as h
    code = (benchmark or (await asyncio.to_thread(fund_store.get_settings)).get("benchmark") or "SPY").upper()
    if code in BENCHMARKS and BENCHMARKS[code].get("attribution") is False:
        return {"available": False, "reason": f"Sector attribution does not apply to the fund's benchmark "
                                              f"({BENCHMARKS[code]['label']}): see attribution by sleeve, instrument "
                                              f"and regime in the monthly reporting pack (Fund Governance)."}
    if code in BENCHMARKS and code != "SPY":
        return await _run(h.brinson_base, book, code, days, timeout=180)
    return await _run(h.brinson, book, code, days)


@router.get("/api/v1/portfolio/analytics/tracking-error")
@ttl_cache(900)
async def pa_tracking_error(book: Optional[str] = None,
                            benchmark: Optional[str] = Query(None, pattern=r"^[A-Za-z0-9^._\-]{1,12}$")):
    """Ex-ante tracking error and beta versus the benchmark (default: the fund's own — e.g. BIFS, 50% MSCI World +
    50% MSCI World Equal Weighted in GBP), in the fund's base currency, with each active weight's contribution."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.tracking_error, book, benchmark)


@router.get("/api/v1/portfolio/analytics/liquidity")
@ttl_cache(900)
async def pa_liquidity(book: Optional[str] = None, participation: float = Query(0.20, gt=0, le=1)):
    """Days to liquidate and the liquidity cost added to VaR."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.liquidity, book, participation)


@router.get("/api/v1/portfolio/lots")
async def pa_lots(book: Optional[str] = None):
    """Open FIFO tax lots per position."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.lots, book)


@router.get("/api/v1/portfolio/tca")
@ttl_cache(900)
async def pa_tca(limit: int = Query(200, ge=1, le=1000)):
    """Transaction-cost analysis of the fund's and paper traders' fills."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.tca, limit)


@router.get("/api/v1/portfolio/ideas/performance")
@ttl_cache(900)
async def pa_ideas():
    """Mark-to-market of every trade idea since it was proposed."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.idea_tracking)


@router.get("/api/v1/portfolio/news")
@ttl_cache(900)
async def pa_news(book: Optional[str] = None):
    """Headlines and filings tagged to each holding, with tone versus the position."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.holding_news, book)


@router.get("/api/v1/portfolio/sector-exposure")
@ttl_cache(600)
async def pa_sector_exposure(book: Optional[str] = None):
    """The book's net sector exposure (look-through), to set beside the regime sector allocation."""
    from api.handlers import portfolio_analytics as h
    return await _run(h.sector_exposure, book)


@router.get("/api/v1/fund/benchmark")
@ttl_cache(1800)
async def fund_benchmark(code: Optional[str] = Query(None, pattern=r"^[A-Za-z_]{2,12}$")):
    """The fund's benchmark in its base currency: returns over standard windows, volatility, the proxies used and
    what the series is not (licensed MSCI levels, constituents)."""
    from api import fund_store
    from api.calculations import benchmark as bm
    st = await _run(fund_store.get_settings)
    c = (code or st.get("benchmark") or "SPY").upper()
    if c not in bm.BENCHMARKS:
        return {"available": False, "reason": f"Unknown benchmark {c}. Available: {', '.join(bm.BENCHMARKS)}."}
    return await _run(bm.summary, c, st.get("base_currency") or "USD")
