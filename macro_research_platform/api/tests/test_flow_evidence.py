from datetime import date
import pytest
from api.marketdata.flow_evidence import parse_form4,insider_summary,estimate_etf_flows


def xml(plan='0'):
    return f'''<ownershipDocument><aff10b5One>{plan}</aff10b5One><reportingOwner><reportingOwnerId><rptOwnerName>Test Person</rptOwnerName><rptOwnerCik>123</rptOwnerCik></reportingOwnerId><reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship></reportingOwner><nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Common</value></securityTitle><transactionDate><value>2026-10-30</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>100</value></transactionShares><transactionPricePerShare><value>10</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts><postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction></nonDerivativeTable><footnotes><footnote id="F1">No transactions pursuant to 10b5-1.</footnote></footnotes></ownershipDocument>'''


def test_checkbox_is_not_inferred_from_a_plan_mention_and_missing_is_unknown():
    row=parse_form4(xml(),'acc','2026-11-02','https://www.sec.gov/test')[0]
    assert row['plan_10b5_1'] is False and row['value']==1000 and row['owner_cik']=='123'
    assert parse_form4(xml('1'),'a','2026-11-02','url')[0]['plan_10b5_1'] is True
    assert parse_form4(xml(''),'a','2026-11-02','url')[0]['plan_10b5_1'] is None


def test_summary_excludes_amendments_duplicate_compensation_and_wrong_direction():
    r=parse_form4(xml(),'acc','2026-11-02','url')[0]
    rows=[r,dict(r),{**r,'code':'A'},{**r,'direction':'sell'},{**r,'owner_cik':'456','insider':'Second Owner','accession':'second'}]
    s=insider_summary({'transactions':rows},today=date(2026,11,2))
    assert s['purchase_usd_known']==2000 and s['distinct_reporting_buyers']==2 and s['multiple_buyers']
    assert s['excluded_rows']==3


def test_future_and_unknown_value_do_not_become_observed_cash():
    r=parse_form4(xml(),'acc','2026-11-02','url')[0]
    s=insider_summary({'transactions':[{**r,'value':None},{**r,'date':'2027-01-01'}],'failed_filings':[{}]},today=date(2026,11,2))
    assert s['purchase_usd_known']==0 and s['missing_value_transactions']==1 and s['coverage']=='partial'


def test_etf_flow_sums_interval_prices_not_endpoint_revaluation():
    f=estimate_etf_flows([('2026-10-23',[100,10]),('2026-10-26',[110,11]),('2026-10-30',[120,12])],today=date(2026,11,2))
    assert f['week_usd']==pytest.approx(10*11+10*12)
    assert f['week_days']==7


def test_etf_short_history_split_and_stale_data_remain_unquantified():
    assert 'week_usd' not in estimate_etf_flows([('2026-10-29',[100,10]),('2026-10-30',[110,11])],today=date(2026,11,2))
    split=estimate_etf_flows([('2026-10-23',[100,10]),('2026-10-30',[200,5])],today=date(2026,11,2))
    assert split['quality']=='review_required' and split['week_usd'] is None
    assert 'week_usd' not in estimate_etf_flows([('2026-10-01',[100,10]),('2026-10-02',[110,11])],today=date(2026,11,2))


def test_new_13f_dollars_are_not_scaled_based_on_small_portfolio_size(monkeypatch):
    from api.marketdata import extras,core
    core._cache.clear()
    sub={'name':'Test manager','filings':{'recent':{'form':['13F-HR','13F-HR'],'accessionNumber':['now','old'],'reportDate':['2022-12-31','2022-09-30'],'filingDate':['2023-02-01','2022-11-01']}}}
    class Response:
        def json(self):return sub
    monkeypatch.setattr(extras,'_sec_get',lambda u:Response())
    monkeypatch.setattr(extras,'_info_table',lambda c,a:[{'issuer':'Test','class':'Common','cusip':str(i),'value':1000,'shares':100,'put_call':None} for i in range(6)])
    monkeypatch.setattr(extras,'_cusip_tickers',lambda c:{k:'TEST' for k in c})
    monkeypatch.setattr(extras,'_sec_names',lambda:{})
    r=extras.thirteen_f('123')
    assert r['total_value']==6000
    core._cache.clear()


def test_amendment_affected_original_is_not_counted_as_unreconciled_cash():
    r=parse_form4(xml(),'original','2026-11-02','url')[0]
    s=insider_summary({'transactions':[r,{**r,'form':'4/A','amendment':True,'value':10}]},today=date(2026,11,2))
    assert s['purchase_transactions']==0 and s['amendment_affected_groups']==1 and s['excluded_rows']==2


def test_future_amendment_does_not_suppress_current_disclosure():
    r=parse_form4(xml(),'original','2026-11-02','url')[0]
    s=insider_summary({'transactions':[r,{**r,'form':'4/A','amendment':True,'filed':'2026-11-03'}]},today=date(2026,11,2))
    assert s['purchase_transactions']==1 and s['amendment_affected_groups']==0
