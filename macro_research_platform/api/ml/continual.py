"""Automatic, bounded research refits from established market/macro feeds.

No generated targets, web scraping, code rewriting or automatic trading. Observations
and labels retain the existing publication-lag and known-after rules.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time

log=logging.getLogger(__name__)
STATE=Path(__file__).resolve().parents[2]/'data'/'processed'/'ml_continual.json'
_lock=threading.Lock()


def _read():
    try:
        value=json.loads(STATE.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def _write(value):
    import tempfile
    STATE.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=STATE.parent,delete=False) as handle:
        json.dump(value,handle,allow_nan=False);tmp=handle.name
    os.replace(tmp,STATE)


def status():
    return {'enabled':os.getenv('ML_AUTO_LEARN','1').lower() not in ('0','false','off'),
            'schedule':'Every six hours and at startup while the backend is running.',
            'minimum_refit_days':7,'new_label_refit_days':1,'failure_retry_hours':24,
            'policy':'Changed validated inputs or matured labels may trigger a research refit. Production promotion still requires the existing evidence and approval gates.',
            **_read()}


def observe():
    """Fingerprint exactly the assembled, lagged learning inputs and matured labels."""
    import numpy as np
    from datetime import datetime,timezone
    from api.ml import deep
    fr=deep.load_frame()
    origin=datetime.now(timezone.utc).strftime('%Y-%m')
    if not fr['months'] or not 0<=deep._months_between(fr['months'][-1],origin)<=3:raise ValueError('Learning inputs are stale or future-dated')
    # Validate the same transformations, label purge and history requirement as training.
    from api.ml.deep_config import configured,fingerprint
    deep._prepare(fr,len(fr['months']),origin,configured())
    known=deep._labels_known(fr,origin)
    counts={task:int(np.isfinite(known[:,j]).sum()) for j,task in enumerate(fr['tasks'])}
    digest=signature(fr,origin)
    return {'known_label_counts':counts,'digest':digest,'as_of':fr['months'][-1],'months':len(fr['months']),
            'tasks':fr['tasks'],'core_inputs':len(fr['core_keys']),'panel_inputs':len(fr['panel_keys']),'news_inputs':len(fr['text_keys']),
            'limitation':'Some macro/news history is revised data, not a complete first-release archive.'}


def cycle(*,now=None,observer=None,requester=None):
    """Scheduler entry point. Single flight, durable cooldown, no champion changes."""
    if not status()['enabled']:return {'action':'disabled'}
    if not _lock.acquire(blocking=False):return {'action':'already_checking'}
    now=time.time() if now is None else now
    try:
        from api.ml import deep
        if deep.status().get('training'):return {'action':'training_active'}
        old=_read()
        # Avoid repeatedly hitting providers after a failure or daily restart.
        interval=24*3600 if old.get('action') in ('blocked','training_failed') else 6*3600
        if now-old.get('last_attempt',0)<interval:return {'action':'cooldown'}
        old.update(last_attempt=now)
        try:
            snapshot=(observer or observe)()
            previous_counts=old.get('accepted_label_counts') or (old.get('observation') or {}).get('known_label_counts',{})
            if previous_counts and 'accepted_label_counts' not in old:old['accepted_label_counts']=previous_counts
            new_labels=bool(previous_counts) and any(count>previous_counts.get(task,0) for task,count in snapshot.get('known_label_counts',{}).items())
            refit_days=1 if new_labels else 7
            if snapshot['digest']==old.get('accepted_digest'):action='unchanged'
            elif now-old.get('last_queued',0)<refit_days*86400:action='refit_cooldown'
            else:
                response=(requester or deep.request_retrain)()
                action='queued' if response.get('queued') else 'training_active'
                if action=='queued':old.update(accepted_digest=snapshot['digest'],accepted_label_counts=snapshot.get('known_label_counts',{}),last_queued=now)
            old.update(action=action,observation=snapshot,new_matured_labels=new_labels,refit_minimum_days=refit_days,error=None,last_checked=now)
        except Exception as exc:
            log.exception('Automatic neural learning check failed')
            old.update(action='blocked',error=f'Learning check failed ({type(exc).__name__}); existing forecasts remain available.',last_checked=now)
        _write(old)
        return status()
    finally:_lock.release()


def completed(success,digest=None):
    """Persist worker outcome so a failed attempt can be retried after restart."""
    with _lock:
        old=_read();old.update(last_completed=time.time(),last_training_success=bool(success))
        if not success:
            old.pop('accepted_digest',None);old['last_queued']=0
            old.update(action='training_failed',error='Research training failed; existing forecasts remain available. A later data check may retry.')
        else:
            old.update(action='research_updated',error=None,last_queued=time.time())
            if digest:old['accepted_digest']=digest
        _write(old)


def signature(fr,origin):
    import numpy as np
    from api.ml import deep
    from api.ml.deep_config import fingerprint
    h=hashlib.sha256(fingerprint().encode())
    for names in ('months','core_keys','text_keys','tasks'):h.update(json.dumps(fr[names]).encode())
    for key in ('C','P'):
        arr=np.asarray(fr[key],dtype='<f8')
        if not np.isfinite(arr).all():raise ValueError('Nonfinite required learning inputs')
        h.update(arr.tobytes())
    # Stable missing-value representation; future outcomes cannot trigger training.
    for arr in (fr['T'],deep._labels_known(fr,origin)):
        h.update(json.dumps([[float(v) if np.isfinite(v) else None for v in row] for row in arr],allow_nan=False).encode())
    return h.hexdigest()
