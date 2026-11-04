"""
Operations monitor: know when a data feed fails or the numbers stop matching independent sources, without having to
look.

  feeds   every 10 minutes the source-health probe runs; a change of state (live → degraded / down, or back) is
          recorded as an event — the in-app alerts pick events up, so a stuck feed is noticed in minutes, not days
  audit   after each US close the accuracy audit (scripts/audit_accuracy.py) runs against this server; its pass /
          fail counts are recorded, and any FAIL becomes an event

Events are kept in data/processed/monitor/events.jsonl (append-only, last 2,000 kept) — the same evidence an
operational due-diligence reviewer asks for: incidents, when they started, when they were resolved.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "processed" / "monitor"
_lock = threading.Lock()
RANK = {"live": 0, "connected": 0, "degraded": 1, "down": 2, "off": 0}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(ev: Dict[str, Any]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / "events.jsonl"
    with _lock:
        lines = path.read_text().splitlines() if path.exists() else []
        lines.append(json.dumps(ev))
        path.write_text("\n".join(lines[-2000:]) + "\n")


def events(limit: int = 50) -> List[Dict[str, Any]]:
    path = DIR / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]


def check_feeds() -> List[Dict[str, Any]]:
    """Probe every source and record state changes. Returns the new events."""
    from api import health_sources
    h = health_sources.get_sources_health(force=True)
    state_path = DIR / "feed_state.json"
    try:
        prev = json.loads(state_path.read_text())
    except Exception:
        prev = {}
    new, cur = [], {}
    for name, s in (h.get("sources") or {}).items():
        st = s.get("status") or "unknown"
        cur[name] = st
        before = prev.get(name)
        if before is not None and before != st:
            worse = RANK.get(st, 1) > RANK.get(before, 1)
            ev = {"time": _now(), "kind": "feed", "source": name, "from": before, "to": st,
                  "severity": "critical" if st == "down" else "warning" if worse else "resolved",
                  "detail": str(s.get("detail") or "")[:200]}
            new.append(ev)
            _append(ev)
    DIR.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(cur))
    return new


def run_audit(base: Optional[str] = None, timeout_s: int = 1800) -> Dict[str, Any]:
    """Run the accuracy audit against this server and record its counts (and any failures) as events."""
    port = os.getenv("RUNTIME_API_PORT") or "8000"
    base = base or f"http://127.0.0.1:{port}"
    out_dir = ROOT / "data" / "processed" / "audit"
    t0 = time.time()
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_accuracy.py"), "--base", base, "--out", str(out_dir)],
                       cwd=str(ROOT), timeout=timeout_s, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        ev = {"time": _now(), "kind": "audit", "severity": "warning", "detail": f"accuracy audit timed out after {timeout_s}s"}
        _append(ev)
        return ev
    reports = sorted(out_dir.glob("accuracy_*.json"), key=lambda p: p.stat().st_mtime)
    if not reports or reports[-1].stat().st_mtime < t0:
        ev = {"time": _now(), "kind": "audit", "severity": "warning", "detail": "accuracy audit produced no report"}
        _append(ev)
        return ev
    rep = json.loads(reports[-1].read_text())
    counts = rep.get("counts") or {}
    fails = [r for r in rep.get("results") or [] if r.get("status") in ("FAIL", "ERROR")]
    ev = {"time": _now(), "kind": "audit", "severity": "critical" if fails else "ok", "counts": counts,
          "report": reports[-1].name, "seconds": round(time.time() - t0),
          "failures": [{"check": r.get("check") or r.get("name"), "detail": str(r.get("detail") or r.get("note") or "")[:160]}
                       for r in fails[:12]],
          "detail": f"{counts.get('PASS', 0)} pass, {counts.get('FAIL', 0)} fail, {counts.get('ERROR', 0)} error, {counts.get('WARN', 0)} warn"}
    _append(ev)
    return ev


def summary() -> Dict[str, Any]:
    evs = events(200)
    audits = [e for e in evs if e.get("kind") == "audit"]
    try:
        state = json.loads((DIR / "feed_state.json").read_text())
    except Exception:
        state = {}
    # open incidents: the latest event per source that is not resolved
    open_inc: Dict[str, Dict[str, Any]] = {}
    for e in reversed(evs):
        if e.get("kind") == "feed":
            if e["severity"] == "resolved":
                open_inc.pop(e["source"], None)
            else:
                open_inc[e["source"]] = e
    return {"feeds": state, "open_incidents": list(open_inc.values()), "last_audit": audits[0] if audits else None,
            "events": evs[:50],
            "note": "Feeds are probed every 10 minutes; the accuracy audit runs after each US close (22:30 UTC, weekdays)."}
