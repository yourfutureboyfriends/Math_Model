"""Integration invariants for causal/debate/stress/continual paths."""
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn
from api.ml.institutional.causal import CausalMaskedGATConv,CausalDiscoveryEngine,LaggedStructure,causal_forecast
from api.ml.institutional.advanced_continual import EWCDRLoss,StratifiedRegimeReplayBuffer,continual_training_step
from api.ml.institutional.continual import Experience,EWC
from api.ml.institutional.model import ModelConfig
from api.ml.institutional.training import TrainableMacroSystem
from api.ml.institutional.reasoning import AgentDebateOrchestrator,AgentScore,parse_debate_to_features,MacroVAE
from api.ml.institutional.provenance import prov_document
from api.ml.institutional.lineage import InferenceManifest
from api.ml.institutional.data import PointInTimeFeatureStore,Observation,FeatureSpec


def batch():
    return {'specialists':torch.randn(1,6,3,4),'graph_nodes':torch.randn(1,3,20),
            'edge_index':torch.tensor([[0,1],[1,2]]),'edge_weight':torch.tensor([.3,.8]),
            'known_future':torch.zeros(1,12,4),'target':torch.zeros(1,4,6),'known':torch.ones(1,4,6,dtype=torch.bool)}


def system():
    return TrainableMacroSystem(ModelConfig(domains=3,domain_inputs=4,hidden=16,heads=4),('binary',)*6)


def test_causal_mask_forbids_reverse_and_nonexistent_messages():
    layer=CausalMaskedGATConv(4,8,2).eval();nodes=torch.randn(1,3,4)
    mask=torch.zeros(3,3,dtype=torch.bool);mask[1,0]=True;mask[2,1]=True
    out,attention=layer(nodes,mask)
    assert torch.isfinite(out).all()
    assert torch.equal(attention.masked_select(~mask),torch.zeros_like(attention.masked_select(~mask)))
    changed=nodes.clone();changed[:,2]+=100
    again,_=layer(changed,mask)
    assert torch.equal(out[:,:2],again[:,:2])


def test_temporal_feedback_is_time_expanded_and_intervention_cuts_mechanism():
    coef=np.array([[[.5,.2],[.7,.1]]]);s=LaggedStructure(('feature:a','feature:b'),((0,0,1),(1,0,1),(0,1,1),(1,1,1)),coef,np.zeros(2),'2026-01-01T00:00:00Z',1)
    import networkx as nx
    assert nx.is_directed_acyclic_graph(s.expanded_dag())
    engine=CausalDiscoveryEngine();engine.structure=s
    path=engine.perform_intervention(0,torch.tensor(2.),history=torch.zeros(1,2),steps=3)
    assert path[:,0].tolist()==[2,2,2] and path[1,1].item()==pytest.approx(1.4)
    m=system().eval();b=batch();result=causal_forecast(m,b,s,torch.zeros(1,2),node_ids=('feature:a','feature:b','feature:c'),node_id=0,intervention_value=torch.tensor(2.))
    assert result['predictions'].shape==(1,4,6) and torch.isfinite(result['predictions']).all()


def test_edge_prior_reaches_both_graph_attention_layers():
    m=system().eval();b=batch();b['edge_index']=torch.tensor([[0,1],[2,2]])
    with torch.no_grad():
        a=m.predict(b)['graph_attention'];b['edge_weight']=torch.tensor([100.,.001]);c=m.predict(b)['graph_attention']
    assert not torch.allclose(a,c)


def test_ewcdr_protects_confident_binary_logits_without_updating_weights():
    class Small(nn.Module):
        def __init__(self):super().__init__();self.weight=nn.Parameter(torch.tensor(10.))
        def predict(self,b):return {'predictions':self.weight.expand(1,1,1)}
    m=Small();e=Experience('x','2020-01-01T00:00:00Z','2021-01-01T00:00:00Z','s','expansion',{'target':torch.ones(1,1,1),'known':torch.ones(1,1,1,dtype=torch.bool)})
    dr=EWCDRLoss.estimate(m,[e]);ordinary=EWC.estimate(m,[e],lambda m,b:torch.nn.functional.binary_cross_entropy_with_logits(m.predict(b)['predictions'],b['target']))
    assert dr.fisher['weight']>ordinary.fisher['weight']*1e6
    assert m.weight.item()==10


def test_regime_replay_preserves_population_distribution(tmp_path):
    r=StratifiedRegimeReplayBuffer(tmp_path/'replay.sqlite',capacity=20)
    for i in range(100):
        r.add(Experience(str(i),'2020-01-01T00:00:00Z','2021-01-01T00:00:00Z','s','expansion' if i<90 else 'inflation',{'x':torch.tensor(i)}),cutoff='2022-01-01T00:00:00Z')
    sample=r.sample(2000,cutoff='2022-01-01T00:00:00Z',schema='s')
    assert .86<sum(e.stratum=='expansion' for e in sample)/len(sample)<.94
    assert not r.sample(10,cutoff='2019-01-01T00:00:00Z',schema='s')


def test_debate_protocol_and_static_features_reach_same_task_heads():
    seen=[]
    def invoke(role,payload):
        seen.append(payload)
        return {'probabilities':[.2]*6,'evidence_ids':['event'],'rationale':'Evidence-limited opinion'}
    d=AgentDebateOrchestrator(invoke,{},'2026-01-01T00:00:00Z')
    d.independent_drafting([{'id':'event','available_at':'2025-12-31T00:00:00Z'}]);d.iterative_critique()
    assert all('prior_round' not in p for p in seen[:3])
    features=parse_debate_to_features(json.dumps(d.weighted_consensus()))
    m=system().eval();b=batch();a=m.predict(b)['predictions'];b['debate_features']=features
    assert torch.equal(a,m.predict(b)['predictions']) # new projection is inert until trained
    m.loss(b).backward();assert m.network.debate_projection.weight.grad.abs().sum()>0


def test_world_model_stress_uses_existing_graph_and_heads():
    m=system().eval();b=batch();vae=MacroVAE(12,16,hidden=16,latent=4)
    embeddings=m.predict(b)['node_embeddings'].detach();x=b['specialists'].flatten(2)
    reconstruction,mu,lv=vae(x,embeddings)
    loss=vae.objective(reconstruction,x,mu,lv,torch.ones_like(x,dtype=torch.bool));loss.backward()
    out=vae.stress_forecast(m,b,torch.zeros(1,4))
    assert out['predictions'].shape==(1,4,6) and torch.isfinite(out['predictions']).all()


def test_prov_json_is_readable_by_standard_library():
    from prov.model import ProvDocument
    manifest=InferenceManifest(*(['a'*64]*9),'commit')
    doc=prov_document(manifest,identifier='one',started='2026-01-01T00:00:00Z',ended='2026-01-01T00:01:00Z',output_digest='b'*64,status='completed')
    parsed=ProvDocument.deserialize(content=json.dumps(doc),format='json')
    assert len(parsed.get_records())>20


def test_graph_snapshot_excludes_later_revision(tmp_path):
    store=PointInTimeFeatureStore(tmp_path/'pit.sqlite');spec={'feature:gdp':FeatureSpec('US','gdp',max_age='180D')}
    for day,value in [('2026-01-31',1.),('2026-02-10',2.)]:
        clock=day+'T12:00:00Z';store.append(Observation('US','gdp','2025-12-31T00:00:00Z',clock,clock,value,'a'*64),now=clock)
    values,sha=store.snapshot_graph('2026-02-01T00:00:00Z',spec,tmp_path/'snapshots')
    assert values['feature:gdp']==1 and (tmp_path/'snapshots'/(sha+'.json')).exists()


def test_pcmci_runs_on_existing_observed_kg_nodes():
    rng=np.random.default_rng(7);x=rng.normal(size=(150,2));x[1:,1]=.8*x[:-1,0]+rng.normal(size=149)*.1
    frame=pd.DataFrame(x,index=pd.date_range('2000-01-01',periods=150,freq='MS',tz='UTC'),columns=['feature:a','feature:b'])
    result=CausalDiscoveryEngine(maximum_lag=1).fit(frame,cutoff='2020-01-01T00:00:00Z',graph_node_ids=tuple(frame.columns))
    assert (0,1,1) in result.edges


def test_foraging_uses_model_heads_rejects_future_sources_and_trains_offline(tmp_path):
    from api.ml.institutional.foraging import ModelQueryEpisode,model_foraging_environment,train_foraging_policy,calculate_foraging_reward
    from stable_baselines3.common.env_checker import check_env
    m=system().eval();b=batch()
    episode=ModelQueryEpisode('2026-01-01T12:00:00Z','fixed',{'Fed':'2026-01-01T11:00:00Z'},b,{'Fed':b},{'Fed':'snapshot'},np.zeros((4,6)),'2026-02-01T00:00:00Z')
    env=model_foraging_environment(m,[episode],cutoff='2026-03-01T00:00:00Z',model_digest='fixed')
    check_env(env,warn=False)
    env.reset(seed=2);obs,reward,terminated,truncated,info=env.step(1)
    assert truncated and info['observed_brier_gain']==0 and np.isfinite(reward)
    report=train_foraging_policy(env,tmp_path/'policy',steps=64)
    assert (tmp_path/'policy.zip').exists() and report['steps']==64
    episode.source_available_at['Fed']='2026-01-02T00:00:00Z'
    with pytest.raises(ValueError):model_foraging_environment(m,[episode],cutoff='2026-03-01T00:00:00Z',model_digest='fixed')


def test_debate_can_abstain_without_manufacturing_macro_probabilities():
    def abstain(role,payload):return {'probabilities':[.5]*6,'evidence_ids':['event'],'rationale':'No macro forecast evidence','abstain':True}
    d=AgentDebateOrchestrator(abstain,{},'2026-01-01T00:00:00Z')
    d.independent_drafting([{'id':'event','available_at':'2025-12-31T00:00:00Z'}]);d.iterative_critique()
    with pytest.raises(ValueError,match='All agents abstained'):d.weighted_consensus()


def test_purged_cv_demands_fresh_fold_fit_and_never_calls_it_prospective():
    from types import SimpleNamespace
    from api.ml.institutional.validation import PurgedChallengerEvaluation
    starts=pd.date_range('2020-01-01',periods=60,freq='MS',tz='UTC');ends=starts+pd.Timedelta(days=10)
    def fit(indices,cutoff):return SimpleNamespace(training_indices=indices)
    def predict(model,indices):return pd.DataFrame({'target':np.arange(len(indices))%2,'champion_probability':.5,'challenger_probability':.5})
    report=PurgedChallengerEvaluation(3,'15D').run(starts,ends,ends,cutoff='2030-01-01T00:00:00Z',fit=fit,predict=predict)
    assert report['fold_local_fit'] and report['relative_brier_gain']==0 and 'not prospective' in report['scope']
    with pytest.raises(ValueError,match='training-index'):
        PurgedChallengerEvaluation(3).run(starts,ends,ends,cutoff='2030-01-01T00:00:00Z',fit=lambda i,c:SimpleNamespace(training_indices=[]),predict=predict)


def test_provider_budget_and_transient_retry_are_bounded(monkeypatch):
    import requests
    from api.ml.institutional.application import ExistingProviderExtractor
    extractor=object.__new__(ExistingProviderExtractor)
    extractor.config={'provider':'groq','model':'openai/gpt-oss-120b','base_url':'https://example.com','key':'test-only'};extractor.throttled=False
    calls=[];sleeps=[]
    class Response:
        headers={'Retry-After':'16'}
        def __init__(self,status):self.status_code=status;self.ok=status==200
        def json(self):return {'choices':[{'message':{'content':'{"events":[]}'}}]}
    def post(*args,**kwargs):calls.append(kwargs['json']);return Response(429 if len(calls)==1 else 200)
    monkeypatch.setattr(requests,'post',post)
    monkeypatch.setattr('api.ml.institutional.application.time.sleep',sleeps.append)
    assert extractor.invoke_json({'type':'object'},[('system','Return JSON'),('human','Public evidence')],token_budget=1024)=={'events':[]}
    assert sleeps==[16] and len(calls)==2 and calls[0]['max_tokens']==1024 and calls[0]['reasoning_effort']=='low'


def test_causal_control_and_null_intervention_use_identical_graph_and_weights():
    coef=np.array([[[.5,.2],[.7,.1]]]);s=LaggedStructure(('feature:a','feature:b'),((0,0,1),(1,0,1),(0,1,1),(1,1,1)),coef,np.zeros(2),'2026-01-01T00:00:00Z',1)
    m=system().eval();b=batch();history=torch.ones(1,2)
    with torch.no_grad():
        control=causal_forecast(m,b,s,history,node_ids=('feature:a','feature:b','feature:c'),node_id=0)
        identical=causal_forecast(m,b,s,history,node_ids=('feature:a','feature:b','feature:c'),node_id=0,intervention_value=torch.tensor(.7))
    assert torch.allclose(control['predictions'],identical['predictions'])


def test_source_query_history_counts_sessions_not_manual_duplicates(tmp_path):
    from api.ml.institutional.source_history import query_history_status
    for i,day in enumerate(['2026-01-01','2026-01-01','2026-01-02']):
        folder=tmp_path/str(i);folder.mkdir();(folder/'episode.json').write_text(json.dumps({'complete':True,'origin':day+'T12:00:00Z','actions':{'Fed':{}}}))
    summary=query_history_status(tmp_path)
    assert summary['complete_episodes']==3 and summary['distinct_days']==2 and not summary['live_ppo_enabled']


def test_query_collector_freezes_weights_and_isolates_source_alternatives(tmp_path):
    from types import SimpleNamespace
    from api.ml.institutional.source_history import SourceQueryRecorder
    from api.ml.institutional.graph import DynamicEventGraph
    from api.ml.institutional.application_data import graph_input
    import sqlite3
    live=DynamicEventGraph(tmp_path/'live',('feature:a','feature:b','feature:c'),max_nodes=32,core_edges=(('feature:a','feature:b'),))
    m=system().eval();original=batch();identity=['before-learning']
    def tensors(fr,state,index,structure,graph,origin):
        inputs={k:v.clone() for k,v in original.items()};extra,_=graph_input(graph,origin);inputs.update(extra);return inputs
    ports=SimpleNamespace(shadow=lambda:identity[0],load=lambda _: (m,{}, {'schema':'fixed'},None,None,{'files':{'weights':{'sha256':'a'*64}}}),
        graph=live,tensors=tensors,fr={'months':['2026-01']},recipe_id='b'*64,source_sha='c'*64)
    collector=SourceQueryRecorder(ports,tmp_path/'episodes')
    now=datetime.now(timezone.utc).isoformat()
    event={'id':'new','entity':'fed','action':'rate_cut','available_at':now,'first_seen_at':now,'source_digest':'d'*64}
    collector.observe(SimpleNamespace(name='A',feed_url='https://example.com/a'),[event],[],{'feed_requests':1})
    collector.observe(SimpleNamespace(name='B',feed_url='https://example.com/b'),[],[],{'feed_requests':1})
    identity[0]='after-learning'
    record=collector.finish(['A','B'])
    assert record['model_id']=='before-learning' and record['complete']
    assert len(record['actions']['A']['trace']['embeddings'])>len(record['baseline']['embeddings'])
    assert record['actions']['B']['trace']['probabilities']==record['baseline']['probabilities']
    assert record['actions']['A']['trace']['available_at']==record['baseline']['available_at']
    assert record['actions']['A']['trace']['prediction_available_at']<=record['origin']
    with sqlite3.connect(live.database) as c:assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0]==0


def test_clock_and_decay_do_not_create_fake_new_learning_information():
    import networkx as nx
    from api.ml.institutional.application_data import learning_information_signature
    g=nx.DiGraph();g.add_node('event:a',kind='event',age=.1);g.add_node('entity:a',kind='entity');g.add_edge('entity:a','event:a',weight=.9)
    first=learning_information_signature('source','schema',g)
    g.nodes['event:a']['age']=.9;g.edges['entity:a','event:a']['weight']=.5
    assert learning_information_signature('source','schema',g)==first
    g.add_node('event:b',kind='event')
    assert learning_information_signature('source','schema',g)!=first


def test_frozen_source_replay_masks_unmatured_labels_and_rejects_corruption(tmp_path):
    from api.ml.institutional.source_replay import load_source_replay,source_replay_readiness,frozen_foraging_environment,ensure_research_policy
    from api.ml.institutional.lineage import file_digest
    now='2026-01-01T12:00:00Z';known='2026-03-01T00:00:00Z'
    folder=tmp_path/'one';folder.mkdir();(folder/'baseline.pt').write_bytes(b'baseline');(folder/'source.pt').write_bytes(b'source')
    trace={'probabilities':np.full((4,6),.5).tolist(),'embeddings':np.zeros((3,16)).tolist(),'available_at':now,'prediction_available_at':now,'graph_snapshot':'a'*64}
    action={'trace':trace,'available_at':now,'eligible':True,'source_failures':[],'tensors':'source.pt','tensors_sha256':file_digest(folder/'source.pt'),'feed_requests':1}
    record={'complete':True,'feature_schema':'schema','started_at':now,'evaluation_cutoff':now,'origin':now,'baseline':trace,'baseline_tensors':'baseline.pt','baseline_sha256':file_digest(folder/'baseline.pt'),
            'actions':{'Fed':action},'expected_sources':['Fed'],'month':'2026-01','weights_sha256':'a'*64,'source_snapshot':'b'*64}
    (folder/'episode.json').write_text(json.dumps(record))
    labels={task: (known,1.) for task in ['2026-01:yields_up_3m:3','2026-01:inflation_up_3m:3','2026-01:oil_up_3m:3']}
    early,_=load_source_replay(tmp_path,cutoff='2026-02-01T00:00:00Z',feature_schema='schema',labels=labels)
    assert len(early)==1 and not early[0].known.any()
    later,counts=load_source_replay(tmp_path,cutoff='2026-04-01T00:00:00Z',feature_schema='schema',labels=labels)
    assert later[0].known.sum()==3 and not counts['invalid_episodes']
    assert source_replay_readiness(later)['labelled_monthly_origins']==1
    assert ensure_research_policy(later,tmp_path/'policies',cutoff='2026-04-01T00:00:00Z')['status']=='collecting_outcomes'
    env=frozen_foraging_environment(later);env.reset(seed=2);_,_,_,ended,info=env.step(1)
    assert ended and info['observed_brier_gain']==0
    (folder/'source.pt').write_bytes(b'corrupted')
    bad,counts=load_source_replay(tmp_path,cutoff='2026-04-01T00:00:00Z',feature_schema='schema',labels=labels)
    assert not bad and counts['invalid_episodes']==1


def test_policy_graph_features_ignore_node_order_and_padding():
    from api.ml.institutional.foraging import ForagingGraphFeatures,InformationForagingEnv,QueryResult
    env=InformationForagingEnv(lambda seed:QueryResult(np.full((4,6),.5),np.ones((3,16)),0.,'base'),{'Fed':lambda:None},offline=True,embedding_width=16)
    extractor=ForagingGraphFeatures(env.observation_space).eval()
    observation,_=env.reset(seed=1);a={k:torch.tensor(v).unsqueeze(0) for k,v in observation.items()}
    order=torch.randperm(256);b={**a,'nodes':a['nodes'][:,order],'node_mask':a['node_mask'][:,order]}
    with torch.no_grad():assert torch.allclose(extractor(a),extractor(b),atol=1e-6)


def test_ready_source_policy_is_published_once_as_research_only(tmp_path,monkeypatch):
    from api.ml.institutional.source_replay import FrozenSourceEpisode,ensure_research_policy
    trace={'probabilities':np.full((4,6),.5).tolist(),'embeddings':np.zeros((3,16)).tolist(),'graph_snapshot':'a'*64}
    records=[];known=np.zeros((4,6),bool);known[1,2:5]=True
    for i,month in enumerate(pd.date_range('2018-01-01',periods=24,freq='MS').strftime('%Y-%m')):
        records.append(FrozenSourceEpisode(str(i),month+'-01T12:00:00Z',month,'schema','a'*64,trace,{'Fed':{'trace':trace,'feed_requests':1}},np.zeros((4,6)),known))
    calls=[]
    def train(env,path,**kwargs):calls.append(path);path.with_suffix('.zip').write_bytes(b'research-test-policy');return {}
    monkeypatch.setattr('api.ml.institutional.foraging.train_foraging_policy',train)
    first=ensure_research_policy(records,tmp_path,cutoff='2026-01-01T00:00:00Z')
    second=ensure_research_policy(records,tmp_path,cutoff='2026-01-02T00:00:00Z')
    assert first['status']=='research_policy_trained' and not first['live_ppo_enabled'] and first==second and len(calls)==1
