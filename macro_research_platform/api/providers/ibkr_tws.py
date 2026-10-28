"""
Interactive Brokers TWS / IB Gateway — a market-data source (read-only) through the socket API on this computer.

What it adds: quotes on the exchanges the IBKR account subscribes to (real-time), and IBKR's free delayed quotes
elsewhere (labelled as delayed) — London, Xetra, Paris, Amsterdam, Milan, Madrid, Zurich, Tokyo, Hong Kong, Sydney,
Singapore, Toronto and the US — plus historical daily bars for those listings.

DATA ONLY: this module requests market data and contract details and nothing else. It never places, modifies or
cancels an order (none of those calls appear in it; a test checks the source), and TWS's own "Read-Only API" setting
blocks orders at the gateway too. It is not tied to a fund and reads no positions.

Setup: TWS (or IB Gateway) running and logged in, API → Settings: "Enable ActiveX and Socket Clients" and "Read-Only
API" ticked. Defaults 127.0.0.1:7496 (TWS live); IBKR_TWS_HOST / IBKR_TWS_PORT / IBKR_TWS_CLIENT_ID in .env override
(7497 = TWS paper, 4001 / 4002 = IB Gateway).
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import socket
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_state: Dict[str, Any] = {"loop": None, "thread": None, "ib": None, "lock": threading.Lock()}

# Yahoo suffix → (IBKR exchange, currency). The listing is pinned with primaryExchange so SMART routing still prices it.
SUFFIX = {"L": ("LSE", "GBP"), "DE": ("IBIS", "EUR"), "F": ("FWB", "EUR"), "PA": ("SBF", "EUR"), "AS": ("AEB", "EUR"),
          "MI": ("BVME", "EUR"), "MC": ("BM", "EUR"), "SW": ("EBS", "CHF"), "T": ("TSEJ", "JPY"), "HK": ("SEHK", "HKD"),
          "AX": ("ASX", "AUD"), "SI": ("SGX", "SGD"), "TO": ("TSE", "CAD"), "V": ("VENTURE", "CAD"), "ST": ("SFB", "SEK"),
          "CO": ("KFB", "DKK"), "OL": ("OSE", "NOK"), "VI": ("VSE", "EUR"), "BR": ("ENEXT.BE", "EUR")}


class IbkrUnavailable(RuntimeError):
    """TWS / IB Gateway is not running, not logged in, or the API is not enabled."""


def _addr() -> tuple:
    return (os.getenv("IBKR_TWS_HOST", "127.0.0.1"), int(os.getenv("IBKR_TWS_PORT", "7496")),
            int(os.getenv("IBKR_TWS_CLIENT_ID", "77")))


def tws_running() -> bool:
    host, port, _ = _addr()
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def to_contract(symbol: str):
    """Yahoo-style symbol → an ib_async Stock contract (None for indices, FX and futures)."""
    from ib_async import Stock
    s = symbol.strip().upper()
    if any(c in s for c in "=^"):
        return None
    base, _, suf = s.rpartition(".") if "." in s and s.rpartition(".")[2] in SUFFIX else (s, "", "")
    if not suf:
        return Stock(s.replace("-", " "), "SMART", "USD")                      # BRK-B → "BRK B"
    exch, ccy = SUFFIX[suf]
    sym = base.lstrip("0") if suf == "HK" else base.replace("-", ".") if suf == "L" else base
    return Stock(sym, "SMART", ccy, primaryExchange=exch)


# ── the connection lives on its own event-loop thread ────────────────────────
def _loop() -> asyncio.AbstractEventLoop:
    with _state["lock"]:
        if _state["loop"] is None:
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=loop.run_forever, name="ibkr-tws", daemon=True)
            t.start()
            _state.update(loop=loop, thread=t)
        return _state["loop"]


def _run(coro, timeout: float = 20.0):
    return asyncio.run_coroutine_threadsafe(coro, _loop()).result(timeout)


async def _ib():
    from ib_async import IB
    ib = _state["ib"]
    if ib is not None and ib.isConnected():
        return ib
    host, port, cid = _addr()
    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=cid, readonly=True, timeout=8)
    except Exception as e:
        raise IbkrUnavailable(f"Could not connect to TWS on {host}:{port}: {e}. Check TWS is logged in and API → "
                              "'Enable ActiveX and Socket Clients' is ticked.")
    _state["ib"] = ib
    return ib


def _connect():
    if not tws_running():
        raise IbkrUnavailable("TWS / IB Gateway is not running on this computer (or the API port is closed).")
    return _run(_ib())


# ── data ─────────────────────────────────────────────────────────────────────
def status() -> Dict[str, Any]:
    if not tws_running():
        return {"connected": False, "reason": "TWS / IB Gateway is not running on this computer (or the API port is closed)."}
    try:
        ib = _connect()
        return {"connected": True, "server_version": ib.client.serverVersion(), "accounts": len(ib.managedAccounts()),
                "read_only": True, "port": _addr()[1]}
    except IbkrUnavailable as e:
        return {"connected": False, "reason": str(e)}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) or v <= 0 else v
    except (TypeError, ValueError):
        return None


async def _quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    ib = await _ib()
    ib.reqMarketDataType(3)              # real-time where subscribed, IBKR's free delayed data otherwise
    pairs = [(s, to_contract(s)) for s in symbols]
    pairs = [(s, c) for s, c in pairs if c is not None]
    if not pairs:
        return []
    qualified = await ib.qualifyContractsAsync(*[c for _, c in pairs])
    ok = {id(c) for c in qualified if getattr(c, "conId", 0)}
    pairs = [(s, c) for s, c in pairs if id(c) in ok]
    tickers = await ib.reqTickersAsync(*[c for _, c in pairs])
    out = []
    for (s, c), t in zip(pairs, tickers):
        last, close = _num(t.last), _num(t.close)
        price = last or _num(t.marketPrice()) or close
        out.append({"symbol": s, "price": price, "bid": _num(t.bid), "ask": _num(t.ask), "previous_close": close,
                    "change_pct": (price / close - 1) if price and close else None, "volume": _num(t.volume),
                    "currency": c.currency, "exchange": c.primaryExchange or c.exchange,
                    "delayed": t.marketDataType in (3, 4), "time": t.time.isoformat() if t.time else None})
    return out


def quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    """Quotes for Yahoo-style symbols — real-time where the account subscribes, else delayed (flagged)."""
    _connect()
    return _run(_quotes(symbols[:50]), timeout=30)


async def _history(symbol: str, duration: str, bar: str) -> List[Dict[str, Any]]:
    ib = await _ib()
    c = to_contract(symbol)
    if c is None:
        raise IbkrUnavailable(f"{symbol} is not a stock listing IBKR quotes here.")
    q = await ib.qualifyContractsAsync(c)
    if not q or not getattr(q[0], "conId", 0):
        raise IbkrUnavailable(f"IBKR has no contract for {symbol}.")
    bars = await ib.reqHistoricalDataAsync(q[0], endDateTime="", durationStr=duration, barSizeSetting=bar,
                                           whatToShow="TRADES", useRTH=True, formatDate=1)
    return [{"date": str(b.date), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars]


def history(symbol: str, duration: str = "1 Y", bar: str = "1 day") -> Dict[str, Any]:
    """Historical bars (trades, regular hours) for a stock listing."""
    _connect()
    rows = _run(_history(symbol, duration, bar), timeout=60)
    return {"symbol": symbol, "rows": rows, "source": "Interactive Brokers (TWS API)"}
