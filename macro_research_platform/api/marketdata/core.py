"""
Markets mode data — universal by design.

  * search(q)       every asset class and exchange Yahoo lists (equities worldwide, ETFs,
                    mutual funds, indices, currencies, futures, crypto), nothing filtered out
  * quote(s)        price, change, range, volume, market cap, currency, exchange, session
  * overview()      world indices, rates, FX, commodities, crypto in one batch
  * profile(s)      business description / fund facts / instrument facts
  * statements(s)   SEC EDGAR (as filed) for US filers, Yahoo statements for everyone else
  * news(s)         headlines + the company's latest SEC filings (8-K, 10-Q, …)
  * movers(region)  gainers / losers / most active for any region
  * screen(...)     Yahoo's global equity screener (region, sector, size, valuation, yield)

Every value comes from a provider or is absent; failures raise, never return zeros.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
_cache: Dict[str, tuple] = {}
_lock = threading.Lock()


class NotFound(LookupError):
    """The thing asked for doesn't exist or the input is invalid (HTTP 404 / 400)."""
    pass


class Upstream(RuntimeError):
    """A data source failed or rate-limited (HTTP 502 / 503)."""
    pass


_inflight: Dict[str, threading.Lock] = {}


STALE_MAX = 24 * 3600


# Stale-while-revalidate: an entry past its TTL (TTL ≥ 5 min, so live quotes are never served old) but younger than
# SWR_FACTOR × TTL is returned at once while one background refresh runs — screens no longer wait on a cold upstream
# fetch every time a cache lapses; only the first load after start does.
SWR_MIN_TTL = 300
SWR_FACTOR = 4
_refreshing: set = set()


def _refresh_later(key: str, fn: Callable[[], Any]) -> None:
    with _lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def go():
        try:
            _fill(key, fn)                    # on failure the old entry stays; past SWR_FACTOR × TTL callers wait
        except Exception as e:                                                # noqa: BLE001 — next caller retries
            logger.info("[cache] background refresh of %s failed: %s", key, type(e).__name__)
        finally:
            with _lock:
                _refreshing.discard(key)
    threading.Thread(target=go, name=f"swr-{key[:40]}", daemon=True).start()


def _fill(key: str, fn: Callable[[], Any]) -> Any:
    """Fetch and store, single-flight per key."""
    with _lock:
        flight = _inflight.setdefault(key, threading.Lock())
    with flight:
        try:
            val = fn()
        finally:
            with _lock:
                _inflight.pop(key, None)
        _disk_save(key, val)
        with _lock:
            _cache[key] = (time.time(), val)
        return val


# Screens that take 25 s – 2 min to build cold (hundreds of downloads, slow public APIs) keep their last good result on
# disk: after a restart the saved copy is served at once — marked stale, so the screen says "saved copy, refreshing" —
# while a fresh one builds in the background. Kept up to PERSIST_MAX old.
PERSIST_PREFIXES = ("imap:", "ins:breadth", "ins:impm:", "ins:uoa", "ins:risk", "edge:", "flow:etf", "bw:", "wcrs:", "overview")
PERSIST_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "screen_cache"
PERSIST_MAX = 3 * 86400


def _persist_path(key: str) -> Optional[Path]:
    if not key.startswith(PERSIST_PREFIXES):
        return None
    import hashlib
    return PERSIST_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")


def _disk_load(key: str):
    p = _persist_path(key)
    if not p:
        return None
    try:
        age = time.time() - p.stat().st_mtime
        if age > PERSIST_MAX:
            return None
        import json
        return (p.stat().st_mtime, json.loads(p.read_text()))
    except Exception:
        return None


def _disk_save(key: str, val: Any) -> None:
    p = _persist_path(key)
    if not p or not isinstance(val, (dict, list)):
        return
    try:
        import json
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(val, default=str))
        tmp.replace(p)                                    # atomic: a reader never sees half a file
    except Exception as e:
        logger.debug("[cache] could not save %s: %s", key, e)


def _cached(key: str, ttl: float, fn: Callable[[], Any]) -> Any:
    """TTL cache with single-flight: concurrent misses for one key (several launchpad windows on
    the same data) wait for a single upstream fetch instead of each calling the provider."""
    with _lock:
        hit = _cache.get(key)
    if hit is None and (disk := _disk_load(key)) is not None:
        with _lock:                                       # first use since a restart: the saved copy
            _cache.setdefault(key, disk)
            hit = _cache[key]
        if time.time() - hit[0] >= ttl:
            _refresh_later(key, fn)
            v = hit[1]
            return {**v, "stale": True, "stale_age_s": int(time.time() - hit[0])} if isinstance(v, dict) else v
    with _lock:
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        swr = bool(hit) and ttl >= SWR_MIN_TTL and time.time() - hit[0] < SWR_FACTOR * ttl
    if swr:
        _refresh_later(key, fn)
        return hit[1]
    with _lock:
        flight = _inflight.setdefault(key, threading.Lock())
    with flight:
        with _lock:                                  # filled while we waited?
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        try:
            val = fn()
        except NotFound:
            raise
        except Exception as e:
            # the provider failed (rate limit, outage, timeout): serve the last good value if it is
            # under a day old, marked stale, rather than turning a working screen into an error
            with _lock:
                old = _cache.get(key)
            if old and time.time() - old[0] < STALE_MAX:
                logger.info("[cache] %s refresh failed (%s): serving %ds-old data", key, type(e).__name__, time.time() - old[0])
                v = old[1]
                return {**v, "stale": True, "stale_age_s": int(time.time() - old[0])} if isinstance(v, dict) else v
            raise
        finally:
            with _lock:
                _inflight.pop(key, None)
        _disk_save(key, val)
        with _lock:
            _cache[key] = (time.time(), val)
            if len(_cache) > 2000:                   # bound memory
                for k in sorted(_cache, key=lambda k: _cache[k][0])[:500]:
                    _cache.pop(k, None)
        return val


# ── Yahoo rate-limit guard ──────────────────────────────────────────────────
# Yahoo throttles an IP that sends bursts (hundreds of requests from launchpad windows, breadth scans).
# Hammering it while throttled extends the block and turns every screen into an error, so: at most a
# few requests at once, and after a 429 a cool-down (15 s, doubling to 5 min) during which calls fail
# fast — `_cached` then serves the last good data, marked stale.
_YH: Dict[str, float] = {"until": 0.0, "backoff": 15.0}
_YH_SEM = threading.BoundedSemaphore(6)


def _rate_limited(e: BaseException) -> bool:
    m = f"{type(e).__name__} {e}"
    return "RateLimit" in m or "Too Many Requests" in m or "Rate limited" in m or " 429" in m


def _yahoo_cooling() -> Optional[str]:
    left = _YH["until"] - time.time()
    return f"Yahoo is rate-limiting this server — pausing requests for {int(left) + 1}s." if left > 0 else None


def _yahoo_tripped() -> None:
    _YH["until"] = time.time() + _YH["backoff"]
    logger.warning("[yahoo] rate-limited — cooling down %.0fs", _YH["backoff"])
    _YH["backoff"] = min(300.0, _YH["backoff"] * 2)


# Short cool-downs are waited out rather than returned to the screen as an error.
YAHOO_WAIT_MAX = 20.0


def _wait_or_raise() -> None:
    """During a cool-down: wait if it ends within YAHOO_WAIT_MAX seconds, else fail fast."""
    left = _YH["until"] - time.time()
    if left > YAHOO_WAIT_MAX:
        raise Upstream(_yahoo_cooling() or "Yahoo is rate-limiting this server.")
    if left > 0:
        time.sleep(left)


def yahoo_call(fn: Callable[[], Any]) -> Any:
    """Run one Yahoo request under the guard (waits out a short cool-down; raises Upstream on a long one or a 429)."""
    _wait_or_raise()
    with _YH_SEM:
        try:
            out = fn()
        except Exception as e:
            if _rate_limited(e):
                _yahoo_tripped()
                raise Upstream("Yahoo is rate-limiting this server — try again in a minute.") from e
            raise
    _YH["backoff"] = 15.0
    return out


# Every yfinance HTTP request — including the call sites that use yf.Ticker / yf.download directly — passes through
# this layer: at most YAHOO_HTTP_CONCURRENCY at once and a token bucket (bursts of YAHOO_BURST run at once — a 300-stock
# heat map loads at full speed — while sustained traffic is held to YAHOO_RATE a second, the pattern that draws 429s);
# short cool-downs are waited out, a 429 trips the guard.
YAHOO_HTTP_CONCURRENCY = 4          # per lane: bulk downloads and interactive requests each get their own
YAHOO_RATE = 8.0
YAHOO_BURST = 100.0
_YH_HTTP_SEM = threading.BoundedSemaphore(YAHOO_HTTP_CONCURRENCY)          # bulk lane (yf.download of many symbols)
_YH_LIVE_SEM = threading.BoundedSemaphore(YAHOO_HTTP_CONCURRENCY)          # interactive lane (one quote / one history)
_YH_BUCKET = {"tokens": YAHOO_BURST, "at": time.time()}
_YH_PACE_LOCK = threading.Lock()


def _take_token() -> float:
    """Seconds to wait before the next Yahoo request may start (0 when a token is available)."""
    with _YH_PACE_LOCK:
        now = time.time()
        b = _YH_BUCKET
        b["tokens"] = min(YAHOO_BURST, b["tokens"] + (now - b["at"]) * YAHOO_RATE)
        b["at"] = now
        b["tokens"] -= 1
        return 0.0 if b["tokens"] >= 0 else -b["tokens"] / YAHOO_RATE


# Tickers currently being fetched by a large yf.download (more than BULK_MIN_SYMBOLS symbols), with a reference count:
# their requests go to the bulk lane; a small download (the dashboard's eight live prices) stays interactive.
BULK_MIN_SYMBOLS = 10
_BULK_TICKERS: Dict[str, int] = {}
_BULK_LOCK = threading.Lock()


def _in_bulk_download() -> bool:
    """True for a request made on behalf of a ticker in a large multi-ticker download."""
    import sys
    f = sys._getframe(2)
    while f is not None:
        if f.f_code.co_name in ("_download_one", "_download_one_threaded") and f.f_code.co_filename.endswith("multi.py"):
            t = str(f.f_locals.get("ticker") or "").upper()
            with _BULK_LOCK:
                return _BULK_TICKERS.get(t, 0) > 0
        f = f.f_back
    return False


def _install_bulk_registry() -> None:
    """Wrap yf.download so the tickers of a large download are registered for its duration."""
    try:
        import yfinance as _yf
        from yfinance import multi as _multi
    except Exception:
        return
    if getattr(_multi.download, "_registered", False):
        return
    orig = _multi.download

    def download(tickers, *a, **kw):
        lst = tickers if isinstance(tickers, (list, tuple, set)) else str(tickers).replace(",", " ").split()
        lst = [str(t).upper() for t in lst]
        bulk = len(lst) > BULK_MIN_SYMBOLS
        if bulk:
            with _BULK_LOCK:
                for t in lst:
                    _BULK_TICKERS[t] = _BULK_TICKERS.get(t, 0) + 1
        try:
            return orig(tickers, *a, **kw)
        finally:
            if bulk:
                with _BULK_LOCK:
                    for t in lst:
                        n = _BULK_TICKERS.get(t, 0) - 1
                        if n > 0:
                            _BULK_TICKERS[t] = n
                        else:
                            _BULK_TICKERS.pop(t, None)
    download._registered = True
    _multi.download = download
    _yf.download = download


def _install_yahoo_throttle() -> None:
    try:
        from yfinance import data as _yd
    except Exception:                                   # yfinance missing: nothing to throttle
        return
    if getattr(_yd.YfData._make_request, "_throttled", False):
        return
    orig = _yd.YfData._make_request

    def throttled(self, *a, **kw):
        _wait_or_raise()
        bulk = _in_bulk_download()
        with (_YH_HTTP_SEM if bulk else _YH_LIVE_SEM):
            wait = _take_token()
            if bulk and wait > 0:            # only bulk downloads queue on the bucket; a single quote never waits
                time.sleep(wait)             # behind a 300-ticker heat map (it still spends a token)
            try:
                return orig(self, *a, **kw)
            except Exception as e:
                if _rate_limited(e):
                    _yahoo_tripped()
                raise
    throttled._throttled = True
    _yd.YfData._make_request = throttled


_install_yahoo_throttle()
_install_bulk_registry()


def yahoo_download(symbols, **kw):
    """yf.download under the guard. yfinance swallows per-symbol errors into a dict instead of
    raising, so an empty frame caused by a 429 would otherwise look like 'no price history'."""
    import yfinance as yf

    def run():
        df = yf.download(symbols, progress=False, **kw)
        errs = getattr(getattr(yf, "shared", None), "_ERRORS", {}) or {}
        if any(_rate_limited(Exception(str(v))) for v in errs.values()):
            raise Upstream("Too Many Requests")
        return df
    return yahoo_call(run)


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


TYPE_LABEL = {"EQUITY": "Stock", "ETF": "ETF", "MUTUALFUND": "Fund", "INDEX": "Index", "CURRENCY": "FX",
              "CRYPTOCURRENCY": "Crypto", "FUTURE": "Future", "OPTION": "Option", "MONEYMARKET": "Money market"}


# ── Search ───────────────────────────────────────────────────────────────────
def search(q: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Search securities by name or ticker."""
    q = q.strip()
    if not q:
        return []

    def fetch():
        import yfinance as yf
        try:
            res = yf.Search(q, max_results=limit, news_count=0, enable_fuzzy_query=True).quotes or []
        except Exception as e:
            raise Upstream(f"Search unavailable: {e}")
        out = []
        for r in res:
            sym = r.get("symbol")
            if not sym:
                continue
            t = (r.get("quoteType") or "").upper()
            out.append({"symbol": sym, "name": r.get("longname") or r.get("shortname") or sym,
                        "type": TYPE_LABEL.get(t, t.title() or "Other"), "exchange": r.get("exchDisp") or r.get("exchange"),
                        "sector": r.get("sectorDisp") or r.get("sector"), "industry": r.get("industryDisp") or r.get("industry")})
        alias = SEARCH_ALIASES.get(q.lower())
        if alias and alias[0] not in {h["symbol"] for h in out}:
            out.insert(0, {"symbol": alias[0], "name": alias[1], "type": "Stock", "exchange": None, "sector": None, "industry": None,
                           "home_listing": True})
        return _home_first(out)[:limit]
    return _cached(f"search:{q.lower()}:{limit}", 600, fetch)


# Common names Yahoo's search doesn't resolve to the company (abbreviations, brands)
SEARCH_ALIASES = {"tsmc": ("2330.TW", "Taiwan Semiconductor Manufacturing"), "lvmh": ("MC.PA", "LVMH Moët Hennessy Louis Vuitton"),
                  "tencent": ("0700.HK", "Tencent Holdings"), "alibaba": ("9988.HK", "Alibaba Group"), "byd": ("1211.HK", "BYD Company"),
                  "aramco": ("2222.SR", "Saudi Aramco"), "hsbc": ("HSBA.L", "HSBC Holdings"), "shell": ("SHEL.L", "Shell plc"),
                  "unilever": ("ULVR.L", "Unilever"), "nestle": ("NESN.SW", "Nestlé"), "novo": ("NOVO-B.CO", "Novo Nordisk"),
                  "novo nordisk": ("NOVO-B.CO", "Novo Nordisk"), "samsung": ("005930.KS", "Samsung Electronics"),
                  "reliance": ("RELIANCE.NS", "Reliance Industries"), "sap": ("SAP.DE", "SAP SE"), "siemens": ("SIE.DE", "Siemens")}


def _home_first(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Put a foreign company's home listing ahead of its US ADR or OTC line ("toyota" → 7203.T
    before TM), as Bloomberg resolves names to the primary listing."""
    try:
        from api import global_universe as gu
        u = gu.load(rebuild_if_stale=False)
        items = u if isinstance(u, list) else (u.get("stocks") or [])
        by_name = _cached("search:homes", 86400, lambda: {_norm(x.get("name")): x for x in items
                                                          if x.get("name") and "." in str(x.get("symbol", ""))})
    except Exception:
        return hits
    out: List[Dict[str, Any]] = []
    placed = set()
    for h in hits:
        if h["symbol"] in placed:
            continue
        home = by_name.get(_norm(h.get("name"))) if h.get("type") == "Stock" and "." not in h["symbol"] else None
        if home and home["symbol"] != h["symbol"] and home["symbol"] not in placed:
            found = next((x for x in hits if x["symbol"] == home["symbol"]), None)      # already listed further down?
            out.append({**(found or {"symbol": home["symbol"], "name": home.get("name"), "type": "Stock", "exchange": home.get("exchange"),
                                      "sector": home.get("sector"), "industry": None}), "home_listing": True})
            placed.add(home["symbol"])
        out.append(h)
        placed.add(h["symbol"])
    return out


# ── Quotes ───────────────────────────────────────────────────────────────────
def _info(symbol: str) -> Dict[str, Any]:
    import yfinance as yf

    def fetch():
        try:
            info = yahoo_call(lambda: yf.Ticker(symbol).info or {})
        except Upstream:
            raise
        except Exception as e:
            raise Upstream(f"Yahoo unavailable for {symbol}: {e}")
        if not info or (info.get("regularMarketPrice") is None and info.get("previousClose") is None
                        and info.get("navPrice") is None and not info.get("longName") and not info.get("shortName")):
            raise NotFound(f"No instrument found for '{symbol}'.")
        return info
    return _cached(f"info:{symbol}", 60, fetch)


def _sane_yield(fwd: Optional[float], trailing: Optional[float]) -> Optional[float]:
    """Yahoo's forward yield keeps the pre-split dividend rate for a while after a split
    (Tokio Marine showed 25% after its 10:1 split); fall back to the trailing yield then."""
    if fwd is not None and fwd > 0.15 and trailing is not None and trailing < fwd / 3:
        return trailing
    return fwd


def div_yield(i: Dict[str, Any]) -> Optional[float]:
    """Dividend yield as a decimal. Yahoo's `dividendYield` is always in percent (0.32 = 0.32%,
    2.42 = 2.42%); funds carry a decimal `yield` instead."""
    dy = _f(i.get("dividendYield"))
    if dy is not None:
        return _sane_yield(dy / 100, _f(i.get("trailingAnnualDividendYield")))
    y = _f(i.get("yield"))
    return y if y is not None else _f(i.get("trailingAnnualDividendYield"))


def _finnhub_quote(sym: str) -> Optional[Dict[str, Any]]:
    """Real-time US quote from Finnhub (free key, 60 calls/min) — None if unavailable."""
    import os
    key = os.getenv("FINNHUB_API_KEY") or ""
    if not key or any(c in sym for c in ".^=") or sym.endswith("-USD"):
        return None

    def fetch():
        import requests
        r = requests.get("https://finnhub.io/api/v1/quote", params={"symbol": sym, "token": key}, timeout=6)
        if r.status_code != 200:
            return None
        j = r.json()
        return j if (j.get("c") or 0) > 0 else None
    try:
        return _cached(f"fh:{sym}", 10, fetch)
    except Exception:
        return None


def quote(symbol: str) -> Dict[str, Any]:
    """A security's latest quote and key statistics."""
    s = symbol.strip().upper()
    i = _info(s)
    price = _f(i.get("regularMarketPrice")) or _f(i.get("currentPrice")) or _f(i.get("navPrice"))
    prev = _f(i.get("regularMarketPreviousClose")) or _f(i.get("previousClose"))
    chg = price - prev if price is not None and prev else None
    t = (i.get("quoteType") or "").upper()
    return {"symbol": s, "name": i.get("longName") or i.get("shortName") or s, "type": TYPE_LABEL.get(t, t.title()),
            "exchange": i.get("fullExchangeName") or i.get("exchange"), "currency": i.get("currency"),
            "price": price, "previous_close": prev, "change": chg, "change_pct": chg / prev if chg is not None else None,
            "open": _f(i.get("regularMarketOpen")) or None, "day_high": _f(i.get("regularMarketDayHigh")) or None,     # 0 = no range (yield indices)
            "day_low": _f(i.get("regularMarketDayLow")) or None, "volume": _f(i.get("regularMarketVolume")),
            "avg_volume": _f(i.get("averageVolume")), "week52_high": _f(i.get("fiftyTwoWeekHigh")),
            "week52_low": _f(i.get("fiftyTwoWeekLow")), "market_cap": _f(i.get("marketCap")),
            "market_state": i.get("marketState"), "exchange_timezone": i.get("exchangeTimezoneName"),
            "quote_time": i.get("regularMarketTime"), "delay_minutes": i.get("exchangeDataDelayedBy"),
            **_quote_extras(i, price, prev),
            "source": "Yahoo Finance"} | _realtime(s, i)


def _realtime(s: str, i: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay a real-time last price: Finnhub for US-listed stocks and ETFs; for other listings the user's own
    connections when they are running — Futu for Hong Kong (LV1 real-time), IBKR TWS where the account's
    market-data subscription is real-time. Never a delayed price in place of Yahoo's."""
    t = (i.get("quoteType") or "").upper()
    if t == "CRYPTOCURRENCY":
        return _crypto_realtime(s, i)
    if t not in ("EQUITY", "ETF"):
        return {}
    if (i.get("currency") or "USD") != "USD" or "." in s:
        return _local_realtime(s)
    fh = _finnhub_quote(s)
    if not fh:
        return {}
    return {"price": fh["c"], "change": fh.get("d"), "change_pct": (fh.get("dp") or 0) / 100 if fh.get("dp") is not None else None,
            "day_high": fh.get("h") or None, "day_low": fh.get("l") or None, "open": fh.get("o") or None, "previous_close": fh.get("pc") or None,
            "quote_time": fh.get("t"), "delay_minutes": 0, "source": "Finnhub (real-time) · fundamentals Yahoo Finance"}


def _crypto_realtime(s: str, i: Dict[str, Any]) -> Dict[str, Any]:
    """Live crypto price from Coinbase / Binance's free public APIs; the change stays against Yahoo's previous close."""
    from api.providers import crypto_live as cl
    coin = cl.coin_of(s)
    ref = _f(i.get("regularMarketPrice"))
    q = cl.price(coin) if coin else {}
    if not q or not cl.plausible(q.get("price"), ref):
        return {}
    p, prev = q["price"], _f(i.get("regularMarketPreviousClose")) or _f(i.get("previousClose"))
    out = {"price": p, "delay_minutes": 0, "quote_time": q.get("time"), "source": f"{q['source']} · statistics Yahoo Finance"}
    if q.get("bid") and q.get("ask") and q["bid"] <= q["ask"]:
        out |= {"bid": q["bid"], "ask": q["ask"]}
    if prev:
        out |= {"change": p - prev, "change_pct": p / prev - 1}
    hi, lo = _f(i.get("regularMarketDayHigh")), _f(i.get("regularMarketDayLow"))
    if hi and p > hi:
        out["day_high"] = p
    if lo and p < lo:
        out["day_low"] = p
    return out


def crypto_overlay(rows: List[Dict[str, Any]], price_key: str = "price", change_key: Optional[str] = "change_1d") -> Optional[str]:
    """Replace the price of every -USD row with the live exchange price (one request for all), re-deriving the 1-day
    change from the implied previous close. Returns the live source's name when any row changed."""
    from api.providers import crypto_live as cl
    if not any(cl.coin_of(str(r.get("symbol") or "")) for r in rows):
        return None
    live = cl.prices()
    used = False
    for r in rows:
        coin = cl.coin_of(str(r.get("symbol") or ""))
        p, old = (live["coins"].get(coin) if coin else None), r.get(price_key)
        if not cl.plausible(p, old):
            continue
        if change_key and r.get(change_key) is not None and old:
            prev = old / (1 + r[change_key])
            r[change_key] = p / prev - 1
        r[price_key], r["live"] = p, True
        used = True
    return live["source"] if used else None


def _local_realtime(s: str) -> Dict[str, Any]:
    """Real-time price for a non-US listing from FutuOpenD (Hong Kong) or TWS (real-time subscriptions only)."""
    def fetch():
        if s.endswith(".HK"):
            try:
                from api.providers import futu_provider as fp
                if fp.opend_running():
                    r = fp.snapshot([s])
                    if r and r[0].get("price"):
                        q = r[0]
                        return {"price": q["price"], "previous_close": q.get("previous_close"),
                                "change": q["price"] - q["previous_close"] if q.get("previous_close") else None,
                                "change_pct": q.get("change_pct"), "day_high": q.get("high"), "day_low": q.get("low"),
                                "delay_minutes": 0, "source": "Futu (real-time) · fundamentals Yahoo Finance"}
            except Exception as e:
                logger.debug("[quote] futu %s: %s", s, e)
        try:
            from api.providers import ibkr_tws as it
            if it.tws_running():
                r = it.quotes([s])
                if r and r[0].get("price") and not r[0].get("delayed"):
                    q = r[0]
                    return {"price": q["price"], "previous_close": q.get("previous_close"),
                            "change": q["price"] - q["previous_close"] if q.get("previous_close") else None,
                            "change_pct": q.get("change_pct"), "delay_minutes": 0,
                            "source": "Interactive Brokers (real-time) · fundamentals Yahoo Finance"}
        except Exception as e:
            logger.debug("[quote] ibkr %s: %s", s, e)
        return {}
    try:
        return _cached(f"rt_local:{s}", 5, fetch)
    except Exception:
        return {}


def _quote_extras(i: Dict[str, Any], price: Optional[float], prev: Optional[float]) -> Dict[str, Any]:
    """Brokerage-style quote fields: top of book, extended hours, valuation, activity."""
    vol, hi, lo = _f(i.get("regularMarketVolume")), _f(i.get("regularMarketDayHigh")), _f(i.get("regularMarketDayLow"))
    flt = _f(i.get("floatShares"))
    dy = div_yield(i)
    pre, post = _f(i.get("preMarketPrice")), _f(i.get("postMarketPrice"))
    bid, ask = _f(i.get("bid")), _f(i.get("ask"))
    if bid and ask and bid > ask:          # stale crossed book outside the session — show neither side
        bid = ask = None
    fund = (i.get("quoteType") or "").upper() in ("ETF", "MUTUALFUND", "INDEX", "CURRENCY", "FUTURE", "CRYPTOCURRENCY")
    pe = lambda k: None if fund else (lambda v: v if v is not None and 0 < v < 5000 else None)(_f(i.get(k)))   # negative earnings → NM
    return {
        "bid": bid if bid else None, "ask": ask if ask else None,
        "bid_size": _f(i.get("bidSize")) or None, "ask_size": _f(i.get("askSize")) or None,
        "pre_market_price": pre, "pre_market_change_pct": (pre / prev - 1) if pre and prev else None,
        "post_market_price": post, "post_market_change_pct": (post / price - 1) if post and price else None,
        "trailing_pe": pe("trailingPE"), "forward_pe": pe("forwardPE"), "price_to_book": _f(i.get("priceToBook")),
        "eps_ttm": _f(i.get("epsTrailingTwelveMonths")) or _f(i.get("trailingEps")), "dividend_yield": dy,
        "beta": _f(i.get("beta")), "shares_outstanding": _f(i.get("sharesOutstanding")), "float_shares": flt,
        "turnover": price * vol if price and vol else None,
        "turnover_ratio": vol / flt if vol and flt else None,
        "amplitude": (hi - lo) / prev if hi and lo and prev else None,
        "avg_volume_10d": _f(i.get("averageDailyVolume10Day")),
        "volume_ratio": vol / _f(i.get("averageDailyVolume10Day")) if vol and _f(i.get("averageDailyVolume10Day")) else None,
    }


def tape(symbol: str) -> Dict[str, Any]:
    """Today's session from 1-minute bars: recent prints, VWAP, a tick-rule split of volume into
    buying and selling, and a volume-by-price profile. (Free data has no true tick-by-tick
    trades or order book; one-minute bars are the finest free granularity.)"""
    s = symbol.strip().upper()

    def fetch():
        import yfinance as yf
        try:
            df = yf.Ticker(s).history(period="5d", interval="1m", prepost=False, auto_adjust=False)
        except Exception as e:
            raise Upstream(f"Intraday data unavailable for {s}: {e}")
        if df is None or df.empty:
            raise NotFound(f"No intraday data for {s}.")
        last_day = df.index[-1].date()
        d = df[df.index.date == last_day]
        d = d[d["Volume"].fillna(0) >= 0]
        closes, vols = d["Close"].astype(float), d["Volume"].fillna(0).astype(float)
        prints, up_v, down_v, flat_v = [], 0.0, 0.0, 0.0
        prev = None
        for ts, c, v in zip(d.index, closes, vols):
            side = 0 if prev is None or c == prev else (1 if c > prev else -1)
            if side > 0:
                up_v += v
            elif side < 0:
                down_v += v
            else:
                flat_v += v
            prints.append({"time": ts.strftime("%H:%M"), "price": c, "volume": v, "side": side})
            prev = c
        vwap = float((d["Close"] * d["Volume"]).sum() / d["Volume"].sum()) if d["Volume"].sum() > 0 else None
        # volume profile: 24 price buckets across the day's range
        lo, hi = float(d["Low"].min()), float(d["High"].max())
        buckets: List[Dict[str, Any]] = []
        if hi > lo:
            n = 24
            step = (hi - lo) / n
            vol_at = [0.0] * n
            for c, v in zip(closes, vols):
                k = min(n - 1, int((c - lo) / step))
                vol_at[k] += v
            buckets = [{"price_low": lo + k * step, "price_high": lo + (k + 1) * step, "volume": vol_at[k]} for k in range(n)]
        tz = str(df.index.tz) if df.index.tz is not None else None
        return {"symbol": s, "date": str(last_day), "timezone": tz, "prints": prints[-80:][::-1], "bars": len(d),
                "vwap": vwap, "high": hi, "low": lo, "volume": float(vols.sum()),
                "up_volume": up_v, "down_volume": down_v, "flat_volume": flat_v, "profile": buckets,
                "method": "1-minute bars (Yahoo). Buy/sell split by the tick rule: volume in a minute that closed up counts as "
                          "buying, down as selling — an estimate, not exchange-reported order flow."}

    out = _cached(f"tape:{s}", 60, fetch)
    return {**out, **_futu_tape(s, out)}


def _futu_tape(s: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """With FutuOpenD running and a quote right for the market: the latest prints as real ticks carrying the exchange's
    buy / sell flag, and the day's buy / sell split from Futu's full-day buyer- vs seller-initiated turnover. Empty
    otherwise (the 1-minute-bar estimate stands)."""
    try:
        from api.providers import futu_provider as fp
        if not fp.opend_running() or not fp.to_futu(s):
            return {}
        t = fp.ticks(s, 300)
        flow = fp.capital_flow(s)
    except Exception as e:
        logger.debug("[tape] futu %s: %s", s, e)
        return {}
    sizes = flow.get("by_order_size") or {}
    tin = sum((v.get("in") or 0) for v in sizes.values())
    tout = sum((v.get("out") or 0) for v in sizes.values())
    extra: Dict[str, Any] = {}
    if t.get("ticks"):
        extra["prints"] = [{"time": str(x["time"])[11:19], "price": x["price"], "volume": x["volume"], "side": x["side"]}
                           for x in t["ticks"][:80]]
    if tin + tout > 0:
        share = tin / (tin + tout)
        vol = base.get("volume") or 0.0
        extra.update(up_volume=vol * share, down_volume=vol * (1 - share), flat_volume=0.0, buy_share=share)
    if extra:
        extra["method"] = ("Futu: prints are exchange ticks with their buy / sell direction; the day's buy / sell split is "
                           "Futu's buyer- vs seller-initiated turnover. VWAP and the volume profile use 1-minute bars (Yahoo).")
        extra["source"] = "Futu OpenAPI (ticks, capital flow) · Yahoo 1-minute bars"
    return extra


OVERVIEW: Dict[str, List[tuple]] = {
    "Equity indices": [("^GSPC", "S&P 500"), ("^NDX", "Nasdaq 100"), ("^DJI", "Dow Jones"), ("^RUT", "Russell 2000"),
                       ("^GSPTSE", "TSX"), ("^BVSP", "Bovespa"), ("^STOXX50E", "Euro Stoxx 50"), ("^FTSE", "FTSE 100"),
                       ("^GDAXI", "DAX"), ("^FCHI", "CAC 40"), ("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"),
                       ("000001.SS", "Shanghai Comp."), ("^KS11", "KOSPI"), ("^TWII", "Taiwan"), ("^BSESN", "Sensex"),
                       ("^AXJO", "ASX 200")],
    "Rates & volatility": [("^IRX", "US 3M yield"), ("^FVX", "US 5Y yield"), ("^TNX", "US 10Y yield"), ("^TYX", "US 30Y yield"),
                           ("^VIX", "VIX"), ("^MOVE", "MOVE (bond vol)")],
    "Currencies": [("DX-Y.NYB", "Dollar index"), ("EURUSD=X", "EUR/USD"), ("GBPUSD=X", "GBP/USD"), ("JPY=X", "USD/JPY"),
                   ("CHF=X", "USD/CHF"), ("AUDUSD=X", "AUD/USD"), ("CAD=X", "USD/CAD"), ("CNY=X", "USD/CNY"),
                   ("INR=X", "USD/INR"), ("MXN=X", "USD/MXN"), ("BRL=X", "USD/BRL")],
    "Commodities": [("CL=F", "WTI crude"), ("BZ=F", "Brent"), ("NG=F", "Natural gas"), ("GC=F", "Gold"), ("SI=F", "Silver"),
                    ("HG=F", "Copper"), ("PL=F", "Platinum"), ("ZC=F", "Corn"), ("ZW=F", "Wheat"), ("ZS=F", "Soybeans"),
                    ("KC=F", "Coffee"), ("CT=F", "Cotton")],
    "Crypto": [("BTC-USD", "Bitcoin"), ("ETH-USD", "Ether"), ("SOL-USD", "Solana"), ("XRP-USD", "XRP"),
               ("BNB-USD", "BNB"), ("DOGE-USD", "Dogecoin")],
}


YIELDS = {"^IRX", "^FVX", "^TNX", "^TYX"}


def _month_ago(c) -> Optional[float]:
    """Close on or before the same day a month earlier (calendar-based, so 7-day markets work)."""
    import pandas as pd
    prior = c[c.index <= c.index[-1] - pd.DateOffset(months=1)]
    return float(prior.iloc[-1]) if len(prior) else None


def overview() -> Dict[str, Any]:
    """Last price and 1-day / 1-month / YTD change for each instrument, one batched download."""
    def fetch():
        import pandas as pd
        import yfinance as yf
        syms = [s for g in OVERVIEW.values() for s, _ in g]
        try:
            df = yf.download(syms, period="1y", interval="1d", auto_adjust=False, group_by="ticker",
                             threads=True, progress=False)
        except Exception as e:
            raise Upstream(f"Market data unavailable: {e}")
        groups = []
        for g, items in OVERVIEW.items():
            rows = []
            for s, label in items:
                try:
                    c = df[s]["Close"].dropna()
                    if s.endswith("=X") or s.endswith("=F") or s.startswith("^"):
                        c = c[c.index.dayofweek < 5]      # no weekend prints outside crypto
                except Exception:
                    c = pd.Series(dtype=float)
                if len(c) < 2:
                    rows.append({"symbol": s, "name": label, "price": None})
                    continue
                last = float(c.iloc[-1])
                ytd = c[c.index.year == c.index[-1].year]
                base_ytd = c[c.index.year < c.index[-1].year]
                if s in YIELDS:     # yields move in basis points, not percent of the level
                    prev_y = base_ytd.iloc[-1] if len(base_ytd) else ytd.iloc[0]
                    rows.append({"symbol": s, "name": label, "price": last, "date": c.index[-1].strftime("%Y-%m-%d"), "is_yield": True,
                                 "change_1d_bp": (last - float(c.iloc[-2])) * 100,
                                 "change_1m_bp": (last - m1) * 100 if (m1 := _month_ago(c)) is not None else None,
                                 "change_ytd_bp": (last - float(prev_y)) * 100,
                                 "spark": [round(float(x), 6) for x in c.iloc[-60:]]})
                    continue
                prev1 = float(c.iloc[-2])
                if s.endswith("=X") and (fx := fx_last_prev(s, c)):         # FX: previous close from the ECB fixing
                    last, prev1 = fx[0], fx[1]
                rows.append({"symbol": s, "name": label, "price": last, "date": c.index[-1].strftime("%Y-%m-%d"),
                             "change_1d": last / prev1 - 1,
                             "change_1m": (last / m1 - 1) if (m1 := _month_ago(c)) else None,     # by date: crypto trades 7 days
                             "change_ytd": last / float(base_ytd.iloc[-1]) - 1 if len(base_ytd) else (last / float(ytd.iloc[0]) - 1 if len(ytd) else None),
                             "spark": [round(float(x), 6) for x in c.iloc[-60:]]})
            groups.append({"group": g, "rows": rows,
                           "is_yield": g == "Rates & volatility"})
        return {"groups": groups, "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "Yahoo Finance"}
    base = _cached("overview", 120, fetch)
    try:                                                     # live crypto on top of the cached board, without mutating it
        groups = [{**g, "rows": [dict(r) for r in g["rows"]]} for g in base.get("groups", [])]
        src = crypto_overlay([r for g in groups for r in g["rows"]])
        if src:
            return {**base, "groups": groups, "source": f"{base.get('source', 'Yahoo Finance')} · crypto {src}"}
    except Exception as e:
        logger.debug("[overview] crypto overlay: %s", e)
    return base


# ── Profile ──────────────────────────────────────────────────────────────────
def profile(symbol: str) -> Dict[str, Any]:
    """A company's profile: sector, industry, description, officers, key figures."""
    s = symbol.strip().upper()
    i = _info(s)
    t = (i.get("quoteType") or "").upper()
    base = {"symbol": s, "name": i.get("longName") or i.get("shortName") or s, "type": TYPE_LABEL.get(t, t.title()),
            "currency": i.get("currency"), "exchange": i.get("fullExchangeName") or i.get("exchange"),
            "description": i.get("longBusinessSummary") or i.get("description")}
    if t == "EQUITY":
        base.update({"sector": i.get("sector"), "industry": i.get("industry"), "country": i.get("country"),
                     "website": i.get("website"), "employees": i.get("fullTimeEmployees"),
                     "valuation": {k: _f(i.get(v)) for k, v in (("trailing_pe", "trailingPE"), ("forward_pe", "forwardPE"),
                                   ("price_to_book", "priceToBook"), ("price_to_sales", "priceToSalesTrailing12Months"),
                                   ("ev_to_ebitda", "enterpriseToEbitda"), ("peg", "trailingPegRatio"),
                                   ("beta", "beta"))} | {"dividend_yield": div_yield(i)},
                     "analysts": {"target_mean": _f(i.get("targetMeanPrice")), "target_low": _f(i.get("targetLowPrice")),
                                  "target_high": _f(i.get("targetHighPrice")), "recommendation": i.get("recommendationKey"),
                                  "analysts": i.get("numberOfAnalystOpinions")}})
        dy = base["valuation"].get("dividend_yield")
        if dy is not None and dy > 1:                # Yahoo reports this in percent for some listings
            base["valuation"]["dividend_yield"] = dy / 100
    elif t in ("ETF", "MUTUALFUND"):
        base.update({"category": i.get("category"), "fund_family": i.get("fundFamily"),
                     # netExpenseRatio is in percent (SPY 0.0945 = 0.0945%); the older field is a decimal
                     "expense_ratio": (_f(i.get("netExpenseRatio")) / 100 if _f(i.get("netExpenseRatio")) is not None
                                       else _f(i.get("annualReportExpenseRatio"))),
                     "total_assets": _f(i.get("totalAssets")), "yield": _f(i.get("yield")),
                     "inception": i.get("fundInceptionDate"),
                     "ytd_return": (_f(i.get("ytdReturn")) / 100) if _f(i.get("ytdReturn")) is not None else None})     # percent → decimal
    else:
        base.update({"underlying": i.get("underlyingSymbol"), "expiry": i.get("expireDate"),
                     "open_interest": _f(i.get("openInterest")), "circulating_supply": _f(i.get("circulatingSupply"))})
    return base


# ── Statements ───────────────────────────────────────────────────────────────
KEY_LINES = {
    "income": ["Total Revenue", "Cost Of Revenue", "Gross Profit", "Operating Expense", "Research And Development",
               "Selling General And Administration", "Operating Income", "EBITDA", "EBIT", "Interest Expense",
               "Pretax Income", "Tax Provision", "Net Income", "Net Income Common Stockholders", "Diluted EPS", "Basic EPS",
               "Diluted Average Shares"],
    "balance": ["Total Assets", "Current Assets", "Cash And Cash Equivalents", "Receivables", "Inventory",
                "Total Liabilities Net Minority Interest", "Current Liabilities", "Total Debt", "Long Term Debt",
                "Stockholders Equity", "Total Equity Gross Minority Interest", "Net Debt", "Working Capital",
                "Ordinary Shares Number"],
    "cashflow": ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow", "Investing Cash Flow",
                 "Financing Cash Flow", "Cash Dividends Paid", "Repurchase Of Capital Stock", "Issuance Of Debt",
                 "Repayment Of Debt", "End Cash Position"],
}
def statements(symbol: str) -> Dict[str, Any]:
    """SEC EDGAR (official, as filed) for US filers; Yahoo statements otherwise."""
    from api.providers import sec_edgar
    s = symbol.strip().upper()
    try:
        if sec_edgar.resolve(s):
            return {**sec_edgar.statements(s), "provider": "sec"}
    except LookupError:
        pass
    except sec_edgar.EdgarError as e:
        logger.info("[markets] EDGAR unavailable for %s: %s", s, e)

    def fetch():
        import yfinance as yf
        tk = yf.Ticker(s)
        tables = {}
        for key, attr in (("income", "income_stmt"), ("balance", "balance_sheet"), ("cashflow", "cashflow"),
                          ("income_q", "quarterly_income_stmt"), ("balance_q", "quarterly_balance_sheet"),
                          ("cashflow_q", "quarterly_cashflow")):
            try:
                df = getattr(tk, attr)
            except Exception:
                df = None
            if df is None or df.empty:
                continue
            df = df.iloc[:, :8]
            df = df.loc[:, df.notna().sum() >= 3]                 # yfinance pads with near-empty old periods
            if df.empty:
                continue
            rows = [{"item": str(idx), "values": [_f(v) for v in row]} for idx, row in df.iterrows()]
            rows = [r for r in rows if any(v not in (None, 0) for v in r["values"])]      # drop empty / all-zero lines
            order = {name: i for i, name in enumerate(KEY_LINES.get(key.replace("_q", ""), []))}
            rows.sort(key=lambda r: order.get(r["item"], len(order)))                     # standard lines first
            tables[key] = {"periods": [c.strftime("%Y-%m-%d") for c in df.columns], "rows": rows,
                           "key_lines": len([r for r in rows if r["item"] in order])}
        if not tables:
            raise NotFound(f"No financial statements available for {s}.")
        # headline ratios from the latest annual statements (same tiles as the SEC view)
        def latest(tab, item):
            t = tables.get(tab)
            row = next((r for r in (t or {}).get("rows", []) if r["item"] == item), None)
            return row["values"][0] if row and row["values"] else None
        def ratio(a, b):
            return round(a / b, 4) if a is not None and b not in (None, 0) else None
        rev, ni, eq = latest("income", "Total Revenue"), latest("income", "Net Income"), latest("balance", "Stockholders Equity")
        ratios = {"gross_margin": ratio(latest("income", "Gross Profit"), rev), "operating_margin": ratio(latest("income", "Operating Income"), rev),
                  "net_margin": ratio(ni, rev), "fcf_margin": ratio(latest("cashflow", "Free Cash Flow"), rev),
                  "roe": ratio(ni, eq), "roa": ratio(ni, latest("balance", "Total Assets")),
                  "debt_to_equity": ratio(latest("balance", "Total Debt"), eq),
                  "current_ratio": ratio(latest("balance", "Current Assets"), latest("balance", "Current Liabilities"))}
        return {"ticker": s, "provider": "yahoo", "tables": tables, "ratios": ratios, "currency": _info(s).get("financialCurrency"),
                "source": "Yahoo Finance (company reports)"}
    return _cached(f"stmts2:{s}", 6 * 3600, fetch)


# ── News & filings ───────────────────────────────────────────────────────────
# currency names used in FX headlines ("euro", "yen", "sterling"…), for currency-pair news
CCY_WORDS = {"EUR": ["euro"], "JPY": ["yen"], "GBP": ["sterling", "pound"], "CHF": ["swiss franc", "franc"], "AUD": ["aussie", "australian dollar"],
             "CAD": ["loonie", "canadian dollar"], "NZD": ["kiwi", "new zealand dollar"], "CNY": ["yuan", "renminbi"], "CNH": ["yuan", "renminbi"],
             "HKD": ["hong kong dollar"], "INR": ["rupee"], "KRW": ["won"], "MXN": ["peso"], "BRL": ["real"], "ZAR": ["rand"], "TRY": ["lira"],
             "SEK": ["krona"], "NOK": ["krone"], "SGD": ["singapore dollar"], "TWD": ["taiwan dollar"], "RUB": ["rouble", "ruble"],
             "PLN": ["zloty"], "IDR": ["rupiah"], "THB": ["baht"], "USD": ["dollar", "greenback"]}


def _fx_pair(s: str) -> Optional[Tuple[str, str]]:
    """EURUSD=X → (EUR, USD); JPY=X → (USD, JPY)."""
    if not s.endswith("=X"):
        return None
    b = s[:-2]
    return (b[:3], b[3:6]) if len(b) == 6 else (("USD", b) if len(b) == 3 else None)


def news(symbol: str) -> Dict[str, Any]:
    """Latest headlines for a symbol."""
    s = symbol.strip().upper()
    pair = _fx_pair(s)

    def fetch():
        # Yahoo's per-ticker news feed went empty in 2026; its search endpoint still returns
        # headlines, so query by the instrument's name (falls back to the ticker feed).
        import yfinance as yf
        items = []
        try:
            name = _info(s).get("shortName") or s
        except Exception:
            name = s
        try:
            # several queries — the full name retrieves poorly ("NVIDIA Corporation", "SAP SE"):
            # the distinctive name word, the name, and the ticker; merged and de-duplicated
            first = next((w for w in _norm(name).split() if len(w) >= 3), None)
            queries = list(dict.fromkeys(q for q in (first, name, s.split(".")[0] if "." in s else s) if q))
            if pair:                                            # "EUR/USD", "euro dollar": not the 3-letter code
                foreign = pair[0] if pair[0] != "USD" else pair[1]
                queries = [f"{pair[0]}/{pair[1]}", f"{CCY_WORDS.get(foreign, [foreign])[0]} {CCY_WORDS.get(pair[1] if foreign == pair[0] else pair[0], ['dollar'])[0]}"]
            raw, seen_t = [], set()
            for q in queries:
                try:
                    for n in yf.Search(q, max_results=1, news_count=15).news or []:
                        t0 = ((n.get("content") or n).get("title") or "").strip().lower()
                        if t0 and t0 not in seen_t:
                            seen_t.add(t0)
                            raw.append(n)
                except Exception:
                    continue
            if not raw:
                raw = yf.Ticker(s).news or []
            if pair:
                foreign = pair[0] if pair[0] != "USD" else pair[1]
                gq = f'"{pair[0]}/{pair[1]}" OR "{CCY_WORDS.get(foreign, [foreign])[0]}" currency OR forex'
                raw = _extra_company_news(s, None, query=gq) + raw
            else:
                raw = _extra_company_news(s, first or name) + raw      # company-specific sources first
            for n in raw[:60]:
                c = n.get("content") or n
                url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
                       or c.get("link"))
                t = c.get("pubDate") or c.get("providerPublishTime")
                if isinstance(t, (int, float)):
                    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
                items.append({"title": c.get("title"), "publisher": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
                              "time": t, "url": url, "summary": c.get("summary")})
        except Exception as e:
            logger.info("[markets] news unavailable for %s: %s", s, e)
        items = [i for i in items if i["title"]]
        seen_titles: set = set()                       # the same story from two feeds
        items = [i for i in items if not (i["title"].strip().lower() in seen_titles or seen_titles.add(i["title"].strip().lower()))]
        # Yahoo's name search mixes in general market stories: keep the ones about this company
        # (its name's distinctive words or its ticker); fall back to all if too few match
        import re
        if pair:
            # a currency pair: the pair itself, or a non-dollar currency's name — "EUR 256.00" share-price
            # stories mention the code, not the currency
            terms = [f"{pair[0]}/?{pair[1]}"] + [re.escape(w) for c in pair if c != "USD" for w in CCY_WORDS.get(c, [])]
            pats = [re.compile(rf"\b(?:{t})s?\b", re.I) for t in terms]
            keep = [i for i in items if any(p.search(i["title"]) for p in pats)]
            return sorted(keep, key=lambda i: str(i.get("time") or ""), reverse=True)[:20]
        words = [w for w in _norm(name).split() if len(w) >= 3][:1]       # the distinctive first word ("toyota", not "motor")
        base = s.split(".")[0].split("=")[0].lstrip("^")
        pats = [re.compile(rf"\b{re.escape(w)}", re.I) for w in words] + ([re.compile(rf"\b{re.escape(base)}\b")] if len(base) >= 2 else [])
        about = [i for i in items if any(p.search(f"{i['title']} {i.get('summary') or ''}") for p in pats)]
        is_stock = (_info(s).get("quoteType") or "").upper() == "EQUITY"
        keep = about if (about and is_stock) or len(about) >= 4 else items
        return sorted(keep, key=lambda i: str(i.get("time") or ""), reverse=True)[:20]
    out = {"symbol": s, "news": _cached(f"news2:{s}", 900, fetch), "filings": []}
    try:
        out["filings"] = sec_filings(s)
    except Exception as e:
        logger.info("[markets] filings unavailable for %s: %s", s, e)
    return out


def _extra_company_news(symbol: str, word: Optional[str], query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Company news beyond Yahoo's (often generic) search: Finnhub's company feed for US listings
    (free key) and Google News' RSS search by company name — in Yahoo's item shape."""
    import os
    import re
    import requests
    from email.utils import parsedate_to_datetime
    out: List[Dict[str, Any]] = []
    key = os.getenv("FINNHUB_API_KEY") or ""
    if key and "." not in symbol and "=" not in symbol and not symbol.startswith("^"):
        try:
            today = time.strftime("%Y-%m-%d")
            frm = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 14 * 86400))
            r = requests.get("https://finnhub.io/api/v1/company-news", params={"symbol": symbol, "from": frm, "to": today, "token": key}, timeout=10)
            for x in (r.json() if r.status_code == 200 else [])[:25]:
                out.append({"title": x.get("headline"), "publisher": x.get("source"), "summary": x.get("summary"), "link": x.get("url"),
                            "providerPublishTime": x.get("datetime")})
        except Exception as e:
            logger.debug("[news] finnhub %s: %s", symbol, e)
    if word or query:
        try:
            r = requests.get("https://news.google.com/rss/search", params={"q": query or f'"{word}" stock OR shares OR earnings', "hl": "en-US", "gl": "US", "ceid": "US:en"},
                             headers={"User-Agent": "Mozilla/5.0 (MacroTerminal research)"}, timeout=10)
            for title, link, pub, src in re.findall(r"<item><title>(.*?)</title><link>(.*?)</link>.*?<pubDate>(.*?)</pubDate>.*?<source[^>]*>(.*?)</source>", r.text, re.S)[:20]:
                import html as _h
                t = _h.unescape(title)
                t = re.sub(r"\s+-\s+[^-]+$", "", t)                      # Google appends " - Publisher"
                try:
                    ts = int(parsedate_to_datetime(pub).timestamp())
                except Exception:
                    ts = None
                out.append({"title": t, "publisher": _h.unescape(src), "link": link, "providerPublishTime": ts, "summary": None})
        except Exception as e:
            logger.debug("[news] google %s: %s", word or query, e)
    return out


def sec_filings(symbol: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Latest SEC filings (official submissions feed) for US filers."""
    from api.providers import sec_edgar
    ent = sec_edgar.resolve(symbol)
    if not ent:
        return []

    def fetch():
        j = sec_edgar._get(f"https://data.sec.gov/submissions/CIK{ent['cik']:010d}.json") or {}
        r = (j.get("filings") or {}).get("recent") or {}
        out = []
        for form, date, accn, doc, desc in zip(r.get("form", []), r.get("filingDate", []), r.get("accessionNumber", []),
                                               r.get("primaryDocument", []), r.get("primaryDocDescription", [])):
            if form in ("4", "3", "5", "144", "SC 13G", "SC 13G/A"):
                continue                                # insider/ownership noise
            out.append({"form": form, "date": date, "description": desc or form,
                        "url": f"https://www.sec.gov/Archives/edgar/data/{ent['cik']}/{accn.replace('-', '')}/{doc}"})
            if len(out) >= limit:
                break
        return out
    return _cached(f"filings:{symbol}", 1800, fetch)


# ── Movers & screener ────────────────────────────────────────────────────────
REGIONS = {"us": "United States", "ca": "Canada", "gb": "United Kingdom", "de": "Germany", "fr": "France",
           "nl": "Netherlands", "ch": "Switzerland", "se": "Sweden", "it": "Italy", "es": "Spain", "jp": "Japan",
           "hk": "Hong Kong", "cn": "China", "kr": "South Korea", "tw": "Taiwan", "in": "India", "au": "Australia",
           "sg": "Singapore", "br": "Brazil", "mx": "Mexico", "za": "South Africa", "sa": "Saudi Arabia"}


_SUFFIX_WORDS = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "ag", "se", "sa",
                 "nv", "n.v", "s.a", "s.a.b", "group", "holdings", "holding", "the", "class", "a", "b", "adr", "kgaa", "spa", "s.p.a", "ab",
                 "asa", "oyj", "bhd", "tbk", "pt", "and", "&"}


def _norm(name: Optional[str]) -> str:
    """Company name reduced to its distinctive words (whole-word suffix removal)."""
    import re
    words = re.findall(r"[^\W_][\w&.]*", (name or "").lower())
    words = [w.strip(".") for w in words]
    return " ".join(w for w in words if w and w not in _SUFFIX_WORDS)


# Markets whose main board is the home listing for each other's companies: Hong Kong is the
# primary market for mainland Chinese firms (H-shares, red chips) and vice versa.
HOME_EQUIV = {"hk": {"HK", "CN"}, "cn": {"CN", "HK"}}
# Dual-primary listings that belong in their second market's screens (index constituents there)
DUAL_PRIMARY = {"0005.HK", "2888.HK", "2378.HK", "0945.HK",              # HSBC, StanChart, Prudential, Manulife
                "9988.HK", "9618.HK", "9999.HK", "9888.HK", "9961.HK", "2015.HK", "9868.HK", "9866.HK", "1179.HK"}   # US+HK dual primaries


def _foreign_index(region: str) -> Dict[str, Any]:
    """Large companies whose home listing is OUTSIDE `region` (from the global universe):
    their names, and market values for those over $20bn — to drop cross-listings such as
    Nvidia or GE trading in Frankfurt, even when the line carries an older company name."""
    def build():
        try:
            from api import global_universe as gu
            u = gu.load(rebuild_if_stale=False)
            items = u if isinstance(u, list) else (u.get("stocks") or [])
        except Exception:
            return {"names": set()}
        home = HOME_EQUIV.get(region, {region.upper()})
        # foreign = headquartered AND primarily listed abroad (an Indian bank with a US ADR is
        # still an Indian company on the Indian screen)
        foreign = [x for x in items if str(x.get("listing_country") or x.get("country") or "").upper() not in home
                   and str(x.get("country") or "").upper() not in home]
        return {"names": {_norm(x.get("name")) for x in foreign if x.get("name")}}
    return _cached(f"foreignidx:{region}", 86400, build)


def _foreign_names(region: str) -> set:
    return _foreign_index(region)["names"]


def _is_cross_listing(row: Dict[str, Any], region: str, fidx: Dict[str, Any]) -> bool:
    """A foreign company's line on this market: its name is a foreign primary-listed company,
    or it is a large company that barely trades here. Cross-listings (GE in Frankfurt or
    Mexico, still named "General Electric") turn over well under 0.0003% of their value a day;
    domestic large caps trade 0.01–0.5%. (Matching on market value alone was unreliable:
    hundreds of companies sit within 1% of each other around $100bn.)"""
    if row["symbol"] in DUAL_PRIMARY:
        return False
    if _norm(row.get("name")) in fidx["names"]:
        return True
    mc, px = row.get("market_cap"), row.get("price")
    vol = max(row.get("volume") or 0, row.get("avg_volume") or 0)      # before the open today's volume is 0
    if mc and px and (row.get("volume") is not None or row.get("avg_volume") is not None):
        usd = to_usd(mc, row.get("currency"))
        if usd and usd > 3e8:
            traded = px * vol * (0.01 if row.get("currency") in ("GBp", "GBX", "ZAc", "ILA") else 1.0)  # minor units
            if traded / mc < 3e-6:                       # ~100x below the thinnest domestic line seen (Roche bearer 3e-5)
                return True
    return False


def _primary_only(rows: List[Dict[str, Any]], region: str) -> List[Dict[str, Any]]:
    if region == "us":
        return rows
    import re
    fidx = _foreign_index(region)

    def rank(r):
        # One line per company: the NSE line in India, then a line with a market value that isn't a
        # preferred or second trading line (ENB-PY.TO, NOVNEE.SW), then the most traded.
        sym = str(r["symbol"])
        pref = bool(re.search(r"-P[A-Z0-9]*\.|-PR\.|EE\.SW$", sym))
        return (region == "in" and sym.endswith(".NS"), r.get("market_cap") is not None, not pref,
                (r.get("price") or 0) * (r.get("volume") or 0))
    best: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        n = _norm(r.get("name"))
        if n not in best or rank(r) > rank(best[n]):
            best[n] = r
    return [r for r in rows if r.get("name")                     # nameless lines are stray foreign listings (DG.SW)
            and best.get(_norm(r.get("name"))) is r
            and not _is_cross_listing(r, region, fidx)]          # a foreign company's cross-listing


def _rows(quotes: List[Dict]) -> List[Dict[str, Any]]:
    return [{"symbol": q.get("symbol"), "name": q.get("longName") or q.get("shortName"), "price": _f(q.get("regularMarketPrice")),
             "change_pct": (_f(q.get("regularMarketChangePercent")) or 0) / 100 if q.get("regularMarketChangePercent") is not None else None,
             "volume": _f(q.get("regularMarketVolume")), "market_cap": _f(q.get("marketCap")), "currency": q.get("currency"),
             "avg_volume": _f(q.get("averageDailyVolume3Month")) or _f(q.get("averageDailyVolume10Day")),
             "exchange": q.get("fullExchangeName") or q.get("exchange"), "pe": _f(q.get("trailingPE")),
             "dividend_yield": _sane_yield(_f(q.get("dividendYield")) / 100 if _f(q.get("dividendYield")) is not None else None,
                                           _f(q.get("trailingAnnualDividendYield"))),
             "sector": q.get("sector")}
            for q in quotes if q.get("symbol")]


def _yscreen(*a, **k):
    """yf.screen with retries: Yahoo intermittently answers 401 (stale session crumb) or 429."""
    import yfinance as yf
    last = None
    for attempt in range(3):
        try:
            return yf.screen(*a, **k)
        except Exception as e:
            last = e
            msg = str(e)
            if not any(x in msg for x in ("401", "429", "Unauthorized", "Crumb", "crumb", "Too Many")):
                raise
            if attempt == 1:
                try:                                   # force a fresh cookie/crumb on the second retry
                    from yfinance.data import YfData
                    d = YfData()
                    d._cookie, d._crumb = None, None
                except Exception:
                    pass
            time.sleep(1.0 + attempt)
    raise last


def _enrich(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add value traded (price × volume, in the major currency unit) and USD market cap."""
    for r in rows:
        minor = 0.01 if r.get("currency") in MINOR_UNITS else 1.0
        r["value_traded"] = r["price"] * r["volume"] * minor if r.get("price") and r.get("volume") else None
        r["market_cap_usd"] = to_usd(r.get("market_cap"), r.get("currency"))
        r["value_traded_usd"] = to_usd(r["value_traded"], MINOR_UNITS.get(r.get("currency"), r.get("currency")))
    return rows


def movers(region: str = "us", kind: str = "gainers", count: int = 25) -> Dict[str, Any]:
    """Top gainers, losers or most active in a region.

    Raises:
        NotFound: unknown region or kind.
    """
    if region not in REGIONS:
        raise NotFound(f"Unknown region '{region}'.")
    if kind not in ("gainers", "losers", "active"):
        raise NotFound("kind must be gainers, losers or active")

    def fetch():
        from yfinance import EquityQuery as Q
        try:
            if region == "us":
                res = _yscreen({"gainers": "day_gainers", "losers": "day_losers", "active": "most_actives"}[kind], count=max(count, 50))
            else:
                q = Q("and", [Q("is-in", ["exchange", *MAIN_EXCHANGES[region]]),          # exchange, not Yahoo's region tag
                              Q("gt", ["intradaymarketcap", 2e9 * usd_to_local(region)])])     # ≈ $2bn floor
                field = "dayvolume" if kind == "active" else "percentchange"      # re-ranked by value below
                res = _yscreen(q, sortField=field, sortAsc=(kind == "losers"), size=250)
        except Exception as e:
            raise Upstream(f"Screener unavailable: {e}")
        rows = _enrich([r for r in _primary_only(_rows(res.get("quotes") or []), region) if not _is_secondary_line(r["symbol"])])
        # Yahoo sorts on a lagging snapshot while the rows carry live values — re-rank on what's shown.
        # "Most active" ranks by value traded, as Bloomberg's MOST does: share counts favour
        # low-priced stocks and aren't comparable across markets.
        if kind == "active":
            rows.sort(key=lambda r: -(r["value_traded"] or 0))
        else:
            sign = 1 if kind == "gainers" else -1
            rows = sorted([r for r in rows if r["change_pct"] is not None and r["change_pct"] * sign > 0],
                          key=lambda r: -sign * r["change_pct"])
        return {"region": region, "region_name": REGIONS[region], "kind": kind, "rows": rows[:count],
                "source": "Yahoo Finance screener",
                "note": ("Most active = highest value traded today. " if kind == "active" else "")
                        + ("" if region == "us" else "Companies above ~$2bn market cap, primary listings on the main exchange.")}
    return _cached(f"movers:{region}:{kind}:{count}", 300, fetch)


# Main domestic exchange(s) per region (Yahoo exchange codes) — excludes OTC venues and
# international order books such as London's IOB (.IL) that list foreign shares.
MAIN_EXCHANGES = {"us": ["NMS", "NYQ", "ASE", "NCM", "NGM", "PCX", "BTS"], "ca": ["TOR", "VAN"], "gb": ["LSE"],
                  "de": ["GER"], "fr": ["PAR"], "nl": ["AMS"], "ch": ["EBS"], "se": ["STO"], "it": ["MIL"], "es": ["MCE"],
                  "jp": ["JPX"], "hk": ["HKG"], "cn": ["SHH", "SHZ"], "kr": ["KSC", "KOE"], "tw": ["TAI", "TWO"],
                  "in": ["NSI", "BSE"], "au": ["ASX"], "sg": ["SES"], "br": ["SAO"], "mx": ["MEX"], "za": ["JNB"], "sa": ["SAU"]}

REGION_CCY = {"us": "USD", "ca": "CAD", "gb": "GBP", "de": "EUR", "fr": "EUR", "nl": "EUR", "ch": "CHF", "se": "SEK",
              "it": "EUR", "es": "EUR", "jp": "JPY", "hk": "HKD", "cn": "CNY", "kr": "KRW", "tw": "TWD", "in": "INR",
              "au": "AUD", "sg": "SGD", "br": "BRL", "mx": "MXN", "za": "ZAR", "sa": "SAR"}


def usd_to_local(region: str) -> float:
    """Local currency per USD (Yahoo screens market cap in the listing's currency)."""
    ccy = "GBP" if region == "_gbp" else REGION_CCY.get(region, "USD")
    if ccy == "USD":
        return 1.0
    if region == "gb":            # London lines are quoted in pence and Yahoo screens UK market caps in GBp
        return usd_to_local("_gbp") * 100

    def fetch():
        import yfinance as yf
        pair = f"{ccy}=X" if ccy not in ("EUR", "GBP", "AUD") else f"{ccy}USD=X"
        c = yf.download(pair, period="5d", interval="1d", progress=False, auto_adjust=False)["Close"].dropna()
        x = float(c.iloc[-1].iloc[0] if hasattr(c.iloc[-1], "iloc") else c.iloc[-1])
        return fx_checked(ccy, 1 / x if ccy in ("EUR", "GBP", "AUD") else x)[0]
    try:
        return _cached(f"fx:{ccy}", 3600, fetch)
    except Exception as e:
        raise Upstream(f"FX rate for {ccy} unavailable: {e}")


# ── FX reference: ECB fixings as the second source ──────────────────────────────────────────────────────────────
# Yahoo's daily FX bars are unreliable around the day boundary (a stale bar on 26 Oct 2026 showed USD/BRL at 4.96
# when the market traded 5.40–5.59, so its "1-day change" read +7.5%). Every FX day-change in the platform is measured
# against the previous business day's ECB reference fixing (14:15 CET, ~30 currencies); live levels more than
# FX_MAX_DEVIATION from the latest fixing are replaced by it and flagged.
FX_MAX_DEVIATION = 0.10       # gross errors only (wrong units, dead feed): EM currencies can move 4–5% in a day


def ecb_fixings(days: int = 14) -> Dict[str, Dict[str, float]]:
    """ECB reference rates per USD for the last `days` calendar days: {YYYY-MM-DD: {ccy: units per USD}} (USD = 1)."""
    def fetch():
        import datetime as _dt
        import requests
        start = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        r = requests.get(f"https://api.frankfurter.dev/v1/{start}..", params={"base": "USD"}, timeout=10)
        r.raise_for_status()
        return {d: {**v, "USD": 1.0} for d, v in (r.json().get("rates") or {}).items()}
    try:
        return _cached(f"ecb_fix:{days}", 6 * 3600, fetch)
    except Exception as e:                                         # a second source must never break the first
        logger.warning("[fx] ECB fixings unavailable: %s", e)
        return {}


def fx_prev_fixing(ccy: str, before: str) -> Optional[Tuple[str, float]]:
    """(date, units of `ccy` per USD) of the latest ECB fixing strictly before `before` (YYYY-MM-DD), if any."""
    fx = ecb_fixings()
    for d in sorted(fx, reverse=True):
        if d < before and ccy in fx[d]:
            return d, fx[d][ccy]
    return None


def fx_checked(ccy: str, per_usd: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """A live rate (units of `ccy` per USD) checked against the latest ECB fixing: returned as is, or replaced by the
    fixing (with a note) when it is more than FX_MAX_DEVIATION away — a bad tick, not a market move."""
    fx = ecb_fixings()
    if not fx or ccy == "USD":
        return per_usd, None
    d = max(fx)
    ref = fx[d].get(ccy)
    if ref is None:
        return per_usd, None
    if per_usd is None or abs(per_usd / ref - 1) > FX_MAX_DEVIATION:
        note = (f"{ccy}: the live rate {per_usd:.4f} is {per_usd / ref - 1:+.1%} from the ECB fixing of {d} ({ref:.4f}) — the fixing is used"
                if per_usd else f"{ccy}: no live rate — the ECB fixing of {d} is used")
        logger.warning("[fx] %s", note)
        return ref, note
    return per_usd, None


def fx_last_prev(symbol: str, closes) -> Optional[Tuple[float, float, str]]:
    """(last, previous close, basis) for a Yahoo FX symbol — 'JPY=X' (JPY per USD), 'EURUSD=X' (USD per EUR) or a cross
    'EURJPY=X' — from its daily closes: the last close validated against the ECB fixing, the previous close taken from
    the previous business day's ECB fixing. None when the symbol isn't FX or the ECB has neither currency."""
    import re
    m = re.fullmatch(r"([A-Z]{3})([A-Z]{3})?=X", symbol)
    if not m or len(closes) < 1:
        return None
    base, quote_ = (("USD", m.group(1)) if not m.group(2) else (m.group(1), m.group(2)))
    last_date = closes.index[-1].strftime("%Y-%m-%d")
    fb, fq = fx_prev_fixing(base, last_date), fx_prev_fixing(quote_, last_date)
    if not fb or not fq:
        return None
    prev = fq[1] / fb[1]                                            # units of quote per base at the fixing
    last = float(closes.iloc[-1])
    # validate the live level through the non-USD leg(s)
    if base == "USD":
        last = fx_checked(quote_, last)[0] or last
    elif quote_ == "USD":
        chk = fx_checked(base, 1 / last if last else None)[0]
        last = 1 / chk if chk else last
    return last, prev, f"previous close: ECB fixing {fq[0]}"


# Exchanges that quote in minor units: London pence, Johannesburg cents, Tel Aviv agorot
MINOR_UNITS = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ZAC": "ZAR", "ILA": "ILS"}


def to_usd(amount: Optional[float], ccy: Optional[str]) -> Optional[float]:
    """Convert an amount in `ccy` to USD. Yahoo's `marketCap` for lines quoted in minor units
    (GBp, ZAc, ILA) is already in the major unit, so those amounts are treated as GBP/ZAR/ILS."""
    if amount is None or not ccy:
        return None
    major = MINOR_UNITS.get(ccy, ccy.upper())
    if major == "USD":
        return amount

    def fetch():
        import yfinance as yf
        c = yf.download(f"{major}USD=X", period="5d", interval="1d", progress=False, auto_adjust=False)["Close"].dropna()
        usd_per = float(c.iloc[-1].iloc[0] if hasattr(c.iloc[-1], "iloc") else c.iloc[-1])
        per_usd, _ = fx_checked(major, 1 / usd_per if usd_per else None)        # validated against the ECB fixing
        return 1 / per_usd if per_usd else usd_per
    try:
        return amount * _cached(f"usdper:{major}", 3600, fetch)
    except Exception:
        return None


# Yahoo symbol suffixes of each market's main exchange(s)
REGION_SUFFIX = {"us": ("",), "ca": ("TO", "V"), "gb": ("L",), "de": ("DE",), "fr": ("PA",), "nl": ("AS",), "ch": ("SW",),
                 "se": ("ST",), "it": ("MI",), "es": ("MC",), "jp": ("T",), "hk": ("HK",), "cn": ("SS", "SZ"), "kr": ("KS", "KQ"),
                 "tw": ("TW", "TWO"), "in": ("NS", "BO"), "au": ("AX",), "sg": ("SI",), "br": ("SA",), "mx": ("MX",),
                 "za": ("JO",), "sa": ("SR",)}


def _primary_multi(rows: List[Dict[str, Any]], regs: List[str]) -> List[Dict[str, Any]]:
    """Primary listings only, for one market or several (e.g. the eurozone): each market's lines
    are filtered against that market's own home rule, so Nvidia in Milan or Frankfurt drops out."""
    if len(regs) == 1:
        return _primary_only(rows, regs[0])
    out: List[Dict[str, Any]] = []
    for r in regs:
        sfx = REGION_SUFFIX.get(r, ())
        mine = [x for x in rows if str(x["symbol"]).partition(".")[2] in sfx]
        out += _primary_only(mine, r)
    return out


def _is_secondary_line(symbol: str) -> bool:
    """Lines that list foreign shares: LSE international codes like 0YG8.L, and Brazilian
    depositary receipts (BDRs, codes ending 31–35 such as AAPL34.SA)."""
    import re
    base, _, suffix = symbol.partition(".")
    if suffix == "L" and len(base) == 4 and base[0] == "0":
        return True
    return suffix == "SA" and bool(re.fullmatch(r"[A-Z0-9]{4}3[1-5]", base))


SCREEN_FIELDS = {"market_cap_min": ("gt", "intradaymarketcap"), "market_cap_max": ("lt", "intradaymarketcap"),
                 "pe_max": ("lt", "peratio.lasttwelvemonths"), "pe_min": ("gt", "peratio.lasttwelvemonths"),
                 "dividend_yield_min": ("gt", "forward_dividend_yield"), "change_pct_min": ("gt", "percentchange"),
                 "change_pct_max": ("lt", "percentchange"), "price_min": ("gt", "intradayprice")}
SORTS = {"market_cap": "intradaymarketcap", "change": "percentchange", "volume": "dayvolume", "pe": "peratio.lasttwelvemonths",
         "dividend_yield": "forward_dividend_yield"}
SECTORS = ["Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy",
           "Financial Services", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]


def _screen_supplement(rows: List[Dict[str, Any]], region: str, sector: Optional[str], filters: Dict[str, Any],
                       fx: float) -> List[Dict[str, Any]]:
    """Large companies Yahoo's screener leaves out of a market (Allianz in Germany, Reliance and TCS
    in India, NAB and ANZ in Australia): the global universe's home listings for the market, quoted
    live and put through the same filters."""
    try:
        from api import global_universe as gu
        u = gu.load(rebuild_if_stale=False)
        items = u if isinstance(u, list) else (u.get("stocks") or [])
    except Exception:
        return []
    sfx = REGION_SUFFIX.get(region, ())
    have = {r["symbol"] for r in rows} | {_norm(r.get("name")) for r in rows}
    floor = min((to_usd(r["market_cap"], r.get("currency")) or 0 for r in rows if r.get("market_cap")), default=0)
    cands = [i for i in items if str(i.get("symbol", "")).partition(".")[2] in sfx and i["symbol"] not in have
             and _norm(i.get("name")) not in have and (i.get("mcap_usd") or 0) > max(floor, 2e9)]
    cands = sorted(cands, key=lambda i: -(i.get("mcap_usd") or 0))[:12]
    if not cands:
        return []

    def one(sym):
        try:
            i = _info(sym)
        except Exception:
            return None
        if not i.get("regularMarketPrice") or not i.get("marketCap"):
            return None
        q = {**i, "symbol": sym}
        q["dividendYield"] = i.get("dividendYield")
        return _rows([q])[0] | {"sector": i.get("sector")}
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(6) as ex:
        got = [r for r in ex.map(one, [c["symbol"] for c in cands]) if r]
    f = {k: v for k, v in filters.items() if v is not None}

    def ok(r):
        mc = r.get("market_cap") or 0
        pe, dy, ch, px = r.get("pe"), r.get("dividend_yield"), r.get("change_pct"), r.get("price")
        return ((not sector or r.get("sector") == sector)
                and ("market_cap_min" not in f or mc > f["market_cap_min"] * fx)
                and ("market_cap_max" not in f or mc < f["market_cap_max"] * fx)
                and ("pe_max" not in f or (pe is not None and pe < f["pe_max"]))
                and ("pe_min" not in f or (pe is not None and pe > f["pe_min"]))
                and ("dividend_yield_min" not in f or (dy is not None and dy * 100 > f["dividend_yield_min"]))
                and ("change_pct_min" not in f or (ch is not None and ch * 100 > f["change_pct_min"]))
                and ("change_pct_max" not in f or (ch is not None and ch * 100 < f["change_pct_max"]))
                and ("price_min" not in f or (px is not None and px > f["price_min"])))
    return [r for r in got if ok(r)]


def _us_domestic(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """US screens: drop ADRs and other foreign companies' US lines (TSM, SAP, Toyota's TM), as the
    other markets drop foreign cross-listings — they belong to their home market's screen."""
    fidx = _foreign_index("us")
    return [r for r in rows if _norm(r.get("name")) not in fidx["names"]]


def screen(regions: List[str], sector: Optional[str] = None, sort: str = "market_cap", ascending: bool = False,
           size: int = 50, offset: int = 0, include_adrs: bool = False, **filters) -> Dict[str, Any]:
    """Yahoo's global equity screener. Filters use percent for dividend yield and change."""
    from yfinance import EquityQuery as Q
    regs = [r for r in regions if r in REGIONS] or ["us"]
    size = max(1, min(size, 250))
    # The exchange defines the market. Yahoo's per-stock "region" tag is unreliable (Allianz is
    # tagged US, which silently dropped it from Germany), so it's used for the US only; foreign
    # lines on a market's exchange are removed afterwards by _primary_only.
    exch = Q("is-in", ["exchange", *[e for r in regs for e in MAIN_EXCHANGES[r]]])
    parts = [Q("eq", ["region", "us"]), exch] if regs == ["us"] else [exch]
    if sector:
        if sector not in SECTORS:
            raise NotFound(f"Unknown sector '{sector}'.")
        parts.append(Q("eq", ["sector", sector]))
    fx = usd_to_local(regs[0]) if len(regs) == 1 else None
    if len({REGION_CCY[r] for r in regs}) > 1 and any(filters.get(k) is not None for k in ("market_cap_min", "market_cap_max")):
        raise NotFound("Market-cap filters need regions that share a currency (Yahoo screens in local currency).")
    if fx is None and regs:
        fx = usd_to_local(regs[0])
    for k, v in filters.items():
        if v is None or k not in SCREEN_FIELDS:
            continue
        op, field = SCREEN_FIELDS[k]
        val = float(v) * fx if k.startswith("market_cap") else float(v)      # market caps are given in USD
        parts.append(Q(op, [field, val]))
    query = Q("and", parts) if len(parts) > 1 else parts[0]
    key = f"screen2:{regs}:{sector}:{sort}:{ascending}:{size}:{offset}:{include_adrs}:{sorted((k, v) for k, v in filters.items() if v is not None)}"

    def fetch():
        # Over-fetch (up to 3 pages) so dropping cross-listings and foreign depositary receipts —
        # which crowd the top of Brazil's and Mexico's lists — still leaves a full page.
        rows: List[Dict[str, Any]] = []
        total, off = None, offset
        pages = 6 if len(regs) > 1 else 3      # filtering (cross-listings, ADRs) can need more raw rows to fill a page
        for _ in range(pages):
            try:
                res = _yscreen(query, sortField=SORTS.get(sort, "intradaymarketcap"), sortAsc=ascending,
                                size=250, offset=off)
            except Exception as e:
                if rows:
                    break
                raise Upstream(f"Screener unavailable: {e}")
            total = res.get("total")
            page = _rows(res.get("quotes") or [])
            for k, r in enumerate(page):
                r["_raw"] = off + k                      # position in Yahoo's list, to resume page 2 exactly
            rows += page
            kept = _primary_multi(rows, regs)
            if "us" in regs and not include_adrs:
                kept = _us_domestic(kept)
            kept = [r for r in kept if not _is_secondary_line(r["symbol"]) and not (sort == "market_cap" and not r.get("market_cap"))]
            off += len(page)
            if len(kept) >= size or len(page) < 250 or (total is not None and off >= total):
                break
        rows = _primary_multi(rows, regs)
        if "us" in regs and not include_adrs:
            rows = _us_domestic(rows)
        rows = [r for r in rows if not _is_secondary_line(r["symbol"])
                and not (sort == "market_cap" and not r.get("market_cap"))]     # drop warrants/notes with no market value
        if len(regs) == 1 and offset == 0:
            rows = rows + _screen_supplement(rows, regs[0], sector, filters, fx)
        col = {"change": "change_pct"}.get(sort, sort)
        if col in ("market_cap", "change_pct", "volume", "pe", "dividend_yield"):    # Yahoo ranks on a lagging snapshot
            has = [r for r in rows if r.get(col) is not None]
            rows = sorted(has, key=lambda r: r[col], reverse=not ascending) + [r for r in rows if r.get(col) is None]
        more = len(rows) > size or (total is not None and off < total)
        rows = rows[:size]
        # page 2 resumes just after the last row shown here (not offset + size: filtering consumed more)
        raw = [r["_raw"] for r in rows if "_raw" in r]
        nxt = (max(raw) + 1) if raw else off
        for r in rows:
            r.pop("_raw", None)
        rows = _enrich(rows)
        return {"total": total, "rows": rows, "offset": offset, "next_offset": nxt if more else None,
                "listed_total": total, "source": "Yahoo Finance global screener"}
    return _cached(key, 300, fetch)
