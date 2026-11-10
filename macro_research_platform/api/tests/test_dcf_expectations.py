import pytest
from api.marketdata import dcf
from api.marketdata.core import NotFound
from api.marketdata.dcf_expectations import apply_risk_basis, expectations, reprice_rate_shift
from api.tests.test_dcf_refinements import base


def test_risk_basis_preserves_currency_and_does_not_double_count_country():
    inp=base(currency='EUR', risk_free=.025, country_risk_premium=.01, erp_implied=.035)
    data,erp=apply_risk_basis(inp)
    assert erp==pytest.approx(.06)
    assert data['risk_free']==.025 and inp['erp']==.045
    assert apply_risk_basis(inp,'market_implied')[1]==pytest.approx(.045)
    manual,total=apply_risk_basis(inp,explicit_erp=.07)
    assert total==.07 and manual['erp_is_total_override']
    with pytest.raises(NotFound):apply_risk_basis(inp,explicit_erp=float('nan'))


@pytest.mark.parametrize('mid_year',[True,False])
@pytest.mark.parametrize('method',['three_stage','two_stage'])
def test_parallel_rate_shift_reconciles_and_is_monotonic(mid_year,method):
    v=dcf.value(base(),mid_year=mid_year,method=method)
    assert reprice_rate_shift(v,0)==pytest.approx(v['per_share'])
    assert reprice_rate_shift(v,.02)<reprice_rate_shift(v,.01)<v['per_share']


@pytest.mark.parametrize('extra',[{'growth_y1':.15},{'ebit':40e9,'target_margin_default':.20,'margin_fade_years':3}])
def test_grid_center_reconciles_to_selected_case_without_mutating(extra):
    inp=base(**extra);before=dict(inp);v=dcf.value(inp)
    result=expectations(inp,v)
    assert result['grid'][4]['per_share']==pytest.approx(v['per_share'])
    assert inp==before
    assert len(result['rate_stress'])==2


def test_reverse_recovers_growth_at_own_model_price():
    inp=base();v=dcf.value(inp);inp['price']=v['per_share']
    result=expectations(inp,v)
    assert result['implied_growth']==pytest.approx(.08,abs=1e-5)
    assert result['implied_margin']==pytest.approx(.2,abs=1e-5)
