"""Share read-only blocking work without letting client timeouts cancel other callers."""
import asyncio
import weakref
from typing import Callable
from api.workflows.telemetry import count


class WorkCapacityError(RuntimeError):
    pass


# Per-loop state: synchronous access between awaits is atomic on that event loop.
_LOOPS = weakref.WeakKeyDictionary()
MAX_DISTINCT_WORK = 16


async def shared_read(fn: Callable, *args, timeout: float = 45, **kwargs):
    from api.funds import CURRENT
    loop = asyncio.get_running_loop()
    pending = _LOOPS.setdefault(loop, {})
    key = (fn, CURRENT.get(), repr(args), repr(sorted(kwargs.items())))
    task = pending.get(key)
    if task is None:
        if len(pending) >= MAX_DISTINCT_WORK:
            count('upstream.capacity_rejected')
            raise WorkCapacityError('Market data workers are busy; retry shortly.')
        count('upstream.started')
        task = loop.create_task(asyncio.to_thread(fn, *args, **kwargs))
        pending[key] = task

        def done(f):
            if pending.get(key) is f:
                pending.pop(key, None)
            # Retrieve exceptions even if every HTTP waiter has disconnected.
            if not f.cancelled():
                f.exception()

        task.add_done_callback(done)
    else:
        count('upstream.joined')
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout)
    except asyncio.TimeoutError:
        count('upstream.waiter_timeout')
        raise


def status():
    pending=_LOOPS.get(asyncio.get_running_loop(),{})
    return {'inflight':len(pending),'capacity':MAX_DISTINCT_WORK}
