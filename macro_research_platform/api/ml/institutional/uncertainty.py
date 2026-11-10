"""Split conformal sets/intervals bound to one frozen model and calibration cohort."""
from __future__ import annotations
import math
import numpy as np


class SplitConformal:
    """Binary targets produce label sets, not confidence intervals for p(Y=1).

    Regression targets produce residual prediction intervals. Finite-sample
    marginal coverage requires exchangeable calibration/test scores; arbitrary
    macro time series/regime shifts do not inherit that guarantee. Monitor actual
    delayed-label coverage and abstain when calibration is stale/insufficient.
    """
    def __init__(self, task_types: tuple[str,...], alpha: float = .05, minimum: int = 64,
                 simultaneous: bool = False) -> None:
        if not 0<alpha<1 or minimum<1 or any(t not in ('binary','regression') for t in task_types):
            raise ValueError('Invalid conformal configuration')
        self.types,self.alpha,self.minimum,self.simultaneous = task_types,alpha,minimum,simultaneous
        self.q: np.ndarray | None = None
        self.model_digest: str | None = None

    def fit(self, prediction: np.ndarray, target: np.ndarray, matured: np.ndarray, *, model_digest: str) -> 'SplitConformal':
        p,y,mask = np.asarray(prediction),np.asarray(target),np.asarray(matured,dtype=bool)
        if p.ndim!=3 or p.shape!=y.shape or mask.shape!=p.shape or p.shape[-1]!=len(self.types):
            raise ValueError('Expected [N,H,K] calibration arrays')
        self.q = np.full(p.shape[1:],np.inf)
        self.counts = np.zeros(p.shape[1:],dtype=int)
        alpha = self.alpha/np.prod(p.shape[1:]) if self.simultaneous else self.alpha
        for h in range(p.shape[1]):
            for j,kind in enumerate(self.types):
                valid = mask[:,h,j]&np.isfinite(p[:,h,j])&np.isfinite(y[:,h,j])
                a,b = p[valid,h,j],y[valid,h,j]
                if kind=='binary':
                    if ((a<0)|(a>1)).any() or not np.isin(b,[0,1]).all():
                        raise ValueError('Calibrated binary probabilities and labels required')
                    scores = np.where(b==1,1-a,a)
                else:
                    scores = np.abs(a-b)
                n = len(scores); self.counts[h,j] = n
                rank = math.ceil((n+1)*(1-alpha))
                if n>=self.minimum and rank<=n:
                    self.q[h,j] = np.partition(scores,rank-1)[rank-1]
        self.model_digest = model_digest
        return self

    def predict(self, prediction: np.ndarray, *, model_digest: str) -> dict:
        if self.q is None or self.model_digest!=model_digest:
            raise ValueError('Calibration missing or belongs to different weights')
        p = np.asarray(prediction,dtype=float)
        if p.shape[-2:]!=self.q.shape or not np.isfinite(p).all():
            raise ValueError('Invalid conformal prediction shape/values')
        binary,intervals = {},{}
        for j,kind in enumerate(self.types):
            if kind=='binary':
                if ((p[...,j]<0)|(p[...,j]>1)).any(): raise ValueError('Invalid probabilities')
                binary[j] = np.stack([p[...,j]<=self.q[:,j],1-p[...,j]<=self.q[:,j]],-1)
            else:
                intervals[j] = np.stack([p[...,j]-self.q[:,j],p[...,j]+self.q[:,j]],-1)
        return {'label_sets':binary,'prediction_intervals':intervals,'calibration_counts':self.counts.copy(),
                'insufficient_calibration':~np.isfinite(self.q),'alpha':self.alpha,
                'guarantee':'Marginal under exchangeability; not unconditional time-series probability-interval coverage.'}
