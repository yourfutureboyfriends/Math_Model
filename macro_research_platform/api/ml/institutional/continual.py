"""Daily fine-tuning primitives: durable stratified replay and diagonal empirical EWC."""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import sqlite3
from typing import Callable,Iterable
import numpy as np
import torch
from torch import Tensor,nn
from api.ml.institutional.data import utc


@dataclass
class Experience:
    id: str
    origin: str
    label_known_at: str
    feature_schema: str
    stratum: str  # Fixed ex-ante regime/event label, computed using eligible information.
    tensors: dict[str,Tensor]

    def __post_init__(self) -> None:
        if utc(self.origin)>utc(self.label_known_at):
            raise ValueError('Label availability precedes its forecast origin')
        if 'target' in self.tensors:
            if 'known' not in self.tensors or not (self.tensors['known'].bool() & torch.isfinite(self.tensors['target'])).any():
                raise ValueError('A supervised experience needs an observed target cell')


class ReplayBuffer:
    """Bounded durable examples, stratified over observed strata.

    Records are immutable. A changed label vintage requires a new ID. Only
    matured labels can be inserted/sampled; schema versions never mix.
    Untrusted checkpoints/pickle are not loaded (weights_only tensor payloads).
    Capacity retention uses deterministic random priorities, not latest-only FIFO.
    """
    def __init__(self, path: Path, capacity: int = 10_000) -> None:
        if capacity<1:
            raise ValueError('Positive replay capacity required')
        self.path,self.capacity = path,capacity
        path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS replay(id TEXT PRIMARY KEY, origin TEXT, known TEXT,
                schema TEXT, stratum TEXT, priority REAL, payload BLOB)''')

    def add(self, item: Experience, *, cutoff: str) -> None:
        import hashlib
        if not utc(item.origin)<=utc(item.label_known_at)<=utc(cutoff):
            raise ValueError('Immature or future replay example')
        if not item.tensors or any(not isinstance(v,Tensor) for v in item.tensors.values()):
            raise ValueError('Replay stores tensors only')
        stream = BytesIO()
        torch.save({k:v.detach().cpu() for k,v in item.tensors.items()},stream)
        priority = int(hashlib.sha256(item.id.encode()).hexdigest()[:13],16)/16**13
        with sqlite3.connect(self.path,timeout=30) as c:
            c.execute('INSERT OR IGNORE INTO replay VALUES(?,?,?,?,?,?,?)',
                      (item.id,utc(item.origin).isoformat(),utc(item.label_known_at).isoformat(),item.feature_schema,item.stratum,priority,stream.getvalue()))
            # Reserve capacity equally across strata; selection is reproducible.
            strata = [r[0] for r in c.execute('SELECT DISTINCT stratum FROM replay ORDER BY stratum')]
            if len(strata)>self.capacity:
                raise ValueError('More strata than replay capacity')
            for i,stratum in enumerate(strata):
                quota = self.capacity//len(strata) + int(i<self.capacity%len(strata))
                c.execute('DELETE FROM replay WHERE id IN (SELECT id FROM replay WHERE stratum=? ORDER BY priority,id LIMIT -1 OFFSET ?)',(stratum,quota))

    def sample(self, count: int, *, cutoff: str, schema: str, seed: int = 0, exclude: set[str] | None = None) -> list[Experience]:
        if count<0:
            raise ValueError('Invalid replay sample count')
        with sqlite3.connect(self.path) as c:
            rows = c.execute('SELECT id,origin,known,schema,stratum,payload FROM replay WHERE known<=? AND origin<=? AND schema=? ORDER BY id',
                             (utc(cutoff).isoformat(),utc(cutoff).isoformat(),schema)).fetchall()
        groups: dict[str,list] = {}
        for row in rows:
            if row[0] not in (exclude or set()):
                groups.setdefault(row[4],[]).append(row)
        rng = np.random.default_rng(seed)
        for values in groups.values():
            rng.shuffle(values)
        picked = []
        while groups and len(picked)<count:
            for stratum in sorted(list(groups)):
                if len(picked)>=count: break
                picked.append(groups[stratum].pop())
                if not groups[stratum]: del groups[stratum]
        return [Experience(*row[:5],torch.load(BytesIO(row[5]),map_location='cpu',weights_only=True)) for row in picked]


class EWC:
    """Diagonal empirical Fisher from per-example supervised gradients.

    Keep preprocessing/schema frozen for a fine-tune. A schema change or drift
    full reset requires a fresh EWC estimate; no parameter-name partial matches.
    """
    def __init__(self, model: nn.Module, fisher: dict[str,Tensor], anchor: dict[str,Tensor]) -> None:
        if any(not torch.isfinite(v).all() or (v<0).any() for v in fisher.values()) or any(not torch.isfinite(v).all() for v in anchor.values()):
            raise ValueError('Invalid Fisher/anchor values')
        self.fisher,self.anchor = fisher,anchor
        current = dict(model.named_parameters())
        if set(current)!=set(fisher) or set(current)!=set(anchor):
            raise ValueError('EWC parameter schema mismatch')
        if any(current[k].shape!=fisher[k].shape or current[k].shape!=anchor[k].shape for k in current):
            raise ValueError('EWC parameter shape mismatch')

    @classmethod
    def estimate(cls, model: nn.Module, examples: Iterable[Experience],
                 supervised_loss: Callable[[nn.Module,dict[str,Tensor]],Tensor], max_examples: int = 256) -> 'EWC':
        anchor = {k:p.detach().clone() for k,p in model.named_parameters()}
        fisher = {k:torch.zeros_like(p) for k,p in model.named_parameters()}
        mode = model.training
        model.eval()
        count = 0
        try:
            for item in examples:
                if count>=max_examples: break
                model.zero_grad(set_to_none=True)
                loss = supervised_loss(model,item.tensors)
                if loss.ndim or not torch.isfinite(loss):
                    raise ValueError('Finite scalar per-example Fisher loss required')
                loss.backward()
                for name,p in model.named_parameters():
                    if p.grad is not None: fisher[name] += p.grad.detach().square()
                count += 1
        finally:
            model.zero_grad(set_to_none=True)
            model.train(mode)
        if count==0:
            raise ValueError('No matured observations for Fisher estimate')
        return cls(model,{k:v/count for k,v in fisher.items()},anchor)

    def save(self, path: Path, *, feature_schema: str, anchor_model_digest: str) -> None:
        """Save alongside an immutable artifact bundle; tensor-only safe reload."""
        import os,tempfile
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            torch.save({'fisher':{k:v.cpu() for k,v in self.fisher.items()},
                        'anchor':{k:v.cpu() for k,v in self.anchor.items()},
                        'feature_schema':feature_schema,'anchor_model_digest':anchor_model_digest},f)
            f.flush();os.fsync(f.fileno());name=f.name
        try:os.link(name,path)
        finally:os.unlink(name)

    @classmethod
    def load(cls, model: nn.Module, path: Path, *, feature_schema: str) -> 'EWC':
        payload = torch.load(path,map_location='cpu',weights_only=True)
        if payload['feature_schema']!=feature_schema:
            raise ValueError('EWC feature schema mismatch')
        return cls(model,payload['fisher'],payload['anchor'])

    def penalty(self, model: nn.Module) -> Tensor:
        parameters = dict(model.named_parameters())
        if set(parameters)!=set(self.anchor):
            raise ValueError('Changed architecture cannot reuse EWC')
        return .5*sum((self.fisher[k].to(p.device)*(p-self.anchor[k].to(p.device)).square()).sum()
                      for k,p in parameters.items())


@dataclass(frozen=True)
class FineTuneConfig:
    steps: int = 20
    learning_rate: float = 1e-5
    replay_per_new: int = 3
    ewc_strength: float = 10.
    load_balance_strength: float = .01
    gradient_clip: float = 1.


def daily_fine_tune(model: nn.Module, new: list[Experience], replay: ReplayBuffer,
                    loss_fn: Callable[[nn.Module,dict[str,Tensor]],Tensor], *, cutoff: str,
                    schema: str, ewc: EWC | None, config: FineTuneConfig = FineTuneConfig(),
                    seed: int = 0) -> dict:
    """Mutates a challenger copy only; never the serving model. No pseudo-labels.

    loss_fn handles masked targets and MoE balancing; Fisher callbacks must use
    supervised loss only. Per-example optimization accommodates varying graph N.
    """
    if not new:
        return {'status':'skipped_no_new_matured_labels','steps':0}
    if config.steps<1 or config.learning_rate<=0 or config.replay_per_new<0 or config.ewc_strength<0:
        raise ValueError('Invalid fine-tuning configuration')
    if any(e.feature_schema!=schema or utc(e.label_known_at)>utc(cutoff) or utc(e.origin)>utc(cutoff) for e in new):
        raise ValueError('Ineligible new observations')
    historical = replay.sample(len(new)*config.replay_per_new,cutoff=cutoff,schema=schema,seed=seed,exclude={e.id for e in new})
    examples = new+historical
    rng = np.random.default_rng(seed)
    optimizer = torch.optim.AdamW(model.parameters(),lr=config.learning_rate,weight_decay=.001)
    model.train()
    losses = []
    for _ in range(config.steps):
        item = examples[int(rng.integers(len(examples)))]
        optimizer.zero_grad(set_to_none=True)
        loss = loss_fn(model,item.tensors)
        if ewc is not None: loss = loss+config.ewc_strength*ewc.penalty(model)
        if loss.ndim or not torch.isfinite(loss):
            raise FloatingPointError('Nonfinite/scalar continual loss')
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),config.gradient_clip,error_if_nonfinite=True)
        optimizer.step()
        if any(not torch.isfinite(p).all() for p in model.parameters()):
            raise FloatingPointError('Nonfinite fine-tuned weights')
        losses.append(float(loss.detach()))
    model.eval()
    for item in new: replay.add(item,cutoff=cutoff)
    return {'status':'fine_tuned','steps':config.steps,'new':len(new),'replay':len(historical),'last_loss':losses[-1]}
