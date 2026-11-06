import numpy as np
import pandas as pd

UNIVERSE = ["ACWI", "SPY", "GLD", "TLT", "XLE"]
TRADABLE_UNIVERSE = "GLOBAL"
START = "2016-01-01"
BENCHMARK = "ACWI"
ACCOUNT_CALENDAR = "ACWI"
ACCOUNT_CURRENCY = "USD"
ASSET_CLASSES = {"GLD": "commodity", "TLT": "rates", "XLE": "equity"}
PARAMS = {}
OPTIONS = [
    {"underlying": "*", "type": "call", "delta": 0.70, "name": "CBUY"},
    {"underlying": "*", "type": "call", "delta": 0.25, "name": "CCAP"},
]

def strategy(data, risk_profile="growth", core_budget=None, option_risk=0.0075, target_vol=None,
             max_core_asset=None, max_equity_core=None, max_option_notional=0.35,
             delta_cap=0.25, profit_take=0.50, stop_risk=0.50,
             close_dte=7, iv_rv_hurdle=1.10, cost_buffer=0.06,
             allow_modelled_credit=False, tail_daily_limit=None, **params):
    if params or risk_profile not in ["balanced","growth"]:
        raise ValueError("Unknown strategy parameters")
    growth=risk_profile=="growth"
    if core_budget is None:core_budget=0.95 if growth else 0.85
    if target_vol is None:target_vol=0.22 if growth else 0.18
    if max_core_asset is None:max_core_asset=0.45 if growth else 0.35
    if max_equity_core is None:max_equity_core=0.85 if growth else 0.70
    if tail_daily_limit is None:tail_daily_limit=0.03 if growth else 0.02
    if not 0 <= core_budget <= 0.95 or not 0 <= option_risk <= 0.025:
        raise ValueError("Invalid core or option risk budget")
    if not 0.01<=tail_daily_limit<=0.05:
        raise ValueError("Invalid daily empirical tail budget")
    if not 0.08 <= target_vol <= 0.30 or not 0 < max_core_asset <= 0.50:
        raise ValueError("Invalid volatility or asset cap")
    if not 0 < max_equity_core <= 0.90 or not 0 < max_option_notional <= 0.50:
        raise ValueError("Invalid equity or derivative cap")
    if not 0 < delta_cap <= 0.50 or not 0 < profit_take <= 2 or not 0 < stop_risk <= 1:
        raise ValueError("Invalid option limits")
    if not 1 <= close_dte <= 15 or not 1 <= iv_rv_hurdle <= 2 or not 0 <= cost_buffer <= 0.25:
        raise ValueError("Invalid expiry or pricing thresholds")
    if not isinstance(allow_modelled_credit,bool):
        raise ValueError("allow_modelled_credit must be boolean")
    px=data.close.astype(float)
    if not isinstance(px.index,pd.DatetimeIndex) or not px.index.is_unique or not px.index.is_monotonic_increasing or not px.columns.is_unique:
        raise ValueError("Dates and instruments must be unique and ordered")
    opt=data.opt
    for key in ["spot","strike","delta","iv","dte","roll"]:
        if key not in opt:
            raise ValueError("Load the declared OPTIONS before running")
    names=[u for u in px.columns if data.instruments.get(u,{}).get("kind") != "option"]
    if not names:
        raise ValueError("No usable underlying history")
    observed=data.observed.reindex(index=px.index,columns=px.columns).fillna(False)
    returns=px[names].pct_change(fill_method=None)
    vol=returns.rolling(63,min_periods=63).std()*np.sqrt(252)
    fast=returns.rolling(20,min_periods=20).std()*np.sqrt(252)
    ready=observed[names].rolling(253,min_periods=253).sum()>=200
    trend=px[names]>=px[names].rolling(200,min_periods=200).mean()
    m12=px[names].shift(21)/px[names].shift(252)-1
    m6=px[names].shift(21)/px[names].shift(126)-1
    eligible=ready & trend & (m12>0) & (m6>0) & (vol>=0.03) & (vol<=0.80)
    if data.members is not None:
        eligible=eligible & data.members.reindex(index=px.index,columns=names).fillna(False)
    tradable_value=(px[names]*data.volume[names]).rolling(20,min_periods=15).median()
    eligible=eligible & (tradable_value>=1000000/data.usd_per_unit.to_numpy()[:,None])
    rank=0.60*m12.where(eligible).rank(axis=1,pct=True)+0.40*m6.where(eligible).rank(axis=1,pct=True)
    equity=[]
    for u in names:
        asset_class=ASSET_CLASSES.get(u,"equity")
        if asset_class not in ["equity","commodity","rates","fx","credit"]:
            raise ValueError("Unsupported ASSET_CLASSES label")
        if asset_class=="equity":
            equity.append(u)
    roll=opt["roll"].fillna(False).astype(bool)
    specs={o["name"]:o for o in OPTIONS}
    groups={}
    for n in opt["iv"].columns:
        meta=data.instruments.get(n,{})
        u=meta.get("underlying",specs.get(n,{}).get("underlying"))
        kind=meta.get("option_type",specs.get(n,{}).get("type"))
        if u in names and n in px and kind in ["put","call"]:
            groups.setdefault(u,{}).setdefault(kind,[]).append(n)
    out=pd.DataFrame(np.nan,index=px.index,columns=px.columns)
    core=pd.Series(0.0,index=px.columns)
    active=None
    initialized=False
    months=px.index.to_period("M")
    monthly=np.r_[True,months[1:]!=months[:-1]]
    for t in range(len(px)):
        changed=False
        closed=False
        if active is not None:
            legs=active["legs"]
            rolled=any(bool(roll[n].iloc[t]) for n in legs)
            marks=[float(px[n].iloc[t]) for n in legs]
            valid=np.isfinite(marks).all()
            value=sum(c*float(px[n].iloc[t]) for n,c in legs.items()) if valid else np.nan
            gain=value-active["entry"]-active["buffer"]
            dte=min(float(opt["dte"][n].iloc[t]) for n in legs)
            delta=abs(sum(c*float(opt["delta"][n].iloc[t]) for n,c in legs.items()))*active["notional"]
            target=profit_take*(abs(active["entry"]) if active["entry"]<0 else active["risk"])
            member_exit=data.members is not None and not bool(data.members.reindex(columns=names).iloc[t].fillna(False)[active["underlying"]])
            exit_now=rolled or member_exit or (valid and (gain>=target or gain<=-stop_risk*active["risk"]
                                         or dte<=close_dte or delta>=delta_cap))
            if exit_now:
                active=None;changed=True;closed=not rolled
        if monthly[t] or not initialized or bool(roll.iloc[t].any()) or (data.members is not None and bool((core.reindex(names)>0).where(~data.members.reindex(columns=names).iloc[t].fillna(False),False).any())):
            core[:]=0.0
            selected=rank.iloc[t].dropna().sort_values(ascending=False).index[:3]
            if len(selected):
                weights=1/np.maximum(vol.iloc[t].reindex(selected).to_numpy(),0.05)
                weights=weights/weights.sum()*core_budget
                core.loc[selected]=np.minimum(weights,max_core_asset)
                equity_weight=float(core.reindex(equity).sum())
                if equity_weight>max_equity_core:core.loc[equity]*=max_equity_core/equity_weight
                h=returns.iloc[max(0,t-62):t+1].reindex(columns=names).fillna(0).to_numpy()
                if len(h)==63:
                    risk=float(np.std(h@core.reindex(names).to_numpy(),ddof=1)*np.sqrt(252))
                    if risk>target_vol:core*=target_vol/risk
                    portfolio_returns=h@core.reindex(names).to_numpy()
                    cutoff=float(np.quantile(portfolio_returns,0.05))
                    tail=portfolio_returns[portfolio_returns<=cutoff]
                    expected_shortfall=-float(tail.mean()) if len(tail) else 0.0
                    if expected_shortfall>tail_daily_limit:core*=tail_daily_limit/expected_shortfall
            initialized=True;changed=True
        if active is not None:
            delta=abs(sum(c*float(opt["delta"][n].iloc[t]) for n,c in active["legs"].items()))
            if np.isfinite(delta):
                n=min(active["notional"],delta_cap/max(delta,0.000001),
                      max(0.0,0.50-float(core[active["underlying"]]))/max(delta,0.000001),
                      max(0.0,1.80-float(core.abs().sum()))/2)
                if n<active["notional"]-0.000001:
                    active["notional"]=n;changed=True
                    if n<=0:active=None;closed=True
        if active is None and not closed and option_risk>0:
            choices=[]
            available=set(eligible.columns[eligible.iloc[t].to_numpy()])
            rolled_names=roll.columns[roll.iloc[t].to_numpy()]
            rolled_underlyings=set(data.instruments[n].get("underlying") for n in rolled_names)
            for u in sorted(available & rolled_underlyings):
                kinds=groups.get(u,{})
                if not bool(eligible[u].iloc[t]) or not bool(observed[u].iloc[t]):continue
                for kind,option_names in kinds.items():
                    candidates=[n for n in option_names if bool(roll[n].iloc[t]) and bool(observed[n].iloc[t])]
                    if len(candidates)<2:continue
                    candidates=sorted(candidates,key=lambda n:float(opt["strike"][n].iloc[t]))
                    low,high=candidates[0],candidates[-1]
                    if low==high:continue
                    legs={high:-1,low:1} if kind=="put" else {low:1,high:-1}
                    sources=[str(data.instruments.get(n,{}).get("vol_source") or "").lower() for n in legs]
                    anchored=all("(implied)" in source and not source.startswith("model:") for source in sources)
                    if kind=="put" and not anchored and not allow_modelled_credit:continue
                    spots=[float(opt["spot"][n].iloc[t]) for n in legs]
                    dtes=[float(opt["dte"][n].iloc[t]) for n in legs]
                    strikes=[float(opt["strike"][n].iloc[t]) for n in [low,high]]
                    prices={n:float(px[n].iloc[t]) for n in legs}
                    iv=float(np.mean([float(opt["iv"][n].iloc[t]) for n in legs]))
                    rv=max(float(vol[u].iloc[t]),float(fast[u].iloc[t]))
                    deltas=[float(opt["delta"][n].iloc[t]) for n in legs]
                    if not np.isfinite(spots+dtes+strikes+list(prices.values())+[iv,rv]+deltas).all():continue
                    if not np.allclose(spots,spots[0]) or not np.allclose(dtes,dtes[0]) or spots[0]<=0:continue
                    if min(dtes)<=close_dte+1 or max(dtes)>400 or not 0<strikes[0]<strikes[1]:continue
                    if any(p<0 for p in prices.values()) or rv<=0:continue
                    if kind=="put" and iv/rv<iv_rv_hurdle:continue
                    ccy=data.instruments[low].get("currency",data.account_currency)
                    if data.instruments[high].get("currency",data.account_currency)!=ccy:continue
                    fx=1.0
                    if ccy!=data.account_currency:
                        if data.fx is None or ccy not in data.fx:continue
                        fx=float(data.fx[ccy].iloc[t])
                        if not np.isfinite(fx) or fx<=0:continue
                    width=(strikes[1]-strikes[0])*fx
                    entry=sum(c*prices[n] for n,c in legs.items())
                    usd=float(data.usd_per_unit.iloc[t])
                    if not usd>0 or not np.isfinite(usd):continue
                    buffer=sum(abs(c)*(cost_buffer*prices[n]+1.30/(float(data.instruments[n].get("lot_size") or 100)*usd)) for n,c in legs.items())
                    risk=width+entry+buffer if kind=="put" else entry+buffer
                    if not 0<risk<width+buffer:continue
                    if kind=="put" and not -width<entry<-buffer:continue
                    if kind=="call" and not buffer<entry<width-buffer:continue
                    delta=abs(sum(c*float(opt["delta"][n].iloc[t]) for n,c in legs.items()))
                    budget=min(option_risk,max(0.0,0.98-float(core.sum())))
                    n=min(max_option_notional,budget*spots[0]/risk,delta_cap/max(delta,0.000001),
                          max(0.0,0.50-float(core[u]))/max(delta,0.000001),max(0.0,1.80-float(core.abs().sum()))/2)
                    if n<=0:continue
                    score=float(rank[u].iloc[t]) if kind=="call" else max(0.0,iv/rv-1)
                    choices.append((score,u,legs,entry,buffer,risk,n))
            if choices:
                score,u,legs,entry,buffer,risk,n=sorted(choices,key=lambda x:(-x[0],x[1]))[0]
                active={"underlying":u,"legs":legs,"entry":entry,"buffer":buffer,"risk":risk,"notional":n}
                changed=True
        if changed:
            current=core.copy()
            if active is not None:
                for n,c in active["legs"].items():current[n]=c*active["notional"]
            out.iloc[t]=current.to_numpy()
    return out
