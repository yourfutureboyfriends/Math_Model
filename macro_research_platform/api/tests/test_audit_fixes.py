"""Fixes found by the accuracy audit (scripts/audit_accuracy.py):
- ETF premium paired a same-day NAV with the previous day's close after the market shut (SMH +744bp on a −7% day).
- SEC facts and point-in-time EPS waited out a 3-day cache while a new 10-Q was already filed (MSFT a quarter behind)."""
import json
import time
import types

import pytest

from api.marketdata import etfarb


def _info(state, prev, last, nav):
    return {"navPrice": nav, "previousClose": prev, "regularMarketPrice": last, "marketState": state, "shortName": "Fund",
            "regularMarketTime": 1793390400}


def test_etf_premium_pairs_nav_with_its_own_close_after_the_session(monkeypatch):
    import yfinance as yf
    monkeypatch.setattr(etfarb, "yahoo_call", lambda fn: fn())
    monkeypatch.setattr(yf, "Ticker", lambda s: types.SimpleNamespace(info=_info("CLOSED", 561.67, 522.49, 522.76)))
    r = etfarb._one("SMH")
    assert r["close_basis"] == "latest close" and r["premium_bp"] == pytest.approx(-5.2, abs=0.1)
    # during the session the NAV is yesterday's: keep the previous close
    monkeypatch.setattr(yf, "Ticker", lambda s: types.SimpleNamespace(info=_info("REGULAR", 561.67, 522.49, 561.60)))
    r = etfarb._one("SMH")
    assert r["close_basis"] == "previous close" and r["premium_bp"] == pytest.approx(1.2, abs=0.1)


def test_point_in_time_eps_refreshes_when_a_newer_filing_exists(tmp_path, monkeypatch):
    from api.providers import sec_edgar as se
    monkeypatch.setattr(se, "CACHE", tmp_path)
    path = tmp_path / "pit" / "TST.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"eps_ttm": [["2026-07-29", 17.96]]}))
    monkeypatch.setattr(se, "resolve", lambda t: {"cik": 1})
    monkeypatch.setattr(se, "_pit_events", lambda t: {"eps_ttm": [("2026-07-29", 17.96), ("2026-10-28", 19.16)]})
    monkeypatch.setattr(se, "latest_periodic_live", lambda cik: "2026-10-28")
    assert se.pit_events("TST")["eps_ttm"][-1] == ("2026-10-28", 19.16)        # cache was fresh by age, stale by filing
    monkeypatch.setattr(se, "_pit_events", lambda t: pytest.fail("refetched although current"))
    assert se.pit_events("TST")["eps_ttm"][-1][1] == 19.16                      # now current: served from cache


def test_live_filing_check_is_cached(monkeypatch):
    from api.providers import sec_edgar as se
    calls = []
    monkeypatch.setattr(se, "_get", lambda url: calls.append(url) or {"filings": {"recent": {"form": ["8-K", "10-Q"], "filingDate": ["2026-10-30", "2026-10-28"]}}})
    se._live_latest.clear()
    assert se.latest_periodic_live(42) == "2026-10-28" and se.latest_periodic_live(42) == "2026-10-28"
    assert len(calls) == 1
