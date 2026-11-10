"""Socket.IO transport for api/ml/stream.py.

Kept out of api/main.py on purpose: that module is already the largest assembler in the repo, and
registering from here costs it two calls instead of another hundred lines.

Authentication is not optional here. Every REST endpoint these payloads come from calls
web.user(request, None), which requires a signed-in user. A push channel carrying the same data
has to check the same thing or it becomes an unauthenticated bypass — the /ws/prices websocket
already accepts any connection, and this is not going to repeat that.

Note on `disconnect`: python-socketio stores one handler per event, so registering a second
`disconnect` here would silently overwrite the one in api/main.py (or be overwritten by it,
depending on import order). `register()` therefore returns a cleanup coroutine for main.py's
existing handler to await, rather than claiming the event.
"""
from __future__ import annotations

import time

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from api.ml import stream

logger = logging.getLogger(__name__)

#: What a client sends to subscribe. The token is a bearer JWT, the same one the REST API uses,
#: and it travels in the subscribe payload rather than the handshake so an unauthenticated client
#: can connect and simply never receive a frame.
SUBSCRIBE_EVENT = "subscribe_ml_stream"
UNSUBSCRIBE_EVENT = "unsubscribe_ml_stream"
ERROR_EVENT = "ml_stream_error"
ACK_EVENT = "ml_stream_state"

#: sid -> topic -> sink, so a disconnect can always find what to unsubscribe.
_sinks: Dict[str, Dict[str, stream.Sink]] = {}
_started: bool = False


#: How often a live subscription's token is re-validated.
RECHECK_SECONDS = 60


def _identity(auth: Any) -> Optional[Dict[str, Any]]:
    from api.core.access import decode_token

    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        return None
    return decode_token(token)


def register(sio: Any) -> Callable[[str], Awaitable[None]]:
    """Attach the subscribe/unsubscribe handlers; returns the per-client cleanup coroutine."""

    @sio.on(SUBSCRIBE_EVENT)
    async def subscribe_ml_stream(sid: str, data: Any) -> None:
        global _started
        payload = data if isinstance(data, dict) else {}
        topic = payload.get("topic")
        if topic not in stream.TOPICS:
            await sio.emit(ERROR_EVENT, {"error": "unknown_topic",
                                         "detail": f"topic must be one of {list(stream.TOPICS)}"},
                           room=sid)
            return

        user = _identity(payload.get("auth"))
        if user is None:
            # Say why without revealing whether the token was missing, malformed or revoked.
            await sio.emit(ERROR_EVENT, {"error": "unauthorized",
                                         "detail": "A valid token is required."}, room=sid)
            return

        mine = _sinks.setdefault(sid, {})
        if topic in mine:
            return                                            # idempotent

        auth = payload.get("auth")
        checked = {"at": time.monotonic()}

        async def sink(event: str, frame: Dict[str, Any]) -> None:
            # A subscription outlives the moment it was authorised: re-check the token (expiry, revocation,
            # disabled account, password change) at most once per RECHECK_SECONDS before sending more frames.
            if time.monotonic() - checked["at"] >= RECHECK_SECONDS:
                checked["at"] = time.monotonic()
                if _identity(auth) is None:
                    for t, fn in _sinks.pop(sid, {}).items():
                        stream.broadcaster().unsubscribe(t, fn)
                    await sio.emit(ERROR_EVENT, {"error": "unauthorized", "detail": "Session ended; sign in again."}, room=sid)
                    return
            await sio.emit(event, frame, room=sid)

        state = stream.broadcaster().subscribe(topic, sink)
        mine[topic] = sink

        if not _started:
            stream.broadcaster().start()                      # sampling begins with the first reader
            _started = True
            logger.info("[ml-stream] sampling started")

        # Hand back the last frame per channel at once, so the panel is not blank until the next
        # sample lands.
        await sio.emit(ACK_EVENT, {**state, "user": user.get("username")}, room=sid)

    @sio.on(UNSUBSCRIBE_EVENT)
    async def unsubscribe_ml_stream(sid: str, data: Any) -> None:
        topic = data.get("topic") if isinstance(data, dict) else None
        sink = _sinks.get(sid, {}).pop(topic, None) if topic in stream.TOPICS else None
        if sink is not None:
            stream.broadcaster().unsubscribe(topic, sink)

    async def cleanup(sid: str) -> None:
        """Drop every sink belonging to this client.

        Without it a closed tab stays registered: the broadcaster would keep emitting into a dead
        room and, worse, keep sampling a topic nobody is watching — the one cost the demand-driven
        design exists to avoid.
        """
        for topic, sink in _sinks.pop(sid, {}).items():
            stream.broadcaster().unsubscribe(topic, sink)

    return cleanup


async def shutdown() -> None:
    """Stop the sampling loops. Called from the app's lifespan shutdown."""
    global _started
    await stream.broadcaster().stop()
    _sinks.clear()
    _started = False
