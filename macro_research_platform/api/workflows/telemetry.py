"""Bounded in-process performance statistics. Never retain URLs, query strings or user data."""
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar

_LOCK=threading.Lock()
_COUNTS=Counter()
_ROUTES={}
_STARTED=time.monotonic()
_STAGES={}
_REQUEST_STAGES=ContextVar('performance_stages',default=None)


def begin_request():
    return _REQUEST_STAGES.set([])


def end_request(token):
    stages=_REQUEST_STAGES.get() or []
    _REQUEST_STAGES.reset(token)
    return stages


@contextmanager
def stage(name):
    # Names come only from bounded internal call sites, never URLs or cache keys.
    if name not in {'market_cache_fill','yahoo_provider','alfred_provider','forecast_archive','offline_replay'}:name='other'
    started=time.monotonic();status='ok'
    try:yield
    except BaseException:
        status='error';raise
    finally:
        elapsed=(time.monotonic()-started)*1000
        with _LOCK:
            row=_STAGES.setdefault(name,{'calls':0,'errors':0,'samples':deque(maxlen=512)})
            row['calls']+=1;row['errors']+=status=='error';row['samples'].append(elapsed)
        collector=_REQUEST_STAGES.get()
        if collector is not None and len(collector)<64:collector.append((name,elapsed,status))


def count(name):
    with _LOCK:
        _COUNTS[name]+=1


def observe(route,method,status,seconds,stages=None):
    key=f'{method} {route}'
    with _LOCK:
        if key not in _ROUTES and len(_ROUTES)>=256:key='OTHER'
        r=_ROUTES.setdefault(key,{'count':0,'errors':0,'client_errors':0,'seconds':0.,'max_ms':0.,'samples':deque(maxlen=512),'stages':Counter()})
        r['count']+=1;r['errors']+=status>=500;r['client_errors']+=400<=status<500;r['seconds']+=seconds
        r['max_ms']=max(r['max_ms'],seconds*1000);r['samples'].append(seconds*1000)
        for name,elapsed,_ in stages or []:r['stages'][name]+=elapsed


def snapshot():
    with _LOCK:
        rows=[]
        for key,r in _ROUTES.items():
            sample=sorted(r['samples'])
            rows.append({'route':key,'requests':r['count'],'errors_5xx':r['errors'],'errors_4xx':r['client_errors'],
                         'mean_ms':r['seconds']*1000/r['count'],'max_ms':r['max_ms'],
                         'p50_ms':sample[max(0,int(.50*len(sample))-1)],
                         'p95_ms':sample[max(0,int(.95*len(sample))-1)],'sample_count':len(sample),
                         'stage_total_ms':dict(r['stages'])})
        return {'uptime_seconds':time.monotonic()-_STARTED,'routes':sorted(rows,key=lambda r:r['p95_ms'],reverse=True),
                'stages':{name:{'calls':r['calls'],'errors':r['errors'],'p95_ms':sorted(r['samples'])[max(0,int(.95*len(r['samples']))-1)]} for name,r in _STAGES.items()},
                'counters':dict(_COUNTS),'note':'Process-local lifetime counts; p95 uses the latest 512 requests per route. Templates only; no symbols, queries or user payloads retained.'}
