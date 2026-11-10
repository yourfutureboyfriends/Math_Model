"""Actual application feature/target adapter. Historical seed != operational PIT history."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from api.ml.institutional.lineage import digest,file_digest
from api.ml.institutional.model import ModelConfig

TASK_NAMES=('recession_12m','spx_drawdown_6m','yields_up_3m','inflation_up_3m','oil_up_3m','unemployment_up_6m')
HORIZONS=(1,3,6,12)
NATIVE_HORIZONS=(12,6,3,3,3,6)
LAGS=(12,1,1,2,1,1)


def target_schema():
    return {'version':'macro-24-targets-v1','tasks':list(TASK_NAMES),'horizons':list(HORIZONS),
            'known_after':[[h+lag for lag in LAGS] for h in HORIZONS],
            'deployment_scope':list(zip(TASK_NAMES,NATIVE_HORIZONS)),
            'definitions':['Any NBER recession month in forward window','10% close-to-first-month-close equity drawdown',
                           'Higher monthly 10Y yield','Higher monthly CPI y/y','Higher monthly WTI price','Higher monthly unemployment'],
            'limitations':'Historical seed labels/features use currently available revised histories. Promotion evidence uses recorded prospective forecasts only.'}


def targets(months):
    """24 distinct labels with source-specific conservative maturation delays."""
    from api.ml.features import _fred_monthly,_yahoo_daily
    levels={key:_fred_monthly(sid) for key,sid in [('rec','USREC'),('yield','GS10'),('cpi','CPIAUCSL'),('oil','WTISPLC'),('unemp','UNRATE')]}
    levels['inflation']=(levels['cpi']/levels['cpi'].shift(12)-1)*100
    spx=_yahoo_daily('^GSPC').dropna()
    dictionaries={key:{d.strftime('%Y-%m'):float(v) for d,v in s.items() if np.isfinite(v)} for key,s in levels.items()}
    y=np.full((len(months),4,6),np.nan,dtype=np.float32)
    for i,month in enumerate(months):
        start=pd.Timestamp(month+'-01')
        for hi,h in enumerate(HORIZONS):
            end=start+pd.DateOffset(months=h)
            future=end.strftime('%Y-%m')
            window=pd.date_range(start,periods=h,freq='MS').strftime('%Y-%m')
            if all(m in dictionaries['rec'] for m in window):y[i,hi,0]=float(any(dictionaries['rec'][m]>=.5 for m in window))
            if not spx.empty:
                a=spx[spx.index>=start];w=a[a.index<end]
                if not w.empty and spx.index[-1]>=end:y[i,hi,1]=float(w.min()<=.9*a.iloc[0])
            for task,key in ((2,'yield'),(3,'inflation'),(4,'oil'),(5,'unemp')):
                series=dictionaries[key]
                if month in series and future in series:y[i,hi,task]=float(series[future]>series[month])
    return y


def maturity(month,cutoff):
    from api.ml.deep import _months_between
    current=pd.Timestamp(cutoff).strftime('%Y-%m')
    elapsed=_months_between(month,current)
    return np.array([[elapsed>=h+lag for lag in LAGS] for h in HORIZONS],dtype=bool)


def fetch_frame(root:Path):
    from api.ml.deep import load_frame
    fr=load_frame(include_targets=False)
    if fr['months'][-1]!=datetime.now(timezone.utc).strftime('%Y-%m'):
        raise ValueError('Current-month model inputs are required; no backdated forecast')
    fr['Y24']=targets(fr['months'])
    payload={k:np.asarray(v) for k,v in fr.items() if k in ('C','P','T','Y24','months','core_keys','text_keys','panel_keys','tasks','known_after')}
    stream=io.BytesIO();np.savez_compressed(stream,**payload);raw=stream.getvalue()
    sha=hashlib.sha256(raw).hexdigest();path=root/'raw'/(sha+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_bytes(raw)
    return fr,path,sha


def read_frame(path):
    with np.load(path,allow_pickle=False) as data:
        return {k:data[k].tolist() if data[k].dtype.kind in ('U','S') else data[k] for k in data.files}


def feature_schema(fr,state):
    from api.ml.modular import feature_groups
    from api.ml.deep import N_FACTORS
    groups=feature_groups(fr['core_keys'],N_FACTORS,fr['text_keys'])
    if max(map(len,groups.values()))>16:raise ValueError('Domain width exceeds configured capacity; no silent feature truncation')
    names=sorted(groups)
    groups={name:groups[name] for name in names}
    structure={'core_keys':fr['core_keys'],'panel_keys':fr['panel_keys'],'text_keys':fr['text_keys'],'groups':groups,'domain_names':names,
               'target_schema':target_schema(),'preprocessor_digest':hashlib.sha256(b''.join(np.asarray(state[k]).tobytes() for k in sorted(state))).hexdigest()}
    return structure,digest(structure)


def pack(fr,state,index,groups):
    from api.ml.deep import transform_features,SEQ,N_FACTORS
    if index<SEQ-1:raise ValueError('Insufficient sequence history')
    x=transform_features(fr,state)[index-SEQ+1:index+1]
    out=np.zeros((1,SEQ,len(groups),16),dtype=np.float32)
    valid=np.zeros_like(out,dtype=bool)
    text_offset=len(fr['core_keys'])+N_FACTORS
    texts=len(fr['text_keys'])
    for domain,indices in enumerate(groups.values()):
        out[0,:,domain,:len(indices)]=np.clip(x[:,indices],-10,10)
        for column,feature in enumerate(indices):
            if feature<text_offset:valid[0,:,domain,column]=True
            elif feature<text_offset+texts:valid[0,:,domain,column]=np.isfinite(fr['T'][index-SEQ+1:index+1,feature-text_offset])
    future=np.array([[np.sin(2*np.pi*(pd.Timestamp(fr['months'][index]+'-01').month+h)/12),
                       np.cos(2*np.pi*(pd.Timestamp(fr['months'][index]+'-01').month+h)/12),h/12,1.] for h in range(1,13)],dtype=np.float32)
    return {'specialists':torch.from_numpy(out),'observed_features':torch.from_numpy(valid),'known_future':torch.from_numpy(future[None])}


def graph_input(graph,origin):
    from api.ml.institutional.graph import graph_tensors
    x,edges,ids=graph_tensors(graph,origin)
    return {'graph_nodes':torch.from_numpy(x[None]),'edge_index':torch.from_numpy(edges),
            'edge_weight':torch.tensor([graph.edges[a,b]['weight'] for a,b in graph.edges],dtype=torch.float32)},ids


def load_graph(path):
    import networkx as nx
    payload=json.loads(Path(path).read_text());graph=nx.DiGraph()
    for n in payload['nodes']:graph.add_node(n['id'],**{k:v for k,v in n.items() if k!='id'})
    for e in payload['edges']:graph.add_edge(e['source'],e['target'],**{k:v for k,v in e.items() if k not in ('source','target')})
    return graph


def calibrate(model,items):
    from sklearn.linear_model import LogisticRegression
    records=[]
    model.eval()
    with torch.no_grad():
        for item in items:
            p=model.predict(item.tensors)['predictions'][0].numpy()
            records.append((p,item.tensors['target'][0].numpy(),item.tensors['known'][0].numpy()))
    result=[]
    for h in range(4):
        row=[]
        for j in range(6):
            values=[(p[h,j],y[h,j]) for p,y,k in records if k[h,j] and np.isfinite(y[h,j])]
            if len(values)<30 or min(sum(v[1]==0 for v in values),sum(v[1]==1 for v in values))<5:row.append(None);continue
            x,y=np.array(values).T
            fit=LogisticRegression(C=.2).fit(x[:,None],y)
            row.append({'slope':float(fit.coef_[0,0]),'intercept':float(fit.intercept_[0]),'observations':len(y)})
        result.append(row)
    return {'cells':result,'scope':'Disjoint retrospective foundation calibration; prospective validation still required.'}


def probabilities(logits,calibrator):
    values=np.array(logits,dtype=float).copy();ready=np.zeros((4,6),dtype=bool)
    for h,row in enumerate(calibrator['cells']):
        for j,cell in enumerate(row):
            if cell is not None:values[h,j]=values[h,j]*cell['slope']+cell['intercept'];ready[h,j]=True
    return 1/(1+np.exp(-np.clip(values,-40,40))),ready


def origin_regime(frame:dict,index:int) -> str:
    """Observable origin-state buckets; no later recession label enters routing."""
    values=dict(zip(frame['core_keys'],frame['C'][index]))
    inflation=values.get('cpi_yoy',float('nan'));labour=values.get('unemp_d6',float('nan'))
    if np.isfinite(labour) and labour>=.5:return 'labour_contraction'
    if np.isfinite(inflation) and inflation>=4:return 'high_inflation'
    return 'other_observed_state'


def learning_information_signature(source_snapshot:str,feature_schema_id:str,graph:object) -> str:
    """Deduplicate actual information, excluding clock/decay-only graph changes.

    Raw observations/schema and immutable event identities drive eligibility.
    Graph age and decaying edge weights still affect inference, but a repeated
    refresh cannot masquerade as newly observed training information.
    """
    events=sorted(name for name,data in graph.nodes(data=True) if data.get('kind')=='event')
    return digest({'source_snapshot':source_snapshot,'feature_schema':feature_schema_id,'events':events})
