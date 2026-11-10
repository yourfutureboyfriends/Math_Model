"""Versioned event graph. Co-occurrence/correlation edges are associations, not causal shock paths."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
import itertools
import json
import math
from pathlib import Path
import sqlite3
from typing import Any
import networkx as nx
import numpy as np
import pandas as pd
from api.ml.institutional.data import utc
from api.ml.institutional.lineage import digest,write_once


ACTIONS = ('rate_hike','rate_cut','inflation_release','employment_release','guidance','supply_disruption','geopolitical_event','other')
NODE_FEATURE_DIM = 20


class DynamicEventGraph:
    """Durable deduplicated event ledger; bounded, rebuildable origin snapshots.

    Keep the evidence graph separate from any approved economic-dependency graph.
    The fixed neural input feature width does not depend on the number of nodes.
    Only days with successful configured-source collection enter correlation counts.
    """
    def __init__(self, root: Path, core_nodes: tuple[str,...] = (), max_nodes: int = 256,
                 half_life_days: float = 30., window_days: int = 90, min_correlation_days: int = 30,
                 core_edges: tuple[tuple[str,str],...] = ()) -> None:
        if half_life_days<=0 or max_nodes<len(core_nodes)+8:
            raise ValueError('Invalid graph budget')
        if any(a not in core_nodes or b not in core_nodes for a,b in core_edges):raise ValueError('Unknown core edge endpoint')
        self.core_edges = core_edges
        self.root,self.core,self.max_nodes = root,core_nodes,max_nodes
        self.half_life,self.window,self.minimum = half_life_days,window_days,min_correlation_days
        root.mkdir(parents=True,exist_ok=True)
        self.database = root/'events.sqlite'
        with sqlite3.connect(self.database) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, available_at TEXT, payload TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS observed_days(day TEXT PRIMARY KEY, available_at TEXT)')

    def append(self, events: list[dict[str,Any]], *, cutoff: str, sources_complete: bool) -> None:
        now = utc(cutoff)
        with sqlite3.connect(self.database,timeout=30) as c:
            for event in events:
                if utc(event['available_at'])>now or utc(event['first_seen_at'])>now:
                    raise ValueError('Future graph event rejected')
                c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?)',(event['id'],utc(event['available_at']).isoformat(),json.dumps(event,allow_nan=False)))
            if sources_complete:
                c.execute('INSERT OR IGNORE INTO observed_days VALUES(?,?)',(now.date().isoformat(),now.isoformat()))

    def snapshot(self, cutoff: str) -> tuple[nx.DiGraph,str]:
        now = utc(cutoff)
        start = now-pd.Timedelta(days=self.window)
        with sqlite3.connect(self.database) as c:
            rows = c.execute('SELECT payload FROM events WHERE available_at<=? AND available_at>=? ORDER BY available_at,id',
                             (now.isoformat(),start.isoformat())).fetchall()
            days = [r[0] for r in c.execute('SELECT day FROM observed_days WHERE available_at<=? AND available_at>=? ORDER BY day',
                                          (now.isoformat(),start.isoformat()))]
        events = [json.loads(r[0]) for r in rows]
        graph = nx.DiGraph()
        graph.graph['as_of'] = now.isoformat()
        graph.add_nodes_from((name,{'kind':'core','core':True}) for name in self.core)
        for a,b in self.core_edges:graph.add_edge(a,b,weight=1.,relation='configured_input_path')
        evidence: dict[tuple[str,str,str],list[tuple[float,str]]] = defaultdict(list)
        by_document: dict[str,set[str]] = defaultdict(set)
        document_decay: dict[str,float] = defaultdict(float)
        counts: dict[str,Counter] = defaultdict(Counter)
        for event in events:
            entity,action = 'entity:'+event['entity'],'action:'+event['action']
            age = (now-utc(event['available_at'])).total_seconds()/86400
            decay = 2**(-age/self.half_life)
            event_node = 'event:'+event['id']
            graph.add_node(entity,kind='entity',core=False)
            graph.add_node(action,kind='action',core=False)
            graph.add_node(event_node,kind='event',core=False,available_at=event['available_at'],source_digest=event['source_digest'],
                           action=event['action'],temporal_type=event.get('temporal_type','observed'),sentiment=float(event.get('sentiment',0.)),confidence=float(event.get('confidence',0.)))
            graph.nodes[action]['action'] = event['action']
            evidence[(entity,event_node,'evidence')].append((decay,event['id']))
            evidence[(event_node,action,'reported_action')].append((decay,event['id']))
            by_document[event['source_digest']].add(entity)
            document_decay[event['source_digest']] = max(document_decay[event['source_digest']],decay)
            counts[utc(event['available_at']).date().isoformat()][entity] += 1
        for document,entities in by_document.items():
            for a,b in itertools.combinations(sorted(entities),2):
                evidence[(a,b,'cooccurrence')].append((document_decay[document],'document co-occurrence'))
                evidence[(b,a,'cooccurrence')].append((document_decay[document],'document co-occurrence'))
        # Confidence is recorded but is never treated as calibrated event truth.
        for (a,b,relation),support in evidence.items():
            weight = sum(s[0] for s in support)
            if weight>=.02:
                graph.add_edge(a,b,weight=weight,relation=relation,evidence=[s[1] for s in support][:32])
        entities = sorted({e for day in counts.values() for e in day})[:64]
        if len(days)>=self.minimum and len(entities)>1:
            frame = pd.DataFrame([{e:counts[d][e] for e in entities} for d in days],dtype=float)
            corr = frame.corr(min_periods=self.minimum)
            for a,b in itertools.combinations(entities,2):
                r = corr.loc[a,b]
                if np.isfinite(r) and abs(r)>=.5:
                    latest_a = max(d for d in days if counts[d][a]>0)
                    latest_b = max(d for d in days if counts[d][b]>0)
                    last_joint_support = utc(min(latest_a,latest_b)+'T00:00:00Z')
                    age = max(0.,(now-last_joint_support).total_seconds()/86400)
                    strength = float(abs(r)*2**(-age/self.half_life))
                    if strength>=.02:
                        for source,target in ((a,b),(b,a)):
                            if not graph.has_edge(source,target):
                                graph.add_edge(source,target,weight=strength,signed_correlation=float(r),relation='event_count_correlation',n_days=len(days))
        # Prune derived view only; never delete historical ledger entries/snapshots.
        optional = [n for n,d in graph.nodes(data=True) if not d.get('core')]
        ranked = sorted(optional,key=lambda n:(-graph.degree(n,weight='weight'),n))
        graph.remove_nodes_from(ranked[max(0,self.max_nodes-len(self.core)):])
        payload = {'schema':'macro.event_graph.v1','as_of':now.isoformat(),'node_ids':sorted(graph),
                   'nodes':[{ 'id':n,**graph.nodes[n]} for n in sorted(graph)],
                   'edges':[{ 'source':a,'target':b,**d} for a,b,d in sorted(graph.edges(data=True))],
                   'limitations':'Reported evidence and statistical associations; not causal structure or verified event truth.'}
        version = digest(payload)
        path = self.root/'snapshots'/(version+'.json')
        if not path.exists():
            write_once(path,payload)
        return graph,version


def graph_tensors(graph: nx.DiGraph, cutoff: str) -> tuple[np.ndarray,np.ndarray,list[str]]:
    """Twenty fixed-width node attributes; no future targets or model forecasts.

    Use this adapter only for this event graph. A provenance graph needs a
    separate whitelist adapter; do not include target/forecast node values.
    """
    origin = utc(cutoff)
    ids = sorted(graph)
    if not ids:
        raise ValueError('Empty graph')
    index = {name:i for i,name in enumerate(ids)}
    features = []
    for name in ids:
        data = graph.nodes[name]
        stamp = data.get('available_at')
        age = (origin-utc(stamp)).total_seconds()/86400 if stamp else 0.
        if age<0:
            raise ValueError('Future graph node')
        kind = data.get('kind')
        if kind not in ('core','entity','action','event') or name.startswith(('forecast:','task:','observation:','model:','paper:')):
            raise ValueError('Target/output/reference nodes are not graph model inputs')
        value = data.get('value_z')
        if value is not None and not np.isfinite(value): raise ValueError('Nonfinite PIT node value')
        features.append([float(kind==k) for k in ('core','entity','action','event')]
            +[float(data.get('action')==action) for action in ACTIONS]
            +[float(data.get('sentiment',0.)),float(data.get('confidence',0.)),min(age/90,1.),
              np.log1p(graph.in_degree(name,weight='weight')),np.log1p(graph.out_degree(name,weight='weight')),
              float(np.clip(value,-10,10)) if value is not None else 0.,float(value is None),float(data.get('temporal_type')=='announced')])
    edges = np.array([(index[a],index[b]) for a,b in graph.edges],dtype=np.int64).T.reshape(2,-1)
    return np.array(features,dtype=np.float32),edges,ids


def rolling_graph_statistics(history: list[tuple[str,nx.DiGraph]], cutoff: str, window_days: int = 30) -> pd.DataFrame:
    """Origin-filtered PageRank/degrees and edge-strength change over a past window.

    Momentum is last-snapshot minus last snapshot available before window start;
    missing baseline yields NaN, never an invented historical zero.
    """
    now = utc(cutoff)
    eligible = sorted([(utc(t),g) for t,g in history if utc(t)<=now],key=lambda pair:pair[0])
    if not eligible:
        raise ValueError('No point-in-time graph snapshot')
    _,current = eligible[-1]
    baseline = [g for t,g in eligible if t<=now-pd.Timedelta(days=window_days)]
    rank = nx.pagerank(current,weight='weight')
    return pd.DataFrame([{'node':n,'pagerank':rank[n],'in_degree':current.in_degree(n),'out_degree':current.out_degree(n),
                          'incoming_weight_momentum':current.in_degree(n,weight='weight')-(baseline[-1].in_degree(n,weight='weight') if n in baseline[-1] else 0.) if baseline else np.nan}
                         for n in sorted(current)])
