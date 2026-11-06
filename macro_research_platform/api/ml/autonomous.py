"""Nonblocking application supervisor. API process never imports Torch or fits models."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]/'data'/'processed'/'ml_autonomous'
_lock=threading.Lock()
_job={'running':False}


def _read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None


def runtime_directory():
    record=_read(ROOT/'active_runtime.json') or {}
    path=Path(record.get('path',ROOT/'uninitialized')).resolve()
    return path if path.is_relative_to(ROOT.resolve()) else ROOT/'uninitialized'


def capture_baseline():
    from api.ml import engine
    from api.ml.live import _write
    now=datetime.now(timezone.utc).isoformat();month=now[:7];tasks={}
    for name,hit in list(engine._mem.items()):
        data=hit.get('data',{})
        if not data.get('available') or data.get('month')!=month:continue
        signal=data.get('signal',{});p=signal.get('probability')
        if not isinstance(p,(float,int)) or not math.isfinite(p) or not 0<=p<=1:continue
        tasks[name]={'probability':float(p),'model':signal.get('model'),'trained_through':now,
                     'positive_share':data.get('positive_share'),'coefficients':data.get('champion',{}).get('coefficients'),
                     'network_weights':data.get('network',{}).get('weights'),'as_of_inputs':data.get('as_of_inputs')}
    # Recover actually logged current-month reference predictions after a
    # backend restart; never recompute a historical prediction using new data.
    try:
        from contextlib import closing
        with closing(engine._conn()) as c:
            promoted={r['task'] for r in c.execute('SELECT task FROM ml_promotions')}
            for row in c.execute("SELECT task,probability,logged_at FROM ml_forecasts WHERE month=? AND model='champion'",(month,)):
                if row['task'] not in tasks and row['task'] not in promoted:
                    tasks[row['task']]={'probability':float(row['probability']),'model':'champion',
                        'trained_through':row['logged_at'],'source':'Actual persisted incumbent logistic forecast',
                        'weights_available':False,'positive_share':None}
    except sqlite3.Error:pass
    recipe=hashlib.sha256((Path(engine.__file__).read_text()+'native-served-reference-v1').encode()).hexdigest()
    _write(ROOT/'baseline_current.json',{'recipe':recipe,'observed_at':now,'tasks':tasks,
        'scope':'Actual incumbent serving outputs captured before autonomous work; no retroactive predictions.'})
    return len(tasks)


def _external_running():
    path=ROOT/'application.lock'
    if not path.exists():return False
    with path.open('r') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
    return False


def status():
    folder=runtime_directory();state=_read(folder/'state.json') or {}
    forecast=_read(folder/'forecast.json')
    enabled=os.getenv('ML_AUTONOMOUS_ENABLED','1').lower() not in ('0','false','off')
    current=None
    registry=folder/'registry.sqlite'
    if registry.exists():
        with sqlite3.connect('file:'+str(registry)+'?mode=ro',uri=True) as c:
            row=c.execute('SELECT id FROM champion WHERE singleton=1').fetchone();current=row[0] if row else None
    events=[]
    ledger=ROOT/'graph'/'events.sqlite'
    if ledger.exists():
        with sqlite3.connect('file:'+str(ledger)+'?mode=ro',uri=True) as c:
            for (payload,) in c.execute('SELECT payload FROM events ORDER BY available_at DESC LIMIT 8'):
                event=json.loads(payload);events.append({k:event.get(k) for k in ('entity','action','evidence','source_url','available_at','confidence')})
    return {'enabled':enabled,'job':{**_job,'running':_job['running'] or _external_running()},'state':state,'forecast':forecast,'recent_events':events,
            'registry_champion':current,'failure':_read(folder/'failure.json'),
            'schedule':'Automatically after the NYSE session closes, with holidays and early closes respected; backend must remain running.',
            'learning_policy':'New matured outcomes trigger supervised replay/EWC updates. New observations can update a shadow encoder with masked-feature reconstruction while forecasting heads remain fixed. No manufactured forecast labels.',
            'promotion_policy':'Only recorded prospective comparisons can promote the six existing task horizons. Other horizons remain research outputs. Insufficient calibration, returns or outcome history retains the incumbent.'}


def request(manual=False):
    if os.getenv('ML_AUTONOMOUS_ENABLED','1').lower() in ('0','false','off'):return {'queued':False,'reason':'disabled'}
    if _external_running():return {'queued':False,'reason':'already_running'}
    if not _lock.acquire(blocking=False):return {'queued':False,'reason':'already_running'}
    try:
        ROOT.mkdir(parents=True,exist_ok=True);capture_baseline()
        _job.update(running=True,started_at=datetime.now(timezone.utc).isoformat(),error=None)
        def work():
            try:
                env={**os.environ,'ML_DEEP_PARENT_PID':str(os.getpid()),'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
                cmd=[sys.executable,'-m','api.ml.institutional.application']+(['--manual'] if manual else [])
                with (ROOT/'worker.log').open('a') as log:
                    result=subprocess.run(cmd,cwd=str(Path(__file__).resolve().parents[2]),env=env,stdout=log,stderr=log,timeout=1800)
                if not result.returncode:
                    failure=runtime_directory()/'failure.json'
                    if failure.exists():failure.unlink()
                if result.returncode:_job['error']='The autonomous worker did not complete. Its last known state and existing served models were retained.'
            except Exception as exc:_job['error']='Worker stopped ('+type(exc).__name__+'); existing served models retained.'
            finally:
                _job.update(running=False,finished_at=datetime.now(timezone.utc).isoformat());_lock.release()
        threading.Thread(target=work,name='autonomous-ml-supervisor',daemon=True).start()
        return {'queued':True,'manual':manual}
    except Exception:
        _lock.release();raise


def due():
    """Cheap scheduling check; no source fetch or model construction."""
    if _job['running'] or _external_running():return {'action':'already_running'}
    try:
        import exchange_calendars as xcals
        import pandas as pd
        now=pd.Timestamp.now(tz='UTC');day=now.tz_convert('America/New_York').date()
        cal=xcals.get_calendar('XNYS')
        if not cal.is_session(str(day)):return {'action':'non_session'}
        start=cal.session_close(str(day))+pd.Timedelta(minutes=20)
        if not start<=now<=start+pd.Timedelta(minutes=60):return {'action':'not_due'}
        state=status()['state']
        if state.get('last_run_date')==str(day):return {'action':'already_completed'}
        return request()
    except Exception as exc:return {'action':'schedule_unavailable','error_type':type(exc).__name__}


def served(task):
    """Read only a fresh, calibrated forecast from the actual promoted pointer."""
    record=_read(ROOT/'serving.json')
    if not record:return None
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(record['origin'])).total_seconds()
        if not 0<=age<=36*3600:return None
        if record.get('target_month',datetime.now(timezone.utc).strftime('%Y-%m'))!=datetime.now(timezone.utc).strftime('%Y-%m'):return None
        path=Path(record['registry_path']).resolve()
        if not path.is_relative_to(ROOT.resolve()):return None
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
            champion=c.execute('SELECT id FROM champion WHERE singleton=1').fetchone()
        if not champion or champion[0]!=record['model_id']:return None
        tasks=['recession_12m','spx_drawdown_6m','yields_up_3m','inflation_up_3m','oil_up_3m','unemployment_up_6m']
        horizons=[12,6,3,3,3,6];j=tasks.index(task);h=[1,3,6,12].index(horizons[j])
        if not record['calibration_ready'][h][j]:return None
        p=float(record['probabilities'][h][j])
        if not math.isfinite(p) or not 0<=p<=1:return None
        skill=record.get('skill_vs_reference_prior',{}).get(task+'|'+str(horizons[j]))
        return {'probability':p,'model':'autonomous_tft','model_id':record['model_id'],'origin':record['origin'],
                'scope':'Gate-promoted TFT/GAT/MoE forecast','useful':skill is not None and skill>0,'skill_vs_base_rate':skill}
    except (KeyError,ValueError,TypeError,OSError,sqlite3.Error):return None


def decorate(data):
    if not data.get('available'):return data
    signal=served(data.get('task'))
    if not signal:return data
    return {**data,'models':{**data.get('models',{}),'autonomous_tft':{'name':'Autonomous TFT / GAT','what':'Automatically promoted on prospective evidence','probability':signal['probability'],'record':None}},
            'promotion':{**data.get('promotion',{}),'requires_human_approval':False,'status':'Autonomous model promoted after evidence gates passed'},'legacy_signal':data.get('signal'),'signal':{**data.get('signal',{}),**signal},
            'autonomous_provenance':{'model_id':signal['model_id'],'origin':signal['origin']}}
