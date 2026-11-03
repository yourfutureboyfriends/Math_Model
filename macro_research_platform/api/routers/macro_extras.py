"""Macro extras: Fed watch (FOMC statement redline, dissents, tone) and FINRA margin debt."""
import asyncio

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/v1/mkt/fedwatch")
async def fed_watch():
    """What changed in the latest FOMC statement versus the previous one, dissents, and a lexicon tone score for recent
    statements and speeches (federalreserve.gov)."""
    from api.marketdata import fedwatch
    from api.marketdata.core import Upstream
    try:
        return await asyncio.to_thread(fedwatch.fedwatch)
    except Upstream as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/mkt/margin-debt")
async def margin_debt():
    """FINRA customer margin debt and free credit balances, monthly since 1997, with year-on-year growth."""
    from api.marketdata import freedata
    from api.marketdata.core import Upstream
    try:
        return await asyncio.to_thread(freedata.margin_debt)
    except Upstream as e:
        raise HTTPException(503, str(e))
