"""Behaviour-cloned PPO agent with bounded offline/online execution paths."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import numpy as np
import torch
from torch import Tensor
import torch.nn.functional as F
from stable_baselines3 import PPO
from api.ml.institutional.foraging import InformationForagingEnv,ForagingGraphFeatures
from api.ml.institutional.data import utc


@dataclass(frozen=True)
class BehaviourExample:
    """Best observed historical source alternative, not a globally optimal oracle."""
    observation:dict[str,np.ndarray]
    action:int
    observed_at:datetime
    label_known_at:datetime
    action_names:tuple[str,...]


@dataclass(frozen=True)
class RewardWeights:
    information:float=.1
    accuracy:float=1.
    cost:float=.05


def composite_foraging_reward(before:np.ndarray,after:np.ndarray,*,cost:float,targets:np.ndarray|None=None,
                               known:np.ndarray|None=None,weights:RewardWeights=RewardWeights()) -> dict[str,float]:
    """R=w1*KL(Bern(after)||Bern(before))+w2*Brier gain-w3*cost.

    KL is a belief update/surprise measure, not proof of beneficial information.
    Accuracy is zero until observed labels are supplied by the PIT reward ledger.
    Arrays have shape [H,6] or [24]; nonfinite and unbounded values fail closed.
    """
    p,q=np.asarray(before,float),np.asarray(after,float)
    if p.shape!=q.shape or p.size!=24 or not np.isfinite([p,q]).all() or ((p<0)|(p>1)|(q<0)|(q>1)).any():raise ValueError('Invalid TFT reward distributions')
    if not np.isfinite([cost,weights.information,weights.accuracy,weights.cost]).all() or min(cost,weights.information,weights.accuracy,weights.cost)<0:raise ValueError('Invalid reward weights/cost')
    p,q=np.clip(p,1e-6,1-1e-6),np.clip(q,1e-6,1-1e-6)
    information=float(np.mean(q*np.log(q/p)+(1-q)*np.log((1-q)/(1-p))))
    accuracy=0.
    if targets is not None:
        y=np.asarray(targets,float);mask=np.zeros_like(p,dtype=bool) if known is None else np.asarray(known,bool)
        if y.shape!=p.shape or mask.shape!=p.shape or not np.isfinite(y[mask]).all() or not np.isin(y[mask],[0,1]).all():raise ValueError('Invalid outcome mask')
        if mask.any():accuracy=float(((p[mask]-y[mask])**2-(q[mask]-y[mask])**2).mean())
    return {'reward':weights.information*information+weights.accuracy*accuracy-weights.cost*cost,
            'information_kl':information,'accuracy_brier_gain':accuracy,'cost':cost}


class ForagingAgent:
    """PPO with BC pretraining enforced before any online environment interaction.

    Live callbacks remain approved, bounded source adapters. This class cannot
    grant a new provider subscription or change the application's release gates.
    Online .learn never silently rounds beyond the configured step budget.
    """
    def __init__(self,env:InformationForagingEnv,*,rollout_steps:int=16,maximum_online_steps:int=64,seed:int=1729) -> None:
        if not env.offline:raise ValueError('Construct the agent with offline replay before live use')
        if rollout_steps<2 or rollout_steps>256 or maximum_online_steps<rollout_steps:raise ValueError('Invalid rollout budget')
        self.env,self.rollout_steps,self.online_budget=env,rollout_steps,maximum_online_steps
        self.cloned=False;self.seed=seed
        self.model=PPO('MultiInputPolicy',env,n_steps=rollout_steps,batch_size=min(8,rollout_steps),n_epochs=2,seed=seed,device='cpu',
                       policy_kwargs={'features_extractor_class':ForagingGraphFeatures,'net_arch':{'pi':[32],'vf':[32]}},verbose=0)

    def behaviour_clone(self,examples:list[BehaviourExample],*,cutoff:datetime,epochs:int=3,batch_size:int=32) -> dict[str,float]:
        """Historical states -> categorical logits [B,A] -> CE(expert_action).

        Only outcomes known by training cutoff may supply demonstration labels.
        Source action names/order and observation spaces must match the PPO env.
        Batches are assembled incrementally, not as one unbounded state tensor.
        """
        if not examples or len(examples)>100_000 or not 1<=epochs<=20 or not 1<=batch_size<=128:raise ValueError('Invalid BC dataset/compute budget')
        for example in examples:
            if not utc(example.observed_at)<=utc(example.label_known_at)<=utc(cutoff):raise ValueError('Future/unmatured demonstration')
            if example.action_names!=self.env.names or not self.env.observation_space.contains(example.observation) or not self.env.action_space.contains(example.action):raise ValueError('BC action/state schema mismatch')
            if example.action and (not example.observation['actions_remaining'][example.action-1] or example.observation['budget'][0]<=0):raise ValueError('Demonstration selected an unavailable source')
        max_row=max(sum(v.nbytes for v in e.observation.values()) for e in examples)
        if max_row*batch_size>32*1024*1024:raise MemoryError('BC minibatch memory budget exceeded')
        rng=np.random.default_rng(self.seed);losses=[];policy=self.model.policy;policy.set_training_mode(True)
        for _ in range(epochs):
            order=rng.permutation(len(examples))
            for start in range(0,len(order),batch_size):
                batch=[examples[int(i)] for i in order[start:start+batch_size]]
                observations={k:torch.as_tensor(np.stack([e.observation[k] for e in batch]),device=policy.device) for k in batch[0].observation}
                actions=torch.tensor([e.action for e in batch],dtype=torch.long,device=policy.device) # [B]
                distribution=policy.get_distribution(observations)
                logits=distribution.distribution.logits # [B,A], categorical source/STOP actions
                loss=F.cross_entropy(logits,actions)
                if not torch.isfinite(loss):raise FloatingPointError('Invalid BC objective')
                policy.optimizer.zero_grad(set_to_none=True);loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True);policy.optimizer.step()
                losses.append(float(loss.detach()))
        self.cloned=True;policy.set_training_mode(False)
        return {'epochs':float(epochs),'updates':float(len(losses)),'loss':losses[-1]}

    # American spelling is also accepted by application integrations.
    behavior_clone=behaviour_clone

    def train_offline(self,steps:int=256) -> None:
        """Fine-tune the cloned policy in outcome-labelled frozen replay only."""
        if not self.cloned:raise RuntimeError('Behaviour cloning must complete before PPO training')
        if not self.env.offline or steps<self.rollout_steps or steps%self.rollout_steps or steps>100_000:raise ValueError('Invalid offline PPO budget')
        self.model.learn(total_timesteps=steps)

    def train_online(self,env:InformationForagingEnv,*,steps:int=16) -> None:
        """Bounded on-policy rollout; caller still owns prospective release approval.

        No pseudo accuracy reward is invented. A live environment must enforce
        its own declared provider/request/cost limits before each source call.
        """
        if not self.cloned:raise RuntimeError('Live interaction requires completed behaviour cloning')
        if env.offline or env.names!=self.env.names or env.maximum_queries is None:raise ValueError('Bounded compatible live source environment required')
        if steps<self.rollout_steps or steps%self.rollout_steps or steps>self.online_budget:raise ValueError('Online step budget would be exceeded')
        self.model.set_env(env);self.model.learn(total_timesteps=steps,reset_num_timesteps=False)
        self.online_budget-=steps
