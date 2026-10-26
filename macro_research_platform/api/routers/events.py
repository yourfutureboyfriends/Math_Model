"""Macro event dataset API (api/event_dataset.py): point-in-time releases, surprise proxies and market reactions."""
from __future__ import annotations

import asyncio
import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["research"])


async def _ds(refresh: bool = False):
    from api import event_dataset as ed
    try:
        return await asyncio.wait_for(asyncio.to_thread(ed.dataset, refresh), timeout=240)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Building the event dataset took too long — try again.")


@router.get("/api/v1/research/events")
async def events(event: Optional[str] = Query(None, pattern=r"^[a-z_]{2,30}$"), start: Optional[str] = None,
                 limit: int = Query(500, ge=1, le=5000)):
    d = await _ds()
    rows = [e for e in d["events"] if (not event or e["event"] == event) and (not start or e["date"] >= start)]
    return {k: d[k] for k in ("version", "hash", "built_at", "start", "errors", "event_types", "assets", "method")} | {
        "events": rows[-limit:], "count": len(rows)}


@router.get("/api/v1/research/events/summary")
async def events_summary(event: str = Query("us_cpi", pattern=r"^[a-z_]{2,30}$"), horizon: str = Query("h0", pattern="^h[05]$")):
    from api import event_dataset as ed
    d = await _ds()
    if event not in d["event_types"]:
        raise HTTPException(400, f"event must be one of {', '.join(d['event_types'])}")
    return {**ed.summary(d, event, horizon), "hash": d["hash"], "version": d["version"]}


@router.post("/api/v1/research/events/rebuild")
async def events_rebuild(request: Request):
    from api.core.access import require_roles
    require_roles(request, {"pm", "analyst", "quant", "risk"})
    d = await _ds(refresh=True)
    return {"hash": d["hash"], "events": len(d["events"]), "errors": d["errors"], "built_at": d["built_at"]}


@router.get("/api/v1/research/events.csv")
async def events_csv(event: Optional[str] = Query(None, pattern=r"^[a-z_]{2,30}$")):
    """Flat CSV (one row per event) with the dataset hash in the first line, for reproducible research."""
    d = await _ds()
    assets = list(d["assets"])
    buf = io.StringIO()
    buf.write(f"# macro event dataset {d['version']} hash {d['hash']} built {d['built_at']}\n")
    w = csv.writer(buf)
    w.writerow(["event", "date", "time_et", "period", "actual", "prior", "expectation_proxy", "surprise", "surprise_z"]
               + [f"{a}_{h}" for a in assets for h in ("h0", "h5")])
    for e in d["events"]:
        if event and e["event"] != event:
            continue
        w.writerow([e[k] for k in ("event", "date", "time_et", "period", "actual", "prior", "expectation_proxy", "surprise",
                                   "surprise_z")] + [e["reactions"].get(a, {}).get(h) for a in assets for h in ("h0", "h5")])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=macro_events_{d['hash']}.csv"})
