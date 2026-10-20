"""
Spreadsheet / API access to the terminal's public data (the BDH / BDP idea): any Yahoo symbol, any FRED series and
the composite model's weekly history, as a wide CSV or JSON table, plus the latest value of each.

  GET /api/v1/data/history?ids=SPY,^VIX,fred:CPIAUCSL,model:composite&start=2020-01-01&freq=M&format=csv
  GET /api/v1/data/latest?ids=SPY,fred:UNRATE,field:macro.regime&format=csv

Excel: Data → From Web → paste the URL (the server must be reachable from Excel). Python/R: read the CSV URL.
Market and macro data are open reads like the rest of the research API; book data is not exposed here.
"""
from __future__ import annotations

import asyncio
import csv
import io
import re
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["data"])
ID_RE = re.compile(r"^(fred:[A-Z0-9_]{2,30}|model:composite|field:[a-z_.]{3,40}|[A-Za-z0-9^=.\-]{1,20})$")
MAX_IDS = 25


def _ids(ids: str) -> List[str]:
    out = [i.strip() for i in ids.split(",") if i.strip()]
    if not out or len(out) > MAX_IDS:
        raise HTTPException(422, f"Give 1–{MAX_IDS} comma-separated ids.")
    bad = [i for i in out if not ID_RE.match(i)]
    if bad:
        raise HTTPException(422, f"Unrecognised id(s): {', '.join(bad[:5])}. Use a Yahoo symbol, fred:SERIES, "
                                 "model:composite or field:<alert field>.")
    return out


def _series(i: str, start: str) -> Dict[str, float]:
    if i.startswith("fred:"):
        from api.handlers.macro_inputs import _fetch_fred_history_sync
        from datetime import date
        days = (date.today() - date.fromisoformat(start)).days + 10
        s = _fetch_fred_history_sync(i[5:], max(days, 30))
        return {d: v for d, v in zip(s.dates, s.values) if d >= start}
    if i == "model:composite":
        from api.handlers.composite_history import composite_history
        pts = asyncio.run(composite_history(260))["points"]
        return {p["date"]: p["composite"] for p in pts if p["date"] >= start and p["composite"] is not None}
    if i.startswith("field:"):
        raise HTTPException(422, f"{i} has no history — use it with /api/v1/data/latest.")
    from api.market_bars import bars
    b = bars(i.upper(), "1d", "max" if start < "2015-01-01" else "10y")
    return {x["t"]: x["c"] for x in b["bars"] if x["t"] >= start}


def _resample(s: Dict[str, float], freq: str) -> Dict[str, float]:
    if freq == "D":
        return s
    out: Dict[str, float] = {}
    for d in sorted(s):                                    # last observation of each week / month
        key = d[:7] if freq == "M" else _iso_week(d)
        out[key] = s[d]
    return out


def _iso_week(d: str) -> str:
    from datetime import date
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f"{y}-W{w:02d}"


def _csv(header: List[str], rows: List[List]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


@router.get("/api/v1/data/history")
async def data_history(ids: str, start: str = Query("2020-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
                       freq: str = Query("D", pattern="^(D|W|M)$"), format: str = Query("csv", pattern="^(csv|json)$")):
    """Wide table: one row per date, one column per id (daily closes / observations; W and M = last of period)."""
    idl = _ids(ids)

    def load(i):
        try:
            return _resample(_series(i, start), freq)
        except HTTPException:
            raise
        except Exception:
            return {}
    cols = await asyncio.gather(*[asyncio.to_thread(load, i) for i in idl])
    dates = sorted(set().union(*[c.keys() for c in cols]))
    rows = [[d] + [c.get(d) for c in cols] for d in dates]
    missing = [i for i, c in zip(idl, cols) if not c]
    if format == "json":
        return {"columns": ["date"] + idl, "rows": rows, "missing": missing}
    return PlainTextResponse(_csv(["date"] + idl, rows), media_type="text/csv",
                             headers={"X-Missing-Ids": ",".join(missing)} if missing else None)


@router.get("/api/v1/data/latest")
async def data_latest(ids: str, format: str = Query("csv", pattern="^(csv|json)$")):
    """Latest value and its date for each id (fields: the current model / sentiment reading)."""
    idl = _ids(ids)

    def one(i):
        if i.startswith("field:"):
            from api.marketdata import field_alerts as fa
            f = i[6:]
            if not fa.valid_field(f):
                return [i, None, None, "unknown field"]
            return [i, fa.value(f), None, fa.field_label(f)]
        try:
            s = _series(i, "2000-01-01" if i.startswith("fred:") else "2024-01-01")
        except Exception as e:
            return [i, None, None, str(e)[:80]]
        if not s:
            return [i, None, None, "no data"]
        d = max(s)
        return [i, s[d], d, ""]
    rows = await asyncio.gather(*[asyncio.to_thread(one, i) for i in idl])
    if format == "json":
        return {"rows": [dict(zip(("id", "value", "date", "note"), r)) for r in rows]}
    return PlainTextResponse(_csv(["id", "value", "date", "note"], [list(r) for r in rows]), media_type="text/csv")
