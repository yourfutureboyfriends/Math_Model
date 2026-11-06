"""Hand-calculated screening cases and fund isolation, without vendor calls."""
from datetime import date
import pytest
from api.pe import opportunities as O

TODAY=date.today().isoformat()
def company(**changes):
    return dict(revenue=100,ebitda=20,pre_money=80,investment=20,growth=0,exit_margin=.2,exit_multiple=10,exit_net_debt=0,dilution=0,years=5,hurdle=.1,**changes)

def property_values():
    return dict(purchase=100,acquisition_costs=5,works=10,soft_costs=0,contingency=0,ltv=.5,interest=.1,sale_cost=0,years=5,hurdle=.1,annual_rent=12,vacancy=0,opex=2,maintenance=1,rent_growth=0,exit_yield=.1)

def test_primary_equity_ownership_and_return():
    r=O.analyse('company',company(),'growth',TODAY)
    assert r['metrics']['entry_ownership']==pytest.approx(.2)
    assert r['cases'][1]['exit_equity_proceeds']==pytest.approx(40)
    assert r['metrics']['irr']==pytest.approx(2**.2-1)
    assert r['cases'][0]['irr']<r['cases'][1]['irr']<r['cases'][2]['irr']

def test_dilution_and_net_debt_reduce_proceeds():
    v=company();v.update(dilution=.25,exit_net_debt=100)
    assert O.analyse('company',v,'growth',TODAY)['cases'][1]['exit_equity_proceeds']==pytest.approx(15)
    v['exit_net_debt']=1000
    assert O.analyse('company',v,'growth',TODAY)['metrics']['irr']==-1

def test_missing_is_not_zero_and_nonfinite_rejected():
    r=O.analyse('company',{},'growth',TODAY)
    assert r['metrics']=={} and 'investment' in r['missing']
    for values in ({'investment':float('nan')},{'purchase':True},{'years':1.5},{'ltv':1.1}):
        with pytest.raises(ValueError):O.analyse('property',values,'residential',TODAY)

def test_fund_net_multiples_and_listed_discount():
    r=O.analyse('fund',dict(paid_in=100,distributed=60,nav=90,price=8,nav_per_share=10,nav_haircut=.2,unfunded=50,liquid_reserve=25),'listed',TODAY,TODAY)
    m=r['metrics'];assert m['dpi']==.6 and m['rvpi']==.9 and m['tvpi']==1.5
    assert m['discount']==pytest.approx(.2) and m['stressed_discount']==pytest.approx(0) and m['call_coverage']==.5
    assert 'irr' not in m

def test_zero_paid_in_does_not_create_performance_and_private_has_no_discount():
    r=O.analyse('fund',{'paid_in':0,'distributed':10,'nav':20,'price':8,'nav_per_share':10},'private',TODAY)
    assert 'tvpi' not in r['metrics'] and 'discount' not in r['metrics']

def test_rental_cashflow_and_balloon_are_reconciled():
    r=O.analyse('property',property_values(),'residential',TODAY)
    m=r['metrics'];assert m['total_cost']==115 and m['loan']==50 and m['initial_equity']==65
    assert m['noi']==10 and m['dscr']==2 and m['cash_yield']==pytest.approx(4/65)
    assert [x['equity_cashflow'] for x in r['cashflows']]==[-65,4,4,4,4,54]
    assert m['moic']==pytest.approx(70/65) and m['profit']==5

def test_cash_deficits_count_as_additional_equity():
    v=property_values();v.update(annual_rent=3,opex=2)
    r=O.analyse('property',v,'commercial',TODAY)
    assert r['cashflows'][1]['equity_cashflow']==-5
    assert r['metrics']['moic']==0 and r['metrics']['irr'] is None

def test_development_residual_separate_from_annual_hurdle():
    v=property_values();v.update(gdv=200,profit_target=.25)
    r=O.analyse('property',v,'development',TODAY)
    # Unlevered residual = 200/1.25 - 10 works - 5 fixed acquisition costs.
    assert r['metrics']['residual_land_value']==145
    assert r['metrics']['profit']==60 # 200 less total cost 115 and 25 interest.
    assert r['cases'][0]['irr']<r['cases'][1]['irr']

def test_opportunity_update_and_per_fund_storage(tmp_path,monkeypatch):
    from api import funds
    monkeypatch.setattr(funds,'db_path',lambda:tmp_path/f'{funds.CURRENT.get()}.db')
    body=dict(kind='company',name='Research target',values={},subtype='growth',stage='Research',as_of=TODAY,checks=[])
    saved=O.save('analyst',body)
    assert saved['analysis']['status']=='Incomplete inputs'
    changed=O.save('pm',{**body,'name':'Reviewed target'},saved['id'])
    assert len(O.list_opportunities('company'))==1 and changed['owner']=='pm'
    token=funds.CURRENT.set('other')
    try:assert O.list_opportunities('company')==[]
    finally:funds.CURRENT.reset(token)
    with pytest.raises(ValueError):O.save('pm',{**body,'source_url':'javascript:alert(1)'})
    with pytest.raises(LookupError):O.save('pm',body,9999)
