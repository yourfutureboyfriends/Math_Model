"""EWC-DR binary adaptation, population-proportional regime replay and updates."""
from __future__ import annotations
import sqlite3
from typing import Callable
import numpy as np
import torch
from torch import Tensor,nn
import torch.nn.functional as F
from api.ml.institutional.continual import EWC,Experience,ReplayBuffer
from api.ml.institutional.data import utc


class EWCDRLoss(EWC):
    """Logits-reversal importance, adapted to masked independent Bernoulli heads.

    The cited method was evaluated in classification, not macro forecasting.
    Importance uses BCE(-z,y); ordinary training continues to use BCE(z,y).
    This is a surrogate importance measure, not the likelihood's true Fisher.
    """
    @classmethod
    def estimate(cls, model: nn.Module, examples: list[Experience], max_examples: int = 128) -> 'EWCDRLoss':
        """Accumulate squared per-origin gradients without stepping the optimizer."""
        if max_examples<1:raise ValueError('Positive importance budget required')
        def reversed_loss(system: nn.Module, batch: dict[str,Tensor]) -> Tensor:
            logits=system.predict(batch)['predictions']
            if logits.shape[0]!=1:raise ValueError('Importance requires per-origin examples')
            y=batch['target'].to(logits);known=batch['known'].to(logits.device).bool()&torch.isfinite(y)
            if not known.any():raise ValueError('Observed labels required for importance')
            if ((y[known]!=0)&(y[known]!=1)).any():raise ValueError('EWC-DR adapter supports binary heads only')
            # Omega_i = (1/N) sum_n [d BCE(-z_n,y_n)/d theta_i]^2.
            return F.binary_cross_entropy_with_logits(-logits[known],y[known])
        from api.ml.institutional.pcgrad import is_shared_parameter
        named=dict(model.named_parameters());shared=[(k,p) for k,p in named.items() if p.requires_grad and is_shared_parameter(k)]
        if not shared:raise ValueError('No shared backbone parameters')
        # Private entries are zero placeholders only for legacy bundle compatibility.
        anchor={k:p.detach().clone() for k,p in named.items()};fisher={k:torch.zeros_like(p) for k,p in named.items()}
        previous=model.training;model.eval();count=0
        try:
            for item in examples[:max_examples]:
                loss=reversed_loss(model,item.tensors)
                if not torch.isfinite(loss):raise FloatingPointError('Invalid reversed-logit objective')
                gradients=torch.autograd.grad(loss,[p for _,p in shared],allow_unused=True)
                for (name,_),gradient in zip(shared,gradients):
                    if gradient is not None:fisher[name]+=gradient.detach().square()
                count+=1
        finally:model.train(previous)
        if not count:raise ValueError('Observed importance examples required')
        return cls(model,{k:v/count for k,v in fisher.items()},anchor)


class StratifiedRegimeReplayBuffer(ReplayBuffer):
    """Durable equal-capacity strata, sampled using full eligible regime prevalence.

    Counts include evicted records through an immutable ID ledger. Allocation is
    proportional to eligible history, not the balanced storage capacity. Regime
    tags must be computed with information available at the origin, never labels.
    """
    def __init__(self,*args,**kwargs) -> None:
        super().__init__(*args,**kwargs)
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE IF NOT EXISTS regime_population(id TEXT PRIMARY KEY,known TEXT,schema TEXT,stratum TEXT)')

    def add(self,item:Experience,*,cutoff:str) -> None:
        if utc(item.label_known_at)>utc(cutoff):raise ValueError('Future regime example')
        super().add(item,cutoff=cutoff)
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT OR IGNORE INTO regime_population VALUES(?,?,?,?)',(item.id,utc(item.label_known_at).isoformat(),item.feature_schema,item.stratum))

    def sample(self,count:int,*,cutoff:str,schema:str,seed:int=0,exclude:set[str]|None=None) -> list[Experience]:
        if count<0:raise ValueError('Negative replay count')
        candidates=super().sample(self.capacity,cutoff=cutoff,schema=schema,seed=seed,exclude=exclude)
        with sqlite3.connect(self.path) as c:
            counts=dict(c.execute('SELECT stratum,COUNT(*) FROM regime_population WHERE known<=? AND schema=? GROUP BY stratum',(utc(cutoff).isoformat(),schema)))
        groups:dict[str,list[Experience]]={}
        for item in candidates:groups.setdefault(item.stratum,[]).append(item)
        if not groups or not count:return []
        names=sorted(groups);weights=np.array([counts.get(name,len(groups[name])) for name in names],float);weights/=weights.sum()
        rng=np.random.default_rng(seed)
        # Replacement preserves prevalence when a rare regime has small storage.
        return [groups[names[int(i)]][int(rng.integers(len(groups[names[int(i)]])))] for i in rng.choice(len(names),size=count,p=weights)]


def continual_training_step(model:nn.Module,optimizer:torch.optim.Optimizer,new_batch:dict[str,Tensor],
                            replay_batches:list[dict[str,Tensor]],ewc: EWC|None,
                            *,replay_weight:float=.75,ewc_strength:float=10.) -> dict[str,float]:
    """One challenger step: L=(1-r)L_new+r mean(L_replay)+lambda L_EWC.

    Input eligibility/PIT checks remain mandatory at the replay/worker boundary.
    Unknown labels are masked by the existing multi-task objective.
    """
    from api.ml.institutional.pcgrad import continual_train_step
    return continual_train_step(model,optimizer,new_batch,replay_batches,ewc,replay_weight=replay_weight,ewc_strength=ewc_strength)
