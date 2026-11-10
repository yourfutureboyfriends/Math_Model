import subprocess,sys
from pathlib import Path
from api.ml import live as L


def test_api_live_status_never_imports_torch(monkeypatch,tmp_path):
    monkeypatch.setattr(L,'ROOT',tmp_path)
    before='torch' in sys.modules
    result=L.status()
    assert not result['checkpoint_available'] and result['trace'] is None
    assert ('torch' in sys.modules)==before


def test_training_progress_keeps_recent_finite_metrics(monkeypatch,tmp_path):
    monkeypatch.setattr(L,'ROOT',tmp_path)
    monkeypatch.setenv('ML_TRACE_KIND','preview')
    L.training_event(stage='preview_fit',seed=0,epoch=1,validation_loss=.6)
    L.training_event(seed=0,epoch=2,validation_loss=.5)
    result=L.status()['preview_training']
    assert result['stage']=='preview_fit' and result['epoch']==2 and len(result['history'])==2


def test_measured_trace_is_causal_and_checkpoint_inference_matches(tmp_path):
    code='''import json,sys,numpy as np,torch
from pathlib import Path
from dataclasses import replace
from api.ml import deep as D,live as L
from api.ml.deep_config import PROFILES
from api.ml.modular import feature_groups
torch.set_num_threads(2);L.ROOT=Path(sys.argv[1])
rng=np.random.default_rng(10);n=200
fr={'months':[f'{2000+i//12}-{i%12+1:02d}' for i in range(n)],'C':rng.normal(size=(n,3)),'P':rng.normal(size=(n,3)),'T':rng.normal(size=(n,1)),'Y':rng.integers(0,2,(n,2)).astype(float),'tasks':['a','b'],'core_keys':['ts','pay6','spx6'],'text_keys':['news'],'panel_keys':['p1','p2','p3'],'known_after':[4,7]}
state=D.fit_preprocessor(fr,140);X=D.transform_features(fr,state);indices=list(range(23,180));groups=feature_groups(fr['core_keys'],3,fr['text_keys'])
cfg=replace(PROFILES['expanded'],epochs=2,seeds=1,seed_budget_seconds=20)
net=D._train(D._windows(X,indices),fr['Y'][indices],0,cfg,cut=120,groups=groups)
x=torch.tensor(D._windows(X,[199]));t=net.trace(x)
for step in (0,7,23):
 with torch.no_grad():expected=torch.sigmoid(net(x[:,:step+1])).numpy()[0]
 assert np.allclose(t['probabilities'][step],expected,atol=1e-6)
 assert len(t['attention'][step])==step+1 and abs(sum(t['attention'][step])-1)<1e-6
changed=x.clone();changed[:,8:]+=10
assert np.allclose(net.trace(changed)['probabilities'][:8],t['probabilities'][:8],atol=1e-6)
first=L.save_checkpoint(fr,[net],state,cfg,'inspection_preview')
D.load_frame=lambda **kw:fr
result=L.worker(preview=False);second=L.status()['trace']
assert result['ok'] and second['purpose']=='inspection_preview' and not second['inputs_changed']
assert np.allclose(first['seeds'][0]['probabilities'],second['seeds'][0]['probabilities'],atol=1e-7)
fr['C'][-1,0]+=1;L.worker(preview=False);assert L.status()['trace']['inputs_changed']
print(json.dumps({'steps':len(t['routing']),'modules':len(t['modules']),'checkpoint_roundtrip':True}))'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,timeout=100)
    assert result.returncode==0,result.stderr[-2500:]
