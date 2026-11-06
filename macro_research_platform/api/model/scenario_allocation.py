"""Constrained expected-case versus worst-scenario research allocation, never order generation."""
import numpy as np


def compare(assets,covariance,scenarios,baseline,max_weight,volatility_ceiling,risk_aversion,turnover_penalty):
    from scipy.optimize import minimize
    n=len(assets);cov=np.asarray(covariance,dtype=float);prior=np.asarray(baseline,dtype=float)
    if len(set(assets))!=n or cov.shape!=(n,n) or prior.shape!=(n,):raise ValueError('Unique asset names and matching covariance/baseline dimensions required')
    if not np.isfinite(cov).all() or not np.isfinite(prior).all() or (prior<0).any() or prior.sum()>1+1e-10:raise ValueError('Finite inputs and nonnegative baseline weights summing to at most one required')
    if not np.allclose(cov,cov.T):raise ValueError('Annual covariance must be symmetric')
    try:np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as e:raise ValueError('Annual covariance must be positive definite') from e
    means=np.asarray([s['annual_returns'] for s in scenarios],dtype=float);cash=np.asarray([s['cash_return'] for s in scenarios])
    if means.shape!=(len(scenarios),n):raise ValueError('Each scenario needs an annual return for every asset')
    probs=np.asarray([s['probability'] for s in scenarios])
    if not np.isclose(probs.sum(),1,rtol=0,atol=1e-8):raise ValueError('Analyst scenario probabilities must sum to one')
    def returns(w):return means@w+cash*(1-w.sum())
    def summarize(w):
        r=returns(w)
        return {'weights':{a:float(x) for a,x in zip(assets,w)},'cash_weight':float(1-w.sum()),
                'annual_volatility':float(np.sqrt(max(0,w@cov@w))),'expected_annual_return':float(probs@r),
                'worst_scenario_return':float(r.min()),'one_way_weight_change':float(abs(w-prior).sum()),
                'scenarios':[{'name':s['name'],'portfolio_return':float(value)} for s,value in zip(scenarios,r)]}
    results={'baseline':summarize(prior)}
    x0=np.minimum(prior,max_weight)
    if x0.sum()>1:x0/=x0.sum()
    vol=float(np.sqrt(x0@cov@x0))
    if vol>volatility_ceiling:x0*=volatility_ceiling/vol
    for mode in ('expected_case','worst_scenario'):
        w0=np.r_[x0,float(returns(x0).min())]
        def objective(x):
            w=x[:n];reward=float(probs@returns(w)) if mode=='expected_case' else x[-1]
            cost=turnover_penalty*np.sqrt((w-prior)**2+1e-16).sum()
            return -reward+.5*risk_aversion*(w@cov@w)+cost
        constraints=[{'type':'ineq','fun':lambda x:1-x[:n].sum()},
                     {'type':'ineq','fun':lambda x:volatility_ceiling**2-x[:n]@cov@x[:n]}]
        if mode=='worst_scenario':constraints.append({'type':'ineq','fun':lambda x:returns(x[:n])-x[-1]})
        opt=minimize(objective,w0,method='SLSQP',bounds=[(0,max_weight)]*n+[(-2,2)],constraints=constraints,
                     options={'maxiter':500,'ftol':1e-10})
        feasible=opt.success and opt.x[:n].sum()<=1+1e-7 and opt.x[:n]@cov@opt.x[:n]<=volatility_ceiling**2+1e-7
        results[mode]=summarize(opt.x[:n]) if feasible else {'available':False,'reason':'Constrained solver did not produce a verified feasible solution; no fallback allocation supplied'}
    return {'portfolios':results,'scenario_probabilities':{s['name']:s['probability'] for s in scenarios},
            'risk_basis':'Supplied annual nominal base-currency covariance; cash treated as riskless in this approximation',
            'note':'Research allocations from analyst-supplied scenarios/covariance, not calibrated institutional forecasts. Long-only, no leverage, explicit cash, per-asset cap and volatility ceiling. Expected-case uses supplied probabilities; worst-scenario uses the minimum across supplied cases, not all possible outcomes or a most-probable stress. Turnover is an objective penalty, not observed execution cost. No holdings, trades or live model settings are changed.'}
