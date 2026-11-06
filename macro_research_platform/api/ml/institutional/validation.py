"""Purging uses target windows; walk-forward also enforces actual label availability."""
from __future__ import annotations
from collections.abc import Iterator,Callable
from typing import Any
import numpy as np
import pandas as pd
from api.ml.institutional.data import utc


def _times(values: object) -> pd.DatetimeIndex:
    result = pd.DatetimeIndex(values)
    if result.tz is None or result.hasnans:
        raise ValueError('Use non-null timezone-aware timestamps')
    return result.tz_convert('UTC')


class PurgedKFold:
    """Symmetric purged K-fold for research selection; may train on later folds.

    Use WalkForward for a deployment replay. Fit scalers, PCA and graph link
    estimation inside each training fold. Embargo is applied on both sides.
    """
    def __init__(self, folds: int = 5, embargo: str = '30D') -> None:
        if folds<2:
            raise ValueError('Need at least two folds')
        self.folds,self.embargo = folds,pd.Timedelta(embargo)
        if self.embargo<pd.Timedelta(0):
            raise ValueError('Negative embargo')

    def split(self, starts: object, ends: object) -> Iterator[tuple[np.ndarray,np.ndarray]]:
        a,b = _times(starts),_times(ends)
        if len(a)!=len(b) or len(a)<self.folds or not a.is_monotonic_increasing or (b<a).any():
            raise ValueError('Invalid ordered target intervals')
        for test in np.array_split(np.arange(len(a)),self.folds):
            keep = (b < a[test].min()-self.embargo) | (a > b[test].max()+self.embargo)
            train = np.flatnonzero(keep)
            if len(train):
                yield train,test


class WalkForward:
    """Expanding/rolling training; only labels released before validation origin."""
    def __init__(self, min_train: int = 120, validation_rows: int = 30, step: int = 30,
                 embargo: str = '30D', train_rows: int | None = None) -> None:
        if min(min_train,validation_rows,step)<1:
            raise ValueError('Window sizes must be positive')
        self.min_train,self.validation_rows,self.step = min_train,validation_rows,step
        self.embargo,self.train_rows = pd.Timedelta(embargo),train_rows
        if self.embargo<pd.Timedelta(0):
            raise ValueError('Negative embargo')

    def split(self, starts: object, ends: object, known_at: object) -> Iterator[tuple[np.ndarray,np.ndarray]]:
        a,b,k = _times(starts),_times(ends),_times(known_at)
        if not len(a)==len(b)==len(k) or not a.is_monotonic_increasing or (b<a).any() or (k<b).any():
            raise ValueError('Invalid label windows or availability')
        for first in range(self.min_train,len(a),self.step):
            cutoff = a[first]-self.embargo
            train = np.flatnonzero((a<a[first]) & (b<cutoff) & (k<=cutoff))
            if self.train_rows is not None:
                train = train[-self.train_rows:]
            if len(train)>=self.min_train:
                yield train,np.arange(first,min(first+self.validation_rows,len(a)))


class WalkForwardOptimization:
    """Execute fold-local fitting; callbacks own the explicit PIT feature adapter.

    `fit(train_indices, cutoff)` must fit transforms, link estimates and model
    using only those rows, returning an object with `trained_through`.
    `predict(fitted, test_indices)` returns timestamped audited forecast rows.
    No foundation checkpoint trained beyond the fold cutoff may be reused.
    """
    def __init__(self, splitter: WalkForward) -> None:
        self.splitter = splitter

    def run(self, starts: object, ends: object, known_at: object, fit: Callable[[np.ndarray,pd.Timestamp],Any], predict: Callable[[Any,np.ndarray],pd.DataFrame]) -> pd.DataFrame:
        a = _times(starts)
        records = []
        for train,test in self.splitter.split(starts,ends,known_at):
            cutoff = a[test[0]]-self.splitter.embargo
            fitted = fit(train,cutoff)
            if not hasattr(fitted,'trained_through') or pd.Timestamp(fitted.trained_through)>cutoff:
                raise ValueError('Fitted fold violates its training cutoff')
            out = predict(fitted,test)
            if not isinstance(out,pd.DataFrame) or not {'origin','feature_asof'}.issubset(out):
                raise ValueError('Timestamped prediction frame required')
            origins = _times(out['origin'])
            if not set(origins).issubset(set(a[test])) or (_times(out['feature_asof'])>origins).any():
                raise ValueError('Prediction features contain future/foreign origins')
            records.append(out.assign(trained_through=pd.Timestamp(fitted.trained_through)))
        return pd.concat(records,ignore_index=True) if records else pd.DataFrame()


class PurgedChallengerEvaluation:
    """Fold-local purged CV diagnostics, kept separate from prospective evidence.

    Ordinary purged K-fold can train on observations chronologically after a
    validation origin. Its scores are research diagnostics, never falsely stamped
    as prospective forecasts. Production promotion still requires the existing
    walk-forward/prospective gate.
    """
    def __init__(self,folds:int=5,embargo:str='30D') -> None:
        self.splitter=PurgedKFold(folds,embargo)

    def run(self,starts:object,ends:object,known_at:object,*,cutoff:str,
            fit:Callable[[np.ndarray,pd.Timestamp],Any],predict:Callable[[Any,np.ndarray],pd.DataFrame]) -> dict[str,Any]:
        """Refit all transformations/models per fold and score paired binary heads.

        predict must return target/champion_probability/challenger_probability.
        fit returns an object with training_indices, recorded by the fold adapter.
        No warmed checkpoint trained on held-out origins is eligible.
        """
        a,b,k=_times(starts),_times(ends),_times(known_at)
        if not len(a)==len(b)==len(k) :raise ValueError('Inconsistent CV windows')
        if (k<b).any() or (k>utc(cutoff)).any():raise ValueError('Unmatured CV labels')
        folds=[];parts=[]
        for train,test in self.splitter.split(a,b):
            fitted=fit(train,utc(cutoff))
            if set(map(int,getattr(fitted,'training_indices',[])))!=set(map(int,train)):
                raise ValueError('Fold-local fit requires exact training-index attestation')
            result=predict(fitted,test)
            required=['target','champion_probability','challenger_probability']
            if not set(required)<=set(result) or result.empty:raise ValueError('Missing paired CV predictions')
            numbers=result[required].to_numpy(float)
            if not np.isfinite(numbers).all() or not np.isin(numbers[:,0],[0,1]).all() or ((numbers[:,1:]<0)|(numbers[:,1:]>1)).any():raise ValueError('Invalid CV probabilities')
            folds.append({'training_rows':len(train),'test_rows':len(test),'prediction_rows':len(result)})
            parts.append(numbers)
        if len(parts)!=self.splitter.folds:raise ValueError('Insufficient eligible purged folds')
        values=np.concatenate(parts);champion=float(np.mean((values[:,1]-values[:,0])**2));challenger=float(np.mean((values[:,2]-values[:,0])**2))
        return {'scope':'Purged CV research diagnostic, not prospective deployment evidence','fold_local_fit':True,
                'embargo_enforced':True,'folds':folds,'champion_brier':champion,'challenger_brier':challenger,
                'relative_brier_gain':(champion-challenger)/champion if champion>0 else None}
