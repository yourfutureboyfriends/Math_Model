"""Explain the data actually used by a monthly macro decision, without forecasting accuracy claims."""
import numpy as np
import pandas as pd


def decision_quality(coverage, decision, as_of, returns, now=None, anchors=None):
    now=pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz='UTC').tz_localize(None)
    month=now.to_period('M').to_timestamp();as_of=pd.Timestamp(as_of)
    age=max(0,(month.year-as_of.year)*12+month.month-as_of.month-1)
    loadings=decision.loadings;drivers=[];blocks={}
    for row in coverage:
        actual=row['key'] in loadings.get(row['block'],{})
        row['eligible']=row['used'];row['used']=actual
        if not actual and not row.get('exclusion_reason'):row['exclusion_reason']='Insufficient usable history, zero variance or missing factor coverage'
    for block,factor in (('growth',decision.growth),('inflation',decision.inflation)):
        latest=factor.index[-1];eligible=[r for r in coverage if r['block']==block and r['used']]
        observed=[r for r in eligible if r.get('available_month')==pd.Timestamp(latest).strftime('%Y-%m')]
        blocks[block]={'used_series':len(eligible),'observed_at_factor_month':len(observed),'factor_month':pd.Timestamp(latest).strftime('%Y-%m')}
    for block,values in loadings.items():
        for key,loading in sorted(values.items(),key=lambda x:-abs(x[1]))[:4]:
            row=next((r for r in coverage if r['key']==key),{})
            drivers.append({'key':key,'label':row.get('label',key),'block':block,'loading':loading,'latest_transformed':row.get('latest_transformed'),'available_month':row.get('available_month'),'note':'Loading measures factor association, not causality or an investment return contribution.'})
    excluded_assets=[a for a in returns.columns if a not in decision.assets]
    warnings=[]
    if anchors:
        for block,anchor in zip(('growth','inflation'),anchors):
            if anchor not in loadings.get(block,{}):warnings.append(f'{block.capitalize()} sign anchor {anchor} is unavailable; orientation uses the largest absolute loading instead.')
    if excluded_assets:warnings.append("Asset proxies excluded for insufficient history or missing latest returns: "+", ".join(excluded_assets))
    if age:warnings.append(f'The return/decision base is {age} completed month(s) behind the latest completed calendar month.')
    if any(not r['used'] for r in coverage):warnings.append('Some configured inputs were excluded; inspect coverage before interpreting the factors.')
    if any(b['observed_at_factor_month']<b['used_series'] for b in blocks.values()):warnings.append('The latest factor uses a ragged data edge: some inputs are absent and contribute their standardized mean, not new observations.')
    if any(pd.Timestamp(b['factor_month'])<as_of for b in blocks.values()):warnings.append('A factor ends before the decision month; the latest regime forecast is unavailable.')
    if any(not np.isfinite(float(x)) for x in decision.regime_probs.values()):warnings.append('Regime probabilities are not finite.')
    return {'status':'stale' if age or any(pd.Timestamp(b['factor_month'])<as_of for b in blocks.values()) else 'review_required' if warnings else 'checks_clear',
            'decision_month':as_of.strftime('%Y-%m'),'target_month':(as_of+pd.offsets.MonthBegin()).strftime('%Y-%m'),'completed_months_behind':age,
            'used_assets':len(decision.assets),'configured_assets':len(returns.columns),'excluded_assets':excluded_assets,'used_inputs':sum(r['used'] for r in coverage),'configured_inputs':len(coverage),'blocks':blocks,'drivers':drivers,'warnings':warnings,
            'vintage_basis':'latest_revised_with_approximate_publication_lags','point_in_time_verified':False,
            'interpretation':'Factors are standardized growth/inflation indicators, not GDP or CPI forecasts. Direction probabilities are model estimates, not calibrated certainty. Historical tests use revised data and approximate monthly release lags; they are not vintage-accurate real-time backtests. Availability checks do not independently verify a fresh upstream fetch; loaders may serve saved observations.'}
