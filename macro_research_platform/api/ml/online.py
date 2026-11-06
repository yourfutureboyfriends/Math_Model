"""Continuous provider supervision with data contracts, archives and bounded workers.

Only existing public/configured data adapters are used. Provider context quotes are
kept separate from the monthly publication-lagged model inputs.
"""
from __future__ import annotations
from datetime import datetime,timezone
import gzip
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
import time

ROOT=Path(__file__).resolve().parents[2]/'data'/'processed'/'ml_online'
_lock=threading.Lock()
log=logging.getLogger(__name__)
CONTRACTS={
 'market_context':{'title':'Configured market quote providers','seconds':900,'timeout':120,'cache':None,'minimum_series':3,'used_for':'Context only; not substituted into monthly training inputs'},
 'market_features':{'title':'Yahoo historical market features','seconds':21600,'timeout':180,'cache':'ri_ml_market','minimum_series':3,'required':['spx6','spx_vol3','usd6'],'used_for':'Publication-lagged monthly price/volatility features'},
 'macro_features':{'title':'FRED macroeconomic features','seconds':21600,'timeout':180,'cache':'ri_ml_fred','minimum_series':8,'used_for':'Publication-lagged monthly macro features'},
 'news_features':{'title':'SF Fed and FRED news/uncertainty','seconds':21600,'timeout':180,'cache':'ri_ml_text','minimum_series':4,'used_for':'Monthly news features with missing-data flags'},
 'context_features':{'title':'Expanded stress, liquidity, expectations and credit factors','seconds':21600,'timeout':240,'cache':'ri_ml_context','minimum_series':8,'used_for':'Optional missing-aware research inputs; conservative publication lags'},
 'macro_panel':{'title':'FRED macro panel','seconds':86400,'timeout':300,'cache':'ri_ml_panel','minimum_series':50,'used_for':'Lagged macro factors; training-only PCA'},
}


def read():
    from api.ml.live import _read
    return _read(ROOT/'state.json') or {'sources':{}}


def write(value):
    from api.ml.live import _write
    _write(ROOT/'state.json',value)


def status():
    state=read()
    return {'enabled':os.getenv('ML_ONLINE_ENABLED','1').lower() not in ('0','false','off'),
            'schedule':'Provider supervisor checks every minute while the backend is running.',
            'sources':[{**contract,'id':name,**state.get('sources',{}).get(name,{})} for name,contract in CONTRACTS.items()],
            'running':_lock.locked(),'last_check':state.get('last_check'),
            'policy':'Quotes refresh every 15 minutes; lagged market/macro/news features every six hours; broad macro panel daily. Actual availability and provider entitlements determine coverage.',
            'learning':'Inference refreshes on accepted input changes. Research checks run every six hours; newly matured labels can permit a daily refit, otherwise weekly limits remain. Existing promotion gates apply.'}


def validate_table(table,contract,previous=None,origin=None):
    """Reject broken schemas, nonfinite/future data, or material coverage loss."""
    origin=origin or datetime.now(timezone.utc).strftime('%Y-%m')
    if not isinstance(table,dict) or len(table)<contract['minimum_series']:raise ValueError('Insufficient series coverage')
    if any(k not in table for k in contract.get('required',[])):raise ValueError('Required model feature missing')
    if previous and len(set(table)&set(previous))<.95*len(previous):raise ValueError('Material feature-schema coverage loss')
    newest=[];count=0
    for key,series in table.items():
        if not isinstance(key,str) or not isinstance(series,dict) or len(series)<120:raise ValueError('Insufficient feature history')
        for month,value in series.items():
            if not isinstance(month,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month) or month>origin:raise ValueError('Invalid/future feature timestamp')
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid feature value')
        newest.append(max(series));count+=len(series)
    from api.ml.deep import _months_between
    if any(_months_between(m,origin)>4 for m in newest):raise ValueError('A required source series is stale')
    return {'series':len(table),'observations':count,'latest':max(newest),'oldest_latest':min(newest)}


def drift_summary(table,previous):
    """A review flag for changed aligned values, not proof of concept drift."""
    changed=0;revised=0;aligned=0;largest=0.
    for key,series in table.items():
        old=(previous or {}).get(key,{})
        if not old:continue
        values=list(old.values());mean=sum(values)/len(values);sd=(sum((v-mean)**2 for v in values)/len(values))**.5
        for month,value in series.items():
            if month in old:
                aligned+=1
                if not math.isclose(value,old[month],rel_tol=1e-10,abs_tol=1e-10):revised+=1
        if series[max(series)]!=old[max(old)]:changed+=1
        if sd>1e-9:largest=max(largest,abs(series[max(series)]-mean)/sd)
    return {'changed_latest_series':changed,'revised_aligned_values':revised,'aligned_values':aligned,
            'largest_latest_z':largest,'review_flag':largest>4 or (aligned>0 and revised/aligned>.1),
            'meaning':'Input/revision shift indicator; not a forecast-accuracy measurement or automatic promotion.'}


def archive(name,data,now=None):
    now=time.time() if now is None else now
    raw=json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest=hashlib.sha256(raw).hexdigest();folder=ROOT/'snapshots'/name;path=folder/(digest+'.json.gz')
    if not path.exists():
        # Never silently erase history; stop accepting new snapshots at the local cap.
        folder.mkdir(parents=True,exist_ok=True)
        if len(list(folder.glob('*.json.gz'))) >= (100000 if name=='market_context' else 1000):raise ValueError('Snapshot archive capacity reached')
        import tempfile
        body=json.dumps({'source':name,'observed_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'digest':digest,'data':data},allow_nan=False).encode()
        with tempfile.NamedTemporaryFile(dir=folder,delete=False) as handle:handle.write(gzip.compress(body));tmp=handle.name
        os.replace(tmp,path)
    return digest,str(path.relative_to(ROOT))


def _fetch(name):
    from api.ml import features as F,panel
    if name=='market_features':return F._build_market()
    if name=='macro_features':return F._build_fred()
    if name=='news_features':return F._build_text()
    if name=='context_features':
        from api.ml.context import fetch
        return fetch()
    if name=='macro_panel':return panel._build()
    from api.marketdata.core import quote
    rows=[]
    for symbol in ('SPY','TLT','HYG','GLD','UUP'):
        try:
            record=quote(symbol);price=record.get('price')
            if price is not None and math.isfinite(price) and price>0:
                rows.append({'symbol':symbol,'price':price,'currency':record.get('currency'),'source':record.get('source'),
                             'quote_time':record.get('quote_time'),'delay_minutes':record.get('delay_minutes')})
        except Exception:log.warning('Online learning context quote unavailable for %s',symbol)
    if len(rows)<3:raise ValueError('Insufficient context quote coverage')
    return {'quotes':rows,'fetched_at':datetime.now(timezone.utc).isoformat(),'used_for':'Context only, not monthly training labels or features'}


def refresh_source(name):
    contract=CONTRACTS[name]
    from api.handlers.macro_inputs import _disk_load
    previous=((_disk_load(contract['cache']) or {}).get('data') or {}) if contract['cache'] else None
    data=_fetch(name)
    quality=validate_table(data,contract,previous) if previous is not None else {'quotes':len(data['quotes'])}
    drift=drift_summary(data,previous) if previous is not None else None
    digest,path=archive(name,data)
    if contract['cache']:
        # Commit only validated data, atomically; failed/partial fetches preserve last-good inputs.
        from api.ml.live import _write
        from api.handlers.macro_inputs import _DISK_DIR
        _write(_DISK_DIR/(contract['cache']+'.json'),{'saved_at':time.time(),'data':data})
    return {'digest':digest,'snapshot':path,'quality':quality,'drift':drift,'refreshed_at':datetime.now(timezone.utc).isoformat(),
            'quotes':data.get('quotes') if previous is None else None}


def _run_source(name):
    import subprocess,sys
    env={**os.environ,'ML_DEEP_PARENT_PID':str(os.getpid())}
    result=subprocess.run([sys.executable,'-m','api.ml.online','--source',name],cwd=str(Path(__file__).resolve().parents[2]),env=env,capture_output=True,text=True,timeout=CONTRACTS[name]['timeout'])
    if result.returncode:raise RuntimeError('Provider refresh failed validation or was unavailable')
    return json.loads([line for line in result.stdout.splitlines() if line.startswith('{')][-1])


def cycle(*,now=None,runner=None):
    if not status()['enabled']:return {'action':'disabled'}
    if not _lock.acquire(blocking=False):return {'action':'already_refreshing'}
    now=time.time() if now is None else now
    try:
        state=read();sources=state.setdefault('sources',{});state['last_check']=now
        due=[name for name,c in CONTRACTS.items() if now-sources.get(name,{}).get('last_attempt',0)>=max(c['seconds'],sources.get(name,{}).get('backoff_seconds',0))]
        if not due:write(state);return {'action':'not_due'}
        name=min(due,key=lambda key:sources.get(key,{}).get('last_attempt',0));record=sources.setdefault(name,{})
        record.update(last_attempt=now,status='refreshing');write(state)
        try:
            result=(runner or _run_source)(name);changed=result['digest']!=record.get('digest')
            record.update(result,last_success=now,status='accepted',failures=0,backoff_seconds=0,error=None,changed=changed)
            if changed and CONTRACTS[name]['cache']:
                from api.ml import live
                if live.status()['checkpoint_available']:live.request_refresh()
        except Exception as exc:
            failures=record.get('failures',0)+1
            record.update(status='last_good_retained',failures=failures,error=f'Provider refresh failed ({type(exc).__name__}); prior data retained.',backoff_seconds=min(86400,900*2**min(failures,6)))
            log.exception('Online source refresh failed for %s',name)
        write(state);return {'action':record['status'],'source':name}
    finally:_lock.release()


if __name__=='__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv('.env')
    from api.ml.deep import _worker_parent_guard
    _worker_parent_guard()
    parser=argparse.ArgumentParser();parser.add_argument('--source',choices=list(CONTRACTS),required=True)
    args=parser.parse_args();print(json.dumps(refresh_source(args.source),allow_nan=False))
