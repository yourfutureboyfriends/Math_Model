import asyncio
import copy
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from api.workflows import store, analytics


@pytest.fixture
def database(tmp_path,monkeypatch):
    from api.core import app_db
    path=tmp_path/'workflow-test.db'
    monkeypatch.setattr(app_db,'app_db_path',lambda:str(path))
    return path


def test_versioned_storage_isolates_users_and_funds_and_detects_lost_updates(database):
    r=store.put('a','alice','record','thesis',{'thesis':'first'})
    assert r['version']==1
    assert store.records('b','alice')==store.records('a','bob')==[]
    with pytest.raises(store.Conflict):store.put('a','alice','record','thesis',{'thesis':'lost'},0)
    store.put('a','alice','record','thesis',{'thesis':'second'},1)
    assert [r['version'] for r in store.history('a','alice','record')]==[2,1]
    assert store.history('b','alice','record')==[]


def snapshot(revenue=100,margin=.2,reinvestment=5,discount=.9,terminal=100,cash=10,units=.1):
    pv=(revenue*margin-reinvestment)*discount;ev=pv+terminal;eq=ev+cash
    return {'symbol':'TEST','kind':'valuation','payload':{'model':'fcff','currency':'USD','primary':{'inputs':{},'valuation':{'model':'fcff','per_share':eq*units,'equity_value':eq,'enterprise_value':ev,'pv_terminal':terminal,'projection':[{'year':1,'revenue':revenue,'nopat':revenue*margin,'reinvestment':reinvestment,'discount_factor':discount}]}}}}


def test_attribution_reconciles_without_fresh_quotes():
    a=snapshot();b=snapshot(revenue=120,margin=.3,discount=.8,terminal=110,units=.09)
    r=analytics.valuation_bridge(a,b)
    assert sum(x['contribution'] for x in r['contributions'])==pytest.approx(r['after']-r['before'])
    assert r['residual']==pytest.approx(0)
    assert analytics.valuation_bridge(a,a)['change']==0
    b['payload']['currency']='GBP'
    with pytest.raises(ValueError):analytics.valuation_bridge(a,b)


def test_reconciliation_keeps_currencies_distinct_and_combines_books():
    r=analytics.reconcile([{'symbol':'A','quantity':10,'currency':'USD'}],[{'symbol':'A','quantity':4,'currency':'USD'},{'symbol':'A','quantity':6,'currency':'USD'},{'symbol':'A','quantity':2,'currency':'GBP'}])
    assert r['breaks']==1
    assert next(x for x in r['rows'] if x['currency']=='USD')['status']=='matched'
    assert next(x for x in r['rows'] if x['currency']=='GBP')['status']=='missing_at_broker'


def test_quality_withholds_mismatched_cashflow_comparisons():
    r=analytics.quality({'net_income':10,'revenue':100,'cashflow_evidence':{'status':'unavailable','cfo':20}})
    assert r['cash_conversion'] is None
    r=analytics.quality({'net_income':10,'revenue':100,'cashflow_evidence':{'status':'matched','cfo':5,'sbc':2,'capex':1}})
    assert r['cash_conversion']==.5
    assert r['cash_after_capex_and_sbc']==2
    assert not r['reported_adjusted_reconciliation']['available']


def test_signed_scenario_and_missing_price_coverage():
    r=analytics.scenario([{'symbol':'LONG','market_value':100},{'symbol':'SHORT','market_value':-50},{'symbol':'MISSING','market_value':None}],-.2,0,20,.5,1.5)
    assert r['scenario_pnl'] is None
    assert r['known_position_pnl']==pytest.approx(-10)
    assert r['known_position_margin']==pytest.approx(100)
    assert r['equity_buffer_after_margin'] is None
    assert not r['coverage_complete'] and r['unpriced']==['MISSING']


def test_forecast_validation_rejects_lookahead_and_reports_brier():
    row={'issued_at':'2020-01-02T00:00:00Z','actual_at':'2020-02-01T00:00:00Z','trained_through':'2020-01-01T00:00:00Z','probability':.8,'actual':1}
    bad={**row,'trained_through':'2020-03-01T00:00:00Z'}
    r=analytics.validate_forecasts([row,bad]);assert r['accepted']==1 and r['rejected']==1
    assert r['brier']==pytest.approx(.04);assert r['benchmark_brier']==.25;assert r['drift'] is None


def request(method='GET',user=None):
    return Request({'type':'http','method':method,'path':'/','headers':[],'state':{'user':user}})


def test_route_permissions_reject_anonymous_and_viewer_writes(database):
    from api.routers.workflows import scope,put_record,Record
    with pytest.raises(HTTPException) as e:scope(request())
    assert e.value.status_code==401
    viewer={'username':'v','role':'viewer'}
    assert scope(request(user=viewer))[1]=='v'
    with pytest.raises(HTTPException) as e:asyncio.run(put_record('x',Record(kind='thesis',payload={}),request('PUT',viewer)))
    assert e.value.status_code==403


def test_monitor_deduplicates_and_creates_version_history(database,monkeypatch):
    from api.workflows.monitor import scan
    from api.marketdata import security,research
    value={'estimates':{'eps':[{'period':'0q','avg':1}]}}
    monkeypatch.setattr(security,'earnings',lambda s:copy.deepcopy(value))
    monkeypatch.setattr(research,'filings',lambda s:{'filings':[{'url':'https://example.com/filing'}]})
    assert scan('a','alice',['A'])['new_snapshots']==2
    assert scan('a','alice',['A'])['new_snapshots']==0
    value['estimates']['eps'][0]['avg']=2
    assert scan('a','alice',['A'])['new_snapshots']==1
    assert len(store.history('a','alice','monitor:A:earnings'))==2
    assert store.events('a','bob')==[]


def test_security_alias_requires_explicit_target_and_conflict_is_not_overwritten(database,monkeypatch):
    from api.workflows import securities
    from api.marketdata import core
    monkeypatch.setattr(core,'_info',lambda s:{'symbol':s,'exchange':'NYQ','currency':'USD'})
    a=securities.resolve('A');b=securities.resolve('B')
    securities.alias('ALIAS',a['id'],'Issuer listing evidence','admin')
    assert securities.normalize('alias')=='A'
    with pytest.raises(store.Conflict):securities.alias('ALIAS',b['id'],'Different listing evidence','admin')


def test_forecast_bins_do_not_double_count_boundaries_or_duplicate_rows():
    rows=[{'issued_at':'2020-01-02T00:00:00Z','actual_at':'2020-02-01T00:00:00Z','trained_through':'2020-01-01T00:00:00Z','probability':p,'actual':1} for p in (.2,.4,.6,.8,1)]
    result=analytics.validate_forecasts(rows+[rows[0]])
    assert sum(b['count'] for b in result['calibration'])==result['accepted']==5
    assert result['duplicates_excluded']==1


def test_monitor_records_return_to_previous_estimate_and_preserves_stale_baseline(database,monkeypatch):
    from api.workflows.monitor import scan
    from api.marketdata import security,research
    payload={'estimates':{'eps':[{'period':'0q','avg':1}]}}
    monkeypatch.setattr(security,'earnings',lambda s:copy.deepcopy(payload))
    monkeypatch.setattr(research,'filings',lambda s:{'filings':[]})
    scan('a','alice',['A']);payload['estimates']['eps'][0]['avg']=2;scan('a','alice',['A'])
    payload['estimates']['eps'][0]['avg']=1;scan('a','alice',['A'])
    assert len(store.history('a','alice','monitor:A:earnings'))==3
    payload['stale']=True;payload['estimates']['eps'][0]['avg']=4
    assert scan('a','alice',['A'])['failures']
    assert len(store.history('a','alice','monitor:A:earnings'))==3


def test_workflow_reads_require_full_authentication_state():
    from api.core.access import needs_auth
    assert needs_auth('GET','/api/v1/workflows/research')
    assert needs_auth('GET','/api/v1/workflows/performance')


def test_minor_units_do_not_merge_with_major_currency_cash():
    result=analytics.reconcile([{'symbol':'X','quantity':10,'currency':'GBp'}],[{'symbol':'X','quantity':10,'currency':'GBP'}])
    assert result['breaks']==2


def test_reconciliation_compares_only_explicitly_compatible_values_and_fx():
    broker=[{'symbol':'A','quantity':10,'currency':'USD','market_value':110,'value_currency':'GBP','fx_rate':.8}]
    book=[{'symbol':'A','quantity':10,'currency':'USD','market_value':100,'value_currency':'GBP','fx_rate_to_base':.75}]
    result=analytics.reconcile(broker,book)
    assert result['rows'][0]['market_value_difference']==10
    assert result['rows'][0]['fx_rate_difference']==pytest.approx(.05)
    assert result['rows'][0]['status']=='valuation_or_cash_break'
    broker[0]['value_currency']='EUR'
    result=analytics.reconcile(broker,book)
    assert result['rows'][0]['market_value_difference'] is None
    assert result['rows'][0]['fx_rate_difference'] is None


def test_telemetry_is_bounded_and_contains_templates_only():
    from api.workflows import telemetry
    telemetry.observe('/api/v1/example/{symbol}','GET',503,.2)
    result=telemetry.snapshot()
    row=next(r for r in result['routes'] if r['route']=='GET /api/v1/example/{symbol}')
    assert row['errors_5xx']>=1 and row['p95_ms']>=0
    assert row['sample_count']<=512


def test_scheduled_monitor_rechecks_the_users_fund_position(database,monkeypatch):
    from api.workflows import monitor
    from api import funds,positions
    from api.core import accounts
    store.monitor('a','alice',{'symbols':['A'],'interval_minutes':60,'enabled':True})
    monkeypatch.setattr(accounts,'get_user',lambda _: {'username':'alice','role':'analyst'})
    monkeypatch.setattr(funds,'get',lambda _: {'id':'a','members':['alice']})
    monkeypatch.setattr(positions,'apply_to_user',lambda _: {'username':'alice','role':'viewer'})
    calls=[];monkeypatch.setattr(monitor,'scan',lambda *a:calls.append(a))
    before=funds.CURRENT.get();monitor.run_due()
    assert not calls
    assert not store.monitor('a','alice')['enabled']
    assert funds.CURRENT.get()==before


def test_record_limit_rejects_nonfinite_or_oversized_json(database):
    with pytest.raises(ValueError):store.put('a','alice','x','thesis',{'value':float('nan')})
    with pytest.raises(ValueError):store.put('a','alice','x','thesis',{'text':'x'*1_000_001})
    assert store.records('a','alice')==[]



def test_scenario_distinguishes_unrealized_pnl_from_cash_and_reconciles_equity():
    r=analytics.scenario([{'symbol':'LONG','market_value':100},{'symbol':'SHORT','market_value':-50}],-.2,0,20,.5,1.5)
    assert r['cash_balance']==20
    assert r['stressed_equity']==pytest.approx(60)
    assert r['equity_buffer_after_margin']==pytest.approx(-40)
    assert r['indicative_funding_gap']==pytest.approx(40)
