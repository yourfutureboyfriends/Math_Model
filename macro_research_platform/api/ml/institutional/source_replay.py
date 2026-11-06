"""Verified frozen source episodes -> outcome-masked offline foraging replay."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import numpy as np
from api.ml.institutional.data import utc
from api.ml.institutional.lineage import digest,file_digest


@dataclass(frozen=True)
class FrozenSourceEpisode:
    """Predictions/embeddings actually recorded under one frozen model identity."""
    identity:str
    origin:str
    month:str
    feature_schema:str
    weights_sha256:str
    baseline:dict[str,Any]
    actions:dict[str,dict[str,Any]]
    targets:np.ndarray
    known:np.ndarray


def _checked_trace(trace:dict[str,Any],origin:str) -> None:
    p=np.asarray(trace['probabilities'],float);embeddings=np.asarray(trace['embeddings'],float)
    if p.shape!=(4,6) or not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('Invalid archived forecast cells')
    if embeddings.ndim!=2 or not 1<=len(embeddings)<=256 or not 1<=embeddings.shape[1]<=512 or not np.isfinite(embeddings).all():raise ValueError('Invalid archived KG embeddings')
    if not utc(trace['available_at'])<=utc(trace['prediction_available_at'])<=utc(origin):raise ValueError('Backdated or future source inference')


def _verify_tensor(folder:Path,name:str,expected:str) -> None:
    path=(folder/name).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file() or file_digest(path)!=expected:
        raise ValueError('Source replay tensor integrity mismatch')


def load_source_replay(destination:Path,*,cutoff:str,feature_schema:str,
                       labels:dict[str,tuple[str,float]]) -> tuple[list[FrozenSourceEpisode],dict[str,int]]:
    """Verify artifact hashes/times and join only first-observed matured labels.

    Frozen probabilities are replayed as recorded; they are never recomputed
    using a later model. Missing/future labels remain masked, not pseudo-labelled.
    Invalid episodes are counted separately and never enter policy training.
    """
    from api.ml.institutional.application_data import TASK_NAMES,HORIZONS
    episodes=[];counts={'invalid_episodes':0,'incompatible_episodes':0,'future_episodes':0}
    for path in sorted(destination.glob('*/episode.json')):
        try:
            r=json.loads(path.read_text())
            if not r.get('complete'):continue
            if r['feature_schema']!=feature_schema:counts['incompatible_episodes']+=1;continue
            if utc(r['origin'])>utc(cutoff):counts['future_episodes']+=1;continue
            if not utc(r['started_at'])<=utc(r['evaluation_cutoff'])<=utc(r['origin']):raise ValueError('Invalid query observation window')
            _verify_tensor(path.parent,r['baseline_tensors'],r['baseline_sha256']);_checked_trace(r['baseline'],r['origin'])
            actions=r['actions']
            if not actions or sorted(actions)!=sorted(r['expected_sources']):raise ValueError('Incomplete source alternatives')
            width=np.asarray(r['baseline']['embeddings']).shape[1]
            for action in actions.values():
                if not action['eligible'] or action['source_failures'] or utc(action['available_at'])>utc(r['evaluation_cutoff']):raise ValueError('Unobserved source alternative')
                _verify_tensor(path.parent,action['tensors'],action['tensors_sha256']);_checked_trace(action['trace'],r['origin'])
                if action['trace']['available_at']!=r['baseline']['available_at'] or np.asarray(action['trace']['embeddings']).shape[1]!=width:raise ValueError('Mixed query evaluation context')
            target=np.full((4,6),np.nan);known=np.zeros((4,6),bool)
            for hi,horizon in enumerate(HORIZONS):
                for j,task in enumerate(TASK_NAMES):
                    entry=labels.get(r['month']+':'+task+':'+str(horizon))
                    if entry is None:continue
                    known_at,value=entry
                    if utc(known_at)>utc(cutoff):continue
                    if value not in (0.,1.):raise ValueError('Non-binary query outcome')
                    if utc(known_at)<=utc(r['origin']):continue
                    target[hi,j]=value;known[hi,j]=True
            identity=digest({'origin':r['origin'],'weights':r['weights_sha256'],'snapshot':r['source_snapshot']})
            episodes.append(FrozenSourceEpisode(identity,r['origin'],r['month'],feature_schema,r['weights_sha256'],r['baseline'],actions,target,known))
        except (OSError,ValueError,KeyError,TypeError):counts['invalid_episodes']+=1
    return episodes,counts


def source_replay_readiness(episodes:list[FrozenSourceEpisode],*,minimum_origins:int=24,minimum_cells:int=3) -> dict[str,Any]:
    """Deduplicate monthly target origins; repeated refreshes are not evidence."""
    first:dict[str,FrozenSourceEpisode]={}
    for episode in sorted(episodes,key=lambda e:e.origin):
        if int(episode.known.sum())>=minimum_cells:first.setdefault(episode.month,episode)
    ready=len(first)>=minimum_origins
    return {'ready_for_offline_training':ready,'labelled_monthly_origins':len(first),'required_monthly_origins':minimum_origins,
            'verified_episodes':len(episodes),'known_target_cells':sum(int(e.known.sum()) for e in first.values()),
            'reason':'Offline replay is ready for research training; prospective policy evaluation is still required.' if ready else 'Collecting independent monthly query origins and subsequently observed outcomes; repeated daily refreshes do not replace these.'}


def frozen_foraging_environment(episodes:list[FrozenSourceEpisode],*,minimum_cells:int=3) -> Any:
    """Actual archived model outputs -> Gym replay, with no provider/network calls.

    Actions are independent source alternatives and terminate after one query.
    Cost is documented as normalized request units, not monetary trading costs.
    """
    from api.ml.institutional.foraging import InformationForagingEnv,QueryResult
    first:dict[str,FrozenSourceEpisode]={}
    for episode in sorted(episodes,key=lambda e:e.origin):
        if episode.known.sum()>=minimum_cells:first.setdefault(episode.month,episode)
    eligible=list(first.values())
    if not eligible:raise ValueError('No outcome-labelled source episodes')
    names=tuple(sorted(eligible[0].actions));width=np.asarray(eligible[0].baseline['embeddings']).shape[1]
    if any(tuple(sorted(e.actions))!=names or np.asarray(e.baseline['embeddings']).shape[1]!=width for e in eligible):raise ValueError('Incompatible source action/embedding schemas')
    active:FrozenSourceEpisode|None=None
    rng=np.random.default_rng(1729)
    def result(trace:dict[str,Any],cost:float) -> QueryResult:
        if active is None:raise RuntimeError('Reset replay before use')
        return QueryResult(np.asarray(trace['probabilities']),np.asarray(trace['embeddings']),cost,trace['graph_snapshot'],active.targets,active.known)
    def reset(seed:int|None) -> QueryResult:
        nonlocal active,rng
        if seed is not None:rng=np.random.default_rng(seed)
        active=eligible[int(rng.integers(len(eligible)))];return result(active.baseline,0.)
    def query(name:str) -> QueryResult:
        if active is None:raise RuntimeError('Reset replay before querying')
        action=active.actions[name];units=max(1.,float(action.get('feed_requests',1))+float(action.get('document_attempts',0)))
        return result(action['trace'],min(units/7.,1.))
    return InformationForagingEnv(reset,{name:lambda name=name:query(name) for name in names},offline=True,embedding_width=width,budget=1.,maximum_queries=1)


def ensure_research_policy(episodes:list[FrozenSourceEpisode],destination:Path,*,cutoff:str) -> dict[str,Any]:
    """Automatically fit a bounded research PPO candidate when outcomes suffice.

    This artifact never activates live source selection. A separate prospective
    utility/cost evaluation must support that decision. Missing outcome history
    produces an explicit waiting state rather than fabricated learning rewards.
    """
    readiness=source_replay_readiness(episodes)
    if not readiness['ready_for_offline_training']:return {'status':'collecting_outcomes',**readiness,'live_ppo_enabled':False}
    selected:dict[str,FrozenSourceEpisode]={}
    for episode in sorted(episodes,key=lambda e:e.origin):
        if episode.known.sum()>=3:selected.setdefault(episode.month,episode)
    cohort=list(selected.values())
    dataset=digest([{'episode':e.identity,'known':e.known.tolist(),'targets':np.where(e.known,e.targets,0.).tolist()} for e in cohort])
    folder=destination/dataset;manifest=folder/'manifest.json'
    if manifest.exists():return json.loads(manifest.read_text())
    from tempfile import TemporaryDirectory
    from api.ml.institutional.foraging import train_foraging_policy
    from api.ml.institutional.lineage import write_once
    destination.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=destination) as temporary:
        stage=Path(temporary)
        env=frozen_foraging_environment(cohort)
        train_foraging_policy(env,stage/'policy',steps=256)
        report={'status':'research_policy_trained','dataset_sha256':dataset,'weights_sha256':file_digest(stage/'policy.zip'),
                'trained_at':utc(cutoff).isoformat(),'labelled_monthly_origins':len(cohort),'steps':256,'live_ppo_enabled':False,
                'scope':'Offline research only. Awaiting prospective source-utility and compute-cost evaluation before live activation.'}
        write_once(stage/'manifest.json',report)
        # No overwrite of a prior immutable candidate; single-host worker lock applies.
        import os
        os.rename(stage,folder)
        return report
