"""Lagged discovery and explicit model-conditional interventions on KG variables.

Provenance nodes are never treated as observed economic variables. PCMCI links
are hypotheses conditional on its assumptions, not identified causal facts.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import networkx as nx
import numpy as np
import pandas as pd
import torch
from torch import Tensor
from api.ml.institutional.data import utc
from api.ml.institutional.model import DenseGAT


@dataclass(frozen=True)
class LaggedStructure:
    """Immutable discovery result; edges are (source, destination, positive lag)."""
    node_ids: tuple[str, ...]
    edges: tuple[tuple[int, int, int], ...]
    coefficients: np.ndarray
    intercept: np.ndarray
    fitted_through: str
    maximum_lag: int

    def expanded_dag(self) -> nx.DiGraph:
        """Retain temporal feedback as a DAG over (time, variable), never flatten it."""
        graph = nx.DiGraph()
        for t in range(self.maximum_lag + 1):
            graph.add_nodes_from((t, i) for i in range(len(self.node_ids)))
        for source, destination, lag in self.edges:
            for t in range(lag, self.maximum_lag + 1):
                graph.add_edge((t - lag, source), (t, destination))
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError('Time-expanded discovery must be acyclic')
        return graph


class CausalDiscoveryEngine:
    """PCMCI/ParCorr on train-only, finite, stationary candidate node series.

    Caller supplies transformed observed series, not labels or provenance paths.
    Mixed-frequency/PIT alignment must precede discovery. No imputation with
    later observations is performed here. Unknown/missing observations fail shut.
    """
    def __init__(self, maximum_lag: int = 3, alpha: float = .01, minimum_rows: int = 120) -> None:
        if not 1 <= maximum_lag <= 12 or not 0 < alpha < 1 or minimum_rows < 30:
            raise ValueError('Invalid discovery configuration')
        self.maximum_lag, self.alpha, self.minimum_rows = maximum_lag, alpha, minimum_rows
        self.structure: LaggedStructure | None = None

    def fit(self, frame: pd.DataFrame, *, cutoff: str, graph_node_ids: tuple[str, ...]) -> LaggedStructure:
        """Fit only declared feature nodes, BH-adjust MCI tests, then fit mechanisms."""
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        from tigramite.independence_tests.parcorr import ParCorr
        if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
            raise ValueError('Unique chronological node observations required')
        if any(not str(c).startswith('feature:') or c not in graph_node_ids for c in frame.columns):
            raise ValueError('Discovery accepts observed KG feature nodes only')
        times=pd.to_datetime(frame.index,utc=True)
        train=frame.loc[times <= utc(cutoff)]
        values=train.to_numpy(dtype=float)
        if len(train)<max(self.minimum_rows, 10*len(frame.columns)) or len(frame.columns)<2 or not np.isfinite(values).all():
            raise ValueError('Insufficient complete train-only node history')
        if (values.std(0)<1e-8).any():raise ValueError('Constant node series cannot be discovered')
        pcmci=PCMCI(dataframe=pp.DataFrame(values),cond_ind_test=ParCorr(significance='analytic'),verbosity=0)
        result=pcmci.run_pcmci(tau_min=1,tau_max=self.maximum_lag,pc_alpha=self.alpha)
        adjusted=pcmci.get_corrected_pvalues(p_matrix=result['p_matrix'],tau_min=1,tau_max=self.maximum_lag,fdr_method='fdr_bh')
        edges=tuple((int(i),int(j),int(lag)) for i,j,lag in np.argwhere(adjusted<self.alpha) if lag>0)
        n=len(frame.columns);coef=np.zeros((self.maximum_lag,n,n));bias=np.zeros(n)
        # X[j,t] = b[j] + sum_lag,i B[lag,j,i] X[i,t-lag] + epsilon[j,t].
        for j in range(n):
            parents=[(i,lag) for i,d,lag in edges if d==j]
            design=np.ones((len(values)-self.maximum_lag,1+len(parents)))
            for k,(i,lag) in enumerate(parents):design[:,k+1]=values[self.maximum_lag-lag:len(values)-lag,i]
            target=values[self.maximum_lag:,j]
            ridge=np.eye(design.shape[1])*.01;ridge[0,0]=0
            fitted=np.linalg.solve(design.T@design+ridge,design.T@target)
            bias[j]=fitted[0]
            for k,(i,lag) in enumerate(parents):coef[lag-1,j,i]=fitted[k+1]
        self.structure=LaggedStructure(tuple(map(str,frame.columns)),edges,coef,bias,times[times<=utc(cutoff)][-1].isoformat(),self.maximum_lag)
        self.structure.expanded_dag()
        return self.structure

    def perform_intervention(self, node_id: int, intervention_value: Tensor | None, *, history: Tensor, steps: int = 12) -> Tensor:
        """Simulate do(X[node,t]=v) under fitted linear lagged mechanisms.

        Incoming mechanisms at the intervened future node are replaced, not
        merely conditioned. Other nodes follow the learned lag equations. This
        Passing None follows the unchanged mechanisms for a paired baseline.
        This is a model-conditional scenario, not an empirically identified effect.
        """
        s=self.structure
        if s is None:raise RuntimeError('Fit and version mechanisms before intervention')
        if not 0<=node_id<len(s.node_ids) or steps<1 or steps>120 or history.shape!=(s.maximum_lag,len(s.node_ids)):
            raise ValueError('Intervention/history schema mismatch')
        if not torch.isfinite(history).all() or (intervention_value is not None and (intervention_value.numel()!=1 or not torch.isfinite(intervention_value).all())):
            raise ValueError('Finite scalar intervention and history required')
        coef=torch.as_tensor(s.coefficients,dtype=history.dtype,device=history.device)
        bias=torch.as_tensor(s.intercept,dtype=history.dtype,device=history.device)
        trajectory=[x.clone() for x in history]
        for _ in range(steps):
            next_value=bias+sum(coef[lag-1]@trajectory[-lag] for lag in range(1,s.maximum_lag+1))
            if intervention_value is not None:
                next_value=next_value.clone();next_value[node_id]=intervention_value.to(history).reshape(())
            if not torch.isfinite(next_value).all() or next_value.abs().max()>1e6:raise FloatingPointError('Unstable scenario mechanisms')
            trajectory.append(next_value)
        return torch.stack(trajectory[-steps:])


class CausalMaskedGATConv(DenseGAT):
    """Torch-equivalent GAT with adjacency[destination,source] and no implicit edges.

    A node's own embedding is a residual, not an extra causal message. Nodes
    without parents receive a zero message. Parameters match the existing GAT.
    """
    def forward(self, nodes: Tensor, adjacency: Tensor) -> tuple[Tensor,Tensor]:
        if adjacency.dtype!=torch.bool or adjacency.shape!=(nodes.shape[1],nodes.shape[1]):
            raise ValueError('Boolean causal adjacency must match the node schema')
        edges=adjacency.nonzero().T.flip(0).to(nodes.device)
        return super().forward(nodes,edges,allowed_mask=adjacency)


def causal_forecast(system: Any, tensors: dict[str,Tensor], structure: LaggedStructure, history: Tensor,
                    *, node_ids: tuple[str,...], node_id: int, intervention_value: Tensor | None = None) -> dict[str,Tensor]:
    """Route a fitted SCM scenario into the actual TFT graph and task heads.

    Only declared KG value channels are changed. Results are research scenario
    outputs; the original specialist inputs and production serving state remain
    unchanged and the output must not be represented as an identified effect.
    """
    engine=CausalDiscoveryEngine(structure.maximum_lag);engine.structure=structure
    path=engine.perform_intervention(node_id,intervention_value,history=history,steps=1)
    dag=structure.expanded_dag();order=sorted(dag);lookup={node:i for i,node in enumerate(order)}
    if len(order)>256:raise ValueError('Time-expanded causal graph exceeds model budget')
    source=tensors['graph_nodes']
    nodes=source.new_zeros((source.shape[0],len(order),source.shape[-1]))
    sequence=torch.cat([history,path],0)
    for position,(t,i) in enumerate(order):
        key=structure.node_ids[i]
        if key not in node_ids:raise ValueError('SCM variable missing from forecast graph')
        nodes[:,position]=source[:,node_ids.index(key)]
        nodes[:,position,17]=sequence[t,i];nodes[:,position,18]=0
    adjacency=torch.zeros((len(order),len(order)),dtype=torch.bool,device=source.device)
    for a,b in dag.edges:adjacency[lookup[b],lookup[a]]=True
    batch=dict(tensors);batch['graph_nodes']=nodes;batch['causal_mask']=adjacency
    batch['edge_index']=adjacency.nonzero().T.flip(0)
    batch.pop('edge_weight',None)
    return system.predict(batch)
