"""Period and currency integrity for the developed-market audit corrections."""
from types import SimpleNamespace

import pandas as pd
import pytest
import yfinance as yf

from api.marketdata import dcf
from api.tests.test_dcf_refinements import base


def test_half_years_are_not_summed_as_four_quarters(monkeypatch):
    dates = pd.to_datetime(['2026-06-30', '2025-12-31', '2025-06-30', '2024-12-31'])
    inc = pd.DataFrame([[100]*4, [20]*4], index=['Total Revenue', 'Operating Income'], columns=dates)
    monkeypatch.setattr(yf, 'Ticker', lambda _: SimpleNamespace(quarterly_income_stmt=inc))
    assert dcf._ttm_from_quarters('TEST') is None


def test_quarterly_cashflows_must_match_income_dates_and_zero_dna_is_valid(monkeypatch):
    dates = pd.to_datetime(['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30'])
    inc = pd.DataFrame([[100]*4, [20]*4], index=['Total Revenue', 'Operating Income'], columns=dates)
    cf = pd.DataFrame([[-10]*4, [0]*4], index=['Capital Expenditure', 'Depreciation And Amortization'], columns=dates)
    monkeypatch.setattr(yf, 'Ticker', lambda _: SimpleNamespace(quarterly_income_stmt=inc, quarterly_cashflow=cf))
    monkeypatch.setattr(dcf, '_statement_currency', lambda *a: 'USD')
    actual = dcf._ttm_from_quarters('TEST')
    assert actual['revenue'] == 400 and actual['capex'] == 40 and actual['dna'] == 0
    assert actual['as_of'] == '2026-06-30' and actual['currency'] == 'USD'
    cf.columns = dates - pd.Timedelta(days=15)
    assert dcf._ttm_from_quarters('TEST')['capex'] is None


def test_annual_fallback_keeps_reported_period_and_missing_cashflow(monkeypatch):
    date = pd.to_datetime(['2025-12-31'])
    inc = pd.DataFrame([[100], [12], [8]], index=['Total Revenue', 'Operating Income', 'Net Income'], columns=date)
    class Ticker:
        income_stmt = inc
        @property
        def cashflow(self):
            raise RuntimeError('provider unavailable')
    monkeypatch.setattr(yf, 'Ticker', lambda _: Ticker())
    monkeypatch.setattr(dcf, '_statement_currency', lambda *a: 'USD')
    actual = dcf._annual_from_statements('TEST')
    assert actual['ebit'] == 12 and actual['period'] == 'annual' and actual['capex'] is None
    assert actual['net_income'] == 8


def test_period_alignment_recomputes_forecast_drivers_without_changing_price():
    inp = base(margin=0.4, margin_history=[0.10, 0.12, 0.09], roic_history=[], invested_capital=50e9,
               margin_normalized=0.4, margin_fade_years=3, target_margin_default=0.4)
    statement = {'revenue': 80e9, 'ebit': 8e9, 'as_of': '2025-12-31', 'period': 'annual',
                 'capex': 6e9, 'dna': 2e9, 'currency': 'USD'}
    out = dcf.restate_statement_inputs(inp, statement)
    assert out['margin'] == 0.1 and out['target_margin_default'] == 0.1
    assert out['sales_to_capital'] == 1.6 and out['net_capex_to_revenue'] == 0.05
    assert out['price'] == inp['price'] and inp['margin_normalized'] == 0.4
    assert out['statement_currency_verified'] is True


def test_conflicting_statement_currency_is_rejected_before_valuation():
    statement = {'revenue': 6e9, 'ebit': 1e9, 'as_of': '2025-12-31', 'period': 'annual', 'currency': 'CNY'}
    with pytest.raises(dcf.NotFound, match='Statement currency CNY'):
        dcf.restate_statement_inputs(base(currency='USD'), statement)


def test_review_flags_follow_accounting_and_data_not_market_price():
    inp = base(industry='Asset Management')
    assert dcf.model_suitability(inp, 'excess_return')['status'] == 'review_required'
    assert dcf.model_suitability(base(industry='Software', net_capex_to_revenue=0.03), 'fcff')['status'] == 'standard_model'
    assert dcf.model_suitability(base(industry='Real Estate Services'), 'fcff')['status'] == 'review_required'


def test_sustainable_growth_ceiling_avoids_high_yield_perpetuity(monkeypatch):
    monkeypatch.setattr(dcf, 'TERMINAL_RULE', 'gdp')
    assert dcf.default_terminal_growth(base(currency='USD', risk_free=0.05)) == 0.04
    assert dcf.default_terminal_growth(base(currency='CHF', risk_free=0.005)) == 0.005


def test_quarter_currency_metadata_detects_reporting_currency_transition(monkeypatch):
    from api.marketdata import core
    core._cache.pop('dcf:statement_ccy:CURRENCY_TEST:quarterly:2026-06-30', None)
    dates = ['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30']
    records = [{'asOfDate': date, 'currencyCode': 'USD' if n < 2 else 'CNY'} for n, date in enumerate(dates)]
    data = {'timeseries': {'result': [{'quarterlyTotalRevenue': records}]}}
    monkeypatch.setattr(yf, 'Ticker', lambda _: SimpleNamespace(_data=SimpleNamespace(get_raw_json=lambda *a, **k: data)))
    assert dcf._statement_currency('CURRENCY_TEST', '2026-06-30', 'quarterly') == 'mixed:CNY/USD'
