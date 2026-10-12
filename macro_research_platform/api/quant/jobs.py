"""
Background jobs for long Code Lab work (large-universe strategies run in the sandbox): one id per job,
a lifecycle (queued → running → done | failed | cancelled), progress text, cancellation that kills the
sandbox process, and bounded concurrency. Jobs live in memory — a restart loses them (the client sees
'unknown job' and can run again); results are not trading records.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

MAX_PARALLEL = 2
KEEP_S = 3600
_pool = ThreadPoolExecutor(MAX_PARALLEL, thread_name_prefix="quant-job")
_jobs: Dict[str, "Job"] = {}
_lock = threading.Lock()


class Job:
    def __init__(self, owner: str, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.owner, self.kind = owner, kind
        self.state = "queued"
        self.message = "Waiting for a free worker…"
        self.created = time.time()
        self.started: Optional[float] = None
        self.finished: Optional[float] = None
        self.result: Any = None
        self.error: Optional[str] = None
        self.cancelled = False

    def progress(self, message: str) -> None:
        self.message = message

    def view(self, with_result: bool = True) -> Dict[str, Any]:
        out = {"id": self.id, "kind": self.kind, "state": self.state, "message": self.message, "error": self.error,
               "elapsed_s": round((self.finished or time.time()) - (self.started or self.created), 1)}
        if with_result and self.state == "done":
            out["result"] = self.result
        return out


def submit(owner: str, kind: str, fn: Callable[["Job"], Any]) -> Job:
    job = Job(owner, kind)
    with _lock:
        now = time.time()
        for k in [k for k, j in _jobs.items() if j.finished and now - j.finished > KEEP_S]:
            _jobs.pop(k, None)
        running = sum(1 for j in _jobs.values() if j.owner == owner and j.state in ("queued", "running"))
        if running >= 2:
            raise ValueError("You already have two jobs running — wait for one or cancel it.")
        _jobs[job.id] = job

    def run():
        if job.cancelled:
            job.state, job.finished = "cancelled", time.time()
            return
        job.state, job.started = "running", time.time()
        try:
            job.result = fn(job)
            job.state = "cancelled" if job.cancelled else "done"
        except Exception as e:                                   # noqa: BLE001 — reported to the user
            job.state = "cancelled" if job.cancelled else "failed"
            job.error = str(e)[:600]
        finally:
            job.finished = time.time()
            job.message = {"done": "Finished.", "cancelled": "Cancelled.", "failed": "Failed."}.get(job.state, job.message)
    _pool.submit(run)
    return job


def get(job_id: str, owner: str, is_admin: bool = False) -> Optional[Job]:
    j = _jobs.get(job_id)
    return j if j and (j.owner == owner or is_admin) else None


def cancel(job_id: str, owner: str, is_admin: bool = False) -> bool:
    j = get(job_id, owner, is_admin)
    if not j or j.state in ("done", "failed", "cancelled"):
        return False
    j.cancelled = True
    j.message = "Cancelling…"
    return True
