"""
Background jobs for long Code Lab work (large-universe strategies run in the sandbox): one id per job,
a lifecycle (queued → running → done | failed | cancelled | interrupted), progress text, cancellation that
kills the sandbox process, and bounded concurrency. Every state change is written to the app database
(quant_jobs), so finished results survive a restart; jobs that were running when the server stopped are
marked 'interrupted' on startup (their process is gone) and can simply be run again.
"""
from __future__ import annotations

import json
import sqlite3
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


_ready = False


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS quant_jobs (id TEXT PRIMARY KEY, owner TEXT, kind TEXT, state TEXT,
                     message TEXT, error TEXT, created REAL, started REAL, finished REAL, result TEXT)""")
        # a process restart kills running jobs: say so instead of leaving them 'running' forever
        c.execute("UPDATE quant_jobs SET state = 'interrupted', message = 'The server restarted while this job ran — run it again.', "
                  "finished = ? WHERE state IN ('queued', 'running')", (time.time(),))
        c.execute("DELETE FROM quant_jobs WHERE finished IS NOT NULL AND finished < ?", (time.time() - 7 * 86400,))
    _ready = True


def _save(job: "Job") -> None:
    try:
        _init()
        with _conn() as c:
            c.execute("INSERT INTO quant_jobs (id, owner, kind, state, message, error, created, started, finished, result) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state, message=excluded.message, "
                      "error=excluded.error, started=excluded.started, finished=excluded.finished, result=excluded.result",
                      (job.id, job.owner, job.kind, job.state, job.message, job.error, job.created, job.started, job.finished,
                       json.dumps(job.result, default=str) if job.state == "done" else None))
    except Exception:                                          # noqa: BLE001 — persistence must not break the job
        pass


def _load(job_id: str) -> Optional["Job"]:
    try:
        _init()
        with _conn() as c:
            r = c.execute("SELECT * FROM quant_jobs WHERE id = ?", (job_id,)).fetchone()
    except Exception:                                          # noqa: BLE001
        return None
    if not r:
        return None
    j = Job(r["owner"], r["kind"])
    j.id, j.state, j.message, j.error = r["id"], r["state"], r["message"], r["error"]
    j.created, j.started, j.finished = r["created"], r["started"], r["finished"]
    j.result = json.loads(r["result"]) if r["result"] else None
    return j


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
    _save(job)

    def run():
        if job.cancelled:
            job.state, job.finished = "cancelled", time.time()
            return
        job.state, job.started = "running", time.time()
        _save(job)
        try:
            job.result = fn(job)
            job.state = "cancelled" if job.cancelled else "done"
        except Exception as e:                                   # noqa: BLE001 — reported to the user
            job.state = "cancelled" if job.cancelled else "failed"
            job.error = str(e)[:600]
        finally:
            job.finished = time.time()
            job.message = {"done": "Finished.", "cancelled": "Cancelled.", "failed": "Failed."}.get(job.state, job.message)
            _save(job)
    _pool.submit(run)
    return job


def get(job_id: str, owner: str, is_admin: bool = False) -> Optional[Job]:
    j = _jobs.get(job_id) or _load(job_id)
    return j if j and (j.owner == owner or is_admin) else None


def cancel(job_id: str, owner: str, is_admin: bool = False) -> bool:
    j = get(job_id, owner, is_admin)
    if not j or j.state in ("done", "failed", "cancelled", "interrupted") or job_id not in _jobs:
        return False
    j.cancelled = True
    j.message = "Cancelling…"
    return True
