"""Executable contract tests for the opt-in institutional/autonomous package."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn
from api.ml.institutional.model import MacroTFT,ModelConfig,DenseGAT
from api.ml.institutional.data import PITFeatureStore,Observation,FeatureSpec
from api.ml.institutional.continual import ReplayBuffer,Experience,EWC,FineTuneConfig,daily_fine_tune
from api.ml.institutional.ingestion import FinancialIngestionAgent,EventBatch
from api.ml.institutional.graph import DynamicEventGraph,graph_tensors,rolling_graph_statistics
from api.ml.institutional.losses import MultiTaskLoss
from api.ml.institutional.monitor import DistributionMonitor
from api.ml.institutional.registry import PromotionGate,GateConfig,ModelRegistry
from api.ml.institutional.lineage import digest,file_digest,InferenceAudit,InferenceManifest
from api.ml.institutional.uncertainty import SplitConformal
from api.ml.institutional.validation import WalkForward,PurgedKFold

torch.set_num_threads(2)


def test_tft_shapes_gradients_and_decoder_causality():
    torch.manual_seed(4)
    model = MacroTFT(ModelConfig(domains=5,domain_inputs=3,graph_inputs=4,known_future_inputs=2,tasks=2,hidden=16,heads=2,dropout=0.))
    x,nodes,edges,future = torch.randn(2,8,5,3),torch.randn(2,7,4),torch.tensor([[0,1],[1,2]]),torch.randn(2,12,2)
    model.eval()
    a = model(x,nodes,edges,future)
    assert a['predictions'].shape==(2,4,2)
    assert torch.allclose(a['variable_selection'].sum(-1),torch.ones(2,8))
    changed = future.clone(); changed[:,-1] += 100
    b = model(x,nodes,edges,changed)
    torch.testing.assert_close(a['predictions'][:,0],b['predictions'][:,0])
    loss = a['predictions'].square().mean()+.01*a['load_balance']
    loss.backward()
    assert model.moe.router.weight.grad.abs().sum()>0
    assert model.graph.first.projection.weight.grad.abs().sum()>0
    assert (a['routing']>0).sum(-1).max()<=2


def test_gat_direction_and_invalid_edges():
    gat = DenseGAT(3,8,2)
    _,weights = gat(torch.randn(1,3,3),torch.tensor([[0],[1]]))
    assert weights[0,:,1,0].sum()>0 and weights[0,:,0,1].sum()==0
    with pytest.raises(ValueError): gat(torch.randn(1,3,3),torch.tensor([[3],[0]]))


def test_pit_latest_vintage_and_mixed_release_alignment(tmp_path):
    store = PITFeatureStore(tmp_path/'pit.sqlite')
    def put(feature,period,release,value):
        store.append(Observation('US',feature,period,release,release,value,'a'*64),now=release)
    put('GDP','2020-03-31T23:00:00Z','2020-04-30T12:30:00Z',1.)
    put('GDP','2020-03-31T23:00:00Z','2020-05-30T12:30:00Z',9.)
    spec = [FeatureSpec('US','GDP',max_age='180D')]
    assert np.isnan(store.view('2020-04-20T00:00:00Z',spec)[0]['US:GDP'])
    old,old_digest = store.view('2020-05-01T00:00:00Z',spec)
    new,new_digest = store.view('2020-06-01T00:00:00Z',spec)
    assert old['US:GDP']==1 and new['US:GDP']==9 and old_digest!=new_digest


def test_masked_multitask_loss_and_conformal_scope():
    criterion = MultiTaskLoss(('binary','regression'),2,focal_tasks=(0,))
    pred = torch.zeros(3,2,2,requires_grad=True)
    target = torch.full_like(pred,float('nan')); target[:,:,0] = torch.tensor([0.,1.,0.])[:,None]
    loss = criterion(pred,target,torch.isfinite(target)); loss.backward()
    assert torch.isfinite(loss) and pred.grad[:,:,1].sum()==0
    p = np.full((100,2,1),.5); y = np.tile([0,1],50)[:,None,None]*np.ones((1,2,1))
    conformal = SplitConformal(('binary',),minimum=20).fit(p,y,np.ones_like(y,dtype=bool),model_digest='frozen')
    out = conformal.predict(p[:1],model_digest='frozen')
    assert out['label_sets'][0].shape==(1,2,2)
    assert out['label_sets'][0].all()
    with pytest.raises(ValueError): conformal.predict(p[:1],model_digest='changed')


def test_purging_and_label_maturity():
    origin = pd.date_range('2000-01-01',periods=200,freq='D',tz='UTC')
    ends,known = origin+pd.Timedelta(days=10),origin+pd.Timedelta(days=20)
    folds = list(WalkForward(min_train=30,validation_rows=10,step=10,embargo='5D').split(origin,ends,known))
    assert folds
    for train,test in folds:
        assert (known[train]<=origin[test[0]]-pd.Timedelta(days=5)).all()
    for train,test in PurgedKFold(4,'5D').split(origin,ends):
        assert ((ends[train]<origin[test].min()-pd.Timedelta(days=5))|(origin[train]>ends[test].max()+pd.Timedelta(days=5))).all()


def event(identifier='1',available='2025-01-01T00:00:00Z'):
    return {'id':identifier,'entity':'fed','action':'guidance','source_digest':'a'*64,
            'available_at':available,'first_seen_at':available,'confidence':.9}


def test_graph_pit_decay_snapshot_and_deduplication(tmp_path):
    graph = DynamicEventGraph(tmp_path,('rates','oil'),half_life_days=10)
    graph.append([event(),event()],cutoff='2025-01-01T00:00:00Z',sources_complete=True)
    first,one = graph.snapshot('2025-01-01T00:00:00Z')
    later,two = graph.snapshot('2025-01-11T00:00:00Z')
    assert one!=two and len(first)==len(later)
    a = next(iter(first.edges)); assert later.edges[a]['weight']==pytest.approx(first.edges[a]['weight']/2)
    x,edges,names = graph_tensors(first,'2025-01-01T00:00:00Z')
    assert x.shape==(len(names),20) and edges.shape[0]==2
    with pytest.raises(ValueError): graph.append([event('future','2025-02-01T00:00:00Z')],cutoff='2025-01-01T00:00:00Z',sources_complete=True)
    stats = rolling_graph_statistics([('2025-01-01T00:00:00Z',first),('2025-01-11T00:00:00Z',later)],'2025-01-01T00:00:00Z')
    assert stats.incoming_weight_momentum.isna().all()


def test_extraction_rejects_unsupported_quotes_and_future_release(tmp_path):
    class Extractor:
        def invoke(self,messages):
            return EventBatch.model_validate({'events':[{'entity':'Fed','action':'guidance','sentiment':-.2,'confidence':.9,'evidence':'a quote that is not in the source'}]})
    agent = FinancialIngestionAgent(Extractor(),'test-model-v1',tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    assert not agent.extract_document(text='Federal Reserve statement about interest rates.',url='https://example.com',published_at=now,first_seen=now,now=now)
    with pytest.raises(ValueError): agent.extract_document(text='example',url='https://example.com',published_at='2099-01-01T00:00:00Z',first_seen=now,now=now)


def experience(i=0):
    return Experience(str(i),'2024-01-01T00:00:00Z','2024-02-01T00:00:00Z','schema1','stress' if i%2 else 'normal',{'x':torch.tensor([[1.,float(i%3)]]),'y':torch.tensor([[float(i%2)]])})


def test_replay_maturity_sampling_and_ewc(tmp_path):
    replay = ReplayBuffer(tmp_path/'replay.sqlite',capacity=20)
    for i in range(20): replay.add(experience(i),cutoff='2025-01-01T00:00:00Z')
    sampled = replay.sample(8,cutoff='2025-01-01T00:00:00Z',schema='schema1')
    assert len(sampled)==8 and {e.stratum for e in sampled}=={'normal','stress'}
    with pytest.raises(ValueError): replay.add(experience(99),cutoff='2024-01-01T00:00:00Z')
    model = nn.Linear(2,1)
    def loss(m,t): return nn.functional.binary_cross_entropy_with_logits(m(t['x']),t['y'])
    ewc = EWC.estimate(model,sampled,loss)
    assert float(ewc.penalty(model))==0
    with torch.no_grad(): model.weight.add_(1)
    assert ewc.penalty(model)>0
    report = daily_fine_tune(model,[experience(100)],replay,loss,cutoff='2025-01-01T00:00:00Z',schema='schema1',ewc=ewc,config=FineTuneConfig(steps=2))
    assert report['steps']==2
    assert daily_fine_tune(model,[],replay,loss,cutoff='2025-01-01T00:00:00Z',schema='schema1',ewc=ewc)['status']=='skipped_no_new_matured_labels'


def test_drift_requires_distinct_windows_and_enough_samples():
    rng = np.random.default_rng(1)
    monitor = DistributionMonitor(rng.normal(size=(200,3)),patience=2)
    changed = rng.normal(10,1,size=(100,3))
    assert not monitor.update(changed,window_id='a').trigger
    assert not monitor.update(changed,window_id='a').trigger
    assert monitor.update(changed,window_id='b').trigger
    assert not monitor.update(changed[:2],window_id='c').ready


def test_audit_records_and_no_clobber(tmp_path):
    manifest = InferenceManifest(*(['a'*64]*9),'commit1')
    with InferenceAudit(tmp_path,manifest,'b'*64,'2025-01-01T00:00:00Z') as audit:
        audit.result({'probability':.5})
    records = list(tmp_path.glob('*.completed.json'))
    assert len(records)==1 and json.loads(records[0].read_text())['status']=='completed'


def test_promotion_rejects_short_or_leaking_evidence():
    gate = PromotionGate()
    assert not gate.evaluate(pd.DataFrame(),pd.DataFrame(),cutoff='2025-01-01T00:00:00Z',candidate_recipe='c',champion_recipe='b',attempt=1,required_cells={('recession',12)})['promote']


def test_registry_atomic_cas_and_idempotence(tmp_path):
    registry = ModelRegistry(tmp_path/'registry.sqlite')
    def register(name):
        folder = tmp_path/name; folder.mkdir()
        files = {}
        for kind in ('weights','preprocessor','calibrator','target_schema','configuration'):
            path = folder/(kind+'.txt'); path.write_text(name+kind)
            files[kind] = {'path':path.name,'sha256':file_digest(path)}
        return registry.register(folder,{'files':files,'pit_verified':True,'recipe_digest':digest(name)})
    old,new = register('old'),register('new')
    registry.bootstrap(old)
    decision = registry.decide(new,old,{'promote':True,'reason':'test_passed'},run_id='one')
    assert registry.champion()==new and decision['promote']
    assert registry.decide(new,old,{},run_id='one')==decision
    assert not registry.decide(old,old,{'promote':True},run_id='stale')['promote']


def test_paired_gate_positive_path_and_lookahead_guard():
    rng = np.random.default_rng(8)
    origin = pd.date_range('2000-01-01',periods=160,freq='MS',tz='UTC')
    y = rng.integers(0,2,len(origin))
    frame = pd.DataFrame({'origin':origin,'task':'recession','horizon':12,'label_id':[str(i) for i in range(len(origin))],
        'target':y,'label_known_at':origin+pd.Timedelta(days=730),
        'champion_probability':rng.uniform(.3,.7,len(origin)),'challenger_probability':np.where(y==1,.9,.1),
        'champion_trained_through':origin-pd.Timedelta(days=1),'challenger_trained_through':origin-pd.Timedelta(days=1),
        'feature_asof':origin,'evaluation_mode':'prospective','prediction_available_at':origin,
        'candidate_recipe':'c','champion_recipe':'b','target_schema':'s'})
    daily = rng.normal(0,.01,300)
    returns = pd.DataFrame({'date':pd.date_range('2020-01-01',periods=300,tz='UTC'),
        'champion_net_excess_return':daily,'challenger_net_excess_return':daily+.003,
        'cost_model_digest':'cost','execution_policy_digest':'policy','candidate_recipe':'c','champion_recipe':'b'})
    gate = PromotionGate(GateConfig(bootstrap_draws=200))
    arguments = dict(cutoff='2025-01-01T00:00:00Z',candidate_recipe='c',champion_recipe='b',attempt=1,required_cells={('recession',12)})
    decision = gate.evaluate(frame,returns,**arguments)
    assert decision['promote'],decision
    frame['challenger_trained_through'] = frame.origin+pd.Timedelta(days=1)
    assert gate.evaluate(frame,returns,**arguments)['reason']=='lookahead_in_evaluation'


def test_daily_pipeline_retains_champion_without_new_labels(tmp_path):
    from api.ml.institutional.pipeline import AutonomousDailyPipeline,DailyData
    from api.ml.institutional.ingestion import Source
    from datetime import timedelta
    class Ingestor:
        def ingest(self,*a,**kw): return [],[]
    class Registry:
        def decision(self,run): return None
        def champion(self): return 'champion'
    class Ports:
        def build_data(self,*a): return DailyData([],digest('schema'),digest('snapshot'),True,False,{})
        def fine_tune(self,*a): pytest.fail('No labels: must not fine-tune')
        def full_retrain(self,*a): pytest.fail('No drift: must not reset')
    now = datetime.now(timezone.utc)
    graph = DynamicEventGraph(tmp_path/'graph',('rates',))
    pipeline = AutonomousDailyPipeline(tmp_path/'daily',Ingestor(),[Source('test','https://example.com',('example.com',))],graph,Registry(),PromotionGate(),Ports(),lambda day:now-timedelta(minutes=30),digest('recipe'))
    assert pipeline.run(now)['status']=='skipped_no_new_matured_labels'
    assert pipeline.run(now)['status']=='skipped_no_new_matured_labels'


def test_autonomous_drift_reset_and_atomic_promotion_path(tmp_path):
    from api.ml.institutional.pipeline import AutonomousDailyPipeline,DailyData,Candidate
    from api.ml.institutional.ingestion import Source
    from datetime import timedelta
    registry = ModelRegistry(tmp_path/'registry.sqlite')
    recipe = digest('recipe')
    def bundle(name,graph='',source=''):
        folder=tmp_path/name;folder.mkdir()
        files={}
        for key in ('weights','preprocessor','calibrator','target_schema','configuration'):
            file=folder/(key+'.json');file.write_text(json.dumps({'fixture':name}))
            files[key]={'path':file.name,'sha256':file_digest(file)}
        return Candidate(folder,{'files':files,'pit_verified':True,'recipe_digest':recipe,'source_snapshot_digest':source,'graph_snapshot_digest':graph})
    baseline=bundle('base');old=registry.register(baseline.directory,baseline.manifest);registry.bootstrap(old)
    calls=[]
    class Ingestor:
        def ingest(self,*a,**kw):return [],[]
    class Ports:
        def build_data(self,cutoff,graph):
            self.graph=graph
            return DailyData([experience(1)],'schema',digest('snapshot'),True,True,{'trigger':True})
        def fine_tune(self,*a):pytest.fail('Drift must route to a fresh reset')
        def full_retrain(self,*a):calls.append('reset');return bundle('reset',self.graph,digest('snapshot'))
        def evaluate(self,*a,**kw):return pd.DataFrame(),pd.DataFrame()
        def champion_recipe(self,*a):return recipe
        def required_cells(self):return {('recession',12)}
    class PassedGate:
        def evaluate(self,*a,**kw):return {'promote':True,'reason':'fixture_only'}
    now=datetime.now(timezone.utc)
    run=AutonomousDailyPipeline(tmp_path/'daily',Ingestor(),[Source('test','https://example.com',('example.com',))],DynamicEventGraph(tmp_path/'graph',('rates',)),registry,PassedGate(),Ports(),lambda day:now-timedelta(minutes=30),recipe)
    decision=run.run(now)
    assert decision['promote'] and registry.champion()!=old and calls==['reset']
    assert run.run(now)==decision and calls==['reset']


def test_registry_rechecks_weights_before_promotion(tmp_path):
    registry=ModelRegistry(tmp_path/'registry.sqlite')
    def make(name):
        folder=tmp_path/name;folder.mkdir();artifact=folder/'artifact';artifact.write_text(name)
        manifest={'pit_verified':True,'recipe_digest':digest(name),'files':{key:{'path':'artifact','sha256':file_digest(artifact)} for key in ('weights','preprocessor','calibrator','target_schema','configuration')}}
        return registry.register(folder,manifest),artifact
    old,_=make('old');new,path=make('new');registry.bootstrap(old)
    path.write_text('modified after evaluation')
    with pytest.raises(ValueError,match='changed after'):registry.decide(new,old,{'promote':True},run_id='tamper')
    assert registry.champion()==old


def test_gat_uses_dynamic_edge_weight_priors():
    gat=DenseGAT(3,8,2)
    _,weights=gat(torch.zeros(1,2,3),torch.tensor([[0],[1]]),torch.tensor([9.]))
    torch.testing.assert_close(weights[0,:,1,0],torch.full((2,),.9))
    _,self_weights=gat(torch.zeros(1,2,3),torch.tensor([[0],[0]]),torch.tensor([0.]))
    assert torch.isfinite(self_weights).all()
