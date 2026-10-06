"""Strategy Lab endpoints: research-backed systematic models, their combination, and
today's positions (api/strategy_lab.py)."""
import asyncio

from fastapi import APIRouter, Request

router = APIRouter(tags=["strategies"])
_BG: set = set()


def _spawn(coro) -> None:
    t = asyncio.get_running_loop().create_task(coro)
    _BG.add(t)
    t.add_done_callback(_BG.discard)


@router.get("/api/v1/strategies")
async def strategies():
    from api import strategy_lab as sl
    cur = await asyncio.to_thread(sl.latest)
    if not cur:
        if not sl.status()["running"]:
            _spawn(sl.run_in_background())
        return {"available": False, "status": sl.status(),
                "reason": "Running the Strategy Lab for the first time (about two minutes)."}
    return {**cur, "status": sl.status()}


@router.post("/api/v1/strategies/run")
async def strategies_run(request: Request):
    from api import strategy_lab as sl
    from api.core.access import require_roles
    require_roles(request, {"pm", "quant"})
    if not sl.status()["running"]:
        _spawn(sl.run_in_background())
    return {"started": True, "status": sl.status()}
