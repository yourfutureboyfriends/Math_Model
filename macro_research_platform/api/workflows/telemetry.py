"""Bounded in-process performance statistics. Never retain URLs, query strings or user data."""
import threading
import time
from collections import Counter, deque

_LOCK=threading.Lock()
_COUNTS=Counter()
_ROUTES={}
_STARTED=time.monotonic()


def count(name):
    with _LOCK:
        _COUNTS[name]+=1


def observe(route,method,status,seconds):
    key=f'{method} {route}'
    with _LOCK:
        if key not in _ROUTES and len(_ROUTES)>=256:key='OTHER'
        r=_ROUTES.setdefault(key,{'count':0,'errors':0,'client_errors':0,'seconds':0.,'max_ms':0.,'samples':deque(maxlen=512)})
        r['count']+=1;r['errors']+=status>=500;r['client_errors']+=400<=status<500;r['seconds']+=seconds
        r['max_ms']=max(r['max_ms'],seconds*1000);r['samples'].append(seconds*1000)


def snapshot():
    with _LOCK:
        rows=[]
        for key,r in _ROUTES.items():
            sample=sorted(r['samples'])
            rows.append({'route':key,'requests':r['count'],'errors_5xx':r['errors'],'errors_4xx':r['client_errors'],
                         'mean_ms':r['seconds']*1000/r['count'],'max_ms':r['max_ms'],
                         'p95_ms':sample[max(0,int(.95*len(sample))-1)],'sample_count':len(sample)})
        return {'uptime_seconds':time.monotonic()-_STARTED,'routes':sorted(rows,key=lambda r:r['p95_ms'],reverse=True),
                'counters':dict(_COUNTS),'note':'Process-local lifetime counts; p95 uses the latest 512 requests per route. Templates only; no symbols, queries or user payloads retained.'}
