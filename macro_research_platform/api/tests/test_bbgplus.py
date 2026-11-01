"""IMOV / TRA / VAP: contributions add up to the index move, period returns use the right base, the volume profile
puts the point of control where the volume traded."""
import numpy as np
import pandas as pd
import pytest

from api.marketdata import bbgplus


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(bbgplus, "_cached", lambda key, ttl, fn: fn())


def test_index_movers_contributions_sum_to_the_weighted_move(monkeypatch):
    from api.marketdata import funds
    monkeypatch.setattr(funds, "index_members", lambda code: {
        "name": "Test 3", "source": "test", "note": None,
        "members": [{"symbol": "AAA", "name": "A", "sector": "Tech", "weight": 0.5},
                    {"symbol": "BRK.B", "name": "B", "sector": "Fin", "weight": 0.3},
                    {"symbol": "CCC", "name": "C", "sector": "Tech", "weight": 0.2}]})
    idx = pd.date_range("2026-10-29", periods=2)
    closes = pd.DataFrame({"AAA": [100, 110], "BRK-B": [50, 45], "CCC": [10, 10], "^GSPC": [1000, 1020]}, index=idx)
    seen = {}
    monkeypatch.setattr(bbgplus, "_store_closes", lambda syms, idx: None)   # the Yahoo path
    monkeypatch.setattr(bbgplus, "_closes", lambda syms, period, adjusted: seen.setdefault("syms", syms) and closes)
    r = bbgplus.index_movers("spx")
    assert "BRK-B" in seen["syms"]                                   # Yahoo's spelling of class shares
    by = {x["symbol"]: x for x in r["leaders"]}
    assert by["AAA"]["contrib_bps"] == pytest.approx(500)            # 0.5 × +10%
    assert by["BRK.B"]["contrib_bps"] == pytest.approx(-300)         # 0.3 × −10%
    assert r["implied_bps"] == pytest.approx(200) and r["change_bps"] == pytest.approx(200)
    assert by["AAA"]["contrib_pts"] == pytest.approx(50)             # 5% of the prior level 1000
    assert r["leaders"][0]["symbol"] == "AAA" and r["laggards"][0]["symbol"] == "BRK.B"
    assert (r["advancers"], r["decliners"]) == (1, 1)
    assert r["sectors"][0] == {"sector": "Tech", "contrib_bps": pytest.approx(500)}


def test_index_movers_rejects_indices_without_weights():
    with pytest.raises(bbgplus.NotFound):
        bbgplus.index_movers("RUT")


def test_period_returns_use_the_close_before_each_period_and_annualise_long_ones():
    idx = pd.bdate_range("2020-01-01", "2026-10-30")
    s = pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    today = idx[-1]
    r = bbgplus._period_returns(s, today)
    ytd_base = s[s.index <= pd.Timestamp("2025-12-31")].iloc[-1]
    assert r["YTD"] == pytest.approx(200 / ytd_base - 1)
    five = s[s.index <= today - pd.DateOffset(years=5)].iloc[-1]
    assert r["5Y"] == pytest.approx((200 / five) ** (1 / 5) - 1)
    short = bbgplus._period_returns(s.iloc[-300:], today)
    assert short["3Y"] is None and short["5Y"] is None               # history doesn't reach back: no number, not a wrong one


def test_volume_profile_centres_on_where_volume_traded(monkeypatch):
    idx = pd.bdate_range("2026-01-01", periods=60)
    high = np.full(60, 102.0); low = np.full(60, 98.0); vol = np.full(60, 1e6)
    high[:5], low[:5], vol[:5] = 120.0, 110.0, 1e4                    # a light excursion higher
    df = pd.DataFrame({"Open": 100.0, "High": high, "Low": low, "Close": 100.0, "Volume": vol}, index=idx)
    from api.marketdata import toolkit
    monkeypatch.setattr(toolkit, "_history", lambda sym, period: df)
    r = bbgplus.volume_at_price("tst", days=60, bins=22)
    assert 98 <= r["poc"] <= 102
    assert r["value_low"] >= 97 and r["value_high"] <= 103
    assert r["position"] == "inside value"
    assert sum(b["share"] for b in r["bins"]) == pytest.approx(1)


def test_index_movers_prefers_the_local_store_when_it_is_current(monkeypatch):
    from api.marketdata import funds
    monkeypatch.setattr(funds, "index_members", lambda code: {"name": "T", "source": "t", "note": None,
        "members": [{"symbol": "AAA", "sector": "Tech", "weight": 1.0}]})
    idx = pd.date_range("2026-10-29", periods=2)
    monkeypatch.setattr(bbgplus, "_store_closes", lambda syms, i: pd.DataFrame({"AAA": [10, 11], "^NDX": [100, 110]}, index=idx))
    monkeypatch.setattr(bbgplus, "_closes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded anyway")))
    assert bbgplus.index_movers("NDX")["implied_bps"] == pytest.approx(1000)
