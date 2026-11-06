"""An absent curve or credit series must not read as a genuine "Neutral".

`get_regime_data` mapped missing z-scores through `_val`, which returned 0.0, and `_dir` then
labelled 0.0 "Neutral" with a neutral tone — visually identical to a real dead-centre reading, and
contradicting this module's own "Data honesty" contract that values are never fabricated.
`_z()` returns an empty Series whenever the panel lacks the column, and `rolling(36,
min_periods=24)` leaves NaN regardless, so this is reachable on any FRED rate-limit.

The same 0.0 flowed into `forecast_tracker.log_regime_forecast` through `scores.get(..., 0.0)`,
recording a fabricated score against a real prediction.
"""
import numpy as np
import pandas as pd
import pytest

from api import regime_data as rd


def _frame(*, curve, credit, months=30, g_z=0.5, i_z=0.1):
    """A monthly regime history shaped like _monthly_regime_frame's output."""
    idx = pd.date_range("2020-01-31", periods=months, freq="ME")
    return pd.DataFrame(
        {
            "regime": ["Goldilocks"] * months,
            "confidence": [0.8] * months,
            "g_z": [g_z] * months,
            "i_z": [i_z] * months,
            "curve_z": curve,
            "credit_z": credit,
        },
        index=idx,
    )


@pytest.fixture
def regime(monkeypatch):
    logged = {}

    class _Tracker:
        def log_regime_forecast(self, **kw):
            logged.update(kw)
            return 1

    monkeypatch.setattr(rd, "forecast_tracker", _Tracker())

    def _run(frame):
        monkeypatch.setattr(rd, "_monthly_regime_frame", lambda: frame)
        return rd.get_regime_data(), logged

    return _run


def _impact(data, factor):
    return next(i for i in data.interpretations if i["factor"] == factor)


def test_present_z_scores_still_read_directionally(regime):
    data, _ = regime(_frame(curve=[0.5] * 30, credit=[0.5] * 30))
    assert _impact(data, "Liquidity")["impact"] == "Easing"          # steeper curve = easier
    assert _impact(data, "Liquidity")["color"] == "success"
    assert _impact(data, "Risk")["impact"] == "Risk-Off"             # wider spreads = risk-off
    assert _impact(data, "Risk")["color"] == "danger"


def test_missing_z_scores_report_unavailable_not_neutral(regime):
    nan = [np.nan] * 30
    data, _ = regime(_frame(curve=nan, credit=nan))
    assert _impact(data, "Liquidity")["impact"] == "Unavailable"
    assert _impact(data, "Risk")["impact"] == "Unavailable"
    # the point of the fix: absent must be distinguishable from dead-centre
    assert _impact(data, "Liquidity")["impact"] != "Neutral"


def test_a_genuine_zero_still_reads_neutral(regime):
    # Guards against the fix collapsing every reading into "Unavailable".
    data, _ = regime(_frame(curve=[0.0] * 30, credit=[0.0] * 30))
    assert _impact(data, "Liquidity")["impact"] == "Neutral"
    assert _impact(data, "Risk")["impact"] == "Neutral"


def test_one_missing_series_does_not_take_the_other_with_it(regime):
    data, _ = regime(_frame(curve=[0.5] * 30, credit=[np.nan] * 30))
    assert _impact(data, "Liquidity")["impact"] == "Easing"
    assert _impact(data, "Risk")["impact"] == "Unavailable"


def test_forecast_is_logged_with_real_scores(regime):
    _, logged = regime(_frame(curve=[0.5] * 30, credit=[0.5] * 30, g_z=0.7, i_z=0.3))
    assert logged["growth_score"] == pytest.approx(0.7)
    assert logged["inflation_score"] == pytest.approx(0.3)


def test_forecast_is_not_logged_when_its_inputs_are_missing(regime):
    frame = _frame(curve=[0.5] * 30, credit=[0.5] * 30)
    frame["g_z"] = np.nan
    _, logged = regime(frame)
    assert logged == {}, "a forecast built on a missing score must not be recorded as 0.0"
