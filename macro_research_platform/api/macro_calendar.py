"""
Macro calendar: FOMC meetings and FRED release dates — the dates every panel, the event dataset and the
blackout calendar agree on.

Functions
    _fetch_fomc_meetings()                     (first day, decision day) of every FOMC meeting, scraped from the
                                               Federal Reserve's calendar page; cached 24 h
    _fetch_fomc_dates()                        the decision days (last day of each meeting), sorted
    _fomc_blackout_start(first_day)            start of the Fed's communications blackout (second Saturday before)
    _fetch_fred_release_dates(id, n, past)     upcoming (or the last n past) release dates of a FRED release
                                               (CPI = 10, Employment Situation = 50); cached 6 h
    _calendar_release_dates(id, start, end)    scheduled dates from the economic calendar's disk cache
    _parse_fomc_calendar(html)                 parser for the Fed page (tested separately)
    lru_cache_with_ttl(ttl_seconds)            memoise a function for a time; empty / None results are not cached,
                                               so one failed fetch does not pin an empty answer for the whole TTL

Failure behaviour: every fetch returns [] on a network or parse failure and logs a warning — callers fall back to
their own estimates and say so; nothing here raises into a request.

Names keep their leading underscore for compatibility with existing callers (api.main re-imports them).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def lru_cache_with_ttl(ttl_seconds: int = 300):
    """LRU cache with TTL (time-to-live) support."""
    def decorator(func):
        cache = {}
        timestamps = {}
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from arguments
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()
            # Check if cached value is still valid
            if key in cache:
                if now - timestamps[key] < ttl_seconds:
                    return cache[key]
                else:
                    # Expired, remove from cache
                    del cache[key]
                    del timestamps[key]
            # Compute and cache new value. Empty/None results (a failed fetch) are not
            # cached, so one network blip doesn't pin an empty answer for the whole TTL.
            result = func(*args, **kwargs)
            if result is None or (hasattr(result, "__len__") and len(result) == 0):
                return result
            cache[key] = result
            timestamps[key] = now
            return result
        return wrapper
    return decorator


def _parse_fomc_calendar(html: str) -> list[tuple[str, str]]:
    """(first_day, decision_day) ISO dates for every FOMC meeting on the Fed's calendar page.

    The page groups meetings under "<YEAR> FOMC Meetings" panels; each meeting row has a
    month cell ("June", or "Apr/May" for a meeting spanning two months) and a day cell
    ("16-17", "30-1", "17-18*"). The decision is announced on the LAST day. Notation votes
    are skipped (they are not meetings).
    """
    import re
    from datetime import date as _date
    from bs4 import BeautifulSoup

    def _month(txt: str) -> int:
        return datetime.strptime(txt.strip()[:3], "%b").month

    meetings = []
    soup = BeautifulSoup(html, "html.parser")
    for panel in soup.select(".panel"):
        heading = panel.select_one(".panel-heading")
        ym = re.search(r"(\d{4})\s+FOMC Meetings", heading.get_text(" ", strip=True)) if heading else None
        if not ym:
            continue
        year = int(ym.group(1))
        for row in panel.select(".fomc-meeting"):
            mcell, dcell = row.select_one(".fomc-meeting__month"), row.select_one(".fomc-meeting__date")
            if not mcell or not dcell:
                continue
            day_txt = dcell.get_text(" ", strip=True)
            days = [int(d) for d in re.findall(r"\d+", day_txt)]
            if not days or "notation" in day_txt.lower():
                continue
            months = [m for m in mcell.get_text(strip=True).split("/") if m]
            try:
                m_start = _month(months[0])
                d1, d2 = days[0], days[-1]
                m_end = _month(months[-1]) if (len(months) > 1 and d2 < d1) else m_start
                meetings.append((_date(year, m_start, d1).isoformat(), _date(year, m_end, d2).isoformat()))
            except (ValueError, IndexError):
                continue
    return sorted(set(meetings), key=lambda m: m[1])


@lru_cache_with_ttl(ttl_seconds=86400)
def _fetch_fomc_meetings() -> list[tuple[str, str]]:
    """(first_day, decision_day) for every meeting on federalreserve.gov (cached 24h)."""
    try:
        import requests
        r = requests.get(
            "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return _parse_fomc_calendar(r.text)
    except Exception as e:
        logger.warning(f"FOMC scrape failed: {e}")
        return []


def _fetch_fomc_dates() -> list[str]:
    """FOMC decision dates (last day of each meeting), sorted."""
    return [end for _, end in _fetch_fomc_meetings()]


def _fomc_blackout_start(first_day):
    """Fed communications blackout begins the second Saturday before the meeting's first day."""
    from datetime import timedelta as _td
    back = (first_day.weekday() - 5) % 7 or 7     # days back to the preceding Saturday
    return first_day - _td(days=back + 7)


# FRED release dates for NFP and CPI
@lru_cache_with_ttl(ttl_seconds=21600)
def _fetch_fred_release_dates(release_id: int, n: int = 8, past: bool = False) -> list[str]:
    """Release dates for a FRED release (CPI = 10, Employment Situation = 50).

    Upcoming dates (default) need include_release_dates_with_no_data=true — without it FRED
    only returns dates that already have data, so the upcoming list was always empty and
    every caller silently used its heuristic fallback. past=True returns the most recent
    `n` past release dates, newest last.
    """
    try:
        import requests
        from api.config import FRED_API_KEY
        if not FRED_API_KEY:
            logger.warning("FRED_API_KEY not set, release dates unavailable")
            return []
        today = datetime.now().date().isoformat()
        params = {"release_id": release_id, "api_key": FRED_API_KEY, "file_type": "json",
                  "include_release_dates_with_no_data": "true", "sort_order": "desc", "limit": 200}
        r = requests.get("https://api.stlouisfed.org/fred/release/dates", params=params, timeout=8)
        dates = sorted({d["date"] for d in r.json().get("release_dates", [])})
        if past:
            return [d for d in dates if d < today][-n:]
        return [d for d in dates if d >= today][:n]
    except Exception as e:
        logger.warning(f"FRED release dates failed: {e}")
        return []


def _calendar_release_dates(release_id: int, start, end) -> list[str]:
    """Scheduled dates from the economic calendar's cache (disk, 12h, last good copy on a
    FRED outage), so every panel shows the same official date. [] if never fetched."""
    try:
        from api.econ_calendar import _dates
        return _dates(release_id, start, end)
    except Exception as e:
        logger.warning(f"release dates {release_id} unavailable: {e}")
        return []
