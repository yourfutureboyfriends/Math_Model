"""Push transport for the ML observability state the UI currently polls.

Two topics, because their natural rates differ by an order of magnitude and mixing them means
either starving the research view or flooding it:

  system1_inference   fast matrix-inference state   (deep live trace, provider supervisor)
  system2_reasoning   slow research state           (research graph, autonomous challenger)

Payloads are the same objects the REST endpoints in api/routers/macro_extras.py return, produced
by the same functions, so the stream and the polled route cannot disagree about what the system
is doing. Nothing here fabricates a value: a builder that raises is forwarded as a frame with
ok=False and the error text, and the client keeps showing the last good frame rather than a
plausible-looking zero.

Sampling is demand-driven and bounded. A topic is only sampled while it has at least one
subscriber, so an unwatched dashboard costs nothing. The single channel with a side effect,
api.ml.live.request_refresh, is already coalesced at its source to at most one bounded subprocess
per minute and returns immediately; driving it from the subscriber count matches the cadence that
api/ml/live.py:status() already documents ("refreshes at most once per minute while this view is
open").

Frames are last-value, not queued: if a channel produces faster than a client drains, the client
sees the newest state and the frame sequence number tells it that it skipped some. For a live
instrument panel that is the correct trade — a backlog of stale network states is worse than a gap.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Bump when the envelope changes shape. Clients reject a version they do not understand rather
#: than silently mis-reading a field.
SCHEMA_VERSION = 1

SYSTEM1 = "system1_inference"
SYSTEM2 = "system2_reasoning"
TOPICS: Tuple[str, ...] = (SYSTEM1, SYSTEM2)

#: A sink receives one encoded frame per sample. Kept as a plain callable so the transport
#: (Socket.IO room emit, a test spy, a log line) is not this module's business.
Sink = Callable[[str, Dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Channel:
    """One sampled stream of state.

    sample      read-only producer; must not mutate system state
    interval    seconds between samples while the topic has subscribers
    blocking    run sample in a worker thread (it touches the filesystem or sqlite)
    kick        optional side effect invoked once per `kick_interval`, e.g. asking the deep
                inference worker to remeasure. Must be self-limiting at its source.
    """

    topic: str
    name: str
    sample: Callable[[], Any]
    interval: float
    blocking: bool = False
    kick: Optional[Callable[[], Any]] = None
    kick_interval: float = 60.0

    def __post_init__(self) -> None:
        if self.topic not in TOPICS:
            raise ValueError(f"Unknown topic {self.topic!r}")
        if not self.name or self.interval <= 0:
            raise ValueError("A channel needs a name and a positive interval")
        if self.kick is not None and self.kick_interval < self.interval:
            raise ValueError("A kick cannot fire more often than the channel is sampled")


def _channels() -> Tuple[Channel, ...]:
    """Built lazily: importing the ML modules pulls in torch-adjacent dependency chains."""
    from api.ml import live, online
    from api.ml.autonomous import status as autonomous_status
    from api.ml.research_graph import build as research_graph_build

    return (
        # System 1 — the measured network state, and the provider supervisor feeding it.
        Channel(SYSTEM1, "deep_live", live.status, interval=2.0, blocking=True,
                kick=live.request_refresh, kick_interval=60.0),
        Channel(SYSTEM1, "online_status", online.status, interval=30.0),
        # System 2 — slow research: the causal/research graph and the autonomous challenger.
        Channel(SYSTEM2, "research_graph", research_graph_build, interval=30.0, blocking=True),
        Channel(SYSTEM2, "autonomous_status", autonomous_status, interval=5.0, blocking=True),
    )


@dataclass
class Frame:
    """One encoded sample. `seq` is per channel and monotonic, so a client can tell a gap from
    a repeat without needing a clock."""

    topic: str
    channel: str
    seq: int
    ok: bool
    payload: Any = None
    error: Optional[str] = None
    computed_ms: Optional[float] = None
    sent_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    )

    def to_json(self) -> Dict[str, Any]:
        return {
            "v": SCHEMA_VERSION,
            "topic": self.topic,
            "channel": self.channel,
            "seq": self.seq,
            "ok": self.ok,
            "payload": self.payload,
            "error": self.error,
            "computed_ms": self.computed_ms,
            "sent_at": self.sent_at,
        }


class Broadcaster:
    """Samples the channels of a topic while it has subscribers, and fans frames out.

    Deliberately transport-agnostic and injectable: `channels`, `clock` and `sleep` are
    constructor arguments so the whole loop is testable without waiting on a wall clock or
    touching the ML modules.
    """

    def __init__(
        self,
        channels: Optional[Sequence[Channel]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        to_thread: Callable[..., Awaitable[Any]] = asyncio.to_thread,
    ) -> None:
        self._channels: Tuple[Channel, ...] = tuple(channels) if channels is not None else _channels()
        names = [(c.topic, c.name) for c in self._channels]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate channel name within a topic")
        self._clock, self._sleep, self._to_thread = clock, sleep, to_thread
        self._sinks: Dict[str, set[Sink]] = {t: set() for t in TOPICS}
        self._seq: Dict[Tuple[str, str], int] = {}
        self._next_kick: Dict[Tuple[str, str], float] = {}
        self._latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._tasks: Dict[str, asyncio.Task[None]] = {}

    # ── subscription ────────────────────────────────────────────────────────────────────
    def subscribe(self, topic: str, sink: Sink) -> Dict[str, Any]:
        """Register a sink and hand back the last frame per channel, so a new client is not
        staring at an empty panel until the next sample."""
        if topic not in TOPICS:
            raise ValueError(f"Unknown topic {topic!r}")
        self._sinks[topic].add(sink)
        snapshot = {
            name: frame
            for (t, name), frame in self._latest.items()
            if t == topic
        }
        return {"v": SCHEMA_VERSION, "topic": topic, "state": snapshot}

    def unsubscribe(self, topic: str, sink: Sink) -> None:
        self._sinks.get(topic, set()).discard(sink)

    def subscriber_count(self, topic: str) -> int:
        return len(self._sinks.get(topic, ()))

    # ── sampling ────────────────────────────────────────────────────────────────────────
    async def sample(self, channel: Channel) -> Frame:
        """Run one channel's producer and wrap the result, capturing failure as data."""
        key = (channel.topic, channel.name)
        self._seq[key] = seq = self._seq.get(key, 0) + 1
        started = self._clock()
        try:
            payload = await self._to_thread(channel.sample) if channel.blocking else channel.sample()
            frame = Frame(channel.topic, channel.name, seq, True, payload=payload,
                          computed_ms=round((self._clock() - started) * 1000, 2))
        except Exception as exc:                                     # noqa: BLE001 — a broken
            logger.warning("[ml-stream] %s/%s failed: %s", *key, exc)  # channel must not kill the rest
            frame = Frame(channel.topic, channel.name, seq, False,
                          error=f"{type(exc).__name__}: {exc}",
                          computed_ms=round((self._clock() - started) * 1000, 2))
        self._latest[key] = frame.to_json()
        return frame

    async def _maybe_kick(self, channel: Channel) -> None:
        if channel.kick is None:
            return
        key = (channel.topic, channel.name)
        now = self._clock()
        if now < self._next_kick.get(key, 0.0):
            return
        self._next_kick[key] = now + channel.kick_interval
        try:
            await self._to_thread(channel.kick)
        except Exception as exc:                                     # noqa: BLE001
            logger.warning("[ml-stream] %s/%s kick failed: %s", *key, exc)

    async def _emit(self, topic: str, event: str, frame: Dict[str, Any]) -> None:
        # Iterate a copy: a sink may unsubscribe itself while being awaited.
        for sink in list(self._sinks.get(topic, ())):
            try:
                await sink(event, frame)
            except Exception as exc:                                 # noqa: BLE001 — one dead
                logger.info("[ml-stream] dropping a failing sink: %s", exc)  # client must not stall
                self._sinks[topic].discard(sink)

    async def run_topic(self, topic: str) -> None:
        """Sample every channel of `topic` on its own cadence, only while subscribed."""
        channels = [c for c in self._channels if c.topic == topic]
        due = {c.name: 0.0 for c in channels}
        while True:
            if not self._sinks[topic]:
                await self._sleep(1.0)          # idle: no subscribers, no sampling, no side effects
                for c in channels:
                    due[c.name] = 0.0           # re-arm so a new subscriber gets a prompt sample
                continue
            now = self._clock()
            runnable = [c for c in channels if now >= due[c.name]]
            if runnable:
                # Independent channels sample concurrently; a slow filesystem read on one must
                # not delay the others.
                for c in runnable:
                    due[c.name] = now + c.interval
                await self._maybe_kick_all(runnable)
                frames = await asyncio.gather(*(self.sample(c) for c in runnable))
                for frame in frames:
                    await self._emit(topic, f"{topic}:{frame.channel}", frame.to_json())
            await self._sleep(min(c.interval for c in channels))

    async def _maybe_kick_all(self, channels: Iterable[Channel]) -> None:
        for channel in channels:
            await self._maybe_kick(channel)

    # ── lifecycle ───────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        for topic in TOPICS:
            if topic not in self._tasks and any(c.topic == topic for c in self._channels):
                self._tasks[topic] = asyncio.get_running_loop().create_task(
                    self.run_topic(topic), name=f"ml-stream-{topic}"
                )

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):               # noqa: BLE001
                pass
        self._tasks.clear()


#: One process-wide broadcaster, created on first use inside a running loop.
_broadcaster: Optional[Broadcaster] = None


def broadcaster() -> Broadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = Broadcaster()
    return _broadcaster
