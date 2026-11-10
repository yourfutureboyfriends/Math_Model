"""Small target-based nowcast challenger using supplied dated information, never live allocation."""
import numpy as np
from datetime import datetime


def evaluate(rows,min_train=20):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    rows=sorted(rows,key=lambda r:r['forecast_at']);names=sorted({k for r in rows for k in r['features']})
    if not 1<=len(names)<=20:raise ValueError('Supply 1–20 consistently named indicator features')
    seen=set();output=[]
    for r in rows:
        if r['period'] in seen:raise ValueError('One forecast origin per target period is supported')
        seen.add(r['period'])
        origin=datetime.fromisoformat(r['forecast_at'])
        if datetime.fromisoformat(r['features_available_at'])>origin:raise ValueError('Features were unavailable at their forecast origin')
        if r.get('target') is not None and (not r.get('target_available_at') or datetime.fromisoformat(r['target_available_at'])<=origin):raise ValueError('Target outcomes must become available after their forecast origin')
        training=[a for a in rows if a['period']!=r['period'] and a.get('target') is not None and a.get('target_available_at') and datetime.fromisoformat(a['target_available_at'])<=origin and datetime.fromisoformat(a['forecast_at'])<origin]
        if len(training)<min_train:continue
        x=np.array([[a['features'].get(k,np.nan) if a['features'].get(k) is not None else np.nan for k in names] for a in training],dtype=float)
        active=np.isfinite(x).sum(axis=0)>=min_train//2
        if not active.any():continue
        x=x[:,active];mean=np.nanmean(x,axis=0);x=np.where(np.isnan(x),mean,x)
        current=np.array([r['features'].get(k,np.nan) if r['features'].get(k) is not None else np.nan for k in names],dtype=float)[active]
        observed=int(np.isfinite(current).sum())
        if observed<max(1,int(active.sum())//2):continue
        current=np.where(np.isnan(current),mean,current)
        scaler=StandardScaler().fit(x);y=np.array([a['target'] for a in training])
        model=Ridge(alpha=10.).fit(scaler.transform(x),y)
        prediction=float(model.predict(scaler.transform(current.reshape(1,-1)))[0])
        output.append({'period':r['period'],'forecast_at':r['forecast_at'],'prediction':prediction,'baseline':float(y.mean()),
                       'actual':r.get('target'),'training_count':len(training),'used_features':[n for n,use in zip(names,active) if use],
                       'observed_features':observed,'available_features':int(active.sum()),'target_available_at':r.get('target_available_at')})
    scored=[r for r in output if r['actual'] is not None]
    metric={}
    if scored:
        errors=np.array([r['prediction']-r['actual'] for r in scored]);base=np.array([r['baseline']-r['actual'] for r in scored])
        mse=float(np.mean(errors**2));ref=float(np.mean(base**2))
        metric={'count':len(scored),'mae':float(np.mean(abs(errors))),'rmse':float(np.sqrt(mse)),
                'baseline_rmse':float(np.sqrt(ref)),'mse_skill':1-mse/ref if ref>0 else None}
    return {'available':bool(output),'forecasts':output,'evaluation':metric,'specification':{'ridge_alpha':10.,'minimum_training_periods':min_train},
            'note':'Fixed ridge bridge challenger against an expanding training-mean baseline. Training targets must be released by each forecast origin; scaling and missing-value means use training only. Imported feature vintages and timestamps are analyst supplied, not independently certified. This is not the existing standardized growth factor or a structural causal model. Results remain research-only.'}
