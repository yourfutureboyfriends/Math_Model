"""
Deep sequence model: specialist input modules feeding a recurrent network (GRU) that reads the last 24 months of the economy and answers every task
at once (multi-task), in PyTorch.

Inputs at each month: every task's core inputs (union), 8 principal-component factors of the ~70-series panel
(re-estimated inside each training window), and the text & news block (with a 'missing' flag per series, since some
start in 1985). A sequence model sees trajectories — a curve that inverted and is now re-steepening, a slide in
hiring — not one month's snapshot. Multi-task learning shares one representation across the six questions, giving
the network roughly six times the training signal of a single task (Caruana 1997; standard at Google/DeepMind).

Training: versioned stacked-GRU / temporal-attention profiles (64×2 default, 256×4 XL), with masked binary cross-entropy
(a task's label is used only if its answer was known at the refit); AdamW (profile-specific learning rate and weight decay); early stopping
on the last 15% of the training window, chronologically (patience 15, max 150 epochs); an ensemble of 5 seeds.
Walk-forward: refit every two Januaries from 1985 on data known by then; forecasts the next two years' months.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from api.ml.deep_config import configured, fingerprint, model_key
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

SEQ = 24
HIDDEN = 32
SEEDS = 5
REFIT_EVERY = 2
N_FACTORS = 8


def _months_between(a: str, b: str) -> int:
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb - ya) * 12 + mb - ma


GAP_FILL = 3          # the Oct-2025 shutdown cancelled a CPI report; derived series lost up to three months


def _month_range(a: str, b: str) -> List[str]:
    y, m = map(int, a.split("-"))
    out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _fill(series: Dict[str, float], months: List[str]) -> Dict[str, float]:
    out, last, age = {}, None, 0
    for m in months:
        if m in series:
            out[m], last, age = series[m], series[m], 0
        elif last is not None and age < GAP_FILL:
            age += 1
            out[m] = last
        else:
            last, age = None, 0
    return out


def assemble(tasks, feats, panel, text, panel_keys: List[str], include_targets=True) -> Dict[str, Any]:
    """Monthly frame: core (union of task inputs), panel (complete series), text (with gaps), labels per task."""
    core_keys = sorted({k for t in tasks for k in t.features})
    # sequences need consecutive months: carry each series' last value across gaps of up to GAP_FILL months (what was
    # known at the time — e.g. quarterly sentiment before 1978, a missing payroll vintage), then keep the longest run
    start = max(min(d) for d in [*(feats[k] for k in core_keys), *(panel[k] for k in panel_keys)])
    end = max(max(d) for d in [*(feats[k] for k in core_keys), *(panel[k] for k in panel_keys)])
    allm = _month_range(start, end)
    src = {**{k: _fill(feats[k], allm) for k in core_keys}, **{k: _fill(panel[k], allm) for k in panel_keys}}
    ok = [all(m in src[k] for k in src) for m in allm]
    best, cur = (0, 0), None
    for i, good in enumerate(ok + [False]):
        if good and cur is None:
            cur = i
        elif not good and cur is not None:
            best = (cur, i)  # newest complete run; an old long run is not a live input set
            cur = None
    months = allm[best[0]:best[1]]
    C = np.array([[src[k][m] for k in core_keys] for m in months], float)
    P = np.array([[src[k][m] for k in panel_keys] for m in months], float)
    tk = sorted(text)
    T = np.array([[text[k].get(m, np.nan) for k in tk] for m in months], float)
    Y = np.full((len(months), len(tasks)), np.nan)
    for j, t in enumerate(tasks):
        tgt = t.target() if include_targets else {}
        for i, m in enumerate(months):
            if m in tgt:
                Y[i, j] = tgt[m]
    return {"months": months, "C": C, "P": P, "T": T, "Y": Y, "core_keys": core_keys, "text_keys": tk,
            "tasks": [t.name for t in tasks], "known_after": [t.known_after for t in tasks]}


def fit_preprocessor(fr,train_end):
    C,P,T=fr['C'],fr['P'],fr['T']
    cm,cs=C[:train_end].mean(0),C[:train_end].std(0)+1e-9
    pm,ps=P[:train_end].mean(0),P[:train_end].std(0)+1e-9
    Zp=(P-pm)/ps
    _,_,vt=np.linalg.svd(Zp[:train_end],full_matrices=False)
    V=vt[:N_FACTORS].T;F=Zp@V
    fm,fs=F[:train_end].mean(0),F[:train_end].std(0)+1e-9
    observed=np.isfinite(T[:train_end]);count=observed.sum(0)
    tm=np.divide(np.where(observed,T[:train_end],0.).sum(0),count,out=np.zeros(T.shape[1]),where=count>0)
    variance=np.divide(np.where(observed,(T[:train_end]-tm)**2,0.).sum(0),count,out=np.zeros(T.shape[1]),where=count>0)
    ts=np.sqrt(variance)+1e-9
    tm=np.where(np.isfinite(tm),tm,0.);ts=np.where(np.isfinite(ts)&(ts>1e-9),ts,1.)
    return dict(cm=cm,cs=cs,pm=pm,ps=ps,V=V,fm=fm,fs=fs,tm=tm,ts=ts)


def transform_features(fr,state):
    C,P,T=fr['C'],fr['P'],fr['T'];s=state
    factors=((P-s['pm'])/s['ps'])@s['V']
    news=(T-s['tm'])/s['ts'];missing=~np.isfinite(news);news[missing]=0.
    return np.hstack([(C-s['cm'])/s['cs'],(factors-s['fm'])/s['fs'],news,missing.astype(float)]).astype(np.float32)


def _features(fr: Dict[str, Any], train_end: int) -> np.ndarray:
    """Fit only on training observations; the saved transform can later process new data."""
    return transform_features(fr,fit_preprocessor(fr,train_end))


def _windows(X: np.ndarray, idx: List[int]) -> np.ndarray:
    return np.stack([X[i - SEQ + 1:i + 1] for i in idx]).astype(np.float32)


def _make_net(d_in, d_out, cfg, groups=None):
    if cfg.architecture == "modular":
        from api.ml.modular import make_network
        return make_network(d_in,d_out,cfg,groups)
    import torch
    from torch import nn
    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru=nn.GRU(d_in,cfg.hidden,num_layers=cfg.layers,batch_first=True,dropout=cfg.dropout if cfg.layers>1 else 0.)
            self.attention=nn.MultiheadAttention(cfg.hidden,cfg.attention_heads,dropout=cfg.dropout,batch_first=True) if cfg.attention_heads else None
            self.norm=nn.LayerNorm(cfg.hidden)
            self.head=nn.Sequential(nn.Dropout(cfg.dropout),nn.Linear(cfg.hidden,max(16,cfg.hidden//2)),nn.GELU(),nn.Dropout(cfg.dropout),nn.Linear(max(16,cfg.hidden//2),d_out))
        def forward(self,x):
            h,_=self.gru(x);last=h[:,-1:]
            if self.attention is not None:
                context,_=self.attention(last,h,h,need_weights=False);last=last+context
            return self.head(self.norm(last[:,0]))
    return Net()


def _train(Xw: np.ndarray, Yw: np.ndarray, seed: int, cfg=None, cut=None, sample_weights=None, groups=None):
    import torch
    from torch import nn
    cfg=cfg or configured()
    if Xw.ndim!=3 or Yw.ndim!=2 or len(Xw)!=len(Yw) or len(Xw)<30 or not np.isfinite(Xw).all():raise ValueError('Insufficient or malformed neural training windows')
    torch.manual_seed(seed)
    cut=int(len(Xw)*.85) if cut is None else cut
    if not 10<=cut<len(Xw):raise ValueError('Chronological validation window is required')
    if not np.isfinite(Yw[:cut]).any() or not np.isfinite(Yw[cut:]).any():raise ValueError('Known training and validation labels are required')
    net=_make_net(Xw.shape[2],Yw.shape[1],cfg,groups)
    opt=torch.optim.AdamW(net.parameters(),lr=cfg.learning_rate,weight_decay=cfg.weight_decay)
    scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,patience=4,factor=.5,min_lr=1e-5)
    trained_heads=[len(np.unique(Yw[:cut,j][np.isfinite(Yw[:cut,j])]))==2 for j in range(Yw.shape[1])]
    if not any(trained_heads):raise ValueError('No task has both outcome classes in the training window')
    xt,yt=torch.tensor(Xw[:cut]),torch.tensor(Yw[:cut])
    xv,yv=torch.tensor(Xw[cut:]),torch.tensor(Yw[cut:])
    yt[:,~np.asarray(trained_heads,dtype=bool)]=float('nan');yv[:,~np.asarray(trained_heads,dtype=bool)]=float('nan')
    weights=np.ones(cut,dtype=np.float32) if sample_weights is None else np.asarray(sample_weights[:cut],dtype=np.float32)
    if weights.shape!=(cut,) or not np.isfinite(weights).all() or np.any(weights<=0):raise ValueError('Training weights must be positive and finite')
    wt=torch.tensor(weights)
    bce=nn.BCEWithLogitsLoss(reduction='none')
    def loss(x,y,w=None):
        mask=torch.isfinite(y);l=bce(net(x),torch.nan_to_num(y));m=mask.float()
        if w is not None:m=m*w[:,None]
        denom=m.sum(0);active=denom>0
        return ((l*m).sum(0)/denom.clamp(min=1e-9))[active].mean()
    best,best_state,bad=float('inf'),None,0;began=time.monotonic();reason='epoch limit';epochs=0
    for epoch in range(cfg.epochs):
        if time.monotonic()-began>cfg.seed_budget_seconds:reason='seed time budget';break
        net.train();perm=torch.randperm(len(xt))
        for b in range(0,len(xt),cfg.batch_size):
            ix=perm[b:b+cfg.batch_size]
            if not torch.isfinite(yt[ix]).any():continue
            opt.zero_grad();l=loss(xt[ix],yt[ix],wt[ix])
            if not torch.isfinite(l):raise ValueError('Nonfinite neural training loss')
            l.backward();nn.utils.clip_grad_norm_(net.parameters(),cfg.gradient_clip);opt.step()
        epochs=epoch+1;net.eval()
        with torch.no_grad():v=float(loss(xv,yv))
        if not np.isfinite(v):raise ValueError('Nonfinite validation loss')
        scheduler.step(v)
        if __import__('os').getenv('ML_TRACE_WORKER')=='1':
            from api.ml.live import training_event
            training_event(seed=seed,epoch=epochs,validation_loss=v,train_loss=float(l.detach()),profile=cfg.profile)
        if v<best-1e-4:best,best_state,bad=v,{k:t.detach().clone() for k,t in net.state_dict().items()},0
        else:
            bad+=1
            if bad>=cfg.patience:reason='early stopping';break
    if best_state is None:raise ValueError('Training budget expired before a validated checkpoint')
    net.load_state_dict(best_state);net.eval()
    net.trained_heads=trained_heads
    net.training_report={'profile':cfg.profile,'architecture':cfg.architecture,'modules':list(groups or {'combined_inputs':[]}), 'fingerprint':fingerprint(cfg),'parameters':sum(p.numel() for p in net.parameters()),'epochs':epochs,'validation_loss':best,'elapsed_s':time.monotonic()-began,'stop_reason':reason,'train_windows':cut,'validation_windows':len(Xw)-cut,'trained_heads':net.trained_heads}
    return net


def _predict(nets, Xw: np.ndarray) -> np.ndarray:
    import torch
    with torch.no_grad():
        x = torch.tensor(Xw)
        predictions=[]
        for n in nets:
            p=torch.sigmoid(n(x)).numpy();p[:,~np.asarray(n.trained_heads,dtype=bool)]=np.nan;predictions.append(p)
        return np.nanmean(predictions, axis=0)      # (rows, tasks)


def _labels_known(fr: Dict[str, Any], upto: str) -> np.ndarray:
    """Labels with each task's answer hidden unless known by `upto` (the refit date)."""
    Y = fr["Y"].copy()
    year,month=map(int,upto.split("-"))
    for j, ka in enumerate(fr["known_after"]):
        index=year*12+month-1-ka
        cut=f"{index//12}-{index%12+1:02d}"
        for i, m in enumerate(fr["months"]):
            if m >= cut:
                Y[i, j] = np.nan
    return Y


def _prepare(fr,train_end,origin,cfg):
    Y=_labels_known(fr,origin)
    idx=[i for i in range(SEQ-1,train_end) if np.isfinite(Y[i]).any()]
    if len(idx)<120:raise ValueError('Need at least 120 labelled sequence windows')
    cut=int(len(idx)*.85);validation_origin=fr['months'][idx[cut]]
    # Inner-validation transformations see training features only, not holdout features.
    X=_features(fr,idx[cut]);Yw=Y[idx].astype(np.float32)
    inner_known=_labels_known(fr,validation_origin)
    Yw[:cut]=inner_known[np.asarray(idx[:cut])]
    age=np.array([_months_between(fr['months'][i],validation_origin) for i in idx],float)
    weights=np.clip(np.exp(-np.log(2)*np.maximum(age,0)/cfg.recent_half_life_months),.05,1.).astype(np.float32)
    return X,idx,Yw,cut,weights


def _fold_cache(X,Yw,test,cut,cfg,compute,groups=None):
    import hashlib,json,os,tempfile
    from pathlib import Path
    h=hashlib.sha256((fingerprint(cfg)+str(cut)+str(test)+json.dumps(groups,sort_keys=True)).encode())
    for arr in (X[:max(test)+1],Yw):h.update(np.ascontiguousarray(arr).tobytes())
    directory=Path(__file__).resolve().parents[2]/'data'/'processed'/'ml_deep_folds'/fingerprint(cfg)
    path=directory/(h.hexdigest()+'.json')
    try:
        saved=np.asarray(json.loads(path.read_text()),dtype=float)
        if saved.shape==(len(test),Yw.shape[1]) and np.all(np.isnan(saved)|((saved>=0)&(saved<=1))):return saved
    except (OSError,ValueError,TypeError):pass
    result=compute()
    try:
        directory.mkdir(parents=True,exist_ok=True)
        if len(list(directory.glob('*.json')))<2000:
            rows=[[float(v) if np.isfinite(v) else None for v in row] for row in result]
            with tempfile.NamedTemporaryFile(mode='w',dir=directory,delete=False) as f:
                json.dump(rows,f,allow_nan=False);tmp=f.name
            os.replace(tmp,path)
    except OSError:pass
    return result


def _groups(fr):
    from api.ml.modular import feature_groups
    keys=fr.get("core_keys",[f"core_{i}" for i in range(fr["C"].shape[1])])
    return feature_groups(keys,min(N_FACTORS,fr["P"].shape[1]),fr.get("text_keys",[f"text_{i}" for i in range(fr["T"].shape[1])]))


def walk_forward(fr: Dict[str, Any], start_year: int = 1985) -> Dict[str, Dict[str, float]]:
    """Raw out-of-sample probabilities {task: {month: p}} — refit every REFIT_EVERY Januaries on data known by then."""
    import torch
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    cfg=configured()
    months = fr["months"]
    out: Dict[str, Dict[str, float]] = {t: {} for t in fr["tasks"]}
    last_year = int(months[-1][:4])
    for yr in range(start_year, last_year + 1, REFIT_EVERY):
        origin = f"{yr}-01"
        train_end = next((i for i, m in enumerate(months) if m >= origin), len(months))
        if train_end < SEQ + 96:
            continue
        try:X,idx,Yw,cut,weights=_prepare(fr,train_end,origin,cfg)
        except ValueError:continue
        test = [i for i, m in enumerate(months) if yr <= int(m[:4]) < yr + REFIT_EVERY and i >= SEQ - 1]
        if not test:continue
        def fit_predict():
            nets=[_train(_windows(X,idx),Yw,s,cfg,cut,weights,_groups(fr)) for s in range(cfg.seeds)]
            return _predict(nets,_windows(X,test))
        p=_fold_cache(X,Yw,test,cut,cfg,fit_predict,_groups(fr))
        for k, i in enumerate(test):
            for j, t in enumerate(fr["tasks"]):
                if np.isfinite(p[k,j]):out[t][months[i]]=round(float(p[k,j]),5)
        logger.info("[ml.deep] refit %s: %d training windows, %d test months", origin, len(idx), len(test))
    return out


def live(fr: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, List[float]]]:
    """Fit on everything known now; today's probability per task and each seed's (for the uncertainty)."""
    months = fr["months"]
    from datetime import datetime, timezone
    if __import__("os").getenv("ML_TRACE_WORKER")=="1":
        from api.ml.live import training_event
        training_event(stage="live_fit",message="Fitting the current research checkpoint")
    cfg=configured();X,idx,Yw,cut,weights=_prepare(fr,len(months),datetime.now(timezone.utc).strftime('%Y-%m'),cfg)
    nets=[_train(_windows(X,idx),Yw,s,cfg,cut,weights,_groups(fr)) for s in range(cfg.seeds)]
    import torch
    with torch.no_grad():
        x = torch.tensor(_windows(X, [len(months) - 1]))
        each=[]
        for n in nets:
            p=torch.sigmoid(n(x)).numpy()[0];p[~np.asarray(n.trained_heads,dtype=bool)]=np.nan;each.append(p)
    live.last_reports=[n.training_report for n in nets]
    if __import__('os').getenv('ML_TRACE_WORKER')=='1' and hasattr(nets[0],'trace'):
        from api.ml.live import save_checkpoint
        save_checkpoint(fr,nets,fit_preprocessor(fr,idx[cut]),cfg,purpose='full_research')
    live.last_routing=[n.routing(x) for n in nets if hasattr(n,"routing")]
    p = np.nanmean(each, axis=0)
    return ({t:float(p[j]) for j,t in enumerate(fr["tasks"]) if np.isfinite(p[j])},
            {t:[float(e[j]) for e in each if np.isfinite(e[j])] for j,t in enumerate(fr["tasks"]) if np.isfinite(p[j])})


def load_frame(include_targets=True) -> Dict[str, Any]:
    """Shared ingestion contract for data checks, automatic learning and worker training."""
    from api.ml import features as F
    from api.ml import panel as PN
    from api.ml.engine import FFILL_MONTHS, _carry, panel_keys
    from api.ml.tasks import TASKS
    feats, panel, text = F.load(), PN.load(), F.load_text()
    from api.ml import context
    text = {**text, **context.load()}
    tasks = [t for t in TASKS.values() if all(k in feats for k in t.features)]
    if len(tasks)!=len(TASKS):raise ValueError('Required task inputs are missing')
    pk = panel_keys(panel)
    if len(pk)<8:raise ValueError('Insufficient macro-panel coverage')
    recent = sorted({m for k in pk for m in panel[k]})[-FFILL_MONTHS - 1:]
    recent += [m for m in sorted({m for t in tasks for k in t.features for m in feats[k]}) if m > recent[-1]]
    panel = {k: _carry(panel[k], recent) for k in pk}
    fr = assemble(tasks, feats, panel, text, pk,include_targets=include_targets)
    from datetime import datetime,timezone
    if not fr['months'] or not 0<=_months_between(fr['months'][-1],datetime.now(timezone.utc).strftime('%Y-%m'))<=3:raise ValueError('Deep-model inputs are stale, empty or future-dated')
    fr['panel_keys']=pk
    return fr


def build() -> Dict[str, Any]:
    """Assemble, walk forward and fit live inside the isolated worker."""
    fr=load_frame()
    from api.ml.continual import signature
    from datetime import datetime,timezone
    digest=signature(fr,datetime.now(timezone.utc).strftime("%Y-%m"))
    bt = walk_forward(fr)
    now, seeds = live(fr)
    return {"data_digest":digest,"configuration":asdict(configured()),"modules":_groups(fr),"routing":getattr(live,"last_routing",[]),"fingerprint":fingerprint(),"training_reports":getattr(live,"last_reports",[]),"backtest": bt, "now": now, "seeds": seeds, "as_of": fr["months"][-1],
            "inputs": len(fr["core_keys"]) + N_FACTORS + 2 * len(fr["text_keys"]), "sequence_months": SEQ, "tasks": fr["tasks"],
            "window": [fr["months"][0], fr["months"][-1]]}


def _run_worker() -> Dict[str, Any]:
    """PyTorch runs in its own process: on macOS its OpenMP runtime and LightGBM's crash one process that loads both
    (a segmentation fault), so the backend never imports torch — it starts this worker and reads its JSON."""
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    r = subprocess.run([sys.executable, "-m", "api.ml.deep"], cwd=root, capture_output=True, text=True, timeout=3 * 3600,
                       env={**os.environ, "OMP_NUM_THREADS": "4", "ML_DEEP_PARENT_PID":str(os.getpid()),"ML_TRACE_WORKER":"1"})
    if r.returncode != 0:
        raise RuntimeError(f"deep worker exited {r.returncode}: {(r.stderr or '')[-400:]}")
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


_joint_lock=threading.Lock()
_joint_state={"training":False}


def status():
    from api.ml.deep_config import catalogue
    from api.ml.continual import status as learning_status
    return {**catalogue(),**_joint_state,'continual':learning_status()}


def joint(force: bool = False) -> Optional[Dict[str, Any]]:
    """One isolated Torch worker shared by all tasks; architecture/protocol caches never mix."""
    from api import research_indicators as ri
    with _joint_lock:
        _joint_state.update(training=True,started_at=time.time())
        try:
            from datetime import datetime,timezone
            cache_key='ml_deep_v4_'+fingerprint()+'_'+datetime.now(timezone.utc).strftime('%Y-%m')
            data,cache=ri._cached(cache_key,_run_worker,ttl=0 if force else 30*24*3600)
            _joint_state.update(cache_status=cache,last_completed=time.time(),fingerprint=fingerprint(),modules=(data or {}).get('modules'),routing=(data or {}).get('routing'),training_reports=(data or {}).get('training_reports'))
            if force and cache!='ok':raise RuntimeError('Fresh research rebuild failed; stale results are not a completed refit')
            if data and data.get('fingerprint')!=fingerprint():return None
            return data
        finally:_joint_state['training']=False


def _worker_parent_guard():
    """Stop a detached worker after its backend exits, avoiding duplicate orphan fits."""
    import os
    parent=os.getenv('ML_DEEP_PARENT_PID')
    if not parent:return
    expected=int(parent)
    if os.getppid()!=expected:os._exit(1)
    def watch():
        while True:
            time.sleep(3)
            if os.getppid()!=expected:os._exit(1)
    threading.Thread(target=watch,name='deep-parent-watch',daemon=True).start()


if __name__ == "__main__":                                      # the worker: python -m api.ml.deep
    import json
    import sys
    import warnings
    warnings.filterwarnings("ignore")
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:                                           # noqa: BLE001 — the config module reads the key too
        pass
    _worker_parent_guard()
    if '--preview' in sys.argv or '--infer' in sys.argv:
        from api.ml.live import worker
        result=worker(preview='--preview' in sys.argv)
    else:
        from api.ml.live import training_event
        training_event(stage='walk_forward',message='Building chronological research records')
        result=build()
        training_event(stage="complete",message="Research checkpoint and measured states complete")
    sys.stdout.write(json.dumps(result) + "\n")


def request_retrain():
    """Explicit background rebuild, shared across all tasks; no model promotion."""
    if _joint_state.get('training') or not _retrain_lock.acquire(blocking=False):return {**status(),'queued':False,'reason':'A shared training worker is already active'}
    _joint_state.update(training=True,requested_at=time.time(),error=None)
    def work():
        result=None
        try:
            result=joint(force=True)
            if result is None:_joint_state['error']='No validated research checkpoint was produced.'
            else:
                from api.ml import engine
                engine._mem.clear()  # next task request recalibrates against the new versioned record
        except Exception as exc:
            logger.exception('[ml.deep] rebuild failed')
            _joint_state['error']=f'Rebuild failed ({type(exc).__name__}); the champion remains available.'
        finally:
            from api.ml.continual import completed
            try:completed(not bool(_joint_state.get('error')),digest=(result or {}).get('data_digest'))
            except OSError:logger.warning('Could not persist neural learning completion')
            _joint_state['training']=False;_retrain_lock.release()
    threading.Thread(target=work,name='deep-research-rebuild',daemon=True).start()
    return {**status(),'queued':True}

_retrain_lock=threading.Lock()


_peek_lock=threading.Lock()


def peek(start=False):
    """Read this version's completed cache without waiting for the shared worker."""
    from datetime import datetime,timezone
    from api.handlers.macro_inputs import _disk_load
    key='ri_ml_deep_v4_'+fingerprint()+'_'+datetime.now(timezone.utc).strftime('%Y-%m')
    hit=_disk_load(key,max_age=30*24*3600)
    data=(hit or {}).get('data')
    if data and data.get('fingerprint')==fingerprint():return data
    if start:
        with _peek_lock:
            if not _joint_state.get('training'):
                _joint_state.update(training=True,error=None)
                def work():
                    try:
                        result=joint()
                        if result:
                            from api.ml import engine
                            engine._mem.clear()
                    except Exception as exc:
                        logger.exception('Background deep fit failed')
                        _joint_state.update(training=False,error=f'Deep fit failed ({type(exc).__name__}); other models remain available.')
                threading.Thread(target=work,name='deep-optional-fit',daemon=True).start()
    return None
