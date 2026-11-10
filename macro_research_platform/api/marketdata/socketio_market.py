"""Socket.IO market-data broadcaster — the `live_data` half of the market stream contract.

`frontend/src/hooks/useMarketStream.ts` waits for `live_data` carrying `{prices: PriceData[]}`.
Before this module the backend emitted only static acks, so that listener never fired and the hook
was dead weight. This registers the real subscription handler and samples the price repository on
the same 5s cadence the raw `/ws/prices` transport already uses.

Two rules carried over from the ML stream bridge:

  * Sampling is demand-driven. The task runs only while the `market_data` room is non-empty, so an
    unwatched server costs nothing. Socket.IO drops a sid from its rooms on disconnect, which is
    what lets the loop notice an empty room and stop — no `disconnect` handler is registered here,
    because python-socketio keeps one handler per event and main.py already owns it.
  * Nothing is invented. `name` and `asset_class` have no source in this repository, so they are
    emitted empty rather than guessed. A symbol whose change history is missing emits `null` for
    `change`/`pct_change` rather than `0`, because `0` asserts "unchanged" about a symbol we know
    nothing about.

`REGIME_CHANGE` is deliberately not implemented: its only source, `api.regime_data.get_regime_data`,
is DataFrame-scale dashboard work and polling it every 5s would be worse than not sending it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SUBSCRIBE_EVENT = "subscribe_market_data"
LIVE_EVENT = "live_data"
ROOM = "market_data"
INTERVAL = 5.0


def _prices_payload() -> Optional[Dict[str, Any]]:
    """One `live_data` payload, or None when the price repository has nothing to serve."""
    from api.services.price_service import price_service

    current = price_service.get_current_prices()
    if not current:
        return None

    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    items: List[Dict[str, Any]] = []
    for symbol, price in current.items():
        # get_price_with_change re-reads the repository's change series; None means that symbol has
        # no history yet, which is reported as null rather than as a zero change.
        detail = price_service.get_price_with_change(symbol) or {}
        items.append(
            {
                "symbol": symbol,
                "price": price,
                "change": detail.get("change_abs"),
                "pct_change": detail.get("change_pct"),
                "timestamp": now,
                "asset_class": "",
                "name": "",
            }
        )
    return {"prices": items}


def register(sio) -> None:
    """Attach the market-data subscription handler to an existing AsyncServer."""

    running: Dict[str, bool] = {"task": False}

    async def _broadcast_loop() -> None:
        try:
            while True:
                # Socket.IO removes a disconnected sid from its rooms, so an empty room here means
                # every watcher is gone and sampling should stop.
                if not sio.manager.get_participants(None, ROOM):
                    break
                payload = await asyncio.to_thread(_prices_payload)
                if payload is not None:
                    await sio.emit(LIVE_EVENT, payload, room=ROOM)
                await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[market-stream] broadcast loop failed")
        finally:
            running["task"] = False

    @sio.on(SUBSCRIBE_EVENT)
    async def subscribe_market_data(sid: str, data: Any = None) -> None:
        """Acknowledge a subscription, join the room, and start sampling for the first watcher."""
        await sio.enter_room(sid, ROOM)
        await sio.emit("market_data_update", {"status": "subscribed"}, room=sid)
        if not running["task"]:
            running["task"] = True
            sio.start_background_task(_broadcast_loop)
            logger.info("[market-stream] sampling started")


async def shutdown(sio) -> None:
    """Cancel sampling on application shutdown so no task outlives the server."""
    for sid in [p[0] for p in sio.manager.get_participants(None, ROOM)]:
        await sio.leave_room(sid, ROOM, None)
