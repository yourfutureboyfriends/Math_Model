"""Masked multi-task objectives; uncertainty weights are not probability intervals."""
from __future__ import annotations
import torch
from torch import Tensor,nn
import torch.nn.functional as F


class MultiTaskLoss(nn.Module):
    """Bounded homoscedastic weighting over task/horizon cells.

    Focal classification weighting is a training surrogate, not an exact
    homoscedastic likelihood. Fit probability calibration on separate data.
    Missing labels contribute neither data loss nor uncertainty regularization.
    """
    def __init__(self, task_types: tuple[str,...], horizons: int, focal_tasks: tuple[int,...] = (), gamma: float = 2.) -> None:
        super().__init__()
        if any(t not in ('binary','regression') for t in task_types):
            raise ValueError('Unknown task type')
        self.task_types,self.focal_tasks,self.gamma = task_types,focal_tasks,gamma
        self.raw_log_variance = nn.Parameter(torch.zeros(horizons,len(task_types)))

    def forward(self, prediction: Tensor, target: Tensor, known: Tensor) -> Tensor:
        if prediction.shape != target.shape or known.shape != target.shape:
            raise ValueError('Predictions, targets and known mask must have shape [B,H,K]')
        if not torch.isfinite(prediction).all():
            raise ValueError('Nonfinite predictions')
        mask = known.bool() & torch.isfinite(target)
        y = torch.where(mask,target,torch.zeros_like(target))
        variance = 6*torch.tanh(self.raw_log_variance/6)
        losses = []
        for j,kind in enumerate(self.task_types):
            if kind=='binary':
                if ((y[:,:,j][mask[:,:,j]]!=0)&(y[:,:,j][mask[:,:,j]]!=1)).any():
                    raise ValueError('Binary target must be zero or one')
                loss = F.binary_cross_entropy_with_logits(prediction[:,:,j],y[:,:,j],reduction='none')
                if j in self.focal_tasks:
                    loss = (1-torch.exp(-loss)).pow(self.gamma)*loss
                coefficient = 1.
            else:
                loss = (prediction[:,:,j]-y[:,:,j]).square()
                coefficient = .5
            counts = mask[:,:,j].sum(0)
            average = (loss*mask[:,:,j]).sum(0)/counts.clamp_min(1)
            weighted = coefficient*torch.exp(-variance[:,j])*average + .5*variance[:,j]
            losses.extend(weighted[counts>0].unbind())
        return torch.stack(losses).mean() if losses else prediction.sum()*0
