from __future__ import annotations
import math
from .schema import DataError, utc

def forecast(feature,config,asof):
    f=config.forecast
    if not f.validated or not f.trained_through or not f.validation_id:raise DataError("No validated Quant Lab forecast")
    if utc(f.trained_through)>=utc(asof):raise DataError("Forecast training overlaps decision date")
    mean=f.intercept+sum(c*feature[n] for n,c in f.coefficients.items())
    vol=sum(w*feature[n] for w,n in zip(f.volatility_weights,("volatility20","volatility63","volatility252")))
    if not math.isfinite(mean) or not math.isfinite(vol) or not 0<vol<5:raise DataError("Invalid forecast")
    return {"daily_log_mean":mean,"annual_volatility":vol,"mean_uncertainty_daily":f.mean_uncertainty_daily,"validation_id":f.validation_id}

def classify(feature,market,iv,forecast_value,config):
    p=config.regime
    expansion=feature["volatility20"]/max(feature["volatility63"],1e-9)
    ratio=iv/forecast_value["annual_volatility"]
    trend=feature["price"]>feature["sma200"]
    panic=market["drawdown"]<=p.panic_drawdown and market["volatility20"]>p.max_vol_expansion*max(market["volatility63"],1e-9)
    rebound=market["momentum21"]>=p.rebound_momentum
    strong=trend and feature["momentum63"]>=p.strong_momentum and feature["momentum21"]>0
    bullish=trend and feature["momentum63"]>=p.bullish_momentum
    bearish=not trend and feature["momentum63"]<=p.bearish_momentum and feature["momentum21"]<0 and not rebound
    sideways=abs(feature["momentum63"])<=p.range_momentum and expansion<=p.max_vol_expansion
    label="strong_bull" if strong else "bull" if bullish else "bear" if bearish else "range" if sideways else "uncertain"
    active=[]
    if not panic:
        if bullish and ratio>=p.min_iv_rv and expansion<=p.max_vol_expansion:active.append("bull_put")
        if strong:active.append("bull_call")
        if bearish:active.append("bear_put")
        if sideways and ratio>=p.min_iv_rv:active.append("iron_condor")
    signal=abs(feature["momentum63"])/(max(feature["volatility63"],0.01)*math.sqrt(63/252))
    confidence=min(1.0,signal/2) if label!="range" else max(0.0,1-abs(feature["momentum63"])/p.range_momentum)
    return {"label":label,"strategies":active,"confidence":confidence,"iv_forecast_ratio":ratio,"volatility_expansion":expansion,"panic":panic,"rebound":rebound}
