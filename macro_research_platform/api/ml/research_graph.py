"""Read-only evidence graph: configured relationships and saved observations, never inferred causality.

Building this graph does not fetch providers, start training or import Torch.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json

PAPERS = [
 ('qlib','Qlib research workflow','https://arxiv.org/abs/2009.11189','https://github.com/microsoft/qlib','Workflow reference; not an installed dependency.'),
 ('doubleadapt','DoubleAdapt','https://arxiv.org/abs/2306.09862','https://github.com/SJTU-DMTai/DoubleAdapt','Candidate incremental adapter; not implemented in the served model.'),
 ('ddgda','DDG-DA','https://arxiv.org/abs/2201.04038','https://github.com/microsoft/qlib/tree/main/qlib/contrib/meta/data_selection','Candidate learned sample weighting; current recency weights are fixed.'),
 ('cbp','Continual Backpropagation','https://doi.org/10.1038/s41586-024-07711-7','https://github.com/shibhansh/loss-of-plasticity','Research reference; neuron replacement is not enabled.'),
 ('abides','ABIDES-Gym','https://arxiv.org/abs/2110.14771','https://github.com/jpmorganchase/abides-jpmc-public','Execution simulation reference; not the macro forecasting engine.'),
]


def build(trace=None, provider_state=None):
    from api.ml.features import FEATURES, TEXT
    from api.ml.tasks import TASKS
    from api.ml.modular import CORE_GROUPS
    from api.ml import panel,context
    from api.handlers.macro_inputs import _disk_load
    if trace is None:
        from api.ml.live import _read, directory
        trace = _read(directory()/'trace.json') or {}
    if provider_state is None:
        from api.ml.online import read
        provider_state = read()
    nodes={};edges=[]
    def node(id,label,kind,detail,**extra):
        nodes[id]={'id':id,'label':label,'kind':kind,'detail':detail,**extra}
    def edge(source,target,relation,detail,observed=False,**extra):
        edges.append({'id':f'{source}|{relation}|{target}','source':source,'target':target,
                      'relation':relation,'detail':detail,'observed':observed,**extra})
    providers={
      'market_features':('Market history','https://finance.yahoo.com/'),
      'macro_features':('FRED macro data','https://fred.stlouisfed.org/'),
      'news_features':('News & uncertainty','https://www.frbsf.org/research-and-insights/data-and-indicators/daily-news-sentiment-index/'),
      'macro_panel':('Broad macro panel','https://fred.stlouisfed.org/'),
      'context_features':('Expanded research factors','https://fred.stlouisfed.org/'),
      'core':('Core Fed / ALFRED inputs','https://alfred.stlouisfed.org/'),
    }
    for key,(label,url) in providers.items():
        state=provider_state.get('sources',{}).get(key,{})
        node('source:'+key,label,'source','Configured source adapter. A connection does not imply a successful current refresh.',
             url=url,observed_at=state.get('refreshed_at'),status=state.get('status','configured'),
             quality=state.get('quality'),error=state.get('error'),digest=state.get('digest'))
    groups={**{k:list(v) for k,v in CORE_GROUPS.items()},'news':list(TEXT),'macro_factors':[]}
    for spec in context.SPECS.values():groups.setdefault(spec[2],[])
    for group in groups:
        node('module:'+group,group.replace('_',' ').title(),'module','Configured specialist encoder; displayed paths describe architecture, not causal influence.')
    for key,(label,unit,description) in {**FEATURES,**TEXT}.items():
        group=next((g for g,keys in groups.items() if key in keys),None)
        source='news_features' if key in TEXT else 'market_features' if key in ('spx6','spx_vol3','usd6') else 'core' if key in ('ts','ntfs','ebp','pay6') else 'macro_features'
        node('feature:'+key,label,'feature',description,unit=unit,key=key,status='configured',
             limitation='Per-feature freshness is not inferred from an adapter-level acceptance time.')
        edge('source:'+source,'feature:'+key,'supplies',description)
        if group:edge('feature:'+key,'module:'+group,'encoded_by','Configured modular feature membership.')
    panel_data=((_disk_load('ri_ml_panel') or {}).get('data')) or {}
    for key,(group,code,label) in panel.SERIES.items():
        id='feature:p_'+key;values=panel_data.get('p_'+key,{})
        node(id,label,'feature','FRED-MD-style panel input. Transformation code '+str(code)+'. Revised historical data with one-month lag.',
             key='p_'+key,group=group,url='https://fred.stlouisfed.org/series/'+key,
             status='cached panel input' if values else 'missing panel input',as_of=max(values) if values else None,
             coverage_months=len(values),factor_family='macro panel')
        edge('source:macro_panel',id,'supplies','FRED monthly series; one-month lag is not a historical release-vintage reconstruction.')
        edge(id,'module:macro_factors','encoded_by','Training-only PCA compression of eligible panel series. Individual factor loading is not exposed here.')
    context_coverage=context.coverage()
    for row in context_coverage:
        id='feature:'+row['key']
        node(id,row['label'],'feature',row['limitation'],key=row['key'],group=row['group'],url=row['source_url'],
             status=row['status'],as_of=row['latest'],coverage_months=row['observations'],lag_months=row['lag_months'],
             transform=row['transform'],factor_family='expanded research')
        edge('source:context_features',id,'supplies','FRED '+row['series']+'; '+str(row['lag_months'])+'-month conservative lag.')
        edge(id,'module:'+row['group'],'encoded_by','Optional research input with its own missing-value flag; requires fresh model validation.')
    edge('source:macro_panel','module:macro_factors','transformed_into','Macro panel → training-fitted PCA factors; no individual factor attribution is asserted.')
    node('model:fusion','Fusion & temporal memory','model','Specialist representations → learned routing and concatenation → GRU → temporal attention.',
         observed_at=trace.get('inferred_at'),trained_at=trace.get('trained_at'),status=trace.get('purpose','no saved checkpoint'),
         digest=trace.get('input_digest'),as_of=trace.get('as_of'))
    seeds=trace.get('seeds') or []
    for group in groups:
        weights=[]
        for seed in seeds:
            names=seed.get('modules',[])
            if group in names and seed.get('routing'):
                weights.append(seed['routing'][-1][names.index(group)])
        weight=sum(weights)/len(weights) if weights else None
        edge('module:'+group,'model:fusion','routes_to','Latest saved routing averaged over available seeds; routing is not causal attribution.' if weights else 'Configured architecture; no saved routing measurement.',
             observed=bool(weights),weight=weight,observed_at=trace.get('inferred_at'))
    for key,task in TASKS.items():
        id='task:'+key
        node(id,task.title,'forecast',task.question,used_for=task.used_for,known_after=task.known_after,
             status='configured task',limitation='Saved research probabilities are uncalibrated and are not served forecasts.')
        edge('model:fusion',id,'predicts','Configured task head; not evidence that this head has been validated or promoted.')
        for feature in task.features:
            if 'feature:'+feature in nodes:edge('feature:'+feature,id,'task_input','Declared task feature for the conventional task models; not an individual modular-network connection.')
        values=[]
        for seed in seeds:
            if key in trace.get('tasks',[]) and seed.get('probabilities'):
                v=seed['probabilities'][-1][trace['tasks'].index(key)]
                if v is not None:values.append(v)
        if values:
            observation='observation:'+key
            node(observation,'Raw research: '+task.title,'observation','Latest saved research-head probability averaged across trained seeds; not a historical out-of-sample result.',
                 value=sum(values)/len(values),as_of=trace.get('as_of'),observed_at=trace.get('inferred_at'),digest=trace.get('input_digest'))
            edge(id,observation,'saved_output','Read from the saved network trace.',observed=True,observed_at=trace.get('inferred_at'))
    node('method:workflow','Research / validation workflow','method','Data snapshots, delayed labels, chronological evaluation and separate promotion decisions.')
    edge('method:workflow','model:fusion','governs','Implementation workflow; model quality must be evaluated separately.')
    for key,label,url,code,detail in PAPERS:
        node('paper:'+key,label,'paper',detail,url=url,code_url=code,status='research reference')
        edge('paper:'+key,'method:workflow','research_reference',detail)
    payload={'factor_coverage':context_coverage,'coverage_gaps':['Global country-specific fundamentals and fiscal risk','Company earnings, valuation, ownership and flows','Geopolitics, climate and unexpected events','Release-vintage histories for revised indicators','Supply-chain index ingestion and licensed positioning data'],'nodes':list(nodes.values()),'edges':edges,'as_of':trace.get('as_of'),
             'scope':'Current macro ML sources, configured inputs, architecture, saved research outputs and reviewed papers. Company/document ingestion is not yet connected.',
             'limitations':['Connections are provenance or configuration, not causation.','Research references do not mean their algorithms are implemented.','Source acceptance does not certify every observation as a historical release vintage.']}
    payload['revision']=hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()[:16]
    payload['generated_at']=datetime.now(timezone.utc).isoformat()
    return payload
