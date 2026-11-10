"""The market-data broadcaster must send what useMarketStream actually listens for.

The defect this pins: the frontend waited on `live_data` while the backend emitted only static
acks, so the listener never fired. These tests assert the event name, the payload keys, and that
unknown values stay unknown instead of being invented.

Written without pytest-asyncio: it is not installed in this environment, and an unawaited
`async def` test is reported as a failure that looks like a skip. `asyncio.run` keeps the
coroutine tests honest with no new dependency.
"""
from __future__ import annotations

import asyncio

import pytest

from api.marketdata import socketio_market as m

PRICE_KEYS = {"symbol", "price", "change", "pct_change", "timestamp", "asset_class", "name"}


class FakeManager:
    def __init__(self, participants=None):
        self.participants = participants if participants is not None else [("sid-1", None, None)]

    def get_participants(self, namespace, room):
        return self.participants


class FakeSio:
    """Records emits and captures the background task instead of running it."""

    def __init__(self, participants=None):
        self.handlers = {}
        self.emits = []
        self.rooms = []
        self.tasks = []
        self.manager = FakeManager(participants)

    def on(self, event):
        def deco(fn):
            self.handlers[event] = fn
            return fn
        return deco

    def start_background_task(self, coro_fn, *args):
        self.tasks.append(coro_fn(*args))

    async def emit(self, event, data=None, room=None):
        self.emits.append((event, data, room))

    async def enter_room(self, sid, room):
        self.rooms.append((sid, room))

    async def leave_room(self, sid, room, namespace):
        self.rooms.remove((sid, room))


class StubPriceService:
    def __init__(self, prices, changes):
        self._prices, self._changes = prices, changes

    def get_current_prices(self):
        return self._prices

    def get_price_with_change(self, symbol):
        change = self._changes.get(symbol)
        if change is None:
            return {"change_pct": None, "change_abs": None}
        return {"change_pct": change, "change_abs": self._prices[symbol] * change / 100}


@pytest.fixture
def stub_prices(monkeypatch):
    def install(prices, changes):
        import api.services.price_service as ps
        monkeypatch.setattr(ps, "price_service", StubPriceService(prices, changes))
    return install


def test_registers_exactly_one_subscribe_handler():
    sio = FakeSio()
    m.register(sio)
    assert list(sio.handlers) == [m.SUBSCRIBE_EVENT]


def test_subscribe_joins_the_room_acks_and_starts_sampling_once():
    sio = FakeSio()
    m.register(sio)

    async def act():
        await sio.handlers[m.SUBSCRIBE_EVENT]("sid-1", {})
        await sio.handlers[m.SUBSCRIBE_EVENT]("sid-2", {})

    asyncio.run(act())

    assert sio.rooms == [("sid-1", m.ROOM), ("sid-2", m.ROOM)]
    acks = [(e[1], e[2]) for e in sio.emits if e[0] == "market_data_update"]
    assert acks == [({"status": "subscribed"}, "sid-1"), ({"status": "subscribed"}, "sid-2")]
    # Two watchers must not start two loops.
    assert len(sio.tasks) == 1
    for t in sio.tasks:
        t.close()


def test_payload_matches_the_frontend_contract(stub_prices):
    stub_prices({"SPX": 5000.0, "VIX": 14.0}, {"SPX": 1.0, "VIX": -2.0})
    payload = m._prices_payload()

    assert set(payload) == {"prices"}
    by_symbol = {p["symbol"]: p for p in payload["prices"]}
    assert set(by_symbol) == {"SPX", "VIX"}
    for item in payload["prices"]:
        assert set(item) == PRICE_KEYS
    assert by_symbol["SPX"]["price"] == 5000.0
    assert by_symbol["SPX"]["pct_change"] == 1.0
    assert by_symbol["VIX"]["pct_change"] == -2.0


def test_unknown_change_is_null_not_zero(stub_prices):
    # A symbol with no history must not be reported as unchanged.
    stub_prices({"NEW": 10.0}, {})
    item = m._prices_payload()["prices"][0]
    assert item["change"] is None
    assert item["pct_change"] is None


def test_name_and_asset_class_are_never_invented(stub_prices):
    # The repository has no display-name or asset-class source; empty means unknown.
    stub_prices({"SPX": 5000.0}, {"SPX": 1.0})
    item = m._prices_payload()["prices"][0]
    assert item["name"] == ""
    assert item["asset_class"] == ""


def test_no_payload_when_the_repository_is_empty(stub_prices):
    stub_prices({}, {})
    assert m._prices_payload() is None


def test_loop_emits_live_data_to_the_room(stub_prices):
    stub_prices({"SPX": 5000.0}, {"SPX": 1.0})
    sio = FakeSio()
    m.register(sio)

    async def act():
        await sio.handlers[m.SUBSCRIBE_EVENT]("sid-1", {})
        runner = asyncio.ensure_future(sio.tasks[0])
        await asyncio.sleep(0.05)          # let one tick through; the loop sleeps between them
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass

    asyncio.run(act())

    live = [e for e in sio.emits if e[0] == m.LIVE_EVENT]
    assert live, "the broadcaster never emitted live_data"
    assert live[0][2] == m.ROOM
    assert set(live[0][1]) == {"prices"}
    assert live[0][1]["prices"][0]["symbol"] == "SPX"


def test_loop_stops_when_no_one_is_watching(stub_prices):
    stub_prices({"SPX": 5000.0}, {"SPX": 1.0})
    sio = FakeSio()
    m.register(sio)

    async def act():
        await sio.handlers[m.SUBSCRIBE_EVENT]("sid-1", {})
        sio.manager.participants = []      # every watcher left
        await sio.tasks[0]                 # must return, not run forever

    asyncio.run(act())

    assert [e for e in sio.emits if e[0] == m.LIVE_EVENT] == []
