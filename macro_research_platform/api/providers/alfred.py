"""
ALFRED — FRED's archive of past data vintages (St. Louis Fed, free, uses FRED_API_KEY).

Most macro series are revised after release (GDP several times, payrolls twice, then
benchmarked yearly). A backtest that uses today's revised history sees numbers nobody had
at the time. ALFRED returns a series as it stood on any past date, the first-release
values, or the full revision history.

  as_of(series, date)        observations as published on `date`
  first_release(series)      each observation's first published value + its release date
  revisions(series)          first release vs latest, per observation, with summary stats
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)
API = "https://api.stlouisfed.org/fred/series/observations"
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "alfred"
TTL = 12 * 3600


class AlfredError(RuntimeError):
    pass


def _key() -> str:
    from api.config import FRED_API_KEY
    if not FRED_API_KEY:
        raise AlfredError("FRED_API_KEY is not set.")
    return FRED_API_KEY


def _fetch(params: Dict[str, Any], cache_name: str) -> List[Dict[str, Any]]:
    path = CACHE / f"{cache_name}.json"
    try:
        if time.time() - path.stat().st_mtime < TTL:
            return json.loads(path.read_text())
    except Exception:
        pass
    try:
        from api import fred_guard
        if fred_guard.is_open():
            raise AlfredError("FRED is rate-limiting requests right now — try again shortly.")
    except ImportError:
        pass
    try:
        r = requests.get(API, params={**params, "api_key": _key(), "file_type": "json"}, timeout=40)
        if r.status_code == 400:
            raise AlfredError(r.json().get("error_message", "Bad request"))
        r.raise_for_status()
        obs = r.json().get("observations", [])
    except AlfredError:
        raise
    except Exception as e:
        try:
            return json.loads(path.read_text())
        except Exception:
            raise AlfredError(f"ALFRED request failed: {e}") from e
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obs))
    return obs


def _num(v: str) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None                                      # FRED uses "." for missing


def as_of(series: str, vintage_date: str, start: str = "1990-01-01") -> List[Dict[str, Any]]:
    obs = _fetch({"series_id": series, "realtime_start": vintage_date, "realtime_end": vintage_date,
                  "observation_start": start}, f"{series}_asof_{vintage_date}_{start}")
    return [{"date": o["date"], "value": _num(o["value"])} for o in obs]


def first_release(series: str, start: str = "1990-01-01") -> List[Dict[str, Any]]:
    """output_type=4: initial release only, each with the date it was published."""
    obs = _fetch({"series_id": series, "realtime_start": "1776-07-04", "realtime_end": "9999-12-31",
                  "output_type": 4, "observation_start": start}, f"{series}_first_{start}")
    return [{"date": o["date"], "value": _num(o["value"]), "released": o.get("realtime_start")} for o in obs]


def latest(series: str, start: str = "1990-01-01") -> List[Dict[str, Any]]:
    obs = _fetch({"series_id": series, "observation_start": start}, f"{series}_latest_{start}")
    return [{"date": o["date"], "value": _num(o["value"])} for o in obs]


def revisions(series: str, start: str = "2000-01-01", transform: str = "level") -> Dict[str, Any]:
    """First release vs today's value for each observation. `transform`: level, or pct
    (period-over-period % change computed within each vintage — what models usually use)."""
    import numpy as np
    first = {o["date"]: o for o in first_release(series, start)}
    now = latest(series, start)
    rows = []
    prev_first = prev_now = None
    for o in now:
        f = first.get(o["date"])
        fv, nv = (f or {}).get("value"), o["value"]
        if transform == "pct":
            pf, pn = prev_first, prev_now
            prev_first, prev_now = fv, nv
            fv = (fv / pf - 1) * 100 if fv is not None and pf else None
            nv = (nv / pn - 1) * 100 if nv is not None and pn else None
        if fv is None or nv is None:
            continue
        rows.append({"date": o["date"], "first": round(fv, 4), "latest": round(nv, 4),
                     "revision": round(nv - fv, 4), "released": (f or {}).get("released")})
    rev = np.array([r["revision"] for r in rows]) if rows else np.array([])
    lat = np.array([r["latest"] for r in rows]) if rows else np.array([])
    fst = np.array([r["first"] for r in rows]) if rows else np.array([])
    stats = {}
    if rev.size >= 8:
        stats = {"mean_revision": round(float(rev.mean()), 4), "mean_abs_revision": round(float(np.abs(rev).mean()), 4),
                 "share_revised_up": round(float((rev > 0).mean()), 3),
                 "sign_flips": int(((fst > 0) != (lat > 0)).sum()) if transform == "pct" else None,
                 "correlation_first_vs_latest": round(float(np.corrcoef(fst, lat)[0, 1]), 3)}
    return {"series": series, "transform": transform, "rows": rows, "stats": stats, "source": "ALFRED (St. Louis Fed)"}
