"""BIFS benchmark: 50% MSCI World + 50% MSCI World Equal Weighted in GBP, from ETF proxies, rebalanced daily."""
import numpy as np
import pandas as pd
import pytest

from api.calculations import benchmark as bm
from api.calculations import fx_accounting as fa

DAYS = pd.bdate_range("2024-08-26", periods=60)


@pytest.fixture()
def legs(monkeypatch):
    world = pd.Series(10000.0 * np.cumprod(np.r_[1, np.full(59, 1.001)]), index=DAYS)      # GBp, +0.1%/day
    ew = pd.Series(5.0 * np.cumprod(np.r_[1, np.full(49, 1.002)]), index=DAYS[10:])           # USD, launches later
    world.attrs["currency"], ew.attrs["currency"] = "GBp", "USD"
    data = {"SWDA.L": world, "MWEQ.L": ew}
    monkeypatch.setattr(bm, "_closes_local", lambda s: data[s])
    usd_per_gbp = pd.Series(np.linspace(1.25, 1.30, 60), index=DAYS)        # sterling strengthens: USD assets lose
    monkeypatch.setattr(fa, "_major_usd_series", lambda major: usd_per_gbp if major == "GBP" else None)
    return data, usd_per_gbp


def test_legs_convert_to_gbp(legs):
    data, gbp = legs
    w = bm.in_base("SWDA.L", "GBP")
    assert w.iloc[0] == pytest.approx(100.0)                                # pence → pounds, no FX
    e = bm.in_base("MWEQ.L", "GBP")
    assert e.iloc[0] == pytest.approx(5.0 / gbp.loc[DAYS[10]])                # USD → GBP at that day's rate


def test_blend_is_daily_rebalanced_and_starts_with_both_legs(legs):
    data, gbp = legs
    s = bm.series("BIFS", "GBP")
    r = s["returns"]
    assert str(r.index[0].date()) == str(DAYS[11].date())                     # first full day of the equal-weight leg
    ew_gbp = (data["MWEQ.L"] / gbp.reindex(data["MWEQ.L"].index)).pct_change()
    expected = 0.5 * 0.001 + 0.5 * ew_gbp.loc[r.index[5]]
    assert r.iloc[5] == pytest.approx(expected, rel=1e-9)
    summ = bm.summary("BIFS", "GBP")
    assert summ["start"] == str(DAYS[11].date()) and any("Sep 2024" in x for x in summ["limitations"])


def test_unknown_benchmark_is_refused():
    with pytest.raises(KeyError):
        bm.series("NOPE", "GBP")
