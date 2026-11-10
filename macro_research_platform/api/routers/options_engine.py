from __future__ import annotations
import asyncio
import threading
from pathlib import Path
from typing import Any
from datetime import datetime,timezone
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel

_replay_sem=asyncio.Semaphore(1)
router=APIRouter(prefix="/api/v1/quant/options-engine",tags=["options-engine"])

class ImportIn(BaseModel):
    export:dict[str,Any]
class ApprovalIn(BaseModel):
    acknowledge:bool=False
    evidence:dict[str,Any]
class RevokeIn(BaseModel):
    reason:str
class BookIn(BaseModel):
    config_id:str
    capital:float=1_000_000
    mode:str="research"
class TickIn(BaseModel):
    data:dict[str,Any]
class ReplayIn(BaseModel):
    config_id:str
    data:dict[str,Any]
    capital:float=1_000_000
    event_limit:int=1000
class StopIn(BaseModel):
    reason:str
    acknowledge:bool=False

def user(request,roles=("quant","analyst","risk","pm")):
    from api.core.access import require_roles
    return require_roles(request,set(roles))
def registry():
    from api.quant.optengine.registry import Registry
    return Registry(Path(__file__).resolve().parents[2]/"data"/"processed"/"quant"/"options_engine.sqlite")
def failure(exc):
    from api.quant.optengine.registry import ConflictError
    if isinstance(exc,ConflictError):raise HTTPException(409,str(exc))
    if isinstance(exc,PermissionError):raise HTTPException(403,str(exc))
    raise HTTPException(400,str(exc))

@router.get("/meta")
async def meta(request:Request):
    user(request)
    from api.quant.optengine.config import EngineConfig,STRATEGIES
    from api.quant.optengine.quantlab import config_export
    return {"strategies":list(STRATEGIES),"defaults":config_export(EngineConfig()),"live_execution":False,"forecast_required":True,"paper_approval_required":True,
            "historical_chains_available_from_free_data":False,"universe":"Uses every underlying supplied by the configured Quant Lab universe; requests shortlisted chains lazily"}

@router.post("/configs")
async def import_config(body:ImportIn,request:Request):
    u=user(request)
    from api.quant.optengine.quantlab import import_export
    try:
        cfg=import_export(body.export)
        return await asyncio.to_thread(registry().import_research,u["username"],cfg.to_dict())
    except (ValueError,TypeError,KeyError) as e:failure(e)

@router.get("/configs/{config_id}")
async def get_config(config_id:str,request:Request):
    u=user(request);row=await asyncio.to_thread(registry().get_config,config_id,u["username"],u["role"]=="admin")
    if not row:raise HTTPException(404,"Unknown owned configuration")
    return row

@router.post("/configs/{config_id}/approve")
async def approve(config_id:str,body:ApprovalIn,request:Request):
    u=user(request,("pm","risk"))
    try:return await asyncio.to_thread(registry().approve,config_id,u,body.evidence,body.acknowledge)
    except (ValueError,PermissionError,RuntimeError) as e:failure(e)

@router.post("/configs/{config_id}/revoke")
async def revoke(config_id:str,body:RevokeIn,request:Request):
    u=user(request,("pm","risk"))
    try:return await asyncio.to_thread(registry().revoke,config_id,u,body.reason)
    except (ValueError,PermissionError) as e:failure(e)

@router.post("/books")
async def create_book(body:BookIn,request:Request):
    u=user(request,("quant","pm","risk"))
    try:return await asyncio.to_thread(registry().create_book,u["username"],body.config_id,body.capital,body.mode)
    except (ValueError,PermissionError) as e:failure(e)

@router.get("/books/{book_id}")
async def get_book(book_id:str,request:Request):
    u=user(request);row=await asyncio.to_thread(registry().get_book,book_id,u["username"],u["role"]=="admin")
    if not row:raise HTTPException(404,"Unknown owned book")
    return row

def run_tick(book_id,owner,raw):
    from api.quant.optengine import EngineConfig,DecisionEngine,PaperBook
    from api.quant.optengine.quantlab import provider_from_payload
    from api.quant.optengine.schema import DataError,utc
    reg=registry();row=reg.get_book(book_id,owner)
    if not row:raise DataError("Unknown owned book")
    config=reg.get_config(row["config_id"],owner)
    cfg=EngineConfig.from_dict(config["config"]);book=PaperBook.from_dict(row["state"])
    provider,settlements=provider_from_payload(raw,cfg)
    if len(raw["snapshots"])!=1:raise DataError("Tick requires exactly one snapshot")
    asof=raw["snapshots"][0]["snapshot"]["asof"]
    if book.mode=="paper" and utc(asof)>datetime.now(timezone.utc):raise DataError("Paper snapshot is in the future; use research replay")
    result=DecisionEngine(cfg,provider,config).tick(book,asof,settlements.get(asof))
    reg.commit_tick(book_id,owner,row["revision"],book.to_dict(),asof,result["events"])
    return result

@router.post("/books/{book_id}/tick")
async def tick(book_id:str,body:TickIn,request:Request):
    u=user(request,("quant","pm","risk"))
    try:return await asyncio.to_thread(run_tick,book_id,u["username"],body.data)
    except (ValueError,PermissionError,RuntimeError,KeyError,TypeError) as e:failure(e)

@router.post("/books/{book_id}/stop")
async def stop(book_id:str,body:StopIn,request:Request):
    u=user(request,("pm","risk"))
    from api.quant.optengine import PaperBook
    if not body.acknowledge or not body.reason:raise HTTPException(400,"A reason and acknowledgement are required")
    reg=registry();row=reg.get_book(book_id,u["username"])
    if not row:raise HTTPException(404,"Unknown owned book")
    book=PaperBook.from_dict(row["state"]);book.emergency_stop(body.reason)
    try:return reg.commit_tick(book_id,u["username"],row["revision"],book.to_dict(),datetime.now(timezone.utc).isoformat(),[{"event":"manual_emergency_stop","reason":body.reason,"actor":u["username"]}])
    except RuntimeError as e:failure(e)

@router.get("/books/{book_id}/events")
async def events(book_id:str,request:Request,after:int=0,limit:int=100):
    u=user(request);out=await asyncio.to_thread(registry().events,book_id,u["username"],after,limit,u["role"]=="admin")
    if out is None:raise HTTPException(404,"Unknown owned book")
    return {"events":out}

@router.post("/backtest")
async def backtest(body:ReplayIn,request:Request):
    u=user(request)
    from api.quant.optengine import EngineConfig
    from api.quant.optengine.quantlab import provider_from_payload,replay
    row=registry().get_config(body.config_id,u["username"])
    if not row:raise HTTPException(404,"Unknown owned research configuration")
    cfg=EngineConfig.from_dict(row["config"])
    cancel=threading.Event()
    def run():
        provider,settlements=provider_from_payload(body.data,cfg)
        dates=[e["snapshot"]["asof"] for e in body.data["snapshots"]]
        reg=registry();book_row=reg.create_book(u["username"],cfg.config_id,body.capital,"research")
        def persist(asof,state,events):
            nonlocal book_row
            book_row=reg.commit_tick(book_row["id"],u["username"],book_row["revision"],state,asof,events)
        result=replay(cfg,provider,dates,body.capital,mode="research",settlements=settlements,cancel=cancel,event_sink=persist,event_limit=body.event_limit)
        result["audit"]["book_id"]=book_row["id"]
        return result
    try:
        async with _replay_sem:return await asyncio.wait_for(asyncio.to_thread(run),timeout=240)
    except asyncio.TimeoutError:
        cancel.set()
        raise HTTPException(504,"Historical replay exceeded time budget; run a local provider job")
    except asyncio.CancelledError:
        cancel.set();raise
    except (ValueError,KeyError,TypeError,PermissionError) as e:failure(e)
