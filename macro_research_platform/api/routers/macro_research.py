"""Authenticated institutional-style macro evidence and research tools."""
import asyncio
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Request,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict,field_validator
from api.routers.workflows import scope,call,VintageComparison,EvidenceURLModel
from api.workflows.evidence import instant,digest
from api.workflows import store
import uuid

router=APIRouter(prefix='/api/v1/workflows/macro',tags=['macro-research'])


class Release(EvidenceURLModel):
    model_config=ConfigDict(extra='forbid')
    country:str=Field(min_length=2,max_length=8,pattern=r'^[A-Z]+$')
    indicator:str=Field(min_length=2,max_length=100)
    reference_period:str=Field(min_length=4,max_length=40)
    units:str=Field(min_length=1,max_length=80)
    transformation:str=Field(min_length=1,max_length=80)
    seasonal_adjustment:str=Field(min_length=1,max_length=80)
    entry_type:Literal['forecast','actual','revision']
    forecast_basis:Literal['analyst','model','consensus']='analyst'
    value:float=Field(allow_inf_nan=False)
    scheduled_at:str=Field(max_length=64)
    published_at:str|None=Field(None,max_length=64)
    source:str=Field(min_length=2,max_length=160)
    source_url:str=Field(max_length=2000)
    contributor_count:int|None=Field(None,ge=1,le=10000)
    dispersion:float|None=Field(None,ge=0,allow_inf_nan=False)
    supersedes:str|None=Field(None,max_length=64)
    linked_symbols:list[str]=Field(default_factory=list,max_length=20)
    @field_validator('linked_symbols')
    @classmethod
    def symbols(cls,values):
        import re
        if any(not re.fullmatch(r'[A-Za-z0-9.^=_-]{1,64}',v) for v in values):raise ValueError('Invalid linked symbol')
        return list(dict.fromkeys(v.upper() for v in values))


@router.post('/releases')
async def release_save(body:Release,request:Request):
    fund,owner=scope(request)
    from api.workflows.macro_releases import add
    return await call(add,fund,owner,body.model_dump())


@router.get('/releases')
async def releases(request:Request,available_at:str|None=Query(None,max_length=64)):
    fund,owner=scope(request)
    from api.workflows.macro_releases import ledger
    return await call(ledger,fund,owner,available_at)


@router.get('/conditions')
async def conditions(request:Request):
    scope(request)
    from api.marketdata.fcig import conditions as load
    from api.marketdata.core import Upstream
    try:return await call(load)
    except Upstream:raise HTTPException(503,'Official Federal Reserve FCI-G is unavailable; no proxy was substituted')


class Uncertainty(BaseModel):
    covariance:list[list[float]]=Field(min_length=1,max_length=20)
    prior_weights:list[float]=Field(min_length=1,max_length=20)
    monthly_views:list[float]=Field(min_length=1,max_length=20)
    risk_aversion:float=Field(2.5,gt=0,le=100)
    tau:float=Field(.05,gt=0,le=5)
    confidence:float=Field(1,gt=0,le=10000)
    monthly_view_error_variances:list[float]|None=Field(None,max_length=20)


@router.post('/uncertainty')
async def uncertainty(body:Uncertainty,request:Request):
    scope(request)
    def evaluate():
        import numpy as np
        from api.model.core import black_litterman
        c=np.array(body.covariance);w=np.array(body.prior_weights);v=np.array(body.monthly_views)
        if c.shape!=(len(v),len(v)) or w.shape!=v.shape:raise ValueError('Covariance, weights and views must have matching dimensions')
        if not np.isfinite(w).all() or not np.isclose(w.sum(),1):raise ValueError('Finite prior weights must sum to one')
        legacy,prior=black_litterman(c,w,v,body.risk_aversion,body.tau,body.confidence)
        legacy2,_=black_litterman(c,w,v,body.risk_aversion,body.tau*2,body.confidence)
        explicit=None
        if body.monthly_view_error_variances is not None:
            explicit,_=black_litterman(c,w,v,body.risk_aversion,body.tau,body.confidence,body.monthly_view_error_variances)
        return {'prior_monthly':prior.tolist(),'default_posterior_monthly':legacy.tolist(),'doubled_tau_posterior_monthly':legacy2.tolist(),
                'maximum_tau_difference':float(np.max(abs(legacy-legacy2))),
                'independent_variance_posterior_monthly':explicit.tolist() if explicit is not None else None,
                'note':'Default view uncertainty scales with tau, so tau cancels from posterior means. Independent supplied view-error variances define a different research convention and must be estimated on training data in monthly-return-squared units. This tool does not change live model settings or certify the variances.'}
    try:return await call(evaluate)
    except Exception as e:
        import numpy as np
        if isinstance(e,np.linalg.LinAlgError):raise HTTPException(422,'Covariance must be positive definite')
        raise


_lab_lock=asyncio.Lock()


async def begin_experiment(fund,owner,kind,specification,code_hash):
    rid='macro-exp:'+str(uuid.uuid4())
    payload={'id':rid,'kind':'macro_experiment','experiment':kind,'status':'running','specification':specification,
             'code_hash':code_hash,'started_at':store.now(),'note':'Recorded before this run; does not establish an untouched holdout or recover earlier unregistered searches.'}
    await call(store.put,fund,owner,rid,'reconciliation',payload,0)
    return payload


async def end_experiment(fund,owner,payload,status,result=None):
    value={**payload,'status':status,'finished_at':store.now(),'result_sha256':digest(result) if result is not None else None}
    return await call(store.put,fund,owner,payload['id'],'reconciliation',value,1)


@router.post('/challengers')
async def challengers(body:VintageComparison,request:Request):
    fund,owner=scope(request)
    if _lab_lock.locked():raise HTTPException(409,'A challenger comparison is already running')
    from api.model.research import compare_vintages
    from api.model import challengers as lab
    from api.quant.store import register_code_run
    from pathlib import Path
    import hashlib
    async with _lab_lock:
        code_hash=hashlib.sha256(Path(lab.__file__).read_bytes()).hexdigest()
        pending=await begin_experiment(fund,owner,'US macro challengers',body.model_dump(),code_hash)
        try:result=await compare_vintages(body.start,body.end,research_challengers=True)
        except BaseException as e:
            await asyncio.shield(end_experiment(fund,owner,pending,'failed'))
            if isinstance(e,(ValueError,TypeError)):raise HTTPException(422,str(e))
            raise
        research=result.get('vintage',{}).get('research_challengers') or {}
        await end_experiment(fund,owner,pending,'completed' if research else 'unavailable',result)
        data_hash=digest({'macro_vintages':result.get('vintages',[]),'returns_input_sha256':result.get('returns_input_sha256')})
        for name in ('economic','return_momentum','combined','joint_regime'):
            metrics=(research.get('sleeves') or {}).get(name,{})
            await call(register_code_run,owner,'Macro challenger / '+name,{'code_hash':code_hash,'data_hash':data_hash,
                'engine_version':lab.VERSION,'record_type':'macro_challenger' if research else 'unavailable',
                'params':{'start':body.start,'end':body.end,'sleeve':name,'specification':research.get('specification')},
                'data_first':body.start,'data_last':body.end,'holdout':body.start,'fund':fund,
                'universe':list((research.get('monthly') or [{}])[0].get('economic',{}).get('weights',{})),
                'availability':research.get('available',False)},metrics)
        return {**result,'registered_research':True,'experiment_record_id':pending['id'],
                'note':result.get('note','')+' Run specification was recorded before evaluation in account/fund research history. Completed attempts also enter the account-wide quant registry; selection after viewing results is not an untouched holdout.'}


class BridgeRow(BaseModel):
    period:str=Field(min_length=4,max_length=40)
    forecast_at:str=Field(max_length=64)
    features_available_at:str=Field(max_length=64)
    features:dict[str,float|None]=Field(min_length=1,max_length=20)
    target:float|None=Field(None,allow_inf_nan=False)
    target_available_at:str|None=Field(None,max_length=64)
    @field_validator('features')
    @classmethod
    def finite_features(cls,v):
        import math
        if any(len(k)>80 or x is not None and not math.isfinite(x) for k,x in v.items()):raise ValueError('Finite indicator features required')
        return v


class BridgeInput(EvidenceURLModel):
    target_name:str=Field(min_length=3,max_length=100)
    units:str=Field(min_length=1,max_length=80)
    source_url:str=Field(max_length=2000)
    rows:list[BridgeRow]=Field(min_length=1,max_length=500)


@router.post('/bridge')
async def bridge(body:BridgeInput,request:Request):
    fund,owner=scope(request)
    from api.model.bridge import evaluate
    rows=[]
    for r in body.model_dump()['rows']:
        for key in ('forecast_at','features_available_at','target_available_at'):
            if r[key]:r[key]=await call(instant,r[key])
        if datetime.fromisoformat(r['forecast_at'])>datetime.fromisoformat(store.now()):raise HTTPException(422,'Forecast origin cannot be in the future')
        if r.get('target') is not None and r.get('target_available_at') and datetime.fromisoformat(r['target_available_at'])>datetime.fromisoformat(store.now()):raise HTTPException(422,'Provided outcomes must already be observed')
        rows.append(r)
    from pathlib import Path
    import hashlib
    import api.model.bridge as engine
    code_hash=hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()
    pending=await begin_experiment(fund,owner,'Target bridge',{'target':body.target_name,'units':body.units,'input_sha256':digest(rows),'source_url':body.source_url},code_hash)
    try:result=await call(evaluate,rows)
    except BaseException:
        await asyncio.shield(end_experiment(fund,owner,pending,'failed'));raise
    await end_experiment(fund,owner,pending,'completed' if result['available'] else 'unavailable',result)
    from api.quant.store import register_code_run
    ordered=sorted(rows,key=lambda r:r['forecast_at'])
    await call(register_code_run,owner,'Macro bridge / '+body.target_name,{'code_hash':code_hash,'data_hash':digest(rows),'engine_version':'bridge-v1',
        'record_type':'bridge_challenger','params':{'units':body.units,'alpha':10},'data_first':ordered[0]['forecast_at'],'data_last':ordered[-1]['forecast_at'],
        'holdout':result['forecasts'][0]['forecast_at'] if result['forecasts'] else None,
        'universe':list(ordered[0]['features'])},{})
    return {**result,'target_name':body.target_name,'units':body.units,'source_url':body.source_url,'registered_research':True,'experiment_record_id':pending['id']}


class Strategic(BaseModel):
    asset_type:Literal['equity','bond']
    horizon_years:int=Field(10,ge=3,le=30)
    base_currency:str=Field(min_length=3,max_length=8)
    inflation:float=Field(ge=-.5,le=.5)
    annual_fx_return:float=Field(0,ge=-.9,le=1)
    hedged:bool=False
    annual_hedging_cost:float=Field(0,ge=-.5,le=.5)
    annual_fee:float=Field(0,ge=0,le=.5)
    dividend_yield:float|None=Field(None,ge=0,le=.5)
    eps_growth:float|None=Field(None,ge=-.9,le=1)
    starting_pe:float|None=Field(None,gt=0,le=1000)
    ending_pe:float|None=Field(None,gt=0,le=1000)
    yield_carry:float|None=Field(None,ge=-.2,le=1)
    roll_return:float|None=Field(None,ge=-.5,le=.5)
    annual_yield_change:float|None=Field(None,ge=-.2,le=.2)
    duration:float|None=Field(None,ge=0,le=100)
    convexity:float|None=Field(None,ge=0,le=10000)
    annual_credit_loss:float|None=Field(None,ge=0,le=1)


@router.post('/strategic')
async def strategic(body:Strategic,request:Request):
    scope(request)
    from api.workflows.strategic import assumptions
    return await call(assumptions,body.model_dump())


class MacroView(EvidenceURLModel):
    id:str=Field(min_length=1,max_length=128)
    expected_version:int=Field(0,ge=0)
    horizon:Literal['structural','cyclical','release','tactical']
    title:str=Field(min_length=5,max_length=200)
    thesis:str=Field(min_length=10,max_length=5000)
    invalidation:str=Field(min_length=10,max_length=2000)
    review_at:str=Field(max_length=64)
    source_url:str=Field(max_length=2000)
    quantitative_baseline:str=Field(min_length=3,max_length=2000)
    override_rationale:str|None=Field(None,max_length=2000)


@router.post('/views')
async def view_save(body:MacroView,request:Request):
    fund,owner=scope(request)
    raw=body.model_dump();version=raw.pop('expected_version');raw['review_at']=await call(instant,raw['review_at'])
    return await call(store.put,fund,owner,body.id,'thesis',{'id':body.id,'kind':'macro_view',**raw},version)


@router.get('/views')
async def views(request:Request):
    fund,owner=scope(request)
    return {'views':[{'version':r['version'],**r['payload']} for r in await call(store.records,fund,owner) if r['kind']=='thesis' and r['payload'].get('kind')=='macro_view']}


class AllocationScenario(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    probability:float=Field(ge=0,le=1)
    annual_returns:list[float]=Field(min_length=1,max_length=20)
    cash_return:float=Field(ge=-.2,le=.5)
    @field_validator('annual_returns')
    @classmethod
    def finite_returns(cls,v):
        import math
        if any(not math.isfinite(x) or not -.99<=x<=2 for x in v):raise ValueError('Annual scenario returns must be finite and between -99% and 200%')
        return v


class Allocation(BaseModel):
    base_currency:str=Field(min_length=3,max_length=8)
    horizon_years:int=Field(ge=1,le=30)
    assets:list[str]=Field(min_length=1,max_length=20)
    covariance:list[list[float]]=Field(min_length=1,max_length=20)
    scenarios:list[AllocationScenario]=Field(min_length=2,max_length=12)
    baseline:list[float]=Field(min_length=1,max_length=20)
    max_weight:float=Field(.6,gt=0,le=1)
    volatility_ceiling:float=Field(.1,gt=0,le=1)
    risk_aversion:float=Field(2.5,ge=0,le=100)
    turnover_penalty:float=Field(.001,ge=0,le=.1)
    @field_validator('scenarios')
    @classmethod
    def distinct_names(cls,v):
        if len({s.name for s in v})!=len(v):raise ValueError('Scenario names must be unique')
        return v


@router.post('/allocation')
async def allocation(body:Allocation,request:Request):
    scope(request)
    from api.model.scenario_allocation import compare
    raw=body.model_dump();currency=raw.pop('base_currency');horizon=raw.pop('horizon_years')
    return {**await call(compare,**raw),'base_currency':currency,'horizon_years':horizon,
            'horizon_basis':'Annualized assumptions over the stated horizon, not an explicit multi-year path simulation'}
