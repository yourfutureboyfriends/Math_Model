"""
FRED Data Freshness Validator

Tracks release dates and validates data is current.
FRED API provides release dates via series/observations endpoint.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# FRED Release schedules (typical - actual dates vary)
FRED_RELEASE_SCHEDULE = {
    # GDP: Monthly, typically last Thursday of month following quarter end
    "A191RL1Q225SBEA": {"frequency": "monthly", "lag_days": 30},
    # CPI: Monthly, typically 10-15th of following month
    "CPIAUCSL_PC1": {"frequency": "monthly", "lag_days": 15},
    "CPIAUCSL": {"frequency": "monthly", "lag_days": 15},
    # Fed Funds: Daily
    "FEDFUNDS": {"frequency": "daily", "lag_days": 1},
    # HY Spreads: Daily
    "BAMLH0A0HYM2": {"frequency": "daily", "lag_days": 1},
    # Yield Curve: Daily
    "T10Y2Y": {"frequency": "daily", "lag_days": 1},
    # M2: Weekly
    "M2SL": {"frequency": "weekly", "lag_days": 7},
    # Sahm Rule: Monthly
    "SAHMREALTIME": {"frequency": "monthly", "lag_days": 15},
    # VIX: Daily
    "VIXCLS": {"frequency": "daily", "lag_days": 1},
}

@dataclass
class DataFreshnessStatus:
    series_id: str
    metric_name: str
    last_observation_date: Optional[datetime]
    days_since_update: Optional[int]
    max_acceptable_lag: int
    is_stale: bool
    is_critical: bool  # Critical if very stale


def check_fred_data_freshness(
    series_id: str,
    last_date: Optional[datetime],
    metric_name: str = ""
) -> DataFreshnessStatus:
    """
    Check if FRED data is within acceptable freshness window.

    Args:
        series_id: FRED series ID
        last_date: Last observation date from FRED
        metric_name: Human-readable metric name

    Returns:
        DataFreshnessStatus with staleness assessment
    """
    schedule = FRED_RELEASE_SCHEDULE.get(series_id, {"frequency": "daily", "lag_days": 3})
    max_lag = schedule["lag_days"]

    if last_date is None:
        return DataFreshnessStatus(
            series_id=series_id,
            metric_name=metric_name or series_id,
            last_observation_date=None,
            days_since_update=None,
            max_acceptable_lag=max_lag,
            is_stale=True,
            is_critical=True
        )

    days_since = (datetime.now() - last_date).days
    is_stale = days_since > max_lag
    is_critical = days_since > max_lag * 2  # Double the lag = critical

    return DataFreshnessStatus(
        series_id=series_id,
        metric_name=metric_name or series_id,
        last_observation_date=last_date,
        days_since_update=days_since,
        max_acceptable_lag=max_lag,
        is_stale=is_stale,
        is_critical=is_critical
    )


def validate_all_freshness(
    observation_dates: Dict[str, Optional[datetime]]
) -> List[DataFreshnessStatus]:
    """
    Validate freshness of all FRED series.

    Args:
        observation_dates: Dict of {series_id: last_observation_date}

    Returns:
        List of freshness statuses
    """
    results = []
    for series_id, last_date in observation_dates.items():
        status = check_fred_data_freshness(series_id, last_date)
        results.append(status)

        if status.is_critical:
            logger.critical(
                f"[FRESHNESS] CRITICAL: {status.metric_name} ({series_id}) "
                f"is {status.days_since_update} days stale (max: {status.max_acceptable_lag})"
            )
        elif status.is_stale:
            logger.warning(
                f"[FRESHNESS] STALE: {status.metric_name} ({series_id}) "
                f"is {status.days_since_update} days stale (max: {status.max_acceptable_lag})"
            )

    return results


def get_freshness_summary(statuses: List[DataFreshnessStatus]) -> Dict:
    """
    Generate summary of freshness checks for dashboard.

    Returns dict with:
        - total_series: int
        - fresh: int
        - stale: int
        - critical: int
        - stale_series: List[str]
    """
    total = len(statuses)
    fresh = sum(1 for s in statuses if not s.is_stale)
    stale = sum(1 for s in statuses if s.is_stale and not s.is_critical)
    critical = sum(1 for s in statuses if s.is_critical)
    stale_series = [s.metric_name for s in statuses if s.is_stale]

    return {
        "totalSeries": total,
        "fresh": fresh,
        "stale": stale,
        "critical": critical,
        "freshnessPct": round(fresh / total * 100, 1) if total > 0 else 0,
        "staleSeries": stale_series[:10],  # Top 10 for display
        "lastChecked": datetime.now().isoformat(),
    }


# Expected release dates for known series (as of May 2026)
EXPECTED_RELEASES = {
    # CPI: Released monthly, typically around 10-15th
    "CPIAUCSL_PC1": datetime(2026, 5, 12),  # Next release
    # GDP: Quarterly
    "A191RL1Q225SBEA": datetime(2026, 4, 29),  # Q1 2026 advance
}


def get_next_expected_release(series_id: str) -> Optional[datetime]:
    """Get expected next release date for a series."""
    return EXPECTED_RELEASES.get(series_id)


# ─────────────────────────────────────────────────────────────────────────────
# Live per-field freshness (served by /api/v1/freshness)
# ─────────────────────────────────────────────────────────────────────────────
# Freshness is graded against each series' release calendar (api/release_calendar.py):
# "is the latest period that should be published by now present?", not "how old is the
# observation date". See that module for the states.
_FRESHNESS_CACHE: Dict[str, object] = {"data": None, "ts": 0.0}
_FRESHNESS_TTL = 300  # seconds


def get_live_freshness(force: bool = False, today=None) -> Dict:
    """Latest observation of every model input from FRED, graded against its release
    calendar. Returns per-series detail (status FRESH|STALE|CRITICAL|UNKNOWN plus the
    calendar state, expected period, periods behind and next expected release), per-
    category roll-ups and a summary. Cached ~5 min."""
    import time as _time
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date as _date
    from api.release_calendar import SERIES, assess

    now = _time.time()
    cached = _FRESHNESS_CACHE.get("data")
    if not force and today is None and cached and now - float(_FRESHNESS_CACHE["ts"]) < _FRESHNESS_TTL:
        return cached  # type: ignore[return-value]

    try:
        from api.providers.fred_provider import FREDProvider
        provider = FREDProvider()
    except Exception as e:  # pragma: no cover - defensive
        return {"available": False, "reason": f"FRED provider unavailable: {e}", "series": []}

    def _latest(series_id: str):
        try:
            # limit>1: the newest row can be a "." holiday placeholder.
            obs = provider.fetch_latest(series_id, limit=10)
            if obs is not None and obs.date:
                return datetime.strptime(obs.date[:10], "%Y-%m-%d").date(), obs.value
        except Exception as e:
            logger.warning("[FRESHNESS] date fetch failed for %s: %s", series_id, e)
        return None, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        # The display transform (e.g. CPI % YoY) shares observation dates with the base series.
        latest = list(pool.map(lambda sp: _latest(sp.value_series), SERIES))

    asof = today or _date.today()
    out = []
    for spec, (last_date, value) in zip(SERIES, latest):
        row = assess(spec, last_date, asof)
        row["latest_value"] = round(value, 3) if isinstance(value, (int, float)) else value
        out.append(row)

    categories: Dict[str, Dict[str, int]] = {}
    for r in out:
        c = categories.setdefault(r["category"], {"total": 0, "fresh": 0})
        c["total"] += 1
        c["fresh"] += r["status"] == "FRESH"
    known = [r for r in out if r["status"] != "UNKNOWN"]
    fresh = sum(1 for s in out if s["status"] == "FRESH")
    result = {
        "available": True,
        "method": "release-calendar",
        "series": out,
        "categories": categories,
        "fresh": fresh,
        "stale": sum(1 for s in out if s["status"] in ("STALE", "CRITICAL")),
        "unknown": len(out) - len(known),
        "total": len(out),
        "score_pct": round(100 * fresh / len(known)) if known else None,
        "checked_at": datetime.now().isoformat(),
    }
    if today is None:
        _FRESHNESS_CACHE["data"] = result
        _FRESHNESS_CACHE["ts"] = now
    return result
