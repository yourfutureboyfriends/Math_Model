from dataclasses import replace
import pytest
from api.marketdata.dcf_scenarios import FCFModel,RiskAssumptions,Scenario,cost_of_capital,regional_risk,value_fcf,reverse_dcf,scenario_matrix,operating_scenarios,solve_bounded
from api.marketdata import dcf
from api.tests.test_dcf_refinements import base


def model():return FCFModel(100.,.10,9,.025,10.,250.,net_debt=50.)


def test_country_and_governance_are_not_scaled_by_beta():
    r=cost_of_capital(RiskAssumptions(risk_free=.04,beta=2,market_risk_premium=.05,country_risk_premium=.03,governance_risk_premium=.02,equity_weight=.8,debt_weight=.2,cost_of_debt=.06,tax_rate=.25))
    assert r['cost_of_equity']==pytest.approx(.19) and r['wacc']==pytest.approx(.8*.19+.2*.045)
    legacy=dcf.wacc(base(beta=2,erp=.08,country_risk_premium=.03,governance_risk_premium=.02,risk_free=.04))
    assert legacy['cost_of_equity']==pytest.approx(.19) and legacy['market_risk_premium']==pytest.approx(.05)


def test_regional_profiles_are_explicit_and_replace_not_stack():
    original=RiskAssumptions(country_risk_premium=.01)
    west,_=regional_risk(original,'western_tech');china,_=regional_risk(original,'china_structural',.05)
    assert cost_of_capital(west)['wacc']==pytest.approx(.085)
    assert cost_of_capital(china)['wacc']==pytest.approx(.135)
    assert value_fcf(model(),.135)['per_share']<value_fcf(model(),.085)['per_share']
    assert original.country_risk_premium==.01


@pytest.mark.parametrize('mid_year',[False,True])
def test_reverse_recovers_price_generated_growth_wacc_and_terminal(mid_year):
    m=replace(model(),mid_year=mid_year);v=value_fcf(m,.095);m=replace(m,market_price=v['per_share'])
    r=reverse_dcf(m,.095)
    for key,expected in [('implied_fcf_cagr',m.growth),('implied_wacc',.095),('implied_terminal_growth',m.terminal_growth)]:
        assert r[key]['status']=='solved' and r[key]['value']==pytest.approx(expected,abs=1e-8)
        assert abs(r[key]['residual'])<1e-6


def test_probabilities_and_bad_scenarios_do_not_create_biased_expected_value():
    r=scenario_matrix(model(),RiskAssumptions())
    rows=r['matrix'].to_dict('records')
    assert rows[0]['per_share']<rows[1]['per_share']<rows[2]['per_share']
    assert r['expected_value']==pytest.approx(sum(x['probability']*x['per_share'] for x in rows))
    with pytest.raises(ValueError):scenario_matrix(model(),RiskAssumptions(),[Scenario('Base',.8)])
    bad=scenario_matrix(model(),RiskAssumptions(),[Scenario('Bear',.25,wacc_shift=-.08),Scenario('Base',.75)])
    assert bad['expected_value'] is None and not bad['complete_probability_mass']


def test_root_solver_reports_no_solution_and_multiple_roots():
    assert solve_bounded(lambda x:x*x+1,-1,1)['status']=='no_root_in_bounds'
    assert solve_bounded(lambda x:(x-.2)*(x-.8),0,1)['status']=='multiple_roots'
    with pytest.raises(ValueError):value_fcf(model(),model().terminal_growth)
    with pytest.raises(ValueError):value_fcf(replace(model(),base_fcf=-100),.1)


def test_operating_matrix_reconciles_base_and_does_not_mutate():
    inp=base();before=dict(inp);r=operating_scenarios(inp)
    assert inp==before
    assert r['matrix'][1]['per_share']==pytest.approx(dcf.value(inp)['per_share'])
    assert r['expected_value']==pytest.approx(sum(x['weighted_value'] for x in r['matrix']))
    assert r['matrix'][0]['per_share']<r['matrix'][1]['per_share']<r['matrix'][2]['per_share']


def test_fixed_cashflow_reverse_does_not_recalculate_reinvestment(monkeypatch):
    inp=base();v=dcf.value(inp,discount=.11);inp['price']=v['per_share'];calls=[]
    real=dcf.value
    def counted(*args,**kwargs):calls.append(kwargs);return real(*args,**kwargs)
    monkeypatch.setattr(dcf,'value',counted)
    assert dcf.implied_discount(inp,discount=.11)==pytest.approx(.11,abs=1e-8)
    assert len(calls)==1


def test_invalid_weighted_mass_and_regional_override():
    with pytest.raises(ValueError):operating_scenarios(base(),probabilities={'bear':.2,'base':.3,'bull':.2})
    report=operating_scenarios(base(),profile='china_structural')
    assert report['risk']['governance_risk_premium']==pytest.approx(.02)
    assert report['risk']['country_risk_premium']==pytest.approx(.03)
