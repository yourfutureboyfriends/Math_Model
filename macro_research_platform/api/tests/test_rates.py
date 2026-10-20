"""Rate service: as-of availability (never a later observation), one day-count convention."""
import pandas as pd
import pytest

from api.quant import rates


@pytest.fixture()
def irx(monkeypatch):
    s = pd.Series([2.0, 4.0, 5.0], index=pd.to_datetime(["2020-01-02", "2020-06-01", "2021-01-04"]))
    monkeypatch.setattr(rates, "_irx", lambda: s)
    return s


def test_daily_uses_latest_observation_on_or_before(irx):
    d = rates.daily(["2019-12-31", "2020-01-02", "2020-05-29", "2020-06-01", "2022-01-03"])
    assert d.iloc[0] == 0.0                                      # before the series: no rate, not a future one
    assert d.iloc[1] == pytest.approx(0.02 / 252)
    assert d.iloc[2] == pytest.approx(0.02 / 252)                # 4% is not known until 1 June
    assert d.iloc[3] == pytest.approx(0.04 / 252)
    assert d.iloc[4] == pytest.approx(0.05 / 252)


def test_annual_never_borrows_a_later_value(irx):
    assert rates.annual("2020-02-01", "2020-03-01") == pytest.approx(0.02)       # as-of start, not the June print
    assert rates.annual("2019-01-01", "2019-06-01") == 0.0                        # nothing known yet


def test_accrue_matches_daily_convention(irx):
    a = rates.accrue(1000.0, "2020-06-01", "2020-06-08")                          # 5 sessions after 1 June
    assert a == pytest.approx(1000 * 5 * 0.04 / 252)
    assert rates.accrue(1000.0, "2020-06-01", "2020-06-08", cash_spread=0.01) == pytest.approx(1000 * 5 * 0.03 / 252)
    assert rates.accrue(-1000.0, "2020-06-01", "2020-06-08", borrow_spread=0.01) == pytest.approx(-1000 * 5 * 0.05 / 252)
