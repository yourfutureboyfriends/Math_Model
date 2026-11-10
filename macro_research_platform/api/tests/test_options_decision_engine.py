from dataclasses import replace
from datetime import timedelta
import json
import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.quant.optengine import EngineConfig,DecisionEngine,PaperBook
from api.quant.optengine.config import ForecastConfig,DataConfig,RiskConfig,ConfigError
from api.quant.optengine.schema import Quote,Spot,DataError,AssignmentEvent,Opportunity,utc
from api.quant.optengine.features import FeaturePanel
from api.quant.optengine.providers import Snapshot,HistoricalProvider
from api.quant.optengine.quantlab import config_export,import_export,replay,provider_from_payload
from api.quant.optengine.scoring import measure,execution_value
from api.quant.optengine.regimes import forecast,classify
from api.quant.optengine.risk import size,reservation
from api.quant.optengine.registry import Registry,ConflictError
from api.quant.optengine.execution import LiveExecutionDisabled
from api.quant.optengine.strategies import BUILDERS
from api.quant.optengine.strategies.base import bounds,payoff,valid_legs

T='2025-04-25T20:00:00+00:00'
T1='2025-04-28T20:00:00+00:00'
EXP='2025-06-02T20:00:00+00:00'

def config(**kwargs):
    return EngineConfig(forecast=ForecastConfig(validated=True,trained_through='2023-12-31T00:00:00+00:00',validation_id='fixture-not-performance-evidence',intercept=.003),data=DataConfig(allow_model_quotes=True),**kwargs)

def chain(u='A',asof=T,physical=False):
    out=[]
    for kind,strikes,deltas in [('put',[90,95,100],[-.1,-.25,-.5]),('call',[100,105,110],[.5,.25,.1])]:
        for strike,delta in zip(strikes,deltas):
            premium={.1:.25,.25:1.25,.5:3.05}[abs(delta)]
            out.append(Quote(f'{u}:{kind}:{strike}',u,kind,strike,EXP,premium-.025,premium+.025,.5,delta,.01,.10,-.02,100,1000,asof,asof,exercise='american' if physical else 'european',settlement='physical' if physical else 'cash',source='fixture'))
    return out

def snapshot(asof=T,us=('SPY','A'),assignments=(),physical=False):
    return Snapshot(asof,{u:Spot(u,99.99,100.01,'USD',asof,asof) for u in us},{'USD':1},asof,annual_cash_rate=.03,buying_power=1_000_000,assignments=assignments)

def feature(momentum=.2):
    return {'spot':100.,'price':100.,'sma200':90. if momentum>0 else 110.,'momentum21':momentum/3,'momentum63':momentum,'momentum252':momentum*3,'market_momentum63':.02,'volatility20':.2,'volatility63':.2,'volatility252':.2,'drawdown':-.02,'sector':'TECH','country':'US'}

def opportunity(name='bull_put',cfg=None,physical=False):
    cfg=cfg or config()
    op=BUILDERS[name](chain(physical=physical),T,feature(),{'confidence':1},cfg.strategies[name])[0]
    return measure(op,snapshot(),cfg)

def provider(n=2,availability=None):
    symbols=['SPY']+[f'S{i:04d}' for i in range(n-1)] if n>2 else ['SPY','A']
    index=pd.bdate_range(end=T,periods=300)
    time=np.arange(300)
    increments=.004+.003*np.sin(time[:,None]*.71+np.arange(n)[None,:]*.43)
    close=pd.DataFrame(100*np.exp(np.cumsum(increments,axis=0)),index=index,columns=symbols)
    volume=pd.DataFrame(1_000_000.,index=index,columns=symbols)
    meta={u:{'currency':'USD','sector':f'SECTOR{i%10}','country':'US','tradable':u!='SPY','available_at':'2020-01-01T00:00:00+00:00'} for i,u in enumerate(symbols)}
    panel=FeaturePanel(close,volume,meta)
    snaps={t:snapshot(t,symbols) for t in (T,T1)}
    return HistoricalProvider(panel,lambda u,t:chain(u,t),snaps,cache_size=8,availability=availability),close,volume,meta

def intent(op,contracts=1):
    return {'order_id':'test-order','created_at':T,'contracts':contracts,'opportunity':op.to_dict()}

@pytest.mark.parametrize('name',list(BUILDERS))
def test_four_builders_have_defined_payoffs(name):
    cfg=config();op=opportunity(name,cfg)
    low,high=bounds(op.legs)
    samples=payoff(op.legs,np.linspace(0,1_000_000,1000))
    assert samples.min()>=low and samples.max()<=high
    assert op.max_loss>0 and op.max_profit>0 and op.margin>=op.max_loss
    assert len(op.legs)==(4 if name=='iron_condor' else 2)
    assert np.isfinite(op.expected_net) and op.terms['forecast']['validation_id']==cfg.forecast.validation_id
    assert op.max_loss==pytest.approx(op.entry-low+op.terms['roundtrip_reserve'])

@pytest.mark.parametrize('bad',[{'risk':{'max_position_loss':.06}}, {'schema_version':True},{'forecast':{'validated':True}}, {'score_weights':{'edge':1}}, {'unknown':1}, {'data':{'shortlist':200}}, {'approved_ranges':{'risk.max_position_loss':[.02,.03]}}])
def test_invalid_configs_fail_closed(bad):
    with pytest.raises((ConfigError,TypeError)):EngineConfig.from_dict(bad)

def test_export_identity_and_status():
    cfg=config();raw=config_export(cfg)
    assert import_export(json.loads(json.dumps(raw))).config_id==cfg.config_id
    raw['config']['risk']['max_position_loss']=.005
    with pytest.raises(DataError):import_export(raw)
    raw=config_export(cfg);raw['status']='approved'
    with pytest.raises(DataError):import_export(raw)

@pytest.mark.parametrize('change',[{'available_at':T1},{'quoted_at':'2025-04-24T20:00:00+00:00'},{'open_interest':None},{'delta':.25},{'multiplier':True},{'bid':2.,'ask':1.},{'iv':float('nan')}])
def test_bad_contract_data_rejected(change):
    with pytest.raises(DataError):replace(chain()[0],**change).validate(T,config().data,'research')

def test_model_quotes_cannot_be_paper():
    with pytest.raises(DataError):chain()[0].validate(T,config().data,'paper')

def test_snapshot_identity_and_future_fx():
    with pytest.raises(DataError):replace(snapshot(),fx_available_at=T1).validate()
    with pytest.raises(DataError):replace(snapshot(),spots={'WRONG':snapshot().spots['A']}).validate()

def test_features_have_no_future_leakage():
    p,close,vol,meta=provider();before=p.features(T)
    future=pd.Timestamp(T1)
    close.loc[future]=1e12;vol.loc[future]=1e12
    after=FeaturePanel(close,vol,meta).features(T)
    assert before==after
    assert p.features(T) is before

def test_unobserved_latest_bar_is_not_used():
    p,close,vol,meta=provider();obs=pd.DataFrame(True,index=close.index,columns=close.columns);obs.iloc[-1,1]=False
    assert 'A' not in FeaturePanel(close,vol,meta,obs).features(T)

def test_forecast_required_and_trained_before_decision():
    p,*_=provider();book=PaperBook(1_000_000,EngineConfig().config_id)
    result=DecisionEngine(EngineConfig(),p).tick(book,T)
    assert not result['decisions'] and not p.chain_requests
    cfg=replace(config(),forecast=replace(config().forecast,trained_through=T))
    with pytest.raises(DataError):forecast(feature(),cfg,T)

@pytest.mark.parametrize('mom,expected',[(.2,'bull_call'),(-.2,'bear_put'),(0.,'iron_condor')])
def test_regime_selects_directions(mom,expected):
    cfg=config();f=feature(mom);market=feature(.02)
    assert expected in classify(f,market,.5,forecast(f,cfg,T),cfg)['strategies']

def test_full_universe_screen_only_requests_finalist_chains():
    cfg=config();p,*_=provider(3117);result=DecisionEngine(cfg,p).tick(PaperBook(1_000_000,cfg.config_id),T)
    assert result['screening']['universe']==3117
    assert result['screening']['shortlist']==75 and result['screening']['finalists']==35
    assert len(p.chain_requests)==35 and len(p.cache)<=8
    assert result['screening']['approved_intents']<=cfg.risk.max_positions
    assert len(next(e for e in result['events'] if e['event']=='underlying_signals')['signals'])==3117

def test_availability_filter_precedes_loading_chains():
    cfg=config();p,*_=provider(101,lambda u,t:{'available_at':t,'available':u.endswith('0')})
    result=DecisionEngine(cfg,p).tick(PaperBook(1_000_000,cfg.config_id),T)
    assert 0<len(p.chain_requests)<35
    assert all(u.endswith('0') for u,t in p.chain_requests)
    assert result['screening']['shortlist']==75

def test_risk_budget_and_buying_power():
    cfg=config();p,*_=provider();op=opportunity(cfg=cfg);book=PaperBook(100_000,cfg.config_id);snap=snapshot()
    decision=size(op,book,snap,p,cfg)
    assert decision.contracts>0
    assert decision.contracts*op.max_loss<=book.nav*cfg.risk.max_position_loss
    assert size(op,book,replace(snap,buying_power=0),p,cfg).contracts==0
    assert size(op,book,snap,p,cfg,[reservation(op,1,snap)]).contracts==0
    book.emergency_stop('manual')
    assert size(op,book,snap,p,cfg).contracts==0

def test_missing_correlation_blocks_additional_exposure():
    cfg=config();p,*_=provider();op=opportunity(cfg=cfg);snap=snapshot();other=reservation(op,1,snap);other['underlying']='MISSING'
    assert size(op,PaperBook(1_000_000,cfg.config_id),snap,p,cfg,[other]).reason=='Correlation data unavailable'

def test_next_snapshot_fills_and_cash_ledger():
    cfg=config();op=opportunity(cfg=cfg);book=PaperBook(100_000,cfg.config_id)
    with pytest.raises(DataError):book.fill(intent(op),op,2,snapshot(),cfg)
    fill=book.fill(intent(op),op,2,snapshot(T1),cfg)
    quotes={q.contract_id:q for q in chain(asof=T1)}
    book.mark(snapshot(T1),quotes,cfg)
    assert book.nav==pytest.approx(book.cash+sum(p['mark'] for p in book.positions))
    assert book.cash==pytest.approx(100_000-fill['entry']-fill['fees'])
    assert book.fill(intent(op),op,2,snapshot(T1),cfg) is None
    closed=book.close(book.positions[0],snapshot(T1),quotes,cfg,'fixture exit')
    assert book.cash==pytest.approx(100_000-fill['entry']-fill['fees']+closed['cashflow'])
    assert len(closed['legs'])==2 and not book.positions
    assert book.cash<100_000

def test_position_quotes_and_spots_fail_closed():
    cfg=config();op=opportunity(cfg=cfg);book=PaperBook(100_000,cfg.config_id);book.fill(intent(op),op,1,snapshot(T1),cfg)
    with pytest.raises(DataError):book.mark(snapshot(T1),{},cfg)
    quotes={q.contract_id:q for q in chain(asof=T1)}
    with pytest.raises(DataError):book.mark(replace(snapshot(T1),spots={}),quotes,cfg)
    quotes[op.contract_ids[0]]=replace(quotes[op.contract_ids[0]],strike=94)
    with pytest.raises(DataError):book.mark(snapshot(T1),quotes,cfg)

def test_partial_physical_assignment_splits_and_unwinds():
    cfg=config();op=opportunity(cfg=cfg,physical=True);book=PaperBook(100_000,cfg.config_id);book.fill(intent(op),op,2,snapshot(T1),cfg)
    event=AssignmentEvent('assignment-1','test-order',op.contract_ids[0],1,T1,T1)
    snap=snapshot(T1,assignments=(event,));book.apply_assignments(snap,cfg)
    assert book.inventory['A']==100 and len(book.positions)==2
    assert sum(p['contracts'] for p in book.positions)==2
    assert book.apply_assignments(snap,cfg)==[]
    quotes={q.contract_id:q for q in chain(asof=T1,physical=True)}
    assigned=next(p for p in book.positions if p['assignment_unwind'])
    book.close(assigned,snap,quotes,cfg,'assignment unwind');book.unwind_inventory(snap,cfg)
    assert not book.inventory and len(book.positions)==1 and book.positions[0]['contracts']==1
    book.mark(snap,quotes,cfg)
    assert np.isfinite(book.nav)

def test_physical_collateral_exceeds_expiry_defined_loss():
    op=opportunity(physical=True)
    assert op.margin>=9500 and op.margin>op.max_loss

def test_expiry_requires_official_identity_and_instructions():
    cfg=config();op=opportunity(cfg=cfg);book=PaperBook(100_000,cfg.config_id);book.fill(intent(op),op,1,snapshot(T1),cfg)
    snap=snapshot(EXP)
    with pytest.raises(DataError):book.settle(snap,{},cfg)
    event={'underlying':'A','expiry':EXP,'currency':'USD','available_at':EXP,'price':92.,'source':'fixture'}
    cash=book.cash;book.settle(snap,{('A',EXP):event},cfg)
    assert book.cash==pytest.approx(cash-300) and not book.positions
    op=opportunity(cfg=cfg,physical=True);book=PaperBook(100_000,cfg.config_id);book.fill(intent(op),op,1,snapshot(T1),cfg)
    with pytest.raises(DataError):book.settle(snap,{('A',EXP):event},cfg)
    event['exercises']={op.contract_ids[0]:True,op.contract_ids[1]:False}
    book.settle(snap,{('A',EXP):event},cfg)
    assert book.inventory['A']==100

def test_tick_revalidates_and_emergency_stop_closes():
    cfg=config();p,*_=provider();book=PaperBook(1_000_000,cfg.config_id);engine=DecisionEngine(cfg,p)
    first=engine.tick(book,T)
    assert first['decisions'] and not book.positions
    second=engine.tick(book,T1)
    assert book.positions and any(e['event']=='fill' for e in second['events'])
    with pytest.raises(DataError):engine.tick(book,T1)
    book.emergency_stop('user stop');t2='2025-04-29T20:00:00+00:00';p.snapshots[t2]=snapshot(t2)
    third=engine.tick(book,t2)
    assert third['status']=='stopped' and not book.positions and not book.pending

def test_live_execution_prohibited():
    with pytest.raises(LiveExecutionDisabled):PaperBook(100_000,config().config_id,'live')

def test_registry_ownership_approval_and_transaction_conflict(tmp_path):
    reg=Registry(tmp_path/'registry.sqlite');cfg=replace(config(),data=DataConfig());key=cfg.config_id
    reg.import_research('alice',cfg.to_dict())
    assert reg.get_config(key,'bob') is None
    with pytest.raises(ConfigError):reg.create_book('alice',key,100_000,'paper')
    evidence={'run_id':'fixture','config_id':key,'validation_id':cfg.forecast.validation_id,'reviewed_by':'fixture reviewer','validation_end':'2024-12-31T00:00:00+00:00'}
    with pytest.raises(PermissionError):reg.approve(key,{'username':'alice','role':'quant'},evidence,True)
    approved=reg.approve(key,{'username':'alice','role':'risk'},evidence,True)
    assert approved['status']=='approved'
    row=reg.create_book('alice',key,100_000,'paper');bid=row['id']
    reg.commit_tick(bid,'alice',0,row['state'],T,[{'event':'fixture'}])
    with pytest.raises(ConflictError):reg.commit_tick(bid,'alice',0,row['state'],T,[{'event':'must rollback'}])
    assert len(reg.events(bid,'alice'))==1 and reg.events(bid,'bob') is None
    reg.revoke(key,{'username':'alice','role':'risk'},'fixture revoke')
    assert not DecisionEngine(cfg,None,reg.get_config(key,'alice')).entry_permission(PaperBook(100_000,key,'paper'),T1)

def test_model_quote_configs_cannot_be_approved(tmp_path):
    reg=Registry(tmp_path/'registry.sqlite');cfg=config();reg.import_research('alice',cfg.to_dict())
    with pytest.raises(ConfigError):reg.approve(cfg.config_id,{'username':'alice','role':'admin'},{},True)

def test_api_authentication_ownership_and_live_block(tmp_path,monkeypatch):
    from api.routers import options_engine as endpoint
    reg=Registry(tmp_path/'registry.sqlite');monkeypatch.setattr(endpoint,'registry',lambda:reg)
    app=FastAPI();app.include_router(endpoint.router)
    @app.middleware('http')
    async def fixture_auth(request,call_next):
        request.state.user={'username':request.headers['fixture-user'],'role':request.headers.get('fixture-role','quant')} if request.headers.get('fixture-user') else None
        return await call_next(request)
    client=TestClient(app);base='/api/v1/quant/options-engine';headers={'fixture-user':'alice'}
    assert client.get(base+'/meta').status_code==401
    cfg=EngineConfig();row=client.post(base+'/configs',json={'export':config_export(cfg)},headers=headers)
    assert row.status_code==200
    assert client.get(base+'/configs/'+cfg.config_id,headers={'fixture-user':'bob'}).status_code==404
    assert client.post(base+'/books',json={'config_id':cfg.config_id,'mode':'live'},headers=headers).status_code==403
    assert client.post(base+'/configs/'+cfg.config_id+'/approve',json={'evidence':{},'acknowledge':True},headers=headers).status_code==403
    book=client.post(base+'/books',json={'config_id':cfg.config_id},headers=headers)
    assert book.status_code==200
    bid=book.json()['id']
    assert client.post(base+'/books/'+bid+'/stop',json={'reason':'stop','acknowledge':True},headers=headers).status_code==403
    stopped=client.post(base+'/books/'+bid+'/stop',json={'reason':'stop','acknowledge':True},headers={**headers,'fixture-role':'risk'})
    assert stopped.status_code==200 and stopped.json()['state']['stopped']
    assert len(client.get(base+'/books/'+bid+'/events',headers=headers).json()['events'])==1

@pytest.mark.parametrize('name,momentum,mean',[('bull_put',.06,.0005),('bull_call',.2,.003),('bear_put',-.2,-.003),('iron_condor',0.,0.)])
def test_each_strategy_can_generate_a_qualified_intent(name,momentum,mean):
    cfg=config();cfg=replace(cfg,forecast=replace(cfg.forecast,intercept=mean),strategies={n:replace(s,enabled=n==name) for n,s in cfg.strategies.items()})
    p,*_=provider();features=p.features(T);base=features['A'];target={**base,**feature(momentum)}
    if name in ('bull_put','iron_condor'):target.update({f'volatility{k}':.10 for k in (20,63,252)})
    market={**features['SPY'],**feature(.02)}
    p.features=lambda t,min_history=253:{'SPY':market,'A':target}
    result=DecisionEngine(cfg,p).tick(PaperBook(1_000_000,cfg.config_id),T)
    assert len(result['decisions'])==1
    assert result['decisions'][0]['opportunity']['strategy']==name

def test_foreign_currency_contract_and_fx_risk_conversion():
    cfg=config();cfg=replace(cfg,account_currency='GBP');op=opportunity(cfg=config())
    op.legs=tuple(replace(l,quote=replace(l.quote,currency='EUR')) for l in op.legs)
    snap=replace(snapshot(),account_currency='GBP',fx={'GBP':1.,'EUR':.85},spots={'A':replace(snapshot().spots['A'],currency='EUR')})
    measured=measure(op,snap,cfg)
    assert measured.entry==pytest.approx(sum(execution_value(l,cfg.costs) for l in op.legs)*.85)
    book=PaperBook(100_000,cfg.config_id);p,*_=provider()
    decision=size(measured,book,snap,p,cfg)
    assert decision.contracts*measured.max_loss<=book.nav*.01
    with pytest.raises(DataError):measure(op,replace(snap,fx={'GBP':1}),cfg)

def payload():
    p,close,volume,meta=provider()
    return {'history':{'symbols':list(close.columns),'available_at':[t.isoformat() for t in close.index],'close':close.to_numpy().tolist(),'volume':volume.to_numpy().tolist(),'metadata':meta,'market':'SPY'},'snapshots':[{'snapshot':{'asof':t,'spots':{u:{'underlying':u,'bid':99.99,'ask':100.01,'currency':'USD','quoted_at':t,'available_at':t} for u in close.columns},'fx':{'USD':1},'fx_available_at':t,'annual_cash_rate':.03},'chains':{u:[q.to_dict() for q in chain(u,t)] for u in close.columns}} for t in (T,T1)]}

def test_quantlab_replay_and_api_tick_audit(tmp_path,monkeypatch):
    from api.routers import options_engine as endpoint
    cfg=config();raw=payload();p,settlements=provider_from_payload(raw,cfg)
    result=replay(cfg,p,[T,T1],settlements=settlements)
    assert len(result['book']['positions'])==1 and result['metrics'] is not None
    assert not result['provenance']['profitability_validated'] and result['provenance']['no_optimization']
    json.dumps(result,allow_nan=False)
    reg=Registry(tmp_path/'registry.sqlite');reg.import_research('alice',cfg.to_dict());monkeypatch.setattr(endpoint,'registry',lambda:reg)
    row=reg.create_book('alice',cfg.config_id,1_000_000,'research')
    for entry in raw['snapshots']:
        tick=endpoint.run_tick(row['id'],'alice',{'history':raw['history'],'snapshots':[entry]})
        assert tick['status']=='ok'
    saved=reg.get_book(row['id'],'alice')
    assert saved['revision']==2 and len(saved['state']['positions'])==1
    event_types={e['event']['event'] for e in reg.events(row['id'],'alice',limit=1000)}
    assert {'underlying_signals','opportunity','order_intent','risk_at_fill','fill'}<=event_types

def test_no_valid_position_data_rolls_back_and_latches_stop():
    cfg=config();p,*_=provider();book=PaperBook(1_000_000,cfg.config_id);engine=DecisionEngine(cfg,p);engine.tick(book,T);engine.tick(book,T1)
    cash=book.cash;positions=json.dumps(book.positions,sort_keys=True);t2='2025-04-29T20:00:00+00:00';p.snapshots[t2]=snapshot(t2);p.chain_loader=lambda u,t:[]
    result=engine.tick(book,t2)
    assert result['nav'] is None and result['status']=='data_blocked' and book.stopped
    assert book.cash==cash and json.dumps(book.positions,sort_keys=True)==positions and not book.pending

def test_regime_alone_does_not_create_trade_without_net_edge():
    cfg=config();cfg=replace(cfg,forecast=replace(cfg.forecast,intercept=0.),strategies={n:replace(s,enabled=n=='iron_condor') for n,s in cfg.strategies.items()})
    p,*_=provider();features=p.features(T);target={**features['A'],**feature(0.)};target.update({f'volatility{k}':.4 for k in (20,63,252)});market={**features['SPY'],**feature(.02)}
    p.features=lambda t,min_history=253:{'SPY':market,'A':target}
    result=DecisionEngine(cfg,p).tick(PaperBook(1_000_000,cfg.config_id),T)
    assert not result['decisions']
    assert any(e['event']=='opportunity' and e['reason'] and 'edge' in e['reason'].lower() for e in result['events'])

def test_audit_compression_is_lossless_and_queryable(tmp_path):
    from api.quant.optengine.registry import encode_event,decode_event
    event={'event':'underlying_signals','signals':[{'underlying':f'S{i}','feature':feature()} for i in range(3117)]}
    encoded=encode_event(event)
    assert isinstance(encoded,bytes) and len(encoded)<len(json.dumps(event))/10
    assert decode_event(encoded)==event
    cfg=EngineConfig();reg=Registry(tmp_path/'registry.sqlite');reg.import_research('alice',cfg.to_dict());row=reg.create_book('alice',cfg.config_id,100_000,'research')
    reg.commit_tick(row['id'],'alice',0,row['state'],T,[event])
    assert reg.events(row['id'],'alice')[0]['event']==event

def test_universe_identity_is_pinned_to_configuration():
    cfg=config();p,*_=provider();p.universe_name='UNAPPROVED_UNIVERSE'
    with pytest.raises(DataError):DecisionEngine(cfg,p).tick(PaperBook(100_000,cfg.config_id),T)

def test_position_sector_and_correlated_budgets_bound_sizing():
    cfg=config();p,*_=provider(4);op=opportunity(cfg=cfg);op.underlying='S0000';snap=snapshot(us=p.universe);book=PaperBook(1_000_000,cfg.config_id)
    existing=reservation(op,1,snap);existing.update(underlying='S0001',risk=24_000,margin=24_000)
    assert size(op,book,snap,p,cfg,[existing]).contracts==0
    existing.update(risk=18_800,sector='TECH',country='US')
    decision=size(op,book,snap,p,cfg,[existing])
    assert decision.contracts*op.max_loss+18_800<=cfg.risk.max_sector_loss*book.nav
    blocked=replace(cfg,risk=replace(cfg.risk,max_positions=1))
    assert size(op,book,snap,p,blocked,[existing]).reason=='Position limit'

def test_drawdown_stop_cancels_pending_entries():
    cfg=config();p,*_=provider();book=PaperBook(1_000_000,cfg.config_id);book.cash=800_000
    result=DecisionEngine(cfg,p).tick(book,T)
    assert result['status']=='stopped' and book.stop_reason=='Portfolio drawdown emergency stop'
    assert not book.pending and not result['decisions']

def test_quant_router_exposes_new_endpoints():
    from api.routers.quant import router
    paths={route.path for route in router.routes}
    assert '/api/v1/quant/options-engine/backtest' in paths
    assert '/api/v1/quant/options-engine/books/{book_id}/tick' in paths

def test_replay_streams_complete_audit_with_bounded_response():
    cfg=config();p,settlements=provider_from_payload(payload(),cfg);stored=[]
    result=replay(cfg,p,[T,T1],settlements=settlements,event_limit=1,event_sink=lambda t,state,events:stored.extend(events))
    assert len(result['events'])==1 and not result['audit']['complete'] and result['audit']['persisted']
    assert len(stored)==result['audit']['event_count'] and len(stored)>1
    assert any(e['event']=='fill' for e in stored)

def test_api_backtest_persists_research_audit(tmp_path,monkeypatch):
    from api.routers import options_engine as endpoint
    reg=Registry(tmp_path/'registry.sqlite');cfg=config();reg.import_research('alice',cfg.to_dict());monkeypatch.setattr(endpoint,'registry',lambda:reg)
    app=FastAPI();app.include_router(endpoint.router)
    @app.middleware('http')
    async def fixture_auth(request,call_next):
        request.state.user={'username':'alice','role':'quant'}
        return await call_next(request)
    client=TestClient(app)
    result=client.post('/api/v1/quant/options-engine/backtest',json={'config_id':cfg.config_id,'data':payload(),'event_limit':1})
    assert result.status_code==200
    raw=result.json();assert raw['audit']['persisted'] and raw['audit']['returned_events']==1
    assert len(reg.events(raw['audit']['book_id'],'alice',limit=1000))==raw['audit']['event_count']
    assert reg.get_book(raw['audit']['book_id'],'alice')['state']['mode']=='research'

def test_sparse_recent_volatility_window_cannot_understate_risk():
    p,close,volume,meta=provider();observed=pd.DataFrame(True,index=close.index,columns=close.columns)
    observed.iloc[-20:-3,1]=False
    assert observed.iloc[-253:,1].sum()>200
    assert 'A' not in FeaturePanel(close,volume,meta,observed).features(T)

def test_missing_matching_spread_has_explicit_rejection_reason():
    cfg=config();p,*_=provider();p.chain_loader=lambda u,t:[replace(q,expiry='2025-08-01T20:00:00+00:00') for q in chain(u,t)]
    result=DecisionEngine(cfg,p).tick(PaperBook(1_000_000,cfg.config_id),T)
    assert not result['decisions']
    assert any(e['event']=='opportunity_rejected' and 'targets' in e['reason'] for e in result['events'])
