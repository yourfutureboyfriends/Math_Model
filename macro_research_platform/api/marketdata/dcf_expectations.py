"""Price-independent risk assumptions and expectations checks using the existing DCF engines."""
import math
from api.marketdata.core import NotFound


def apply_risk_basis(inp,basis='normalized',normalized_erp=.05,explicit_erp=None,discount=None):
    from api.marketdata import dcf
    if basis not in ('normalized','market_implied') or not math.isfinite(normalized_erp) or not 0<=normalized_erp<=.15:
        raise NotFound('Choose normalized or market_implied ERP and a normalized premium between 0 and 15%.')
    if explicit_erp is not None and (not math.isfinite(explicit_erp) or not 0<=explicit_erp<=.15):
        raise NotFound('Total ERP must be between 0 and 15%.')
    data=dict(inp);country=data.get('country_risk_premium') or 0
    if explicit_erp is not None:
        total=explicit_erp;label='manual_erp';source=f'User-provided total ERP {total:.2%} (including any country premium)';data['erp_is_total_override']=True
    else:
        mature=normalized_erp if basis=='normalized' else data.get('erp_implied')
        if mature is None:mature=dcf.ERP_FALLBACK
        total=mature+country;label=basis
        source=f'Normalized mature-market ERP assumption {mature:.2%}; independent of current pricing' if basis=='normalized' else (data.get('erp_implied_source') or 'Market-implied ERP unavailable: fallback assumption')
        data['erp_mature']=mature
    data.update(erp=total,erp_basis=label,erp_source=source,discount_override=discount is not None)
    return data,total


def reprice_rate_shift(v,shift):
    rows=v.get('projection') or [];a=v.get('assumptions') or {}
    if not rows or not v.get('equity_value') or v.get('per_share') is None:
        raise NotFound('Captured cash flows or positive equity value are unavailable for rate stress.')
    cumulative=1.;pv=0.
    for row in rows:
        rate=row['discount_rate']+shift
        df=cumulative/(1+rate)**(.5 if a.get('mid_year',True) else 1)
        cumulative/=1+rate;pv+=row['fcff']*df
    terminal_rate=a.get('discount_terminal',a['discount'])+shift
    growth=a['terminal_growth']
    if terminal_rate<=growth:raise NotFound('Terminal discount rate must exceed perpetual growth.')
    tv=v['terminal_fcff']/(terminal_rate-growth)
    terminal_df=cumulative*((1+terminal_rate)**.5 if a.get('mid_year',True) else 1)
    equity=pv+tv*terminal_df+(v['equity_value']-v['enterprise_value'])
    return max(0.,equity)*(v['per_share']/v['equity_value'])


def expectations(inp,valuation,overrides=None,normalized_erp=.05,implied_growth=None):
    from api.marketdata import dcf
    kw=dict(overrides or {});kw.pop('growth',None)
    allowed={'years','terminal_growth','target_margin','sales_to_capital','ronic','discount','beta','erp','tax','include_leases','mid_year','method','fade_years','ke_method','working_capital_ratio'}
    kw={k:v for k,v in kw.items() if k in allowed and v is not None}
    price=inp.get('price');a=valuation.get('assumptions') or {};rows=valuation.get('projection') or []
    findings=[]
    if inp.get('erp_implied_fallback'):findings.append('Market-implied ERP is unavailable; its comparison uses a fallback and is not an observed market premium.')
    if inp.get('discount_override'):findings.append('The manual discount rate overrides the selected premium basis in the primary valuation.')
    terminal=valuation.get('terminal_share')
    if terminal is not None and terminal>.8:findings.append('More than 80% of enterprise value depends on terminal cash flows; inspect perpetual growth, reinvestment and competitive fade.')
    cap=dcf.LR_NOMINAL_GROWTH.get(str(inp.get('currency') or '').upper())
    if cap is not None and a.get('terminal_growth',0)>cap:findings.append('Selected perpetual growth exceeds the model currency growth ceiling; this is a user assumption requiring review.')
    implied=implied_growth if implied_growth is not None else (dcf.reverse(inp,**kw) if price and price>0 else None)
    growth_gap=implied-(a.get('growth') or 0) if implied is not None else None
    normalized=dict(kw);normalized.pop('discount',None);normalized['erp']=normalized_erp+(inp.get('country_risk_premium') or 0);normalized['ke_method']='capm'
    normalized_implied=dcf.reverse(inp,**normalized) if price and price>0 else None
    grid=[]
    # Compare a range of operating outcomes under the selected discount/ERP assumptions.
    base_g=a.get('growth',inp.get('growth',0));base_margin=a.get('target_margin',inp.get('target_margin_default'))
    if base_margin is None and inp.get('revenue'):base_margin=inp['ebit']/inp['revenue']
    for delta in (-.05,0,.05):
        for md in (-.05,0,.05):
            growth=max(-.5,min(2.,base_g+delta));margin=max(-1.,min(.9,base_margin+md)) if base_margin is not None else None
            data=dict(inp);data['growth']=growth
            data['growth_y1']=max(-.5,min(2.,(a.get('growth_y1',base_g)+delta)))
            args=dict(kw)
            if md or (overrides or {}).get('target_margin') is not None:args['target_margin']=margin
            try:
                v=dcf.value(data,**args);value=v.get('per_share')
                grid.append({'growth':growth,'margin':margin,'per_share':value,'upside':value/price-1 if value is not None and price and price>0 else None})
            except NotFound as e:grid.append({'growth':growth,'margin':margin,'per_share':None,'error':str(e)})
    base_rate=a.get('discount');duration=[]
    for bump in (.01,.02):
        try:
            if base_rate is None:continue
            value=reprice_rate_shift(valuation,bump)
            duration.append({'rate_increase':bump,'discount':base_rate+bump,'per_share':value,'change_vs_base':value/valuation['per_share']-1 if value is not None and valuation.get('per_share',0)>0 else None})
        except NotFound as e:duration.append({'rate_increase':bump,'per_share':None,'error':str(e)})
    # A bounded implied-margin solve can fail where reinvestment makes the response nonlinear.
    lo,hi=-.1,.8;implied_margin=None
    if price and price>0:
        margin_data=dict(inp);margin_data.update(growth=base_g,growth_y1=a.get('growth_y1',base_g))
        def gap(m):return dcf.value(margin_data,**{**kw,'target_margin':m})['per_share']-price
        try:
            low,high=gap(lo),gap(hi)
            if low*high<=0:
                for _ in range(45):
                    mid=(lo+hi)/2;g=gap(mid)
                    if (g>0)==(high>0):hi,high=mid,g
                    else:lo,low=mid,g
                implied_margin=(lo+hi)/2
        except (NotFound,TypeError):pass
    if implied_margin is not None and base_margin is not None and implied_margin>base_margin+.05:findings.append('Price requires a long-run operating margin over five percentage points above the selected case, holding other drivers fixed.')
    if growth_gap is not None and growth_gap>.05:findings.append('Price requires revenue growth over five percentage points above the selected case, holding other drivers fixed.')
    return {'price':price,'currency':inp.get('price_currency'),'cashflow_currency':inp.get('currency'),'country':inp.get('country'),
            'risk_basis':inp.get('erp_basis'),'risk_free':inp.get('risk_free'),'erp':kw.get('erp',inp.get('erp')),
            'market_implied_mature_erp':inp.get('erp_implied'),'market_implied_source':inp.get('erp_implied_source'),'market_implied_as_of':inp.get('erp_implied_as_of'),'normalized_mature_erp':normalized_erp,
            'implied_growth':implied,'implied_growth_normalized':normalized_implied,'selected_growth':a.get('growth'),'growth_gap':growth_gap,
            'implied_margin':implied_margin,'selected_margin':base_margin,'terminal_share':terminal,'currency_growth_ceiling':cap,
            'grid':grid,'rate_stress':duration,'findings':findings,
            'method':'Rate shocks shift every captured discount rate in parallel, holding operating cash flows fixed. Reverse DCF solves one operating driver at a time. Growth/margin grid and rate shocks are deterministic scenarios, not probabilities or confidence intervals. Implied growth and margin are alternative explanations, not jointly required targets. No regional valuation haircut or market-price calibration is applied.'}
