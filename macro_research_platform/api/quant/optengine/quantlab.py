from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
from collections import deque
import pandas as pd
from .config import EngineConfig
from .engine import DecisionEngine
from .execution import PaperBook
from .features import FeaturePanel
from .providers import HistoricalProvider,Snapshot
from .schema import AssignmentEvent,Quote,Spot,DataError,utc

def provider_from_payload(raw,config):
    history=raw["history"]
    index=pd.DatetimeIndex([utc(x) for x in history["available_at"]])
    columns=history["symbols"]
    close=pd.DataFrame(history["close"],index=index,columns=columns,dtype=float)
    volume=pd.DataFrame(history["volume"],index=index,columns=columns,dtype=float)
    observed=pd.DataFrame(history["observed"],index=index,columns=columns,dtype=bool) if "observed" in history else None
    panel=FeaturePanel(close,volume,history.get("metadata"),observed,history.get("market","SPY"))
    snapshots={};chains={};settlements={}
    for entry in raw["snapshots"]:
        body=dict(entry["snapshot"]);body["spots"]={u:Spot(**s) for u,s in body["spots"].items()};body["assignments"]=tuple(AssignmentEvent(**e) for e in body.get("assignments",[]))
        snap=Snapshot(**body).validate()
        if snap.asof in snapshots:raise DataError("Duplicate snapshot clock")
        snapshots[snap.asof]=snap
        chains[snap.asof]=entry.get("chains",{})
        settlements[snap.asof]={(e["underlying"],e["expiry"]):e for e in entry.get("settlements",[])}
    def loader(u,asof):return chains.get(asof,{}).get(u,[])
    def availability(u,asof):
        raw=chains.get(asof,{}).get(u,[])
        valid=[q for q in raw if utc(q["available_at"])<=utc(asof) and utc(q["quoted_at"])<=utc(asof) and min(s.min_dte for s in config.strategies.values())<=Quote(**q).dte(asof)<=max(s.max_dte for s in config.strategies.values())]
        return {"available_at":asof,"available":bool(valid)}
    provider=HistoricalProvider(panel,loader,snapshots,config.data.max_chain_cache,availability,history.get("universe","GLOBAL"))
    return provider,settlements

def replay(config,provider,dates,capital=1_000_000,approval=None,mode="research",settlements=None,cancel=None,event_sink=None,event_limit=1000):
    from api.quant import codelab
    book=PaperBook(capital,config.config_id,mode)
    engine=DecisionEngine(config,provider,approval)
    if isinstance(event_limit,bool) or not isinstance(event_limit,int) or not 0<=event_limit<=10000:raise DataError("Invalid replay event limit")
    records=[];events=deque(maxlen=event_limit);previous=capital;event_count=0;chain_sources=set()
    ordered=list(dates)
    if ordered!=sorted(ordered,key=utc) or len(set(ordered))!=len(ordered):raise DataError("Replay dates must be ordered and unique")
    for asof in ordered:
        if cancel is not None and cancel.is_set():raise DataError("Replay cancelled")
        result=engine.tick(book,asof,(settlements or {}).get(asof,{}))
        events.extend({"asof":asof,**e} for e in result["events"])
        event_count+=len(result["events"])
        chain_sources.update(q.source for qs in provider.cache.values() for q in qs)
        if event_sink is not None:event_sink(asof,book.to_dict(),result["events"])
        if result["nav"] is None:
            records.append({"asof":asof,"nav":None,"return":None,"status":result["status"]})
            continue
        nav=result["nav"]
        records.append({"asof":asof,"nav":nav,"return":nav/previous-1,"status":result["status"]})
        previous=nav
    frame=pd.DataFrame(records)
    metrics=None
    if len(frame) and frame["return"].notna().all():
        returns=pd.Series(frame["return"].to_numpy(),index=pd.DatetimeIndex([utc(x) for x in frame["asof"]]))
        rf=pd.Series([provider.snapshot(x).annual_cash_rate/252 if provider.snapshot(x).annual_cash_rate is not None else 0 for x in frame["asof"]],index=returns.index)
        metrics=codelab.metrics(returns,rf)
    return {"mode":mode,"config_id":config.config_id,"metrics":metrics,"dates":frame["asof"].tolist(),"returns":[None if pd.isna(v) else float(v) for v in frame["return"]],
            "record":records,"events":list(events),"audit":{"event_count":event_count,"returned_events":len(events),"complete":event_count<=len(events),"persisted":event_sink is not None},"book":book.to_dict(),"provenance":{"underlying_universe":len(provider.universe),"chain_requests":len(provider.chain_requests),
              "forecast":asdict(config.forecast),"no_optimization":True,"chain_sources":sorted(chain_sources),
              "cash_rates_known":all(provider.snapshot(x).annual_cash_rate is not None for x in dates),"assignment":"explicit events and expiry instructions; no inferred actual assignment probability",
              "execution":"next-snapshot atomic paper fills at quoted bid/ask plus configured costs","profitability_validated":False}}

def config_export(config):
    return {"schema":"optengine.quantlab.v1","config_id":config.config_id,"config":config.to_dict(),"status":"research","scope":"paper_only"}

def import_export(raw):
    if raw.get("schema")!="optengine.quantlab.v1":raise DataError("Unsupported Quant Lab export schema")
    config=EngineConfig.from_dict(raw["config"])
    if raw.get("config_id")!=config.config_id or raw.get("status")!="research":raise DataError("Export hash/status mismatch; approval must come from registry")
    return config
