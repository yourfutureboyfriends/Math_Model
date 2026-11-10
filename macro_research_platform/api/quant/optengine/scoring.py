from __future__ import annotations
import math
import numpy as np
from .schema import DataError, number
from .strategies.base import bounds, payoff
from .regimes import forecast

NODES,WEIGHTS=np.polynomial.hermite.hermgauss(41)
WEIGHTS=WEIGHTS/np.sqrt(np.pi)

def execution_value(leg,costs,opening=True):
    q=leg.quote
    buy=leg.quantity>0 if opening else leg.quantity<0
    slip=costs.slippage_fraction_spread*(q.ask-q.bid)
    price=q.ask+slip if buy else max(0.0,q.bid-slip)
    price=(math.ceil(price/q.tick_size-1e-9) if buy else math.floor(price/q.tick_size+1e-9))*q.tick_size
    return leg.quantity*q.multiplier*price

def measure(op,snapshot,config,correlation=0.0):
    cfg=config.strategies[op.strategy]
    fx=snapshot.conversion(op.currency)
    low,high=bounds(op.legs)
    entry=sum(execution_value(l,config.costs) for l in op.legs)*fx
    fees=sum(abs(l.quantity) for l in op.legs)*config.costs.commission_per_contract
    close_spread=sum(abs(l.quantity)*l.quote.multiplier*(l.quote.ask-l.quote.bid)*(0.5+config.costs.slippage_fraction_spread) for l in op.legs)*fx
    roundtrip=2*fees+close_spread
    if snapshot.annual_cash_rate is None:raise DataError("Cash/discount rate missing")
    risk=entry-low*fx+roundtrip
    reward=high*fx-entry-roundtrip
    if risk<=0 or reward<=0:raise DataError("Non-economic spread after costs")
    credit=op.strategy in ("bull_put","iron_condor")
    if credit and entry>=-fees:raise DataError("Credit spread does not generate a credit")
    if not credit and entry<=fees:raise DataError("Debit spread does not require a debit")
    forecast_value=forecast(op.feature,config,snapshot.asof)
    dte=op.legs[0].quote.dte(snapshot.asof)
    sessions=dte*252/365
    volatility=forecast_value["annual_volatility"]*math.sqrt(dte/365)
    spot=op.feature["spot"]
    means=[forecast_value["daily_log_mean"]+sign*forecast_value["mean_uncertainty_daily"] for sign in (-1,0,1)]
    expected=[];profits=None
    discount=math.exp(-snapshot.annual_cash_rate*dte/365)
    for mean in means:
        terminal=spot*np.exp(np.clip(mean*sessions+math.sqrt(2)*volatility*NODES,-30,30))
        profits=payoff(op.legs,terminal)*fx*discount-entry-roundtrip
        expected.append(float(WEIGHTS@profits))
    expected_net=min(expected)
    center_terminal=spot*np.exp(np.clip(means[1]*sessions+math.sqrt(2)*volatility*NODES,-30,30))
    center_profit=payoff(op.legs,center_terminal)*fx*discount-entry-roundtrip
    probability=float(WEIGHTS@(center_profit>0))
    funding=max([l.quote.strike*l.quote.multiplier*fx*config.risk.assignment_collateral_fraction for l in op.legs if l.quantity<0 and l.quote.settlement=="physical"] or [0.0])
    op.entry=entry;op.max_loss=risk;op.max_profit=reward;op.margin=max(risk,funding+max(0.0,entry)+fees);op.expected_net=expected_net;op.expected_risk_return=expected_net/risk
    op.confidence=op.regime["confidence"];op.probability_profit=probability
    for key in ("delta","gamma","vega","theta"):
        setattr(op,key,sum(l.quantity*l.quote.multiplier*getattr(l.quote,key) for l in op.legs))
    liquidity=float(np.mean([min(1.0,l.quote.volume/max(config.data.min_option_volume*10,1))*0.5+min(1.0,l.quote.open_interest/max(config.data.min_open_interest*10,1))*0.5 for l in op.legs]))
    op.terms={"expiry":op.expiry,"currency":op.currency,"multiplier":op.multiplier,"operational_reserve_local":funding/fx,"edge":max(-1.0,min(1.0,op.expected_risk_return)),"direction":op.confidence,"liquidity":liquidity,"diversification":1-min(1,abs(correlation)),
              "entry_fees":fees,"roundtrip_reserve":roundtrip,"forecast":forecast_value,"expected_net_central":expected[1],"expected_net_sensitivity":expected}
    op.score=sum(config.score_weights[k]*op.terms[k] for k in config.score_weights)
    strikes=sorted({l.quote.strike for l in op.legs})
    cash_entry=entry/(fx*op.multiplier)
    if op.strategy=="bull_call":op.breakevens=(strikes[0]+cash_entry,)
    elif op.strategy=="bear_put":op.breakevens=(strikes[-1]-cash_entry,)
    elif op.strategy=="bull_put":op.breakevens=(strikes[-1]+cash_entry,)
    else:op.breakevens=(strikes[1]+cash_entry,strikes[2]-cash_entry)
    if reward/risk<cfg.min_reward_risk:op.rejection="Reward/risk below approved threshold"
    elif credit and -entry/risk<cfg.min_premium_risk:op.rejection="Premium/risk below approved threshold"
    elif expected_net<cfg.min_expected_net_dollars or op.expected_risk_return<cfg.min_expected_risk_return:op.rejection="Forecast edge insufficient after costs and uncertainty"
    elif op.confidence<cfg.min_confidence:op.rejection="Directional/range confidence below threshold"
    return op

def assignment_hazard(op,snapshot):
    spot=op.feature["spot"]
    div=snapshot.dividends.get(op.underlying)
    for l in op.legs:
        q=l.quote
        if l.quantity>=0 or q.exercise!="american":continue
        intrinsic=max(spot-q.strike,0) if q.option_type=="call" else max(q.strike-spot,0)
        extrinsic=max(q.mid-intrinsic,0)
        if q.option_type=="call" and intrinsic>0 and div:
            from .schema import utc
            if utc(div["available_at"])>utc(snapshot.asof):raise DataError("Future dividend event")
            days=(utc(div["ex_date"])-utc(snapshot.asof)).total_seconds()/86400
            if 0<=days<=3 and extrinsic<number(div["amount"],"dividend"):return "Short call dividend assignment risk"
        if q.option_type=="put" and intrinsic>0 and extrinsic<q.strike*max(snapshot.annual_cash_rate or 0,0)*min(q.dte(snapshot.asof),7)/365:
            return "Deep-ITM short put early exercise risk"
    return None
