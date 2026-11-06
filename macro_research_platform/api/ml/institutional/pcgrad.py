"""Automatic six-task PCGrad on shared parameters, with private-head gradients."""
from __future__ import annotations
from collections.abc import Callable
import torch
from torch import Tensor,nn
import torch.nn.functional as F
from api.ml.institutional.continual import EWC


def is_shared_parameter(name:str) -> bool:
    """Task heads, uncertainty weights and reconstruction head are private."""
    return not any(part in name for part in ('task_heads.','objective.','reconstruction_head.','task_weighting.'))


def project_conflicts(gradients:Tensor,*,generator:torch.Generator|None=None) -> Tensor:
    """PCGrad [active_tasks,P] -> shared gradient [P], O(tasks*P) memory.

    g_i <- g_i - min(dot(g_i,g_j),0)/||g_j||² * g_j.
    Peers are original task gradients, not previously projected peer gradients.
    """
    if gradients.ndim!=2 or not torch.isfinite(gradients).all():raise ValueError('Finite task gradient matrix required')
    result=gradients.clone();tasks=len(result)
    for i in range(tasks):
        for j in torch.randperm(tasks,generator=generator,device='cpu').tolist():
            if i==j:continue
            dot=torch.dot(result[i],gradients[j]);norm=gradients[j].square().sum()
            if dot<0 and norm>1e-12:result[i].sub_(dot/norm*gradients[j])
    return result.mean(0)


def task_objectives(model:nn.Module,batch:dict[str,Tensor]) -> tuple[dict[int,Tensor],Tensor]:
    """Existing bounded homoscedastic objective, split into six masked head losses.

    [B,H,6] logits/labels; existing log sigma² parameters [H,6] are learned only
    for observed cells. BCE/focal/regression semantics stay in the shared loss.
    """
    out=model.predict(batch);prediction=out['predictions']
    if prediction.ndim!=3 or prediction.shape[-1]!=6:raise ValueError('Six macroeconomic heads required')
    y=batch['target'].to(prediction);known=batch['known'].to(prediction.device).bool()
    if y.shape!=prediction.shape or known.shape!=prediction.shape:raise ValueError('Target tensors must match [B,H,6]')
    known=known&torch.isfinite(y)
    losses={}
    for j in range(6):
        if known[:,:,j].any():
            selected=torch.zeros_like(known);selected[:,:,j]=known[:,:,j]
            # exp(-s)*L + .5*s, s=6*tanh(raw_log_variance/6).
            losses[j]=model.objective(prediction,y,selected)
    return losses,model.balance*out['load_balance']


def continual_train_step(model:nn.Module,optimizer:torch.optim.Optimizer,new_batch:dict[str,Tensor],
                         replay_batches:list[dict[str,Tensor]]|None=None,ewc:EWC|None=None,*,
                         replay_weight:float=.75,ewc_strength:float=10.,max_gradient_bytes:int=256*1024*1024,
                         seed:int=1729) -> dict[str,float]:
    """One atomic challenger update; PCGrad shared trunk, ordinary private heads.

    EWC is applied only to the shared backbone, even for legacy anchors containing
    head entries. Projection excludes heads and uncertainty parameters. All
    gradient buffers are bounded before forward/autograd allocations start.
    No optimizer step occurs if gradients/losses are nonfinite or schema-invalid.
    """
    if not 0<=replay_weight<=1 or ewc_strength<0:raise ValueError('Invalid continual loss weights')
    named=[(name,p) for name,p in model.named_parameters() if p.requires_grad]
    shared=[(name,p) for name,p in named if is_shared_parameter(name)];private=[(name,p) for name,p in named if not is_shared_parameter(name)]
    if not shared or any(p.dtype!=torch.float32 for _,p in named):raise ValueError('PCGrad requires an FP32 shared backbone; unscaled AMP gradients are not accepted')
    if len({p.device for _,p in named})!=1:raise ValueError('Single-device challenger required')
    parameters=[p for _,p in shared];sizes=[p.numel() for p in parameters];total=sum(sizes)
    if total*(3*6+3)*4>max_gradient_bytes:raise MemoryError('PCGrad gradient budget exceeded; reduce model size or train on an appropriately provisioned worker')
    optimized={id(p) for group in optimizer.param_groups for p in group['params']}
    if any(id(p) not in optimized for _,p in named):raise ValueError('Optimizer is missing model/uncertainty parameters')
    batches=[new_batch]+list(replay_batches or [])
    if len(batches)>9 or any(b['specialists'].shape[0]>32 or b['specialists'].shape[1]>256 for b in batches):raise MemoryError('Continual activation batch budget exceeded')
    if sum(t.numel()*t.element_size() for b in batches for t in b.values())>64*1024*1024:raise MemoryError('Continual input byte budget exceeded')
    model.train();optimizer.zero_grad(set_to_none=True)
    fresh,aux=task_objectives(model,new_batch)
    if not fresh:raise ValueError('At least one observed task is required')
    history:dict[int,list[Tensor]]={}
    for batch in replay_batches or []:
        terms,extra=task_objectives(model,batch);aux=aux+extra/(len(replay_batches or [])+1)
        for j,loss in terms.items():history.setdefault(j,[]).append(loss)
    tasks={}
    for j in sorted(set(fresh)|set(history)):
        if j in fresh and j in history:tasks[j]=(1-replay_weight)*fresh[j]+replay_weight*torch.stack(history[j]).mean()
        else:tasks[j]=fresh[j] if j in fresh else torch.stack(history[j]).mean()
    if any(not torch.isfinite(loss) for loss in tasks.values()):raise FloatingPointError('Nonfinite task objective')
    original=[]
    for loss in tasks.values():
        grads=torch.autograd.grad(loss,parameters,retain_graph=True,allow_unused=True)
        original.append(torch.cat([torch.zeros_like(p).flatten() if g is None else g.detach().flatten() for p,g in zip(parameters,grads)]))
    matrix=torch.stack(original);del original
    merged=project_conflicts(matrix,generator=torch.Generator().manual_seed(seed));del matrix
    regularizer=next(iter(tasks.values()))*0
    if ewc is not None:
        terms=[]
        for name,p in shared:
            if name not in ewc.fisher or ewc.fisher[name].shape!=p.shape:raise ValueError('Shared EWC schema mismatch')
            terms.append((ewc.fisher[name].to(p)*(p-ewc.anchor[name].to(p)).square()).sum())
        regularizer=.5*sum(terms)
    auxiliary=aux+ewc_strength*regularizer
    extras=torch.autograd.grad(auxiliary,parameters,retain_graph=True,allow_unused=True)
    objective=torch.stack(list(tasks.values())).mean()+auxiliary
    private_parameters=[p for _,p in private]
    private_grads=torch.autograd.grad(objective,private_parameters,allow_unused=True) if private_parameters else []
    offset=0
    for p,size,extra in zip(parameters,sizes,extras):
        p.grad=merged[offset:offset+size].view_as(p).clone()
        if extra is not None:p.grad.add_(extra.detach())
        offset+=size
    for p,grad in zip(private_parameters,private_grads):p.grad=None if grad is None else grad.detach()
    nn.utils.clip_grad_norm_([p for _,p in named],1.,error_if_nonfinite=True)
    optimizer.step()
    return {'loss':float(objective.detach()),'ewc':float(regularizer.detach()),'active_tasks':float(len(tasks)),'pcgrad':1.}
