"""The ML push stream: envelope, failure-as-data, demand-driven sampling and bounded kicks.

These matter because the stream replaces polling for a panel people read live. A frame that
silently carried a fabricated zero would be worse than the poll it replaced, and an unwatched
dashboard that kept triggering inference subprocesses would be a cost with no reader.
"""
import asyncio

import pytest

from api.ml import stream
from api.ml.stream import SYSTEM1, SYSTEM2, Broadcaster, Channel, Frame


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def channel(name="deep_live", topic=SYSTEM1, sample=None, interval=2.0, **kw):
    return Channel(topic, name, sample or (lambda: {"ok": True}), interval, **kw)


# ── envelope and validation ──────────────────────────────────────────────────────────────────
def test_frame_envelope_carries_the_schema_version_and_a_monotonic_seq():
    frame = Frame(SYSTEM1, "deep_live", 7, True, payload={"a": 1}, computed_ms=3.5)
    body = frame.to_json()
    assert body["v"] == stream.SCHEMA_VERSION
    assert body["topic"] == SYSTEM1 and body["channel"] == "deep_live"
    assert body["seq"] == 7 and body["ok"] is True and body["payload"] == {"a": 1}
    assert body["error"] is None and body["computed_ms"] == 3.5
    assert body["sent_at"]                                  # an ISO timestamp, not None


def test_channel_rejects_an_unknown_topic_or_a_nonsense_cadence():
    with pytest.raises(ValueError, match="Unknown topic"):
        Channel("system3", "x", lambda: None, 1.0)
    with pytest.raises(ValueError, match="positive interval"):
        Channel(SYSTEM1, "x", lambda: None, 0.0)
    with pytest.raises(ValueError, match="kick cannot fire more often"):
        channel(kick=lambda: None, kick_interval=1.0, interval=2.0)


def test_the_default_registry_covers_both_topics_and_only_kicks_the_deep_channel():
    channels = stream._channels()
    assert {(c.topic, c.name) for c in channels} == {
        (SYSTEM1, "deep_live"), (SYSTEM1, "online_status"),
        (SYSTEM2, "research_graph"), (SYSTEM2, "autonomous_status"),
    }
    # exactly one channel has a side effect, and it is the self-coalescing inference refresh
    kicking = [c.name for c in channels if c.kick is not None]
    assert kicking == ["deep_live"]
    assert all(c.interval > 0 for c in channels)


def test_a_duplicate_channel_name_within_a_topic_is_refused():
    with pytest.raises(ValueError, match="Duplicate channel"):
        Broadcaster(channels=[channel(), channel()])


# ── failure is data, not an exception ────────────────────────────────────────────────────────
def test_a_failing_producer_yields_an_error_frame_rather_than_raising():
    def boom():
        raise RuntimeError("checkpoint unreadable")

    b = Broadcaster(channels=[channel(sample=boom)])
    frame = asyncio.run(b.sample(b._channels[0]))
    assert frame.ok is False and frame.payload is None
    assert "RuntimeError" in frame.error and "checkpoint unreadable" in frame.error
    assert frame.seq == 1


def test_a_blocking_producer_runs_off_the_event_loop():
    calls = []

    def slow():
        calls.append("thread")
        return {"value": 42}

    b = Broadcaster(channels=[channel(sample=slow, blocking=True)])
    frame = asyncio.run(b.sample(b._channels[0]))
    assert frame.ok and frame.payload == {"value": 42} and calls == ["thread"]


def test_sequence_numbers_advance_per_channel_and_a_gap_is_detectable():
    b = Broadcaster(channels=[channel(name="a"), channel(name="b", topic=SYSTEM2)])
    a, bb = b._channels

    async def run():
        return [await b.sample(a), await b.sample(a), await b.sample(bb)]

    fa, fa2, fb = asyncio.run(run())
    assert (fa.seq, fa2.seq, fb.seq) == (1, 2, 1)      # per channel, not global


# ── subscription semantics ───────────────────────────────────────────────────────────────────
def test_subscribing_replays_the_last_frame_so_a_new_client_is_not_blank():
    b = Broadcaster(channels=[channel()])
    asyncio.run(b.sample(b._channels[0]))
    seen = []

    async def sink(event, frame):
        seen.append((event, frame))

    state = b.subscribe(SYSTEM1, sink)
    assert state["v"] == stream.SCHEMA_VERSION and state["topic"] == SYSTEM1
    assert set(state["state"]) == {"deep_live"}
    assert state["state"]["deep_live"]["ok"] is True
    assert b.subscriber_count(SYSTEM1) == 1 and b.subscriber_count(SYSTEM2) == 0


def test_unsubscribing_is_idempotent_and_rejects_an_unknown_topic():
    b = Broadcaster(channels=[channel()])

    async def sink(event, frame):
        pass

    b.subscribe(SYSTEM1, sink)
    b.unsubscribe(SYSTEM1, sink)
    b.unsubscribe(SYSTEM1, sink)                       # no KeyError
    assert b.subscriber_count(SYSTEM1) == 0
    with pytest.raises(ValueError, match="Unknown topic"):
        b.subscribe("system3", sink)


def test_a_failing_sink_is_dropped_without_stalling_the_others():
    b = Broadcaster(channels=[channel()])
    got = []

    async def bad(event, frame):
        raise ConnectionResetError("client vanished")

    async def good(event, frame):
        got.append(frame["seq"])

    b.subscribe(SYSTEM1, bad)
    b.subscribe(SYSTEM1, good)

    async def run():
        frame = await b.sample(b._channels[0])
        await b._emit(SYSTEM1, "x", frame.to_json())
        frame2 = await b.sample(b._channels[0])
        await b._emit(SYSTEM1, "x", frame2.to_json())

    asyncio.run(run())
    assert b.subscriber_count(SYSTEM1) == 1            # the dead sink was removed
    assert got == [1, 2]                               # the healthy one kept receiving


# ── demand-driven sampling and bounded kicks ─────────────────────────────────────────────────
def test_no_subscribers_means_no_sampling_and_no_side_effect():
    samples, kicks = [], []
    clock = FakeClock()

    async def sleeper(seconds):
        clock.advance(seconds)
        if clock.now > 1010:
            raise asyncio.CancelledError

    b = Broadcaster(
        channels=[channel(sample=lambda: samples.append(1) or {}, kick=lambda: kicks.append(1))],
        clock=clock, sleep=sleeper,
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(b.run_topic(SYSTEM1))
    assert samples == [] and kicks == [], "an unwatched topic must cost nothing"


def test_a_subscriber_starts_sampling_and_the_kick_is_rate_limited():
    samples, kicks, received = [], [], []
    clock = FakeClock()
    stop = {"at": 1000.0 + 130.0}

    async def sleeper(seconds):
        clock.advance(seconds)
        if clock.now >= stop["at"]:
            raise asyncio.CancelledError

    async def sink(event, frame):
        received.append((event, frame["seq"], frame["ok"]))

    b = Broadcaster(
        channels=[channel(sample=lambda: samples.append(clock.now) or {"t": clock.now},
                          interval=2.0, kick=lambda: kicks.append(clock.now),
                          kick_interval=60.0)],
        clock=clock, sleep=sleeper,
    )
    b.subscribe(SYSTEM1, sink)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(b.run_topic(SYSTEM1))

    assert samples, "a subscribed topic must sample"
    # ~130s at a 2s cadence, allowing the loop's own sleep granularity
    assert 30 <= len(samples) <= 70, len(samples)
    # the kick is bounded to once per 60s even though the channel samples every 2s
    assert 2 <= len(kicks) <= 4, kicks
    assert all(e == f"{SYSTEM1}:deep_live" for e, _, _ in received)
    assert [s for _, s, _ in received] == list(range(1, len(received) + 1))
    assert all(ok for _, _, ok in received)


def test_the_kick_does_not_fire_before_its_interval_even_with_many_samples():
    kicks = []
    clock = FakeClock()
    b = Broadcaster(
        channels=[channel(sample=lambda: {}, interval=1.0, kick=lambda: kicks.append(clock.now),
                          kick_interval=60.0)],
        clock=clock,
    )
    ch = b._channels[0]

    async def run():
        for _ in range(10):                            # ten samples inside ten seconds
            await b._maybe_kick(ch)
            clock.advance(1.0)

    asyncio.run(run())
    assert len(kicks) == 1, kicks


def test_topics_are_sampled_independently():
    b = Broadcaster(channels=[channel(name="a", topic=SYSTEM1), channel(name="b", topic=SYSTEM2)])
    assert {c.topic for c in b._channels} == {SYSTEM1, SYSTEM2}
    fa = asyncio.run(b.sample(b._channels[0]))
    assert fa.topic == SYSTEM1 and fa.channel == "a"
    # sampling one topic's channel leaves the other's snapshot untouched
    assert b.subscribe(SYSTEM2, _noop)["state"] == {}


async def _noop(event, frame):
    pass
