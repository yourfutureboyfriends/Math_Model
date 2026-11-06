"""Frozen research challengers, independent of live model allocation and order generation."""
import math
import numpy as np
import pandas as pd
from api.model.core import QUADRANTS,realized_regimes,direction_features

# Research hypotheses, not estimated institutional coefficients or a firm's strategy.
EXPOSURES={'Equity':(1.,-1.),'Nominal bonds':(-1.,-1.),'Inflation-linked bonds':(-.5,.5),
           'Corporate credit':(1.,-.5),'Gold':(-.5,1.),'Commodities':(1.,1.)}
VERSION='macro-challengers-v1'


def joint_probability(growth,inflation,k=3):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    x=pd.concat([direction_features(growth,k).add_prefix('g_'),direction_features(inflation,k).add_prefix('i_')],axis=1)
    labels=realized_regimes(growth,inflation,k).shift(-1)
    train=x.join(labels.rename('target')).dropna()
    counts=train.target.value_counts()
    if len(train)<84 or any(counts.get(q,0)<8 for q in QUADRANTS) or x.iloc[[-1]].isna().any().any():return None
    scaler=StandardScaler().fit(train.drop(columns='target'))
    m=LogisticRegression(C=.25,max_iter=1000).fit(scaler.transform(train.drop(columns='target')),train.target)
    values=m.predict_proba(scaler.transform(x.iloc[[-1]]))[0]
    return {'probabilities':{q:float(values[list(m.classes_).index(q)]) for q in QUADRANTS},'training_count':len(train),
            'class_counts':{q:int(counts.get(q,0)) for q in QUADRANTS},'method':'L2-regularized joint multinomial classifier; training-only standardization; fixed C=0.25'}


def multiclass_score(rows,labels):
    valid=[r for r in rows if isinstance(labels.get(pd.Timestamp(r['month']+'-01')),str)]
    if not valid:return {'count':0}
    out={}
    for key in ('independent','joint'):
        bs=[];ll=[];hits=[]
        for r in valid:
            y=labels[pd.Timestamp(r['month']+'-01')];p=r[key]
            bs.append(sum((p[q]-int(q==y))**2 for q in QUADRANTS))
            ll.append(-math.log(max(1e-15,p[y])));hits.append(max(p,key=p.get)==y)
        out[key]={'multiclass_brier':float(np.mean(bs)),'log_loss':float(np.mean(ll)),'accuracy':float(np.mean(hits))}
    return {'count':len(valid),'scores':out,'brier_definition':'Sum over four squared class errors; no division by class count',
            'target_basis':'Final evaluation-vintage factor directions; not immutable GDP/CPI outcomes','note':'Paired months only. A lower sample error is not evidence to promote the challenger without broader unseen evaluation.'}


class Laboratory:
    def __init__(self,params,env):
        self.params=params;self.env=env;self.previous={};self.rows=[];self.joint=[];self.joint_attempts=0;self.joint_withheld=[];self.failure=None

    def observe(self,d,t,next_month,returns):
        self.joint_attempts+=1
        joint=joint_probability(d.growth,d.inflation,self.params.momentum_months)
        if joint is None:
            x=pd.concat([direction_features(d.growth,self.params.momentum_months).add_prefix('g_'),direction_features(d.inflation,self.params.momentum_months).add_prefix('i_')],axis=1)
            train=x.join(realized_regimes(d.growth,d.inflation,self.params.momentum_months).shift(-1).rename('target')).dropna()
            counts=train.target.value_counts()
            self.joint_withheld.append({'month':next_month.strftime('%Y-%m'),'training_count':len(train),
                                       'class_counts':{q:int(counts.get(q,0)) for q in QUADRANTS},
                                       'reason':'Requires 84 matured training labels, eight per class and a complete current feature row'})
        if joint:self.joint.append({'month':next_month.strftime('%Y-%m'),'joint':joint['probabilities'],'independent':d.regime_probs,
                                    'training_count':joint['training_count'],'class_counts':joint['class_counts']})
        if self.failure:return
        assets=d.assets;hist=returns.loc[:t,assets].tail(36)
        if len(hist)<36 or hist.isna().any().any() or any(self.env.get(a) not in EXPOSURES for a in assets):
            self.failure='Research sleeves require 36 complete trailing months and explicit supported asset-class exposures';return
        vol=hist.std(ddof=1)
        if (vol<=0).any():self.failure='Zero historical volatility prevents a supported sleeve';return
        def innovation(f):
            changes=f.diff(self.params.momentum_months).dropna()
            prior=changes.iloc[:-1]
            return float(np.clip((changes.iloc[-1]-prior.mean())/prior.std(ddof=1),-2,2)/2) if len(prior)>=36 and prior.std(ddof=1)>0 else None
        g,i=innovation(d.growth),innovation(d.inflation)
        if g is None or i is None:self.failure='Insufficient past factor changes';return
        economic=np.array([np.clip(EXPOSURES[self.env[a]][0]*g+EXPOSURES[self.env[a]][1]*i,-1,1) for a in assets])
        momentum=np.sign((1+hist.tail(12)).prod().values-1)
        raw={'economic':economic,'return_momentum':momentum,'combined':(economic+momentum)/2}
        row={'month':next_month.strftime('%Y-%m')};next_returns=returns.loc[next_month]
        for name,signal in raw.items():
            w=pd.Series(signal/vol.values,index=assets);gross=w.abs().sum()
            if gross:w/=gross
            expected_vol=math.sqrt(max(float(w.values@d.cov@w.values),0))*math.sqrt(12)
            if expected_vol>self.params.vol_target:w*=self.params.vol_target/expected_vol
            previous=self.previous.get(name,pd.Series(dtype=float))
            held=w.index[w.abs()>1e-10].union(previous.index[previous.abs()>1e-10])
            if any(a not in returns or not np.isfinite(next_returns.get(a,np.nan)) or (abs(previous.get(a,0))>1e-10 and not np.isfinite(returns.loc[t].get(a,np.nan))) for a in held):
                self.failure='Realized returns missing for held research assets; no zero-return substitution';return
            drifted=previous
            if len(previous):
                r=returns.loc[t].reindex(previous.index)
                denominator=1+float((previous*r).sum())
                if denominator<=0:self.failure='Research portfolio equity exhausted';return
                drifted=previous*(1+r)/denominator
            union=w.index.union(drifted.index)
            turnover=float((w.reindex(union,fill_value=0)-drifted.reindex(union,fill_value=0)).abs().sum())
            pnl=float((w*next_returns.reindex(w.index)).sum())
            net=pnl-turnover*self.params.cost_bps/1e4
            if net<=-1:self.failure='Research sleeve equity exhausted; no continuing compounded performance is reported';return
            row[name]={'gross':pnl,'net':net,'turnover':turnover,
                       'gross_exposure':float(w.abs().sum()),'predicted_volatility':expected_vol if expected_vol<=self.params.vol_target else self.params.vol_target,
                       'weights':{a:float(v) for a,v in w.items()}}
            self.previous[name]=w
        self.rows.append(row)

    def result(self,last,growth=None,inflation=None):
        from api.model.backtest import _stats
        summary={name:_stats(pd.Series([r[name]['net'] for r in self.rows],dtype=float)) for name in ('economic','return_momentum','combined')} if not self.failure else {}
        if growth is None and last is not None:growth,inflation=last.growth,last.inflation
        labels=realized_regimes(growth,inflation,self.params.momentum_months) if growth is not None and inflation is not None and not growth.empty and not inflation.empty else pd.Series(dtype=object)
        series=pd.DataFrame({name:[r[name]['net'] for r in self.rows] for name in ('economic','return_momentum','combined')})
        correlation={col:{idx:float(v) if np.isfinite(v) else None for idx,v in values.items()} for col,values in series.corr().to_dict().items()} if len(series)>=12 else None
        return {'version':VERSION,'available':not self.failure and bool(self.rows),'reason':self.failure,'sleeves':summary,'monthly':self.rows if not self.failure else [],
                'joint_regime':multiclass_score(self.joint,labels),'joint_forecasts':self.joint,
                'joint_unavailable_months':self.joint_attempts-len(self.joint),'joint_minimum_training':84,'joint_minimum_per_class':8,
                'joint_unscored_months':sum(not isinstance(labels.get(pd.Timestamp(r['month']+'-01')),str) for r in self.joint),
                'joint_coverage_evidence':self.joint_withheld,
                'sleeve_correlations':correlation if not self.failure else None,
                'specification':{'exposures':EXPOSURES,'momentum_months':12,'volatility_months':36,'gross_cap':1,'volatility_ceiling':self.params.vol_target,'one_way_cost_bps':self.params.cost_bps,'classifier_C':.25},
                'note':'Frozen research hypotheses, not replicas of AQR, Citadel, Renaissance or other firms. Return momentum uses total-return proxy excess histories, not pure spot prices. All three sleeves share assets, dates and a volatility ceiling (not identical realized risk); negative research weights are permitted, gross <=1. Drift uses the same excess-return convention as the baseline, not a full cash-financing ledger. Costs cover turnover, not full futures roll/borrow/funding. No terminal liquidation cost is included. Correlations need at least 12 common months and are descriptive; the combined sleeve is not an independent signal. No orders or live model settings change.'}
