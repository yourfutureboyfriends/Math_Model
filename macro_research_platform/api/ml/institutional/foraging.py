"""Budgeted information-foraging environment; PPO trains on frozen replay only."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable,Any
import numpy as np
import gymnasium as gym
from gymnasium import spaces
import torch
from torch import nn,Tensor
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor


class ForagingGraphFeatures(BaseFeaturesExtractor):
    """Permutation-invariant KG summaries; padding never changes policy state.

    Main-model GAT embeddings already carry neighbor information. Masked mean
    and standard deviation avoid learning accidental node-array positions.
    """
    def __init__(self,observation_space:spaces.Dict,features_dim:int=64) -> None:
        super().__init__(observation_space,features_dim)
        width=observation_space['nodes'].shape[-1]
        inputs=24+2*width+1+observation_space['actions_remaining'].shape[0]
        self.project=nn.Sequential(nn.Linear(inputs,features_dim),nn.LayerNorm(features_dim),nn.GELU())

    def forward(self,observations:dict[str,Tensor]) -> Tensor:
        nodes=observations['nodes'].float();mask=observations['node_mask'].float().unsqueeze(-1)
        count=mask.sum(1).clamp_min(1.)
        mean=(nodes*mask).sum(1)/count
        variance=((nodes-mean.unsqueeze(1)).square()*mask).sum(1)/count
        inputs=torch.cat([observations['entropy'].float(),mean,variance.clamp_min(1e-8).sqrt(),
                          observations['actions_remaining'].float(),observations['budget'].float()],-1)
        return self.project(inputs)


def calculate_foraging_reward(before:np.ndarray,after:np.ndarray,*,cost:float,targets:np.ndarray|None=None,
                               known:np.ndarray|None=None,cost_weight:float=.05) -> tuple[float,dict[str,float]]:
    """Bounded belief-update KL plus observed Brier gain minus provider/compute cost.

    KL(Bern(p_after)||Bern(p_before)) is belief change, not proof of information
    gain. Accuracy is scored only on labels eligible in the frozen replay cutoff.
    No outcome reward is fabricated for live, unlabelled source requests.
    """
    p,q=np.asarray(before,float),np.asarray(after,float)
    if p.shape!=q.shape or p.size!=24 or not np.isfinite([p,q]).all() or ((p<0)|(p>1)|(q<0)|(q>1)).any() or not np.isfinite(cost) or cost<0 or cost_weight<0:
        raise ValueError('Invalid foraging probabilities/cost')
    p,q=np.clip(p,1e-6,1-1e-6),np.clip(q,1e-6,1-1e-6)
    kl=float(np.mean(q*np.log(q/p)+(1-q)*np.log((1-q)/(1-p))))
    accuracy=0.
    if targets is not None:
        y=np.asarray(targets,float);mask=np.asarray(known,bool) if known is not None else np.zeros(p.shape,bool)
        if y.shape!=p.shape or mask.shape!=p.shape or not np.isfinite(y[mask]).all() or not np.isin(y[mask],[0,1]).all():raise ValueError('Invalid matured outcome mask')
        if mask.any():accuracy=float(np.mean((p[mask]-y[mask])**2-(q[mask]-y[mask])**2))
    # Small capped KL prevents a model from maximizing arbitrary disagreement.
    reward=.1*min(kl,.1)+accuracy-cost_weight*cost
    return reward,{'belief_change_kl':kl,'observed_brier_gain':accuracy,'cost':cost}


@dataclass(frozen=True)
class QueryResult:
    """A query's actual/replayed updated task heads and current KG embeddings."""
    probabilities:np.ndarray
    embeddings:np.ndarray
    cost:float
    snapshot:str
    targets:np.ndarray|None=None
    known:np.ndarray|None=None


class InformationForagingEnv(gym.Env):
    """Discrete approved source actions plus STOP, no arbitrary URLs or tools.

    reset_provider returns origin-frozen TFT predictions/KG embeddings. Query
    callbacks must reconstruct only evidence available in that episode. Train
    PPO only with offline=True; live execution is limited to one budgeted episode.
    """
    metadata={'render_modes':[]}
    def __init__(self,reset_provider:Callable[[int|None],QueryResult],queries:dict[str,Callable[[],QueryResult]],
                 *,offline:bool,max_nodes:int=256,embedding_width:int=64,budget:float=3.,maximum_queries:int|None=None) -> None:
        super().__init__()
        if not queries or len(queries)>16 or budget<=0:raise ValueError('Bounded configured queries required')
        if maximum_queries is not None and maximum_queries<1:raise ValueError('Positive query limit required')
        self.maximum_queries=maximum_queries
        self.reset_provider,self.queries,self.offline=reset_provider,queries,offline
        self.names=tuple(queries);self.max_nodes,self.width,self.budget=max_nodes,embedding_width,budget
        self.action_space=spaces.Discrete(len(queries)+1)
        self.observation_space=spaces.Dict({'entropy':spaces.Box(0,np.log(2),shape=(24,),dtype=np.float32),
             'nodes':spaces.Box(-100,100,shape=(max_nodes,embedding_width),dtype=np.float32),
             'node_mask':spaces.MultiBinary(max_nodes),'actions_remaining':spaces.MultiBinary(len(queries)),
             'budget':spaces.Box(0,1,shape=(1,),dtype=np.float32)})
        self.current:QueryResult|None=None;self.used:set[int]=set();self.spent=0.;self.ended=True

    def _observation(self) -> dict[str,np.ndarray]:
        if self.current is None:raise RuntimeError('Reset before using environment')
        p=np.clip(np.asarray(self.current.probabilities).reshape(24),1e-6,1-1e-6)
        e=np.asarray(self.current.embeddings,float)
        if e.ndim!=2 or e.shape[1]!=self.width or len(e)>self.max_nodes or not np.isfinite(e).all():raise ValueError('Foraging KG schema mismatch')
        nodes=np.zeros((self.max_nodes,self.width),np.float32);nodes[:len(e)]=np.clip(e,-100,100)
        mask=np.zeros(self.max_nodes,np.int8);mask[:len(e)]=1
        return {'entropy':(-(p*np.log(p)+(1-p)*np.log(1-p))).astype(np.float32),'nodes':nodes,'node_mask':mask,
                'actions_remaining':np.array([int(i+1 not in self.used) for i in range(len(self.names))],np.int8),
                'budget':np.array([max(0,1-self.spent/self.budget)],np.float32)}

    def reset(self,*,seed:int|None=None,options:dict[str,Any]|None=None) -> tuple[dict[str,np.ndarray],dict[str,Any]]:
        super().reset(seed=seed);self.used=set();self.spent=0.;self.ended=False
        self.current=self.reset_provider(seed)
        return self._observation(),{'snapshot':self.current.snapshot,'offline':self.offline}

    def step(self,action:int) -> tuple[dict[str,np.ndarray],float,bool,bool,dict[str,Any]]:
        if self.ended or self.current is None:raise RuntimeError('Episode has ended; reset required')
        if not self.action_space.contains(action):raise ValueError('Unknown source action')
        if action==0:self.ended=True;return self._observation(),0.,True,False,{'stopped':True}
        if action in self.used:self.ended=True;return self._observation(),-1.,True,False,{'duplicate_query':True}
        # Worst-case callback budget must be enforced by the provider adapter too.
        if self.spent>=self.budget:self.ended=True;return self._observation(),0.,False,True,{'budget_exhausted':True}
        result=self.queries[self.names[action-1]]()
        if result.cost<0 or not np.isfinite(result.cost):raise ValueError('Invalid actual query cost')
        reward,info=calculate_foraging_reward(self.current.probabilities,result.probabilities,cost=result.cost,
                      targets=result.targets if self.offline else None,known=result.known if self.offline else None)
        self.current=result;self.used.add(action);self.spent+=result.cost
        self.ended=len(self.used)==len(self.names) or self.spent>=self.budget or (self.maximum_queries is not None and len(self.used)>=self.maximum_queries)
        return self._observation(),reward,False,self.ended,{**info,'snapshot':result.snapshot,'offline':self.offline}


def train_foraging_policy(env:InformationForagingEnv,path:Path,*,steps:int=1024,seed:int=1729) -> dict[str,Any]:
    """Bounded SB3 PPO on immutable historical query episodes, never live scraping."""
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_checker import check_env
    if not env.offline:raise ValueError('PPO training cannot issue live provider requests')
    if not 64<=steps<=100_000:raise ValueError('Invalid PPO compute budget')
    check_env(env,warn=False)  # Custom masked graph extractor handles the 2D node observation.
    policy=PPO('MultiInputPolicy',env,n_steps=64,batch_size=32,n_epochs=2,seed=seed,device='cpu',
               policy_kwargs={'features_extractor_class':ForagingGraphFeatures,'net_arch':{'pi':[32],'vf':[32]}},verbose=0)
    policy.learn(total_timesteps=steps)
    path.parent.mkdir(parents=True,exist_ok=True);policy.save(str(path))
    return {'path':str(path),'steps':steps,'seed':seed,'scope':'Offline source-reveal policy; requires prospective evaluation before live selection.'}


@dataclass(frozen=True)
class ModelQueryEpisode:
    """Audited origin-frozen query alternatives measured with one model version.

    Each source state contains the baseline plus that source's genuinely observed
    data. Cross-source alternatives must be collected without using later data.
    Live training is ineligible until such episodes have been collected.
    """
    origin:str
    model_digest:str
    source_available_at:dict[str,str]
    baseline:dict[str,Any]
    source_states:dict[str,dict[str,Any]]
    snapshot_ids:dict[str,str]
    targets:np.ndarray|None=None
    targets_known_at:str|None=None


def model_foraging_environment(system:Any,episodes:list[ModelQueryEpisode],*,cutoff:str,model_digest:str) -> InformationForagingEnv:
    """Connect PPO replay directly to the existing TFT heads/GAT embeddings.

    One action per episode prevents combining independently measured source
    alternatives into a counterfactual multi-query state that was never observed.
    Caller must provide actual frozen query alternatives, not source ablations.
    """
    import torch
    from api.ml.institutional.data import utc
    if not episodes:raise ValueError('Actual frozen query episodes are required')
    names=tuple(sorted(episodes[0].source_states))
    for episode in episodes:
        if episode.model_digest!=model_digest or tuple(sorted(episode.source_states))!=names:raise ValueError('Replay model/action identity mismatch')
        if utc(episode.origin)>utc(cutoff) or any(utc(stamp)>utc(episode.origin) for stamp in episode.source_available_at.values()):raise ValueError('Future source in foraging replay')
        if set(episode.source_available_at)!=set(names) or set(episode.snapshot_ids)!=set(names):raise ValueError('Missing source availability/provenance')
    active:ModelQueryEpisode|None=None
    rng=np.random.default_rng(1729)
    def predict(tensors:dict[str,Any],snapshot:str,episode:ModelQueryEpisode) -> QueryResult:
        system.eval()
        with torch.no_grad():out=system.predict(tensors)
        eligible=episode.targets is not None and episode.targets_known_at is not None and utc(episode.targets_known_at)<=utc(cutoff)
        return QueryResult(out['predictions'][0].sigmoid().cpu().numpy(),out['node_embeddings'][0].cpu().numpy(),1.,snapshot,
                           episode.targets if eligible else None,np.isfinite(episode.targets) if eligible else None)
    def reset(seed:int|None) -> QueryResult:
        nonlocal active,rng
        if seed is not None:rng=np.random.default_rng(seed)
        active=episodes[int(rng.integers(len(episodes)))]
        return predict(active.baseline,'baseline:'+active.origin,active)
    def query(name:str) -> QueryResult:
        if active is None:raise RuntimeError('Reset replay origin first')
        return predict(active.source_states[name],active.snapshot_ids[name],active)
    return InformationForagingEnv(reset,{name:lambda name=name:query(name) for name in names},offline=True,
                                  embedding_width=system.network.cfg.hidden,budget=1.)
