"""CRED, PORT replays and helpers (offline: data stubbed)."""
import numpy as np
import pandas as pd
import pytest

from api.marketdata import research as R
from api.marketdata import core


def test_credit_percentiles_and_signals(monkeypatch):
    days = pd.date_range("2023-10-01", periods=700, freq="D")

    def fake(sid, years=4):
        base = np.linspace(4.0, 3.0, len(days)) if sid == "BAMLH0A0HYM2" else np.full(len(days), 1.0)
        if sid == "BAMLH0A3HYC":
            base = np.linspace(8, 12, len(days))
        if sid == "BAMLH0A1HYBB":
            base = np.full(len(days), 2.0)
        return {d.strftime("%Y-%m-%d"): float(v) for d, v in zip(days, base)}
    import api.marketdata.insights as ins
    monkeypatch.setattr(ins, "_fred", fake)
    core._cache.pop("cred", None)
    c = R.credit()
    hy = next(x for x in c["series"] if x["id"] == "BAMLH0A0HYM2")
    assert hy["last"] == pytest.approx(3.0) and hy["percentile"] == 0.0        # tightest of the window
    assert hy["chg_1m_bp"] < 0
    assert any("tight" in s for s in c["signals"])
    assert any("CCC" in s for s in c["signals"])                                 # distress premium at its widest
    core._cache.pop("cred", None)


def test_replays_use_episode_start_and_proxy_missing(monkeypatch):
    idx = pd.bdate_range("2008-08-01", "2024-12-31")
    spx = pd.Series(100.0, index=idx)
    spx[(idx >= "2020-02-19") & (idx <= "2020-03-23")] = np.linspace(100, 66, ((idx >= "2020-02-19") & (idx <= "2020-03-23")).sum())
    spx[idx > "2020-03-23"] = 66.0
    old = pd.Series(50.0, index=idx)
    old[idx > "2020-02-19"] = 40.0                                               # −20% in the Covid window
    young = pd.Series(10.0, index=idx[idx >= "2021-01-04"])                       # listed later → proxied
    monkeypatch.setattr(R, "_daily_closes", lambda syms, start: pd.DataFrame({"^GSPC": spx, "OLD": old, "NEW": young}))
    core._cache.pop("portlong:NEW,OLD", None)
    priced = [{"symbol": "OLD", "value_usd": 1000.0}, {"symbol": "NEW", "value_usd": 1000.0}]
    out = {r["episode"]: r for r in R._replays(priced, {"NEW": {"^GSPC": 0.5}})}
    cov = out["Covid crash"]
    assert cov["spx"] == pytest.approx(-0.34)
    assert cov["proxied"] == ["NEW"]
    # OLD −20%, NEW = 0.5 × −34% = −17% → portfolio −18.5%
    assert cov["return"] == pytest.approx((-0.20 - 0.17) / 2)
    core._cache.pop("portlong:NEW,OLD", None)


def test_8k_item_map():
    assert R.ITEMS_8K["2.02"].startswith("Results")
    assert "4.02" in R.RED_ITEMS and "5.02" in R.AMBER_ITEMS


def test_filing_text_only_opens_edgar():
    with pytest.raises(R.NotFound):
        R.filing_text("https://example.com/evil.htm")


def test_yahoo_guard_cools_down_and_fails_fast(monkeypatch):
    core._YH.update({"until": 0.0, "backoff": 15.0})
    calls = []

    def boom():
        calls.append(1)
        raise Exception("YFRateLimitError: Too Many Requests. Rate limited. Try after a while.")
    with pytest.raises(core.Upstream):
        core.yahoo_call(boom)
    assert core._YH["until"] > 0 and core._YH["backoff"] == 30.0
    import time as _t
    core._YH["until"] = _t.time() + core.YAHOO_WAIT_MAX + 30      # a long cool-down: fail fast, no request is sent
    with pytest.raises(core.Upstream, match="pausing"):
        core.yahoo_call(boom)
    assert len(calls) == 1
    slept = []                                                   # a short one is waited out, then the call runs
    monkeypatch.setattr(core.time, "sleep", lambda s: slept.append(s))
    core._YH["until"] = _t.time() + 5
    assert core.yahoo_call(lambda: 8) == 8 and slept and slept[0] <= 5.01
    core._YH.update({"until": 0.0, "backoff": 30.0})
    assert core.yahoo_call(lambda: 7) == 7 and core._YH["backoff"] == 15.0   # a success resets the back-off


def test_stale_value_served_when_provider_throttles():
    core._cache["t:stale"] = (0.0, {"x": 1})                   # expired entry
    import time
    core._cache["t:stale"] = (time.time() - 120, {"x": 1})
    out = core._cached("t:stale", 60, lambda: (_ for _ in ()).throw(core.Upstream("Too Many Requests")))
    assert out["x"] == 1 and out["stale"] is True
    core._cache.pop("t:stale", None)


def test_throttled_ticker_is_not_cached_as_empty(monkeypatch):
    from api.marketdata import security

    class FakeT:
        def __init__(self, s):
            pass

        @property
        def major_holders(self):
            raise Exception("YFRateLimitError: Too Many Requests. Rate limited.")

        institutional_holders = mutualfund_holders = insider_transactions = None
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", FakeT)
    core._YH.update({"until": 0.0, "backoff": 15.0})
    core._cache.pop("hds:ZZZ", None)
    with pytest.raises(core.Upstream):
        security.holders("ZZZ")
    assert "hds:ZZZ" not in core._cache                          # nothing empty stored for hours
    assert core._YH["until"] > 0                                  # and the shared cool-down is on
    core._YH.update({"until": 0.0, "backoff": 15.0})


def test_index_options_use_option_root():
    from api.marketdata import security
    assert security.OPTION_ROOT["^GSPC"] == "^SPX"
