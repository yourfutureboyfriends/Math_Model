"""Free official data sources: SEC EDGAR fundamentals, ALFRED vintages (point-in-time
macro), DBnomics (90+ statistics agencies and central banks) and the Fama–French factor
library. All read-only."""
import asyncio

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["data-sources"])


@router.get("/api/v1/fundamentals/{ticker}")
async def fundamentals(ticker: str, years: int = Query(10, ge=1, le=20), quarters: int = Query(12, ge=4, le=40)):
    from api.providers import sec_edgar
    try:
        return await asyncio.wait_for(asyncio.to_thread(sec_edgar.statements, ticker, years, quarters), timeout=60)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except sec_edgar.EdgarError as e:
        raise HTTPException(503, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, "SEC EDGAR is slow to respond — try again.")


@router.get("/api/v1/alfred/revisions/{series}")
async def alfred_revisions(series: str, start: str = "2000-01-01", transform: str = Query("level", pattern="^(level|pct)$")):
    from api.providers import alfred
    try:
        return await asyncio.to_thread(alfred.revisions, series.upper(), start, transform)
    except alfred.AlfredError as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/alfred/as-of/{series}")
async def alfred_as_of(series: str, date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), start: str = "1990-01-01"):
    from api.providers import alfred
    try:
        return {"series": series.upper(), "vintage": date,
                "observations": await asyncio.to_thread(alfred.as_of, series.upper(), date, start)}
    except alfred.AlfredError as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/dbnomics/series")
async def dbnomics_series(code: str):
    from api.providers import dbnomics
    try:
        return await asyncio.to_thread(dbnomics.series, code)
    except dbnomics.DBnomicsError as e:
        raise HTTPException(404, str(e))


@router.get("/api/v1/dbnomics/search")
async def dbnomics_search(q: str = Query(..., min_length=2), limit: int = Query(20, ge=1, le=50)):
    from api.providers import dbnomics
    try:
        return {"results": await asyncio.to_thread(dbnomics.search, q, limit)}
    except Exception as e:
        raise HTTPException(503, f"DBnomics search failed: {e}")


@router.get("/api/v1/factors")
async def factor_returns():
    """Recent and long-run performance of the Fama–French factors (annualised)."""
    from api.providers import factor_library as fl
    try:
        f = await asyncio.to_thread(fl.factors)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    out = []
    for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]:
        s = f[c].dropna()
        row = {"factor": c, "name": fl.NAMES[c]}
        for label, days in (("1y", 252), ("5y", 1260), ("since_1963", len(s))):
            x = s.iloc[-days:]
            row[label] = round(float((1 + x).prod() ** (252 / len(x)) - 1), 4) if len(x) > 20 else None
        out.append(row)
    return {"factors": out, "as_of": f.index[-1].strftime("%Y-%m-%d"), "source": "Kenneth R. French Data Library (CRSP)"}
