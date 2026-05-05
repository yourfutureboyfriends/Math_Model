#!/usr/bin/env python3
"""
WebSocket Streaming Manager
============================
Handles real-time market data streaming using yfinance
and broadcasts updates to all connected clients every 2 seconds.

Integrates with the existing python-socketio AsyncServer in main.py.

Architecture:
- Data ingestion thread (yfinance polling with AsyncWebSocket support)
- Price cache with threading.Lock() protection
- Broadcast thread (emits to all clients every 2s)
- Market clock thread (timezone-based status)
- Regime watcher thread (alerts on changes)
"""

import threading
import time
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Callable, Any, List
from concurrent.futures import ThreadPoolExecutor

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
    Run yfinance AsyncWebSocket stream if available.
    Falls back to polling if AsyncWebSocket unavailable.
    """
    try:
        import yfinance as yf

        # Try AsyncWebSocket first (newer yfinance versions)
        if hasattr(yf, "AsyncWebSocket"):
            logging.info("[WebSocket] Using yfinance AsyncWebSocket")
            ws = yf.AsyncWebSocket(
                tickers=list(STREAM_TICKERS.keys()),
                callback=_price_updater,
            )
            asyncio.run(ws.listen())
        else:
            # Fallback: polling loop
            logging.info("[WebSocket] AsyncWebSocket not available, using polling")
            _polling_fallback()
    except Exception as e:
        logging.warning(f"[WebSocket] Stream error: {e}, using polling fallback")
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
            try:
                await _sio.emit("live_data", {"prices": snapshot})
            except Exception as e:
                logging.warning(f"[WebSocket] Broadcast error: {e}")


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

            # FIXED: Use shared regime context, not independent classification (BUG-05)
            try:
                from api.regime_context import build_regime_context
                # Import latest values from data cache or compute
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
                await _sio.emit(
                    "REGIME_CHANGE",
                    {
                        "regime": current_regime,
                        "timestamp": datetime.now().isoformat(),
                        "details": regime_data or {},
                    }
                )
        except Exception as e:
            logging.warning(f"[WebSocket] Regime watcher error: {e}")


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
    logging.info("[WebSocket] Streaming threads started")


def get_stream_status():
    """Return current streaming status for health checks."""
    return {
        "tickers_count": len(STREAM_TICKERS),
        "cached_prices": len(_price_cache),
        "connected_clients": _connected_clients,
        "market_clock": _get_market_clock(),
    }


# Convenience functions for main.py to call
def update_client_count(count: int):
    """Update the connected client count."""
    set_connected_clients(count)


def get_connected_count() -> int:
    """Get current connected client count."""
    return _connected_clients
