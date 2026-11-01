"""Authenticated connected workflows; tenant scope always comes from verified middleware."""
import asyncio
import re
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict
from api.workflows import store, analytics

router=APIRouter(prefix='/api/v1/workflows',tags=['workflows'])
ROLES={'pm','quant','analyst','risk','trader'}


def scope(request):
    from api.core.access import require_roles
    from api.funds import CURRENT
    return CURRENT.get(),require_roles(request,ROLES)['username']


async def call(fn,*args,**kw):
    try:return await asyncio.to_thread(fn,*args,**kw)
    except store.Conflict as e:raise HTTPException(409,str(e))
    except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e))


class Record(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['observation','thesis','reconciliation']
    payload:dict[str,Any]
    expected_version:int=Field(0,ge=0)


@router.get('/research')
async def research(request:Request):
    fund,owner=scope(request)
    rows,config,events=await asyncio.gather(call(store.records,fund,owner),call(store.monitor,fund,owner),call(store.events,fund,owner))
    return {'records':rows,'monitor':config,'events':events,'storage':'server','fund':fund,'owner':owner}


@router.put('/research/{rid}')
async def put_record(rid:str,body:Record,request:Request):
    fund,owner=scope(request)
    return await call(store.put,fund,owner,rid,body.kind,body.payload,body.expected_version)


@router.get('/research/{rid}/history')
async def history(rid:str,request:Request):
    fund,owner=scope(request)
    return {'versions':await call(store.history,fund,owner,rid)}


class Monitor(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbols:list[str]=Field(max_length=10)
    interval_minutes:int=Field(60,ge=60,le=10080)
    enabled:bool=False


@router.put('/monitor')
async def configure_monitor(body:Monitor,request:Request):
    fund,owner=scope(request)
    symbols=list(dict.fromkeys(s.strip().upper() for s in body.symbols))
    if any(not re.fullmatch(r'[A-Z0-9.^=_-]{1,64}',s) for s in symbols) or (body.enabled and not symbols):raise HTTPException(422,'Choose 1–10 valid symbols to enable monitoring.')
    return await call(store.monitor,fund,owner,{**body.model_dump(),'symbols':symbols})


@router.post('/monitor/run')
async def scan_monitor(request:Request):
    fund,owner=scope(request)
    return await call(store.queue_monitor,fund,owner)


class Pair(BaseModel):
    before_id:str=Field(max_length=128)
    after_id:str=Field(max_length=128)


@router.post('/valuation-attribution')
async def attribution(body:Pair,request:Request):
    fund,owner=scope(request)
    rows=await call(store.records,fund,owner);byid={r['id']:r for r in rows}
    a,b=byid.get(body.before_id),byid.get(body.after_id)
    if not a or not b:raise HTTPException(404,'Saved observations not found in this account/fund.')
    x,y=a['payload'],b['payload']
    if a['kind']!='observation' or b['kind']!='observation' or x.get('kind')!='valuation' or y.get('kind')!='valuation' or x.get('symbol')!=y.get('symbol'):raise HTTPException(422,'Select two valuation captures for the same symbol.')
    return await call(analytics.valuation_bridge,x,y)


@router.get('/security/{symbol}')
async def security(symbol:str,request:Request):
    scope(request)
    if len(symbol)>64:raise HTTPException(422,'Symbol is too long')
    from api.workflows.securities import resolve
    from api.routers.marketdata import _run
    return await _run(resolve,symbol)


class Alias(BaseModel):
    alias:str=Field(min_length=1,max_length=64)
    security_id:str=Field(min_length=1,max_length=160)
    evidence:str=Field(min_length=10,max_length=2000)


@router.post('/security-alias')
async def alias(body:Alias,request:Request):
    from api.core.access import require_roles
    from api.workflows.securities import alias
    user=require_roles(request,{'admin'})
    return await call(alias,body.alias.strip().upper(),body.security_id,body.evidence,user['username'])


@router.get('/earnings-quality/{symbol}')
async def earnings_quality(symbol:str,request:Request):
    scope(request)
    from api.marketdata import dcf
    from api.routers.marketdata import _run
    inp=await _run(dcf.inputs,symbol)
    return analytics.quality(inp)


class BrokerRow(BaseModel):
    symbol:str=Field(min_length=1,max_length=64)
    quantity:float=Field(allow_inf_nan=False)
    currency:str=Field(min_length=1,max_length=12)
    cash:float|None=Field(None,allow_inf_nan=False)
    price:float|None=Field(None,ge=0,allow_inf_nan=False)
    market_value:float|None=Field(None,allow_inf_nan=False)
    value_currency:str|None=Field(None,max_length=12)
    fx_rate:float|None=Field(None,gt=0,allow_inf_nan=False)


class Reconciliation(BaseModel):
    broker:list[BrokerRow]=Field(min_length=1,max_length=2000)
    quantity_tolerance:float=Field(1e-6,ge=0,le=1)


@router.post('/reconcile')
async def reconcile(body:Reconciliation,request:Request):
    scope(request)
    from api.routers.book import portfolio_positions_v1
    from api.workflows.securities import normalize
    book=await portfolio_positions_v1()
    broker=[r.model_dump(exclude_none=True) for r in body.broker];positions=book['positions']
    cash_state={'available':False,'reason':'No CASH row supplied by broker.'}
    if any(r['symbol'].upper()=='CASH' for r in broker):
        from api import fund_store,blotter_store
        from api.calculations.blotter import blotter_totals,cash_balance
        settings,trades=await asyncio.gather(call(fund_store.get_settings),call(blotter_store.list_trades))
        if all(analytics.finite(p.get('cost_basis')) for p in positions):
            totals=blotter_totals(trades);realized=totals['realized_pnl']+float(settings.get('realized_pnl') or 0)
            cash=cash_balance(settings['capital'],positions,realized,totals['commissions'])
            positions=[*positions,{'symbol':'CASH','quantity':cash,'cash':cash,'currency':book['currency']}]
            cash_state={'available':True,'book_cash':cash,'currency':book['currency'],'source':'Fund capital, cost basis, realized P&L and commissions; consistent with the existing fund cash calculation.'}
        else:cash_state={'available':False,'reason':'Cost basis is incomplete; book cash reconciliation is withheld.'}
    def run():
        for r in broker:r['symbol']=normalize(r['symbol'])
        for r in positions:r['symbol']=normalize(r['symbol'])
        result=analytics.reconcile(broker,positions,body.quantity_tolerance)
        result.update(base_currency=book.get('currency'),priced_at=book.get('priced_at'),cash_evidence=cash_state)
        return result
    return await call(run)


class Scenario(BaseModel):
    equity_shock:float=Field(-.2,ge=-1,le=3)
    fx_shock:float=Field(0,ge=-.9,le=3)
    cash:float=Field(0,allow_inf_nan=False)
    long_margin:float=Field(.5,ge=0,le=2)
    short_margin:float=Field(1.5,ge=0,le=3)


@router.post('/risk-scenario')
async def risk_scenario(body:Scenario,request:Request):
    scope(request)
    from api.routers.book import portfolio_positions_v1
    book=await portfolio_positions_v1()
    return {**analytics.scenario(book['positions'],**body.model_dump()),'currency':book.get('currency'),'priced_at':book.get('priced_at')}


@router.get('/risk')
async def risk(request:Request,participation:float=Query(.1,gt=0,le=.5)):
    scope(request)
    from api.routers.book import risk_liquidity_v1
    return await risk_liquidity_v1(book=None,participation=participation,illiquid_days=5.0)


@router.get('/validation')
async def validation(request:Request):
    scope(request)
    from api.services.forecast_tracker import forecast_tracker
    try:return {'models':await call(forecast_tracker.get_accuracy_summary),'evidence':'Tracked outcomes; coverage and evaluated sample count must be checked. Does not independently certify out-of-sample provenance.'}
    except Exception as e:return {'models':{},'available':False,'reason':f'Forecast evidence unavailable ({type(e).__name__})'}


class ForecastRows(BaseModel):
    rows:list[dict[str,Any]]=Field(min_length=1,max_length=10000)


@router.post('/validation/evaluate')
async def evaluate(body:ForecastRows,request:Request):
    scope(request)
    return await call(analytics.validate_forecasts,body.rows)


@router.get('/performance')
async def performance(request:Request):
    from api.core.access import require_roles
    require_roles(request,{'admin'})
    from api.workflows.telemetry import snapshot
    from api.marketdata import core
    from api.utils.cache import _ASYNC_TTL_CACHE,_ASYNC_CACHE_LOCK
    from api.utils.singleflight import status
    out=snapshot()
    with core._lock:out['market_cache']={'entries':len(core._cache),'inflight_keys':len(core._inflight),'background_refreshes':len(core._refreshing),'background_workers':4,'background_capacity':16}
    with _ASYNC_CACHE_LOCK:out['async_cache_entries']=len(_ASYNC_TTL_CACHE)
    out['upstream_work']=status()
    return out


class EarningsAdjustment(BaseModel):
    label:str=Field(min_length=1,max_length=200)
    after_tax_amount:float=Field(allow_inf_nan=False)
    source_url:str=Field(min_length=8,max_length=2000,pattern=r"^https?://")


class AdjustmentBridge(BaseModel):
    period_end:str=Field(min_length=4,max_length=40)
    adjustments:list[EarningsAdjustment]=Field(min_length=1,max_length=30)


@router.post('/earnings-quality/{symbol}/adjustments')
async def adjusted_earnings(symbol:str,body:AdjustmentBridge,request:Request):
    scope(request)
    from api.marketdata import dcf
    from api.routers.marketdata import _run
    inp=await _run(dcf.inputs,symbol)
    if str(inp.get('as_of'))!=body.period_end or not analytics.finite(inp.get('net_income')):
        raise HTTPException(422,'Adjustment period must match the reported income period exactly; reported net income must be available.')
    ni=inp['net_income'];adjusted=ni+sum(r.after_tax_amount for r in body.adjustments);shares=inp.get('shares')
    return {'period_end':body.period_end,'currency':inp.get('currency'),'reported_net_income':ni,'adjusted_net_income':adjusted,
            'adjusted_eps':adjusted/shares if analytics.finite(shares) and shares>0 else None,'adjustments':[r.model_dump() for r in body.adjustments],
            'source':inp.get('source'),'note':'User-entered after-tax adjustments with evidence links. Not provider consensus or an audited company-defined adjusted metric; does not change valuation inputs.'}
