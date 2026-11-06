"""Session-aware daily orchestration; environment-specific data/trainer ports are explicit.

This runner does not bypass the existing production system's promotion gates.
Install a validated champion and wire operational PIT features before scheduling.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime,timezone
import fcntl
import json
from pathlib import Path
from typing import Any,Callable,Protocol
import pandas as pd
from api.ml.institutional.continual import Experience
from api.ml.institutional.data import utc
from api.ml.institutional.graph import DynamicEventGraph
from api.ml.institutional.ingestion import FinancialIngestionAgent,Source
from api.ml.institutional.lineage import digest,write_once
from api.ml.institutional.registry import ModelRegistry,PromotionGate
from api.ml.institutional.monitor import DistributionMonitor


@dataclass
class DailyData:
    new_labels: list[Experience]
    feature_schema: str
    source_snapshot_digest: str
    healthy: bool
    drift_triggered: bool
    drift_evidence: dict[str,Any]
    drift_features: Any = None
    drift_window_id: str = ''
    has_new_information: bool = False
    available_at: str | None = None


@dataclass(frozen=True)
class Candidate:
    directory: Path
    manifest: dict[str,Any]


class LearningPorts(Protocol):
    """Adapters are required, not silently substituted with latest-revised data.

    fit_* writes immutable weights, preprocessing and held-out calibration files.
    A full reset creates new weights/optimizer/EWC; fine-tuning freezes transforms.
    evaluate performs origin-specific fit/preprocessing/graph reconstruction and
    returns audited walk-forward + genuine prospective forecasts, plus one
    cost-adjusted excess portfolio return per trading day (never one per task).
    """
    def build_data(self, cutoff: str, graph_digest: str) -> DailyData: ...
    def fine_tune(self, champion: str, data: DailyData, cutoff: str, run_id: str) -> Candidate: ...
    def full_retrain(self, champion: str, data: DailyData, cutoff: str, run_id: str) -> Candidate: ...
    def evaluate(self, champion: str, candidate: Candidate, cutoff: str, diagnostic_days: int) -> tuple[pd.DataFrame,pd.DataFrame]: ...
    def champion_recipe(self, champion: str) -> str: ...
    def required_cells(self) -> set[tuple[str,int]]: ...


class AutonomousDailyPipeline:
    """Single-host reference runner with process lock and immutable run journal.

    Replace file lock/SQLite with database advisory locks and a transactional
    registry/outbox for multi-host deployment. No inference/position/order action
    is performed by this training pipeline. Failed gates retain the champion.
    """
    def __init__(self, root: Path, ingestor: FinancialIngestionAgent, sources: list[Source],
                 graph: DynamicEventGraph, registry: ModelRegistry, gate: PromotionGate,
                 ports: LearningPorts, market_close: Callable[[date],datetime | None],
                 recipe_digest: str, monitor: DistributionMonitor | None = None) -> None:
        if not sources or len(recipe_digest)!=64:
            raise ValueError('Configured sources and immutable recipe digest are required')
        self.root,self.ingestor,self.sources = root,ingestor,sources
        self.monitor = monitor
        self.graph,self.registry,self.gate,self.ports = graph,registry,gate,ports
        self.market_close,self.recipe = market_close,recipe_digest
        root.mkdir(parents=True,exist_ok=True)

    def run(self, now: datetime | None = None, *, manual: bool = False) -> dict[str,Any]:
        current = utc(now or datetime.now(timezone.utc))
        local = current.tz_convert('America/New_York')
        close = self.market_close(local.date())
        if not manual:
            if close is None:
                return {'status':'skipped_non_session'}
            earliest = utc(close)+pd.Timedelta(minutes=20)
            if not earliest<=current<=earliest+pd.Timedelta(minutes=60):
                return {'status':'outside_session_learning_window'}
        run_id = local.date().isoformat()+'-'+self.recipe[:16]+('-manual-'+current.strftime('%H%M%S%f') if manual else '')
        completed = self.root/'runs'/(run_id+'.json')
        if completed.exists(): return json.loads(completed.read_text())
        with (self.root/'daily.lock').open('a') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return {'status':'already_running'}
            if completed.exists(): return json.loads(completed.read_text())
            prior = self.registry.decision(run_id)
            if prior:
                write_once(completed,prior)
                return prior
            champion = self.registry.champion()
            if not champion:
                return {'status':'held_missing_validated_champion'}
            document_file = self.root/'seen_documents.json'
            seen = set(json.loads(document_file.read_text())) if document_file.exists() else set()
            events,failures = self.ingestor.ingest(self.sources,now=current.isoformat(),seen_documents=seen)
            # Never stamp newly extracted information at the earlier market close.
            cutoff = utc(datetime.now(timezone.utc)).isoformat()
            self.graph.append(events,cutoff=cutoff,sources_complete=not failures)
            _,graph_digest = self.graph.snapshot(cutoff)
            from api.ml.live import _write
            _write(document_file,sorted(seen))
            data = self.ports.build_data(cutoff,graph_digest)
            if data.available_at is not None:
                cutoff=max(utc(cutoff),utc(data.available_at)).isoformat()
            if failures or not data.healthy:
                report = {'status':'held_data_quality','source_failures':failures,'run_id':run_id,'graph_digest':graph_digest}
                # Not a completed day: scheduler may retry after provider recovery.
                return report
            if self.monitor is not None and data.drift_features is not None:
                monitor_path = self.root/('drift-'+digest({'schema':data.feature_schema,'recipe':self.recipe,'reference':self.monitor.reference_digest})+'.json')
                if monitor_path.exists(): self.monitor.load_state_dict(json.loads(monitor_path.read_text()))
                measured = self.monitor.update(data.drift_features,window_id=data.drift_window_id)
                _write(monitor_path,self.monitor.state_dict())
                data.drift_triggered = measured.trigger
                data.drift_evidence = vars(measured)
            reset_path = self.root/'last_full_reset.json'
            if data.drift_triggered and reset_path.exists():
                prior_reset = json.loads(reset_path.read_text())
                if prior_reset.get('recipe')==self.recipe and utc(cutoff)-utc(prior_reset['cutoff'])<pd.Timedelta(days=7):
                    report = {'status':'held_full_retrain_cooldown','run_id':run_id,'graph_digest':graph_digest}
                    write_once(completed,report)
                    return report
            if not data.new_labels and not data.drift_triggered and not data.has_new_information:

                report = {'status':'skipped_no_new_matured_labels','run_id':run_id,'graph_digest':graph_digest}
                write_once(completed,report)
                return report
            if data.drift_triggered:
                train = self.ports.full_retrain
                training_mode = 'full_reset'
            elif data.new_labels:
                train = self.ports.fine_tune
                training_mode = 'supervised_fine_tune'
            else:
                train = getattr(self.ports,'self_supervise')
                training_mode = 'observed_feature_reconstruction'
            candidate = train(champion,data,cutoff,run_id)
            if candidate.manifest.get('recipe_digest')!=self.recipe or candidate.manifest.get('source_snapshot_digest')!=data.source_snapshot_digest or candidate.manifest.get('graph_snapshot_digest')!=graph_digest:
                raise ValueError('Candidate lineage does not match this daily run')
            if data.drift_triggered: _write(reset_path,{'cutoff':cutoff,'recipe':self.recipe})
            candidate_id = self.registry.register(candidate.directory,candidate.manifest)
            forecasts,returns = self.ports.evaluate(champion,candidate,cutoff,diagnostic_days=30)
            arguments={'cutoff':cutoff,'candidate_recipe':self.recipe,
                'champion_recipe':self.ports.champion_recipe(champion),'required_cells':self.ports.required_cells()}
            if isinstance(self.gate,PromotionGate):
                evidence=self.gate.evaluate(forecasts,returns,attempt=1,preflight=True,**arguments)
                # Empty/immature cohorts are not statistical tests and must not
                # silently exhaust the sequential alpha budget before labels mature.
                if evidence.get('ready_for_statistical_test'):
                    evidence=self.gate.evaluate(forecasts,returns,attempt=self.registry.attempt(run_id),**arguments)
            else:
                evidence=self.gate.evaluate(forecasts,returns,attempt=self.registry.attempt(run_id),**arguments)
            evidence.update(graph_digest=graph_digest,source_snapshot_digest=data.source_snapshot_digest,
                            drift=data.drift_evidence,training_mode=training_mode)
            result = self.registry.decide(candidate_id,champion,evidence,run_id=run_id)
            write_once(completed,result)
            return result


def prefect_flow(pipeline: AutonomousDailyPipeline) -> Any:
    """Optional Prefect deployment: `.serve(name=..., cron=..., timezone=...)`.

    Poll 12:00–17:59 New York time every 10 min. The session calendar handles
    holidays and early closes, and the daily run journal suppresses duplicates.
    """
    from prefect import flow
    @flow(name='macro-autonomous-daily-learning',retries=2,retry_delay_seconds=300)
    def run() -> dict[str,Any]:
        return pipeline.run()
    return run


def run_champion_challenger_pipeline(pipeline:AutonomousDailyPipeline,*,manual:bool=False,
                                    purged_validation: Callable[[],dict[str,Any]]|None=None) -> dict[str,Any]:
    """Application entrypoint; purged-CV diagnostics never substitute for PIT gates.

    The optional callback must fit preprocessing, links, calibration and weights
    independently within purged folds. A fitted daily checkpoint is not eligible
    as a fold's starting point when it has seen that fold's validation rows.
    """
    if purged_validation is not None:
        diagnostics=purged_validation()
        if not diagnostics.get('fold_local_fit') or not diagnostics.get('embargo_enforced'):
            raise ValueError('Unattested purged validation result')
        from api.ml.live import _write
        _write(pipeline.root/'purged_validation.json',diagnostics)
    return pipeline.run(manual=manual)
