"""Authenticated connected workflows; tenant scope always comes from verified middleware."""
import asyncio
import re
from datetime import datetime
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator
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


class VintageComparison(BaseModel):
    start:str=Field(pattern=r'^\d{4}-\d{2}-01$')
    end:str=Field(pattern=r'^\d{4}-\d{2}-01$')


class EuropeanOption(BaseModel):
    style:Literal['european']='european'
    side:Literal['call','put']
    spot:float=Field(gt=0,le=1e9)
    strike:float=Field(gt=0,le=1e9)
    volatility:float=Field(gt=0,le=5)
    years:float=Field(gt=0,le=50)
    rate:float=Field(ge=-.2,le=.5)
    dividend_yield:float=Field(ge=-.2,le=.5)
    quantity:float=Field(allow_inf_nan=False)
    multiplier:float=Field(gt=0,le=1e6)
    fx_to_base:float=Field(gt=0,le=1e9)
    underlying_beta:float=Field(ge=-5,le=5)


class StressPosition(BaseModel):
    symbol:str=Field(min_length=1,max_length=64)
    instrument_type:Literal['equity','bond','option','unknown']='unknown'
    market_value_base:float|None=Field(None,allow_inf_nan=False)
    equity_beta:float|None=Field(None,ge=-5,le=5)
    fx_beta:float|None=Field(None,ge=-5,le=5)
    duration:float|None=Field(None,ge=0,le=100)
    convexity:float|None=Field(None,ge=0,le=10000)
    adv_base:float|None=Field(None,gt=0,allow_inf_nan=False)
    margin_rate:float|None=Field(None,ge=0,le=3)
    option_terms:EuropeanOption|None=None


class StressShocks(BaseModel):
    equity:float=Field(-.2,ge=-1,le=1)
    rates:float=Field(.02,ge=-.1,le=.1)
    credit_spread:float=Field(.01,ge=-.1,le=.1)
    fx:float=Field(0,ge=-.9,le=1)
    volatility:float=Field(0,ge=-2,le=2)


class PortfolioStress(BaseModel):
    positions:list[StressPosition]=Field(min_length=1,max_length=500)
    shocks:StressShocks=Field(default_factory=StressShocks)
    base_currency:str=Field(min_length=3,max_length=8)
    cash:float=Field(0,allow_inf_nan=False)
    redemption:float=Field(0,ge=0,allow_inf_nan=False)
    participation:float=Field(.1,gt=0,le=.5)
    volume_multiplier:float=Field(.5,gt=0,le=2)
    loss_limit:float|None=Field(None,gt=0,allow_inf_nan=False)


@router.post('/portfolio-stress')
async def portfolio_stress(body:PortfolioStress,request:Request):
    scope(request)
    from api.workflows.stress import evaluate
    args=body.model_dump();currency=args.pop('base_currency')
    return {**await call(evaluate,**args),'base_currency':currency}


@router.get('/stress-inputs')
async def stress_inputs(request:Request):
    scope(request)
    from api.routers.book import portfolio_positions_v1
    book=await portfolio_positions_v1()
    return {'base_currency':book.get('currency'),'positions':[{'symbol':p['symbol'],'instrument_type':'unknown',
            'market_value_base':p.get('market_value'),'equity_beta':None,'fx_beta':None,'duration':None,'convexity':None,'adv_base':None,'margin_rate':None,'option_terms':None} for p in book.get('positions',[])],
            'priced_at':book.get('priced_at'),'note':'Current direct holdings only. Verify base values, instrument type and sourced sensitivities before evaluating; ETF look-through is not inferred.'}


class ProbabilityRow(BaseModel):
    probability:float=Field(ge=0,le=1)
    outcome:Literal[0,1]
    baseline:float|None=Field(None,ge=0,le=1)
    issued_at:str
    actual_at:str
    trained_through:str


class ProbabilityRows(BaseModel):
    rows:list[ProbabilityRow]=Field(min_length=1,max_length=10000)


@router.post('/probability-check')
async def probability_check(body:ProbabilityRows,request:Request):
    scope(request)
    from api.workflows.evidence import instant
    from api.model.calibration import probability_diagnostics
    rows=[];seen=set()
    for r in body.rows:
        trained,issued,actual=await call(lambda:(instant(r.trained_through),instant(r.issued_at),instant(r.actual_at)))
        if not trained<=issued<actual<=store.now():raise HTTPException(422,'Require training <= issue < observed outcome <= now')
        if issued in seen:raise HTTPException(422,'Duplicate forecast issue timestamp; evaluate one target/model/horizon per request')
        seen.add(issued);rows.append(r)
    return await call(probability_diagnostics,[r.probability for r in rows],[r.outcome for r in rows],[r.baseline for r in rows])


_vintage_lock=asyncio.Lock()


@router.post('/macro-vintages')
async def macro_vintages(body:VintageComparison,request:Request):
    scope(request)
    if _vintage_lock.locked():raise HTTPException(409,'A vintage comparison is already running; retry after it completes')
    from api.model.research import compare_vintages
    async with _vintage_lock:
        try:return await compare_vintages(body.start,body.end)
        except (TypeError,ValueError) as e:raise HTTPException(422,str(e))


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
    method:Literal['ordered','shapley']='ordered'


@router.post('/valuation-attribution')
async def attribution(body:Pair,request:Request):
    fund,owner=scope(request)
    rows=await call(store.records,fund,owner);byid={r['id']:r for r in rows}
    a,b=byid.get(body.before_id),byid.get(body.after_id)
    if not a or not b:raise HTTPException(404,'Saved observations not found in this account/fund.')
    x,y=a['payload'],b['payload']
    if a['kind']!='observation' or b['kind']!='observation' or x.get('kind')!='valuation' or y.get('kind')!='valuation' or x.get('symbol')!=y.get('symbol'):raise HTTPException(422,'Select two valuation captures for the same symbol.')
    return await call(analytics.valuation_bridge,x,y,body.method)


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


@router.get('/experiment-audit')
async def experiment_audit(request:Request):
    _,owner=scope(request)
    from api.quant.store import experiment_audit as audit
    return await call(audit,owner)


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


@router.get('/observations')
async def observations(request:Request,available_at:str=Query(...,max_length=64),symbol:str|None=Query(None,max_length=64)):
    fund,owner=scope(request)
    return {'records':await call(store.observations_at,fund,owner,available_at,symbol),'cutoff':available_at,'note':'Latest version received by this server at the cutoff. Client observation dates cannot backdate availability.'}


class SavedCapture(BaseModel):
    record_id:str=Field(min_length=1,max_length=128)
    version:int|None=Field(None,ge=1)
    mode:Literal['arithmetic','forecast']='arithmetic'


@router.post('/replay')
async def replay_capture(body:SavedCapture,request:Request):
    fund,owner=scope(request)
    rows=await call(store.history,fund,owner,body.record_id)
    row=next((r for r in rows if body.version is None or r['version']==body.version),None)
    if not row:raise HTTPException(404,'Capture version not found in this account/fund')
    if body.mode=='forecast':
        from api.workflows.model_archive import replay_forecast
        from api.workflows.evidence import digest
        record=row['payload'];data=record.get('payload') or {}
        if (record.get('_evidence') or {}).get('raw_sha256')!=digest(data):raise HTTPException(422,'Capture checksum mismatch')
        primary=data.get('primary') or data.get('base') or data
        return await call(replay_forecast,primary.get('valuation',primary))
    from api.workflows.evidence import replay
    return await call(replay,row['payload'])


class EvidenceURLModel(BaseModel):
    @field_validator('source_url','evidence',check_fields=False)
    @classmethod
    def validate_url(cls,value):
        from api.workflows.evidence import valid_source_url
        return valid_source_url(value)


class EvidenceField(EvidenceURLModel):
    model_config=ConfigDict(extra='forbid')
    field:str=Field(min_length=1,max_length=100)
    value:float=Field(allow_inf_nan=False)
    currency:str=Field(min_length=1,max_length=12)
    units:str=Field(min_length=1,max_length=80)
    period_end:str=Field(min_length=1,max_length=40)
    observed_at:str=Field(min_length=1,max_length=64)
    accounting_basis:str=Field(min_length=1,max_length=100)
    source:str=Field(min_length=1,max_length=200)
    source_url:str=Field(pattern=r'^https?://',max_length=2000)


class FieldComparison(BaseModel):
    left:EvidenceField
    right:EvidenceField
    tolerance:float=Field(.01,ge=0,le=1)


@router.post('/compare-evidence')
async def compare_evidence(body:FieldComparison,request:Request):
    scope(request)
    from api.workflows.evidence import compare_fields
    return await call(compare_fields,body.left.model_dump(),body.right.model_dump(),body.tolerance)


class IdentityLink(EvidenceURLModel):
    security_id:str=Field(min_length=1,max_length=160)
    issuer_id:str=Field(min_length=1,max_length=160)
    share_class_id:str=Field(min_length=1,max_length=160)
    valid_from:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    valid_to:str|None=Field(None,pattern=r'^\d{4}-\d{2}-\d{2}$')
    evidence:str=Field(pattern=r'^https?://',max_length=2000)
    identifiers:dict[str,str]=Field(default_factory=dict,max_length=15)


@router.post('/identity-link')
async def identity_link(body:IdentityLink,request:Request):
    from api.core.access import require_roles
    from api.workflows.securities import link_identity
    user=require_roles(request,{'admin'})
    return await call(link_identity,**body.model_dump(),username=user['username'])


@router.get('/identity-history')
async def identity_history(request:Request,security_id:str=Query(...,max_length=160)):
    scope(request)
    from api.workflows.securities import identity_history
    return {'links':await call(identity_history,security_id),'note':'Dated reference assertions; source evidence and author retained. No automatic name-based issuer merges.'}


@router.get('/estimate-history')
async def estimate_history(request:Request,symbol:str=Query(...,min_length=1,max_length=64),available_at:str|None=Query(None,max_length=64)):
    fund,owner=scope(request)
    from api.workflows.evidence import instant
    from api.workflows.intelligence import estimate_revisions
    cutoff=await call(instant,available_at) if available_at else store.now()
    def load():
        with store.connect() as c:
            rows=c.execute("SELECT v.* FROM workflow_versions v JOIN workflow_records r USING(fund,owner,id) WHERE v.fund=? AND v.owner=? AND r.kind='observation' AND v.recorded_at<=? ORDER BY v.recorded_at DESC LIMIT 5000",(fund,owner,cutoff))
            allrows=[store.unpack(r) for r in rows]
        return estimate_revisions([r for r in allrows if r['payload'].get('symbol','').upper()==symbol.upper()]),len(allrows)
    result,count=await call(load)
    return {**result,'scanned_versions':count,'scan_limit':5000,'cutoff':cutoff}


class ValueForecasts(BaseModel):
    rows:list[dict[str,Any]]=Field(min_length=1,max_length=10000)


@router.post('/validation/values')
async def value_forecasts(body:ValueForecasts,request:Request):
    scope(request)
    from api.workflows.intelligence import validate_values
    return await call(validate_values,body.rows)


class ReviewEvent(BaseModel):
    status:Literal['unreviewed','reviewed','dismissed']
    expected_status:Literal['unreviewed','reviewed','dismissed']='unreviewed'


@router.put('/inbox/{event_id}')
async def review_event(event_id:int,body:ReviewEvent,request:Request):
    fund,owner=scope(request)
    return await call(store.event_review,fund,owner,event_id,body.status,body.expected_status)


@router.get('/inbox')
async def research_inbox(request:Request):
    fund,owner=scope(request)
    rows=await call(store.inbox,fund,owner)
    from api.routers.book import portfolio_positions_v1
    exposure={};coverage='unavailable';issuer_exposures=None
    try:
        book=await portfolio_positions_v1()
        for p in book.get('positions',[]):
            s=p.get('symbol');w=p.get('weight_pct')
            if analytics.finite(w):exposure[s]=exposure.get(s,0)+w
        from api.workflows.securities import group_exposures
        issuer_exposures=await call(group_exposures,book.get('positions',[]),store.now()[:10])
        coverage='direct priced positions only; fund look-through is not inferred'
    except Exception:pass
    return {'events':[{**r,'known_direct_weight':exposure.get(r['payload'].get('symbol'))} for r in rows],'exposure_coverage':coverage,'issuer_exposures':issuer_exposures,'note':'Captured source changes and analyst-linked tracker evidence. A link is not proof of price causality.'}


class TrackerEvidence(EvidenceURLModel):
    symbol:str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9.^=_-]+$')
    entity_type:Literal['vessel','airport','airline','port','route']
    entity_id:str=Field(min_length=1,max_length=160)
    start:str=Field(max_length=64)
    end:str|None=Field(None,max_length=64)
    summary:str=Field(min_length=10,max_length=1000)
    relation:str=Field(min_length=10,max_length=2000)
    source_url:str=Field(pattern=r'^https?://',max_length=2000)
    metric:Literal['port_visit','loitering','ais_gap','flights','passengers','freight','other']
    value:float|None=Field(None,ge=0,allow_inf_nan=False)
    units:str|None=Field(None,max_length=80)


@router.post('/tracker-evidence')
async def tracker_evidence(body:TrackerEvidence,request:Request):
    fund,owner=scope(request)
    from api.workflows.evidence import instant,digest
    start=await call(instant,body.start);end=await call(instant,body.end) if body.end else None
    if end and end<start:raise HTTPException(422,'End precedes start')
    if start>store.now() or (end and end>store.now()):raise HTTPException(422,'Reported tracker events cannot be in the future')
    if body.value is not None and not body.units:raise HTTPException(422,'A reported metric requires explicit units')
    raw={**body.model_dump(),'start':start,'end':end,'symbol':body.symbol.upper()}
    rid='tracker:'+digest(raw)
    observation={'id':rid,'symbol':raw['symbol'],'kind':'tracker_event','payload':raw,'observedAt':store.now()}
    return await call(store.put,fund,owner,rid,'observation',observation,0,event={**raw,'kind':'tracker_event','summary':body.summary,'relation_basis':'Analyst-supplied evidence link; independently verify the relationship'})


class TradePrint(BaseModel):
    at:str=Field(max_length=64)
    price:float=Field(gt=0,allow_inf_nan=False)
    volume:float=Field(gt=0,allow_inf_nan=False)


class ExecutionEvidence(EvidenceURLModel):
    side:Literal['BUY','SELL']
    quantity:float=Field(gt=0,allow_inf_nan=False)
    fill_price:float=Field(gt=0,allow_inf_nan=False)
    arrival_price:float|None=Field(None,gt=0,allow_inf_nan=False)
    currency:str=Field(min_length=3,max_length=12)
    base_currency:str=Field(min_length=3,max_length=12)
    decision_at:str=Field(max_length=64)
    fill_at:str=Field(max_length=64)
    window_start:str=Field(max_length=64)
    window_end:str=Field(max_length=64)
    fees:float|None=Field(None,allow_inf_nan=False)
    fx_to_base:float|None=Field(None,gt=0,allow_inf_nan=False)
    fx_at:str|None=Field(None,max_length=64)
    source_url:str=Field(pattern=r'^https?://',max_length=2000)
    trades:list[TradePrint]=Field(default_factory=list,max_length=10000)


@router.post('/execution-evidence')
async def execution_evidence(body:ExecutionEvidence,request:Request):
    scope(request)
    from api.workflows.evidence import instant
    from api.workflows.intelligence import execution_cost
    row=body.model_dump();decision,fill,start,end=[await call(instant,row[k]) for k in ('decision_at','fill_at','window_start','window_end')]
    if decision>fill or fill>store.now() or start>end or not start<=fill<=end:raise HTTPException(422,'Decision/fill/window timestamps are inconsistent')
    if body.fx_to_base is not None:
        if not body.fx_at:raise HTTPException(422,'FX evidence requires an observation timestamp')
        fx=await call(instant,body.fx_at)
        if fx>fill or (datetime.fromisoformat(fill)-datetime.fromisoformat(fx)).total_seconds()>4*86400:raise HTTPException(422,'FX must be observed at/before execution and no more than four days old')
    for t in body.trades:
        if not start<=await call(instant,t.at)<=end:raise HTTPException(422,'A trade print lies outside the declared VWAP window')
    if body.currency==body.base_currency:
        if body.fx_to_base is not None and body.fx_to_base!=1:raise HTTPException(422,'Same currency requires an FX factor of one')
        row['fx_to_base']=1.0
    return await call(execution_cost,row)


@router.get('/capture-coverage')
async def capture_coverage(request:Request):
    fund,owner=scope(request)
    rows=await call(store.records,fund,owner)
    captures=[r for r in rows if r['kind']=='observation'];flags={};datasets={};verified=0
    for r in captures:
        p=r['payload'];meta=p.get('_evidence') or {};kind=p.get('kind','unspecified')
        datasets[kind]=datasets.get(kind,0)+1
        if meta:verified+=1
        for flag in meta.get('quality_flags',[]) if meta else ['legacy_capture_without_envelope']:flags[flag]=flags.get(flag,0)+1
    return {'captures':len(captures),'with_integrity_envelope':verified,'datasets':datasets,'quality_flags':flags,
            'note':'Coverage of current saved captures for this account/fund, not coverage of the market or independently validated provider accuracy.'}


class CorporateEvidence(EvidenceURLModel):
    security_id:str=Field(min_length=1,max_length=160)
    event_type:Literal['split','adr_ratio','ticker_change','delisting']
    effective_date:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    evidence:str=Field(pattern=r'^https?://',max_length=2000)
    ratio:float|None=Field(None,gt=0,allow_inf_nan=False)
    new_symbol:str|None=Field(None,max_length=64,pattern=r'^[A-Za-z0-9.^=_-]+$')


@router.post('/corporate-evidence')
async def corporate_evidence(body:CorporateEvidence,request:Request):
    from api.core.access import require_roles
    from api.workflows.securities import corporate_event
    user=require_roles(request,{'admin'})
    return await call(corporate_event,**body.model_dump(),username=user['username'])


@router.get('/corporate-evidence')
async def corporate_evidence_history(request:Request,security_id:str=Query(...,max_length=160)):
    scope(request)
    from api.workflows.securities import corporate_history
    return {'events':await call(corporate_history,security_id)}
