"""Bounded System 2 VAR-Lasso updates; positive lags produce a temporal DAG."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler
import torch
from torch import Tensor
from api.ml.institutional.causal import LaggedStructure
from api.ml.institutional.data import utc
from api.ml.live import _write


class IncrementalCausalUpdater:
    """Sliding-window VAR-Lasso and EMA in consistent original variable units.

    Only observed numeric economic nodes are accepted, not provenance/model
    nodes. Lasso associations are conditional predictive hypotheses. Full PCMCI
    is not called. No arbitrary cycle deletion is applied to lagged feedback.
    """
    def __init__(self,node_ids:tuple[str,...],*,lags:int=2,window:int=252,penalty:float=.05,
                 ema_alpha:float=.2,threshold:float=1e-5,max_iterations:int=500,state_path:Path|None=None) -> None:
        if not node_ids or len(set(node_ids))!=len(node_ids) or any(not n.startswith('feature:') for n in node_ids):raise ValueError('Unique observed feature node IDs required')
        if not 1<=lags<=3 or window<max(40,5*lags) or len(node_ids)*(lags+1)>256:raise ValueError('VAR window/expanded graph exceeds budget')
        if not 0<ema_alpha<=1 or penalty<=0 or threshold<=0 or not 1<=max_iterations<=5000:raise ValueError('Invalid VAR regularization/EMA bounds')
        self.node_ids,self.lags,self.window=node_ids,lags,window
        self.penalty,self.alpha,self.threshold,self.iterations=penalty,ema_alpha,threshold,max_iterations
        n=len(node_ids);self.coefficients=np.zeros((lags,n,n));self.adjacency=np.zeros_like(self.coefficients);self.intercept=np.zeros(n)
        self.fitted_through:str|None=None;self.signature:str|None=None;self.path=state_path
        if state_path is not None and state_path.exists():
            r=json.loads(state_path.read_text())
            if r['configuration']!=self.configuration():raise ValueError('Incompatible incremental graph configuration')
            for name in ('coefficients','adjacency','intercept'):
                value=np.asarray(r[name],float)
                if value.shape!=getattr(self,name).shape or not np.isfinite(value).all():raise ValueError('Invalid saved VAR tensor')
                setattr(self,name,value)
            self.fitted_through,self.signature=r['fitted_through'],r['signature']

    def configuration(self) -> dict[str,object]:
        return {'nodes':list(self.node_ids),'lags':self.lags,'window':self.window,'penalty':self.penalty,'ema_alpha':self.alpha,'threshold':self.threshold,'max_iterations':self.iterations}

    def update(self,frame:pd.DataFrame,*,cutoff:datetime|str) -> LaggedStructure:
        """Fit train-only standardized windows, convert back to physical units, EMA.

        B_new = alpha*B_lasso + (1-alpha)*B_old;
        A_new = alpha*abs(B_lasso) + (1-alpha)*A_old.
        Callers must supply PIT-aligned/stationary observations already known at
        cutoff. A period timestamp alone is not evidence of historical receipt.
        """
        if tuple(frame.columns)!=self.node_ids or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:raise ValueError('VAR column/time schema mismatch')
        times=pd.to_datetime(frame.index)
        if times.tz is None:raise ValueError('VAR observations need explicit timezones')
        now=utc(cutoff)
        if self.fitted_through is not None and now<utc(self.fitted_through):raise ValueError('Backdated graph update rejected')
        train=frame.loc[times<=now].tail(self.window)
        x=train.to_numpy(dtype=np.float64)
        if len(x)<40 or not np.isfinite(x).all() or (x.std(0)<1e-8).any():raise ValueError('Insufficient finite, nonconstant VAR history')
        signature=hashlib.sha256(x.tobytes()+str(list(train.index)).encode()).hexdigest()
        if signature!=self.signature:
            scaler=StandardScaler().fit(x);z=scaler.transform(x);n=len(self.node_ids)
            design=np.concatenate([z[self.lags-lag:len(z)-lag] for lag in range(1,self.lags+1)],1) # [T-L,L*N]
            beta=np.zeros_like(self.coefficients);bias=np.zeros(n)
            for destination in range(n):
                fit=Lasso(alpha=self.penalty,max_iter=self.iterations,tol=1e-4,selection='cyclic').fit(design,z[self.lags:,destination])
                if fit.n_iter_>=self.iterations:raise RuntimeError('VAR-Lasso did not converge within its iteration budget')
                scaled=fit.coef_.reshape(self.lags,n)
                beta[:,destination,:]=scaled*scaler.scale_[destination]/scaler.scale_[None,:]
                bias[destination]=scaler.mean_[destination]+scaler.scale_[destination]*fit.intercept_-(beta[:,destination,:]*scaler.mean_[None,:]).sum()
            # First update also uses alpha against the documented zero prior.
            self.coefficients=self.alpha*beta+(1-self.alpha)*self.coefficients
            self.adjacency=self.alpha*np.abs(beta)+(1-self.alpha)*self.adjacency
            self.adjacency[self.adjacency<self.threshold]=0.
            self.coefficients=np.where(self.adjacency>0,self.coefficients,0.)
            self.intercept=self.alpha*bias+(1-self.alpha)*self.intercept
            self.signature=signature;self.fitted_through=now.isoformat()
            if self.path is not None:_write(self.path,{'configuration':self.configuration(),'coefficients':self.coefficients.tolist(),
                'adjacency':self.adjacency.tolist(),'intercept':self.intercept.tolist(),'signature':signature,'fitted_through':self.fitted_through})
        edges=tuple((int(i),int(j),int(lag+1)) for lag,j,i in np.argwhere(self.adjacency>0))
        return LaggedStructure(self.node_ids,edges,self.coefficients.copy(),self.intercept.copy(),self.fitted_through or now.isoformat(),self.lags)

    def graph_tensors(self,history:Tensor) -> dict[str,Tensor]:
        """[L+1,N] physical observations -> time-expanded GAT input [1,(L+1)N,20].

        Attention mask is [destination,source]. Every edge points from an earlier
        time slice to a later one, including valid reciprocal economic feedback.
        """
        n=len(self.node_ids);count=(self.lags+1)*n
        if self.fitted_through is None or history.shape!=(self.lags+1,n) or not torch.isfinite(history).all():raise ValueError('Fitted VAR and matching finite history required')
        nodes=torch.zeros(1,count,20,dtype=torch.float32);nodes[:,:,0]=1.
        nodes[0,:,17]=history.detach().float().cpu().flatten().clamp(-10,10)
        mask=torch.zeros(count,count,dtype=torch.bool);weights=[];edges=[]
        for lag,j,i in np.argwhere(self.adjacency>0):
            lag=int(lag)+1
            for t in range(lag,self.lags+1):
                source=(t-lag)*n+int(i);destination=t*n+int(j)
                mask[destination,source]=True;edges.append((source,destination));weights.append(float(self.adjacency[lag-1,j,i]))
        return {'graph_nodes':nodes,'edge_index':torch.tensor(edges,dtype=torch.long).reshape(-1,2).T.contiguous(),
                'edge_weight':torch.tensor(weights,dtype=torch.float32),'causal_mask':mask}
