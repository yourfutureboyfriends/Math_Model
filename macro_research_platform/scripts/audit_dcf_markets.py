"""Reproducible cross-sectional DCF audit, not a price-target optimizer or backtest.

Run from the repository root with PYTHONPATH=. python scripts/audit_dcf_markets.py.
Inputs are checkpointed; --evaluate reruns saved inputs without fetching company data.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.marketdata import core, dcf

DEVELOPED = 'AU AT BE CA DK FI FR DE HK IE IL IT JP NL NZ NO PT SG ES SE CH GB US'.split()
SECTORS = {'Technology': 'Information Technology', 'Healthcare': 'Health Care',
           'Financial Services': 'Financials', 'Basic Materials': 'Materials',
           'Consumer Cyclical': 'Consumer Discretionary', 'Consumer Defensive': 'Consumer Staples'}


def size(cap):
    return 'micro' if cap < 3e8 else 'small' if cap < 2e9 else 'mid' if cap < 1e10 else 'large'


def select(universe):
    """Preselect by geography/size/sector, without looking at model values or returns."""
    stocks = [dict(s) for s in universe['stocks'] if s['country'] in DEVELOPED and s.get('mcap_usd', 0) > 0]
    for s in stocks:
        cached = ROOT / 'data/processed/fundamentals' / (s['symbol'] + '.json')
        if not s.get('sector') and cached.exists():
            sector = json.loads(cached.read_text()).get('info', {}).get('sector')
            s['sector'] = SECTORS.get(sector, sector)
        s['size'] = size(s['mcap_usd'])
    chosen = {}
    def add(s, reason):
        if s['symbol'] not in chosen:
            chosen[s['symbol']] = {**s, 'selection': reason}
    for country in DEVELOPED:
        rows = sorted([s for s in stocks if s['country'] == country], key=lambda s: s['mcap_usd'])
        if not rows:
            continue
        add(rows[-1], 'country: largest')
        mids = [s for s in rows if s['size'] == 'mid']
        add(mids[len(mids)//2] if mids else rows[len(rows)//2], 'country: mid-cap / median available')
        add(rows[0], 'country: smallest in platform universe')
    for sector in sorted({s['sector'] for s in stocks if s.get('sector')}):
        for bucket in ('small', 'mid', 'large'):
            rows = sorted([s for s in stocks if s.get('sector') == sector and s['size'] == bucket], key=lambda s: s['mcap_usd'])
            if rows:
                add(rows[len(rows)//2], 'sector/size coverage')
    # The platform universe is large-cap-heavy; supplement to at least 22 small caps.
    smalls = sorted([s for s in stocks if s['size'] == 'small'], key=lambda s: (s['country'], s['mcap_usd']))
    for s in smalls:
        if sum(x['size'] == 'small' for x in chosen.values()) >= 22:
            break
        add(s, 'small-cap supplement')
    # Include familiar comparison anchors; these do not replace the geography/size sample.
    for symbol in ('AAPL', 'MSFT', 'NVDA', 'TSLA', 'XOM', 'JPM', 'O', '7203.T', 'NESN.SW'):
        row = next((s for s in stocks if s['symbol'] == symbol), None)
        if row:
            add(row, 'diagnostic anchor')
    return sorted(chosen.values(), key=lambda s: (s['country'], s['symbol']))


def fetch(row):
    start = time.monotonic()
    try:
        inp = dcf.inputs(row['symbol'])
        info = dcf._info(row['symbol'])
        dividends = dcf._dividend_history(row['symbol']) if (inp.get('industry') or '').startswith(('REIT', 'Utilities')) else []
        fx = {ccy: core.to_usd(1.0, ccy) for ccy in {inp.get('currency'), inp.get('price_currency')} if ccy}
        return {'selection': row, 'inputs': inp, 'info': info, 'dividends': dividends, 'fx_usd_per': fx,
                'fetched_at': datetime.now(timezone.utc).isoformat(), 'seconds': round(time.monotonic()-start, 2)}
    except Exception as exc:
        return {'selection': row, 'error': f'{type(exc).__name__}: {exc}', 'seconds': round(time.monotonic()-start, 2)}



def supplement(snapshot):
    """Capture additional statement evidence separately; original input snapshots stay immutable."""
    inp = snapshot.get('inputs')
    if not inp or inp.get('source', '').startswith('SEC'):
        return {}
    statement = dcf._ttm_from_quarters(inp['symbol'])
    if statement is None:
        statement = dcf._annual_from_statements(inp['symbol'])
    return {'statement': statement, 'fetched_at': datetime.now(timezone.utc).isoformat()}

def evaluate(snapshot, aligned=False, evidence=None, cashflow_evidence=None):
    row = snapshot['selection']
    result = {k: row.get(k) for k in ('symbol', 'country', 'sector', 'size', 'mcap_usd', 'selection')}
    if 'error' in snapshot:
        return {**result, 'error': snapshot['error']}
    inp = snapshot['inputs']
    sector = snapshot.get('info', {}).get('sector')
    result['sector'] = SECTORS.get(sector, sector) or row.get('sector')
    if aligned and evidence and evidence.get('statement'):
        try:
            inp = dcf.restate_statement_inputs(inp, evidence['statement'])
        except core.NotFound as exc:
            return {**result, 'name': inp.get('name'), 'price': inp.get('price'), 'error': str(exc), 'flags': ['statement_currency_conflict']}
    elif aligned and not inp.get('source', '').startswith('SEC'):
        inp = dict(inp)
        dcf._validate_statement_currency(inp, {})
    if cashflow_evidence:
        from api.marketdata import dcf_fundamentals
        inp = dcf_fundamentals.apply_issuer_adjustments(inp)
        inp = dcf_fundamentals.apply(inp, cashflow_evidence)
    sector = snapshot.get('info', {}).get('sector')
    result.update(sector=SECTORS.get(sector, sector) or row.get('sector'), name=inp.get('name'),
                  price=inp.get('price'), currency=inp.get('currency'), price_currency=inp.get('price_currency'),
                  source=inp.get('source'), statement_date=inp.get('as_of'))
    model = 'excess_return' if inp.get('is_financial') else 'ddm' if (inp.get('industry') or '').startswith(('REIT', 'Utilities')) else 'fcff'
    result['model'] = model
    def convert(amount, currency):
        rate = snapshot.get('fx_usd_per', {}).get(currency)
        return amount * rate if amount is not None and rate is not None else None
    with ExitStack() as stack:
        stack.enter_context(patch.object(dcf, '_info', return_value=snapshot['info']))
        stack.enter_context(patch.object(dcf, '_dividend_history', return_value=snapshot['dividends']))
        stack.enter_context(patch.object(dcf, 'to_usd', side_effect=convert))
        try:
            engine = {'fcff': dcf.value, 'excess_return': dcf.value_financial, 'ddm': dcf.value_ddm}[model]
            value = engine(inp)
            views = dcf.market_views(inp, model)
            result.update(valuation=value, market_views=views, per_share=value['per_share'],
                          ratio=value['per_share']/inp['price'] if value.get('per_share') is not None and inp.get('price') else None,
                          terminal_share=value.get('terminal_share'))
            if model == 'fcff':
                result['implied_growth'] = dcf.reverse(inp)
                result['implied_discount'] = dcf.implied_discount(inp)
            elif model == 'excess_return':
                result['implied_roe'] = dcf.reverse_financial(inp)
            else:
                result['implied_growth'] = value.get('implied_growth')
            flags = []
            if result['ratio'] is not None and not 0.5 <= result['ratio'] <= 2:
                flags.append('price_gap_over_2x')
            if value.get('equity_negative'):
                flags.append('negative_equity_value')
            if (value.get('terminal_share') or 0) > 0.85:
                flags.append('terminal_dependence')
            if not inp.get('risk_free_matched', True):
                flags.append('unmatched_currency_rate')
            if inp.get('margin_basis_note'):
                flags.append('quarter_margin_fallback')
            if inp.get('growth_source') == 'default 5%':
                flags.append('default_growth')
            if inp.get('cash') is None or inp.get('debt') is None:
                flags.append('missing_cash_or_debt')
            if inp.get('as_of') is None:
                flags.append('statement_date_unavailable')
            f = views['current_market']['scenarios']
            if all(f[k].get('per_share') is not None for k in ('base', 'expansion', 'recession')):
                if not f['recession']['per_share'] <= f['base']['per_share'] <= f['expansion']['per_share']:
                    flags.append('scenario_order_inversion')
            for lens in ('fundamental', 'current_market'):
                if any(c.get('error') for c in views[lens]['scenarios'].values()):
                    flags.append(lens + '_scenario_failure')
            from api.marketdata import dcf_fundamentals
            result['calculation_details'] = dcf_fundamentals.diagnostics(inp, value, model)
            result['research_status'] = dcf_fundamentals.research_status(inp, value, model, result['calculation_details'])
            result['suitability'] = dcf.model_suitability(inp, model)
            if result['suitability']['status'] == 'review_required':
                flags.append('model_review_required')
            result['review_status'] = result['suitability']['status']
            result['review_reasons'] = ' | '.join(result['suitability']['reasons'])
            result['flags'] = flags
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
    return result


def summarize(results):
    valid = [r for r in results if r.get('ratio') is not None and math.isfinite(r['ratio'])]
    def stats(rows):
        ratios = [r['ratio'] for r in rows if r.get('ratio') is not None and math.isfinite(r['ratio'])]
        return {'attempted': len(rows), 'valued': len(ratios), 'median_value_price': statistics.median(ratios) if ratios else None,
                'within_30pct': sum(0.7 <= v <= 1.3 for v in ratios)/len(ratios) if ratios else None,
                'outside_2x': sum(not 0.5 <= v <= 2 for v in ratios)}
    return {'total': stats(results), 'countries': {k: stats([r for r in results if r['country'] == k]) for k in DEVELOPED},
            'sectors': {k: stats([r for r in results if (r.get('sector') or 'Unknown') == k]) for k in sorted({r.get('sector') or 'Unknown' for r in results})},
            'sizes': {k: stats([r for r in results if r['size'] == k]) for k in ('micro', 'small', 'mid', 'large')},
            'models': {k: stats([r for r in results if r.get('model') == k]) for k in ('fcff', 'excess_return', 'ddm')},
            'flags': dict(Counter(f for r in results for f in r.get('flags', []))),
            'errors': [{'symbol': r['symbol'], 'error': r['error']} for r in results if 'error' in r]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'data/processed/dcf_audit_2026-10-28')
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--supplement-statements', action='store_true')
    parser.add_argument('--aligned', action='store_true')
    parser.add_argument('--cashflow-evidence', type=Path)
    parser.add_argument('--label', default='current')
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output/'manifest.json'
    if not manifest.exists():
        universe = json.loads((ROOT/'data/processed/global_universe.json').read_text())
        manifest.write_text(json.dumps({'universe_saved_at': universe['saved_at'], 'selection': select(universe)}, indent=2))
    sample = json.loads(manifest.read_text())['selection']
    snapshots = args.output/'snapshots'
    snapshots.mkdir(exist_ok=True)
    evidence_dir = args.output/'statement_evidence'
    evidence_dir.mkdir(exist_ok=True)
    if args.supplement_statements:
        pending = [r for r in sample if not (evidence_dir/(r['symbol']+'.json')).exists()]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(supplement, json.loads((snapshots/(r['symbol']+'.json')).read_text())): r for r in pending}
            for n, future in enumerate(as_completed(jobs), 1):
                symbol = jobs[future]['symbol']
                record = future.result()
                (evidence_dir/(symbol+'.json')).write_text(json.dumps(record, indent=2, default=str, allow_nan=False))
                print(f'evidence {n}/{len(pending)} {symbol}', flush=True)
    if not args.evaluate and not args.supplement_statements:
        pending = [r for r in sample if not (snapshots/(r['symbol']+'.json')).exists()]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(fetch, r): r for r in pending}
            for n, future in enumerate(as_completed(jobs), 1):
                record = future.result()
                symbol = record['selection']['symbol']
                (snapshots/(symbol+'.json')).write_text(json.dumps(record, indent=2, default=str, allow_nan=False))
                print(f'{n}/{len(pending)} {symbol} {record.get("error", "saved")} ({record["seconds"]}s)', flush=True)
    results = []
    for row in sample:
        p = snapshots/(row['symbol']+'.json')
        if p.exists():
            evidence_path = evidence_dir/(row['symbol']+'.json')
            evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else None
            cf_path = args.cashflow_evidence/(row['symbol']+'.json') if args.cashflow_evidence else None
            cf_evidence = json.loads(cf_path.read_text()) if cf_path and cf_path.exists() else None
            results.append(evaluate(json.loads(p.read_text()), args.aligned, evidence, cf_evidence))
    (args.output/(args.label+'.json')).write_text(json.dumps(results, indent=2, default=str, allow_nan=False))
    summary = summarize(results)
    (args.output/(args.label+'_summary.json')).write_text(json.dumps(summary, indent=2))
    columns = ['symbol', 'name', 'country', 'sector', 'size', 'model', 'price', 'per_share', 'ratio', 'terminal_share', 'currency', 'price_currency', 'statement_date', 'implied_growth', 'implied_discount', 'implied_roe', 'review_status', 'review_reasons', 'flags', 'error']
    with (args.output/(args.label+'.csv')).open('w') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
