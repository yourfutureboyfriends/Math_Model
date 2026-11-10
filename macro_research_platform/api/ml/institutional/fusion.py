"""Shape-checked heterogeneous fusion for the existing TFT encoder."""
from __future__ import annotations
import torch
from torch import Tensor,nn


class GraphCrossAttentionLayer(nn.Module):
    """TFT queries [B,T,Ht], GAT keys/values [B,N,Hg] -> [B,T,Ht].

    Padding is excluded explicitly. Attention matrices are not returned/stored;
    PyTorch may select its memory-efficient attention kernel. N is bounded.
    """
    def __init__(self,temporal_dim:int,graph_dim:int,heads:int=4,attention_dim:int|None=None,max_nodes:int=256) -> None:
        super().__init__();d=attention_dim or temporal_dim
        if min(temporal_dim,graph_dim,heads,d,max_nodes)<1 or d%heads:raise ValueError('Invalid cross-attention dimensions')
        self.temporal_dim,self.graph_dim,self.max_nodes=temporal_dim,graph_dim,max_nodes
        self.query=nn.Linear(temporal_dim,d) # [B,T,Ht] -> [B,T,D]
        self.key=nn.Linear(graph_dim,d) # [B,N,Hg] -> [B,N,D]
        self.value=nn.Linear(graph_dim,d) # [B,N,Hg] -> [B,N,D]
        self.attention=nn.MultiheadAttention(d,heads,batch_first=True) # Q:[B,T,D], K/V:[B,N,D] -> [B,T,D]
        self.output=nn.Linear(d,temporal_dim) # [B,T,D] -> [B,T,Ht]
        self.norm=nn.LayerNorm(temporal_dim) # [B,T,Ht] -> [B,T,Ht]

    def forward(self,temporal:Tensor,nodes:Tensor,node_mask:Tensor|None=None) -> Tensor:
        if temporal.ndim!=3 or nodes.ndim!=3 or temporal.shape[0]!=nodes.shape[0] or temporal.shape[-1]!=self.temporal_dim or nodes.shape[-1]!=self.graph_dim:
            raise ValueError('Expected temporal [B,T,Ht] and graph [B,N,Hg]')
        if not 1<=nodes.shape[1]<=self.max_nodes or not torch.isfinite(temporal).all() or not torch.isfinite(nodes).all():raise ValueError('Invalid cross-attention values/node count')
        if node_mask is None:node_mask=torch.ones(nodes.shape[:2],dtype=torch.bool,device=nodes.device)
        if node_mask.shape!=nodes.shape[:2] or node_mask.dtype!=torch.bool or not node_mask.any(-1).all():raise ValueError('Every sample needs an unpadded graph node')
        attended,_=self.attention(self.query(temporal),self.key(nodes),self.value(nodes),key_padding_mask=~node_mask,need_weights=False)
        return self.norm(temporal+self.output(attended))


class FiLMModulator(nn.Module):
    """Debate scalars [B,C] -> gamma/beta [B,1,H] -> encoder [B,T,H].

    Identity initialization avoids disturbing a pretrained encoder before new
    conditional inputs receive supervised gradients. Missing features skip FiLM.
    """
    def __init__(self,hidden_dim:int,condition_dim:int=4,mlp_dim:int=32) -> None:
        super().__init__()
        if min(hidden_dim,condition_dim,mlp_dim)<1:raise ValueError('Positive FiLM dimensions required')
        self.hidden_dim,self.condition_dim=hidden_dim,condition_dim
        self.mlp=nn.Sequential(nn.Linear(condition_dim,mlp_dim),nn.GELU(),nn.Linear(mlp_dim,2*hidden_dim)) # [B,C] -> [B,2H]
        nn.init.zeros_(self.mlp[-1].weight);nn.init.zeros_(self.mlp[-1].bias)

    def forward(self,hidden:Tensor,condition:Tensor) -> Tensor:
        if hidden.ndim!=3 or hidden.shape[-1]!=self.hidden_dim or condition.shape!=(hidden.shape[0],self.condition_dim):raise ValueError('FiLM expects [B,T,H] and [B,C]')
        if not torch.isfinite(hidden).all() or not torch.isfinite(condition).all():raise ValueError('Nonfinite FiLM input')
        gamma_delta,beta=self.mlp(condition).chunk(2,-1) # [B,2H] -> two [B,H]
        # gamma = 1 + delta; no per-time tensor expansion allocation.
        return (1+gamma_delta.unsqueeze(1))*hidden+beta.unsqueeze(1)
