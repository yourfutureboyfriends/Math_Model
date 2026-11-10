from .base import pairs

def build(chain,asof,feature,regime,cfg):
    return pairs("bear_put",chain,asof,feature,regime,cfg,"put",(cfg.long_delta,cfg.short_delta),(1,-1),lambda q:q[1].strike<q[0].strike)
