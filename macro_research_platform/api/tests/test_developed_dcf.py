"""Deterministic market coverage checks; these do not certify live company data."""
import math
import pytest
from api.marketdata import dcf
from api.marketdata.developed_markets import COUNTRIES,context,canonical_country
from api.providers import damodaran
from api.tests.test_dcf_refinements import base

@pytest.mark.parametrize('country,currency',[ (c,p[0]) for c,p in COUNTRIES.items()])
def test_developed_currency_and_sector_matrix(country,currency):
    assert currency in dcf.LR_NOMINAL_GROWTH
    assert currency in dcf.RF_SERIES or currency in ('USD','HKD','SGD')
    for cyclical in (False,True):
        inp=base(country=country,currency=currency,price_currency=currency,cyclical=cyclical,
                 country_risk_premium=.012,erp=.057,governance_risk_premium=.004)
        result=dcf.value(inp)
        assert math.isfinite(result['per_share'])
        ctx=context(inp)
        assert ctx['covered_developed_market'] and ctx['registry_currency']==currency
        assert dcf.wacc(inp)['cost_of_equity']==pytest.approx(.045+.045+.012+.004)


def test_exposure_risk_uses_full_operating_premiums(monkeypatch):
    monkeypatch.setattr(damodaran,'country_risk',lambda c:{'crp':{'United States':.002,'Poland':.02}[c],'rating':'A'})
    result=dcf.exposure_risk(base(),{'United States':.4,'Poland':.6})
    assert result['premium']==pytest.approx(.0128)
    with pytest.raises(Exception):dcf.exposure_risk(base(),{'Poland':.4})


def test_developed_aliases_and_missing_data_are_visible():
    assert canonical_country('Korea, Republic of')=='South Korea'
    ctx=context(base(country='Singapore',country_risk_available=False))
    assert any('unavailable' in n for n in ctx['notes'])
    assert damodaran._region_files('South Korea')['region']=='Global'


def test_tax_aliases_and_current_rows_win_over_historical_appendix(monkeypatch,tmp_path):
    import pandas as pd
    rows=[['Date updated:',pd.Timestamp('2026-01-05'),None],['Country','Corporate Tax Rate','Tax Rate Accounting for Global Minimum Tax'],
          ['United States of America',.2563,.2563],['United Kingdom of Great Britain and Northern Ireland',.25,.25],
          ['Republic of Korea',.264,.264],['China, Hong Kong Special Administrative Region',.165,.165],
          ['United States of America',.35,.35]]
    monkeypatch.setattr(damodaran,'_download',lambda *a:tmp_path/'fixture.xls')
    monkeypatch.setattr(pd,'read_excel',lambda *a,**kw:pd.DataFrame(rows))
    monkeypatch.setattr(damodaran,'_mem',{})
    for country,rate in [('United States',.2563),('United Kingdom',.25),('South Korea',.264),('Hong Kong',.165)]:
        result=damodaran.country_tax(country)
        assert result['available'] and result['rate']==pytest.approx(rate)
        assert result['as_of']=='2026-01-05'
