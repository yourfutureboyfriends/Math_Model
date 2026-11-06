import json
import subprocess
import sys
import pytest
from api.ml import continual as C
from api.ml.modular import feature_groups,validate_groups


def test_routing_covers_every_feature_once():
    groups=feature_groups(['ts','pay6','spx6','unknown'],8,['news','epu'])
    assert groups['rates_credit']==[0] and groups['real_economy']==[1] and groups['market_prices']==[2]
    assert validate_groups(groups,16)==groups
    with pytest.raises(ValueError):validate_groups({'a':[0,1],'b':[1,2]},3)


@pytest.fixture
def learning(monkeypatch,tmp_path):
    from api.ml import deep
    monkeypatch.setattr(C,'STATE',tmp_path/'learning.json')
    monkeypatch.setattr(deep,'status',lambda:{'training':False})
    monkeypatch.setenv('ML_AUTO_LEARN','1')
    return {'digest':'v1','as_of':'2026-10','months':400,'tasks':['test']}


def test_changed_data_refits_once_and_cooldowns_survive_reload(learning):
    calls=[];queue=lambda:(calls.append(1) or {'queued':True})
    now=2_000_000_000
    r=C.cycle(now=now,observer=lambda:learning,requester=queue)
    assert r['action']=='queued' and len(calls)==1
    assert C.cycle(now=now+1,observer=lambda:learning,requester=queue)['action']=='cooldown'
    assert C.cycle(now=now+86401,observer=lambda:learning,requester=queue)['action']=='unchanged'
    learning['digest']='v2'
    assert C.cycle(now=now+2*86401,observer=lambda:learning,requester=queue)['action']=='refit_cooldown'
    assert C.cycle(now=now+8*86401,observer=lambda:learning,requester=queue)['action']=='queued'
    assert len(calls)==2


def test_failed_learning_preserves_service_and_retries(learning):
    def bad():raise ValueError('bad source')
    now=2_000_000_000
    assert C.cycle(now=now,observer=bad)['action']=='blocked'
    assert C.cycle(now=now+86401,observer=lambda:learning,requester=lambda:{'queued':True})['action']=='queued'
    C.completed(False)
    assert 'accepted_digest' not in C._read()
    assert C.cycle(now=now+2*86401,observer=lambda:learning,requester=lambda:{'queued':True})['action']=='queued'


def test_disabled_learning_never_fetches(learning,monkeypatch):
    monkeypatch.setenv('ML_AUTO_LEARN','0')
    assert C.cycle(observer=lambda:pytest.fail('should not fetch'))['action']=='disabled'


def test_specialists_train_route_and_receive_gradients_in_worker():
    code='''import json,numpy as np,torch
from dataclasses import replace
from api.ml.deep_config import PROFILES
from api.ml import deep as D
from api.ml.modular import feature_groups
torch.set_num_threads(2)
cfg=replace(PROFILES['expanded'],epochs=3,seeds=1,seed_budget_seconds=30)
groups=feature_groups(['ts','pay6','spx6'],3,['news'])
rng=np.random.default_rng(5);X=rng.normal(size=(100,24,8)).astype('float32');Y=(X[:,-1,:2]>0).astype('float32')
net=D._train(X[:80],Y[:80],0,cfg,cut=60,groups=groups)
p=D._predict([net],X[80:]);assert p.shape==(20,2) and np.isfinite(p).all()
weights=net.routing(torch.tensor(X[80:]));assert abs(sum(weights.values())-1)<1e-6
assert set(weights)==set(groups)
net.train();net.zero_grad();net(torch.tensor(X[:8])).sum().backward()
assert all(any(p.grad is not None and p.grad.abs().sum()>0 for p in encoder.parameters()) for encoder in net.encoders.values())
net.eval()
a=torch.tensor(X[:1]);b=a.clone();b[:,-1,0]+=2
with torch.no_grad():assert not torch.allclose(net(a),net(b))
print(json.dumps({'routing':weights,'parameters':net.training_report['parameters'],'test_brier':float(np.mean((p-Y[80:])**2))}))'''
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=90)
    assert r.returncode==0,r.stderr[-2000:]
    assert json.loads(r.stdout.splitlines()[-1])['parameters']>0


def test_forced_refit_does_not_treat_stale_cache_as_success(monkeypatch):
    from api.ml import deep
    from api import research_indicators as ri
    from api.ml.deep_config import fingerprint
    monkeypatch.setattr(ri,'_cached',lambda *a,**kw:({'fingerprint':fingerprint()},'stale-cache'))
    with pytest.raises(RuntimeError,match='stale results'):deep.joint(force=True)
    assert not deep.status()['training']


def test_learning_digest_ignores_unmatured_targets_but_detects_new_inputs():
    import copy
    from api.tests.test_ml_scaling import frame
    fr=frame();fr.update(core_keys=['ts','pay6','spx6'],text_keys=['news','epu'])
    a=C.signature(fr,'2019-12');changed=copy.deepcopy(fr)
    changed['Y'][-1,:]=1-changed['Y'][-1,:]
    assert C.signature(changed,'2019-12')==a
    changed['C'][-1,0]+=1
    assert C.signature(changed,'2019-12')!=a
