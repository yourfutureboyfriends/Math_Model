"""Measured modular-network telemetry and isolated, checkpoint-based live inspection.

API imports never load Torch. Preview fits are explicitly separate from production.
"""
from __future__ import annotations
from datetime import datetime,timezone
from dataclasses import asdict,replace
import json
import logging
import os
from pathlib import Path
import threading
import time

ROOT=Path(__file__).resolve().parents[2]/'data'/'processed'/'ml_live'
_lock=threading.Lock()
_job={'running':False}
log=logging.getLogger(__name__)


def directory():
    from api.ml.deep_config import fingerprint
    return ROOT/fingerprint()


def _read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None


def _write(path,value):
    import tempfile
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as handle:
        json.dump(value,handle,allow_nan=False);tmp=handle.name
    os.replace(tmp,path)


def training_event(**event):
    kind=os.getenv('ML_TRACE_KIND','training')
    path=directory()/(kind+'.json');old=_read(path) or {}
    history=old.get('history',[])
    if 'epoch' in event:
        history=(history+[{'at':time.time(),**event}])[-180:]
    _write(path,{**old,**event,'updated_at':datetime.now(timezone.utc).isoformat(),'history':history})


def _checkpoint():
    folder=directory()
    return next((folder/name for name in ('full.pt','preview.pt') if (folder/name).exists()),None)


def status():
    folder=directory();trace=_read(folder/'trace.json')
    return {'job':dict(_job),'trace':trace,'training':_read(folder/'training.json'),
            'preview_training':_read(folder/'preview.json'),'inference':_read(folder/'inference.json'),
            'checkpoint_available':_checkpoint() is not None,
            'cadence':'Measured state is polled every two seconds. Input inference refreshes at most once per minute while this view is open; source publication lags still apply.'}


def _trace(fr,nets,metadata,state):
    import numpy as np
    import torch
    from api.ml import deep
    X=deep.transform_features(fr,state)
    if not np.isfinite(X[-deep.SEQ:]).all():raise ValueError('Nonfinite inference inputs')
    x=torch.tensor(deep._windows(X,[len(fr['months'])-1]));traces=[]
    for net in nets:
        net.eval();trace=net.trace(x)
        for values in trace['probabilities']:
            for j,trained in enumerate(net.trained_heads):
                if not trained:values[j]=None
        traces.append(trace)
    import hashlib
    digest=hashlib.sha256(X[-deep.SEQ:].tobytes()).hexdigest()
    previous=_read(directory()/'trace.json') or {}
    result={**metadata,'months':fr['months'][-deep.SEQ:],'tasks':fr['tasks'],'as_of':fr['months'][-1],
            'inferred_at':datetime.now(timezone.utc).isoformat(),'input_digest':digest,
            'inputs_changed':digest!=previous.get('input_digest'),'seeds':traces,
            'note':'Raw research-model states. Prefix replay starts memory at the beginning of this 24-month window; it is not a historical out-of-sample record. Routing and attention are not causal attribution.'}
    _write(directory()/'trace.json',result)
    return result


def save_checkpoint(fr,nets,state,cfg,purpose):
    import torch
    from api.ml.deep_config import fingerprint
    metadata={'version':fingerprint(),'run_fingerprint':fingerprint(cfg),'configuration':asdict(cfg),
              'purpose':purpose,'trained_at':datetime.now(timezone.utc).isoformat()}
    payload={'metadata':metadata,'preprocessor':{k:torch.tensor(v) for k,v in state.items()},
             'core_keys':fr['core_keys'],'text_keys':fr['text_keys'],'panel_keys':fr['panel_keys'],'tasks':fr['tasks'],
             'groups':nets[0].groups,'states':[n.state_dict() for n in nets],'trained_heads':[n.trained_heads for n in nets]}
    folder=directory();folder.mkdir(parents=True,exist_ok=True)
    name='full.pt' if purpose=='full_research' else 'preview.pt'
    import tempfile
    with tempfile.NamedTemporaryFile(dir=folder,delete=False) as handle:tmp=handle.name
    torch.save(payload,tmp);os.replace(tmp,folder/name)
    return _trace(fr,nets,metadata,state)


def worker(preview=False):
    import numpy as np
    import torch
    from api.ml import deep
    from api.ml.deep_config import configured,DeepConfig
    torch.set_num_threads(2)
    training_event(stage='loading_inputs',message='Reading lagged market, macro and news data')
    fr=deep.load_frame(include_targets=preview)
    if preview:
        cfg=replace(configured(),epochs=3,seeds=1,seed_budget_seconds=20)
        if cfg.architecture!='modular':raise ValueError('Live modular inspection requires a modular profile')
        X,idx,Yw,cut,weights=deep._prepare(fr,len(fr['months']),datetime.now(timezone.utc).strftime('%Y-%m'),cfg)
        training_event(stage='preview_fit',message='Fitting a bounded inspection checkpoint; not a served model')
        net=deep._train(deep._windows(X,idx),Yw,0,cfg,cut,weights,deep._groups(fr))
        result=save_checkpoint(fr,[net],deep.fit_preprocessor(fr,idx[cut]),cfg,'inspection_preview')
    else:
        path=_checkpoint()
        if path is None:raise ValueError('No compatible checkpoint yet')
        saved=torch.load(path,map_location='cpu',weights_only=True)
        for key in ('core_keys','text_keys','panel_keys','tasks'):
            if fr[key]!=saved[key]:raise ValueError('Input schema changed; rebuild this checkpoint')
        cfg=DeepConfig(**saved['metadata']['configuration']);state={k:v.numpy() for k,v in saved['preprocessor'].items()}
        d_in=len(fr['core_keys'])+state['V'].shape[1]+2*len(fr['text_keys']);nets=[]
        for weights,heads in zip(saved['states'],saved['trained_heads']):
            net=deep._make_net(d_in,len(fr['tasks']),cfg,saved['groups']);net.load_state_dict(weights);net.trained_heads=heads;nets.append(net)
        result=_trace(fr,nets,saved['metadata'],state)
    training_event(stage='complete',message='Measured model state updated')
    return {'ok':True,'as_of':result['as_of'],'purpose':result['purpose']}


def request_refresh():
    """Coalesced, bounded subprocess inference; never waits on full training."""
    with _lock:
        if _job.get('running') or time.time()-_job.get('last_attempt',0)<60:return dict(_job)
        _job.update(running=True,last_attempt=time.time(),error=None)
        preview=_checkpoint() is None
        def work():
            import subprocess,sys
            try:
                env={**os.environ,'OMP_NUM_THREADS':'2','ML_TRACE_WORKER':'1','ML_TRACE_KIND':'preview' if preview else 'inference','ML_DEEP_PARENT_PID':str(os.getpid())}
                result=subprocess.run([sys.executable,'-m','api.ml.deep','--preview' if preview else '--infer'],cwd=str(Path(__file__).resolve().parents[2]),env=env,capture_output=True,text=True,timeout=240)
                if result.returncode:raise RuntimeError('Isolated live inspection failed')
                _job.update(last_completed=time.time())
            except Exception as exc:
                log.exception('Live neural inspection failed')
                _job['error']=f'Live inspection failed ({type(exc).__name__}); the last measured state remains visible.'
            finally:_job['running']=False
        threading.Thread(target=work,name='neural-live-inspection',daemon=True).start()
        return dict(_job)
