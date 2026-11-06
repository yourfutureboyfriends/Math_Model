"""Pure FCFF scenario engine: explicit risks, price-implied expectations and weighted values.

Rates are decimals; every amount, share price and equity bridge uses one currency and
one share class. No network calls, automatic price fitting, or regional classification.
Regional presets are analyst assumptions, not observed required returns. Run the example:
    python -m api.marketdata.dcf_scenarios
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import math
from typing import Sequence
import numpy as np
import pandas as pd


def finite(name,value,low=None,high=None):
    if isinstance(value,bool) or not isinstance(value,(int,float,np.number)) or not math.isfinite(value):raise ValueError(f'{name} must be finite')
    if low is not None and value<low or high is not None and value>high:raise ValueError(f'{name} outside supported range')
    return float(value)


@dataclass(frozen=True)
class RiskAssumptions:
    risk_free: float=.04
    beta: float=1.
    market_risk_premium: float=.045
    country_risk_premium: float=0.
    governance_risk_premium: float=0.
    cost_of_debt: float=.055
    tax_rate: float=.25
    equity_weight: float=1.
    debt_weight: float=0.
    equity_floor: float=0.


def cost_of_capital(risk: RiskAssumptions) -> dict:
    """Ke = rf + beta*MRP + CRP + GRP; WACC uses after-tax debt and market weights.

    CRP/GRP are additive (not beta-scaled). Avoid adding risks already embedded in
    cash-flow haircuts. Buybacks are distributions of value, not a second FCFF asset.
    """
    r=asdict(risk)
    for key,v in r.items():finite(key,v,-.5 if key=='risk_free' else -1 if key=='beta' else 0,5 if key=='beta' else 1)
    if not math.isclose(risk.equity_weight+risk.debt_weight,1,abs_tol=1e-9):raise ValueError('Capital weights must sum to one')
    systematic=risk.beta*risk.market_risk_premium
    model=risk.risk_free+systematic+risk.country_risk_premium+risk.governance_risk_premium
    ke=max(model,risk.equity_floor);kd=risk.cost_of_debt*(1-risk.tax_rate)
    return {**r,'systematic_premium':systematic,'cost_of_equity_model':model,'cost_of_equity':ke,
            'cost_of_debt_after_tax':kd,'wacc':risk.equity_weight*ke+risk.debt_weight*kd,
            'equity_floor_applied':ke>model}


REGIONAL_PRESETS={
 'western_tech':{'country_risk_premium':0.,'governance_risk_premium':0.,'reference_wacc_band':[.075,.095],
                 'note':'Illustrative stable-institution scenario. A high beta or local-currency rate can put calculated WACC outside this band; no automatic clamp or buyback discount.'},
 'china_structural':{'country_risk_premium':.03,'governance_risk_premium':.02,'reference_wacc_band':[.12,.15],
                 'note':'Illustrative 5 percentage-point localized equity premium: 3pt country plus 2pt governance. VIE exposure must be established for the actual entity; no automatic nationality inference.'},
}


def regional_risk(risk:RiskAssumptions,profile:str,localized_premium:float|None=None,governance_share:float=.4):
    """Apply an opt-in research preset, replacing (not stacking on) existing CRP/GRP.

    The China localized-premium assumption can be set in the requested 4–6pt range.
    Its effect on WACC is equity-weighted, not necessarily the full 4–6pt.
    """
    if profile not in REGIONAL_PRESETS:raise ValueError('Unknown regional profile')
    preset=REGIONAL_PRESETS[profile]
    crp,grp=preset['country_risk_premium'],preset['governance_risk_premium']
    if localized_premium is not None:
        finite('localized_premium',localized_premium,.04,.06);finite('governance_share',governance_share,0,1)
        if profile!='china_structural':raise ValueError('Localized premium applies to the China structural scenario')
        crp,grp=localized_premium*(1-governance_share),localized_premium*governance_share
    selected=replace(risk,country_risk_premium=crp,governance_risk_premium=grp)
    cost_of_capital(selected)
    return selected,{**preset,'profile':profile,'country_risk_premium':crp,'governance_risk_premium':grp,'basis':'explicit analyst scenario assumption'}


@dataclass(frozen=True)
class FCFModel:
    base_fcf: float
    growth: float
    years: int
    terminal_growth: float
    shares: float
    market_price: float
    net_debt: float=0.
    other_equity_assets: float=0.
    mid_year: bool=False

    def validate(self):
        if not isinstance(self.mid_year,bool):raise ValueError('mid_year must be boolean')
        for key,v in asdict(self).items():
            if key=='mid_year':continue
            finite(key,v)
        if isinstance(self.years,bool) or int(self.years)!=self.years or not 1<=self.years<=50:raise ValueError('Use 1–50 whole forecast years')
        if self.base_fcf<=0:raise ValueError('Constant FCF growth requires positive normalized FCFF; use an explicit turnaround cash-flow path otherwise')
        if self.shares<=0 or self.market_price<=0:raise ValueError('Positive shares and market price are required')
        if self.growth<=-1 or self.terminal_growth<=-1:raise ValueError('Growth must exceed -100%')


def price_cashflows(cashflows:Sequence[float],terminal_fcf:float,wacc:float,terminal_growth:float,shares:float,
                    net_debt:float=0.,other_equity_assets:float=0.,mid_year:bool=False)->dict:
    """Discount a fixed unlevered path. Terminal FCFF is year N+1, not year N.

    Annual cash flows use year-end timing by default. Mid-year is explicit and applied
    consistently to both forecast and continuing cash flows. Negative FCFF is retained.
    """
    cf=np.asarray(cashflows,dtype=float)
    if cf.ndim!=1 or not 1<=cf.size<=100 or not np.all(np.isfinite(cf)):raise ValueError('Supply 1–100 finite annual FCFF observations')
    for k,v in [('terminal_fcf',terminal_fcf),('wacc',wacc),('terminal_growth',terminal_growth),('shares',shares),('net_debt',net_debt),('other_equity_assets',other_equity_assets)]:finite(k,v)
    if shares<=0 or wacc<=-1 or terminal_growth<=-1 or wacc-terminal_growth<.005-1e-12:raise ValueError('Positive shares and WACC at least 0.5pt above terminal growth are required')
    t=np.arange(1,cf.size+1,dtype=float)-(.5 if mid_year else 0.)
    df=np.power(1+wacc,-t);pv=cf*df
    terminal_value=terminal_fcf/(wacc-terminal_growth);pv_terminal=terminal_value*df[-1]
    enterprise=float(pv.sum()+pv_terminal);raw_equity=enterprise-net_debt+other_equity_assets;equity=max(0.,raw_equity)
    if not all(math.isfinite(v) for v in (enterprise,raw_equity,equity/shares,float(pv_terminal))):raise ValueError('Valuation magnitude exceeds finite numeric limits')
    return {'enterprise_value':enterprise,'equity_value_raw':raw_equity,'equity_value':equity,'per_share':equity/shares,
            'pv_explicit':float(pv.sum()),'pv_terminal':float(pv_terminal),'terminal_value':terminal_value,
            'terminal_share':float(pv_terminal/enterprise) if enterprise>0 else None,'wacc':wacc,'terminal_growth':terminal_growth,
            'cashflows':cf.tolist(),'discount_factors':df.tolist(),'present_values':pv.tolist()}


def value_fcf(model:FCFModel,wacc:float)->dict:
    """Explicit constant FCFF CAGR followed by a separate sustainable terminal rate."""
    model.validate()
    cf=model.base_fcf*np.power(1+model.growth,np.arange(1,model.years+1))
    return price_cashflows(cf,float(cf[-1]*(1+model.terminal_growth)),wacc,model.terminal_growth,model.shares,model.net_debt,model.other_equity_assets,model.mid_year)


def solve_bounded(fn,low,high,*,points=101,tolerance=1e-8)->dict:
    """Bracket valid roots, report ambiguity; never return a bound as a solved value."""
    finite('lower bound',low);finite('upper bound',high)
    if low>=high:raise ValueError('Root bounds must be increasing')
    grid=np.linspace(low,high,points);pairs=[];roots=[];previous=None
    for x in grid:
        try:y=float(fn(float(x)))
        except (ValueError,OverflowError,ZeroDivisionError):previous=None;continue
        if not math.isfinite(y):previous=None;continue
        if abs(y)<=tolerance:roots.append(float(x))
        elif previous is not None and previous[1]*y<0:pairs.append((previous[0],float(x),previous[1]))
        previous=(float(x),y)
    for lo,hi,flo in pairs:
        for _ in range(100):
            mid=(lo+hi)/2;fm=fn(mid)
            if abs(fm)<=tolerance or hi-lo<1e-12:break
            if flo*fm<=0:hi=mid
            else:lo,flo=mid,fm
        roots.append(mid)
    unique=[]
    for r in sorted(roots):
        if not unique or abs(r-unique[-1])>1e-7:unique.append(r)
    return {'value':unique[0] if len(unique)==1 else None,'status':'solved' if len(unique)==1 else 'multiple_roots' if unique else 'no_root_in_bounds',
            'roots':unique,'bounds':[low,high],'residual':float(fn(unique[0])) if len(unique)==1 else None,
            'search':'Finite-grid bracketing plus bisection; tangential roots and invalid discontinuities may remain unresolved.'}


def reverse_dcf(model:FCFModel,wacc:float,growth_bounds=(-.6,1.5),wacc_bounds=(.005,.6))->dict:
    """Alternative one-driver price explanations, never a joint growth/risk estimate.

    Implied WACC holds forecast FCFF and terminal FCFF fixed. Implied explicit growth
    holds discount/terminal rates fixed. Implied perpetual growth is separately solved
    holding the forecast path fixed. Every solve reports bounds and repricing error.
    """
    model.validate();base=value_fcf(model,wacc)
    explicit=solve_bounded(lambda g:value_fcf(replace(model,growth=g),wacc)['per_share']-model.market_price,*growth_bounds)
    rate=solve_bounded(lambda r:price_cashflows(base['cashflows'],base['cashflows'][-1]*(1+model.terminal_growth),r,model.terminal_growth,model.shares,model.net_debt,model.other_equity_assets,model.mid_year)['per_share']-model.market_price,max(wacc_bounds[0],model.terminal_growth+.0050001),wacc_bounds[1])
    perpetual=solve_bounded(lambda g:price_cashflows(base['cashflows'],base['cashflows'][-1]*(1+g),wacc,g,model.shares,model.net_debt,model.other_equity_assets,model.mid_year)['per_share']-model.market_price,-.05,min(.06,wacc-.0050001))
    return {'implied_fcf_cagr':explicit,'implied_wacc':rate,'implied_terminal_growth':perpetual,'forecast_years':model.years,
            'interpretation':'Each metric is conditional on all other entered assumptions; implied WACC is not an independently observed discount rate.'}


@dataclass(frozen=True)
class Scenario:
    name:str
    probability:float
    growth_shift:float=0.
    wacc_shift:float=0.
    fcf_multiplier:float=1.


DEFAULT_SCENARIOS=(Scenario('Bear',.25,-.05,.02,.9),Scenario('Base',.5),Scenario('Bull',.25,.05,-.01,1.1))


def scenario_matrix(model:FCFModel,risk:RiskAssumptions,scenarios:Sequence[Scenario]=DEFAULT_SCENARIOS,*,wacc_override:float|None=None)->dict:
    """Probability-weighted per-share values; invalid cases are not dropped/reweighted.

    Probabilities are analyst inputs and must sum to one. A WACC override (e.g. 8.5%
    institutional-premium thesis) is explicitly reported beside the calculated WACC.
    """
    model.validate();capital=cost_of_capital(risk)
    if not scenarios or len(scenarios)>30 or len({s.name for s in scenarios})!=len(scenarios):raise ValueError('Use 1–30 uniquely named scenarios')
    for s in scenarios:
        finite('probability',s.probability,0,1);finite('growth_shift',s.growth_shift);finite('wacc_shift',s.wacc_shift);finite('fcf_multiplier',s.fcf_multiplier,0)
    if not math.isclose(sum(s.probability for s in scenarios),1,abs_tol=1e-9):raise ValueError('Scenario probabilities must sum to one')
    rate=capital['wacc'] if wacc_override is None else finite('wacc_override',wacc_override,0,1)
    rows=[]
    for s in scenarios:
        try:
            m=replace(model,growth=model.growth+s.growth_shift,base_fcf=model.base_fcf*s.fcf_multiplier)
            valuation=value_fcf(m,rate+s.wacc_shift)
            rows.append({'scenario':s.name,'probability':s.probability,'fcf_growth':m.growth,'wacc':rate+s.wacc_shift,'per_share':valuation['per_share'],
                         'enterprise_value':valuation['enterprise_value'],'equity_value':valuation['equity_value'],'terminal_share':valuation['terminal_share'],
                         'weighted_value':s.probability*valuation['per_share'],'upside':valuation['per_share']/model.market_price-1,'status':'calculated'})
        except ValueError as e:rows.append({'scenario':s.name,'probability':s.probability,'per_share':None,'weighted_value':None,'status':str(e)})
    complete=all(r['per_share'] is not None or r['probability']==0 for r in rows)
    expected=sum(r['weighted_value'] or 0 for r in rows) if complete else None
    return {'risk':capital,'applied_base_wacc':rate,'wacc_override':wacc_override,'matrix':pd.DataFrame(rows),
            'expected_value':expected,'expected_upside':expected/model.market_price-1 if expected is not None else None,
            'complete_probability_mass':complete,'reverse':reverse_dcf(model,rate),
            'note':'Scenario probabilities and regional premiums are assumptions. Weighted value is not a confidence interval. No automatic institutional/buyback haircut or VIE inference.'}


if __name__=='__main__':
    # Synthetic, identical business in one currency: isolate risk, not a live stock claim.
    model=FCFModel(base_fcf=100.,growth=.12,years=9,terminal_growth=.025,shares=10.,market_price=250.)
    for profile in REGIONAL_PRESETS:
        risk,metadata=regional_risk(RiskAssumptions(),profile)
        report=scenario_matrix(model,risk)
        print('\n'+profile+' — illustrative inputs only')
        print(report['matrix'].to_string(index=False))
        print('Expected value:',report['expected_value'])
        print('Market implied metrics:',report['reverse'])


def operating_scenarios(inp:dict,overrides:dict|None=None,probabilities:dict|None=None,profile:str='reported',localized_premium:float=.05,
                        governance_premium:float|None=None)->dict:
    """Adapter for the application's revenue/margin/reinvestment FCFF forecast.

    Retains existing sector-specific reinvestment, FX, diluted-share and equity-bridge
    treatment. Reverse FCFF CAGR is intentionally a separate normalized-FCFF model;
    this adapter reports revenue-growth expectations and fixed-path implied WACC.
    """
    from api.marketdata import dcf
    allowed={'growth','terminal_growth','years','target_margin','sales_to_capital','ronic','discount','beta','erp','tax','include_leases','mid_year','method','fade_years','ke_method','working_capital_ratio'}
    kw={k:v for k,v in (overrides or {}).items() if k in allowed and v is not None}
    data=dict(inp);components=dcf.equity_risk_components(data,kw.get('beta',data.get('beta') if data.get('beta') is not None else 1.),kw.get('erp'))
    profile_info={'profile':'reported','basis':'reported country risk plus explicit governance assumption'}
    if profile!='reported':
        chosen,profile_info=regional_risk(RiskAssumptions(),profile,localized_premium if profile=='china_structural' else None)
        data.update(country_risk_premium=chosen.country_risk_premium,governance_risk_premium=chosen.governance_risk_premium)
    if governance_premium is not None:data['governance_risk_premium']=finite('governance_premium',governance_premium,0,.2)
    kw['erp']=components['market_risk_premium']+(data.get('country_risk_premium') or 0.)
    kw['ke_method']='capm'
    p=probabilities if probabilities is not None else {'bear':.25,'base':.5,'bull':.25}
    if set(p)!={'bear','base','bull'}:raise ValueError('Specify bear, base and bull probabilities')
    for probability in p.values():finite('probability',probability,0,1)
    if not math.isclose(sum(p.values()),1,abs_tol=1e-9):raise ValueError('Scenario probabilities must sum to one')
    baseline=dcf.value(data,**kw);rate=baseline['assumptions']['discount']
    growth=kw.get('growth',data.get('growth',0.));g1=kw.get('growth',data.get('growth_y1',growth))
    margin=kw.get('target_margin',data.get('target_margin_default'))
    if margin is None:margin=data['ebit']/data['revenue']
    shifts={'bear':{'growth':-.05,'margin':-.03,'wacc':.02},'base':{'growth':0.,'margin':0.,'wacc':0.},'bull':{'growth':.05,'margin':.02,'wacc':-.01}}
    rows=[]
    for name,shift in shifts.items():
        d=dict(data);args=dict(kw)
        d['growth']=max(-.5,min(2.,growth+shift['growth']));d['growth_y1']=max(-.5,min(2.,g1+shift['growth']))
        args.pop('growth',None)
        if shift['margin']:args['target_margin']=max(-1.,min(.9,margin+shift['margin']))
        if shift['wacc']:args['discount']=rate+shift['wacc']
        try:
            v=dcf.value(d,**args);price=v.get('price');per=v['per_share']
            rows.append({'scenario':name,'probability':p[name],'growth':d['growth'],'wacc':v['assumptions']['discount'],
                'terminal_wacc':v['assumptions']['discount_terminal'],'per_share':per,'enterprise_value':v['enterprise_value'],
                'weighted_value':p[name]*per if per is not None else None,'upside':per/price-1 if per is not None and price and price>0 else None,'error':None})
        except dcf.NotFound as exc:rows.append({'scenario':name,'probability':p[name],'per_share':None,'weighted_value':None,'error':str(exc)})
    complete=all(r['per_share'] is not None or r['probability']==0 for r in rows)
    expected=sum(r['weighted_value'] or 0 for r in rows) if complete else None
    model_price=baseline.get('price')
    return {'profile':profile_info,'risk':baseline['wacc'],'matrix':rows,'expected_value':expected,
        'expected_upside':expected/model_price-1 if expected is not None and model_price and model_price>0 else None,'complete_probability_mass':complete,
        'reverse_revenue_growth':dcf.reverse(data,**{k:v for k,v in kw.items() if k!='growth'}),
        'reverse_fixed_cashflow_wacc':dcf.implied_discount(data,**kw),'cashflow_currency':data.get('currency'),'quote_currency':data.get('price_currency'),
        'forecast_years':baseline['assumptions']['years'],'scenario_shifts':shifts,
        'note':'Analyst probabilities and regional premiums are assumptions, not forecasts or empirical confidence levels. Revenue growth is not FCFF growth. Reverse WACC holds the selected forecast and terminal FCFF fixed. Base preserves the selected rate path; bear/bull apply flat shifted rates. Buybacks do not automatically lower WACC. No price fitting or automatic VIE classification.'}
