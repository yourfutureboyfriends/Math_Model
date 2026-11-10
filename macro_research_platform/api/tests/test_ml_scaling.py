from dataclasses import replace
import json
import subprocess
import sys
import numpy as np
import pytest
from api.ml import deep as D,engine as E
from api.ml.deep_config import PROFILES,configured,fingerprint,model_key,validate
from api.ml.tasks import Task


def frame(n=360):
    rng=np.random.default_rng(11)
    return {'months':[f'{1990+i//12}-{i%12+1:02d}' for i in range(n)],'C':rng.normal(size=(n,3)),'P':rng.normal(size=(n,10)),
            'T':rng.normal(size=(n,2)),'Y':rng.integers(0,2,size=(n,2)).astype(float),'tasks':['a','b'],'known_after':[4,24]}


def test_capacity_is_bounded_and_versions_change(monkeypatch):
    assert PROFILES['research_xl'].hidden==256 and PROFILES['research_xl'].layers==4
    assert fingerprint(PROFILES['research_xl'])!=fingerprint(PROFILES['reference'])
    with pytest.raises(ValueError):validate(replace(PROFILES['expanded'],seeds=500))
    monkeypatch.setenv('ML_DEEP_PROFILE','bad')
    with pytest.raises(ValueError):configured()


def test_live_labels_use_current_month_not_january():
    fr=frame();y=D._labels_known(fr,'2010-06');idx=fr['months'].index('2010-01')
    assert np.isfinite(y[idx,0]) and np.isnan(y[idx+1,0])
    assert np.isnan(y[fr['months'].index('2008-06'),1])


def test_inner_validation_purges_targets_and_fits_scalers_before_holdout():
    fr=frame();X,idx,Y,cut,w=D._prepare(fr,300,'2015-01',PROFILES['expanded'])
    boundary=fr['months'][idx[cut]]
    for j,lag in enumerate(fr['known_after']):
        for row,i in enumerate(idx[:cut]):
            if D._months_between(fr['months'][i],boundary)<=lag:assert np.isnan(Y[row,j])
    changed={**fr,'C':fr['C'].copy(),'P':fr['P'].copy()};changed['C'][idx[cut]:]+=1000;changed['P'][idx[cut]:]+=1000
    X2,*_=D._prepare(changed,300,'2015-01',PROFILES['expanded'])
    np.testing.assert_allclose(X[:idx[cut]],X2[:idx[cut]],atol=1e-6)
    assert w[0]<w[cut-1] and np.isfinite(X).all()


@pytest.fixture
def ledger(monkeypatch,tmp_path):
    import sqlite3
    monkeypatch.setattr(E,'_ready',False)
    def conn():
        c=sqlite3.connect(tmp_path/'models.db');c.row_factory=sqlite3.Row;return c
    monkeypatch.setattr(E,'_conn',conn);E._init()


def test_live_challenger_is_compared_on_identical_months(ledger):
    task=Task('t','T','?',[],[],0,lambda:{'2000-01':0,'2000-02':0})
    E.log_forecast('t','champion','2000-01',.9);E.log_forecast('t','network','2000-01',.8)
    E.log_forecast('t','champion','2000-02',0.)
    r=E.live_record(task)['models']['network']
    assert r['ahead_of_champion'] and r['paired_champion_brier']==.81


def test_old_deep_cohort_does_not_transfer_to_new_architecture(ledger):
    with E._conn() as c:c.execute("INSERT INTO ml_forecasts VALUES ('t','deep_sequence','2000-01',.1,'2000-01-01')")
    E.log_forecast('t','champion','2000-01',.2)
    task=Task('t','T','?',[],[],0,lambda:{'2000-01':0})
    assert 'deep_sequence' not in E.live_record(task)['models']
    E.log_forecast('t','deep_sequence','2000-01',.1)
    assert E.live_record(task)['models']['deep_sequence']['scored']==1


def test_pytorch_profiles_train_in_isolated_process():
    # Never combine LightGBM and Torch OpenMP runtimes in the API/pytest process on macOS.
    code='''import json,numpy as np,torch
from dataclasses import replace
from api.ml import deep as D
from api.ml.deep_config import PROFILES
torch.set_num_threads(2)
rng=np.random.default_rng(7);X=rng.normal(size=(100,24,8)).astype('float32');Y=(X[:,-1,:2]>0).astype('float32')
reports={}
for name in ('reference','expanded','research_xl'):
 cfg=replace(PROFILES[name],epochs=2,seeds=1,seed_budget_seconds=20)
 net=D._train(X[:80],Y[:80],0,cfg,cut=60)
 p=D._predict([net],X[80:]);assert p.shape==(20,2) and np.isfinite(p).all()
 reports[name]={'parameters':net.training_report['parameters'],'epochs':net.training_report['epochs'],'test_brier':float(np.mean((p-Y[80:])**2))}
assert reports['research_xl']['parameters']>100*reports['reference']['parameters']
print(json.dumps(reports))'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr[-1500:]
    report=json.loads(result.stdout.splitlines()[-1]);assert report['research_xl']['epochs']==2
