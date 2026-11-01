"""Inspectable deal diligence and intra-year cash timing; no inferred approval probabilities."""
from __future__ import annotations

import copy
import math
from typing import Any, Dict

CHECKLIST = {
    'earnings': 'Quality of earnings and add-backs',
    'cash': 'Working-capital peg and cash conversion',
    'debt': 'Debt-like liabilities, leases and lender terms',
    'tax': 'Tax structure, losses and deduction limits',
    'commercial': 'Commercial plan and exit comparables',
    'legal': 'Legal, regulatory and execution diligence',
}


def prepare(inp: Dict[str, Any]) -> Dict[str, Any]:
    from api.pe.lbo import LboError
    p = copy.deepcopy(inp)
    def finite(value, label):
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise LboError(f'{label} must be a finite number.')
        if not math.isfinite(v):
            raise LboError(f'{label} must be a finite number.')
        return v
    def scan(value, path='inputs'):
        if isinstance(value, dict):
            for k, v in value.items():
                scan(v, f'{path}.{k}')
        elif isinstance(value, list):
            for i, v in enumerate(value):
                scan(v, f'{path}[{i}]')
        elif isinstance(value, (int, float)) and not math.isfinite(value):
            raise LboError(f'{path} must be finite.')
    scan(p)
    for key in ('tax_rate', 'sweep_pct', 'mip_pct', 'transaction_fee_pct', 'financing_fee_pct', 'exit_fee_pct', 'nol_utilization_pct'):
        if p.get(key) is not None and not 0 <= finite(p[key], key) <= 1:
            raise LboError(f'{key} must be between zero and one.')
    for key in ('min_cash', 'rollover_equity', 'opening_nol', 'opening_disallowed_interest', 'interest_deduction_floor', 'annual_nol_limit'):
        if p.get(key) is not None and finite(p[key], key) < 0:
            raise LboError(f'{key} cannot be negative.')
    for key in ('dna_pct', 'capex_pct'):
        xs = p.get(key, 0)
        if any(finite(x, key) < 0 for x in (xs if isinstance(xs, list) else [xs])):
            raise LboError(f'{key} cannot be negative.')
    for key in ('years', 'exit_year'):
        v = finite(p.get(key, 7 if key == 'years' else 5), key)
        if v != int(v) or not 1 <= v <= 10:
            raise LboError(f'{key} must be a whole number from 1 to 10.')
    if p.get('exit_year', 5) > p.get('years', 7):
        raise LboError('Exit year must be inside the modeled period.')
    if p.get('interest_on', 'average') not in ('average', 'opening'):
        raise LboError('Choose opening or average balance interest.')
    if p.get('interest_cap_basis', 'ebitda') not in ('ebitda', 'ebit'):
        raise LboError('Interest deduction basis must be EBITDA or EBIT.')
    if p.get('interest_cap_pct') is not None and not 0 <= finite(p['interest_cap_pct'], 'Interest cap') <= 1:
        raise LboError('Interest cap must be between zero and one.')
    for t in p.get('tranches', []):
        if not str(t.get('name', '')).strip():
            raise LboError('Name every debt tranche.')
        if t.get('kind') not in ('tla', 'tlb', 'notes', 'mezz'):
            raise LboError('Unsupported debt tranche kind.')
        if finite(t.get('tenor', 7), 'Debt tenor') < 1:
            raise LboError('Debt tenor must be at least one year.')
        for k in ('amount', 'multiple', 'amort_pct', 'coupon', 'spread'):
            if t.get(k) is not None and finite(t[k], k) < 0:
                raise LboError(f'Debt {k} cannot be negative.')
    adjustments = p.get('ebitda_adjustments') or []
    if not isinstance(adjustments, list) or len(adjustments) > 50:
        raise LboError('Use at most 50 EBITDA adjustments.')
    accepted = 0.0
    for row in adjustments:
        amount = finite(row.get('amount', 0), 'EBITDA adjustment')
        if row.get('approved'):
            if not str(row.get('label', '')).strip() or not str(row.get('source', '')).strip():
                raise LboError('Accepted EBITDA adjustments need a description and evidence source.')
            accepted += amount
    reported = finite(p.get('ebitda', 0), 'Reported EBITDA')
    p['ebitda'] = reported + accepted
    p['_ebitda_bridge'] = {'reported': reported, 'accepted_adjustments': accepted,
                          'underwritten': p['ebitda'], 'items': adjustments,
                          'plan_adjusted': bool(p.get('apply_adjustments_to_plan'))}
    if accepted and p.get('apply_adjustments_to_plan'):
        rev = finite(p.get('revenue', 0), 'Revenue')
        if rev <= 0:
            raise LboError('Positive revenue is required to adjust forecast margins.')
        margin = p.get('ebitda_margin', reported/rev)
        p['ebitda_margin'] = [float(x)+accepted/rev for x in margin] if isinstance(margin, list) else float(margin)+accepted/rev
    for key in ('revenue_growth', 'ebitda_margin'):
        xs = p.get(key)
        if xs is not None:
            xs = xs if isinstance(xs, list) else [xs]
            if not xs or any(x is None for x in xs):
                raise LboError(f'{key} needs a value for every provided period.')
            if any(finite(x, key) <= -1 for x in xs) and key == 'revenue_growth':
                raise LboError('Revenue growth must be greater than -100%.')
    return p


def liquidity(inp, base):
    """Quarterly cash-timing diagnostic anchored to annual FCF, not an integrated quarterly debt/tax model.

    Allocate cash FCF and mandatory repayments using explicit user weights, pay annual sweeps in Q4,
    and solve the revolver funding each quarter. This reveals seasonal funding hidden by annual netting.
    Incremental intra-year draw interest/refinancing is deliberately not assumed.
    """
    from api.pe.lbo import LboError
    weights = inp.get('quarterly_cash_weights') or [.25]*4
    debt_weights = inp.get('quarterly_debt_weights') or [0, 0, 0, 1]
    def checked(xs, label):
        if len(xs) != 4 or any(not math.isfinite(float(x)) or float(x) < 0 for x in xs) or abs(sum(xs)-1) > 1e-6:
            raise LboError(f'{label}: four nonnegative weights summing to 100% are required.')
        return xs
    weights, debt_weights = checked(weights, 'Quarterly cash weights'), checked(debt_weights, 'Quarterly debt weights')
    reserve = float(inp.get('min_cash') or 0)
    cash, revolver = reserve, float((inp.get('revolver') or {}).get('drawn_at_close') or 0)
    commitment = float((inp.get('revolver') or {}).get('commitment') or 0)
    rows = []
    for y in base['schedule'][:base['exit_year']]:
        for q in range(4):
            opening_cash = cash
            fcf, due = y['fcf']*weights[q], y['mandatory']*debt_weights[q]
            sweep = y['sweep'] if q == 3 else 0
            available = cash + fcf - due - sweep - reserve
            draw = min(max(0, -available), max(0, commitment-revolver))
            repay = min(revolver, max(0, available))
            revolver += draw-repay
            cash = reserve+available+draw-repay
            rows.append({'year': y['year'], 'quarter': q+1, 'opening_cash': opening_cash, 'fcf': fcf,
                         'mandatory': due, 'sweep': sweep, 'draw': draw, 'repayment': repay,
                         'cash': cash, 'revolver': revolver, 'undrawn': max(0, commitment-revolver),
                         'gap': max(0, reserve-cash)})
    return {'quarters': rows, 'peak_revolver': max([r['revolver'] for r in rows] or [0]),
            'maximum_reserve_shortfall': max([r['gap'] for r in rows] or [0]),
            'first_shortfall': next((f"Y{r['year']} Q{r['quarter']}" for r in rows if r['gap'] > 1e-6), None),
            'note': 'Cash-timing diagnostic: allocated annual FCF, explicit debt-service timing, Q4 sweeps. Excludes incremental seasonal interest, quarterly tax true-ups and refinancing. It does not replace a quarterly underwriting model.'}


def diligence(inp, base, cash_timing):
    completed = inp.get('diligence') or {}
    checks = [{'key': k, 'label': v, 'complete': bool(completed.get(k))} for k, v in CHECKLIST.items()]
    reasons = []
    if not base['calculation_checks']['eligible_for_hurdle']:
        reasons.append('Resolve annual financing or calculation issues.')
    if cash_timing['first_shortfall']:
        reasons.append(f"Seasonal reserve shortfall begins {cash_timing['first_shortfall']}.")
    if any(not t['leverage_ok'] or not t['cover_ok'] for t in base['covenants'][:base['exit_year']]):
        reasons.append('A modeled covenant is breached before exit.')
    if any(not r['complete'] for r in checks):
        reasons.append('Diligence checklist is incomplete; completion is user-attested.')
    if any(not r.get('approved') for r in base['ebitda_bridge']['items']):
        reasons.append('Some EBITDA adjustments remain excluded pending evidence review.')
    return {'checks': checks, 'completed': sum(r['complete'] for r in checks), 'total': len(checks),
            'status': 'review_required' if reasons else 'screening_checks_complete', 'reasons': reasons,
            'note': 'Checklist completion is not investment committee approval or verified legal/tax diligence.'}
