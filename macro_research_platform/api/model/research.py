"""Bounded, read-only vintage comparison; never changes model orders or live allocations."""
import asyncio
from datetime import datetime,timezone
import pandas as pd
from api.model import vintages
from api.model.data import MACRO_SERIES, build_macro_panel
from api.model.core import ModelParams
from api.model.backtest import run_backtest


async def compare_vintages(start, end,research_challengers=False):
    start=pd.Timestamp(start);end=pd.Timestamp(end)
    if start.day!=1 or end.day!=1:raise ValueError('Use month starts (YYYY-MM-01)')
    span=(end.year-start.year)*12+end.month-start.month
    if not 1<=span<=24:raise ValueError('Choose between 1 and 24 evaluation months')
    if end>=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp():raise ValueError('Only completed evaluation months are supported')
    from api.model.economies import get
    e=get('us')
    history,errors=await vintages.load_history()
    if errors:return {'available':False,'reason':'Complete configured macro vintage coverage is required; no revised-data fallback was used','source_errors':errors}
    from api.providers.alfred import CACHE
    source_caches=[]
    for sid in MACRO_SERIES:
        path=CACHE/f'{sid}_intervals_v1_1965-01-01.json'
        source_caches.append({'series':sid,'cache_saved_at':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat() if path.exists() else None})
    try:raw,returns=await e.loader()
    except Exception:return {'available':False,'reason':'Asset/return source history is unavailable; no return series was invented'}
    if returns.empty:return {'available':False,'reason':'No asset-return history available for the requested comparison'}
    rets=returns.loc[returns.index<=end].replace([float('inf'),float('-inf')],float('nan')).dropna(how='all')
    if rets.empty:return {'available':False,'reason':'No finite return observations through the evaluation end date'}
    from api.workflows.evidence import digest
    import math
    returns_hash=digest({'columns':list(rets.columns),'observations':[{'month':t.strftime('%Y-%m'),
                         'values':[float(v) if math.isfinite(v) else None for v in row]} for t,row in rets.iterrows()]})
    panels={};metadata=[]
    def at(t):
        key=pd.Timestamp(t).strftime('%Y-%m')
        if key not in panels:
            cutoff=(pd.Timestamp(t)+pd.offsets.MonthEnd(0)).date().isoformat()
            panels[key],meta=vintages.panel_at(history,cutoff)
            metadata.append(meta)
        return panels[key]
    final=at(end)
    revised=build_macro_panel(raw,MACRO_SERIES).loc[:end]
    p=ModelParams();blocks=e.blocks()
    # Identical return series and model parameters; only macro data basis differs.
    pit=await asyncio.to_thread(run_backtest,final,rets,blocks,e.env(),p,start,e.anchors,e.benchmark,
                                 'Current adjusted proxy histories and revised cash-rate history; macro inputs are vintage-selected',at,research_challengers)
    baseline=await asyncio.to_thread(run_backtest,revised,rets,blocks,e.env(),p,start,e.anchors,e.benchmark)
    bymonth={r['month']:r for r in baseline.get('timeline',[])}
    changes=[]
    vintage_returns={r['month']:r['net'] for r in pit.get('monthly_returns',[])}
    revised_returns={r['month']:r['net'] for r in baseline.get('monthly_returns',[])}
    for row in pit.get('timeline',[]):
        other=bymonth.get(row['month'])
        if other:changes.append({'month':row['month'],'vintage_growth_probability':row['p_g'],'revised_growth_probability':other['p_g'],
                                'vintage_inflation_probability':row['p_i'],'revised_inflation_probability':other['p_i'],
                                'regime_changed':row['top']!=other['top'],
                                'vintage_net_return':vintage_returns.get(row['month']),'revised_net_return':revised_returns.get(row['month'])})
    dates=sorted(m['cutoff'] for m in metadata)
    evidence=[vintages.changes_between(history,a,b) for a,b in zip(dates[:-1],dates[1:])]
    expected=[m.strftime('%Y-%m') for m in pd.date_range(start+pd.offsets.MonthBegin(1),end,freq='MS')]
    common=vintage_returns.keys() & revised_returns.keys()
    return {'available':pit.get('available',False),'reason':pit.get('reason'),'vintage':pit,'revised':baseline,'comparison':changes,'vintages':metadata,
            'common_scored_months':len(common),'requested_evaluation_months':len(expected),
            'unscored_target_months':[m for m in expected if m not in common],
            'release_change_evidence':evidence,
            'source_cache_evidence':source_caches,'fresh_upstream_verification':False,
            'returns_input_sha256':returns_hash,
            'macro_vintage_selected':True,'full_investment_backtest_point_in_time_verified':False,
            'note':'US monthly research only. ALFRED daily availability, completed observation months and earliest archived availability-month alignment; archive start dates do not always establish original publication dates. Revised comparison uses existing approximate lags, so differences combine vintage and alignment effects. Asset/FX/cash histories are not archived point-in-time. Final factor labels can change with re-estimation; small-sample probability diagnostics are descriptive. No live allocation, order or monitoring setting was changed.'}
