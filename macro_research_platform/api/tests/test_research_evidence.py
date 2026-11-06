import copy
import json
from datetime import datetime,timezone
import pytest
from api.workflows import store,evidence,intelligence,analytics,securities
from api.tests.test_connected_workflows import database,snapshot


def test_observation_envelope_is_server_generated_and_old_versions_remain_intact(database,monkeypatch):
    monkeypatch.setattr(store,'now',lambda:'2026-01-02T00:00:00+00:00')
    p={'symbol':'A','kind':'earnings','observedAt':'1900-01-01','payload':{'source':'Test','value':1},'_evidence':{'raw_sha256':'forged'}}
    a=store.put('f','u','r','observation',p)
    assert a['payload']['_evidence']['raw_sha256']==evidence.digest(p['payload'])
    assert store.observations_at('f','u','2026-01-01T00:00:00Z')==[]
    monkeypatch.setattr(store,'now',lambda:'2026-01-03T00:00:00+00:00')
    store.put('f','u','r','observation',{**p,'payload':{'value':2}},1)
    assert store.observations_at('f','u','2026-01-02T12:00:00Z')[0]['payload']['payload']['value']==1
    assert store.observations_at('f','other','2027-01-01T00:00:00Z')==[]
    assert len(store.history('f','u','r'))==2


def test_projection_replay_requires_matching_immutable_payload(database):
    saved=store.put('f','u','v','observation',snapshot())['payload']
    result=evidence.replay(saved)
    assert result['reconciled'] and result['difference']==pytest.approx(0)
    saved['payload']['primary']['valuation']['per_share']+=1
    with pytest.raises(ValueError,match='checksum'):evidence.replay(saved)


def test_shapley_attribution_is_symmetric_and_reconciles():
    a=snapshot();b=snapshot(revenue=120,margin=.3,discount=.8,units=.09)
    forward=analytics.valuation_bridge(a,b,'shapley');reverse=analytics.valuation_bridge(b,a,'shapley')
    assert sum(r['contribution'] for r in forward['contributions'])==pytest.approx(forward['change'])
    for x,y in zip(forward['contributions'],reverse['contributions']):assert x['contribution']==pytest.approx(-y['contribution'])
    assert all(r['value_after'] is None for r in forward['contributions'])


def test_comparison_refuses_mismatched_units_and_exposes_discrepancy():
    a={'field':'sales','period_end':'2025-12-31','currency':'USD','units':'millions','accounting_basis':'GAAP','observed_at':'2026-02-01','value':100,'source':'Issuer','source_url':'https://issuer/report'}
    b={**a,'value':110,'source':'Vendor','source_url':'https://vendor/report'}
    assert evidence.compare_fields(a,b)['status']=='discrepancy'
    assert not evidence.compare_fields(a,b)['independence_verified']
    assert evidence.compare_fields(a,{**b,'units':'thousands'})['status']=='incomparable'
    assert evidence.compare_fields({**a,'value':0},{**b,'value':0})['status']=='within_tolerance'


def test_estimate_revisions_need_actual_fiscal_end_and_never_match_rollover():
    def row(end,value,stamp):return {'recorded_at':stamp,'payload':{'symbol':'A','kind':'earnings','payload':{'currency':'USD','estimates':{'eps':[{'period':'0q','period_end':end,'avg':value}]}}}}
    r=intelligence.estimate_revisions([row('2026-03-31',1,'2026-01-01'),row('2026-03-31',2,'2026-01-02'),row('2026-06-30',3,'2026-01-03'),row(None,4,'2026-01-04')])
    assert len(r['changes'])==1 and r['changes'][0]['change']==1 and r['unmatched_period_rows']==1


def test_dated_identity_links_do_not_overlap_and_group_real_exposures(database):
    with securities.connect() as c:
        for symbol in ['A','B']:c.execute('INSERT INTO workflow_securities VALUES(?,?,?,?,?)',(symbol,'Test',symbol,'{}',store.now()))
    for symbol in ['A','B']:securities.link_identity(symbol,'issuer','class','2020-01-01',None,'https://issuer/report','admin')
    with pytest.raises(store.Conflict):securities.link_identity('A','other','class','2021-01-01',None,'https://issuer/report','admin')
    result=securities.group_exposures([{'symbol':'A','weight_pct':.2},{'symbol':'B','weight_pct':.3},{'symbol':'OTHER','weight_pct':.5}],'2026-01-01')
    assert result['issuers'][0]['known_direct_weight']==pytest.approx(.5) and result['unmapped_symbols']==['OTHER']


def test_inbox_review_is_tenant_scoped_and_optimistic(database):
    store.put('f','u','r','observation',{'payload':{}},event={'summary':'Change'})
    event=store.inbox('f','u')[0]
    assert store.inbox('f','other')==[]
    store.event_review('f','u',event['id'],'reviewed','unreviewed')
    with pytest.raises(store.Conflict):store.event_review('f','u',event['id'],'dismissed','unreviewed')
    with pytest.raises(ValueError):store.event_review('other','u',event['id'],'reviewed','unreviewed')


def test_value_validation_excludes_future_and_lookahead_and_groups_currency():
    r={'issued_at':'2020-01-01T00:00:00Z','actual_at':'2021-01-01T00:00:00Z','trained_through':'2019-12-31T00:00:00Z','forecast':10,'actual':9,'benchmark':8,'currency':'USD','source_url':'https://issuer/report'}
    result=intelligence.validate_values([r,{**r,'trained_through':'2022-01-01T00:00:00Z'},{**r,'actual_at':'2099-01-01T00:00:00Z'}])
    assert result['accepted']==1 and len(result['rejected'])==2 and result['groups'][0]['mae']==1


def test_execution_uses_volume_weighted_prints_and_preserves_unknown_fees():
    r={'side':'BUY','quantity':100,'fill_price':11,'arrival_price':10,'currency':'USD','base_currency':'GBP','fill_at':'2020-01-01','decision_at':'2020-01-01','source_url':'https://broker/report','trades':[{'price':10,'volume':1},{'price':12,'volume':3}]}
    result=intelligence.execution_cost(r)
    assert result['vwap']==11.5 and result['shortfall_local']==100 and result['total_cost_base'] is None
    result=intelligence.execution_cost({**r,'fees':1,'fx_to_base':.8})
    assert result['total_cost_base']==pytest.approx(80.8)


def test_historical_tca_fx_never_uses_later_quotes(monkeypatch):
    from api.handlers import portfolio_analytics as p
    from api import market_bars
    monkeypatch.setattr(market_bars,'bars',lambda *args:{'currency':'GBp'})
    monkeypatch.setattr(p,'_bars',lambda *args:{'2020-01-02':{'c':.8},'2026-01-01':{'c':.5}})
    ccy,rate,day=p._usd_per_unit_on('TEST.L','2020-01-03')
    assert ccy=='GBp' and rate==pytest.approx(1/.8/100) and day=='2020-01-02'
    assert p._usd_per_unit_on('TEST.L','2020-02-01')[1] is None
    monkeypatch.setattr(market_bars,'bars',lambda *args:{})
    assert p._usd_per_unit_on('TEST.L','2020-01-03')[1] is None


from api.tests.test_funds import env


def test_evidence_http_routes_enforce_cutoffs_and_replay_scope(env):
    client=env('analyst');other=env('pm')
    captured=client.put('/api/v1/workflows/research/fcff-test',json={'kind':'observation','payload':snapshot(),'expected_version':0})
    assert captured.status_code==200,captured.text
    assert captured.json()['payload']['_evidence']['raw_sha256']
    result=client.post('/api/v1/workflows/replay',json={'record_id':'fcff-test'})
    assert result.status_code==200 and result.json()['reconciled']
    assert other.post('/api/v1/workflows/replay',json={'record_id':'fcff-test'}).status_code==404
    assert client.get('/api/v1/workflows/observations',params={'available_at':'1900-01-01T00:00:00Z'}).json()['records']==[]
    assert client.get('/api/v1/workflows/observations',params={'available_at':'2020-01-01'}).status_code==422


def test_event_http_validates_dates_and_deduplicates_without_cross_tenant_reads(env):
    client=env('analyst')
    body={'symbol':'MSFT','entity_type':'port','entity_id':'TEST','start':'2020-01-01','summary':'Reported sample event','relation':'User documented supplier relationship','source_url':'https://example.com/report','metric':'other'}
    assert client.post('/api/v1/workflows/tracker-evidence',json=body).status_code==422
    body['start']='2020-01-01T00:00:00Z'
    assert client.post('/api/v1/workflows/tracker-evidence',json={**body,'start':'2999-01-01T00:00:00Z'}).status_code==422
    created=client.post('/api/v1/workflows/tracker-evidence',json=body)
    assert created.status_code==200,created.text
    assert client.post('/api/v1/workflows/tracker-evidence',json=body).status_code==409
    assert env('pm').get('/api/v1/workflows/research').json()['events']==[]


def test_execution_http_rejects_future_fx_and_outside_window_prints(env):
    c=env('analyst')
    body={'side':'BUY','quantity':10,'fill_price':10,'currency':'USD','base_currency':'GBP','decision_at':'2020-01-01T10:00:00Z','fill_at':'2020-01-01T11:00:00Z','window_start':'2020-01-01T10:00:00Z','window_end':'2020-01-01T12:00:00Z','source_url':'https://broker/report','fx_to_base':.8,'fx_at':'2021-01-01T00:00:00Z'}
    assert c.post('/api/v1/workflows/execution-evidence',json=body).status_code==422
    body['fx_at']='2020-01-01T10:59:00Z'
    body['trades']=[{'at':'2020-01-02T00:00:00Z','price':10,'volume':1}]
    assert c.post('/api/v1/workflows/execution-evidence',json=body).status_code==422
    body['trades'][0]['at']='2020-01-01T10:30:00Z'
    result=c.post('/api/v1/workflows/execution-evidence',json=body)
    assert result.status_code==200,result.text
    assert result.json()['vwap']==10 and result.json()['total_cost_base'] is None


def test_vessel_events_are_bounded_and_source_labelled(monkeypatch):
    from api.marketdata import tracking
    import requests
    monkeypatch.setenv('GFW_API_TOKEN','test-not-a-real-key')
    monkeypatch.setattr(tracking,'_cached',lambda key,ttl,fn:fn())
    monkeypatch.setattr(tracking,'vessel_info',lambda q:{'vessel_ids':['verified-id']})
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'entries':[{'id':'event','start':'2020-01-01','type':'GAP'}],'nextOffset':100}
    def get(url,**kwargs):calls.append(kwargs);return Response()
    monkeypatch.setattr(requests,'get',get)
    result=tracking.vessel_events('123456789','ais_gap',90)
    assert result['has_more'] and calls[0]['params']['limit']==100 and calls[0]['params']['vessels[0]']=='verified-id'
    assert 'do not establish' in result['note']


def test_capture_coverage_is_account_scoped_and_counts_unknown_metadata(env):
    c=env('analyst')
    c.put('/api/v1/workflows/research/unknown',json={'kind':'observation','payload':{'payload':{}}})
    result=c.get('/api/v1/workflows/capture-coverage')
    assert result.status_code==200 and result.json()['captures']==1
    assert result.json()['quality_flags']['publisher_availability_unknown']==1
    assert env('pm').get('/api/v1/workflows/capture-coverage').json()['captures']==0


def test_corporate_reference_events_are_append_only_and_do_not_change_positions(database):
    with securities.connect() as c:c.execute('INSERT INTO workflow_securities VALUES(?,?,?,?,?)',('A','Test','A','{}',store.now()))
    event=securities.corporate_event('A','split','2026-01-01','https://issuer/report','admin',2)
    assert event['ratio']==2 and len(securities.corporate_history('A'))==1
    with pytest.raises(store.Conflict):securities.corporate_event('A','split','2026-01-01','https://issuer/report','admin',3)
    with pytest.raises(ValueError):securities.corporate_event('A','adr_ratio','2026-01-02','https://issuer/report','admin',0)
