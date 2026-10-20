"""
Real, dated inputs for the dashboard's macro signals.

Loads ~1y of daily history from Yahoo (S&P 500, VIX, DXY) and FRED (10Y, 2Y and 3M
Treasury yields, effective Fed funds, real-time Sahm rule) so every signal, regime and
recession figure — including its history sparkline — is computed from observed data at
the date it describes. Nothing here substitutes a default value: a series that can't be
fetched is simply empty, and callers decide what is unavailable.

The 2Y and 3M yields come from FRED because Yahoo has no 2-year index (^FVX is the
5-year) and the Estrella-Mishkin probit is estimated on the 3M bill, not Fed funds.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

YAHOO_TICKERS = {"spx": "^GSPC", "vix": "^VIX", "dxy": "DX-Y.NYB"}
FRED_SERIES = {
    "dgs10": "DGS10",
    "dgs2": "DGS2",
    "dgs3mo": "DGS3MO",
    "dff": "DFF",
    "sahm": "SAHMREALTIME",
    "breakeven": "T10YIE",   # 10Y breakeven inflation (market-implied), daily
}
# Max age (days) of an observation used "as of" a date: daily series tolerate
# weekends/holidays, the monthly Sahm series tolerates its publication lag.
_MAX_AGE_DAYS = {"sahm": 75, "cpi": 75}
_DEFAULT_MAX_AGE_DAYS = 7

_TTL_SECONDS = 900
_FETCH_TIMEOUT = 15.0


@dataclass
class DatedSeries:
    """Observations sorted by ISO date string."""
    name: str
    dates: List[str] = field(default_factory=list)
    values: List[float] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, name: str, mapping: Dict[str, float]) -> "DatedSeries":
        items = sorted((d, v) for d, v in mapping.items() if v is not None and v == v)
        return cls(name, [d for d, _ in items], [float(v) for _, v in items])

    def __bool__(self) -> bool:
        return bool(self.values)

    @property
    def latest(self) -> Optional[float]:
        return self.values[-1] if self.values else None

    @property
    def latest_date(self) -> Optional[str]:
        return self.dates[-1] if self.dates else None

    def last_common(self, other: "DatedSeries") -> Optional[tuple]:
        """(date, self_value, other_value) on the latest date BOTH series have — so a
        spread is never one series' today minus the other's yesterday."""
        common = set(self.dates) & set(other.dates)
        if not common:
            return None
        d = max(common)
        return d, self.values[self.dates.index(d)], other.values[other.dates.index(d)]

    def asof(self, d: str) -> Optional[float]:
        """Last observation on or before ISO date `d`, if recent enough."""
        i = bisect_right(self.dates, d) - 1
        if i < 0:
            return None
        max_age = _MAX_AGE_DAYS.get(self.name, _DEFAULT_MAX_AGE_DAYS)
        age = (date.fromisoformat(d[:10]) - date.fromisoformat(self.dates[i][:10])).days
        return self.values[i] if age <= max_age else None


@dataclass
class MacroInputs:
    series: Dict[str, DatedSeries]

    def __getitem__(self, key: str) -> DatedSeries:
        return self.series.get(key) or DatedSeries(key)

    def missing(self) -> List[str]:
        return [k for k in (*YAHOO_TICKERS, *FRED_SERIES) if not self[k]]


# On-disk copy of every successful fetch, so a restart (or a FRED rate-limit / outage)
# serves the last real observations instead of nothing, and fresh copies aren't
# re-downloaded on every process start.
_DISK_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "fred_cache"


def _disk_save(name: str, payload: dict) -> None:
    try:
        _DISK_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _DISK_DIR / f"{name}.json.tmp"
        tmp.write_text(json.dumps({"saved_at": time.time(), **payload}))
        tmp.replace(_DISK_DIR / f"{name}.json")
    except Exception as e:
        logger.debug("[macro_inputs] disk save %s failed: %s", name, e)


def _disk_load(name: str, max_age: Optional[float] = None) -> Optional[dict]:
    """Stored payload, or None if missing / older than max_age seconds."""
    try:
        data = json.loads((_DISK_DIR / f"{name}.json").read_text())
    except Exception:
        return None
    if max_age is not None and time.time() - float(data.get("saved_at", 0)) > max_age:
        return None
    return data


_CACHE: Dict[str, object] = {"ts": 0.0, "data": None}
# Last successfully fetched copy of each series, kept so one failed refresh serves
# real (if older) observations instead of nothing.
_LAST_GOOD: Dict[str, DatedSeries] = {}


async def _fetch_yahoo(key: str, ticker: str) -> DatedSeries:
    from api.handlers.market_handler import _fetch_dated_closes_literal
    try:
        dated = await _fetch_dated_closes_literal(ticker)
    except Exception as e:
        logger.warning("[macro_inputs] %s history failed: %s", ticker, e)
        dated = {}
    return DatedSeries.from_mapping(key, dated)


def _fred():
    from api.config import FRED_API_KEY
    from api.providers.fred_provider import FREDProvider
    return FREDProvider(api_key=FRED_API_KEY or None)


def _fetch_fred_sync(key: str, series_id: str) -> DatedSeries:
    disk_name = f"daily_{series_id}"
    fresh = _disk_load(disk_name, max_age=_TTL_SECONDS)
    if fresh:
        return DatedSeries(key, fresh["dates"], fresh["values"])
    start = (date.today() - timedelta(days=400 if key != "sahm" else 800)).isoformat()
    res = _fred().fetch_series(series_id, start_date=start)
    if not res.success or not res.data:
        logger.warning("[macro_inputs] FRED %s failed: %s", series_id, res.error)
        stale = _disk_load(disk_name)
        return DatedSeries(key, stale["dates"], stale["values"]) if stale else DatedSeries(key)
    out = DatedSeries.from_mapping(key, {o.date: o.value for o in res.data})
    _disk_save(disk_name, {"dates": out.dates, "values": out.values})
    return out


async def load_macro_inputs() -> MacroInputs:
    """Fetch (or return cached) dated history for every signal input."""
    now = time.time()
    cached = _CACHE.get("data")
    if cached is not None and now - float(_CACHE["ts"]) < _TTL_SECONDS:
        return cached  # type: ignore[return-value]

    tasks = [_fetch_yahoo(k, t) for k, t in YAHOO_TICKERS.items()]
    tasks += [asyncio.to_thread(_fetch_fred_sync, k, sid) for k, sid in FRED_SERIES.items()]
    keys = [*YAHOO_TICKERS, *FRED_SERIES]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=_FETCH_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("[macro_inputs] fetch timed out after %ss", _FETCH_TIMEOUT)
        results = [DatedSeries(k) for k in keys]

    series: Dict[str, DatedSeries] = {}
    for key, res in zip(keys, results):
        if isinstance(res, DatedSeries) and res:
            _LAST_GOOD[key] = res
            series[key] = res
        else:
            if isinstance(res, Exception):
                logger.warning("[macro_inputs] %s failed: %s", key, res)
            series[key] = _LAST_GOOD.get(key, DatedSeries(key))

    data = MacroInputs(series)
    # A partial fetch is only cached briefly so the missing series are retried soon.
    _CACHE.update(ts=now if not data.missing() else now - _TTL_SECONDS + 60, data=data)
    return data


# ── Monthly macro history (FRED) ─────────────────────────────────────────────
# A contiguous monthly panel for models that need long history (quadrant surprises,
# HMM regimes). Replaces the hand-maintained data/us_economic_data.csv, which has an
# 18-month gap and forward-filled daily rows that those models treated as monthly data.
MONTHLY_SERIES = {
    "indpro": "INDPRO",     # industrial production index
    "payems": "PAYEMS",     # nonfarm payrolls
    "cpi": "CPIAUCSL",      # headline CPI index
    "gs10": "GS10",         # 10Y Treasury, monthly avg
    "gs2": "GS2",           # 2Y Treasury, monthly avg
    "baa10y": "BAA10YM",    # Moody's Baa minus 10Y (credit spread, full history)
}
_MONTHLY_TTL_SECONDS = 12 * 3600
_MONTHLY_CACHE: Dict[str, object] = {"ts": 0.0, "df": None}


def load_monthly_macro(start: str = "1985-01-01"):
    """Monthly macro panel from FRED, indexed by month start.

    Columns: growth_yoy (INDPRO YoY %), payrolls_yoy, cpi_yoy, curve (GS10-GS2, pp),
    credit (Baa-10Y, pp). The index is every calendar month up to the latest month where
    growth and CPI are both published; unpublished months are NaN. Returns None if FRED is unreachable and nothing was fetched before.
    """
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor

    now = time.time()
    if _MONTHLY_CACHE["df"] is not None and now - float(_MONTHLY_CACHE["ts"]) < _MONTHLY_TTL_SECONDS:
        return _MONTHLY_CACHE["df"]

    def _from_disk(max_age):
        d = _disk_load("monthly_panel", max_age=max_age)
        if not d:
            return None
        df = pd.DataFrame(d["data"], index=pd.to_datetime(d["index"]))
        return df.asfreq("MS")

    fresh = _from_disk(_MONTHLY_TTL_SECONDS)
    if fresh is not None:
        _MONTHLY_CACHE.update(ts=now, df=fresh)
        return fresh

    fred = _fred()

    def _one(sid):
        res = fred.fetch_series(sid, start_date=start)
        if not res.success or not res.data:
            logger.warning("[macro_inputs] FRED monthly %s failed: %s", sid, res.error)
            return None
        s = pd.Series({pd.Timestamp(o.date): o.value for o in res.data}).sort_index()
        return s.resample("MS").mean()

    with ThreadPoolExecutor(max_workers=len(MONTHLY_SERIES)) as pool:
        raw = dict(zip(MONTHLY_SERIES, pool.map(_one, MONTHLY_SERIES.values())))

    if raw["indpro"] is None or raw["cpi"] is None:
        # last good panel in memory, else on disk (any age), else None
        return _MONTHLY_CACHE["df"] if _MONTHLY_CACHE["df"] is not None else _from_disk(None)

    df = pd.DataFrame({
        "growth_yoy": raw["indpro"].pct_change(12, fill_method=None) * 100,
        "cpi_yoy": raw["cpi"].pct_change(12, fill_method=None) * 100,
    })
    if raw["payems"] is not None:
        df["payrolls_yoy"] = raw["payems"].pct_change(12, fill_method=None) * 100
    if raw["gs10"] is not None and raw["gs2"] is not None:
        df["curve"] = raw["gs10"] - raw["gs2"]
    if raw["baa10y"] is not None:
        df["credit"] = raw["baa10y"]

    # Trim to months where both core series exist, but keep the calendar complete:
    # unpublished months (e.g. Oct-2025 CPI, lost to the shutdown) stay as NaN rows
    # so windows count real months instead of silently skipping one.
    both = df.dropna(subset=["growth_yoy", "cpi_yoy"]).index
    df = df.loc[both[0]:both[-1]]
    df = df.reindex(pd.date_range(both[0], both[-1], freq="MS"))
    _MONTHLY_CACHE.update(ts=now, df=df)
    _disk_save("monthly_panel", {"index": [d.strftime("%Y-%m-%d") for d in df.index],
                                 "data": {c: [None if v != v else float(v) for v in df[c]] for c in df.columns}})
    return df


def cpi_release_series(panel) -> DatedSeries:
    """CPI YoY as a DatedSeries keyed by approximate PUBLICATION date (month end + ~14
    days, i.e. mid-following-month), so an as-of lookup only sees prints that had been
    released by then — no look-ahead into a month's CPI before BLS publishes it."""
    import pandas as pd
    if panel is None or "cpi_yoy" not in panel:
        return DatedSeries("cpi")
    s = panel["cpi_yoy"].dropna()
    released = {(d + pd.offsets.MonthEnd(1) + pd.Timedelta(days=14)).strftime("%Y-%m-%d"): float(v)
                for d, v in s.items()}
    return DatedSeries.from_mapping("cpi", released)


# ── Supplementary FRED series (curve tenors, foreign yields, debt ratios, ...) ──
# Cached per series (in memory and on disk, like the core inputs) so the dashboard
# panels that need slow-moving monthly/quarterly series don't refetch them on every
# build and a restart or FRED outage serves the last real observations.
_FRED_SERIES_CACHE: Dict[str, tuple] = {}
_FRED_SERIES_TTL = 3600
# FRED allows ~120 requests/min per key and answers bursts with 429, so cap concurrency
# and retry a rate-limited request with backoff.
_FRED_CONCURRENCY = 4


def _fetch_fred_history_sync(series_id: str, days: int) -> DatedSeries:
    disk_name = f"series_{series_id}_{days}d"
    fresh = _disk_load(disk_name, max_age=_FRED_SERIES_TTL)
    if fresh:
        return DatedSeries(series_id, fresh["dates"], fresh["values"])
    start = (date.today() - timedelta(days=days)).isoformat()
    res = _fred().fetch_series(series_id, start_date=start)
    for pause in (2.0, 5.0):           # back off on FRED 429s (shared per-key limit)
        if res.success or "rate limit" not in str(res.error).lower():
            break
        time.sleep(pause)
        res = _fred().fetch_series(series_id, start_date=start)
    if not res.success or not res.data:
        logger.warning("[macro_inputs] FRED %s failed: %s", series_id, res.error)
        stale = _disk_load(disk_name)
        return DatedSeries(series_id, stale["dates"], stale["values"]) if stale else DatedSeries(series_id)
    out = DatedSeries.from_mapping(series_id, {o.date: o.value for o in res.data})
    _disk_save(disk_name, {"dates": out.dates, "values": out.values})
    return out


async def load_fred_series(series_ids: List[str], days: int = 1100,
                           timeout: float = _FETCH_TIMEOUT) -> Dict[str, DatedSeries]:
    """{series_id: DatedSeries} for arbitrary FRED ids. A series that can't be fetched
    is empty (or its last good copy) — never a substituted value."""
    now = time.time()
    out: Dict[str, DatedSeries] = {}
    todo = []
    for sid in dict.fromkeys(series_ids):
        hit = _FRED_SERIES_CACHE.get(sid)
        if hit and now - hit[0] < _FRED_SERIES_TTL:
            out[sid] = hit[1]
        else:
            todo.append(sid)
    if todo:
        sem = asyncio.Semaphore(_FRED_CONCURRENCY)

        async def _one(sid: str) -> DatedSeries:
            async with sem:
                res = await asyncio.to_thread(_fetch_fred_history_sync, sid, days)
            if res:                        # cached even if it lands after the batch deadline
                _FRED_SERIES_CACHE[sid] = (time.time(), res)
            return res

        tasks = {sid: asyncio.ensure_future(_one(sid)) for sid in todo}
        _done, pending = await asyncio.wait(tasks.values(), timeout=timeout)
        if pending:
            # Keep what finished; the rest keep running in the background (and fill the cache
            # for the next request) while this one falls back to the last good copy.
            logger.warning("[macro_inputs] FRED batch: %d of %d series not back within %ss — using last good copies",
                           len(pending), len(todo), timeout)
            _PENDING_FRED.update(pending)
            for t in pending:
                t.add_done_callback(_PENDING_FRED.discard)
        for sid, t in tasks.items():
            res = t.result() if t.done() and not t.cancelled() and t.exception() is None else None
            if isinstance(res, DatedSeries) and res:
                out[sid] = res
                continue
            stale = _FRED_SERIES_CACHE.get(sid)
            if stale:
                out[sid] = stale[1]
                continue
            disk = _disk_load(f"series_{sid}_{days}d")          # any age: real, if older, data
            out[sid] = DatedSeries(sid, disk["dates"], disk["values"]) if disk else DatedSeries(sid)
    return out


_PENDING_FRED: set = set()     # strong references to fetches still running past a deadline
