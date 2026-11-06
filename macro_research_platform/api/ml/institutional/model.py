"""TFT-style multi-horizon adapter for domain experts and an origin-frozen graph.

Input contracts: specialists [B,T,S,D], graph attributes [B,N,F], directed
edge_index [2,E] (source -> destination), known-future covariates [B,12,K].
Graph covariates are computed at the forecast origin, never from future graphs.
This is a domain-specialist adaptation, not a byte-for-byte port of Google's TFT.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import torch
from torch import Tensor, nn
import torch.nn.functional as F


class GatedResidualNetwork(nn.Module):
    """Context-conditioned GRN with gated skip connection and layer normalization."""
    def __init__(self, inputs: int, hidden: int, output: int, context: int = 0, dropout: float = .1) -> None:
        super().__init__()
        self.first = nn.Linear(inputs, hidden)
        self.context = nn.Linear(context, hidden, bias=False) if context else None
        self.second = nn.Linear(hidden, output)
        self.gate = nn.Linear(output, 2 * output)
        self.skip = nn.Linear(inputs, output) if inputs != output else nn.Identity()
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(output)

    def forward(self, x: Tensor, context: Tensor | None = None) -> Tensor:
        h = self.first(x)
        if self.context is not None:
            if context is None:
                raise ValueError('GRN context is required')
            while context.ndim < h.ndim:
                context = context.unsqueeze(1)
            h = h + self.context(context)
        h = self.dropout(self.second(F.elu(h)))
        return self.norm(self.skip(x) + F.glu(self.gate(h), dim=-1))


class DenseGAT(nn.Module):
    """Small-graph equivalent of multi-head GAT; O(N²), explicitly capped.

    All edges are directed source->destination; self loops are added. Returned
    attention is [B,heads,destination,source]. It is not causal attribution.
    Each batch shares topology; node attributes may change at each origin.
    """
    def __init__(self, inputs: int, hidden: int, heads: int = 4, max_nodes: int = 256) -> None:
        super().__init__()
        if heads<1 or hidden<1 or hidden % heads:
            raise ValueError('hidden must be divisible by graph heads')
        self.heads, self.width, self.max_nodes = heads, hidden // heads, max_nodes
        self.projection = nn.Linear(inputs, hidden, bias=False)
        self.a_source = nn.Parameter(torch.empty(heads, self.width))
        self.a_destination = nn.Parameter(torch.empty(heads, self.width))
        nn.init.xavier_uniform_(self.a_source)
        nn.init.xavier_uniform_(self.a_destination)
        self.norm = nn.LayerNorm(hidden)

    def forward(self, nodes: Tensor, edge_index: Tensor, edge_weight: Tensor | None = None, *, allowed_mask: Tensor | None = None) -> tuple[Tensor, Tensor]:
        b, n, _ = nodes.shape
        if not 1 <= n <= self.max_nodes or not torch.isfinite(nodes).all():
            raise ValueError('Invalid graph size or attributes')
        if edge_index.dtype != torch.long or edge_index.ndim != 2 or edge_index.shape[0] != 2:
            raise ValueError('edge_index must be int64 [2,E]')
        if edge_index.numel() and (edge_index.min() < 0 or edge_index.max() >= n):
            raise ValueError('Graph edge index out of bounds')
        mask = torch.eye(n, dtype=torch.bool, device=nodes.device)
        prior = nodes.new_ones(n,n)
        if edge_weight is not None:
            if edge_weight.shape!=(edge_index.shape[1],) or not torch.isfinite(edge_weight).all() or (edge_weight<0).any():
                raise ValueError('Nonnegative finite graph edge priors required')
        if edge_index.numel():
            magnitude = nodes.new_ones(edge_index.shape[1]) if edge_weight is None else edge_weight.to(nodes.device)
            mask[edge_index[1], edge_index[0]] = magnitude>0
            prior[edge_index[1], edge_index[0]] = magnitude.clamp_min(1e-12)
        if allowed_mask is None:
            mask.fill_diagonal_(True)
            prior.fill_diagonal_(1.)
        else:
            if allowed_mask.dtype!=torch.bool or allowed_mask.shape!=(n,n):raise ValueError('Invalid causal mask')
            mask = mask & allowed_mask.to(nodes.device)
        empty = ~mask.any(-1)
        # Safe softmax for roots; zero the placeholder afterward (no message).
        safe_mask=mask.clone()
        safe_mask[empty,empty]=True
        z = self.projection(nodes).view(b, n, self.heads, self.width)
        src = torch.einsum('bnhd,hd->bhn', z, self.a_source)
        dst = torch.einsum('bnhd,hd->bhn', z, self.a_destination)
        scores = F.leaky_relu(dst.unsqueeze(-1) + src.unsqueeze(-2), .2) + prior.log()
        weights = scores.masked_fill(~safe_mask, -torch.inf).softmax(-1)
        weights = weights.masked_fill(~mask,0.)
        embedded = torch.einsum('bhij,bjhd->bihd', weights, z).reshape(b, n, -1)
        if allowed_mask is not None:embedded=embedded+z.reshape(b,n,-1)  # local state residual, no extra graph edge
        return self.norm(F.elu(embedded)), weights


class GraphEncoder(nn.Module):
    """Two GAT layers and masked pooling to TFT's origin-static covariates."""
    def __init__(self, inputs: int, hidden: int, heads: int = 4) -> None:
        super().__init__()
        self.first = DenseGAT(inputs, hidden, heads)
        self.second = DenseGAT(hidden, hidden, heads)

    def forward(self, nodes: Tensor, edges: Tensor, edge_weight: Tensor | None = None, causal_mask: Tensor | None = None) -> tuple[Tensor, Tensor, Tensor]:
        z, _ = self.first(nodes, edges, edge_weight, allowed_mask=causal_mask)
        z, attention = self.second(z, edges, edge_weight, allowed_mask=causal_mask)
        return z.mean(1), z, attention


class SparseDomainMoE(nn.Module):
    """Top-k domain dispatch: only selected token/expert pairs are evaluated.

    No capacity dropping. All inputs have fixed shape and a domain-level
    availability mask. Include value-level missing indicators in domain inputs.
    The router's soft probabilities and VSN prior preserve router gradients.
    """
    def __init__(self, domains: int, inputs: int, hidden: int, top_k: int = 2) -> None:
        super().__init__()
        if not 1 <= top_k <= domains:
            raise ValueError('Invalid expert top_k')
        self.domains, self.hidden, self.top_k = domains, hidden, top_k
        self.router = nn.Linear(domains * inputs, domains)
        self.experts = nn.ModuleList([
            nn.Sequential(nn.Linear(inputs, hidden), nn.GELU(), nn.Linear(hidden, hidden))
            for _ in range(domains)
        ])

    def forward(self, x: Tensor, available: Tensor | None = None) -> tuple[Tensor, Tensor, Tensor]:
        if x.ndim != 4 or x.shape[2] != self.domains or not torch.isfinite(x).all():
            raise ValueError('Expected finite specialist inputs [B,T,S,D]')
        b, t, s, d = x.shape
        available = torch.ones((b,t,s), dtype=torch.bool, device=x.device) if available is None else available
        if available.shape != (b,t,s) or available.dtype != torch.bool or not available.any(-1).all():
            raise ValueError('Every token requires at least one available specialist')
        clean = x.masked_fill(~available.unsqueeze(-1), 0.)
        logits = self.router(clean.reshape(b*t, s*d)).float()
        availability = available.reshape(b*t, s)
        probabilities = logits.masked_fill(~availability, -torch.inf).softmax(-1)
        selected = probabilities.topk(self.top_k, dim=-1).indices
        gates = torch.zeros_like(probabilities).scatter(1, selected, 1.) * availability
        prior = probabilities * gates
        prior = prior / prior.sum(-1, keepdim=True)
        flat = clean.reshape(b*t,s,d)
        encoded = x.new_zeros(b*t,s,self.hidden)
        for i, expert in enumerate(self.experts):
            rows = torch.nonzero(gates[:,i] > 0, as_tuple=True)[0]
            if len(rows):
                encoded[rows,i] = expert(flat[rows,i])
        # Switch-style balancing surrogate; no rare-regime accuracy guarantee.
        load = gates / gates.sum(-1, keepdim=True)
        balance = s * (probabilities.mean(0) * load.mean(0)).sum()
        return encoded.view(b,t,s,-1), prior.view(b,t,s), balance


class VariableSelectionNetwork(nn.Module):
    """Context-conditioned VSN over specialist representations, with router prior."""
    def __init__(self, variables: int, hidden: int, dropout: float) -> None:
        super().__init__()
        self.transforms = nn.ModuleList([GatedResidualNetwork(hidden,hidden,hidden,dropout=dropout) for _ in range(variables)])
        self.score = GatedResidualNetwork(variables*hidden,hidden,variables,hidden,dropout)

    def forward(self, x: Tensor, context: Tensor, prior: Tensor) -> tuple[Tensor, Tensor]:
        logits = self.score(x.flatten(-2),context)
        logits = (logits + prior.clamp_min(1e-12).log()).masked_fill(prior <= 0, -torch.inf)
        weights = logits.softmax(-1)
        transformed = torch.stack([layer(x[:,:,i]) for i,layer in enumerate(self.transforms)], dim=-2)
        return (transformed * weights.unsqueeze(-1)).sum(-2), weights


class InterpretableAttention(nn.Module):
    """Causal TFT-style attention: separate Q/K heads and shared value projection."""
    def __init__(self, hidden: int, heads: int, dropout: float) -> None:
        super().__init__()
        if heads<1 or hidden<1 or hidden % heads:
            raise ValueError('hidden must divide by temporal heads')
        self.heads, self.width = heads, hidden // heads
        self.query, self.key = nn.Linear(hidden,hidden), nn.Linear(hidden,hidden)
        self.value = nn.Linear(hidden,self.width)
        self.output = nn.Linear(self.width,hidden)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: Tensor, query_start: int) -> tuple[Tensor, Tensor]:
        b,n,_ = x.shape
        q = self.query(x[:,query_start:]).view(b,n-query_start,self.heads,self.width).transpose(1,2)
        k = self.key(x).view(b,n,self.heads,self.width).transpose(1,2)
        scores = q @ k.transpose(-1,-2) / math.sqrt(self.width)
        mask = torch.arange(n,device=x.device)[None,:] <= torch.arange(query_start,n,device=x.device)[:,None]
        weights = scores.masked_fill(~mask,-torch.inf).softmax(-1)
        attended = self.dropout(weights) @ self.value(x).unsqueeze(1)
        return self.output(attended.mean(1)), weights


@dataclass(frozen=True)
class ModelConfig:
    domains: int = 11
    domain_inputs: int = 16
    graph_inputs: int = 20
    known_future_inputs: int = 4
    tasks: int = 6
    hidden: int = 64
    heads: int = 4
    top_k: int = 2
    horizons: tuple[int,...] = (1,3,6,12)
    dropout: float = .1

    def __post_init__(self) -> None:
        object.__setattr__(self,'horizons',tuple(self.horizons))
        for name in ('domains','domain_inputs','graph_inputs','known_future_inputs','tasks','hidden','heads','top_k'):
            value = getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or value<1:
                raise ValueError('Positive integer model dimensions required: '+name)
        if self.hidden%self.heads or self.top_k>self.domains or not 0<=self.dropout<1:
            raise ValueError('Invalid attention, routing or dropout configuration')
        if not self.horizons or any(isinstance(h,bool) or not isinstance(h,int) or not 1<=h<=60 for h in self.horizons):
            raise ValueError('Horizon months must be integers in [1,60]')


class MacroTFT(nn.Module):
    """Sparse domain MoE + GAT origin covariates + TFT-style multi-horizon head.

    Returns raw logits for binary tasks or locations for regression tasks;
    interpretation is specified separately in the immutable target schema.
    Padding is not supported: provide a fixed, fully observed/missing-flagged
    history. known_future must contain only origin-known quantities, e.g. calendar.
    """
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        if not cfg.horizons or tuple(sorted(set(cfg.horizons))) != cfg.horizons or min(cfg.horizons)<1:
            raise ValueError('Horizons must be sorted, unique positive month counts')
        self.cfg = cfg
        h = cfg.hidden
        self.graph = GraphEncoder(cfg.graph_inputs,h,cfg.heads)
        self.debate_projection = nn.Linear(24,h,bias=False)
        nn.init.zeros_(self.debate_projection.weight)
        self.moe = SparseDomainMoE(cfg.domains,cfg.domain_inputs,h,cfg.top_k)
        self.vsn = VariableSelectionNetwork(cfg.domains,h,cfg.dropout)
        self.static_selection = GatedResidualNetwork(h,h,h,dropout=cfg.dropout)
        self.initial_hidden = nn.Linear(h,h)
        self.initial_cell = nn.Linear(h,h)
        self.future_projection = nn.Linear(cfg.known_future_inputs,h)
        self.encoder, self.decoder = nn.LSTM(h,h,batch_first=True), nn.LSTM(h,h,batch_first=True)
        self.local_gate = nn.Sequential(nn.Linear(h,2*h), nn.GLU())
        self.local_norm = nn.LayerNorm(h)
        self.enrichment = GatedResidualNetwork(h,h,h,h,cfg.dropout)
        self.attention = InterpretableAttention(h,cfg.heads,cfg.dropout)
        self.attention_gate = nn.Sequential(nn.Linear(h,2*h), nn.GLU())
        self.attention_norm = nn.LayerNorm(h)
        self.positionwise = GatedResidualNetwork(h,h,h,dropout=cfg.dropout)
        self.final_gate = nn.Sequential(nn.Linear(h,2*h), nn.GLU())
        self.final_norm = nn.LayerNorm(h)
        self.reconstruction_head = nn.Linear(h,cfg.domains*cfg.domain_inputs)
        self.task_heads = nn.ModuleList([nn.Linear(h,1) for _ in range(cfg.tasks)])

    def forward(self, specialists: Tensor, graph_nodes: Tensor, edge_index: Tensor,
                known_future: Tensor, available: Tensor | None = None, edge_weight: Tensor | None = None,
                causal_mask: Tensor | None = None, debate_features: Tensor | None = None) -> dict[str,Tensor]:
        if specialists.ndim!=4 or specialists.shape[2:]!=(self.cfg.domains,self.cfg.domain_inputs) or specialists.shape[1]<1:
            raise ValueError('Specialist input schema mismatch')
        if graph_nodes.ndim!=3 or graph_nodes.shape[0]!=specialists.shape[0] or graph_nodes.shape[-1]!=self.cfg.graph_inputs:
            raise ValueError('Graph input schema mismatch')
        if known_future.ndim!=3 or known_future.shape[0]!=specialists.shape[0] or known_future.shape[-1]!=self.cfg.known_future_inputs:
            raise ValueError('Known-future covariate schema mismatch')
        if known_future.shape[1] != max(self.cfg.horizons) or not torch.isfinite(known_future).all():
            raise ValueError('Supply all origin-known monthly decoder covariates through the maximum horizon')
        static, node_embeddings, graph_attention = self.graph(graph_nodes,edge_index,edge_weight,causal_mask)
        if debate_features is not None:
            if debate_features.shape!=(specialists.shape[0],24) or not torch.isfinite(debate_features).all():raise ValueError('Invalid debate feature schema')
            static = static + self.debate_projection(debate_features)
        context = self.static_selection(static)
        encoded, prior, auxiliary = self.moe(specialists,available)
        selected, selection = self.vsn(encoded,context,prior)
        initial = (self.initial_hidden(context).unsqueeze(0),self.initial_cell(context).unsqueeze(0))
        past, state = self.encoder(selected,initial)
        future_inputs = self.future_projection(known_future)
        future, _ = self.decoder(future_inputs,state)
        local = self.local_norm(torch.cat([selected,future_inputs],1) + self.local_gate(torch.cat([past,future],1)))
        enriched = self.enrichment(local,context)
        attended, attention = self.attention(enriched,selected.shape[1])
        decoder = self.attention_norm(enriched[:,selected.shape[1]:] + self.attention_gate(attended))
        decoder = self.final_norm(local[:,selected.shape[1]:] + self.final_gate(self.positionwise(decoder)))
        ix = torch.tensor(self.cfg.horizons,device=decoder.device)-1
        forecasts = torch.cat([head(decoder[:,ix]) for head in self.task_heads],-1)
        return {'reconstruction':self.reconstruction_head(local[:,:selected.shape[1]]).view(specialists.shape),'predictions':forecasts,'load_balance':auxiliary,'variable_selection':selection,
                'routing':prior,'temporal_attention':attention,'graph_attention':graph_attention,
                'node_embeddings':node_embeddings}
