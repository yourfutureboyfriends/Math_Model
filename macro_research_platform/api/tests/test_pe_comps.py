"""PE comparables and loan-market pricing: quartiles, the precedent book's rules, where a deal sits, and the TLB
spread taken from the loan market when it is available."""
import pytest

from api.pe import comps, market


def test_quartiles_by_hand():
    st = comps._quartiles([8, 10, 12, 14, 16])
    assert (st["low"], st["q1"], st["median"], st["q3"], st["high"], st["n"]) == (8, 10, 12, 14, 16, 5)
    assert comps._quartiles([]) is None
    assert comps._usable(12) and not comps._usable(81) and not comps._usable(-3) and not comps._usable(None)


@pytest.fixture
def book(tmp_path, monkeypatch):
    from api import funds
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: str(tmp_path / "fund.db"))
    comps._ready.clear()
    return tmp_path


def test_precedents_need_a_source_and_positive_ebitda(book):
    ok = {"date": "2025-06-30", "target": "Target A", "sector": "Food Processing", "ev": 1200, "ebitda": 100, "source": "8-K, 2025-06-30"}
    p = comps.add_precedent("pm", ok)
    assert p["ev_ebitda"] == pytest.approx(12.0)
    for bad in ({**ok, "source": " "}, {**ok, "ebitda": 0}, {**ok, "ev": -5}, {**ok, "date": "June"}, {**ok, "target": ""}):
        with pytest.raises(ValueError):
            comps.add_precedent("pm", bad)
    comps.delete_precedent(p["id"])
    assert comps.list_precedents() == []
    with pytest.raises(LookupError):
        comps.delete_precedent(p["id"])


def test_benchmark_places_the_deal_in_the_precedent_range(book, monkeypatch):
    for i, (ev, e) in enumerate([(800, 100), (1000, 100), (1200, 100), (1400, 100), (1600, 100)]):
        comps.add_precedent("pm", {"date": f"2024-0{i + 1}-01", "target": f"T{i}", "sector": "Food Processing", "ev": ev, "ebitda": e, "source": "press release"})
    comps.add_precedent("pm", {"date": "2024-07-01", "target": "Other", "sector": "Software", "ev": 3000, "ebitda": 100, "source": "10-K"})
    monkeypatch.setattr(comps, "trading", lambda s: {"industry": "Food Processing", "stats": comps._quartiles([9, 11, 13, 15]), "peers": []})
    b = comps.benchmark(17.6, 13.0, symbol="HSY")
    assert b["sector"] == "Food Processing" and b["precedent_stats"]["n"] == 5          # the software deal is filtered out
    assert b["precedent_stats"]["median"] == pytest.approx(12.0)
    assert b["entry"]["vs_precedents"] == "above the upper quartile"
    assert b["exit"]["vs_trading"] == "within the interquartile range"
    assert any("control premium" in n for n in b["notes"])


def test_tlb_spread_comes_from_the_loan_market_when_available():
    cr = {"base_rate": 0.04, "b_spread": 0.033, "bb_spread": 0.019, "treasury_5y": 0.048}
    loan = market.financing(100, 10, {**cr, "loan_spread": 0.038})
    bond = market.financing(100, 10, cr)
    assert loan["tranches"][0]["spread"] == pytest.approx(0.0375) and "loan-market" in loan["notes"]
    assert bond["tranches"][0]["spread"] == pytest.approx(0.0325) and "single-B bond" in bond["notes"]
    assert market.financing(100, 10, {**cr, "loan_spread": 0.01})["tranches"][0]["spread"] == pytest.approx(0.0275)  # floor


def test_loan_market_spread_arithmetic(monkeypatch):
    import pandas as pd
    import api.marketdata.core as core

    class T:
        def __init__(self, s):
            self.dividends = pd.Series([0.10, 0.10, 0.11, 0.12], index=pd.date_range("2026-07-01", periods=4, freq="MS"))
            self.info = {"regularMarketPrice": 20.0}
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", T)
    monkeypatch.setattr(core, "_cached", lambda key, ttl, fetch: fetch())
    out = market.loan_market(0.04)
    run_rate = (0.10 + 0.11 + 0.12) / 3 * 12 / 20.0
    assert out["spreads"]["BKLN"] == pytest.approx(run_rate + 0.0065 - 0.04)
    assert out["spread"] == pytest.approx(((run_rate + 0.0065 - 0.04) + (run_rate + 0.0070 - 0.04)) / 2)
