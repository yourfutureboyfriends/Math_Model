"""Bounds and observation-time guards shared by the physical-economy trackers."""
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def position(lat, lon):
    return finite(lat) and finite(lon) and abs(lat) <= 90 and abs(lon) <= 180


def recent(fix, now, max_age):
    return finite(fix) and fix > 0 and now - max_age <= fix <= now + 30


def ship_phase(status, speed):
    if status == 5:
        return 'moored'
    if status == 1:
        return 'anchored'
    if status in (0, 8, 11, 12) or status in (None, 15) and finite(speed) and speed >= 0.5:
        return 'underway'
    return 'unknown'


def calendar_average(rows, end, days, field, minimum=None):
    """Calendar-bounded average; never convert absent AIS observations into zero activity."""
    from datetime import date, timedelta
    end = date.fromisoformat(str(end)[:10])
    start = end - timedelta(days=days - 1)
    observations = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row.get('date'))[:10])
        except ValueError:
            continue
        value = row.get(field)
        if start <= day <= end and finite(value) and value >= 0:
            observations[day] = value
    need = days if minimum is None else minimum
    return sum(observations.values()) / len(observations) if len(observations) >= need and observations else None
