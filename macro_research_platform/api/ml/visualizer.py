"""Lightweight neural inspection, independent of deep training and walk-forward jobs."""
from datetime import datetime, timezone
import logging
import threading
import time
import numpy as np

_mem={}
_pending={}
_lock=threading.Lock()
log=logging.getLogger(__name__)


def build(name):
    from api.ml import engine as E, features as F
    task=E.TASKS[name];feats=F.load();ds=E.dataset(task,feats,{})
    if ds['missing']:return {'available':False,'reason':'Required neural inputs unavailable','task':name}
    rows=ds['rows'];origin=datetime.now(timezone.utc).strftime('%Y-%m')
    y,m=map(int,origin.split('-'));cut=y*12+m-1-task.known_after;before=f'{cut//12}-{cut%12+1:02d}'
    lab=[r for r in rows if r['month']<before and r['y'] is not None]
    if len(lab)<120:return {'available':False,'reason':'Insufficient matured outcomes for neural inspection','task':name}
    X=np.asarray([r['c'] for r in lab],float);Y=np.asarray([r['y'] for r in lab],float)
    if not np.isfinite(X).all() or set(np.unique(Y))!={0.,1.}:return {'available':False,'reason':'Neural inspection needs finite inputs and both outcome classes','task':name}
    network=E.BaggedNet(n=3,max_iter=300).fit(X,Y)
    champion=E.Logit().fit(X,Y)
    now=rows[-1];x=np.asarray(now['c'],float)
    if not np.isfinite(x).all():raise ValueError('Nonfinite current visualizer inputs')
    return {'available':True,'task':name,'month':origin,'as_of_inputs':now['month'],
            'inspection_only':True,'calibration_basis':'Three-seed, bounded inspection fit on matured outcomes; uncalibrated and not the served forecast or a walk-forward result.',
            'network':{'weights':network.export(),'calibration':None},
            'champion':{'probability':float(champion.predict(x)[0])},
            'features':[{'key':k,'label':F.FEATURES.get(k,(k,))[0]} for k in task.features],
            'inputs':dict(zip(task.features,x.tolist())),
            'data_checks':E.data_checks(X,np.asarray([r["c"] for r in rows[-12:]],float),x,task.features),
            'tuned_settings':None,'models':{}}


def request(name):
    from api.ml import engine as E
    if name not in E.TASKS:return {'available':False,'reason':'Unknown task','task':name}
    # A completed task contains its exact exported/calibrated shallow model.
    full=E.cached(name)
    if full and full.get('month')==datetime.now(timezone.utc).strftime('%Y-%m'):return full
    month=datetime.now(timezone.utc).strftime('%Y-%m')
    with _lock:
        hit=_mem.get(name)
        if hit and hit.get('month')==month:
            if not hit.get('available'):_mem.pop(name,None)  # report failure once; an explicit retry can start again
            return hit
        if name not in _pending:
            _pending[name]=time.time()
            def work():
                try:
                    result=build(name);result['month']=month
                    with _lock:_mem[name]=result
                except Exception:
                    log.exception('Neural inspection fit failed')
                    with _lock:_mem[name]={'available':False,'month':month,'reason':'Neural inspection fit failed. Refresh to retry.','task':name}
                finally:
                    with _lock:_pending.pop(name,None)
            threading.Thread(target=work,name=f'neural-inspect-{name}',daemon=True).start()
        return {'available':False,'task':name,'training':True,'reason':'Preparing the interactive shallow network; independent of deep training.',
                'elapsed_s':round(time.time()-_pending[name]),'inspection_only':True}
