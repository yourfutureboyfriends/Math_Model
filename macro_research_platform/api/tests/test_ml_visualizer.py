import numpy as np
from api.ml import engine as E,deep as D,visualizer as V
from api.ml.tasks import Task


def test_deep_peek_never_waits_on_joint_when_training(monkeypatch):
    from api.handlers import macro_inputs
    monkeypatch.setattr(macro_inputs,'_disk_load',lambda *a,**kw:None)
    monkeypatch.setattr(D,'joint',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('blocked')))
    monkeypatch.setattr(D,'_joint_state',{'training':True})
    assert D.peek(start=True) is None


def test_visualizer_fit_does_not_call_deep_or_walk_forward(monkeypatch):
    from api.ml import features as F
    months=[f'{1980+i//12}-{i%12+1:02d}' for i in range(360)]
    target=dict(zip(months,[i%2 for i in range(360)]))
    t=Task('viz','Viz','?',[],['a'],4,lambda:target)
    monkeypatch.setitem(E.TASKS,'viz',t)
    monkeypatch.setattr(F,'load',lambda:{'a':dict(zip(months,np.sin(np.arange(360)/3)))})
    monkeypatch.setattr(D,'joint',lambda *a,**k:(_ for _ in ()).throw(AssertionError('deep called')))
    monkeypatch.setattr(E,'walk_forward',lambda *a,**k:(_ for _ in ()).throw(AssertionError('backtest called')))
    d=V.build('viz')
    assert d['available'] and d['inspection_only'] and d['network']['calibration'] is None
    assert len(d['network']['weights']['nets'])==3
    assert all(s>0 for s in d['network']['weights']['sd'])


def test_export_preserves_small_positive_scales():
    net=E.BaggedNet(n=1).fit(np.array([[1.,0],[1.,1],[1.,2],[1.,3]]),np.array([0,0,1,1]))
    w=net.export()
    assert w['sd'][0]>0


def test_failed_inspection_does_not_get_stuck_in_error_cache(monkeypatch):
    from datetime import datetime,timezone
    monkeypatch.setattr(E,'cached',lambda name:None)
    monkeypatch.setattr(V,'_mem',{'recession_12m':{'month':datetime.now(timezone.utc).strftime('%Y-%m'),'available':False,'reason':'failed'}})
    assert not V.request('recession_12m')['available']
    assert 'recession_12m' not in V._mem


def test_detached_worker_guard_exits_before_training():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-c',"import os;os.environ['ML_DEEP_PARENT_PID']='-1';from api.ml.deep import _worker_parent_guard;_worker_parent_guard();raise AssertionError('guard failed')"],capture_output=True,timeout=20)
    assert result.returncode==1 and b'guard failed' not in result.stderr
