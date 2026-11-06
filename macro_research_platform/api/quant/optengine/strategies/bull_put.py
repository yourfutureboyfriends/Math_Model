from .base import pairs

def build(chain,asof,feature,regime,cfg):
    spot=feature["spot"]
    return pairs("bull_put",chain,asof,feature,regime,cfg,"put",(cfg.short_delta,cfg.wing_delta),(-1,1),lambda q:q[1].strike<q[0].strike<spot)
