from .base import pairs

def build(chain,asof,feature,regime,cfg):
    return pairs("bull_call",chain,asof,feature,regime,cfg,"call",(cfg.long_delta,cfg.short_delta),(1,-1),lambda q:q[0].strike<q[1].strike)
