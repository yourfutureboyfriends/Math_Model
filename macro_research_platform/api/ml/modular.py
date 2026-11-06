"""Feature routing and modular sequence architecture. Torch is imported only in the worker."""
from __future__ import annotations

CORE_GROUPS = {
    'rates_credit': {'ts','ntfs','ebp','baa','y10','y10_d3','ff'},
    'real_economy': {'pay6','unemp_d6','cpi_yoy','cpi_d3','sent_d6'},
    'market_prices': {'spx6','spx_vol3','oil6','usd6'},
}
STAGES = [
    {'name':'Observe','detail':'Existing FRED, market-price and news feeds; publication lags and missing-data checks.'},
    {'name':'Prepare','detail':'Training-only normalization and macro factors; chronological label-horizon purge.'},
    {'name':'Specialize','detail':'Separate rates/credit, economy, market, factor and news encoders.'},
    {'name':'Combine','detail':'Learned routing weights combine specialist representations before temporal memory.'},
    {'name':'Forecast','detail':'Past-only recurrent memory, temporal attention and separate task heads.'},
    {'name':'Evaluate & learn','detail':'Score matured outcomes, refit changed data, preserve versioned evidence and promotion gates.'},
]


def feature_groups(core_keys, n_factors, text_keys):
    groups={}
    for i,key in enumerate(core_keys):
        name=next((g for g,keys in CORE_GROUPS.items() if key in keys),'other_core')
        groups.setdefault(name,[]).append(i)
    offset=len(core_keys)
    if n_factors:groups['macro_factors']=list(range(offset,offset+n_factors))
    offset+=n_factors
    if text_keys:
        from api.ml.context import SPECS
        for i,key in enumerate(text_keys):
            group=SPECS[key][2] if key in SPECS else 'news'
            groups.setdefault(group,[]).extend([offset+i,offset+len(text_keys)+i])
    return groups


def validate_groups(groups, d_in):
    indices=[i for values in groups.values() for i in values]
    if not groups or any(not v for v in groups.values()) or sorted(indices)!=list(range(d_in)):
        raise ValueError('Every input must belong to exactly one nonempty specialist module')
    return {str(k):list(v) for k,v in groups.items()}


def make_network(d_in,d_out,cfg,groups=None):
    import torch
    from torch import nn
    groups=validate_groups(groups or {'combined_inputs':list(range(d_in))},d_in)
    width=max(8,cfg.hidden//4)
    class ModularSequence(nn.Module):
        def __init__(self):
            super().__init__()
            self.groups=groups
            self.encoders=nn.ModuleDict({name:nn.Sequential(nn.Linear(len(ix),width),nn.LayerNorm(width),nn.GELU(),nn.Dropout(cfg.dropout)) for name,ix in groups.items()})
            self.router=nn.Linear(width,1)
            self.fusion=nn.Sequential(nn.Linear(width*len(groups)+width,cfg.hidden),nn.LayerNorm(cfg.hidden),nn.GELU())
            self.gru=nn.GRU(cfg.hidden,cfg.hidden,num_layers=cfg.layers,batch_first=True,dropout=cfg.dropout if cfg.layers>1 else 0.)
            self.attention=nn.MultiheadAttention(cfg.hidden,cfg.attention_heads,dropout=cfg.dropout,batch_first=True) if cfg.attention_heads else None
            self.norm=nn.LayerNorm(cfg.hidden)
            self.heads=nn.ModuleList([nn.Sequential(nn.Linear(cfg.hidden,max(8,cfg.hidden//4)),nn.GELU(),nn.Dropout(cfg.dropout),nn.Linear(max(8,cfg.hidden//4),1)) for _ in range(d_out)])
        def encode(self,x):
            pieces=torch.stack([self.encoders[name](x[:,:,ix]) for name,ix in self.groups.items()],dim=2)
            weights=torch.softmax(self.router(pieces).squeeze(-1),dim=-1)
            pooled=(pieces*weights[:,:,:,None]).sum(2)
            fused=self.fusion(torch.cat([pieces.flatten(2),pooled],dim=-1))
            return fused,weights
        def forward(self,x):
            fused,_=self.encode(x);h,_=self.gru(fused);last=h[:,-1:]
            if self.attention is not None:
                context,_=self.attention(last,h,h,need_weights=False);last=last+context
            z=self.norm(last[:,0])
            return torch.cat([head(z) for head in self.heads],dim=1)
        def trace(self,x):
            """Measured states; prefix predictions use no later states within the window."""
            with torch.no_grad():
                fused,weights=self.encode(x);h,_=self.gru(fused)
                pieces=torch.stack([self.encoders[name](x[:,:,ix]) for name,ix in self.groups.items()],dim=2)
                outputs=[];attention=[]
                for step in range(h.shape[1]):
                    last=h[:,step:step+1]
                    if self.attention is not None:
                        context,att=self.attention(last,h[:,:step+1],h[:,:step+1],need_weights=True)
                        last=last+context;attention.append(att[0,0].cpu().tolist())
                    else:attention.append([])
                    z=self.norm(last[:,0]);outputs.append(torch.sigmoid(torch.cat([head(z) for head in self.heads],dim=1))[0].cpu().tolist())
                return {'routing':weights[0].cpu().tolist(),'module_rms':pieces[0].square().mean(-1).sqrt().cpu().tolist(),
                        'hidden':h[0,:,:min(12,h.shape[-1])].cpu().tolist(),'memory_rms':h[0].square().mean(-1).sqrt().cpu().tolist(),
                        'attention':attention,'probabilities':outputs,'modules':list(self.groups)}
        def routing(self,x):
            # Descriptive weights, not causal importance or investment allocations.
            with torch.no_grad():
                _,weights=self.encode(x)
                return {name:float(weights[:,-1,i].mean()) for i,name in enumerate(self.groups)}
    return ModularSequence()
