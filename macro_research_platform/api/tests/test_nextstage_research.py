import copy
import json
from pathlib import Path
import pandas as pd
import pytest
from api.model.vintages import panel_at,changes_between
from api.model.calibration import probability_diagnostics
from api.workflows import model_archive
from api.workflows.stress import evaluate
from api.tests.test_dcf_refinements import base
from api.tests.test_funds import env


def interval(d,value,start,end='9999-12-31'):
    return {'date':d,'value':value,'available_from':start,'available_until':end}


def test_vintage_selection_does_not_see_future_revisions_or_unreleased_observations():
    history={'TEST':[interval('2020-01-01',100,'2020-02-10','2020-03-09'),interval('2020-01-01',999,'2020-03-10'),interval('2020-02-01',200,'2020-03-15')]}
    spec={'TEST':('growth','level',1)}
    early,meta=panel_at(history,'2020-02-29',spec)
    later,_=panel_at(history,'2020-03-31',spec)
    assert early.loc['2020-02-01','TEST']==100
    assert later.loc['2020-02-01','TEST']==999
    assert later.loc['2020-03-01','TEST']==200
    assert meta['intraday_verified'] is False
    assert panel_at(history,'2020-01-31',spec)[0].empty
    assert panel_at(history,'2020-02-29',spec)[1]['input_sha256']==meta['input_sha256']


def test_vintage_excludes_incomplete_observation_month():
    panel,_=panel_at({'X':[interval('2020-02-01',12,'2020-02-10')]},'2020-02-29',{'X':('growth','level',0)})
    assert panel.empty


def test_release_evidence_separates_revisions_from_new_observations():
    h={'X':[interval('2020-01-01',1,'2020-02-10','2020-03-09'),interval('2020-01-01',2,'2020-03-10'),interval('2020-02-01',3,'2020-03-15')]}
    r=changes_between(h,'2020-02-29','2020-03-31',limit=1)
    assert r['counts']=={'new_observation':1,'revision':1,'withdrawn':0} and r['truncated']


def test_vintage_input_hash_ignores_future_interval_expiry():
    h={'X':[interval('2020-01-01',1,'2020-02-10')]};spec={'X':('growth','level',1)}
    old=panel_at(h,'2020-02-29',spec)[1]['input_sha256']
    h['X'][0]['available_until']='2020-03-09'
    h['X'].append(interval('2020-01-01',2,'2020-03-10'))
    assert panel_at(h,'2020-02-29',spec)[1]['input_sha256']==old


def test_probability_bins_include_endpoints_and_pair_baseline_scores():
    r=probability_diagnostics([0,1,.7,.7],[0,1,1,0],[.5,.5,None,.5])
    assert r['count']==4 and sum(b['count'] for b in r['bins'])==4
    assert r['baseline_count']==3 and r['log_loss']>0
    assert r['bins'][-1]['upper']==1
    assert all(0<=b['wilson_95'][0]<=b['wilson_95'][1]<=1 for b in r['bins'])


@pytest.mark.parametrize('method',['three_stage','two_stage'])
def test_original_forecast_replays_with_pinned_configuration(tmp_path,monkeypatch,method):
    from api.marketdata import dcf
    monkeypatch.setattr(model_archive,'root',lambda:tmp_path)
    monkeypatch.setattr(dcf,'GROWTH_HALF_LIFE',4.)
    v=model_archive.calculate(base(),method=method,growth=.1)
    monkeypatch.setattr(dcf,'GROWTH_HALF_LIFE',1.)
    r=model_archive.replay_forecast(v)
    assert r['exact_output_match'] and r['values']['per_share']['difference']==0
    modified=copy.deepcopy(v);modified['per_share']+=1
    with pytest.raises(ValueError,match='does not match'):model_archive.replay_forecast(modified)


def test_forecast_replay_captures_fx_without_new_provider_requests(tmp_path,monkeypatch):
    from api.marketdata import dcf
    monkeypatch.setattr(model_archive,'root',lambda:tmp_path)
    monkeypatch.setattr(dcf,'to_usd',lambda n,c:n*{'GBP':1.3,'USD':1}[c])
    v=model_archive.calculate(base(currency='GBP',price_currency='USD'))
    monkeypatch.setattr(dcf,'to_usd',lambda *a:pytest.fail('Replay requested live FX'))
    assert model_archive.replay_forecast(v)['reconciled']
    engine=tmp_path/'engines'/f"{v['_model_archive']['engine_sha256']}.py"
    engine.write_text(engine.read_text()+'\n# tampered')
    with pytest.raises(ValueError,match='Offline forecast replay failed'):model_archive.replay_forecast(v)


def test_archive_rejects_client_code_paths():
    with pytest.raises(ValueError,match='trusted server'):model_archive.replay_forecast({'_model_archive':{'id':'../../etc/passwd'}})


def test_financial_model_original_forecast_replay(tmp_path,monkeypatch):
    monkeypatch.setattr(model_archive,'root',lambda:tmp_path)
    v=model_archive.calculate(base(equity_book=40e9,net_income=4e9,is_financial=True),model='excess_return')
    assert model_archive.replay_forecast(v)['reconciled']


def position(**kw):
    return {'symbol':'TEST','instrument_type':'equity','market_value_base':1000.,'equity_beta':1.,'fx_beta':0.,'margin_rate':.5,'adv_base':10000.,**kw}


def test_stress_reconciles_cash_and_reverse_path_without_invented_liquidation_proceeds():
    r=evaluate([position()],{'equity':-.2,'rates':0,'credit_spread':0,'fx':0},100,redemption=150,loss_limit=100)
    assert r['scenario_pnl_base']==pytest.approx(-200)
    assert r['stressed_equity_base']==pytest.approx(900)
    assert r['cash_after_redemption_base']==-50
    assert r['cash_gap_including_margin_base']==450
    assert r['reverse_stress']['path_scale']==pytest.approx(.5)


def test_stress_unknown_option_preserves_coverage_gap_and_short_direction():
    rows=[position(market_value_base=-1000),position(symbol='OPT',instrument_type='option',market_value_base=500)]
    r=evaluate(rows,{'equity':-.2,'rates':0,'credit_spread':0,'fx':0},0)
    assert r['scenario_pnl_base'] is None and r['known_pnl_base']==pytest.approx(200)
    assert r['covered_gross_fraction']==pytest.approx(2/3)
    assert r['indicative_margin_base'] is None


def test_bond_duration_convexity_and_fx_compound():
    r=evaluate([position(instrument_type='bond',duration=5,convexity=30,fx_beta=1)],{'equity':0,'rates':.01,'credit_spread':0,'fx':-.1},0)
    assert r['scenario_pnl_base']==pytest.approx(1000*((1-.05+.0015)*.9-1))


def test_european_repricing_obeys_put_call_parity_and_volatility_shock():
    import math
    from api.workflows.stress import european_price
    call=european_price(100,100,.2,1,.03,.01,'call');put=european_price(100,100,.2,1,.03,.01,'put')
    assert call-put==pytest.approx(100*math.exp(-.01)-100*math.exp(-.03))
    terms={'side':'call','spot':100,'strike':100,'volatility':.2,'years':1,'rate':.03,'dividend_yield':.01,'quantity':1,'multiplier':100,'fx_to_base':1,'underlying_beta':1}
    p=position(instrument_type='option',market_value_base=call*100,option_terms=terms)
    shocks={'equity':0,'rates':0,'credit_spread':0,'fx':0,'volatility':.1}
    r=evaluate([p],shocks,0)
    expected=(european_price(100,100,.3,1,.03,.01,'call')-call)*100
    assert r['scenario_pnl_base']==pytest.approx(expected)
    assert evaluate([p],{**shocks,'volatility':0},0)['scenario_pnl_base']==0


def test_probability_http_rejects_leakage_and_duplicate_targets(env):
    c=env('analyst');row={'probability':.7,'outcome':1,'baseline':.5,'issued_at':'2020-01-01T00:00:00Z','trained_through':'2019-01-01T00:00:00Z','actual_at':'2020-02-01T00:00:00Z'}
    assert c.post('/api/v1/workflows/probability-check',json={'rows':[row]}).json()['count']==1
    assert c.post('/api/v1/workflows/probability-check',json={'rows':[row,row]}).status_code==422
    assert c.post('/api/v1/workflows/probability-check',json={'rows':[{**row,'trained_through':'2021-01-01T00:00:00Z'}]}).status_code==422


def test_http_stress_requires_finite_sensitivities(env):
    c=env('analyst')
    assert c.post('/api/v1/workflows/portfolio-stress',json={'base_currency':'USD','positions':[position()]}).json()['coverage_complete']
    assert c.post('/api/v1/workflows/portfolio-stress',json={'base_currency':'USD','positions':[position(equity_beta=20)]}).status_code==422


def test_telemetry_keeps_stages_without_symbols_or_query_data():
    from api.workflows import telemetry as t
    token=t.begin_request()
    with t.stage('yahoo_provider'):pass
    stages=t.end_request(token)
    t.observe('/test/{symbol}','GET',200,.1,stages)
    r=next(r for r in t.snapshot()['routes'] if r['route']=='GET /test/{symbol}')
    assert r['p50_ms']==100 and 'yahoo_provider' in r['stage_total_ms']
    assert t._REQUEST_STAGES.get() is None


def test_experiment_registry_keeps_other_accounts_private(env):
    from api.quant import store as q
    q.register_code_run('analyst','Example family',{'code_hash':'a','data_hash':'b','holdout':'2020-01-01','data_last':'2021-01-01'},{'sharpe':1.})
    q.register_code_run('analyst','Example family',{'code_hash':'a','data_hash':'b','holdout':'2020-01-01','data_last':'2021-01-01'},{})
    r=env('analyst').get('/api/v1/workflows/experiment-audit')
    assert r.status_code==200,r.text
    assert r.json()['families'][0]['holdout_reused']
    assert r.json()['families'][0]['runs_without_sharpe']==1
    assert env('pm').get('/api/v1/workflows/experiment-audit').json()['families']==[]


def test_vintage_http_rejects_unbounded_future_and_invalid_ranges_before_fetch(env):
    c=env('analyst')
    for row in [{'start':'2020-01-01','end':'2024-01-01'},{'start':'2999-01-01','end':'2999-02-01'},{'start':'2020-15-01','end':'2020-16-01'}]:
        assert c.post('/api/v1/workflows/macro-vintages',json=row).status_code==422
