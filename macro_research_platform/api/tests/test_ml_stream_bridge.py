"""The Socket.IO bridge: authentication, idempotent subscription and per-client cleanup.

The broadcaster's own behaviour is covered in test_ml_stream.py, so the broadcaster is replaced
with a stub here and these tests focus on what the transport adds: that an unauthenticated client
never receives a frame, that a closed tab stops being sampled, and that the bridge does not claim
the `disconnect` event it shares with api/main.py.
"""
import asyncio

import pytest

from api.ml import socketio_bridge as bridge
from api.ml import stream


class FakeSio:
    """Records handler registrations and emissions; supports both decorator forms."""

    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.emitted: list[tuple[str, object, object]] = []

    def on(self, event):
        def deco(fn):
            self.handlers[event] = fn
            return fn
        return deco

    def event(self, fn):
        self.handlers[fn.__name__] = fn
        return fn

    async def emit(self, event, data=None, room=None):
        self.emitted.append((event, data, room))

    def sent(self, event):
        return [d for e, d, _ in self.emitted if e == event]


@pytest.fixture
def wired(monkeypatch):
    """A bridge registered against a fake server, with a stub broadcaster and a stub token check."""
    sio = FakeSio()
    started = []

    fake = stream.Broadcaster(channels=[stream.Channel(stream.SYSTEM1, "stub", lambda: {"n": 1}, 2.0)])
    monkeypatch.setattr(fake, "start", lambda: started.append(True))
    monkeypatch.setattr(stream, "_broadcaster", fake)
    monkeypatch.setattr(bridge, "_started", False)
    bridge._sinks.clear()

    cleanup = bridge.register(sio)
    return sio, cleanup, fake, started


def _subscribe(sio, sid, topic=stream.SYSTEM1, token="good"):
    return asyncio.run(sio.handlers[bridge.SUBSCRIBE_EVENT](sid, {"topic": topic, "auth": {"token": token}}))


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    """decode_token is the same verifier the HTTP auth middleware uses."""
    import api.core.access as access
    monkeypatch.setattr(access, "decode_token",
                        lambda t: {"username": "analyst", "role": "analyst"} if t == "good" else None)


def test_register_claims_only_its_own_events(wired):
    """python-socketio keeps one handler per event, so a second `disconnect` here would silently
    replace the one in api/main.py. The bridge returns a cleanup coroutine instead."""
    sio, cleanup, _, _ = wired
    assert set(sio.handlers) == {bridge.SUBSCRIBE_EVENT, bridge.UNSUBSCRIBE_EVENT}
    assert "disconnect" not in sio.handlers
    assert callable(cleanup)


def test_an_unknown_topic_is_refused(wired):
    sio, _, fake, _ = wired
    _subscribe(sio, "sid-1", topic="system3_reasoning")
    errors = sio.sent(bridge.ERROR_EVENT)
    assert errors and errors[0]["error"] == "unknown_topic"
    assert fake.subscriber_count(stream.SYSTEM1) == 0
    assert sio.sent(bridge.ACK_EVENT) == []


@pytest.mark.parametrize("token", [None, "", "revoked", 123])
def test_a_client_without_a_valid_token_receives_nothing(wired, token):
    sio, _, fake, started = wired
    _subscribe(sio, "sid-1", token=token)
    errors = sio.sent(bridge.ERROR_EVENT)
    assert errors and errors[0]["error"] == "unauthorized"
    # the detail must not distinguish missing from malformed from revoked
    assert errors[0]["detail"] == "A valid token is required."
    assert fake.subscriber_count(stream.SYSTEM1) == 0
    assert sio.sent(bridge.ACK_EVENT) == []
    assert started == [], "an unauthenticated client must not start sampling"


def test_a_valid_token_subscribes_and_replays_the_last_state(wired):
    sio, _, fake, started = wired
    asyncio.run(fake.sample(fake._channels[0]))                # a frame exists before subscribing
    _subscribe(sio, "sid-1")

    acks = sio.sent(bridge.ACK_EVENT)
    assert len(acks) == 1
    assert acks[0]["topic"] == stream.SYSTEM1 and acks[0]["user"] == "analyst"
    assert acks[0]["v"] == stream.SCHEMA_VERSION
    assert set(acks[0]["state"]) == {"stub"}, "a new client gets the last frame, not a blank panel"
    assert fake.subscriber_count(stream.SYSTEM1) == 1
    assert started == [True], "the first subscriber starts sampling"
    assert all(room == "sid-1" for _, _, room in sio.emitted)


def test_subscribing_twice_is_idempotent_and_does_not_restart_sampling(wired):
    sio, _, fake, started = wired
    _subscribe(sio, "sid-1")
    _subscribe(sio, "sid-1")
    assert fake.subscriber_count(stream.SYSTEM1) == 1
    assert len(sio.sent(bridge.ACK_EVENT)) == 1
    assert started == [True]


def test_a_second_client_does_not_start_sampling_again(wired):
    sio, _, fake, started = wired
    _subscribe(sio, "sid-1")
    _subscribe(sio, "sid-2")
    assert fake.subscriber_count(stream.SYSTEM1) == 2
    assert started == [True]


def test_unsubscribe_removes_only_that_topic(wired):
    sio, cleanup, fake, _ = wired
    _subscribe(sio, "sid-1", topic=stream.SYSTEM1)
    _subscribe(sio, "sid-1", topic=stream.SYSTEM2)
    assert fake.subscriber_count(stream.SYSTEM1) == 1 and fake.subscriber_count(stream.SYSTEM2) == 1

    asyncio.run(sio.handlers[bridge.UNSUBSCRIBE_EVENT]("sid-1", {"topic": stream.SYSTEM1}))
    assert fake.subscriber_count(stream.SYSTEM1) == 0
    assert fake.subscriber_count(stream.SYSTEM2) == 1, "an unrelated topic must survive"


def test_cleanup_on_disconnect_releases_every_sink_for_that_client(wired):
    """The point of the returned coroutine: a closed tab must stop being sampled."""
    sio, cleanup, fake, _ = wired
    _subscribe(sio, "sid-1", topic=stream.SYSTEM1)
    _subscribe(sio, "sid-1", topic=stream.SYSTEM2)
    _subscribe(sio, "sid-2", topic=stream.SYSTEM1)

    asyncio.run(cleanup("sid-1"))
    assert fake.subscriber_count(stream.SYSTEM2) == 0
    assert fake.subscriber_count(stream.SYSTEM1) == 1, "the other client is still watching"
    assert "sid-1" not in bridge._sinks

    asyncio.run(cleanup("sid-1"))                            # idempotent
    asyncio.run(cleanup("unknown-sid"))                      # never subscribed
    assert fake.subscriber_count(stream.SYSTEM1) == 1


def test_shutdown_clears_state(wired):
    sio, cleanup, fake, _ = wired
    _subscribe(sio, "sid-1")
    asyncio.run(bridge.shutdown())
    assert bridge._sinks == {} and bridge._started is False


def test_a_revoked_session_stops_receiving_frames(wired, monkeypatch):
    """Authorised at subscribe time, revoked later: once the recheck interval passes the client gets
    `unauthorized`, its subscriptions are dropped and no further frame is sent."""
    import api.core.access as access
    sio, _, fake, _ = wired
    _subscribe(sio, "sid-1")
    sink = bridge._sinks["sid-1"][stream.SYSTEM1]
    asyncio.run(sink("ml_frame", {"n": 1}))                              # still valid: delivered
    assert ("ml_frame", {"n": 1}, "sid-1") in sio.emitted
    monkeypatch.setattr(access, "decode_token", lambda t: None)          # the token is revoked
    monkeypatch.setattr(bridge, "RECHECK_SECONDS", 0)
    asyncio.run(sink("ml_frame", {"n": 2}))
    assert ("ml_frame", {"n": 2}, "sid-1") not in sio.emitted
    assert sio.sent(bridge.ERROR_EVENT)[-1]["error"] == "unauthorized"
    assert "sid-1" not in bridge._sinks
