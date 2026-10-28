"""Benzinga and FMP providers: parsing, guidance direction, FMP's US-only rule and daily budget, the news hub merge and the
earnings-calendar fallback when Yahoo is unavailable."""
from datetime import date

import pytest

from api.providers import benzinga as bz, fmp


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    import api.marketdata.core as core
    monkeypatch.setattr(core, "_cached", lambda key, ttl, fn: fn())


def test_benzinga_ratings_parse_and_order(monkeypatch):
    monkeypatch.setattr(bz, "api_key", lambda: "k")
    rows = {"ratings": [
        {"date": "2026-10-12", "time": "08:00:00", "ticker": "AAPL", "name": "Apple", "analyst": "JP Morgan", "analyst_name": "Samik Chatterjee",
         "action_company": "Maintains", "rating_current": "Overweight", "rating_prior": "Overweight", "adjusted_pt_current": "360", "adjusted_pt_prior": "340", "importance": "5"},
        {"date": "2026-10-20", "time": "07:00:00", "ticker": "AAPL", "name": "Apple", "analyst": "Loop Capital", "analyst_name": "Ananda Baruah",
         "action_company": "Downgrades", "rating_current": "Hold", "rating_prior": "Buy", "adjusted_pt_current": "330", "adjusted_pt_prior": "370", "importance": "5"}]}
    monkeypatch.setattr(bz, "_get", lambda path, params, ttl: rows)
    r = bz.ratings("aapl")
    assert [x["firm"] for x in r] == ["Loop Capital", "JP Morgan"]                        # newest first
    assert r[0]["analyst"] == "Ananda Baruah" and r[0]["pt_change"] == pytest.approx(330 / 370 - 1)


@pytest.mark.parametrize("prior,new,want", [(("3.27", "3.30"), ("3.33", ""), "raised"), (("5.10", "5.20"), ("4.90", "5.00"), "lowered"),
                                            (("", ""), ("17.6", "17.9"), "initiated"), (("1.00", "1.10"), ("1.00", "1.10"), "maintained")])
def test_guidance_direction(monkeypatch, prior, new, want):
    monkeypatch.setattr(bz, "api_key", lambda: "k")
    g = {"guidance": [{"date": "2026-10-27", "ticker": "X", "name": "X", "eps_guidance_prior_min": prior[0], "eps_guidance_prior_max": prior[1],
                       "eps_guidance_min": new[0], "eps_guidance_max": new[1]}]}
    monkeypatch.setattr(bz, "_get", lambda path, params, ttl: g)
    assert bz.guidance()[0]["direction"] == want


def test_fmp_is_us_only_and_guards_its_daily_budget(monkeypatch):
    monkeypatch.setattr(fmp, "api_key", lambda: "k")
    with pytest.raises(fmp.FmpError, match="US listings only"):
        fmp.analyst_view("HSBA.L")
    monkeypatch.setattr(fmp, "_used", {"day": date.today(), "n": fmp.DAILY_BUDGET})
    with pytest.raises(fmp.FmpError, match="allowance"):
        fmp._spend()


def test_earnings_calendar_falls_back_to_fmp_when_yahoo_fails(monkeypatch):
    import yfinance as yf
    from api.marketdata import monitors

    class Broken:
        def get_earnings_calendar(self, **k):
            raise RuntimeError("Too Many Requests")
    monkeypatch.setattr(yf, "Calendars", lambda: Broken())
    monkeypatch.setattr(fmp, "available", lambda: True)
    monkeypatch.setattr(fmp, "earnings_calendar", lambda s, d: [{"symbol": "AMD", "date": "2026-11-03", "eps_estimate": 1.94, "eps_reported": None,
                                                                 "revenue_estimate": 1.3e10, "revenue_reported": None}])
    r = monitors.earnings_calendar("2026-10-28", 7)
    assert r["rows"][0]["symbol"] == "AMD" and r["rows"][0]["revenue_estimate"] == 1.3e10 and "Financial Modeling Prep" in r["source"]
