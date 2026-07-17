"""
Known-answer tests for event-driven volatility (Phase 6A).
Run: pytest api/tests/test_event_vol.py
"""
import numpy as np
from api.calculations.event_vol import realized_vol, event_window_vol


def test_realized_vol_matches_manual():
    closes = [100, 101, 102, 101, 103]
    rets = np.diff(closes) / np.array(closes[:-1])
    expected = round(float(np.std(rets, ddof=1)) * (252 ** 0.5), 4)
    assert realized_vol(closes) == expected


def test_realized_vol_insufficient():
    assert realized_vol([100]) is None


def _series(vols_by_day):
    # build dated closes from a list of daily returns
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(vols_by_day) + 1)]
    price = 100.0
    d = {dates[0]: price}
    for i, r in enumerate(vols_by_day):
        price *= (1 + r)
        d[dates[i + 1]] = price
    return d, dates


def test_event_window_detects_higher_vol():
    rng = np.random.default_rng(0)
    calm = list(rng.normal(0, 0.005, 60))     # 0.5% daily
    spike = list(rng.normal(0, 0.03, 7))      # 3% daily around the "event"
    rets = calm + spike + list(rng.normal(0, 0.005, 60))
    dated, dates = _series(rets)
    event_date = dates[60 + 3]                 # centre of the spike window
    res = event_window_vol(dated, [event_date], window=3)
    assert res["available"] is True
    assert res["event_vol"] > res["baseline_vol"]      # vol expands around the event
    assert res["expansion_pct"] > 0


def test_event_window_insufficient_history():
    res = event_window_vol({"2026-01-01": 100, "2026-01-02": 101}, ["2026-01-01"], window=3)
    assert res["available"] is False
