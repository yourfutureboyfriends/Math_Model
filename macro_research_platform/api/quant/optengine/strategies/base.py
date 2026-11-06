from __future__ import annotations
from itertools import product
import numpy as np
from ..schema import DataError, Leg, Opportunity, utc

def candidates(chain,kind,target,tolerance,expiry):
    matches=[q for q in chain if q.option_type==kind and q.expiry==expiry and abs(abs(q.delta)-target)<=tolerance]
    return sorted(matches,key=lambda q:(abs(abs(q.delta)-target),(q.ask-q.bid)/max(q.mid,1e-9),-q.open_interest,q.contract_id))[:3]

def expiries(chain,asof,cfg):
    dates={q.expiry for q in chain if cfg.min_dte<=q.dte(asof)<=cfg.max_dte}
    middle=(cfg.min_dte+cfg.max_dte)/2
    return sorted(dates,key=lambda e:(abs((utc(e)-utc(asof)).total_seconds()/86400-middle),e))[:2]

def valid_legs(legs):
    if len({l.quote.contract_id for l in legs})!=len(legs):return False
    return len({(l.quote.underlying,l.quote.expiry,l.quote.currency,l.quote.multiplier,l.quote.exercise,l.quote.settlement) for l in legs})==1

def payoff(legs,spots):
    spots=np.asarray(spots,float)
    out=np.zeros_like(spots)
    for l in legs:
        q=l.quote
        intrinsic=np.maximum(spots-q.strike,0) if q.option_type=="call" else np.maximum(q.strike-spots,0)
        out+=l.quantity*q.multiplier*intrinsic
    return out

def bounds(legs):
    if not valid_legs(legs):raise DataError("Mismatched spread legs")
    slope=sum(l.quantity*l.quote.multiplier for l in legs if l.quote.option_type=="call")
    if slope!=0:raise DataError("Unbounded upper-tail option payoff")
    strikes=sorted({l.quote.strike for l in legs})
    values=payoff(legs,[0]+strikes+[max(strikes)*2])
    return float(values.min()),float(values.max())

def pairs(name,chain,asof,feature,regime,cfg,kind,targets,quantities,ordered):
    out=[]
    for expiry in expiries(chain,asof,cfg):
        options=[candidates(chain,kind,target,cfg.delta_tolerance,expiry) for target in targets]
        for quotes in product(*options):
            if not ordered(quotes):continue
            legs=tuple(Leg(q,n) for q,n in zip(quotes,quantities))
            if valid_legs(legs):out.append(Opportunity(name,quotes[0].underlying,legs,asof,feature,regime))
    return out
