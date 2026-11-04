"""Capture financial evidence and score fixed, one-year fundamental forecast rules.

Latest available/restated annual statements are used, not historical publication vintages.
This temporal holdout is a forecast diagnostic, not a point-in-time investment backtest.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.marketdata import dcf_fundamentals as fundamentals


def temporal_validation(records):
    """Latest year is held out; neither candidate uses its revenue, margin or WC to predict it."""
    results = []
    for symbol, data in records.items():
        annual = sorted(data.get('annual', []), key=lambda r: r['as_of'])
        if len(annual) < 3:
            continue
        target, history = annual[-1], annual[:-1]
        previous = history[-1]
        if not target.get('currency') or any(r.get('currency') != target['currency'] for r in history):
            continue
        growths = [b['revenue']/a['revenue']-1 for a, b in zip(history, history[1:])]
        growth = min(0.30, max(-0.10, growths[-1]))
        revenue_forecast = previous['revenue']*(1+growth)
        # Test the missing-WC correction against the legacy net-capex-only rule.
        # Both rules use the same independently forecast revenue.
        if previous.get('net_capex') is None or target.get('reinvestment') is None:
            continue
        wc_ratios = [r['working_capital_investment']/r['revenue'] for r in history[-3:] if r.get('working_capital_investment') is not None]
        if not wc_ratios:
            continue
        old_ratio = max(0.0, previous['net_capex']/previous['revenue'])
        new_ratio = old_ratio + max(0.0, statistics.median(wc_ratios))
        observed = target['reinvestment']
        results.append({'symbol': symbol, 'train_through': previous['as_of'], 'holdout': target['as_of'],
                        'revenue_error': abs(revenue_forecast/target['revenue']-1),
                        'legacy_reinvestment_error': abs(old_ratio*revenue_forecast-observed)/target['revenue'],
                        'working_capital_reinvestment_error': abs(new_ratio*revenue_forecast-observed)/target['revenue'],
                        'working_capital_training_years': len(wc_ratios)})
    def med(key):
        return statistics.median(r[key] for r in results) if results else None
    def mean(key):
        return statistics.mean(r[key] for r in results) if results else None
    return {'method': 'Fixed rules; latest annual year held out; data may be restated; no historical prices, costs or returns used.',
            'n': len(results), 'median_revenue_absolute_error': med('revenue_error'),
            'median_legacy_reinvestment_error': med('legacy_reinvestment_error'),
            'median_working_capital_reinvestment_error': med('working_capital_reinvestment_error'),
            'mean_legacy_reinvestment_error': mean('legacy_reinvestment_error'),
            'mean_working_capital_reinvestment_error': mean('working_capital_reinvestment_error'),
            'cases': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--holdout', action='store_true')
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    base = ROOT/'data/processed/dcf_audit_2026-10-28'
    folder = ROOT/'data/processed/dcf_research_2026-10-28'
    evidence = folder/('holdout_cashflows' if args.holdout else 'cashflows')
    evidence.mkdir(parents=True, exist_ok=True)
    sample = json.loads(((folder/'holdout_manifest.json') if args.holdout else (base/'manifest.json')).read_text())['selection']
    if args.collect:
        pending = [r for r in sample if not (evidence/(r['symbol']+'.json')).exists()]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(fundamentals.collect, row['symbol']): row for row in pending}
            for n, future in enumerate(as_completed(jobs), 1):
                symbol = jobs[future]['symbol']
                try:
                    data = {**future.result(), 'fetched_at': datetime.now(timezone.utc).isoformat()}
                except Exception as exc:
                    data = {'symbol': symbol, 'error': f'{type(exc).__name__}: {exc}'}
                (evidence/(symbol+'.json')).write_text(json.dumps(data, indent=2, allow_nan=False))
                print(f'{n}/{len(pending)} {symbol} {data.get("error", "saved")}', flush=True)
    records = {f.stem: json.loads(f.read_text()) for f in evidence.glob('*.json')}
    validation = temporal_validation(records)
    (folder/('holdout_validation_cash_movement.json' if args.holdout else 'temporal_validation.json')).write_text(json.dumps(validation, indent=2))
    print(json.dumps({k: v for k, v in validation.items() if k != 'cases'}, indent=2), flush=True)
    growth = growth_linked_validation(records)
    (folder/('holdout_growth_linked_validation.json' if args.holdout else 'development_growth_linked_validation.json')).write_text(json.dumps(growth, indent=2))
    print(json.dumps({k: v for k, v in growth.items() if k != 'cases'}, indent=2), flush=True)


def growth_linked_validation(records):
    """Pre-specified balance-intensity candidate, evaluated without a holdout year's inputs."""
    cases = []
    for symbol, data in records.items():
        annual = sorted(data.get('annual', []), key=lambda r: r['as_of'])
        if len(annual) < 3:
            continue
        target, history = annual[-1], annual[:-1]
        prior = history[-1]
        if not target.get('currency') or any(r.get('currency') != target['currency'] for r in history):
            continue
        balances = data.get('working_capital_balances', {})
        intensities = [balances[r['as_of']]/r['revenue'] for r in history[-3:] if balances.get(r['as_of']) is not None]
        if len(intensities) < 2 or prior.get('net_capex') is None or target.get('reinvestment') is None:
            continue
        intensity = statistics.median(intensities)
        if not -1 <= intensity <= 1:
            continue
        growth = min(0.30, max(-0.10, prior['revenue']/history[-2]['revenue']-1))
        predicted_rev = prior['revenue']*(1+growth)
        baseline = max(0.0, prior['net_capex']/prior['revenue'])*predicted_rev
        candidate = baseline + intensity*(predicted_rev-prior['revenue'])
        cases.append({'symbol': symbol, 'train_through': prior['as_of'], 'test_year': target['as_of'],
                      'baseline_error': abs(baseline-target['reinvestment'])/target['revenue'],
                      'candidate_error': abs(candidate-target['reinvestment'])/target['revenue'],
                      'working_capital_ratio': intensity, 'history_years': len(intensities)})
    summary = {'n': len(cases), 'units': 'absolute reinvestment forecast error / realized revenue', 'cases': cases}
    if cases:
        for prefix in ('baseline', 'candidate'):
            summary[prefix+'_median_error'] = statistics.median(r[prefix+'_error'] for r in cases)
            summary[prefix+'_mean_error'] = statistics.mean(r[prefix+'_error'] for r in cases)
        summary['acceptance_passed'] = len(cases) >= 20 and summary['candidate_median_error'] < summary['baseline_median_error'] and summary['candidate_mean_error'] < summary['baseline_mean_error']
    else:
        summary['acceptance_passed'] = False
    return summary


if __name__ == '__main__':
    main()
