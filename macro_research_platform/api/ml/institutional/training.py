"""Trainable TFT wrapper and bounded from-scratch training for a drift challenger."""
from __future__ import annotations
from collections.abc import Callable
import time
import numpy as np
import torch
from torch import Tensor,nn
import torch.nn.functional as F
from api.ml.institutional.model import MacroTFT,ModelConfig
from api.ml.institutional.losses import MultiTaskLoss
from api.ml.institutional.continual import Experience
from api.ml.institutional.data import utc


class TrainableMacroSystem(nn.Module):
    """Loss weights are registered parameters and are included in the optimizer."""
    def __init__(self, cfg: ModelConfig, task_types: tuple[str,...], focal_tasks: tuple[int,...] = (0,), balance: float = .01) -> None:
        super().__init__()
        if len(task_types)!=cfg.tasks:
            raise ValueError('Task schema differs from network heads')
        self.network = MacroTFT(cfg)
        self.objective = MultiTaskLoss(task_types,len(cfg.horizons),focal_tasks)
        self.balance,self.task_types = balance,task_types

    def predict(self, tensors: dict[str,Tensor]) -> dict[str,Tensor]:
        device = next(self.parameters()).device
        inputs = {key:tensors[key].to(device) for key in ('specialists','graph_nodes','edge_index','known_future')}
        for optional in ('available','edge_weight','causal_mask','debate_features'):
            if optional in tensors: inputs[optional] = tensors[optional].to(device)
        return self.network(**inputs)

    def loss(self, tensors: dict[str,Tensor], *, fisher_nll: bool = False) -> Tensor:
        out = self.predict(tensors)
        prediction = out['predictions']
        y,known = tensors['target'].to(prediction.device),tensors['known'].to(prediction.device).bool()
        if not fisher_nll:
            return self.objective(prediction,y,known)+self.balance*out['load_balance']
        # Fisher importance uses per-origin unweighted likelihood, not focal or
        # routing-balancing terms. Replay examples must contain B=1.
        if prediction.shape[0]!=1:
            raise ValueError('Fisher callback requires one forecast origin')
        losses = []
        for j,kind in enumerate(self.task_types):
            mask = known[:,:,j]&torch.isfinite(y[:,:,j])
            if mask.any():
                if kind=='binary':
                    losses.append(F.binary_cross_entropy_with_logits(prediction[:,:,j][mask],y[:,:,j][mask]))
                else:
                    losses.append(.5*(prediction[:,:,j][mask]-y[:,:,j][mask]).square().mean())
        if not losses: raise ValueError('No observed targets for Fisher importance')
        return torch.stack(losses).mean()


def fit_from_scratch(factory: Callable[[],nn.Module], train: list[Experience], validation: list[Experience],
                     loss_fn: Callable[[nn.Module,dict[str,Tensor]],Tensor], *, cutoff: str,
                     embargo_days: int = 30, epochs: int = 50, patience: int = 5,
                     learning_rate: float = .001, maximum_seconds: float = 300., seed: int = 0) -> tuple[nn.Module,dict]:
    """Fresh model/optimizer, chronological holdout, no EWC carry-over on reset.

    Preprocessing/feature/link estimation must already have been fitted on train
    only. Calibration and final evaluation cohorts must remain disjoint.
    """
    import pandas as pd
    if not train or not validation or epochs<1 or patience<1 or maximum_seconds<=0:
        raise ValueError('Nonempty, bounded training/validation cohorts required')
    first_validation = min(utc(e.origin) for e in validation)-pd.Timedelta(days=embargo_days)
    if any(utc(e.label_known_at)>=first_validation for e in train):
        raise ValueError('Training labels overlap the purged validation boundary')
    if any(utc(e.label_known_at)>utc(cutoff) for e in train+validation):
        raise ValueError('Future training/validation labels')
    if len({e.feature_schema for e in train+validation})!=1 or {e.id for e in train}&{e.id for e in validation}:
        raise ValueError('Schema/cohort contamination')
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = factory()
    optimizer = torch.optim.AdamW(model.parameters(),lr=learning_rate,weight_decay=.001)
    started = time.monotonic()
    best,best_state,bad = float('inf'),None,0
    for epoch in range(epochs):
        model.train()
        for index in rng.permutation(len(train)):
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model,train[int(index)].tensors)
            if loss.ndim or not torch.isfinite(loss): raise FloatingPointError('Invalid full-training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True)
            optimizer.step()
            if time.monotonic()-started>maximum_seconds: break
        model.eval()
        with torch.no_grad():
            score = float(torch.stack([loss_fn(model,e.tensors) for e in validation]).mean())
        if not np.isfinite(score): raise FloatingPointError('Invalid validation loss')
        if score<best:
            best,bad = score,0
            best_state = {k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
        else: bad += 1
        if bad>=patience or time.monotonic()-started>maximum_seconds: break
    if best_state is None: raise RuntimeError('No validated full-training checkpoint')
    model.load_state_dict(best_state)
    model.eval()
    return model,{'epochs':epoch+1,'validation_objective':best,'runtime_seconds':time.monotonic()-started,'seed':seed}
