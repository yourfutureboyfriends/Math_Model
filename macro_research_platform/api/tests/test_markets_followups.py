"""Follow-up Markets fixes: captive-finance EV multiples, the Yahoo request throttle, regulator short positions
(UK FCA, Hong Kong SFC), non-SEC filing links, live 10-year yields and fund-asset currencies."""
import io

import pandas as pd
import pytest

from api.marketdata import core, security


def _info(**kw):
    base = {"currency": "JPY", "financialCurrency": "JPY", "marketCap": 36e12, "netIncomeToCommon": 4e12, "totalRevenue": 50e12,
            "ebitda": 7e12, "totalDebt": 38e12, "totalCash": 9e12, "sharesOutstanding": 13e9, "bookValue": 3200.0,
            "trailingEps": 300.0, "forwardEps": 320.0, "industry": "Auto Manufacturers"}
    base.update(kw)
    return base


def test_ev_ebitda_is_not_meaningful_with_a_captive_finance_arm():
    m = security.peer_multiples(_info())
    assert m["captive_finance"] and m["ev_ebitda"] is None and m["pe"] is not None
    plain = security.peer_multiples(_info(industry="Software—Application", totalDebt=1e12))
    assert not plain["captive_finance"] and plain["ev_ebitda"] is not None


def test_every_yfinance_request_goes_through_the_throttle():
    from yfinance import data
    assert getattr(data.YfData._make_request, "_throttled", False)
    assert core.YAHOO_HTTP_CONCURRENCY <= 10 and core.YAHOO_RATE > 0
    core._YH_BUCKET.update(tokens=0.0, at=__import__("time").time())       # empty bucket: the next request waits ~1/rate
    assert 0 < core._take_token() <= 2 / core.YAHOO_RATE


def test_uk_aggregate_short_position(monkeypatch):
    from api.marketdata import shorts_intl as si
    cur = "Name of Company,ISIN,Aggregated net short position (%),Position date\nSHELL PLC,GB00BP6MXD84,1.18,05/10/2026\n"
    hist = ("Name of Company,ISIN,Aggregated net short position (%),Position date,Became historical\n"
            "SHELL PLC,GB00BP6MXD84,1.05,01/09/2026,05/10/2026\n")
    class R:
        def __init__(self, t): self.status_code, self.content, self.text = 200, t.encode(), t
    monkeypatch.setattr(si, "_get", lambda url, timeout=40: R(cur if "current" in url else hist))
    monkeypatch.setattr(si, "_cached", lambda k, ttl, fn: fn())
    monkeypatch.setattr(si, "_info", lambda s: {"longName": "Shell plc"})
    r = si.short_positions("SHEL.L")
    assert r["market"] == "UK" and r["aggregate_pct"] == pytest.approx(0.0118) and r["as_of"] == "2026-10-05"
    assert [p["date"] for p in r["history"]] == ["2026-09-01", "2026-10-05"]


def test_hk_short_position_as_share_of_outstanding(monkeypatch):
    from api.marketdata import shorts_intl as si
    df = pd.read_csv(io.StringIO("Date,Stock Code,Stock Name,Shares,HKD\n16/10/2026,700,TENCENT,76657027,32027305881\n"))
    monkeypatch.setattr(si, "_hk_files", lambda weeks=26: [df.copy()])
    monkeypatch.setattr(si, "_info", lambda s: {"longName": "Tencent", "sharesOutstanding": 9.0e9})
    r = si.short_positions("0700.HK")
    assert r["market"] == "HK" and r["aggregate_pct"] == pytest.approx(76657027 / 9.0e9) and r["as_of"] == "2026-10-16"


def test_non_sec_companies_get_their_regulators_filing_services(monkeypatch):
    from api.marketdata import research
    monkeypatch.setattr(research, "_info", lambda s: {"longName": "Toyota Motor Corporation", "website": "https://global.toyota"})
    r = research._non_sec_filings("7203.T")
    labels = " ".join(l["label"] for l in r["external_filings"])
    assert "EDINET" in labels and "TDnet" in labels and r["filings"] == []


def test_live_yields_require_a_percent_quote_and_agree_with_the_monthly(monkeypatch):
    from api.marketdata import countries
    quotes = [{"symbol": "FR10Y-FR", "code": 0, "last": "4.9113%", "previous_day_closing": "4.9079%", "last_time": "2026-10-27T17:32"},
              {"symbol": "SG10Y-SG", "code": 0, "last": "0.51", "previous_day_closing": "0.51"},
              {"symbol": "IT10Y-IT", "code": 0, "last": "9.9%", "previous_day_closing": "9.9%"}]
    class R:
        def json(self): return {"FormattedQuoteResult": {"FormattedQuote": quotes}}
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    out = countries._live_yields({"FR": {"yield_10y": 4.48, "yield_change_1y_bp": 50.0}, "IT": {"yield_10y": 3.99}})
    assert out["FR"]["yield_10y"] == pytest.approx(4.9113) and out["FR"]["yield_change_1d_bp"] == pytest.approx(0.3, abs=0.05)
    assert "SG" not in out and "IT" not in out          # not a yield quote / 5.9 points from the monthly average
