"""IMOV / TRA / VAP: contributions add up to the index move, period returns use the right base, the volume profile
puts the point of control where the volume traded."""
from datetime import date

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


def test_member_returns_ranks_members_and_counts_those_beating_the_index(monkeypatch):
    from api.marketdata import funds
    monkeypatch.setattr(funds, "index_members", lambda code: {"name": "FTSE 100", "source": "test", "note": None,
        "members": [{"symbol": "AAA.L", "sector": "Tech"}, {"symbol": "BBB.L", "sector": "Banks"}, {"symbol": "CCC.L", "sector": "Tech"}]})
    idx = pd.bdate_range("2025-01-01", "2026-10-30")
    lin = lambda a, b: np.linspace(a, b, len(idx))
    closes = pd.DataFrame({"AAA.L": lin(100, 150), "BBB.L": lin(100, 90), "CCC.L": lin(100, 120), "^FTSE": lin(100, 110)}, index=idx)
    monkeypatch.setattr(bbgplus, "_closes", lambda syms, period, adjusted: closes)
    r = bbgplus.member_returns("UKX", "1Y")
    assert [x["symbol"] for x in r["rows"]] == ["AAA.L", "CCC.L", "BBB.L"] and r["rows"][0]["rank"] == 1
    assert r["beat_index"] == 2 and r["positive"] == 2
    one_year = closes.loc[closes.index <= pd.Timestamp("2025-10-30")].iloc[-1]
    assert r["rows"][0]["1Y"] == pytest.approx(150 / one_year["AAA.L"] - 1)
    assert r["sectors"][0]["sector"] == "Tech"
    with pytest.raises(bbgplus.NotFound):
        bbgplus.member_returns("UKX", "2Y")


def test_pe_history_restates_filed_eps_for_later_splits(monkeypatch):
    from api.marketdata import corporate, extras
    from api.providers import sec_edgar
    monkeypatch.setattr(extras, "_company_only", lambda s, w: None)
    monkeypatch.setattr(sec_edgar, "resolve", lambda s: {"cik": 1})
    # EPS 8 filed before a 4-for-1 split is 2 on today's share count; EPS 2.5 is filed after it
    filed = [(str(d.date()), 8.0) for d in pd.date_range("2020-02-01", "2023-11-01", freq="QS")] + [("2024-02-01", 2.5)]
    monkeypatch.setattr(sec_edgar, "pit_events", lambda s: {"eps_ttm": filed})
    monkeypatch.setattr(corporate, "actions", lambda s: {"splits": [{"date": "2023-12-15", "ratio": 4.0}]})
    idx = pd.bdate_range("2020-03-01", "2024-06-28")
    monkeypatch.setattr(bbgplus, "_closes", lambda syms, period, adjusted: pd.DataFrame({"TST": np.full(len(idx), 40.0)}, index=idx))
    r = bbgplus.pe_history("TST", years=4)
    pes = {p["date"]: p["pe"] for p in r["points"]}
    assert pes["2022-06-03"] == pytest.approx(20.0)                  # 40 / (8 / 4)
    assert r["pe"] == pytest.approx(16.0) and r["eps_ttm"] == pytest.approx(2.5)
    assert r["band_prices"]["mean"] == pytest.approx(r["bands"]["mean"] * 2.5)


def test_world_bonds_spreads_policy_and_real_yield(monkeypatch):
    from api.marketdata import countries, curves, toolkit
    today = str(date.today())
    monkeypatch.setattr(countries, "world_data", lambda: {"countries": {
        "US": {"name": "United States", "region": "americas", "yield_10y": 4.0, "yield_date": today, "yield_source": "^TNX live", "inflation": 3.0},
        "DE": {"name": "Germany", "region": "europe", "yield_10y": 2.5, "yield_date": today, "yield_source": "Bundesbank", "inflation": 2.0},
        "IT": {"name": "Italy", "region": "europe", "yield_10y": 3.6, "yield_date": today, "yield_source": "live", "inflation": 1.5},
        "NZ": {"name": "New Zealand", "region": "apac", "yield_10y": 4.4, "yield_date": "2025-01-31", "yield_source": "OECD monthly average"},
        "XX": {"name": "No yield"}}})
    monkeypatch.setattr(curves, "curves", lambda: {"curves": {"US": {"points": [{"tenor": 2.0, "yield": 3.5}], "slope_2s10s_bp": 50.0}}})
    monkeypatch.setattr(toolkit, "central_banks", lambda: {"banks": [{"code": "US", "rate": 3.75}, {"code": "XM", "rate": 2.0}]})
    r = bbgplus.world_bonds()
    by = {x["iso"]: x for x in r["rows"]}
    assert set(by) == {"US", "DE", "IT", "NZ"}
    assert by["IT"]["spread_de_bp"] == pytest.approx(110) and by["IT"]["spread_us_bp"] == pytest.approx(-40)
    assert by["IT"]["policy_rate"] == 2.0 and by["IT"]["real_yield"] == pytest.approx(2.1)   # euro members use the ECB rate
    assert by["US"]["yield_2y"] == 3.5 and by["US"]["term_spread_bp"] == pytest.approx(25)
    assert by["NZ"]["stale"] and not by["NZ"]["daily"] and by["US"]["daily"]
    assert r["rows"][0]["iso"] == "NZ"                                # highest yield first


def test_filing_search_ranks_the_passage_that_answers(monkeypatch):
    docs = [{"form": "10-K", "filed": "2026-02-01", "period": "2025-12-31", "url": "u1", "passages": [
                {"section": "Item 1A. Risk Factors", "part": "main", "text": "Tariffs on imports from China could raise our costs. " * 3},
                {"section": "Item 5. Market for Registrant's Common Equity", "part": "main",
                 "text": "In May the Board approved a new share repurchase program of up to $10 billion. " * 2},
                {"section": "Item 8.", "part": "main", "text": "Total 1,234 5,678 9,012 share 3,456 7,890 1,111 2,222 3,333 4,444 5,555"}]},
            {"form": "8-K", "filed": "2026-04-30", "period": None, "url": "u2", "passages": [
                {"section": None, "part": "ex99.htm", "text": "Revenue grew 12% and the company repurchased shares worth $2 billion in the quarter."}]}]
    monkeypatch.setattr(bbgplus, "_cached", lambda key, ttl, fn: docs if key.startswith("ds:") else fn())
    r = bbgplus.filing_search("TST", "share repurchase program")
    assert r["hits"][0]["section"].startswith("Item 5") and r["matches"] == 3       # the 8-K's "repurchased shares" counts
    assert r["hits"][-1]["section"] == "Item 8."                      # a table of figures ranks last
    assert [h["form"] for h in bbgplus.filing_search("TST", "repurchase", forms="8-K")["hits"]] == ["8-K"]
    with pytest.raises(bbgplus.NotFound):
        bbgplus.filing_search("TST", "the of and")


def test_passages_follow_filing_sections():
    text = "Item 1A. Risk Factors\n" + "\n".join(["Risk sentence number one is here and is long enough."] * 30) + "\nItem 7. Management's Discussion\nRevenue rose."
    ps = bbgplus._passages(text, size=300)
    assert ps[0]["section"] == "Item 1A. Risk Factors" and all(len(p["text"]) <= 600 for p in ps)
