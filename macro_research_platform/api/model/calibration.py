"""Probability diagnostics only: never refit a forecast on its evaluation sample."""
import math
import numpy as np


def probability_diagnostics(probabilities, outcomes, baselines=None):
    rows=[]
    for i,(p,y) in enumerate(zip(probabilities,outcomes)):
        if not np.isfinite(p) or not np.isfinite(y) or not 0<=p<=1 or y not in (0,1):continue
        b=baselines[i] if baselines is not None else None
        rows.append((float(p),int(y),float(b) if b is not None and np.isfinite(b) and 0<=b<=1 else None))
    if not rows:return {'count':0,'bins':[],'brier':None,'log_loss':None}
    bins=[];n=len(rows)
    for i in range(10):
        r=[(p,y) for p,y,_ in rows if min(int(p*10),9)==i]
        if not r:continue
        k=len(r);rate=sum(y for _,y in r)/k;z=1.96;den=1+z*z/k
        center=(rate+z*z/(2*k))/den;half=z*math.sqrt(rate*(1-rate)/k+z*z/(4*k*k))/den
        bins.append({'lower':i/10,'upper':(i+1)/10,'count':k,'mean_probability':sum(p for p,_ in r)/k,
                     'observed_frequency':rate,'wilson_95':[max(0,center-half),min(1,center+half)]})
    paired=[(p,y,b) for p,y,b in rows if b is not None]
    ref=sum((b-y)**2 for _,y,b in paired)/len(paired) if paired else None
    score=sum((p-y)**2 for p,y,_ in paired)/len(paired) if paired else None
    return {'count':n,'bins':bins,'brier':sum((p-y)**2 for p,y,_ in rows)/n,
            'log_loss':-sum(y*math.log(max(p,1e-15))+(1-y)*math.log(max(1-p,1e-15)) for p,y,_ in rows)/n,
            'baseline_count':len(paired),'brier_skill':1-score/ref if ref and score is not None else None,
            'expected_calibration_error':sum(b['count']*abs(b['mean_probability']-b['observed_frequency']) for b in bins)/n,
            'note':'Descriptive held-out reliability; no recalibration fitted here. Wilson intervals assume independent binary outcomes; serial dependence can make them too narrow.'}
