"""Autonomous, transactional champion/challenger decisions with fail-closed evidence checks."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from api.ml.institutional.data import utc
from api.ml.institutional.lineage import digest,file_digest


@dataclass(frozen=True)
class GateConfig:
    minimum_origins: int = 120
    minimum_prospective_origins: int = 12
    minimum_class_count: int = 10
    block_origins: int = 12
    minimum_blocks: int = 8
    minimum_return_days: int = 252
    return_block_days: int = 21
    bootstrap_draws: int = 2000
    minimum_relative_brier_gain: float = .02
    family_alpha: float = .05
    annual_periods: int = 252
    require_reference_skill: bool = False


def _sharpe(x: np.ndarray, annual: int) -> float:
    sd = x.std(ddof=1)
    return float(x.mean()/sd*np.sqrt(annual)) if sd>1e-12 else float('nan')


def _block_indices(n: int, size: int, rng: np.random.Generator) -> np.ndarray:
    starts = rng.integers(0,n,size=int(np.ceil(n/size)))
    return np.concatenate([(start+np.arange(size))%n for start in starts])[:n]


class PromotionGate:
    """Brier is primary; require positive paired block-bootstrap lower bounds
    for Brier improvement, macro AUC improvement and cost-adjusted Sharpe gain.

    Bootstrap evidence is approximate under dependent/nonstationary data, not a
    distribution-free certificate. Bind block length to target overlap in the
    data's origin frequency. A 2% point improvement alone never promotes.
    Replayed evidence and genuinely prospective evidence are labelled separately.
    """
    def __init__(self, config: GateConfig = GateConfig()) -> None:
        self.config = config

    def evaluate(self, forecasts: pd.DataFrame, returns: pd.DataFrame, *, cutoff: str,
                 candidate_recipe: str, champion_recipe: str, attempt: int,
                 required_cells: set[tuple[str,int]], preflight: bool = False) -> dict[str,Any]:
        cfg = self.config
        if attempt<1 or not 0<cfg.family_alpha<1 or cfg.bootstrap_draws<100:
            raise ValueError('Invalid statistical gate configuration')
        result: dict[str,Any] = {'promote':False,'reason':'insufficient_evidence','attempt':attempt,'primary_metric':'paired_brier',
                                'policy':asdict(cfg),'cutoff':utc(cutoff).isoformat()}
        if forecasts.empty:return result
        required = {'origin','task','horizon','label_id','target','label_known_at','champion_probability','challenger_probability',
                    'champion_trained_through','challenger_trained_through','feature_asof','evaluation_mode',
                    'prediction_available_at','candidate_recipe','champion_recipe','target_schema'}
        if not required.issubset(forecasts):
            return {**result,'reason':'missing_forecast_attestation'}
        f = forecasts.copy()
        for name in ('origin','label_known_at','champion_trained_through','challenger_trained_through','feature_asof','prediction_available_at'):
            try: f[name] = f[name].map(utc)
            except (ValueError,TypeError): return {**result,'reason':'invalid_timestamps'}
        if f.empty or f['target_schema'].nunique()!=1:
            return result
        if not (f.candidate_recipe==candidate_recipe).all() or not (f.champion_recipe==champion_recipe).all():
            return {**result,'reason':'recipe_cohort_mismatch'}
        if (f.feature_asof>f.origin).any() or (f.champion_trained_through>=f.origin).any() or (f.challenger_trained_through>=f.origin).any():
            return {**result,'reason':'lookahead_in_evaluation'}
        if not f.evaluation_mode.isin(['prospective','walk_forward_replay']).all():
            return {**result,'reason':'unknown_evaluation_mode'}
        if (f.loc[f.evaluation_mode=='prospective','prediction_available_at']>f.loc[f.evaluation_mode=='prospective','origin']).any():
            return {**result,'reason':'backfilled_prospective_predictions'}
        f = f[(f.label_known_at<=utc(cutoff))&(f.origin<=utc(cutoff))]
        if f.duplicated(['origin','task','horizon']).any():
            return {**result,'reason':'duplicate_forecasts'}
        # One pre-specified earliest forecast per realized target, not daily
        # replicas of the same monthly label masquerading as new observations.
        f = f.sort_values('origin').drop_duplicates(['task','horizon','label_id'],keep='first')
        numeric = f[['target','champion_probability','challenger_probability']].to_numpy(float)
        if not np.isfinite(numeric).all() or not f.target.isin([0,1]).all() or ((numeric[:,1:]<0)|(numeric[:,1:]>1)).any():
            return {**result,'reason':'invalid_probabilities_or_targets'}
        cells = set(zip(f.task,f.horizon))
        if not required_cells or cells!=required_cells:
            return {**result,'reason':'missing_or_unexpected_task_horizon_cells'}
        groups = [group for _,group in f.groupby(['task','horizon'],sort=True)]
        if any(len(g)<cfg.minimum_origins or g.target.value_counts().reindex([0,1],fill_value=0).min()<cfg.minimum_class_count for g in groups):
            return result
        # Align every task/horizon on exactly the same origin cohort.
        origins = sorted(set.intersection(*(set(g.origin) for g in groups)))
        if len(origins)<max(cfg.minimum_origins,cfg.minimum_blocks*cfg.block_origins):
            return result
        aligned = [g.set_index('origin').loc[origins] for g in groups]
        prospective = set.intersection(*(set(g[g.evaluation_mode=='prospective'].origin) for g in groups))
        if len(prospective)<cfg.minimum_prospective_origins:
            return {**result,'reason':'insufficient_prospective_shadow_evidence'}
        y = np.stack([g.target.to_numpy(float) for g in aligned],1)
        pc = np.stack([g.champion_probability.to_numpy(float) for g in aligned],1)
        pn = np.stack([g.challenger_probability.to_numpy(float) for g in aligned],1)
        old,new = (pc-y)**2,(pn-y)**2
        reference_skills={}
        for j,g in enumerate(aligned):
            if 'reference_prior' not in g:continue
            prior=pd.to_numeric(g.reference_prior,errors='coerce').to_numpy(float)
            valid=np.isfinite(prior)&(prior>=0)&(prior<=1)
            if valid.sum()<cfg.minimum_origins:continue
            base_loss=float(np.mean((prior[valid]-y[valid,j])**2))
            if base_loss>1e-12:
                reference_skills[str(g.task.iloc[0])+'|'+str(int(g.horizon.iloc[0]))]=float(1-new[valid,j].mean()/base_loss)
        if cfg.require_reference_skill and (len(reference_skills)!=len(required_cells) or min(reference_skills.values(),default=-1)<=0):
            return {**result,'reason':'insufficient_positive_skill_vs_recorded_prior'}
        result['skill_vs_reference_prior']=reference_skills
        relative = float((old.mean()-new.mean())/max(old.mean(),1e-12))
        if relative<cfg.minimum_relative_brier_gain or np.any(new.mean(0)>old.mean(0)):
            return {**result,'reason':'brier_margin_or_per_cell_guard_failed','relative_brier_gain':relative}
        r = returns.copy()
        needed = {'date','champion_net_excess_return','challenger_net_excess_return','cost_model_digest','execution_policy_digest','candidate_recipe','champion_recipe'}
        if not needed.issubset(r):
            return {**result,'reason':'missing_cost_adjusted_portfolio_returns'}
        r['date'] = pd.DatetimeIndex(r.date.map(utc)).normalize()
        r = r[r.date<=utc(cutoff)].sort_values('date')
        if r.date.duplicated().any() or len(r)<cfg.minimum_return_days or r.cost_model_digest.nunique()!=1 or r.execution_policy_digest.nunique()!=1:
            return {**result,'reason':'invalid_portfolio_return_cohort'}
        if not (r.candidate_recipe==candidate_recipe).all() or not (r.champion_recipe==champion_recipe).all():
            return {**result,'reason':'return_recipe_mismatch'}
        daily = r[['champion_net_excess_return','challenger_net_excess_return']].to_numpy(float)
        if not np.isfinite(daily).all():
            return {**result,'reason':'nonfinite_portfolio_returns'}
        auc_c = float(np.mean([roc_auc_score(y[:,j],pc[:,j]) for j in range(y.shape[1])]))
        auc_n = float(np.mean([roc_auc_score(y[:,j],pn[:,j]) for j in range(y.shape[1])]))
        sharpe_c,sharpe_n = (_sharpe(daily[:,i],cfg.annual_periods) for i in range(2))
        if not np.isfinite([sharpe_c,sharpe_n]).all():
            return {**result,'reason':'undefined_sharpe'}
        if preflight:
            return {**result,'reason':'ready_for_statistical_test','ready_for_statistical_test':True}
        rng = np.random.default_rng(0)
        differences = []
        for _ in range(cfg.bootstrap_draws):
            ix = _block_indices(len(origins),cfg.block_origins,rng)
            if any(len(np.unique(y[ix,j]))<2 for j in range(y.shape[1])):
                continue
            ir = _block_indices(len(daily),cfg.return_block_days,rng)
            auc_delta = np.mean([roc_auc_score(y[ix,j],pn[ix,j])-roc_auc_score(y[ix,j],pc[ix,j]) for j in range(y.shape[1])])
            differences.append([float((old[ix]-new[ix]).mean()),float(auc_delta),
                                _sharpe(daily[ir,1],cfg.annual_periods)-_sharpe(daily[ir,0],cfg.annual_periods)])
        if len(differences)<.95*cfg.bootstrap_draws or not np.isfinite(differences).all():
            return {**result,'reason':'unstable_block_bootstrap'}
        # Alpha spending over recorded attempts, plus three metric comparisons.
        alpha = cfg.family_alpha/(attempt*(attempt+1)*3)
        if cfg.bootstrap_draws*alpha<1:
            return {**result,'reason':'bootstrap_resolution_insufficient_for_alpha_budget'}
        lower = np.quantile(np.array(differences),alpha,axis=0)
        result.update(promote=bool((lower>0).all()),reason='passed' if (lower>0).all() else 'paired_evidence_not_significant',
                      relative_brier_gain=relative,champion_brier=float(old.mean()),challenger_brier=float(new.mean()),
                      champion_auc=auc_c,challenger_auc=auc_n,champion_sharpe=sharpe_c,challenger_sharpe=sharpe_n,
                      lower_improvement_bounds=lower.tolist(),alpha=alpha,origins=len(origins),prospective_origins=len(prospective),
                      diagnostic_last_30_days={'rows':int((f.origin>=utc(cutoff)-pd.Timedelta(days=30)).sum()),
                                               'used_as_sole_promotion_evidence':False})
        return result


class ModelRegistry:
    """Immutable artifact registrations and SQLite compare-and-swap promotion.

    Serving reads the pointer per request/reload, verifies bundle hashes and
    atomically swaps a newly loaded model. Never mutate a live model's weights.
    Audit/registry storage must be backed up and access-controlled in deployment.
    """
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, manifest TEXT, stage TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS champion(singleton INTEGER PRIMARY KEY CHECK(singleton=1), id TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, payload TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS attempts(n INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT UNIQUE)')

    def register(self, directory: Path, manifest: dict[str,Any]) -> str:
        required = {'weights','preprocessor','calibrator','target_schema','configuration'}
        if not required.issubset(manifest.get('files',{})) or not manifest.get('recipe_digest') or not manifest.get('pit_verified'):
            raise ValueError('Incomplete candidate bundle or missing PIT attestation')
        for _,entry in manifest['files'].items():
            path = (directory/entry['path']).resolve()
            if not path.is_relative_to(directory.resolve()) or file_digest(path)!=entry['sha256']:
                raise ValueError('Candidate artifact integrity check failed')
        identity = digest(manifest)
        record = {'directory':str(directory.resolve()),'manifest':manifest}
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?)',(identity,json.dumps(record,allow_nan=False),'challenger'))
        return identity

    def champion(self) -> str | None:
        with sqlite3.connect(self.path) as c:
            row = c.execute('SELECT id FROM champion WHERE singleton=1').fetchone()
        return row[0] if row else None

    def decision(self, run_id: str) -> dict[str,Any] | None:
        with sqlite3.connect(self.path) as c:
            row = c.execute('SELECT payload FROM decisions WHERE id=?',(run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def attempt(self, run_id: str) -> int:
        with sqlite3.connect(self.path) as c:
            c.execute('INSERT OR IGNORE INTO attempts(run_id) VALUES(?)',(run_id,))
            return int(c.execute('SELECT n FROM attempts WHERE run_id=?',(run_id,)).fetchone()[0])

    def bootstrap(self, artifact: str) -> None:
        """One-time installation of the existing validated champion, not auto selection."""
        with sqlite3.connect(self.path) as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM champion').fetchone() or not c.execute('SELECT 1 FROM artifacts WHERE id=?',(artifact,)).fetchone():
                raise ValueError('Bootstrap requires empty registry and registered artifact')
            c.execute('INSERT INTO champion VALUES(1,?)',(artifact,))
            c.execute("UPDATE artifacts SET stage='champion' WHERE id=?",(artifact,))

    def decide(self, candidate: str, expected_champion: str, evidence: dict[str,Any], *, run_id: str) -> dict[str,Any]:
        decision = {**evidence,'candidate':candidate,'expected_champion':expected_champion,'run_id':run_id}
        with sqlite3.connect(self.path,timeout=30) as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT payload FROM decisions WHERE id=?',(run_id,)).fetchone()
            if prior: return json.loads(prior[0])
            champion = c.execute('SELECT id FROM champion WHERE singleton=1').fetchone()
            if not champion or champion[0]!=expected_champion:
                decision.update(promote=False,reason='champion_changed_during_evaluation')
            if not c.execute('SELECT 1 FROM artifacts WHERE id=?',(candidate,)).fetchone():
                raise ValueError('Unregistered challenger')
            if decision.get('promote'):
                registered = json.loads(c.execute('SELECT manifest FROM artifacts WHERE id=?',(candidate,)).fetchone()[0])
                base = Path(registered['directory']).resolve()
                for entry in registered['manifest']['files'].values():
                    artifact_path = (base/entry['path']).resolve()
                    if not artifact_path.is_relative_to(base) or file_digest(artifact_path)!=entry['sha256']:
                        raise ValueError('Candidate bundle changed after evaluation/registration')
                c.execute("UPDATE artifacts SET stage='archived' WHERE id=?",(expected_champion,))
                c.execute("UPDATE artifacts SET stage='champion' WHERE id=?",(candidate,))
                c.execute('UPDATE champion SET id=? WHERE singleton=1',(candidate,))
            c.execute('INSERT INTO decisions VALUES(?,?)',(run_id,json.dumps(decision,allow_nan=False)))
        return decision
