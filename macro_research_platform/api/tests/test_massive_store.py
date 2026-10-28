"""Massive daily-bars store: files per day, holidays remembered, split adjustment on read (effective splits only),
Yahoo-style ticker mapping, and the heat map's date alignment of live quotes against stored closes."""
from datetime import date

import pandas as pd
import pytest

from api.providers import massive


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(massive, "STORE", tmp_path / "grouped")
    monkeypatch.setattr(massive, "SPLITS_FILE", tmp_path / "splits.json")
    return tmp_path


def _resp(results):
    return {"results": results, "resultsCount": len(results), "status": "OK"}


def test_days_are_stored_once_and_holidays_remembered(store, monkeypatch):
    calls = []

    def fake_get(path, params=None, retries=3):
        calls.append(path)
        if "2026-10-12" in path:
            return _resp([])                                       # a holiday
        return _resp([{"T": "AAPL", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10}, {"T": "BRK.B", "o": 1, "h": 1, "l": 1, "c": 500, "v": 5}])
    monkeypatch.setattr(massive, "_get", fake_get)
    assert len(massive.fetch_day(date(2026, 10, 13))) == 2
    massive.fetch_day(date(2026, 10, 13))
    assert massive.fetch_day(date(2026, 10, 12)) is None
    massive.fetch_day(date(2026, 10, 12))
    assert len(calls) == 2                                          # neither day requested twice
    assert massive.stored_days() == [date(2026, 10, 13)]           # the holiday is not a trading day
    assert date(2026, 10, 12) not in massive.missing_days(30) and date(2026, 10, 13) not in massive.missing_days(30)


def test_panel_maps_tickers_and_applies_only_effective_splits(store, monkeypatch):
    days = {date(2026, 10, 1): 400.0, date(2026, 10, 2): 410.0, date(2026, 10, 5): 102.0}   # a 4-for-1 split on 5 Oct
    for d, c in days.items():
        monkeypatch.setattr(massive, "_get", lambda path, params=None, retries=3, c=c: _resp([{"T": "BRK.B", "o": c, "h": c, "l": c, "c": c, "v": 1}]))
        massive.fetch_day(d)
    import json
    massive.SPLITS_FILE.write_text(json.dumps([{"ticker": "BRK.B", "date": "2026-10-05", "ratio": 4.0},
                                               {"ticker": "BRK.B", "date": "2027-01-15", "ratio": 2.0}]))   # announced, not yet effective
    px = massive.panel(["BRK-B"], days=10)
    assert list(px.columns) == ["BRK-B"]
    assert px["BRK-B"].tolist() == pytest.approx([100.0, 102.5, 102.0])


def test_no_key_means_not_available(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.setattr(massive, "api_key", lambda: None)
    assert not massive.available() and massive.start_backfill() is False
