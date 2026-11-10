"""Market comparisons preserve the existing engines and expose stress assumptions."""
import pytest

from api.marketdata import dcf
from api.tests.test_dcf_refinements import base


def test_market_base_matches_existing_engine_and_does_not_mutate_inputs():
    inp = base(erp_implied=0.045, country_risk_premium=0.0)
    before = dict(inp)
    views = dcf.market_views(inp)
    assert inp == before
    assert views['current_market']['scenarios']['base']['per_share'] == pytest.approx(dcf.value(inp)['per_share'])
    assert views['fundamental']['scenarios']['base']['per_share'] < views['current_market']['scenarios']['base']['per_share']
    assert views['current_market']['scenarios']['recession']['per_share'] < views['current_market']['scenarios']['base']['per_share']


def test_manual_discount_does_not_collapse_comparison_lenses():
    views = dcf.market_views(base(), overrides={'discount': 0.15, 'erp': 0.09})
    assert views['fundamental']['scenarios']['base']['per_share'] != views['current_market']['scenarios']['base']['per_share']


def test_exposure_is_weighted_and_missing_countries_are_rejected(monkeypatch):
    from api.providers import damodaran
    monkeypatch.setattr(damodaran, 'country_risk', lambda c: {'crp': {'United States': 0.0, 'Brazil': 0.06}.get(c, 0.0), 'rating': 'A' if c in ('United States', 'Brazil') else None})
    inp = base()
    risk = dcf.exposure_risk(inp, {'United States': 0.75, 'Brazil': 0.25})
    assert risk['premium'] == pytest.approx(0.015)
    with pytest.raises(dcf.NotFound):
        dcf.exposure_risk(inp, {'Unknown': 1.0})
    for weights in ({'Brazil': 0.5}, {'Brazil': float('nan')}, {'Brazil': -1.0}, {}):
        with pytest.raises(dcf.NotFound):
            dcf.exposure_risk(inp, weights)


def test_financial_base_uses_reported_roe():
    inp = base(equity_book=50e9, net_income=8e9)
    views = dcf.market_views(inp, 'excess_return')
    result = views['current_market']['scenarios']['base']
    assert result['per_share'] == pytest.approx(dcf.value_financial(inp)['per_share'])
    assert result['assumptions']['roe_now'] == pytest.approx(0.16)


def test_cyclical_base_keeps_existing_margin_fade():
    inp = base(ebit=40e9, target_margin_default=0.20, margin_fade_years=3)
    views = dcf.market_views(inp)
    assert views['current_market']['scenarios']['base']['per_share'] == pytest.approx(dcf.value(inp)['per_share'])


def test_invalid_scenario_is_reported_without_losing_other_cases():
    views = dcf.market_views(base(), overrides={'terminal_growth': 0.09})
    assert views['fundamental']['scenarios']['base']['per_share'] is None
    assert 'error' in views['fundamental']['scenarios']['base']


def test_dividend_comparisons_reuse_dividend_engine(monkeypatch):
    monkeypatch.setattr(dcf, '_info', lambda _: {})
    monkeypatch.setattr(dcf, '_dividend_history', lambda _: [{'year': y, 'dps': 2.0 * 1.03 ** (y - 2020)} for y in range(2020, 2026)])
    inp = base(roe=0.15, payout_ratio=0.50)
    views = dcf.market_views(inp, 'ddm')
    assert views['current_market']['scenarios']['base']['per_share'] == pytest.approx(dcf.value_ddm(inp)['per_share'])
    assert views['current_market']['scenarios']['recession']['per_share'] < views['current_market']['scenarios']['base']['per_share']


@pytest.fixture
def valuation_client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.marketdata import core
    from api.routers import marketdata
    inp = base(industry='Software', net_capex_to_revenue=0.02)
    async def primary(*args, **kwargs):
        return {'inputs': inp, 'model': 'fcff', 'valuation': dcf.value(inp)}
    monkeypatch.setattr(marketdata, '_dcf_core', primary)
    monkeypatch.setattr(core, '_info', lambda _: {})
    monkeypatch.setattr(dcf, 'outlook', lambda *args, **kwargs: pytest.fail('Ineligible estimates must not generate convergence paths'))
    monkeypatch.setattr(dcf, '_realized_vol', lambda _: 0.20)
    app = FastAPI()
    app.include_router(marketdata.router)
    with TestClient(app) as client:
        yield client


def test_route_exposes_comparisons_and_retains_primary_valuation(valuation_client):
    response = valuation_client.get('/api/v1/mkt/dcf/TEST?normalized_erp=0.06')
    assert response.status_code == 200
    result = response.json()
    assert result['market_views']['fundamental']['mature_erp'] == 0.06
    assert result['valuation']['per_share'] > 0
    assert result['market_views']['suitability']['status'] == 'standard_model'
    assert result['research_status']['eligible'] is False  # no dated, reconciled cash-flow evidence in this fixture
    assert 'buy_price' not in result['uncertainty']
    assert result['outlook'] is None
    assert len(result['calculation_details']['forecast_steps']) == 2


def test_route_rejects_malformed_exposure_object(valuation_client):
    response = valuation_client.get('/api/v1/mkt/dcf/TEST', params={'country_weights': '[0.5,0.5]'})
    assert response.status_code == 422
