"""Optional, missing-aware research factors. Conservative lags are not release vintages."""
from __future__ import annotations
from datetime import datetime,timezone
import logging
import numpy as np
log=logging.getLogger(__name__)
# FRED id, label, module, transformation, lag in months.
SPECS={
 'x_nfci':('NFCI','Broad financial conditions','financial_stress','level',1),
 'x_stress':('STLFSI4','Financial stress','financial_stress','level',1),
 'x_hy':('BAMLH0A0HYM2','High-yield credit spread','financial_stress','level',1),
 'x_vix':('VIXCLS','Equity implied volatility','financial_stress','log',1),
 'x_sloos':('DRTSCILM','Bank lending standards','credit_cycle','level',4),
 'x_dsr':('TDSP','Household debt-service burden','credit_cycle','level',6),
 'x_fed_assets':('WALCL','Fed balance sheet growth','liquidity','growth3',1),
 'x_rrp':('RRPONTSYD','Reverse repo balance change','liquidity','change3',1),
 'x_tga':('WTREGEN','Treasury cash balance change','liquidity','change3',1),
 'x_breakeven':('T10YIE','10-year inflation compensation','expectations','level',1),
 'x_real_yield':('DFII10','10-year real Treasury yield','expectations','level',1),
 'x_usd':('DTWEXBGS','Broad dollar growth','global_trade','growth3',1),
 'x_import':('IR','Import price inflation','global_trade','growth3',2),
 'x_export':('IQ','Export price inflation','global_trade','growth3',2),
 'x_openings':('JTSJOL','Job openings growth','labour_housing','growth3',2),
 'x_claims':('ICSA','Initial unemployment claims growth','labour_housing','growth3',1),
 'x_housing':('CSUSHPINSA','National house price growth','labour_housing','growth3',3),
}

def transform(series,method,lag,origin=None):
    import pandas as pd
    origin=origin or datetime.now(timezone.utc).strftime('%Y-%m')
    s=series.sort_index().resample('MS').mean()
    s=s.reindex(pd.date_range(s.index.min(),origin+'-01',freq='MS')).ffill(limit=2)
    if method=='growth3':s=np.log(s.where(s>0)).diff(3)*100
    elif method=='change3':s=s.diff(3)
    elif method=='log':s=np.log(s.where(s>0))
    elif method!='level':raise ValueError('Unknown factor transform')
    s=s.shift(lag)
    origin=origin or datetime.now(timezone.utc).strftime('%Y-%m')
    return {d.strftime('%Y-%m'):float(v) for d,v in s.items() if d.strftime('%Y-%m')<=origin and np.isfinite(v)}

def fetch():
    from api.models_ml.recession_ensemble import _fred
    f=_fred();out={}
    for key,(sid,_,_,method,lag) in SPECS.items():
        try:
            values=transform(f.get_series(sid),method,lag)
            from api.ml.deep import _months_between
            origin=datetime.now(timezone.utc).strftime('%Y-%m')
            if len(values)>=120 and _months_between(max(values),origin)<=4:out[key]=values
            else:log.warning('Optional research factor stale or too short: %s',sid)
        except Exception:log.warning('Optional research factor unavailable: %s',sid)
    if len(out)<8:raise ValueError('Insufficient expanded factor coverage')
    previous=cached()
    if previous and len(set(out)&set(previous))<.95*len(previous):
        raise ValueError('Expanded factor coverage loss; retain last-good inputs')
    return out

def cached():
    from api.handlers.macro_inputs import _disk_load
    return ((_disk_load('ri_ml_context') or {}).get('data')) or {}

def load():
    from api import research_indicators as ri
    data,_=ri._cached('ml_context',fetch,ttl=21600)
    # Fixed schema across vintages. Unavailable optional factors have explicit missing flags.
    return {key:(data or {}).get(key,{}) for key in SPECS}

def coverage(data=None):
    data=cached() if data is None else data
    return [{'key':key,'series':sid,'label':label,'group':group,'transform':method,'lag_months':lag,
             'source_url':'https://fred.stlouisfed.org/series/'+sid,'observations':len(data.get(key,{})),
             'latest':max(data[key]) if data.get(key) else None,'status':'cached research input' if data.get(key) else 'missing',
             'limitation':'Conservatively lagged revised data; not a historical release-vintage reconstruction.'}
            for key,(sid,label,group,method,lag) in SPECS.items()]
