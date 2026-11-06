from itertools import product
from ..schema import Leg, Opportunity
from .base import candidates,expiries,valid_legs

def build(chain,asof,feature,regime,cfg):
    out=[]
    for expiry in expiries(chain,asof,cfg):
        sets=[candidates(chain,kind,target,cfg.delta_tolerance,expiry) for kind,target in (("put",cfg.wing_delta),("put",cfg.short_delta),("call",cfg.short_delta),("call",cfg.wing_delta))]
        for quotes in product(*sets):
            if not quotes[0].strike<quotes[1].strike<feature["spot"]<quotes[2].strike<quotes[3].strike:continue
            legs=tuple(Leg(q,n) for q,n in zip(quotes,(1,-1,-1,1)))
            if valid_legs(legs):out.append(Opportunity("iron_condor",quotes[0].underlying,legs,asof,feature,regime))
    return out
