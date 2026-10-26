"""
Controlled hand-off from the options research to the separate Quant Algorithm: versioned, machine-readable
configurations with explicit approval and rollback. Research never changes what is in production by itself.

  config/quant_algo/candidates/<strategy>-v<N>.json   exported from an experiment (any stage; status "candidate")
  config/quant_algo/approved/<strategy>-v<N>.json     immutable once written — a promotion copies the candidate here
  config/quant_algo/production.json                   {"active": {strategy: version file}, "history": [...]}

Promotion requires an administrator, a typed confirmation ("APPROVE <strategy>-v<N>") and, when the configuration did
not survive validation or was not validated on the full (stage 4) universe, an explicit acknowledgement with a reason —
both recorded. Rollback re-activates the previously approved version for that strategy; nothing is deleted.

Schema "quant-algo-options-config/1": strategy_id, version, status, created, created_by, source experiment, data_class,
params, selection_criteria, risk_limits, regimes, validation (segment metrics, survival tests), tests (experiment ids,
stage), data_requirements, known_limitations, content_hash.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3] / "config" / "quant_algo"
SCHEMA = "quant-algo-options-config/1"


def _dirs():
    for d in ("candidates", "approved"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)


def _prod() -> Dict[str, Any]:
    f = ROOT / "production.json"
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {"schema": SCHEMA, "active": {}, "history": []}


def _write_prod(p: Dict[str, Any]) -> None:
    f = ROOT / "production.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=2, default=str))
    tmp.replace(f)


def _next_version(strategy: str) -> int:
    n = 0
    for d in ("candidates", "approved"):
        for f in (ROOT / d).glob(f"{strategy}-v*.json"):
            m = re.search(r"-v(\d+)\.json$", f.name)
            if m:
                n = max(n, int(m.group(1)))
    return n + 1


def _hash(cfg: Dict[str, Any]) -> str:
    body = {k: v for k, v in cfg.items() if k not in ("content_hash", "status", "approval")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def export_candidate(result: Dict[str, Any], strategy: str, user: str) -> Dict[str, Any]:
    """Write a candidate configuration from an experiment result's chosen configuration for `strategy`."""
    _dirs()
    s = (result.get("strategies") or {}).get(strategy)
    if not s:
        raise ValueError(f"The experiment has no result for {strategy}.")
    v = _next_version(strategy)
    stage = int(result.get("stage") or 0)
    cfg = {
        "schema": SCHEMA, "strategy_id": strategy, "version": v, "status": "candidate", "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_by": user, "experiment_id": result.get("experiment_id"), "data_class": s.get("data_class"),
        "params": s["chosen"]["params"], "selection_criteria": s.get("selection_criteria"),
        "risk_limits": result.get("portfolio_defaults"), "regimes": s.get("regimes"),
        "validation": {"development": s["segments"].get("development"), "validation": s["segments"].get("validation"),
                       "walk_forward": s.get("walk_forward", {}).get("metrics"), "survival": s.get("survival"),
                       "overfitting": s.get("overfitting"), "cost_stress": s.get("cost_stress"),
                       "holdout": s["segments"].get("holdout") or "sealed"},
        "tests": {"experiment_ids": [result.get("experiment_id")], "stage": stage,
                  "full_universe_validated": stage >= 4, "universe": result.get("universe")},
        "data_requirements": {"underlying": "daily OHLCV, traded share price, ex-dividend dates",
                              "options": "live option chain with bid/ask, implied volatility and Greeks for strike "
                                         "selection by delta; listed expiries",
                              "signals": s.get("signal_inputs"), "regime_inputs": "VIX term structure, S&P 500 breadth"},
        "known_limitations": result.get("limitations", []) + s.get("limitations", []),
    }
    cfg["content_hash"] = _hash(cfg)
    f = ROOT / "candidates" / f"{strategy}-v{v}.json"
    f.write_text(json.dumps(cfg, indent=2, default=str))
    return {"file": str(f.relative_to(ROOT.parent.parent)), "config": cfg}


def list_configs() -> Dict[str, Any]:
    _dirs()
    out: Dict[str, List[Dict[str, Any]]] = {"candidates": [], "approved": []}
    for d in out:
        for f in sorted((ROOT / d).glob("*.json")):
            try:
                c = json.loads(f.read_text())
            except ValueError:
                continue
            out[d].append({"file": f.name, "strategy_id": c.get("strategy_id"), "version": c.get("version"),
                           "status": c.get("status"), "created": c.get("created"), "experiment_id": c.get("experiment_id"),
                           "stage": (c.get("tests") or {}).get("stage"),
                           "survived": ((c.get("validation") or {}).get("survival") or {}).get("survived"),
                           "approval": c.get("approval"), "params": c.get("params"), "data_class": c.get("data_class")})
    return {**out, "production": _prod()}


def approve(file: str, user: str, confirm: str, acknowledge: bool = False, reason: str = "") -> Dict[str, Any]:
    """Promote a candidate. Requires confirm == "APPROVE <strategy>-v<N>"; a configuration that failed validation or
    lacks a full-universe test also requires acknowledge=True and a reason."""
    _dirs()
    src = ROOT / "candidates" / Path(file).name
    if not src.exists():
        raise ValueError("No such candidate configuration.")
    cfg = json.loads(src.read_text())
    tag = f"{cfg['strategy_id']}-v{cfg['version']}"
    if confirm.strip() != f"APPROVE {tag}":
        raise ValueError(f'Type "APPROVE {tag}" to confirm.')
    if _hash(cfg) != cfg.get("content_hash"):
        raise ValueError("The candidate file was modified after export (hash mismatch) — export it again.")
    warnings = []
    if not ((cfg.get("validation") or {}).get("survival") or {}).get("survived"):
        warnings.append("did not survive the pre-declared validation criteria")
    if not (cfg.get("tests") or {}).get("full_universe_validated"):
        warnings.append("not validated on the full (stage 4) universe")
    if warnings and not (acknowledge and reason.strip()):
        raise ValueError("This configuration " + " and ".join(warnings) + ". Approving it needs an explicit "
                         "acknowledgement and a reason.")
    dst = ROOT / "approved" / src.name
    if dst.exists():
        raise ValueError("This version is already approved (approved files are immutable).")
    cfg["status"] = "approved"
    cfg["approval"] = {"by": user, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "warnings": warnings, "reason": reason}
    dst.write_text(json.dumps(cfg, indent=2, default=str))
    p = _prod()
    prev = p["active"].get(cfg["strategy_id"])
    p["active"][cfg["strategy_id"]] = dst.name
    p["history"].append({"at": cfg["approval"]["at"], "by": user, "action": "approve", "strategy": cfg["strategy_id"],
                         "to": dst.name, "from": prev, "warnings": warnings, "reason": reason})
    _write_prod(p)
    return {"approved": dst.name, "previous": prev, "warnings": warnings}


def rollback(strategy: str, user: str, reason: str = "") -> Dict[str, Any]:
    p = _prod()
    cur = p["active"].get(strategy)
    if not cur:
        raise ValueError(f"No active configuration for {strategy}.")
    approvals = [h["to"] for h in p["history"] if h["strategy"] == strategy and h["action"] == "approve"]
    i = max((k for k, v in enumerate(approvals) if v == cur), default=0)
    target = approvals[i - 1] if i > 0 else None                  # the approval before the current one
    if target:
        p["active"][strategy] = target
    else:
        p["active"].pop(strategy)
    p["history"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": user, "action": "rollback", "strategy": strategy,
                         "to": target, "from": cur, "reason": reason})
    _write_prod(p)
    return {"strategy": strategy, "active": target, "was": cur}


def production() -> Dict[str, Any]:
    """What the Quant Algorithm should run: the active approved configuration per strategy (full documents)."""
    p = _prod()
    out = {}
    for s, f in p["active"].items():
        try:
            out[s] = json.loads((ROOT / "approved" / f).read_text())
        except (OSError, ValueError):
            out[s] = {"error": f"missing approved file {f}"}
    return {"schema": SCHEMA, "active": out, "history": p["history"][-50:]}
