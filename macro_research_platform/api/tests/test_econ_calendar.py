"""Economic calendar: latest-print transforms must match by date, not position."""
from api import econ_calendar
from api.handlers.macro_inputs import DatedSeries


def _monthly(values_by_month):
    dates = sorted(values_by_month)
    return DatedSeries("X", dates, [values_by_month[d] for d in dates])


def test_yoy_skips_missing_month(monkeypatch):
    # Oct-2025 never published: 12 observations back is Jul-2025, not Aug-2025.
    vals = {f"2025-{m:02d}-01": 100.0 + m for m in range(1, 13) if m != 10}
    vals.update({f"2026-{m:02d}-01": 110.0 + m for m in range(1, 9)})
    monkeypatch.setattr("api.handlers.macro_inputs._fetch_fred_history_sync", lambda sid, days: _monthly(vals))
    out = econ_calendar._previous("CPIAUCSL", "yoy", "%")
    assert out["period"] == "2026-08-01"
    assert abs(out["value"] - ((118.0 / 108.0) * 100 - 100)) < 1e-3


def test_yoy_missing_base_returns_none(monkeypatch):
    vals = {"2026-07-01": 1.0, "2026-08-01": 2.0}
    monkeypatch.setattr("api.handlers.macro_inputs._fetch_fred_history_sync", lambda sid, days: _monthly(vals))
    assert econ_calendar._previous("CPIAUCSL", "yoy", "%") is None


def test_mom_and_levels(monkeypatch):
    vals = {"2026-07-01": 200.0, "2026-08-01": 202.0}
    monkeypatch.setattr("api.handlers.macro_inputs._fetch_fred_history_sync", lambda sid, days: _monthly(vals))
    assert econ_calendar._previous("RSAFS", "mom", "%")["text"] == "+1.0% m/m"
    claims = {"2026-09-19": 210000.0, "2026-09-26": 197000.0}
    monkeypatch.setattr("api.handlers.macro_inputs._fetch_fred_history_sync", lambda sid, days: _monthly(claims))
    assert econ_calendar._previous("ICSA", "level_k", "k")["text"] == "197k"


def test_calendar_shape(monkeypatch):
    monkeypatch.setattr(econ_calendar, "_dates", lambda rid, s, e: ["2099-01-15"] if rid == 10 else [])
    monkeypatch.setattr(econ_calendar, "_previous", lambda *a: {"text": "3.4% y/y", "period": "2098-12-01", "value": 3.4})
    from datetime import date
    cal = econ_calendar.build_calendar(today=date(2099, 1, 1))
    cpi = [r for r in cal["upcoming"] if r["release_id"] == 10]
    assert cpi and cpi[0]["previous"] == "3.4% y/y" and cpi[0]["time_et"] == "08:30"
    assert cal["events"][0]["event"] == "CPI Release"       # legacy name kept for event-vol
