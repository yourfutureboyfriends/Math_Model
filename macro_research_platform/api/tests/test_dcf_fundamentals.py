"""Economic identities and time/currency integrity of the research-driven cash-flow layer."""
import io

from openpyxl import load_workbook
import pandas as pd
import pytest

from api.marketdata import dcf, dcf_excel, dcf_fundamentals as f
from api.tests.test_dcf_refinements import base
from api.tests.test_dcf_excel import _evaluate


def evidence():
    def row(year, wc):
        return {'as_of': f'{year}-12-31', 'period': 'annual', 'currency': 'USD', 'revenue': 100.0,
                'capex': 12.0, 'dna': 5.0, 'net_capex': 7.0, 'working_capital_cash': -wc,
                'working_capital_investment': wc, 'reinvestment': 7+wc, 'cfo': 25.0, 'sbc': 3.0,
                'acquisitions_cash': 0.0}
    return {'source': 'test statements', 'annual': [row(2025, 4), row(2024, 2), row(2023, 3)],
            'working_capital_balances': {'2025-12-31': 10, '2024-12-31': 12, '2023-12-31': 8}}


def test_working_capital_sign_and_cashflow_identity():
    date = pd.Timestamp('2025-12-31')
    cf = pd.DataFrame({date: {'Capital Expenditure': -12, 'Depreciation And Amortization': 5,
                            'Change In Working Capital': -4, 'Stock Based Compensation': 3, 'Operating Cash Flow': 25}})
    row = f._cash_period(cf, [date], 100, '2025-12-31', 'annual')
    assert row['working_capital_investment'] == 4 and row['reinvestment'] == 11
    inp = base(revenue=100, ebit=20, currency='USD', as_of='2025-12-31', statement_basis_note='annual', capex=12, dna=5, tax_effective=0.25)
    out = f.apply(inp, evidence())
    assert out['cashflow_evidence']['observed_fcff'] == 4  # 20 * .75 - (12 - 5) - 4
    assert out['cashflow_evidence']['cash_after_capex_and_sbc'] == 10  # CFO - capex - SBC, separate from FCFF
    assert out['working_capital_to_sales'] == pytest.approx(0.10)
    assert 'cashflow_evidence' not in inp


def test_evidence_rejects_period_currency_and_revenue_conflicts():
    inp = base(as_of='2025-12-31', statement_basis_note='annual', revenue=100)
    bad = evidence()
    bad['annual'][0]['currency'] = 'EUR'
    assert f.apply(inp, bad)['cashflow_evidence']['status'] == 'unavailable'
    assert f.apply({**inp, 'as_of': '2026-06-30'}, evidence())['cashflow_evidence']['status'] == 'unavailable'
    assert f.apply({**inp, 'revenue': 150}, evidence())['cashflow_evidence']['status'] == 'unavailable'


def test_working_capital_intensity_never_uses_future_periods():
    inp = base(revenue=100, ebit=20, as_of='2024-12-31', statement_basis_note='annual', capex=12, dna=5)
    data = evidence()
    data['working_capital_balances']['2025-12-31'] = 99
    result = f.apply(inp, data)
    assert result['working_capital_to_sales'] == pytest.approx(0.10)  # median .12/.08, not future .99


def test_growth_linked_working_capital_is_not_double_counted(monkeypatch):
    monkeypatch.setattr(dcf, 'WORKING_CAPITAL_FORECAST', True)
    inp = base(net_capex_to_revenue=0.04, working_capital_to_sales=0.20)
    val = dcf.value(inp, growth=0.10)
    row = val['projection'][0]
    expected = 0.04 * row['revenue'] + .20 * (row['revenue']-inp['revenue'])
    assert row['reinvestment'] == pytest.approx(expected)
    assert row['fcff'] == pytest.approx(row['nopat'] - expected)
    assert row['working_capital_investment'] == pytest.approx(.20*(row['revenue']-inp['revenue']))
    # After the anchor fades, sales-to-capital accounts for all reinvestment, including working capital.
    row6 = val['projection'][5]
    assert row6['reinvestment'] == pytest.approx(row6['ratio_reinvestment'])
    assert row6['working_capital_investment'] == 0


@pytest.mark.parametrize('kwargs', [dict(), dict(working_capital_ratio=0.2), dict(sales_to_capital=2.0), dict(method='two_stage')])
def test_excel_matches_anchored_reinvestment_and_cyclical_margin_fade(kwargs):
    inp = base(net_capex_to_revenue=0.15, target_margin_default=0.15, margin_fade_years=3)
    val = dcf.value(inp, **kwargs)
    data, cells = dcf_excel.build(inp, val)
    wb = load_workbook(io.BytesIO(data))
    assert _evaluate(wb, cells['ev']) == pytest.approx(val['enterprise_value'], rel=1e-9)
    assert _evaluate(wb, cells['per_share']) == pytest.approx(val['per_share'], rel=1e-9)


def test_zero_risk_free_and_zero_tax_are_not_missing():
    inp = base(risk_free=0.0, tax_effective=0.0)
    assert dcf.wacc(inp)['risk_free'] == 0
    assert dcf.default_terminal_growth(inp) == 0
    assert dcf.value(inp)['assumptions']['tax_now'] == 0


def test_funding_gap_suppresses_automatic_valuation_label():
    inp = base(industry='Software', net_capex_to_revenue=0.80, cash=1e9, as_of='2025-12-31')
    val = dcf.value(inp)
    details = f.diagnostics(inp, val, 'fcff')
    assert details['funding_gap_after_cash'] > 0
    assert f.research_status(inp, val, 'fcff', details)['eligible'] is False


def test_balance_working_capital_excludes_cash_and_current_debt():
    date = pd.Timestamp('2025-12-31')
    balance = pd.DataFrame({date: {'Current Assets': 100, 'Cash Cash Equivalents And Short Term Investments': 30,
                                 'Current Liabilities': 80, 'Current Debt': 20}})
    assert f.operating_working_capital(balance, date) == 10
    assert f.operating_working_capital(balance.drop('Current Debt'), date) is None


def test_issuer_operating_profit_adjustment_is_period_currency_and_publication_bound():
    from datetime import date
    inp = base(symbol='0590.HK', currency='HKD', revenue=17205242000, ebit=3441521000,
               as_of='2026-03-31', statement_basis_note='annual', margin_history=[], roic_history=[])
    out = f.apply_issuer_adjustments(inp, today=date(2026, 10, 28))
    assert out['ebit'] == 2648054000
    assert out['issuer_adjustment']['provider_ebit'] == 3441521000
    assert f.apply_issuer_adjustments(inp, today=date(2026, 6, 1)) is inp
    wrong_period = {**inp, 'as_of': '2026-09-30'}
    assert f.apply_issuer_adjustments(wrong_period, today=date(2026, 10, 28)) is wrong_period
    wrong_currency = {**inp, 'currency': 'USD'}
    assert f.apply_issuer_adjustments(wrong_currency, today=date(2026, 10, 28)) is wrong_currency


def test_nav_is_a_dated_reference_and_never_an_automatic_price_target():
    from datetime import date
    inp = base(symbol='INVE-B.ST', price_currency='SEK', price=400)
    refs = f.asset_references(inp, today=date(2026, 10, 28))
    assert refs[0]['per_share'] == 411 and refs[0]['age_days'] == 28
    assert refs[0]['price_to_reported_assets'] == pytest.approx(400/411)
    assert f.asset_references(inp, today=date(2026, 10, 1)) == []
    assert f.asset_references(inp, today=date(2027, 6, 1))[0]['stale'] is True


def test_dividend_discount_rate_matches_dividend_currency(monkeypatch):
    monkeypatch.setattr(dcf, '_info', lambda _: {'dividendYield': 2.0})
    monkeypatch.setattr(dcf, '_dividend_history', lambda _: [])
    inp = base(price_currency='GBP', currency='USD', dividend_risk_free=0.03, risk_free=0.05)
    val = dcf.value_ddm(inp)
    assert val['assumptions']['risk_free'] == 0.03
    assert val['assumptions']['cashflow_currency'] == 'GBP'
    inp.pop('dividend_risk_free')
    with pytest.raises(dcf.NotFound, match='trading currency'):
        dcf.value_ddm(inp)


def test_sales_to_capital_and_explicit_working_capital_cannot_double_count():
    with pytest.raises(dcf.NotFound, match='not both'):
        dcf.value(base(net_capex_to_revenue=0.04), sales_to_capital=2.0, working_capital_ratio=0.20)


@pytest.mark.parametrize('as_of,annual,expected', [
    ('2026-03-31', True, False), ('2024-03-31', True, True),
    ('2025-12-31', False, True), ('2026-09-30', False, False),
    ('2027-03-31', True, True), ('not-a-date', False, True),
])
def test_statement_age_and_future_dates_require_review(as_of, annual, expected):
    from datetime import date
    inp = base(as_of=as_of, statement_basis_note='annual' if annual else None)
    val = dcf.value(inp)
    result = f.research_status(inp, val, 'fcff', {'checks': []}, today=date(2026, 10, 28))
    date_reasons = [r for r in result['reasons'] if 'days old' in r or 'date is in the future' in r or 'date is invalid' in r]
    assert bool(date_reasons) is expected


def test_dividend_default_growth_and_unmatched_rates_block_automatic_labels(monkeypatch):
    from datetime import date
    from api.marketdata import dcf
    inp=base(as_of='2026-10-01',industry='Household Products')
    monkeypatch.setattr(dcf,'_info',lambda _: {'dividendYield':2.0})
    monkeypatch.setattr(dcf,'_dividend_history',lambda _: [])
    val=dcf.value_ddm(inp)
    result=f.research_status(inp,val,'ddm',{'checks':[]},today=date(2026,10,31))
    assert not result['eligible']
    assert any('Dividend growth defaults' in r for r in result['reasons'])
    manual=dcf.value_ddm(inp,growth=.02)
    assert f.research_status(inp,manual,'ddm',{'checks':[]},today=date(2026,10,31))['eligible']
    result=f.research_status({**inp,'dividend_risk_free_matched':False},manual,'ddm',{'checks':[]},today=date(2026,10,31))
    assert not result['eligible'] and any('currency of dividend' in r for r in result['reasons'])


def test_dividend_coverage_requires_review_except_for_reit_accounting():
    from datetime import date
    inp=base(as_of='2026-10-01',industry='Household Products')
    val={'assumptions':{'payout_now':1.3},'terminal_share':.3}
    result=f.research_status(inp,val,'ddm',{'checks':[]},today=date(2026,10,31))
    assert not result['eligible'] and any('Dividends exceed earnings' in r for r in result['reasons'])
    assert f.research_status({**inp,'industry':'REIT—Retail'},val,'ddm',{'checks':[]},today=date(2026,10,31))['eligible']
