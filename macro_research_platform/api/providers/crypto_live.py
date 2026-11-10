"""
Live crypto prices from free public exchange APIs (no key): Coinbase first (true USD), Binance as the fallback
(USDT pairs, within a few basis points of USD). Used to replace Yahoo's delayed crypto price on quotes, the ticker
tape and the CRYPTO screen. Every call is cached for a few seconds; any failure returns nothing, so callers keep
their Yahoo / CoinGecko figures.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)
TTL = 5                                  # seconds
_HDR = {"accept": "application/json", "user-agent": "macro-research-platform"}


def coin_of(symbol: str) -> Optional[str]:
    """'BTC-USD' → 'BTC'; None for anything that is not a USD crypto pair."""
    s = symbol.strip().upper()
    return s[:-4] if s.endswith("-USD") and len(s) > 4 and "=" not in s else None


def price(coin: str) -> Dict[str, Any]:
    """Last trade, bid and ask for one coin against USD, or {}."""
    from api.marketdata.core import _cached
    c = coin.upper()

    def fetch():
        try:
            r = requests.get(f"https://api.exchange.coinbase.com/products/{c}-USD/ticker", headers=_HDR, timeout=6)
            if r.status_code == 200:
                j = r.json()
                if j.get("price"):
                    return {"price": float(j["price"]), "bid": float(j["bid"]) if j.get("bid") else None,
                            "ask": float(j["ask"]) if j.get("ask") else None, "time": j.get("time"), "source": "Coinbase (real-time)"}
        except Exception as e:
            logger.debug("[crypto] coinbase %s: %s", c, e)
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/bookTicker", params={"symbol": f"{c}USDT"}, headers=_HDR, timeout=6)
            r2 = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": f"{c}USDT"}, headers=_HDR, timeout=6)
            if r2.status_code == 200:
                b = r.json() if r.status_code == 200 else {}
                return {"price": float(r2.json()["price"]), "bid": float(b["bidPrice"]) if b.get("bidPrice") else None,
                        "ask": float(b["askPrice"]) if b.get("askPrice") else None,
                        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "Binance (real-time, USDT)"}
        except Exception as e:
            logger.debug("[crypto] binance %s: %s", c, e)
        return {}
    try:
        return _cached(f"crypto_live:{c}", TTL, fetch)
    except Exception:
        return {}


def prices() -> Dict[str, Any]:
    """{'coins': {COIN: usd_price}, 'source'} for every coin Coinbase quotes, in one request (Binance as fallback)."""
    from api.marketdata.core import _cached

    def fetch():
        try:
            r = requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}, headers=_HDR, timeout=8)
            if r.status_code == 200:
                rates = (r.json().get("data") or {}).get("rates") or {}
                coins = {k.upper(): float(f"{1 / float(v):.8g}") for k, v in rates.items() if v and float(v) > 0}   # 1/rate, without float noise
                if coins:
                    return {"coins": coins, "source": "Coinbase (real-time)"}
        except Exception as e:
            logger.debug("[crypto] coinbase rates: %s", e)
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price", headers=_HDR, timeout=8)
            if r.status_code == 200:
                coins = {x["symbol"][:-4]: float(x["price"]) for x in r.json() if x.get("symbol", "").endswith("USDT")}
                if coins:
                    return {"coins": coins, "source": "Binance (real-time, USDT)"}
        except Exception as e:
            logger.debug("[crypto] binance all: %s", e)
        return {"coins": {}, "source": None}
    try:
        return _cached("crypto_live:all", TTL, fetch)
    except Exception:
        return {"coins": {}, "source": None}


def plausible(live: Optional[float], ref: Optional[float], tol: float = 0.25) -> bool:
    """A live price within ±25% of the reference — guards against a ticker that means a different coin on the exchange."""
    return bool(live and ref and abs(live / ref - 1) <= tol)
