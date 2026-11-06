import copy
from datetime import datetime,timedelta,timezone
import numpy as np
import pandas as pd
import pytest
from api.workflows import store,macro_releases
from api.model.core import ModelParams,black_litterman
from api.tests.test_funds import env


def release(**kw):
    return {'country':'US','indicator':'CPI','reference_period':'2026-01','units':'percent','transformation':'month-on-month',
            'seasonal_adjustment':'SA','entry_type':'forecast','forecast_basis':'analyst','value':.3,
            'scheduled_at':'2026-02-10T12:00:00Z','published_at':None,'source':'Test analyst','source_url':'https://example.com/source',
            'supersedes':None,'linked_symbols':['SPY'],**kw}


def test_release_ledger_freezes_actuals_and_revisions_and_preserves_scope(tmp_path,monkeypatch):
    import api.config as cfg
    monkeypatch.setattr(cfg,'DATABASE_URL',f'sqlite:///{tmp_path}/db.sqlite')
    monkeypatch.setattr(store,'now',lambda:'2026-02-01T12:00:00+00:00')
    forecast=macro_releases.add('A','alice',release())
    assert forecast['predeclared_before_scheduled_release']
    with pytest.raises(store.Conflict):macro_releases.add('A','alice',release())
    monkeypatch.setattr(store,'now',lambda:'2026-02-10T13:00:00+00:00')
    actual=macro_releases.add('A','alice',release(entry_type='actual',value=.5,published_at='2026-02-10T12:00:00Z'))
    assert macro_releases.ledger('A','alice')['events'][0]['comparisons'][0]['surprise']==pytest.approx(.2)
    monkeypatch.setattr(store,'now',lambda:'2026-03-10T13:00:00+00:00')
    with pytest.raises(store.Conflict):macro_releases.add('A','alice',release(entry_type='revision',value=.6,published_at='2026-03-10T12:00:00Z',supersedes='wrong'))
    macro_releases.add('A','alice',release(entry_type='revision',value=.6,published_at='2026-03-10T12:00:00Z',supersedes=actual['id']))
    row=macro_releases.ledger('A','alice')['events'][0]['comparisons'][0]
    assert row['first_recorded_actual']==.5 and row['latest_revision']==.6
    assert macro_releases.ledger('A','alice','2026-02-02T00:00:00Z')['events'][0]['comparisons']==[]
    assert macro_releases.ledger('B','alice')['events']==[] and macro_releases.ledger('A','bob')['events']==[]
    assert len(store.inbox('A','alice'))==2


def test_false_future_schedule_cannot_make_post_publication_forecast_score(tmp_path,monkeypatch):
    import api.config as cfg
    monkeypatch.setattr(cfg,'DATABASE_URL',f'sqlite:///{tmp_path}/db.sqlite')
    monkeypatch.setattr(store,'now',lambda:'2026-02-10T11:00:00+00:00')
    macro_releases.add('A','alice',release(scheduled_at='2026-02-10T12:00:00Z'))
    monkeypatch.setattr(store,'now',lambda:'2026-02-10T13:00:00+00:00')
    macro_releases.add('A','alice',release(entry_type='actual',value=.5,published_at='2026-02-10T10:00:00Z'))
    assert macro_releases.ledger('A','alice')['events'][0]['comparisons']==[]
    late=macro_releases.add('A','alice',release(source='Retrospective import'))
    assert not late['predeclared_before_scheduled_release']


def test_release_http_scopes_and_rejects_forged_envelopes(env):
    c=env('analyst');r=c.post('/api/v1/workflows/macro/releases',json=release())
    assert r.status_code==200,r.text
    assert not r.json()['predeclared_before_scheduled_release'] # past schedule cannot create history
    assert env('pm').get('/api/v1/workflows/macro/releases').json()['events']==[]
    assert c.post('/api/v1/workflows/macro/releases',json={**release(),'server_received_at':'2000-01-01'}).status_code==422
    assert c.get('/api/v1/workflows/macro/releases',params={'available_at':'2000-01-01'}).status_code==422
    bad=release(source_url='https://')
    assert c.post('/api/v1/workflows/macro/releases',json=bad).status_code==422


@pytest.mark.parametrize('params',[{'tau':0},{'cost_bps':-1},{'max_weight':float('nan')},{'momentum_months':2.5},{'cov_months':1},{'max_gross':100}])
def test_parameter_contract_rejects_invalid_inputs(params):
    with pytest.raises(ValueError):ModelParams.from_dict(params)


def test_tau_convention_and_independent_uncertainty():
    cov=np.array([[.002,.0003],[.0003,.0005]]);w=np.array([.6,.4]);views=np.array([.01,.003])
    a,_=black_litterman(cov,w,views,2.5,.01,1)
    b,_=black_litterman(cov,w,views,2.5,.2,1)
    assert np.allclose(a,b)
    explicit=np.array([.0005,.0002])
    a,_=black_litterman(cov,w,views,2.5,.01,1,explicit)
    b,_=black_litterman(cov,w,views,2.5,.2,1,explicit)
    assert not np.allclose(a,b)
    with pytest.raises(ValueError):black_litterman(cov,w,views,2.5,.1,1,[-1,.01])


def test_initial_loss_counts_in_max_drawdown():
    from api.model.backtest import _stats
    r=_stats(pd.Series([-.2]+[.01]*11))
    assert r['max_drawdown']==-.2


def test_fcig_reconciles_and_rejects_schema_and_nonfinite_errors():
    from api.marketdata.fcig import parse
    header='date,FCI-G Index (baseline),FFR,10Yr Treasury,Mortgage Rate,BBB,Stock Market,House Prices,Dollar\n'
    r=parse(header+'2026-01-30,.7,.1,.1,.1,.1,.1,.1,.1\n')[0]
    assert abs(r['residual'])<1e-12
    for text in [header+'2026-01-30,1,.1,.1,.1,.1,.1,.1,.1\n',header+'2026-01-30,nan,.1,.1,.1,.1,.1,.1,.1\n','date,wrong\n2026-01-30,1']:
        with pytest.raises(ValueError):parse(text)


def test_challengers_do_not_change_baseline_or_look_ahead():
    from api.tests.test_macro_model import _synthetic
    from api.model.backtest import run_backtest
    pan,rets,blocks,environments=_synthetic(220)
    p=ModelParams(min_history_months=60);start=pan.index[-4].strftime('%Y-%m-%d')
    original=run_backtest(pan,rets,blocks,environments,p,start,benchmark=('Eq','Bond'))
    research=run_backtest(pan,rets,blocks,environments,p,start,benchmark=('Eq','Bond'),research_challengers=True)
    assert original['weights']==research['weights']
    lab=research['research_challengers'];assert lab['available']
    for row in lab['monthly']:
        for name in ('economic','return_momentum','combined'):
            s=row[name];assert s['gross_exposure']<=1+1e-12
            assert s['predicted_volatility']<=p.vol_target+1e-12
            assert s['gross']-s['net']==pytest.approx(s['turnover']*p.cost_bps/10000)
    changed=pan.copy();changed.loc[changed.index[-2]:]*=-100
    future=run_backtest(changed,rets,blocks,environments,p,start,benchmark=('Eq','Bond'),research_challengers=True)
    assert future['research_challengers']['monthly'][0]==lab['monthly'][0]
    assert future['research_challengers']['joint_forecasts'][0]==lab['joint_forecasts'][0]


def test_historical_classifier_scoring_does_not_require_final_allocation(monkeypatch):
    from api.tests.test_macro_model import _synthetic
    from api.model import backtest as bt
    pan,rets,blocks,environments=_synthetic(220)
    original=bt.decide
    monkeypatch.setattr(bt,'decide',lambda panel,returns,blocks,env,t,p,anchors:None if t==rets.index[-1] else original(panel,returns,blocks,env,t,p,anchors))
    r=bt.run_backtest(pan,rets,blocks,environments,ModelParams(min_history_months=60),pan.index[-4].strftime('%Y-%m-%d'),benchmark=('Eq','Bond'),research_challengers=True)
    assert r['research_challengers']['joint_regime']['count']>0
    assert r['forecast_skill']['months_scored']>0


def test_challenger_attempt_is_recorded_before_unavailable_result(env,monkeypatch):
    from api.model import research
    from api.workflows import store
    async def unavailable(*args,**kwargs):return {'available':False,'reason':'Source unavailable'}
    monkeypatch.setattr(research,'compare_vintages',unavailable)
    r=env('analyst').post('/api/v1/workflows/macro/challengers',json={'start':'2024-01-01','end':'2025-01-01'})
    assert r.status_code==200,r.text
    history=store.history('main','analyst',r.json()['experiment_record_id'])
    assert len(history)==2 and history[-1]['payload']['status']=='running' and history[0]['payload']['status']=='unavailable'


def bridge_rows():
    rows=[]
    for n,day in enumerate(pd.date_range('2000-01-01',periods=32,freq='QS')):
        origin=day+pd.Timedelta(days=60);known=day+pd.Timedelta(days=100)
        rows.append({'period':str(day.to_period('Q')),'forecast_at':origin.isoformat()+'+00:00','features_available_at':(origin-pd.Timedelta(days=1)).isoformat()+'+00:00',
                     'features':{'x':float(n),'z':float(n%3)},'target':float(2*n),'target_available_at':known.isoformat()+'+00:00'})
    return rows


def test_bridge_uses_released_training_labels_and_no_future_feature_fitting():
    from api.model.bridge import evaluate
    rows=bridge_rows();a=evaluate(rows)
    assert a['evaluation']['count']>0
    changed=copy.deepcopy(rows);changed[-1]['target']=100000;changed[-1]['features']['x']=100000
    b=evaluate(changed)
    assert a['forecasts'][0]['prediction']==b['forecasts'][0]['prediction']
    bad=copy.deepcopy(rows);bad[-1]['features_available_at']='2999-01-01T00:00:00+00:00'
    with pytest.raises(ValueError):evaluate(bad)


def test_bridge_rejects_future_outcomes_and_registers_valid_attempts(env):
    c=env('analyst');body={'target_name':'GDP growth','units':'qoq SAAR percent','source_url':'https://example.com/data','rows':bridge_rows()}
    r=c.post('/api/v1/workflows/macro/bridge',json=body)
    assert r.status_code==200 and r.json()['registered_research'],r.text
    body['rows'][-1]['target_available_at']='2999-01-01T00:00:00+00:00'
    assert c.post('/api/v1/workflows/macro/bridge',json=body).status_code==422


def test_macro_view_uses_optimistic_history_and_owner_scope(env):
    c=env('analyst');body={'id':'view-test','horizon':'cyclical','title':'Demand slowdown','thesis':'Consumer demand may slow further','invalidation':'Real consumption accelerates sustainably','review_at':'2026-12-01T00:00:00Z','source_url':'https://example.com/report','quantitative_baseline':'Growth model probability unchanged','expected_version':0}
    r=c.post('/api/v1/workflows/macro/views',json=body);assert r.status_code==200,r.text
    assert c.post('/api/v1/workflows/macro/views',json=body).status_code==409
    assert c.get('/api/v1/workflows/macro/views').json()['views'][0]['version']==1
    assert env('pm').get('/api/v1/workflows/macro/views').json()['views']==[]


def test_strategic_equity_and_bond_components_reconcile(env):
    c=env('analyst');body={'asset_type':'equity','base_currency':'USD','inflation':.025,'dividend_yield':.02,'eps_growth':.04,'starting_pe':20,'ending_pe':18,'annual_fx_return':-.01}
    r=c.post('/api/v1/workflows/macro/strategic',json=body).json()
    assert sum(r['components'].values())==pytest.approx(r['annual_local_return'])
    assert r['annual_base_nominal_return']==pytest.approx((1+r['annual_local_return'])*.99-1)
    assert r['annual_base_real_return']==pytest.approx((1+r['annual_base_nominal_return'])/1.025-1)


def test_robust_scenario_comparison_enforces_risk_cash_and_probability_contract():
    from api.model.scenario_allocation import compare
    args={'assets':['Equity','Bonds'],'covariance':[[.0225,.002],[.002,.0064]],'baseline':[.6,.4],
          'scenarios':[{'name':'Expansion','probability':.5,'annual_returns':[.1,.03],'cash_return':.03},
                       {'name':'Slowdown','probability':.3,'annual_returns':[-.1,.07],'cash_return':.025},
                       {'name':'Inflation','probability':.2,'annual_returns':[-.05,-.06],'cash_return':.04}],
          'max_weight':.7,'volatility_ceiling':.12,'risk_aversion':2.5,'turnover_penalty':.001}
    r=compare(**args)
    for key in ('expected_case','worst_scenario'):
        p=r['portfolios'][key]
        assert 'weights' in p
        assert sum(p['weights'].values())+p['cash_weight']==pytest.approx(1)
        assert all(0<=w<=.7+1e-8 for w in p['weights'].values())
        assert p['annual_volatility']<=.12+1e-7
    assert r['portfolios']['worst_scenario']['worst_scenario_return']>=r['portfolios']['baseline']['worst_scenario_return']
    bad=copy.deepcopy(args);bad['scenarios'][0]['probability']=.6
    with pytest.raises(ValueError,match='sum to one'):compare(**bad)


def test_comparison_fingerprints_returns_and_handles_missing_history(monkeypatch):
    import asyncio,dataclasses
    from api.model import research,economies,backtest
    from api.model.data import MACRO_SERIES
    dates=pd.date_range('2018-01-01','2021-01-01',freq='MS')
    raw={sid:pd.Series(100+np.arange(len(dates)),index=dates,dtype=float) for sid in MACRO_SERIES}
    returns=pd.DataFrame({'A':np.full(len(dates),.01)},index=dates)
    async def history():return {sid:[] for sid in MACRO_SERIES},[]
    async def load():return raw,returns
    e=dataclasses.replace(economies.get('us'),loader=load)
    monkeypatch.setattr(economies,'get',lambda _:e)
    monkeypatch.setattr(research.vintages,'load_history',history)
    monkeypatch.setattr(backtest,'run_backtest',lambda *a,**k:{'available':True,'monthly_returns':[],'timeline':[]})
    # research imports the function at module scope too.
    monkeypatch.setattr(research,'run_backtest',backtest.run_backtest)
    a=asyncio.run(research.compare_vintages('2020-01-01','2021-01-01'))
    returns.loc['2020-06-01','A']=.02
    b=asyncio.run(research.compare_vintages('2020-01-01','2021-01-01'))
    assert a['returns_input_sha256']!=b['returns_input_sha256']
    async def empty():return {},pd.DataFrame()
    e=dataclasses.replace(e,loader=empty)
    result=asyncio.run(research.compare_vintages('2020-01-01','2021-01-01'))
    assert not result['available'] and 'history' in result['reason']
