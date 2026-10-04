"""
Release-calendar-aware data freshness.

The old check compared an observation's *date* with a fixed max age. FRED dates monthly
data at the first of the month and quarterly data at the first of the quarter, and every
series is published with a lag, so a perfectly current CPI print (August data, out mid-
September, September not due until mid-October) read as "64 days old → STALE".

Here each series has a frequency and a typical publication lag after the period ENDS.
From those we derive the latest period that *should* be published today and grade the
data by how many periods it is behind that:

  CURRENT           has the latest period that is due                      → FRESH
  DUE               one period behind, but within the release-date grace   → FRESH
                    window (releases slip by a few days; holidays)
  LATE              one period behind, past the grace window               → STALE
  MISSING_PERIODS   two or more periods behind                             → CRITICAL

`status` keeps the FRESH/STALE/CRITICAL/UNKNOWN vocabulary the UI already uses.
Lags are typical (BLS/BEA/Fed calendars); exact dates vary, which the grace absorbs.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SeriesSpec:
    metric: str          # key the UI uses (StaleBadge / Key Metrics)
    name: str
    series_id: str
    frequency: str       # D (business daily) | W (weekly, dated at week end) | M | Q
    lag_days: int        # typical publication lag after the period ends (business days for D)
    grace_days: int      # tolerance for a slipped release before it counts as late
    category: str
    unit: str = ""                 # display unit of the value shown
    transform: str = ""            # FRED units suffix for the displayed value: _PC1 (% YoY), _CHG
    source: str = "FRED"

    @property
    def value_series(self) -> str:
        return self.series_id + self.transform


# Every macro input the models consume. (The jobs report lands on the first Friday, so
# 1-7 days after month end: lag 3 with a 7-day grace.), grouped for the data-quality view.
SERIES: List[SeriesSpec] = [
    # Growth & labour
    SeriesSpec("growth", "Real GDP growth (QoQ saar)", "A191RL1Q225SBEA", "Q", 30, 10, "Growth", unit="% saar"),
    SeriesSpec("indpro", "Industrial production", "INDPRO", "M", 17, 5, "Growth", unit="% YoY", transform="_PC1"),
    SeriesSpec("payrolls", "Nonfarm payrolls", "PAYEMS", "M", 3, 7, "Labour", unit="k jobs m/m", transform="_CHG"),
    SeriesSpec("unemployment", "Unemployment rate", "UNRATE", "M", 3, 7, "Labour", unit="%"),
    SeriesSpec("recession", "Sahm rule (real-time)", "SAHMREALTIME", "M", 3, 7, "Labour", unit="pp"),
    SeriesSpec("claims", "Initial jobless claims", "ICSA", "W", 5, 2, "Labour", unit="claims"),
    # Prices
    SeriesSpec("inflation", "CPI (headline)", "CPIAUCSL", "M", 15, 7, "Inflation", unit="% YoY", transform="_PC1"),
    SeriesSpec("core_pce", "Core PCE price index", "PCEPILFE", "M", 31, 7, "Inflation", unit="% YoY", transform="_PC1"),
    SeriesSpec("breakeven", "10Y breakeven inflation", "T10YIE", "D", 1, 2, "Inflation", unit="%"),
    # Policy, liquidity & rates
    SeriesSpec("fed_funds", "Fed funds rate (monthly avg)", "FEDFUNDS", "M", 2, 5, "Policy & liquidity", unit="%"),
    SeriesSpec("dff", "Effective fed funds (daily)", "DFF", "D", 1, 2, "Policy & liquidity", unit="%"),
    SeriesSpec("m2", "M2 money supply", "M2SL", "M", 27, 7, "Policy & liquidity", unit="% YoY", transform="_PC1"),
    SeriesSpec("liquidity", "10Y Treasury yield", "DGS10", "D", 1, 2, "Rates", unit="%"),
    SeriesSpec("two_year", "2Y Treasury yield", "DGS2", "D", 1, 2, "Rates", unit="%"),
    SeriesSpec("two_ten", "2s10s spread", "T10Y2Y", "D", 1, 2, "Rates", unit="pp"),
    # Credit & risk
    SeriesSpec("hy_spread", "HY credit spread (ICE BofA OAS)", "BAMLH0A0HYM2", "D", 1, 2, "Credit & risk", unit="%"),
    SeriesSpec("risk", "VIX (CBOE close)", "VIXCLS", "D", 1, 2, "Credit & risk", unit="pts"),
]


# ── Period arithmetic ────────────────────────────────────────────────────────
def _is_bday(d: date) -> bool:
    return d.weekday() < 5


def _add_bdays(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    while n:
        d += timedelta(days=step)
        if _is_bday(d):
            n -= step
    return d


def _bdays_between(a: date, b: date) -> int:
    """Business days in (a, b]."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += _is_bday(d)
    return n


def period_start(d: date, freq: str) -> date:
    if freq == "M":
        return d.replace(day=1)
    if freq == "Q":
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    return d


def period_end(start: date, freq: str) -> date:
    if freq == "M":
        return start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if freq == "Q":
        m = start.month + 2
        return date(start.year, m, calendar.monthrange(start.year, m)[1])
    return start                     # D / W observations are dated at their period end


def shift_period(start: date, freq: str, n: int) -> date:
    if freq in ("M", "Q"):
        months = n * (3 if freq == "Q" else 1)
        idx = start.year * 12 + start.month - 1 + months
        return date(idx // 12, idx % 12 + 1, 1)
    if freq == "W":
        return start + timedelta(weeks=n)
    return _add_bdays(start, n)


def release_due(start: date, spec: SeriesSpec) -> date:
    end = period_end(start, spec.frequency)
    return _add_bdays(end, spec.lag_days) if spec.frequency == "D" else end + timedelta(days=spec.lag_days)


def _grace_end(due: date, spec: SeriesSpec) -> date:
    return _add_bdays(due, spec.grace_days) if spec.frequency == "D" else due + timedelta(days=spec.grace_days)


def expected_latest(spec: SeriesSpec, today: date, anchor: Optional[date] = None) -> date:
    """The most recent period (by its FRED observation date) whose release is due by today.
    Weekly series step from `anchor` (their last observation) so the weekday matches."""
    f = spec.frequency
    if f == "D":
        d = today if _is_bday(today) else _add_bdays(today, -1)     # last business day
        return _add_bdays(d, -spec.lag_days)
    p = period_start(today, f) if f != "W" else (anchor or today)
    if f == "W" and anchor:
        while release_due(shift_period(p, f, 1), spec) <= today:
            p = shift_period(p, f, 1)
    while release_due(p, spec) > today:
        p = shift_period(p, f, -1)
    return p


def periods_behind(last: date, expected: date, freq: str) -> int:
    if last >= expected:
        return 0
    if freq in ("M", "Q"):
        months = (expected.year - last.year) * 12 + expected.month - last.month
        return max(1, months // (3 if freq == "Q" else 1))
    if freq == "W":
        return max(1, round((expected - last).days / 7))
    return _bdays_between(last, expected)


def assess(spec: SeriesSpec, last_obs: Optional[date], today: date) -> Dict:
    """Grade one series. Pure — no I/O — so it is unit-testable for any date."""
    base = {"metric": spec.metric, "name": spec.name, "series_id": spec.series_id, "unit": spec.unit,
            "frequency": spec.frequency, "category": spec.category, "source": spec.source,
            "publication_lag_days": spec.lag_days}
    if last_obs is None:
        return {**base, "status": "UNKNOWN", "state": "UNAVAILABLE", "last_observation_date": None,
                "age_days": None, "max_lag_days": None, "expected_period": None,
                "periods_behind": None, "next_expected_release": None}
    f = spec.frequency
    last = period_start(last_obs, f)
    expected = expected_latest(spec, today, anchor=last)
    behind = periods_behind(last, expected, f)
    # For daily data, "one period" is one business day: give the grace in business days.
    if f == "D":
        state = ("CURRENT" if behind == 0 else "DUE" if behind <= spec.grace_days
                 else "LATE" if behind <= spec.grace_days + 3 else "MISSING_PERIODS")
    elif behind == 0:
        state = "CURRENT"
    elif behind == 1:
        state = "DUE" if today <= _grace_end(release_due(expected, spec), spec) else "LATE"
    else:
        state = "MISSING_PERIODS"
    status = {"CURRENT": "FRESH", "DUE": "FRESH", "LATE": "STALE", "MISSING_PERIODS": "CRITICAL"}[state]
    nxt = shift_period(last, f, 1)
    # Age tolerance in calendar days from the observation date (for older consumers).
    tol = (_grace_end(release_due(nxt, spec), spec) - last).days
    return {**base, "status": status, "state": state,
            "last_observation_date": last_obs.isoformat(),
            "age_days": (today - last_obs).days, "max_lag_days": tol,
            "expected_period": expected.isoformat(), "periods_behind": behind,
            "next_expected_release": release_due(nxt, spec).isoformat()}
