"""
ML tasks: the forecasting questions the engine answers, each tied to a decision on the platform.

A task is a binary question about the future, its inputs (from api/ml/features.py), and how long after the forecast
the answer is known (`known_after`, months) — training only ever uses months whose answer was known by then.
Inputs are chosen per task from the economics of the question (fixed, not searched).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np


@dataclass(frozen=True)
class Task:
    name: str
    title: str
    question: str
    used_for: str
    features: List[str]
    known_after: int
    target: Callable[[], Dict[str, int]]
    start_year: int = 1985
    notes: List[str] = field(default_factory=list)


# ── targets ───────────────────────────────────────────────────────────────────
def _recession() -> Dict[str, int]:
    from api.models_ml import recession_ensemble as R
    data, _ = R._inputs()
    return {r["month"]: int(r["y"]) for r in (data or {}).get("rows", []) if r.get("y") is not None}


def _spx_fall_6m() -> Dict[str, int]:
    """1 if the S&P 500 closes 10%+ below the month's first close at any point in the next six months."""
    from api.ml.features import _yahoo_daily
    spx = _yahoo_daily("^GSPC")
    out: Dict[str, int] = {}
    months = sorted({d.strftime("%Y-%m") for d in spx.index})
    for m in months:
        y, mo = map(int, m.split("-"))
        start = spx[spx.index >= f"{m}-01"]
        if start.empty:
            continue
        end_y, end_m = y + (mo - 1 + 6) // 12, (mo - 1 + 6) % 12 + 1
        window = start[start.index < f"{end_y}-{end_m:02d}-01"]
        if window.empty or window.index[-1] < start.index[0]:
            continue
        if spx.index[-1] < np.datetime64(f"{end_y}-{end_m:02d}-01"):
            continue                                              # the six months are not over yet
        out[m] = int(window.min() <= 0.9 * start.iloc[0])
    return out


def _fred_up(series_id: str, horizon: int, transform=None) -> Dict[str, int]:
    """1 if the series' monthly value is higher `horizon` months later."""
    from api.ml.features import _fred_monthly
    s = _fred_monthly(series_id)
    if transform:
        s = transform(s)
    fut = s.shift(-horizon)
    return {d.strftime("%Y-%m"): int(f > v) for d, v, f in zip(s.index, s.values, fut.values)
            if np.isfinite(v) and np.isfinite(f)}


TASKS: Dict[str, Task] = {t.name: t for t in [
    Task("recession_12m", "US recession within 12 months", "Will an NBER recession be under way at any point in the next 12 months?",
         "Recession risk on the desk; the headline model's challenger",
         ["ts", "ntfs", "ebp", "pay6", "spx6", "unemp_d6", "baa"], known_after=24, target=_recession,
         notes=["Answer known 12 months later plus the NBER's announcement lag (≈12 months)."]),
    Task("spx_drawdown_6m", "S&P 500 falls 10%+ within 6 months", "Will the S&P 500 close 10% or more below today's level within six months?",
         "Equity risk sizing and the desk's drawdown warning",
         ["spx6", "spx_vol3", "ts", "ebp", "baa", "ff", "unemp_d6", "sent_d6"], known_after=7, target=_spx_fall_6m),
    Task("yields_up_3m", "10Y yield higher in 3 months", "Will the 10-year Treasury yield be higher in three months?",
         "The playbook's duration call (short duration if likely)",
         ["y10_d3", "ts", "ff", "cpi_yoy", "cpi_d3", "unemp_d6", "spx6", "usd6"], known_after=4,
         target=lambda: _fred_up("GS10", 3)),
    Task("inflation_up_3m", "CPI inflation higher in 3 months", "Will year-on-year CPI inflation be higher in three months?",
         "The inflation axis and the commodity call",
         ["cpi_yoy", "cpi_d3", "oil6", "usd6", "unemp_d6", "pay6", "y10_d3"], known_after=5,
         target=lambda: _fred_up("CPIAUCSL", 3, lambda m: (m / m.shift(12) - 1) * 100)),
    Task("oil_up_3m", "Oil higher in 3 months", "Will WTI crude be higher in three months?",
         "The commodity call",
         ["oil6", "usd6", "cpi_d3", "pay6", "spx6", "ts"], known_after=4, target=lambda: _fred_up("WTISPLC", 3)),
    Task("unemployment_up_6m", "Unemployment higher in 6 months", "Will the unemployment rate be higher in six months?",
         "Labour-market turn; early recession warning",
         ["unemp_d6", "pay6", "ts", "ebp", "spx6", "sent_d6"], known_after=7, target=lambda: _fred_up("UNRATE", 6)),
]}


def get(name: str) -> Optional[Task]:
    return TASKS.get(name)
