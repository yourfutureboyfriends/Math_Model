import pytest
from scripts.audit_dcf_matrix import select_rows,evaluate
from api.tests.test_dcf_refinements import base


def row(symbol,name,cap):return {'symbol':symbol,'name':name,'country':'US','sector':'Industrials','mcap_usd':cap}


def test_selection_uses_distinct_issuers_and_size_diversity_without_value_targets():
    rows=[row('A','Example Inc',40e9),row('A2','Example Corporation',30e9),row('B','Other Ltd',20e9),row('C','Medium Co',5e9),row('D','Smaller plc',1e9)]
    chosen=select_rows(rows)
    assert {r['symbol'] for r in chosen}=={'A','C','D'}
    assert {r['size'] for r in chosen}=={'small','mid','large'}
    assert len(select_rows(rows[:1]))==1


def test_missing_observation_is_not_a_successful_valuation():
    r=evaluate({'selection':row('A','Example',1e9),'error':'Provider unavailable'})
    assert r['status']=='data_unavailable' and not r['checks']


def test_snapshot_replay_checks_mechanics_and_preserves_source_limits():
    inp=base(industry='Software',country='United States')
    r=evaluate({'selection':row('A','Example',1e9),'inputs':inp,'info':{},'dividends':[],'fx_usd_per':{'USD':1},'fetched_at':'2026-10-31'})
    assert r['status']=='research_required'
    assert all(r['checks'].values())
    assert r['expectations']['risk_basis']=='normalized'
    assert inp['erp']==.045


def test_unconfigured_long_run_currency_is_explicitly_review_required():
    from api.marketdata import dcf
    s=dcf.model_suitability(base(currency='ARS',risk_free=.33),'fcff')
    assert s['status']=='review_required'
    assert any('long-run nominal-growth ceiling for ARS' in r for r in s['reasons'])
    assert dcf.default_terminal_growth(base(currency='USD',risk_free=.1))==.04


def test_rate_limited_batch_stops_submitting_and_is_resumable(tmp_path):
    import json
    from scripts.audit_dcf_matrix import fetch_checkpoints,provider_limited
    calls=[]
    def limited(r):
        calls.append(r['symbol']);return {'selection':r,'error':'Upstream: Yahoo is rate-limiting this server'}
    rows=[row(str(i),f'Issuer {i}',1e9) for i in range(10)]
    fetch_checkpoints(rows,tmp_path,workers=1,fetcher=limited)
    assert calls==['0']
    saved=[json.loads(p.read_text()) for p in tmp_path.glob('*.json')]
    assert len(saved)==10 and all(provider_limited(r) for r in saved)
    assert evaluate(saved[0])['status']=='provider_deferred'


def test_pre_revenue_company_is_not_misidentified_as_non_equity():
    from api.marketdata import dcf
    from api.marketdata.core import NotFound
    with pytest.raises(NotFound,match='pre-revenue business'):
        dcf.value(base(revenue=None,ebit=None,industry='Biotechnology'))


def test_request_budget_spreads_across_countries():
    from scripts.audit_dcf_matrix import balanced_rows
    rows=[{**row(f'{country}{i}',f'{country} issuer {i}',1e9),'country':country} for country in ('US','DE','JP') for i in range(3)]
    ordered=balanced_rows(rows)
    assert {r['country'] for r in ordered[:3]}=={'US','DE','JP'}
    assert len({r['symbol'] for r in ordered})==9


def test_report_does_not_count_deferred_requests_as_valuations(tmp_path):
    import json
    from scripts.audit_dcf_matrix import report
    rows=[row('A','First',1e9),row('B','Second',2e9)]
    results=[evaluate({'selection':r,'error':'Provider cooldown: deferred'}) for r in rows]
    report(tmp_path,['US'],[{'country':'US','sector':'Industrials','rows':rows}],rows,results)
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['valued_companies']==0 and summary['valued_markets']==0
    assert summary['coverage_counts']['no_valuation']==11
    assert (tmp_path/'results.csv').exists()


def test_audit_preserves_application_dividend_fallback_and_marks_missing_history():
    inp=base(revenue=None,ebit=None,industry='Biotechnology')
    r=evaluate({'selection':row('A','Example',1e9),'inputs':inp,'info':{'dividendYield':2.0},'dividends':[],'fx_usd_per':{'USD':1}})
    assert r['model']=='ddm' and r['value']>0
    assert r['status']=='research_required'
    assert any('Dividend history was not captured' in reason for reason in r['research_status']['reasons'])


def test_non_lender_financial_preserves_application_cashflow_fallback():
    inp=base(is_financial=True,is_bank_like=False,industry='Capital Markets')
    r=evaluate({'selection':row('A','Example',1e9),'inputs':inp,'info':{},'dividends':[],'fx_usd_per':{'USD':1}})
    assert r['model']=='fcff' and all(r['checks'].values())


def test_prior_snapshot_does_not_hide_a_current_currency_conflict():
    inp=base(industry='Software')
    r=evaluate({'selection':row('A','Example',1e9),'inputs':inp,'info':{},'dividends':[],'fx_usd_per':{'USD':1},'snapshot_provenance':'prior_snapshot','fresh_fetch_error':'Statement currency USD disagrees with financial currency EUR'})
    assert r['snapshot_provenance']=='prior_snapshot' and r['status']=='research_required'
    assert any('current observation is not verified' in reason for reason in r['research_status']['reasons'])
