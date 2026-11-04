"""
Massive (formerly Polygon.io) — a local store of daily bars for every US-listed stock.

The free plan allows 5 requests a minute and two years of end-of-day history, but one request — grouped daily — returns
every US stock's bar for a date (~12,500 tickers). So: one file per trading day in data/processed/massive/ (gitignored),
backfilled once in the background (~520 requests ≈ 1¾ hours, resumable) and topped up with one request a day. Screens
that needed 300–500 Yahoo requests (breadth, heat-map history) read the store instead.

Splits: a stored day keeps the prices of that day, so a later split would look like a crash. `panel()` applies the split
history (Massive /v3/reference/splits) on read: prices before a split's execution date are divided by split_to/split_from.

Key: MASSIVE_API_KEY in .env (never logged). Without a key every function reports `available: False` and callers fall
back to their previous source.
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)
BASE = "https://api.massive.com"
STORE = Path(__file__).resolve().parents[2] / "data" / "processed" / "massive" / "grouped"
SPLITS_FILE = STORE.parent / "splits.json"
MIN_INTERVAL = 12.5                    # 5 requests a minute on the free plan, with a margin
HISTORY_DAYS = 730                     # the free plan's history depth (calendar days)
_lock = threading.Lock()
_last = {"t": 0.0}
_backfill = {"running": False, "done": 0, "todo": 0, "error": None, "thread": None}


def api_key() -> Optional[str]:
    k = os.getenv("MASSIVE_API_KEY")
    if not k:
        try:
            from dotenv import dotenv_values
            k = dotenv_values(Path(__file__).resolve().parents[2] / ".env").get("MASSIVE_API_KEY")
        except Exception:
            k = None
    return k or None


def available() -> bool:
    return api_key() is not None


class MassiveError(RuntimeError):
    """The request failed (bad key, rate limit not cleared, network)."""


class DayNotReady(MassiveError):
    """The day has not closed yet on the free plan — fetch it on the next run."""


def _get(path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict[str, Any]:
    """One rate-limited request (≥ MIN_INTERVAL apart across threads); 429s back off and retry."""
    key = api_key()
    if not key:
        raise MassiveError("MASSIVE_API_KEY is not set.")
    for attempt in range(retries):
        with _lock:
            wait = _last["t"] + MIN_INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            _last["t"] = time.time()
        r = requests.get(BASE + path, params={**(params or {}), "apiKey": key}, timeout=60)
        if r.status_code == 429:
            time.sleep(60 * (attempt + 1))
            continue
        if r.status_code in (401, 403):
            j = r.json() if r.text else {}
            msg = str(j.get("message") or j.get("error") or "")
            if "before end of day" in msg:            # the free plan releases a day only after it closes
                raise DayNotReady(msg[:120])
            raise MassiveError(f"Massive refused the key or the plan ({r.status_code}): {msg[:120]}")
        if r.status_code != 200:
            raise MassiveError(f"Massive HTTP {r.status_code}")
        return r.json()
    raise MassiveError("Massive kept rate-limiting the request.")


# ── the store ────────────────────────────────────────────────────────────────
def _file(d: date) -> Path:
    return STORE / f"{d.isoformat()}.csv.gz"


def stored_days() -> List[date]:
    """Trading days in the store (holidays have a separate .holiday marker)."""
    if not STORE.exists():
        return []
    out = []
    for p in STORE.glob("*.csv.gz"):
        try:
            out.append(date.fromisoformat(p.name[:10]))
        except ValueError:
            pass
    return sorted(out)


def fetch_day(d: date) -> Optional[pd.DataFrame]:
    """Grouped daily bars for every US stock on `d` (unadjusted, as traded that day), stored on disk. A past day is
    fetched once; None for a market holiday."""
    f = _file(d)
    if f.exists():
        return read_day(d)
    if f.with_name(f"{d.isoformat()}.holiday").exists():
        return None
    j = _get(f"/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}", {"adjusted": "false"})
    res = j.get("results") or []
    STORE.mkdir(parents=True, exist_ok=True)
    today_et = datetime.now(timezone(timedelta(hours=-5))).date()
    if not res:
        if d < today_et:                       # a holiday: remember it so it is not requested again
            f.with_name(f"{d.isoformat()}.holiday").touch()
        return None
    df = pd.DataFrame(res).rename(columns={"T": "ticker"})[["ticker", "o", "h", "l", "c", "v"]]
    if d < today_et:                           # today's bar can still change until the close is final
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        f.write_bytes(gzip.compress(buf.getvalue()))
    return df


def read_day(d: date) -> Optional[pd.DataFrame]:
    f = _file(d)
    if not f.exists():
        return None
    return pd.read_csv(io.BytesIO(gzip.decompress(f.read_bytes())))


def _weekdays_back(n_days: int, until: Optional[date] = None) -> List[date]:
    end = until or (datetime.now(timezone.utc) - timedelta(hours=22)).date()      # yesterday's close is final by now
    return [end - timedelta(days=k) for k in range(n_days) if (end - timedelta(days=k)).weekday() < 5]


def missing_days(history_days: int = HISTORY_DAYS) -> List[date]:
    """Weekdays within the free plan's history with no file yet (newest first)."""
    have = {p.name[:10] for p in STORE.glob("*.csv.gz")} | {p.name[:10] for p in STORE.glob("*.holiday")} if STORE.exists() else set()
    return [d for d in _weekdays_back(history_days) if d.isoformat() not in have]


def backfill(history_days: int = HISTORY_DAYS) -> None:
    """Fetch every missing day, newest first (screens become useful early), at the plan's rate. Resumable."""
    todo = missing_days(history_days)
    _backfill.update(running=True, done=0, todo=len(todo), error=None)
    try:
        for d in todo:
            try:
                fetch_day(d)
            except DayNotReady:
                _backfill["done"] += 1
                continue                                   # not an error: the next run picks it up
            except MassiveError as e:
                _backfill["error"] = str(e)[:200]
                if "refused" in str(e):
                    break
            _backfill["done"] += 1
        refresh_splits()
    finally:
        _backfill["running"] = False


def start_backfill() -> bool:
    """Start the backfill in a background thread (no-op without a key or when one is running)."""
    if not available() or _backfill["running"]:
        return False
    t = threading.Thread(target=backfill, name="massive-backfill", daemon=True)
    _backfill["thread"] = t
    t.start()
    return True


def status() -> Dict[str, Any]:
    days = stored_days()
    return {"available": available(), "stored_days": len(days), "first": days[0].isoformat() if days else None,
            "last": days[-1].isoformat() if days else None, "missing": len(missing_days()) if available() else None,
            "backfill": {k: v for k, v in _backfill.items() if k != "thread"}}


# ── splits ───────────────────────────────────────────────────────────────────
def refresh_splits(since: Optional[date] = None) -> List[Dict[str, Any]]:
    """Split history since the start of the store (cached; refreshed at most daily)."""
    try:
        if SPLITS_FILE.exists() and time.time() - SPLITS_FILE.stat().st_mtime < 86400:
            return json.loads(SPLITS_FILE.read_text())
    except Exception:
        pass
    start = since or (date.today() - timedelta(days=HISTORY_DAYS + 30))
    out: List[Dict[str, Any]] = []
    path, params = "/v3/reference/splits", {"execution_date.gte": start.isoformat(), "limit": 1000}
    for _ in range(20):                                    # pages of 1,000
        j = _get(path, params)
        out += [{"ticker": s["ticker"], "date": s["execution_date"], "ratio": s["split_to"] / s["split_from"]}
                for s in j.get("results") or [] if s.get("split_from") and s.get("split_to")]
        nxt = j.get("next_url")
        if not nxt:
            break
        path, params = nxt.replace(BASE, "").split("?")[0], dict(p.split("=", 1) for p in nxt.split("?", 1)[1].split("&") if "=" in p and not p.startswith("apiKey"))
    STORE.parent.mkdir(parents=True, exist_ok=True)
    SPLITS_FILE.write_text(json.dumps(out))
    return out


def _splits() -> List[Dict[str, Any]]:
    try:
        return json.loads(SPLITS_FILE.read_text()) if SPLITS_FILE.exists() else []
    except Exception:
        return []


def panel(tickers: List[str], days: int = 520, field: str = "c") -> pd.DataFrame:
    """Daily `field` (o, h, l, c, v) for `tickers` over the last `days` stored trading days — dates × tickers, split-
    adjusted to today's share basis. Yahoo-style tickers (BRK-B) are mapped to Massive's (BRK.B) and back."""
    want = {t: t.replace("-", ".") for t in tickers}
    rev = {v: k for k, v in want.items()}
    frames = {}
    for d in stored_days()[-days:]:
        df = read_day(d)
        if df is None:
            continue
        s = df[df["ticker"].isin(rev)].set_index("ticker")[field]
        frames[pd.Timestamp(d)] = s
    if not frames:
        return pd.DataFrame()
    px = pd.DataFrame(frames).T.sort_index()
    if field in ("o", "h", "l", "c", "v"):
        last = px.index[-1]
        for sp in _splits():
            if pd.Timestamp(sp["date"]) > last:            # announced, not yet effective: nothing to adjust
                continue
            col = sp["ticker"]
            if col in px.columns and sp["ratio"] > 0:
                before = px.index < pd.Timestamp(sp["date"])
                px.loc[before, col] = px.loc[before, col] * (sp["ratio"] if field == "v" else 1 / sp["ratio"])
    return px.rename(columns=rev)
