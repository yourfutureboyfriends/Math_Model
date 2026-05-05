#!/usr/bin/env python3
"""
WebSocket Streaming Manager with Redis Pub/Sub (Phase 9D)
==========================================================
Handles real-time market data streaming using yfinance
and broadcasts updates to all connected clients every 2 seconds.

NEW: Redis pub/sub integration for multi-worker broadcasting (Phase 9D)
- Local connections maintained per worker
- Redis pub/sub for cross-worker message distribution
- Graceful fallback if Redis unavailable

Architecture:
- Data ingestion thread (yfinance polling)
- Price cache with threading.Lock() protection
- Broadcast thread (emits to local clients + Redis)
- Redis listener thread (receives from other workers)
- Market clock thread (timezone-based status)
- Regime watcher thread (alerts on changes)
"""

import threading
import time
import json
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional, Callable, Any, List, Set
from concurrent.futures import ThreadPoolExecutor

# Redis imports
try:
    import redis.asyncio as redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logging.warning("[WebSocket] redis not available, using local-only broadcast")

try:
    import pytz
    _PYTZ_OK = True
except ImportError:
    _PYTZ_OK = False
    logging.warning("[WebSocket] pytz not available, using zoneinfo")
    from zoneinfo import ZoneInfo

# Global references (set by set_socketio)
_sio = None
_lock = threading.Lock()
_price_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_connected_clients: int = 0
_last_known_regime: Optional[str] = None

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
WS_CHANNEL_PREFIX = "ws:broadcast"

# Redis connection (async - for publishing)
_redis_pool: Optional[redis.Redis] = None
_redis_lock = threading.Lock()

# Market data configuration
STREAM_TICKERS = {
    # Indices
    "^GSPC": {"name": "S&P 500", "asset_class": "equity_index"},
    "^DJI": {"name": "Dow Jones", "asset_class": "equity_index"},
    "^IXIC": {"name": "NASDAQ", "asset_class": "equity_index"},
    "^RUT": {"name": "Russell 2000", "asset_class": "equity_index"},
    "^FTSE": {"name": "FTSE 100", "asset_class": "equity_index"},
    "^GDAXI": {"name": "DAX", "asset_class": "equity_index"},
    "^N225": {"name": "Nikkei 225", "asset_class": "equity_index"},
    "^HSI": {"name": "Hang Seng", "asset_class": "equity_index"},

    # Volatility
    "^VIX": {"name": "VIX", "asset_class": "volatility"},
    "^VXN": {"name": "VXN", "asset_class": "volatility"},

    # FX
    "EURUSD=X": {"name": "EUR/USD", "asset_class": "fx"},
    "GBPUSD=X": {"name": "GBP/USD", "asset_class": "fx"},
    "USDJPY=X": {"name": "USD/JPY", "asset_class": "fx"},
    "DX-Y.NYB": {"name": "DXY", "asset_class": "fx"},

    # Commodities
    "GC=F": {"name": "Gold", "asset_class": "commodity"},
    "SI=F": {"name": "Silver", "asset_class": "commodity"},
    "CL=F": {"name": "Crude Oil", "asset_class": "commodity"},
    "NG=F": {"name": "Natural Gas", "asset_class": "commodity"},
    "HG=F": {"name": "Copper", "asset_class": "commodity"},

    # Bond Yields (as tickers)
    "^TNX": {"name": "10Y Yield", "asset_class": "bond"},
    "^FVX": {"name": "5Y Yield", "asset_class": "bond"},
    "^TYX": {"name": "30Y Yield", "asset_class": "bond"},
}


# Redis Connection Management (Phase 9D)


def _get_redis_pool() -> Optional[redis.Redis]:
    """Get or create Redis connection pool (thread-safe)"""
    global _redis_pool

    if not _REDIS_AVAILABLE:
        return None

    with _redis_lock:
        if _redis_pool is None:
            try:
                _redis_pool = redis.from_url(
                    REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                )
                logging.info("[WebSocket] Redis connection established")
            except Exception as e:
                logging.error(f"[WebSocket] Failed to connect to Redis: {e}")
                _redis_pool = None

        return _redis_pool


async def _broadcast_to_redis(channel: str, message: Dict[str, Any]) -> bool:
    """Broadcast message to Redis pub/sub channel"""
    pool = _get_redis_pool()
    if pool is None:
        return False

    try:
        channel_name = f"{WS_CHANNEL_PREFIX}:{channel}"
        await pool.publish(channel_name, json.dumps(message))
        return True
    except Exception as e:
        logging.warning(f"[WebSocket] Redis publish failed: {e}")
        return False


async def _listen_redis():
    """Listen for messages from Redis and broadcast locally"""
    if not _REDIS_AVAILABLE:
        return

    pool = _get_redis_pool()
    if pool is None:
        return

    try:
        pubsub = pool.pubsub()
        await pubsub.subscribe(
            f"{WS_CHANNEL_PREFIX}:signals",
            f"{WS_CHANNEL_PREFIX}:regime",
            f"{WS_CHANNEL_PREFIX}:market",
            f"{WS_CHANNEL_PREFIX}:alerts",
            f"{WS_CHANNEL_PREFIX}:all",
        )

        logging.info("[WebSocket] Redis pub/sub listener started")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    # Only emit if not from this worker (avoid duplication)
                    if data.get("worker_id") != _get_worker_id():
                        await _emit_local(data)
                except Exception as e:
                    logging.warning(f"[WebSocket] Error processing Redis message: {e}")

    except asyncio.CancelledError:
        logging.info("[WebSocket] Redis listener cancelled")
        raise
    except Exception as e:
        logging.error(f"[WebSocket] Redis listener error: {e}")


def _get_worker_id() -> str:
    """Get unique worker ID for this process"""
    return f"{os.getpid()}_{threading.current_thread().ident}"


# Price and Broadcasting Logic


def _price_updater(symbol: str, price: float, timestamp: datetime):
    """Thread-safe price update from WebSocket feed."""
    with _cache_lock:
        prev = _price_cache.get(symbol, {}).get("price")
        _price_cache[symbol] = {
            "symbol": symbol,
            "price": price,
            "prev_price": prev,
            "change": (price - prev) if prev else 0.0,
            "pct_change": ((price - prev) / prev * 100) if prev else 0.0,
            "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            "asset_class": STREAM_TICKERS.get(symbol, {}).get("asset_class", "unknown"),
            "name": STREAM_TICKERS.get(symbol, {}).get("name", symbol),
        }


def _run_yf_stream():
    """
    Run yfinance streaming.
    Uses polling loop as primary method.
    """
    logging.info("[WebSocket] Using polling fallback (reliable method)")
    _polling_fallback()


def _polling_fallback():
    """Fallback polling every 5 seconds if WebSocket unavailable."""
    import yfinance as yf

    logging.info("[WebSocket] Polling fallback started")
    while True:
        try:
            for symbol in STREAM_TICKERS:
                try:
                    ticker = yf.Ticker(symbol)
                    data = ticker.history(period="1d", interval="1m", prepost=False)
                    if not data.empty:
                        price = data["Close"].iloc[-1]
                        timestamp = datetime.now()
                        if price and price == price:  # NaN check
                            _price_updater(symbol, float(price), timestamp)
                except Exception:
                    continue
        except Exception as e:
            logging.warning(f"[WebSocket] Polling error: {e}")
        time.sleep(5)


def _broadcast_loop_sync():
    """Synchronous wrapper for broadcast loop to run in thread."""
    asyncio.run(_broadcast_loop())


async def _broadcast_loop():
    """Emit 'live_data' event to ALL clients every 2 seconds."""
    global _sio, _connected_clients

    while True:
        await asyncio.sleep(2)
        if _sio is None or _connected_clients == 0:
            continue

        with _cache_lock:
            snapshot = list(_price_cache.values())

        if snapshot:
            message = {
                "type": "live_data",
                "worker_id": _get_worker_id(),
                "timestamp": datetime.utcnow().isoformat(),
                "prices": snapshot,
            }

            try:
                # Emit locally first
                await _sio.emit("live_data", {"prices": snapshot})

                # Also broadcast to Redis for other workers
                await _broadcast_to_redis("market", message)
            except Exception as e:
                logging.warning(f"[WebSocket] Broadcast error: {e}")


async def _emit_local(data: Dict[str, Any]):
    """Emit message to locally connected SocketIO clients"""
    global _sio
    if _sio is None:
        return

    try:
        msg_type = data.get("type")
        if msg_type == "live_data":
            await _sio.emit("live_data", {"prices": data.get("prices", [])})
        elif msg_type == "signal_update":
            await _sio.emit("signal_update", data.get("data", {}))
        elif msg_type == "regime_change":
            await _sio.emit("REGIME_CHANGE", data.get("data", {}))
        elif msg_type == "alert":
            await _sio.emit("alert", data.get("data", {}))
    except Exception as e:
        logging.warning(f"[WebSocket] Local emit error: {e}")


# Market Clock and Regime Watcher


def _get_market_clock():
    """
    Pure timezone logic - no external API.
    Returns market status for major exchanges.
    """
    if _PYTZ_OK:
        utc = pytz.UTC
        now = datetime.now(utc)
    else:
        now = datetime.now().astimezone()

    markets = [
        {"name": "NYSE", "tz": "America/New_York", "open": "09:30", "close": "16:00"},
        {"name": "LSE", "tz": "Europe/London", "open": "08:00", "close": "16:30"},
        {"name": "Xetra", "tz": "Europe/Berlin", "open": "09:00", "close": "17:30"},
        {"name": "TSE", "tz": "Asia/Tokyo", "open": "09:00", "close": "15:00"},
        {"name": "HKEx", "tz": "Asia/Hong_Kong", "open": "09:30", "close": "16:00"},
        {"name": "SGX", "tz": "Asia/Singapore", "open": "09:00", "close": "17:00"},
        {"name": "ASX", "tz": "Australia/Sydney", "open": "10:00", "close": "16:00"},
    ]

    statuses = []
    for m in markets:
        try:
            if _PYTZ_OK:
                tz = pytz.timezone(m["tz"])
                local = now.astimezone(tz)
            else:
                local = now.astimezone(ZoneInfo(m["tz"]))

            time_str = local.strftime("%H:%M")
            is_open = m["open"] <= time_str <= m["close"]
            is_weekday = local.weekday() < 5
            status = "open" if (is_open and is_weekday) else "closed"

            statuses.append({
                "market": m["name"],
                "status": status,
                "local_time": local.strftime("%H:%M"),
                "timezone": m["tz"].split("/")[-1],
            })
        except Exception as e:
            logging.warning(f"[WebSocket] Market clock error for {m['name']}: {e}")

    return {"markets": statuses, "timestamp": now.isoformat() if hasattr(now, 'isoformat') else str(now)}


def _regime_watcher_sync():
    """Synchronous wrapper for regime watcher."""
    asyncio.run(_regime_watcher_loop())


async def _regime_watcher_loop():
    """
    Check regime changes every 60 seconds.
    Emits 'REGIME_CHANGE' event when regime differs from last known.
    Uses Redis pub/sub for cross-worker distribution.
    """
    global _sio, _connected_clients, _last_known_regime

    while True:
        await asyncio.sleep(60)
        if _sio is None or _connected_clients == 0:
            continue

        try:
            # Try to get current regime from various sources
            regime_data = None
            current_regime = None

            try:
                from api.regime_context import build_regime_context
                from api.data_fetcher import _METRIC_CACHE
                growth = _METRIC_CACHE.get("growth", (2.0, 0))[0]
                inflation = _METRIC_CACHE.get("inflation", (3.3, 0))[0]
                regime_ctx = build_regime_context(growth_val=growth, inflation_val=inflation)
                current_regime = regime_ctx.regime
                regime_data = {"regime": current_regime, "confidence": regime_ctx.confidence}
            except Exception:
                current_regime = "unknown"
                regime_data = {"regime": "unknown"}

            if current_regime and current_regime != _last_known_regime:
                _last_known_regime = current_regime

                message = {
                    "type": "regime_change",
                    "worker_id": _get_worker_id(),
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "regime": current_regime,
                        "timestamp": datetime.now().isoformat(),
                        "details": regime_data or {},
                    }
                }

                # Emit locally
                await _sio.emit("REGIME_CHANGE", message["data"])

                # Broadcast to Redis for other workers
                await _broadcast_to_redis("regime", message)

        except Exception as e:
            logging.warning(f"[WebSocket] Regime watcher error: {e}")


def _redis_listener_sync():
    """Synchronous wrapper for Redis listener."""
    asyncio.run(_listen_redis())


# Public API


def set_socketio(socketio_instance):
    """Set the global SocketIO instance singleton."""
    global _sio
    with _lock:
        _sio = socketio_instance


def set_connected_clients(count: int):
    """Update connected clients count."""
    global _connected_clients
    _connected_clients = count


def get_price(symbol: str) -> Optional[Dict[str, Any]]:
    """Thread-safe price lookup."""
    with _cache_lock:
        return _price_cache.get(symbol)


def get_all_prices() -> Dict[str, Any]:
    """Get snapshot of all prices."""
    with _cache_lock:
        return {"prices": list(_price_cache.values())}


def start_streaming():
    """
    Called once at server startup.
    Spawns background threads for streaming, broadcasting, and regime watching.
    """
    # Seed prices on startup (one-time fetch)
    try:
        import yfinance as yf
        logging.info("[WebSocket] Seeding initial prices...")

        for symbol in STREAM_TICKERS:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period="1d", interval="1m")
                if not data.empty:
                    price = data["Close"].iloc[-1]
                    timestamp = datetime.now()
                    if price and price == price:
                        _price_updater(symbol, float(price), timestamp)
            except Exception:
                continue
    except Exception as e:
        logging.warning(f"[WebSocket] Seed error: {e}")

    # Start threads
    threading.Thread(target=_run_yf_stream, daemon=True, name="yf-stream").start()
    threading.Thread(target=_broadcast_loop_sync, daemon=True, name="broadcast").start()
    threading.Thread(target=_regime_watcher_sync, daemon=True, name="regime-watcher").start()

    # Start Redis listener if available
    if _REDIS_AVAILABLE:
        threading.Thread(target=_redis_listener_sync, daemon=True, name="redis-listener").start()
        logging.info("[WebSocket] Redis pub/sub listener thread started")

    logging.info("[WebSocket] Streaming threads started")


def get_stream_status():
    """Return current streaming status for health checks."""
    return {
        "tickers_count": len(STREAM_TICKERS),
        "cached_prices": len(_price_cache),
        "connected_clients": _connected_clients,
        "market_clock": _get_market_clock(),
        "redis_available": _REDIS_AVAILABLE,
        "redis_connected": _redis_pool is not None,
    }


# Convenience functions for main.py to call
def update_client_count(count: int):
    """Update the connected client count."""
    set_connected_clients(count)


def get_connected_count() -> int:
    """Get current connected client count."""
    return _connected_clients


# Phase 9D: New Redis Broadcast Functions


async def broadcast_signal_update(signal_data: Dict[str, Any]) -> bool:
    """Broadcast signal update via Redis to all workers"""
    message = {
        "type": "signal_update",
        "worker_id": _get_worker_id(),
        "timestamp": datetime.utcnow().isoformat(),
        "data": signal_data,
    }

    # Emit locally first
    if _sio:
        await _sio.emit("signal_update", signal_data)

    # Broadcast via Redis
    return await _broadcast_to_redis("signals", message)


async def broadcast_regime_change(regime_data: Dict[str, Any]) -> bool:
    """Broadcast regime change via Redis to all workers"""
    message = {
        "type": "regime_change",
        "worker_id": _get_worker_id(),
        "timestamp": datetime.utcnow().isoformat(),
        "data": regime_data,
    }

    # Emit locally first
    if _sio:
        await _sio.emit("REGIME_CHANGE", regime_data)

    # Broadcast via Redis
    return await _broadcast_to_redis("regime", message)


async def broadcast_alert(alert_data: Dict[str, Any]) -> bool:
    """Broadcast alert via Redis to all workers"""
    message = {
        "type": "alert",
        "worker_id": _get_worker_id(),
        "timestamp": datetime.utcnow().isoformat(),
        "data": alert_data,
    }

    # Emit locally first
    if _sio:
        await _sio.emit("alert", alert_data)

    # Broadcast via Redis
    return await _broadcast_to_redis("alerts", message)
