"""Options research (Quant Lab → Options research): staged experiments, results, the research registry, the sealed
holdout, and the controlled export of approved configurations for the Quant Algorithm — api/quant/optresearch."""
import asyncio
import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["options-research"])
BASE = "/api/v1/quant/options-research"


def _user(request: Request, roles=("pm", "quant", "analyst", "risk")):
    from api.core.access import require_roles
    return require_roles(request, set(roles))


class RunIn(BaseModel):
    """An options-research run: stage (1–4) and its settings."""
    stage: int
    strategies: Optional[List[str]] = None


class RevealIn(BaseModel):
    """Reveal the holdout of an experiment."""
    confirm: str


class ExportIn(BaseModel):
    """Export an experiment's configuration."""
    experiment_id: str
    strategy: str


class ApproveIn(BaseModel):
    """Approve an exported configuration."""
    file: str
    confirm: str
    acknowledge: bool = False
    reason: str = ""


class RollbackIn(BaseModel):
    """Roll a strategy back to its previous configuration, with a reason."""
    strategy: str
    reason: str = ""


@router.get(f"{BASE}/overview")
async def overview(request: Request):
    """Everything the dashboard lists: stages, criteria, hypotheses, experiments, configurations, performance profiles.
    """
    _user(request)
    from api.quant.optresearch import deploy, registry, runner, strategies, validate

    def build():
        prof_dir = Path(runner.ROOT).parent / "profiles"
        profiles = {}
        ab = None
        for f in sorted(prof_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                if f.stem == "ab_summary":
                    ab = d
                    continue
                if "stages" not in d:
                    continue
                profiles[f.stem] = {"total_seconds": d.get("total_seconds"), "shape": d.get("shape"),
                                    "stages": {k: {"seconds": v.get("seconds"), "peak_rss_mb": v.get("peak_rss_mb")}
                                               for k, v in (d.get("stages") or {}).items()}}
            except ValueError:
                continue
        return {"stages": {1: "Correctness: textbook pricing, Greeks, payoff bounds, accounting, look-ahead (synthetic)",
                           2: "Small universe: SPY, QQQ, IWM, DIA (observed implied volatility)",
                           3: "Intermediate: 17 ETFs + the 100 most liquid point-in-time S&P 500 members",
                           4: "Full: every point-in-time S&P 500 member with free price history + ETFs"},
                "segments": {"development": validate.DEV, "validation": validate.VAL, "holdout_start": validate.HOLDOUT_START},
                "criteria": validate.CRITERIA, "strategies": strategies.LABEL, "grids": strategies.GRIDS,
                "defaults": strategies.DEFAULTS, "hypotheses": registry.hypotheses(),
                "experiments": registry.experiments(50), "holdout_log": registry.holdout_log()[:50],
                "configs": deploy.list_configs(), "profiles": profiles, "ab": ab, "limitations": runner.LIMITATIONS}
    return await asyncio.to_thread(build)


@router.post(f"{BASE}/run")
async def run(body: RunIn, request: Request):
    """Start an options-research stage as a background job."""
    u = _user(request, ("pm", "quant"))
    if body.stage not in (1, 2, 3, 4):
        raise HTTPException(400, "stage must be 1, 2, 3 or 4")
    from api.quant import jobs
    from api.quant.optresearch import runner, strategies
    bad = [s for s in (body.strategies or []) if s not in strategies.STRATEGIES]
    if bad:
        raise HTTPException(400, f"Unknown strategies: {bad}")
    try:
        j = jobs.submit(u["username"], f"options_research_{body.stage}",
                        lambda job: runner.run_in_subprocess(body.stage, u["username"], job, body.strategies))
    except ValueError as e:
        raise HTTPException(429, str(e))
    return j.view(False)


@router.get(f"{BASE}/jobs/{{job_id}}")
async def job(job_id: str, request: Request):
    """A research job's status and result (your own jobs; administrators see all)."""
    from api.quant import jobs
    u = _user(request)
    j = jobs.get(job_id, u["username"], u["role"] == "admin")
    if not j:
        raise HTTPException(404, "Unknown job.")
    return j.view()


@router.delete(f"{BASE}/jobs/{{job_id}}")
async def job_cancel(job_id: str, request: Request):
    """Cancel a running research job."""
    from api.quant import jobs
    u = _user(request)
    return {"cancelled": jobs.cancel(job_id, u["username"], u["role"] == "admin")}


@router.get(f"{BASE}/experiments/{{eid}}")
async def experiment(eid: str, request: Request):
    """An experiment's stored result."""
    _user(request)
    from api.quant.optresearch import registry, runner
    if not eid.replace("-", "").isalnum():
        raise HTTPException(400, "Bad experiment id.")
    res = await asyncio.to_thread(runner.load_result, eid)
    if res is None:
        meta = registry.experiment(eid)
        if not meta:
            raise HTTPException(404, "Unknown experiment.")
        return {"experiment_id": eid, "meta": meta, "result": None}
    return {"experiment_id": eid, "meta": registry.experiment(eid), "result": res}


@router.post(f"{BASE}/experiments/{{eid}}/holdout")
async def reveal(eid: str, body: RevealIn, request: Request):
    """Unseal the holdout (2024 →). Logged: tuning after looking is no longer out of sample."""
    u = _user(request, ("pm", "quant"))
    if body.confirm.strip() != "REVEAL HOLDOUT":
        raise HTTPException(400, 'Type "REVEAL HOLDOUT" to confirm — every reveal is logged.')
    from api.quant.optresearch import runner
    try:
        return await asyncio.to_thread(runner.reveal_holdout, eid, u["username"])
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post(f"{BASE}/configs/export")
async def export(body: ExportIn, request: Request):
    """Export an experiment's configuration as a candidate for production."""
    u = _user(request, ("pm", "quant"))
    from api.quant.optresearch import deploy, runner
    res = runner.load_result(body.experiment_id)
    if res is None:
        raise HTTPException(404, "Unknown experiment.")
    try:
        return deploy.export_candidate(res, body.strategy, u["username"])
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post(f"{BASE}/configs/approve")
async def approve(body: ApproveIn, request: Request):
    """Promote a candidate to production for the Quant Algorithm — administrators only, typed confirmation."""
    u = _user(request, ())
    from api.quant.optresearch import deploy
    try:
        return deploy.approve(body.file, u["username"], body.confirm, body.acknowledge, body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post(f"{BASE}/configs/rollback")
async def rollback(body: RollbackIn, request: Request):
    """Roll a strategy's production configuration back (administrators)."""
    u = _user(request, ())
    from api.quant.optresearch import deploy
    try:
        return deploy.rollback(body.strategy, u["username"], body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get(f"{BASE}/configs/production")
async def production(request: Request):
    """The approved configuration per strategy that the Quant Algorithm should use (read-only)."""
    _user(request)
    from api.quant.optresearch import deploy
    return deploy.production()
