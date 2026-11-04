"""Dated cash-flow evidence and transparent valuation diagnostics.

Public methodology: Morgan Stanley Counterpoint Global (capital allocation/ROIC),
UBS HOLT (accounting comparability), AQR (value and quality are separate evidence).
No proprietary firm algorithm or fitted confidence probability is reproduced here.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional

from api.marketdata.core import _f


def _cell(frame, rows, date):
    if frame is None or frame.empty or date not in frame.columns:
        return None
    for row in rows:
        if row in frame.index:
            value = _f(frame.loc[row, date])
            if value is not None:
                return value
    return None



def operating_working_capital(balance, date):
    """Noncash current assets minus nondebt current liabilities, on a single balance date.

    This is an observable proxy, not a bespoke tax/lease reclassification. Missing debt/cash
    components are not assumed to be zero. It is not used for banks or insurers.
    """
    ca = _cell(balance, ('Current Assets',), date)
    cl = _cell(balance, ('Current Liabilities',), date)
    cash = _cell(balance, ('Cash Cash Equivalents And Short Term Investments',), date)
    debt = _cell(balance, ('Current Debt And Capital Lease Obligation', 'Current Debt'), date)
    if debt is None and _cell(balance, ('Total Debt',), date) == 0:
        debt = 0.0
    return ca-cash-cl+debt if all(x is not None for x in (ca, cl, cash, debt)) else None

def _cash_period(cf, dates: List[Any], revenue: Optional[float], as_of: str, period: str) -> Dict[str, Any]:
    fields = {'capex': ('Capital Expenditure',),
              'dna': ('Depreciation And Amortization', 'Depreciation Amortization Depletion'),
              'working_capital_cash': ('Change In Working Capital',),
              'sbc': ('Stock Based Compensation',), 'cfo': ('Operating Cash Flow', 'Total Cash From Operating Activities'),
              'acquisitions_cash': ('Net Business Purchase And Sale', 'Purchase Of Business')}
    out = {'as_of': as_of, 'period': period, 'revenue': revenue}
    for key, rows in fields.items():
        values = [_cell(cf, rows, date) for date in dates]
        out[key] = sum(values) if values and all(v is not None for v in values) else None
    if out['capex'] is not None:
        out['capex'] = abs(out['capex'])
    out['working_capital_investment'] = -out['working_capital_cash'] if out['working_capital_cash'] is not None else None
    out['net_capex'] = out['capex'] - out['dna'] if out['capex'] is not None and out['dna'] is not None else None
    out['reinvestment'] = out['net_capex'] + out['working_capital_investment'] if out['net_capex'] is not None and out['working_capital_investment'] is not None else None
    return out


def _collect(symbol: str) -> Dict[str, Any]:
    """Capture fiscal-year evidence and a genuinely consecutive, date-matched four-quarter sum."""
    import yfinance as yf
    from api.marketdata import dcf
    tk = yf.Ticker(symbol)
    inc, cf = tk.income_stmt, tk.cashflow
    annual = []
    if inc is not None and not inc.empty:
        for date in inc.columns:
            rev = _cell(inc, ('Total Revenue',), date)
            if rev is None or rev <= 0:
                continue
            row = _cash_period(cf, [date], rev, str(date)[:10], 'annual')
            row.update(ebit=_cell(inc, ('Operating Income',), date), net_income=_cell(inc, ('Net Income Common Stockholders', 'Net Income'), date))
            annual.append(row)
    annual.sort(key=lambda r: r['as_of'], reverse=True)
    latest_currency = dcf._statement_currency(symbol, annual[0]['as_of'], 'annual') if annual else None
    for row in annual:
        row['currency'] = dcf._statement_currency(symbol, row['as_of'], 'annual')
    quarterly = None
    q, qcf = tk.quarterly_income_stmt, tk.quarterly_cashflow
    if q is not None and not q.empty:
        dates = list(q.columns[:4])
        if len(dates) == 4 and all(60 <= (dates[n] - dates[n+1]).days <= 120 for n in range(3)):
            revs = [_cell(q, ('Total Revenue',), date) for date in dates]
            if all(v is not None for v in revs) and sum(revs) > 0:
                quarterly = _cash_period(qcf, dates, sum(revs), str(dates[0])[:10], 'ttm')
                quarterly['currency'] = dcf._statement_currency(symbol, quarterly['as_of'], 'quarterly')
    balance = tk.balance_sheet
    working_balances = {str(date)[:10]: operating_working_capital(balance, date) for date in balance.columns} if balance is not None else {}
    return {'working_capital_balances': working_balances, 'symbol': symbol, 'source': 'Yahoo dated income and cash-flow statements', 'annual': annual,
            'ttm': quarterly, 'latest_annual_currency': latest_currency}



def collect(symbol: str) -> Dict[str, Any]:
    from api.marketdata.core import _cached
    return _cached(f"dcf:cashflow_evidence:{symbol}", 3600, lambda: _collect(symbol))

def apply(inp: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Attach evidence only on matching period, currency and revenue; do not rewrite the market inputs."""
    out = dict(inp)
    annual_basis = bool(inp.get('statement_basis_note'))
    candidates = evidence.get('annual', []) if annual_basis else [evidence.get('ttm')]
    current = next((r for r in candidates if r and r['as_of'] == inp.get('as_of')), None)
    if not current:
        out['cashflow_evidence'] = {'status': 'unavailable', 'reason': 'No cash-flow period matching the valuation base.', 'source': evidence.get('source')}
        return out
    if current.get('currency') != inp.get('currency'):
        out['cashflow_evidence'] = {'status': 'unavailable', 'reason': 'Cash-flow evidence has unverified or conflicting reporting currency.', 'source': evidence.get('source')}
        return out
    rev = inp.get('revenue')
    if not rev or abs(current['revenue'] / rev - 1) > 0.02:
        out['cashflow_evidence'] = {'status': 'unavailable', 'reason': 'Statement revenue differs from the valuation base by more than the 2% reconciliation tolerance.', 'source': evidence.get('source')}
        return out
    current = dict(current)
    # Keep the filing-based capex/D&A where present. A material disagreement is a data issue.
    for key in ('capex', 'dna'):
        filed, vendor = inp.get(key), current.get(key)
        if filed is not None and vendor is not None and abs(filed - vendor) > max(abs(filed), abs(vendor), 1) * 0.10:
            out['cashflow_evidence'] = {'status': 'unavailable', 'reason': f'{key} differs materially between filing and cash-flow evidence.', 'source': evidence.get('source')}
            return out
        if filed is not None:
            current[key] = filed
    current['net_capex'] = current['capex'] - current['dna'] if current.get('capex') is not None and current.get('dna') is not None else None
    current['reinvestment'] = current['net_capex'] + current['working_capital_investment'] if current['net_capex'] is not None and current.get('working_capital_investment') is not None else None
    if inp.get('net_capex_to_revenue') is None and current['net_capex'] is not None:
        out['net_capex_to_revenue'] = current['net_capex']/rev
    history = [r for r in evidence.get('annual', []) if r['as_of'] <= current['as_of'] and r.get('currency') == inp.get('currency') and r.get('working_capital_investment') is not None and r.get('revenue')]
    history = sorted(history, key=lambda r: r['as_of'], reverse=True)[:3]
    ratios = [r['working_capital_investment']/r['revenue'] for r in history]
    wc_ratio = statistics.median(ratios) if len(ratios) >= 2 else (current['working_capital_investment']/rev if current.get('working_capital_investment') is not None else None)
    basis = f'median working-capital investment/revenue over {len(ratios)} fiscal years' if len(ratios) >= 2 else 'matching current-period working-capital investment/revenue'
    balances = evidence.get('working_capital_balances', {})
    intensity = [balances[r['as_of']]/r['revenue'] for r in history if balances.get(r['as_of']) is not None]
    if len(intensity) >= 2 and current['net_capex'] is not None:
        wc_sales = statistics.median(intensity)
        if -1 <= wc_sales <= 1:
            out['working_capital_to_sales'] = wc_sales
            out['working_capital_source'] = f'median noncash/nondebt working capital/revenue over {len(intensity)} fiscal years'
    # Historical cash movements remain an observed FCFF component, not a recurring forecast charge.
    tax = inp.get('tax_effective') if inp.get('tax_effective') is not None else inp.get('tax_marginal', 0.25)
    ebit = inp.get('ebit')
    nopat = ebit*(1-tax) if ebit is not None and ebit > 0 else ebit
    actual_fcff = nopat - current['reinvestment'] if nopat is not None and current['reinvestment'] is not None else None
    sbc = inp.get('sbc') if inp.get('sbc') is not None else current.get('sbc')
    owner_proxy = current['cfo'] - current['capex'] - sbc if all(current.get(k) is not None for k in ('cfo', 'capex')) and sbc is not None else None
    out['cashflow_evidence'] = {**current, 'status': 'matched', 'source': evidence.get('source'), 'nopat': nopat,
                                'observed_fcff': actual_fcff, 'sbc': sbc, 'cash_after_capex_and_sbc': owner_proxy,
                                'working_capital_forecast_ratio': wc_ratio, 'working_capital_basis': basis,
                                'working_capital_history_years': len(ratios), 'working_capital_to_sales': out.get('working_capital_to_sales'),
                                'working_capital_forecast_basis': out.get('working_capital_source'),
                                'note': 'Reconstructed period FCFF uses the stated effective/marginal tax assumption, not verified cash taxes. FCFF starts from EBIT, which already expenses SBC. CFO minus capex minus SBC is a separate cash proxy before debt funding; it is not FCFF.'}
    return out


def diagnostics(inp: Dict[str, Any], val: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Calculation trace, economic cross-checks and funding needs; never a fitted accuracy score."""
    cf = inp.get('cashflow_evidence') or {'status': 'unavailable', 'reason': 'No matched cash-flow evidence.'}
    ni, cfo = inp.get('net_income'), cf.get('cfo')
    checks = []
    if cf['status'] != 'matched':
        checks.append(cf.get('reason', 'Cash-flow components unavailable.'))
    if model == 'fcff' and cf.get('status') == 'matched' and cf.get('observed_fcff') is None:
        checks.append('Working-capital/capex/depreciation fields are incomplete; period FCFF cannot be reconstructed.')
    if ni and ni > 0 and cfo is not None and cfo < 0:
        checks.append('Positive accounting earnings but negative operating cash flow; investigate cash conversion.')
    if cf.get('acquisitions_cash') is not None and inp.get('revenue') and -cf['acquisitions_cash'] > 0.10 * inp['revenue']:
        checks.append('Material acquisition spending: reconcile acquisition-driven growth and financing separately.')
    projection = val.get('projection') or []
    cumulative, maximum_gap = 0.0, 0.0
    if model == 'fcff':
        for row in projection:
            cumulative += row['fcff']
            maximum_gap = max(maximum_gap, -cumulative)
    cash = inp.get('cash')
    funding = max(0.0, maximum_gap - cash) if cash is not None and model == 'fcff' else None
    if funding and funding > 0:
        checks.append('Forecast operating cash deficits exceed reported cash; financing/dilution is not modeled automatically.')
    rows = []
    if model == 'fcff' and projection:
        for row in (projection[0], projection[min(val['assumptions']['years'], len(projection))-1]):
            rows.append({'year': row['year'], 'revenue': row['revenue'], 'ebit': row['ebit'],
                         'modeled_tax': row['ebit']-row['nopat'], 'nopat': row['nopat'], 'reinvestment': row['reinvestment'],
                         'fcff': row['fcff'], 'discount_factor': row['discount_factor'], 'present_value': row['pv'],
                         'incremental_return': row.get('incremental_return')})
    returns = [r.get('incremental_return') for r in projection if r.get('stage') == 'explicit' and r.get('incremental_return') is not None]
    if any(v > 0.60 for v in returns):
        checks.append('Some forecast incremental returns exceed 60%; review capital intensity and margin expansion rather than assuming these returns persist.')
    return {'asset_references': asset_references(inp), 'issuer_adjustment': inp.get('issuer_adjustment'), 'cashflow': cf, 'forecast_steps': rows, 'discount': val.get('wacc'), 'equity_bridge': val.get('bridge'),
            'cash_earnings_gap_to_sales': (ni-cfo)/inp['revenue'] if ni is not None and cfo is not None and inp.get('revenue') else None,
            'cash_conversion': cfo/ni if ni is not None and ni > 0 and cfo is not None else None,
            'maximum_cumulative_operating_deficit': maximum_gap if model == 'fcff' else None,
            'funding_gap_after_cash': funding, 'checks': checks,
            'status': 'review_required' if checks else 'components_available',
            'note': 'No accuracy probability is estimated. Funding gap excludes refinancing, acquisitions, dividends and existing credit facilities. Method agreement is not independent validation.'}


def research_status(inp: Dict[str, Any], val: Dict[str, Any], model: str, details: Dict[str, Any], today=None) -> Dict[str, Any]:
    """Separate a numerical model output from eligibility for automatic valuation labels."""
    from api.marketdata import dcf
    reasons = list(dcf.model_suitability(inp, model)['reasons'])
    if model == 'fcff':
        reasons.extend(details['checks'])
    if model == 'ddm':
        assumptions = val.get('assumptions') or {}
        if 'no history: stable growth' in (assumptions.get('growth_source') or ''):
            reasons.append('Dividend growth defaults to stable growth without a history or sustainable-growth bridge; review payout durability and growth before using valuation labels.')
        if not inp.get('dividend_risk_free_matched', inp.get('risk_free_matched', True)):
            reasons.append('The dividend discount rate is not matched to the currency of dividend cash flows.')
        if (assumptions.get('payout_now') or 0) > 1 and not (inp.get('industry') or '').startswith('REIT'):
            reasons.append('Dividends exceed earnings; verify payout coverage and the risk of a dividend cut.')
    from datetime import date
    today = today or date.today()
    if not inp.get('as_of'):
        reasons.append('Statement date is unavailable.')
    else:
        try:
            age = (today - date.fromisoformat(inp['as_of'])).days
            # Explicit screening policy, not a claim about statutory filing deadlines.
            limit = 550 if inp.get('statement_basis_note') else 270
            if age < 0:
                reasons.append('Statement date is in the future; reconcile the valuation base.')
            elif age > limit:
                reasons.append(f'Statement base is {age} days old (review threshold {limit} days).')
        except (TypeError, ValueError):
            reasons.append('Statement date is invalid.')
    if val.get('equity_negative'):
        reasons.append('The operating model leaves no equity value; recovery/asset value is not captured.')
    if (val.get('terminal_share') or 0) > 0.85:
        reasons.append('More than 85% of modeled value depends on the terminal period.')
    reasons = list(dict.fromkeys(reasons))
    return {'eligible': not reasons, 'status': 'research_required' if reasons else 'model_checks_clear',
            'reasons': reasons, 'note': 'Eligibility is a data/model check, not a probability of correctness or a validated investment recommendation.'}


def issuer_facts() -> Dict[str, Any]:
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2]/'config/valuation_evidence.json'
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def apply_issuer_adjustments(inp: Dict[str, Any], facts: Optional[Dict[str, Any]] = None, today=None) -> Dict[str, Any]:
    """Auditable source reconciliation, never a fitted valuation multiplier.

    Only a published fact for the same fiscal-year base, currency and revenue is applied.
    A new quarter/year or reporting-currency change makes the override inapplicable.
    """
    from datetime import date
    from api.marketdata import dcf
    fact = (facts if facts is not None else issuer_facts()).get('operating_profit', {}).get(inp.get('symbol'))
    today = today or date.today()
    if not fact or fact['published_at'] > today.isoformat() or fact['as_of'] != inp.get('as_of') or fact['currency'] != inp.get('currency'):
        return inp
    if not inp.get('statement_basis_note') or not inp.get('revenue') or abs(inp['revenue']/fact['revenue']-1) > 0.001:
        return inp
    statement = {'revenue': fact['revenue'], 'ebit': fact['ebit'], 'as_of': fact['as_of'], 'period': 'annual',
                 'currency': fact['currency'], 'capex': inp.get('capex'), 'dna': inp.get('dna')}
    out = dcf.restate_statement_inputs(inp, statement)
    out['source'] = 'Issuer operating profit reconciled to the matching annual financial base'
    out['issuer_adjustment'] = {**fact, 'provider_ebit': inp.get('ebit'), 'provider_source': inp.get('source')}
    return out


def asset_references(inp: Dict[str, Any], facts: Optional[Dict[str, Any]] = None, today=None) -> List[Dict[str, Any]]:
    """Dated issuer NAV/NTA references, kept outside the model-value blend."""
    from datetime import date
    today = today or date.today()
    records = (facts if facts is not None else issuer_facts()).get('asset_references', {}).get(inp.get('symbol'), [])
    out = []
    for record in records:
        if record['published_at'] > today.isoformat():
            continue
        age = (today-date.fromisoformat(record['as_of'])).days
        same_currency = record['currency'] == inp.get('price_currency')
        price = inp.get('price')
        out.append({**record, 'age_days': age, 'stale': age > 180,
                    'price_to_reported_assets': price/record['per_share'] if same_currency and price and record['per_share'] else None,
                    'note': 'Historical issuer asset value, not a price target. No holding-company/property discount is assumed. Not included in the automatic valuation blend.'})
    return out
