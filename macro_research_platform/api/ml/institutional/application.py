"""Concrete autonomous adapter for the terminal. Runs only in an isolated worker.

Current provider histories seed a research model; only persisted prospective
forecasts and first-observed outcomes count as operational promotion evidence.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone,date
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import numpy as np
import pandas as pd
import torch
from torch import nn
from api.ml.institutional import application_data as D
from api.ml.institutional.continual import Experience,ReplayBuffer,EWC,daily_fine_tune,FineTuneConfig
from api.ml.institutional.advanced_continual import EWCDRLoss,StratifiedRegimeReplayBuffer,continual_training_step
from api.ml.institutional.data import utc,Observation,PointInTimeFeatureStore,FeatureSpec
from api.ml.institutional.graph import DynamicEventGraph
from api.ml.institutional.ingestion import FinancialIngestionAgent,EventBatch,Source
from api.ml.institutional.lineage import digest,file_digest,InferenceManifest,InferenceAudit,write_once
from api.ml.institutional.model import ModelConfig
from api.ml.institutional.pipeline import AutonomousDailyPipeline,DailyData,Candidate,run_champion_challenger_pipeline
from api.ml.institutional.registry import ModelRegistry,PromotionGate,GateConfig
from api.ml.institutional.training import TrainableMacroSystem
from api.ml.live import _read,_write

ROOT=Path(__file__).resolve().parents[2]/'..'/'data'/'processed'/'ml_autonomous'
ROOT=ROOT.resolve()


def source_manifest():
    files=['application.py','application_data.py','model.py','training.py','continual.py','registry.py','ingestion.py','graph.py','pipeline.py','causal.py','advanced_continual.py','reasoning.py','foraging.py','provenance.py','advanced_runtime.py','lineage.py','data.py','validation.py','losses.py','monitor.py','source_history.py','source_replay.py']
    base=Path(__file__).parent
    paths={f:base/f for f in files}
    for f in ('deep.py','features.py','panel.py','context.py','modular.py','tasks.py','engine.py'):
        paths['ml/'+f]=base.parent/f
    return paths


def recipe():
    return digest({'code':{name:file_digest(path) for name,path in source_manifest().items()},
                   'targets':D.target_schema(),'config':asdict(ModelConfig()),'extraction_provider_hint':os.getenv('AI_PROVIDER') or ('groq' if os.getenv('GROQ_API_KEY') else 'auto'),'extraction_model_hint':os.getenv('AI_MODEL','configured-default'),'seed_epochs':os.getenv('ML_AUTONOMOUS_SEED_EPOCHS','6'),'seed_seconds':os.getenv('ML_AUTONOMOUS_SEED_SECONDS','120'),'debate_enabled':os.getenv('ML_DEBATE_ENABLED','1'),'scope':'six native tasks; other horizons research only'})


def market_close(day:date):
    import exchange_calendars as xcals
    cal=xcals.get_calendar('XNYS')
    stamp=pd.Timestamp(day)
    return cal.session_close(stamp).to_pydatetime() if cal.is_session(stamp) else None


class ExistingProviderExtractor:
    """Use the terminal's configured AI provider; credentials never enter artifacts."""
    def __init__(self):
        from api.ai.assistant import config
        self.config=config();self.throttled=False
        if not self.config.get('available'):raise RuntimeError('The terminal AI provider is not available')
        self.version=self.config['provider']+':'+str(self.config['model'])+':macro-events-v1'

    def invoke(self,messages):
        import requests
        if self.throttled:raise RuntimeError('AI provider rate-limited; retry next scheduled run')
        return EventBatch.model_validate(self.invoke_json(EventBatch.model_json_schema(),messages))

    def invoke_json(self,schema:dict,messages:list,*,token_budget:int=2048) -> dict:
        import requests
        if self.throttled:raise RuntimeError('AI provider rate-limited; retry next cycle')
        if not 512<=token_budget<=2048:raise ValueError('Structured extraction token budget outside bounds')
        mapped=[{'role':role,'content':content[:16000] if role=='human' else content} for role,content in messages]
        for message in mapped:
            if message['role']=='human':message['role']='user'
        mapped[0]['content']+='\nReturn only valid JSON matching this schema:\n'+json.dumps(schema)
        body={'model':self.config['model'],'messages':mapped,'temperature':0,'max_tokens':token_budget,'stream':False,
              'response_format':{'type':'json_object'}}
        if self.config['provider']=='groq' and str(self.config['model']).startswith('openai/gpt-oss'):
            body['reasoning_effort']='low'
        for attempt in range(3):
            r=requests.post(self.config['base_url']+'/chat/completions',json=body,
                           headers={'Authorization':'Bearer '+self.config['key']},timeout=(5,75))
            if r.status_code!=429:break
            try:delay=float(r.headers.get('Retry-After','5'))
            except ValueError:delay=5.
            if attempt==2 or not 0<=delay<=30:break
            time.sleep(max(1.,delay))
        if r.status_code==429:self.throttled=True
        if not r.ok:raise RuntimeError('Configured AI provider returned HTTP '+str(r.status_code))
        return json.loads(r.json()['choices'][0]['message']['content'])


class AppPorts:
    def __init__(self,root:Path,graph:DynamicEventGraph,registry:ModelRegistry,recipe_id:str):
        self.root,self.graph,self.registry,self.recipe_id=root,graph,registry,recipe_id
        self.replay=StratifiedRegimeReplayBuffer(root/'replay.sqlite',capacity=2048)
        self.db=root/'prospective.sqlite';self.db.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.db) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, origin TEXT, month TEXT, recipe TEXT,
                baseline_recipe TEXT, baseline TEXT, probabilities TEXT, ready TEXT, payload TEXT)''')
            c.execute('CREATE TABLE IF NOT EXISTS labels(id TEXT PRIMARY KEY, known TEXT, payload TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS trained(id TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE IF NOT EXISTS portfolio_returns(id TEXT PRIMARY KEY, payload TEXT)')
        self.fr=None;self.data=None;self.pending=[];self.observed_at=None

    def status(self,**updates):
        old=_read(self.root/'state.json') or {}
        _write(self.root/'state.json',{**old,**updates,'updated_at':datetime.now(timezone.utc).isoformat()})

    def _bundle_record(self,identifier):
        with sqlite3.connect(self.registry.path) as c:
            row=c.execute('SELECT manifest FROM artifacts WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Model artifact not registered')
        record=json.loads(row[0]);base=Path(record['directory'])
        for entry in record['manifest']['files'].values():
            path=(base/entry['path']).resolve()
            if not path.is_relative_to(base.resolve()) or file_digest(path)!=entry['sha256']:raise ValueError('Model bundle integrity mismatch')
        return base,record['manifest']

    def load(self,identifier):
        base,manifest=self._bundle_record(identifier)
        cfg=ModelConfig(**json.loads((base/'configuration.json').read_text()))
        model=TrainableMacroSystem(cfg,('binary',)*6)
        model.load_state_dict(torch.load(base/'weights.pt',map_location='cpu',weights_only=True));model.eval()
        payload=torch.load(base/'preprocessor.pt',map_location='cpu',weights_only=True)
        state={k:v.numpy() for k,v in payload.items()}
        structure=json.loads((base/'features.json').read_text())
        calibrator=json.loads((base/'calibrator.json').read_text())
        return model,state,structure,calibrator,base,manifest

    def shadow(self):
        saved=_read(self.root/'shadow.json') or {}
        return saved.get('id')

    def core_graph(self,fr):
        from api.ml.modular import feature_groups
        from api.ml.deep import N_FACTORS
        groups=feature_groups(fr['core_keys'],N_FACTORS,fr['text_keys'])
        keys=fr['core_keys']+['factor_'+str(i) for i in range(N_FACTORS)]+fr['text_keys']
        nodes=['source:observations']+['feature:'+k for k in keys]+['domain:'+g for g in groups]
        edges=[('source:observations','feature:'+k) for k in keys]
        for group,indices in groups.items():
            edges += [('feature:'+keys[i],'domain:'+group) for i in indices if i<len(keys)]
        return tuple(nodes),tuple(edges)

    def tensors(self,fr,state,index,structure,graph,origin):
        from api.ml.deep import transform_features,N_FACTORS
        graph=copy.deepcopy(graph)
        x=transform_features(fr,state)[index]
        keys=fr['core_keys']+['factor_'+str(i) for i in range(N_FACTORS)]+fr['text_keys']
        for i,key in enumerate(keys):
            node='feature:'+key
            if node in graph and (i<len(fr['core_keys'])+N_FACTORS or np.isfinite(fr['T'][index,i-len(fr['core_keys'])-N_FACTORS])):
                graph.nodes[node]['value_z']=float(np.clip(x[i],-10,10))
        packed=D.pack(fr,state,index,structure['groups']);extra,_=D.graph_input(graph,origin);packed.update(extra)
        return packed

    def examples(self,fr,state,structure,indices,cutoff):
        import networkx as nx
        nodes,edges=self.core_graph(fr);graph=nx.DiGraph()
        graph.add_nodes_from((n,{'kind':'core','core':True}) for n in nodes)
        graph.add_edges_from((a,b,{'weight':1.}) for a,b in edges)
        result=[]
        schema=digest(structure)
        for i in indices:
            y=fr['Y24'][i];known=D.maturity(fr['months'][i],cutoff)&np.isfinite(y)
            if not known.any():continue
            t=self.tensors(fr,state,i,structure,graph,cutoff)
            t.update(target=torch.tensor(np.nan_to_num(y)[None]),known=torch.tensor(known[None]))
            origin=fr['months'][i]+'-01T00:00:00Z'
            result.append(Experience('foundation:'+schema+':'+fr['months'][i],origin,cutoff,schema,D.origin_regime(fr,i),t))
        return result

    def prepare(self,cutoff):
        self.status(phase='collecting_inputs',message='Freezing current source observations and target availability.')
        self.fr,self.raw_path,self.source_sha=D.fetch_frame(self.root)
        self.observed_at=datetime.now(timezone.utc).isoformat()
        cutoff=self.observed_at
        if len(self.fr['months'])<180:raise ValueError('Insufficient foundation history')
        store=PointInTimeFeatureStore(self.root/'pit_features.sqlite')
        period=pd.Timestamp(self.fr['months'][-1]+'-01',tz='UTC').isoformat()
        collections=[(self.fr['core_keys'],self.fr['C'][-1]),(self.fr['panel_keys'],self.fr['P'][-1]),(self.fr['text_keys'],self.fr['T'][-1])]
        for keys,values in collections:
            for key,value in zip(keys,values):
                if np.isfinite(value):
                    store.append(Observation('US:engineered_monthly',key,period,cutoff,cutoff,float(value),self.source_sha),now=cutoff)
        specs={'feature:'+key:FeatureSpec('US:engineered_monthly',key) for key in self.fr['core_keys']+self.fr['text_keys']}
        _,pit_graph=store.snapshot_graph(cutoff,specs,self.root/'pit_snapshots')
        self.status(pit_graph_snapshot=pit_graph,source_snapshot=self.source_sha,input_month=self.fr['months'][-1],pit_observations_started=True,
                    foundation_history='Currently revised research history; never used as retrospective operational PIT evidence.')

    def build_data(self,cutoff,graph_digest):
        if self.fr is None:self.prepare(cutoff)
        cutoff=max(utc(cutoff),utc(self.observed_at)).isoformat()
        self.current_graph_digest=graph_digest
        self.current_graph=D.load_graph(self.graph.root/'snapshots'/(graph_digest+'.json'))
        shadow=self.shadow()
        if not shadow:raise ValueError('Initial shadow foundation must be built first')
        model,state,structure,cal,base,manifest=self.load(shadow)
        self.schema=digest(structure)
        self.live_tensors=self.tensors(self.fr,state,len(self.fr['months'])-1,structure,self.current_graph,cutoff)
        signature=D.learning_information_signature(self.source_sha,self.schema,self.current_graph)
        previous=_read(self.root/'last_learning.json') or {}
        self.input_signature=signature
        self.pending=self.newly_matured(state,structure,cutoff)
        data=DailyData(self.pending,self.schema,self.source_sha,True,False,{},has_new_information=signature!=previous.get('signature'),available_at=cutoff)
        # Drift uses actual daily frozen observations, not repeated monthly rows.
        latest=self.live_tensors['specialists'][0,-1].flatten().numpy()
        drift_path=self.root/'drift_observations.json';history=_read(drift_path) or []
        day=pd.Timestamp(cutoff).date().isoformat();history=[r for r in history if r['day']!=day and r['schema']==self.schema]
        history=(history+[{'day':day,'schema':self.schema,'values':latest.tolist()}])[-256:];_write(drift_path,history)
        if len(history)>=128:
            from api.ml.institutional.monitor import DistributionMonitor
            matrix=np.array([r['values'] for r in history]);monitor=DistributionMonitor(matrix[:64],min_rows=64,patience=3)
            path=self.root/'drift_state.json';old=_read(path)
            if old and old.get('reference')==monitor.reference_digest:monitor.load_state_dict(old['state'])
            measured=monitor.update(matrix[-64:],window_id=day)
            _write(path,{'reference':monitor.reference_digest,'state':monitor.state_dict()})
            data.drift_triggered=measured.trigger;data.drift_evidence=vars(measured)
        else:data.drift_evidence={'ready':False,'observed_days':len(history),'required_days':128}
        self.data=data
        self.status(phase='checking_learning',new_matured_origins=len(self.pending),has_new_information=data.has_new_information,
                    drift=data.drift_evidence,model_id=shadow,graph_digest=graph_digest)
        return data

    def newly_matured(self,state,structure,cutoff):
        months={m:i for i,m in enumerate(self.fr['months'])};result=[]
        with sqlite3.connect(self.db) as c:
            rows=c.execute('SELECT id,origin,month,payload FROM forecasts ORDER BY origin').fetchall()
            trained={r[0] for r in c.execute('SELECT id FROM trained')}
            selected=set()
            for fid,origin,month,encoded in rows:
                if month in selected or month not in months:continue
                selected.add(month);y=self.fr['Y24'][months[month]];known=D.maturity(month,cutoff)&np.isfinite(y)
                if not known.any():continue
                ids=[]
                for h in range(4):
                    for j in range(6):
                        if not known[h,j]:continue
                        lid=month+':'+D.TASK_NAMES[j]+':'+str(D.HORIZONS[h]);value=float(y[h,j])
                        c.execute('INSERT OR IGNORE INTO labels VALUES(?,?,?)',(lid,cutoff,json.dumps({'value':value,'source':self.source_sha})))
                        saved=c.execute('SELECT known,payload FROM labels WHERE id=?',(lid,)).fetchone()
                        y[h,j]=json.loads(saved[1])['value'];ids.append((lid,saved[0],y[h,j]))
                identity=digest({'forecast':fid,'schema':digest(structure),'labels':ids})
                if identity in trained:continue
                payload=json.loads(encoded);old=D.read_frame(payload['raw_path']);graph=D.load_graph(payload['graph_path'])
                if old['core_keys']!=self.fr['core_keys'] or old['text_keys']!=self.fr['text_keys'] or old['panel_keys']!=self.fr['panel_keys']:continue
                t=self.tensors(old,state,len(old['months'])-1,structure,graph,origin)
                t.update(target=torch.tensor(np.nan_to_num(y)[None]),known=torch.tensor(known[None]))
                stratum=D.origin_regime(old,len(old['months'])-1)
                if payload.get('debate_features') is not None:t['debate_features']=torch.tensor(payload['debate_features'],dtype=torch.float32)
                result.append(Experience(identity,origin,max(s[1] for s in ids),digest(structure),stratum,t))
        return result

    def save(self,model,state,structure,calibrator,graph_digest,cutoff,mode,ewc=None,report=None):
        from uuid import uuid4
        folder=self.root/'bundles'/uuid4().hex;folder.mkdir(parents=True)
        torch.save(model.state_dict(),folder/'weights.pt')
        torch.save({k:torch.from_numpy(v) for k,v in state.items()},folder/'preprocessor.pt')
        for name,payload in [('features',structure),('calibrator',calibrator),('target_schema',D.target_schema()),('configuration',asdict(model.network.cfg))]:
            write_once(folder/(name+'.json'),payload)
        if ewc is not None:ewc.save(folder/'ewc.pt',feature_schema=digest(structure),anchor_model_digest=file_digest(folder/'weights.pt'))
        files={}
        for path in folder.iterdir():
            key={'weights.pt':'weights','preprocessor.pt':'preprocessor'}.get(path.name,path.stem)
            files[key]={'path':path.name,'sha256':file_digest(path)}
        manifest={'recipe_digest':self.recipe_id,'files':files,'pit_verified':True,
                  'pit_scope':'Operational prospective inputs and inference receipts; not a claim about historical seed vintages.',
                  'historical_backtest_eligible':False,'source_snapshot_digest':self.source_sha,'graph_snapshot_digest':graph_digest,
                  'trained_through':cutoff,'training_mode':mode,'feature_schema':digest(structure),
                  'training_report':report or {},'validation_status':'research challenger; requires prospective gate',
                  'lineage_code':file_digest(Path(__file__))}
        identifier=self.registry.register(folder,manifest)
        _write(self.root/'shadow.json',{'id':identifier,'trained_through':cutoff,'mode':mode})
        self.status(model_id=identifier,training_mode=mode,training_report=report,trained_through=cutoff)
        return Candidate(folder,manifest)

    def bootstrap(self,cutoff,graph_digest):
        from api.ml.deep import fit_preprocessor
        self.status(phase='training_foundation',message='Fitting a research seed on existing history; no historical PIT performance claim.')
        n=len(self.fr['months']);last_complete=n-24
        calibration_indices=list(range(max(24,last_complete-72),last_complete))
        calibration_set=set(calibration_indices)
        eligible=[i for i in range(23,n) if i not in calibration_set and (D.maturity(self.fr['months'][i],cutoff)&np.isfinite(self.fr['Y24'][i])).any()]
        if len(eligible)<96:raise ValueError('Insufficient labelled seed history')
        scale_end=min(calibration_indices) if calibration_indices else last_complete
        state=fit_preprocessor(self.fr,scale_end)
        structure,self.schema=D.feature_schema(self.fr,state)
        cfg=ModelConfig(domains=len(structure['groups']))
        torch.manual_seed(1729);model=TrainableMacroSystem(cfg,('binary',)*6)
        picked=[eligible[i] for i in np.linspace(0,len(eligible)-1,min(128,len(eligible)),dtype=int)]
        examples=self.examples(self.fr,state,structure,picked,cutoff)
        calibration=self.examples(self.fr,state,structure,calibration_indices,cutoff)
        optimizer=torch.optim.AdamW(model.parameters(),lr=.0005,weight_decay=.003)
        started=time.monotonic();losses=[]
        epochs=int(os.getenv('ML_AUTONOMOUS_SEED_EPOCHS','6'))
        if not 1<=epochs<=30:raise ValueError('Seed epochs must be within [1,30]')
        budget=int(os.getenv('ML_AUTONOMOUS_SEED_SECONDS','120'))
        if not 10<=budget<=600:raise ValueError('Seed time budget must be within [10,600]')
        rng=np.random.default_rng(1729)
        for epoch in range(epochs):
            model.train()
            for index in rng.permutation(len(examples)):
                optimizer.zero_grad(set_to_none=True)
                loss=model.loss(examples[int(index)].tensors)
                if not torch.isfinite(loss):raise FloatingPointError('Nonfinite foundation loss')
                loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);optimizer.step()
                losses.append(float(loss.detach()))
                if time.monotonic()-started>budget:break
            self.status(phase='training_foundation',epoch=epoch+1,epochs=epochs,loss=losses[-1])
            if time.monotonic()-started>budget:break
        model.eval();cal=D.calibrate(model,calibration)
        for example in examples:self.replay.add(example,cutoff=cutoff)
        ewc=EWCDRLoss.estimate(model,examples[:32])
        self.save(model,state,structure,cal,graph_digest,cutoff,'foundation_reference',ewc,
                  {'epochs':epoch+1,'updates':len(losses),'last_loss':losses[-1],'runtime_seconds':time.monotonic()-started,
                   'history_scope':'Revised-history foundation; prospective evidence starts with persisted forecasts.'})

    def _update(self,data,cutoff,mode):
        model,state,structure,cal,base,manifest=self.load(self.shadow())
        ewc=EWC.load(model,base/'ewc.pt',feature_schema=digest(structure)) if (base/'ewc.pt').exists() else None
        self.status(phase='learning',training_mode=mode,message='Updating only the research challenger.')
        if mode=='supervised_fine_tune':
            optimizer=torch.optim.AdamW(model.parameters(),lr=1e-5,weight_decay=.001)
            historical=self.replay.sample(max(3,len(data.new_labels)*3),cutoff=cutoff,schema=digest(structure),exclude={e.id for e in data.new_labels})
            rng=np.random.default_rng(1729);report={}
            for step in range(12):
                fresh=data.new_labels[int(rng.integers(len(data.new_labels)))].tensors
                replay=[historical[int(rng.integers(len(historical)))].tensors for _ in range(3)] if historical else []
                report=continual_training_step(model,optimizer,fresh,replay,ewc)
            for example in data.new_labels:self.replay.add(example,cutoff=cutoff)
            report.update(steps=12,replay_scope='Population-proportional origin-state regimes',importance='EWC-DR Bernoulli adaptation')
        else:
            # Targets are actual provider observations hidden from the input,
            # not self-generated macro event labels. Forecast heads are frozen.
            original=self.live_tensors['specialists'].clone()
            available=self.live_tensors['observed_features'].bool()
            gen=torch.Generator().manual_seed(1729+int(pd.Timestamp(cutoff).day))
            optimizer=torch.optim.AdamW(model.parameters(),lr=3e-6,weight_decay=0.)
            report={'scope':'Masked observed-feature reconstruction; no forecast targets manufactured.','steps':0}
            protected={name:p.detach().clone() for name,p in model.named_parameters() if 'task_heads' in name or 'objective.' in name}
            for _ in range(8):
                model.train();optimizer.zero_grad(set_to_none=True)
                masked=(torch.rand(original.shape,generator=gen)<.2)&available
                if not masked.any():continue
                batch=dict(self.live_tensors);batch['specialists']=original.masked_fill(masked,0.)
                batch['graph_nodes']=batch['graph_nodes'].clone()
                batch['graph_nodes'][:,:,17]=0.;batch['graph_nodes'][:,:,18]=1.
                out=model.predict(batch)
                loss=(out['reconstruction'][masked]-original[masked]).square().mean()+.01*out['load_balance']
                if ewc is not None:loss=loss+10*ewc.penalty(model)
                if not torch.isfinite(loss):raise FloatingPointError('Nonfinite reconstruction loss')
                loss.backward()
                for name,p in model.named_parameters():
                    if name in protected:p.grad=None
                torch.nn.utils.clip_grad_norm_(model.parameters(),.5,error_if_nonfinite=True);optimizer.step()
                report.update(steps=report['steps']+1,last_loss=float(loss.detach()))
            for name,p in model.named_parameters():
                if name in protected and not torch.equal(p.detach(),protected[name]):raise RuntimeError('Forecast head changed during reconstruction-only update')
            model.eval()
        # Refit calibration to this exact checkpoint, never reuse an old mapping.
        n=len(self.fr['months']);calibration=self.examples(self.fr,state,structure,range(max(24,n-96),max(24,n-24)),cutoff)
        cal=D.calibrate(model,calibration)
        candidate=self.save(model,state,structure,cal,self.current_graph_digest,cutoff,mode,ewc,report)
        with sqlite3.connect(self.db) as c:
            for item in data.new_labels:c.execute('INSERT OR IGNORE INTO trained VALUES(?)',(item.id,))
        _write(self.root/'last_learning.json',{'signature':self.input_signature,'at':cutoff})
        return candidate

    def fine_tune(self,champion,data,cutoff,run_id):return self._update(data,cutoff,'supervised_fine_tune')
    def self_supervise(self,champion,data,cutoff,run_id):return self._update(data,cutoff,'observed_feature_reconstruction')
    def full_retrain(self,champion,data,cutoff,run_id):
        self.bootstrap(cutoff,self.current_graph_digest)
        base,manifest=self._bundle_record(self.shadow())
        return Candidate(base,manifest)

    def champion_recipe(self,champion):return self._bundle_record(champion)[1]['recipe_digest']
    def required_cells(self):return set(zip(D.TASK_NAMES,D.NATIVE_HORIZONS))

    def evaluate(self,champion,candidate,cutoff,diagnostic_days):
        # No fabricated replay/backtest rows from revised seed histories.
        rows=[]
        champion_recipe=self.champion_recipe(champion)
        with sqlite3.connect(self.db) as c:
            forecasts=c.execute('SELECT origin,month,recipe,baseline_recipe,baseline,probabilities,ready,payload FROM forecasts ORDER BY origin').fetchall()
            labels={r[0]:(r[1],json.loads(r[2])) for r in c.execute('SELECT id,known,payload FROM labels')}
        for origin,month,recipe_id,b_recipe,b_json,p_json,r_json,payload in forecasts:
            if recipe_id!=self.recipe_id or b_recipe!=champion_recipe:continue
            base=json.loads(b_json);probs=json.loads(p_json);ready=json.loads(r_json);meta=json.loads(payload)
            for j,task in enumerate(D.TASK_NAMES):
                h=D.NATIVE_HORIZONS[j];hi=D.HORIZONS.index(h);lid=month+':'+task+':'+str(h)
                if lid not in labels or task not in base or not ready[hi][j]:continue
                known,label=labels[lid]
                rows.append({'origin':origin,'task':task,'horizon':h,'label_id':lid,'target':label['value'],'label_known_at':known,
                    'champion_probability':base[task]['probability'],'challenger_probability':probs[hi][j],
                    'champion_trained_through':base[task]['trained_through'],'challenger_trained_through':meta['trained_through'],
                    'feature_asof':meta['feature_asof'],'evaluation_mode':'prospective','prediction_available_at':origin,
                    'candidate_recipe':recipe_id,'champion_recipe':b_recipe,'target_schema':digest(D.target_schema()),'reference_prior':base[task].get('reference_prior')})
        f=pd.DataFrame(rows)
        returns=self.portfolio_returns(forecasts,cutoff,champion_recipe)
        self.status(evaluation={'matured_paired_rows':len(rows),'prospective_forecasts':len(forecasts),
                    'historical_backtest_rows':0,'last_30_days_diagnostic_only':True,
                    'note':'Promotion evidence contains only recorded prospective predictions. Older revised seed data are not retroactive forecasts.'})
        return f,returns

    def portfolio_returns(self,forecasts,cutoff,champion_recipe):
        from api.ml.features import _yahoo_daily
        try:close=_yahoo_daily('SPY').dropna()
        except Exception:return pd.DataFrame()
        schedule=[]
        for origin,month,recipe_id,b_recipe,b_json,p_json,r_json,payload in forecasts:
            base=json.loads(b_json);ready=json.loads(r_json)
            if recipe_id!=self.recipe_id or b_recipe!=champion_recipe or 'spx_drawdown_6m' not in base or not ready[2][1]:continue
            schedule.append((utc(origin),1-2*base['spx_drawdown_6m']['probability'],1-2*json.loads(p_json)[2][1],json.loads(payload).get('risk_free',0.)))
        rows=[];prior=(0.,0.)
        for i in range(1,len(close)):
            previous_day=close.index[i-1].date();day=close.index[i].date()
            try:entry_close=market_close(previous_day);end_close=market_close(day)
            except Exception:continue
            if entry_close is None or end_close is None or utc(end_close)>utc(cutoff):continue
            eligible=[r for r in schedule if r[0]<=utc(entry_close)]
            if not eligible:continue
            signal=max(eligible,key=lambda r:r[0]);a,b=signal[1:3]
            excess=float(close.iloc[i]/close.iloc[i-1]-1)-signal[3]/252
            rows.append({'date':utc(end_close).normalize(),'champion_net_excess_return':a*excess-.0005*abs(a-prior[0]),
                         'challenger_net_excess_return':b*excess-.0005*abs(b-prior[1]),'cost_model_digest':digest('5bps-turnover-v1'),
                         'execution_policy_digest':digest('long-short-1-minus-2-drawdown-enter-next-eligible-close-v1'),
                         'candidate_recipe':self.recipe_id,'champion_recipe':champion_recipe})
            prior=(a,b)
        frozen=[]
        with sqlite3.connect(self.db) as c:
            for row in rows:
                serialized={**row,'date':row['date'].isoformat(),'first_observed_at':cutoff}
                identity=digest({'date':serialized['date'],'candidate_recipe':self.recipe_id,'champion_recipe':champion_recipe,
                                 'policy':row['execution_policy_digest'],'cost':row['cost_model_digest']})
                c.execute('INSERT OR IGNORE INTO portfolio_returns VALUES(?,?)',(identity,json.dumps(serialized,allow_nan=False)))
                saved=c.execute('SELECT payload FROM portfolio_returns WHERE id=?',(identity,)).fetchone()
                frozen.append(json.loads(saved[0]))
        return pd.DataFrame(frozen)

    def record_forecast(self,cutoff,graph_digest,baseline,healthy=True):
        from api.ml.institutional.lineage import file_digest
        model,state,structure,cal,base,manifest=self.load(self.shadow())
        graph=D.load_graph(self.graph.root/'snapshots'/(graph_digest+'.json'))
        batch=self.tensors(self.fr,state,len(self.fr['months'])-1,structure,graph,cutoff)
        from api.ml.institutional.advanced_runtime import debate_features,run_research_probes
        debate=None
        try:
            debate,debate_status=debate_features(self,cutoff)
            if debate is not None:batch['debate_features']=debate
            self.status(debate=debate_status)
        except Exception as exc:self.status(debate={'status':'unavailable','error_type':type(exc).__name__})
        input_sha=hashlib.sha256(b''.join(v.numpy().tobytes() for k,v in sorted(batch.items()))).hexdigest()
        weights_sha=manifest['files']['weights']['sha256']
        origin=datetime.now(timezone.utc).isoformat()
        identity=digest({'origin':origin,'weights':weights_sha,'input':input_sha})
        lineage=InferenceManifest(self.source_sha,file_digest(Path(D.__file__)),manifest['files']['preprocessor']['sha256'],graph_digest,
            weights_sha,digest(D.target_schema()),manifest['files']['calibrator']['sha256'],self.recipe_id,digest(asdict(model.network.cfg)),self.recipe_id)
        with InferenceAudit(self.root/'inference_audit',lineage,input_sha,origin) as audit:
            with torch.no_grad():out=model.predict(batch);logits=out['predictions'][0].numpy()
            probs,ready=D.probabilities(logits,cal)
            if not healthy:ready[:]=False
            audit.result({'probabilities':probs.tolist(),'calibration_ready':ready.tolist(),'scope':'prospective research'})
        if healthy:
            probes=run_research_probes(self,model,batch,state,structure,graph,cutoff)
            self.status(research_probes=probes)
        active=self.registry.champion()
        serving=None
        if active:
            active_base,active_manifest=self._bundle_record(active)
            if active_manifest.get('kind')!='legacy_reference':
                if active==self.shadow():
                    active_probs,active_ready=probs,ready
                else:
                    incumbent,inc_state,inc_structure,inc_cal,active_base,active_manifest=self.load(active)
                    if inc_structure['core_keys']!=self.fr['core_keys'] or inc_structure['text_keys']!=self.fr['text_keys'] or inc_structure['panel_keys']!=self.fr['panel_keys']:
                        raise ValueError('Promoted-model input schema changed; retain incumbent fallback')
                    inc_batch=self.tensors(self.fr,inc_state,len(self.fr['months'])-1,inc_structure,graph,origin)
                    inc_input_sha=hashlib.sha256(b''.join(v.numpy().tobytes() for k,v in sorted(inc_batch.items()))).hexdigest()
                    inc_lineage=InferenceManifest(self.source_sha,file_digest(Path(D.__file__)),active_manifest['files']['preprocessor']['sha256'],graph_digest,
                        active_manifest['files']['weights']['sha256'],digest(D.target_schema()),active_manifest['files']['calibrator']['sha256'],self.recipe_id,digest(asdict(incumbent.network.cfg)),self.recipe_id)
                    with InferenceAudit(self.root/'inference_audit',inc_lineage,inc_input_sha,origin) as audit:
                        with torch.no_grad():inc_logits=incumbent.predict(inc_batch)['predictions'][0].numpy()
                        active_probs,active_ready=D.probabilities(inc_logits,inc_cal)
                        audit.result({'probabilities':active_probs.tolist(),'calibration_ready':active_ready.tolist(),'scope':'active promoted model'})
                baseline={'recipe':active_manifest['recipe_digest'],'tasks':{task:{'probability':float(active_probs[D.HORIZONS.index(D.NATIVE_HORIZONS[j]),j]),
                          'trained_through':active_manifest['trained_through'],'model_id':active} for j,task in enumerate(D.TASK_NAMES)
                          if active_ready[D.HORIZONS.index(D.NATIVE_HORIZONS[j]),j]}}
                serving={'origin':origin,'model_id':active,'weights_sha256':active_manifest['files']['weights']['sha256'],
                         'probabilities':active_probs.tolist(),'calibration_ready':active_ready.tolist(),'target_month':self.fr['months'][-1],
                         'registry_path':str(self.registry.path),'artifact_directory':str(active_base),'scope':'gate-promoted autonomous model'}
        origin=datetime.now(timezone.utc).isoformat()
        identity=digest({'origin':origin,'weights':weights_sha,'input':input_sha})
        baseline_recipe=baseline.get('recipe',digest('legacy-serving-reference'))
        legacy=baseline.get('tasks',{})
        graph_path=str(self.graph.root/'snapshots'/(graph_digest+'.json'))
        ff=self.fr['core_keys'].index('ff') if 'ff' in self.fr['core_keys'] else None
        observed=np.stack([D.maturity(month,origin) for month in self.fr['months']])&np.isfinite(self.fr['Y24'])
        for j,task in enumerate(D.TASK_NAMES):
            hi=D.HORIZONS.index(D.NATIVE_HORIZONS[j]);valid=observed[:,hi,j]
            if task in legacy and valid.any():
                legacy[task]['reference_prior']=float(self.fr['Y24'][valid,hi,j].mean())
        payload={'debate_features':debate.tolist() if debate is not None else None,'raw_path':str(self.raw_path),'graph_path':graph_path,'source_snapshot':self.source_sha,'graph_snapshot':graph_digest,
                 'trained_through':manifest['trained_through'],'feature_asof':self.observed_at,'weights_sha256':weights_sha,
                 'model_id':self.shadow(),'risk_free':float(self.fr['C'][-1,ff]/100) if ff is not None else 0.}
        with sqlite3.connect(self.db) as c:
            c.execute('INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?,?,?,?)',(identity,origin,self.fr['months'][-1],self.recipe_id,
                baseline_recipe,json.dumps(legacy,allow_nan=False),json.dumps(probs.tolist()),json.dumps(ready.tolist()),json.dumps(payload)))
        report={'origin':origin,'model_id':self.shadow(),'weights_sha256':weights_sha,'recipe':self.recipe_id,'source_snapshot':self.source_sha,
                'tasks':list(D.TASK_NAMES),'horizons':list(D.HORIZONS),'probabilities':probs.tolist(),'calibration_ready':ready.tolist(),
                'routing':out['routing'][0,-1].tolist(),'variable_selection':out['variable_selection'][0,-1].tolist(),
                'domain_names':structure['domain_names'],'graph_nodes':int(batch['graph_nodes'].shape[1]),'graph_digest':graph_digest,
                'trained_through':manifest['trained_through'],'target_month':self.fr['months'][-1],'scope':'research challenger; not a production forecast'}
        _write(self.root/'forecast.json',report)
        # Promotion pointer is authoritative. Publish serving data only for a
        # gate-promoted TFT artifact with fresh predictions and calibrated cells.
        if healthy and serving is not None:
            with sqlite3.connect(self.registry.path) as c:
                for (saved_decision,) in c.execute('SELECT payload FROM decisions ORDER BY rowid DESC LIMIT 100'):
                    proof=json.loads(saved_decision)
                    if proof.get('candidate')==active and proof.get('promote'):
                        serving['skill_vs_reference_prior']=proof.get('skill_vs_reference_prior',{});break
            _write(ROOT/'serving.json',serving)
        self.status(phase='complete',message='Daily observations and research forecast recorded.',forecast=report)
        return report


def baseline_artifact(ports,baseline):
    current=ports.registry.champion()
    if current:return current
    folder=ports.root/'baseline_reference';folder.mkdir(parents=True,exist_ok=True)
    payload={'kind':'existing_application_serving_policy','snapshot':baseline,
             'limitations':'Reference to the incumbent application, not a newly validated TFT. Only actual observed incumbent forecasts enter comparisons.'}
    files={}
    for kind in ('weights','preprocessor','calibrator','configuration','target_schema'):
        path=folder/(kind+'.json')
        if not path.exists():write_once(path,D.target_schema() if kind=='target_schema' else payload)
        files[kind]={'path':path.name,'sha256':file_digest(path)}
    manifest={'kind':'legacy_reference','files':files,'pit_verified':True,'recipe_digest':baseline.get('recipe',digest('legacy-serving-reference')),
              'pit_scope':'Actual incumbent prospective forecast capture; no claim of historical PIT validation.'}
    identity=ports.registry.register(folder,manifest);ports.registry.bootstrap(identity)
    return identity


def build_application(root=ROOT):
    root.mkdir(parents=True,exist_ok=True)
    current_recipe=recipe();version=root/'versions'/current_recipe[:16];version.mkdir(parents=True,exist_ok=True)
    _write(root/'active_runtime.json',{'path':str(version),'recipe':current_recipe})
    code_record={'files':{name:{'sha256':file_digest(path),'source':path.read_text()} for name,path in source_manifest().items()},'recipe':current_recipe}
    source_path=version/'source_snapshot.json'
    if not source_path.exists():write_once(source_path,code_record)
    registry=ModelRegistry(version/'registry.sqlite')
    empty_graph=DynamicEventGraph(root/'graph')
    ports=AppPorts(version,empty_graph,registry,current_recipe)
    return ports


def _run_application(manual=False):
    """Real scheduled job. Manual initialization uses actual clock, never a fake close."""
    from api.ml.institutional.data import utc
    torch.set_num_threads(2)
    ports=build_application();ports.status(phase='starting',message='Starting the isolated autonomous worker.')
    cutoff=datetime.now(timezone.utc).isoformat()
    ports.prepare(cutoff)
    nodes,edges=ports.core_graph(ports.fr)
    ports.graph=DynamicEventGraph(ROOT/'graph',nodes,max_nodes=256,core_edges=edges)
    cutoff=datetime.now(timezone.utc).isoformat()
    _,graph_digest=ports.graph.snapshot(cutoff)
    if not ports.shadow():ports.bootstrap(cutoff,graph_digest)
    baseline=_read(ROOT/'baseline_current.json') or {'recipe':digest('legacy-serving-reference'),'tasks':{}}
    baseline_artifact(ports,baseline)
    try:
        extractor=ExistingProviderExtractor()
        provider={'available':True,'provider':extractor.config['provider'],'model':extractor.config['model']}
    except Exception as exc:
        class UnavailableExtractor:
            version='unavailable'
            def invoke(self,messages):raise RuntimeError('Configured AI provider unavailable')
        extractor=UnavailableExtractor();provider={'available':False,'error_type':type(exc).__name__}
    ports.status(provider=provider,phase='ingesting',message='Discovering new official documents and extracting cited events.')
    ingestor=FinancialIngestionAgent(extractor,extractor.version,ROOT/'documents')
    class BudgetedIngestor(FinancialIngestionAgent):
        def ingest(self,sources,**kwargs):
            return super().ingest(sources,max_documents=6,**kwargs)
    ingestor=BudgetedIngestor(extractor,extractor.version,ROOT/'documents')
    config=json.loads(Path(__file__).with_name('config.json').read_text())
    sources=[Source(s['name'],s['feed_url'],tuple(s['allowed_hosts'])) for s in config['ingestion']['sources']]
    # Use the same actual-clock controller for both manual initialization and the
    # scheduled close; only the scheduling guard is bypassed on explicit manual runs.
    close_fn=market_close
    pipeline=AutonomousDailyPipeline(ports.root,ingestor,sources,ports.graph,ports.registry,PromotionGate(GateConfig(require_reference_skill=True)),ports,close_fn,ports.recipe_id)
    from api.ml.institutional.source_history import SourceQueryRecorder,query_history_status
    recorder=None
    try:
        recorder=SourceQueryRecorder(ports,ROOT/'source_queries')
        ingestor.source_observer=recorder.observe
    except Exception as exc:ports.status(query_collection={'status':'unavailable','error_type':type(exc).__name__})
    result=run_champion_challenger_pipeline(pipeline,manual=manual)
    if recorder is not None:
        try:
            recorder.finish([source.name for source in sources])
            from api.ml.institutional.source_replay import load_source_replay,source_replay_readiness,ensure_research_policy
            with sqlite3.connect(ports.db) as c:
                observed_labels={row[0]:(row[1],json.loads(row[2])['value']) for row in c.execute('SELECT id,known,payload FROM labels')}
            episodes,quality=load_source_replay(ROOT/'source_queries',cutoff=datetime.now(timezone.utc).isoformat(),feature_schema=recorder.schema,labels=observed_labels)
            ports.status(query_collection={**query_history_status(ROOT/'source_queries'),**source_replay_readiness(episodes),**quality})
            try:ports.status(source_policy=ensure_research_policy(episodes,ports.root/'source_policies',cutoff=datetime.now(timezone.utc).isoformat()))
            except Exception as exc:ports.status(source_policy={'status':'unavailable','error_type':type(exc).__name__,'live_ppo_enabled':False})
        except Exception as exc:ports.status(query_collection={'status':'unavailable','error_type':type(exc).__name__})
    cutoff=datetime.now(timezone.utc).isoformat();_,graph_digest=ports.graph.snapshot(cutoff)
    ports.record_forecast(cutoff,graph_digest,baseline,healthy=result.get('status')!='held_data_quality')
    completed_day=(datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat() if not manual and result.get('status')!='held_data_quality' else None)
    ports.status(last_run=result,last_run_date=completed_day,provider=provider,enabled=True,schedule='NYSE session close +20 minutes; daily observation collection and supervised/self-supervised eligibility checks.')
    print(json.dumps({'phase':'complete','result':result,'model_id':ports.shadow()},allow_nan=False))


def run_application(manual=False):
    import fcntl
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'application.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'phase':'already_running'}));return
        return _run_application(manual)


if __name__=='__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3]/'.env')
    from api.ml.deep import _worker_parent_guard
    _worker_parent_guard()
    parser=argparse.ArgumentParser();parser.add_argument('--manual',action='store_true');args=parser.parse_args()
    try:run_application(args.manual)
    except Exception as exc:
        import traceback
        version=_read(ROOT/'active_runtime.json') or {}
        if version.get('path'):_write(Path(version['path'])/'failure.json',{'error_type':type(exc).__name__,'message':str(exc)[:240],'at':datetime.now(timezone.utc).isoformat()})
        traceback.print_exc();raise
