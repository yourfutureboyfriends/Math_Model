"""Actual source-query alternatives, captured under frozen model/input identity."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import sqlite3
import time
import torch
from api.ml.institutional.graph import DynamicEventGraph
from api.ml.institutional.lineage import digest,file_digest,write_once
from api.ml.institutional import application_data as D


class SourceQueryRecorder:
    """Capture independent source alternatives against one unchanged baseline.

    Every alternative uses the actual fetched events for that source, the same
    pre-query observation snapshot, preprocessing and immutable model weights.
    No source is assigned a hypothetical outcome or a fabricated market label.
    Temporary graph databases are isolated from the live event ledger.
    """
    def __init__(self,ports:Any,destination:Path) -> None:
        self.ports=ports;self.root=destination/uuid4().hex;self.root.mkdir(parents=True)
        self.started=datetime.now(timezone.utc).isoformat();self.actions:dict[str,Any]={};self.events:dict[str,list[dict[str,Any]]]={}
        self.model_id=ports.shadow()
        self.model,self.state,self.structure,_,base,self.manifest=ports.load(ports.shadow())
        self.model.eval();self.weights=self.manifest['files']['weights']['sha256']
        self.schema=digest(self.structure)
        self.seed=self.root/'seed.sqlite'
        with sqlite3.connect(ports.graph.database) as source,sqlite3.connect(self.seed) as target:source.backup(target)


    def _state(self,name:str,events:list[dict[str,Any]],observed_at:str) -> tuple[dict[str,torch.Tensor],dict[str,Any]]:
        """Reconstruct only the pre-query ledger plus this source's event delta."""
        folder=self.root/('graph_'+digest(name)[:16]);folder.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.seed) as source,sqlite3.connect(folder/'events.sqlite') as target:source.backup(target)
        live=self.ports.graph
        graph_store=DynamicEventGraph(folder,core_nodes=live.core,max_nodes=live.max_nodes,core_edges=live.core_edges,
                                      half_life_days=live.half_life,window_days=live.window,min_correlation_days=live.minimum)
        graph_store.append(events,cutoff=observed_at,sources_complete=False)
        graph,graph_sha=graph_store.snapshot(observed_at)
        # Freeze graph decay/age at collection receipt; never backdate new nodes.
        batch=self.ports.tensors(self.ports.fr,self.state,len(self.ports.fr['months'])-1,self.structure,graph,observed_at)
        with torch.no_grad():output=self.model.predict(batch)
        trace={'probabilities':output['predictions'][0].sigmoid().tolist(),'embeddings':output['node_embeddings'][0].tolist(),
               'graph_snapshot':graph_sha,'available_at':observed_at,'prediction_available_at':datetime.now(timezone.utc).isoformat()}
        return batch,trace

    def observe(self,source:Any,events:list[dict[str,Any]],failures:list[dict[str,str]],metrics:dict[str,Any]) -> None:
        """Called after a real source fetch, including successful empty responses."""
        receipt=datetime.now(timezone.utc).isoformat();name=source.name
        record={'source':name,'feed_url':source.feed_url,'available_at':receipt,'source_failures':failures,
                'event_ids':[e['id'] for e in events],**metrics}
        record['eligible']=not failures
        self.events[name]=events
        self.actions[name]=record

    def finish(self,expected_sources:list[str]) -> dict[str,Any]:
        """Atomically publish a complete episode, or an explicit incomplete record."""
        origin=datetime.now(timezone.utc).isoformat()
        baseline,baseline_trace=self._state('baseline',[],origin)
        for name,record in self.actions.items():
            if not record['eligible']:continue
            try:
                batch,trace=self._state(name,self.events[name],origin)
                state_path=self.root/('state_'+digest(name)[:16]+'.pt')
                torch.save({k:v.detach().cpu() for k,v in batch.items()},state_path)
                record.update(trace=trace,tensors=state_path.name,tensors_sha256=file_digest(state_path))
            except Exception as exc:record.update(eligible=False,audit_error=type(exc).__name__)
        path=self.root/'baseline.pt';torch.save({k:v.detach().cpu() for k,v in baseline.items()},path)
        report={'schema':'macro.source_query.v1','origin':datetime.now(timezone.utc).isoformat(),'evaluation_cutoff':origin,'started_at':self.started,
                'feature_schema':self.schema,'weights_sha256':self.weights,'recipe':self.ports.recipe_id,
                'model_id':self.model_id,'source_snapshot':self.ports.source_sha,'month':self.ports.fr['months'][-1],
                'baseline':baseline_trace,'baseline_tensors':path.name,'baseline_sha256':file_digest(path),
                'actions':self.actions,'expected_sources':expected_sources,
                'complete':set(self.actions)==set(expected_sources) and all(a['eligible'] for a in self.actions.values()),
                'scope':'Observed source alternatives under frozen forecast weights. No future accuracy reward until labels mature.'}
        write_once(self.root/'episode.json',report)
        return report


def query_history_status(destination:Path) -> dict[str,Any]:
    """Count distinct collection days, not repeated manual runs as new evidence."""
    days=set();complete=0;failed=0;actions=set();latest=None
    for path in destination.glob('*/episode.json'):
        try:record=json.loads(path.read_text())
        except (OSError,ValueError):continue
        if record.get('complete'):
            complete+=1;days.add(record['origin'][:10]);actions.update(record['actions']);latest=max(latest or '',record['origin'])
        else:failed+=1
    return {'status':'collecting_query_history' if complete else 'awaiting_successful_source_queries',
            'complete_episodes':complete,'distinct_days':len(days),'incomplete_episodes':failed,'sources':sorted(actions),
            'last_collected_at':latest,'live_ppo_enabled':False,
            'reason':'Query collection is active. Policy training/deployment still requires matured outcome rewards and independent evaluation.'}
