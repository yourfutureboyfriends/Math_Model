"""Markets audit (Oct 2026): FX day-changes and levels checked against ECB fixings, the surprise index on same-vintage
changes, dividend units for minor-unit listings, stale central-bank series, and quote stitching for lagging histories."""
import pandas as pd
import pytest

from api.marketdata import core

FIX = {"2026-10-23": {"USD": 1.0, "EUR": 0.89342, "BRL": 5.0465, "JPY": 157.0},
       "2026-10-26": {"USD": 1.0, "EUR": 0.89381, "BRL": 5.5884, "JPY": 157.45}}


@pytest.fixture
def ecb(monkeypatch):
    monkeypatch.setattr(core, "ecb_fixings", lambda days=14: FIX)


def _bars(vals, end="2026-10-27"):
    return pd.Series(vals, index=pd.bdate_range(end=end, periods=len(vals)))


def test_fx_previous_close_is_the_prior_ecb_fixing_not_a_stale_bar(ecb):
    # Yahoo's Monday bar for USD/BRL was 4.96 (stale) while the market traded 5.40–5.59
    last, prev, basis = core.fx_last_prev("BRL=X", _bars([5.0499, 4.9602, 5.3361]))
    assert prev == pytest.approx(5.5884) and "2026-10-26" in basis
    assert last / prev - 1 == pytest.approx(5.3361 / 5.5884 - 1)
    # USD per EUR, and a cross
    last, prev, _ = core.fx_last_prev("EURUSD=X", _bars([1.12, 1.1215, 1.1148]))
    assert prev == pytest.approx(1 / 0.89381)
    _, prev, _ = core.fx_last_prev("EURJPY=X", _bars([175.5, 176.0, 175.8]))
    assert prev == pytest.approx(157.45 / 0.89381)
    assert core.fx_last_prev("AAPL", _bars([1, 2])) is None


def test_fx_levels_far_from_the_fixing_are_replaced(ecb):
    assert core.fx_checked("BRL", 5.336)[0] == 5.336                   # a real 4.5% move is kept
    v, note = core.fx_checked("BRL", 4.90)                             # 12% off: a bad tick
    assert v == pytest.approx(5.5884) and "ECB fixing" in note
    assert core.fx_checked("EUR", 0.8969) == (0.8969, None)


def test_surprise_changes_use_the_prior_period_from_the_same_release(monkeypatch):
    from api.providers import alfred
    # Aug first printed 773,947; the Sep release revised Aug to 739,322 and printed Sep at 745,021 (+0.77%)
    rows = [{"date": "2026-08-01", "realtime_start": "2026-09-16", "realtime_end": "2026-10-14", "value": "773947"},
            {"date": "2026-08-01", "realtime_start": "2026-10-15", "realtime_end": "9999-12-31", "value": "739322"},
            {"date": "2026-09-01", "realtime_start": "2026-10-15", "realtime_end": "9999-12-31", "value": "745021"}]
    monkeypatch.setattr(alfred, "_fetch", lambda params, name: rows)
    ch = alfred.first_release_changes("RSAFS", start="2026-01-01")
    sep = ch[-1]
    assert sep["prev"] == 739322 and (sep["value"] / sep["prev"] - 1) * 100 == pytest.approx(0.771, abs=1e-3)


def test_stale_central_bank_series_are_left_out():
    from api.marketdata import toolkit
    assert toolkit.CB_STALE_DAYS <= 180 and toolkit.CB_NAMES["KW"][1] == "Central Bank of Kuwait"


def test_lagging_history_is_stitched_to_the_quote(monkeypatch):
    from api.marketdata import toolkit
    import api.marketdata.core as c
    df = pd.DataFrame({"Open": [1.0, 1.0], "High": [1.0, 1.0], "Low": [1.0, 1.0], "Close": [3117.0, 3117.0], "Volume": [1, 1]},
                      index=pd.to_datetime(["2026-10-23", "2026-10-26"]))
    t = int(pd.Timestamp("2026-10-27 06:00", tz="UTC").timestamp())         # 15:00 in Tokyo
    monkeypatch.setattr(c, "_info", lambda s: {"regularMarketPrice": 3102.0, "regularMarketTime": t,
                                               "exchangeTimezoneName": "Asia/Tokyo", "regularMarketVolume": 2e7})
    out = toolkit._stitch_quote("7203.T", df)
    assert out.index[-1] == pd.Timestamp("2026-10-27") and out["Close"].iloc[-1] == 3102.0
    assert len(toolkit._stitch_quote("7203.T", out)) == len(out)            # already current: unchanged


def test_slow_screens_survive_a_restart_as_a_marked_saved_copy(tmp_path, monkeypatch):
    import time as _t
    monkeypatch.setattr(core, "PERSIST_DIR", tmp_path)
    core._cache.pop("imap:TEST", None)
    assert core._cached("imap:TEST", 300, lambda: {"rows": [1]}) == {"rows": [1]}     # built and saved
    core._cache.pop("imap:TEST", None)                                                # "restart"
    p = core._persist_path("imap:TEST")
    old = _t.time() - 600
    import os
    os.utime(p, (old, old))                                                           # saved 10 min ago, TTL 5 min
    refreshed = []
    monkeypatch.setattr(core, "_refresh_later", lambda key, fn: refreshed.append(key))
    v = core._cached("imap:TEST", 300, lambda: {"rows": [2]})
    assert v["rows"] == [1] and v["stale"] is True and refreshed == ["imap:TEST"]       # served at once, refreshing
    core._cache.pop("imap:TEST", None)
    assert core._persist_path("quote:AAPL") is None                                   # only the slow screens persist


def test_crypto_overlay_uses_live_price_and_keeps_the_previous_close(monkeypatch):
    from api.marketdata import core
    from api.providers import crypto_live as cl
    monkeypatch.setattr(cl, "prices", lambda: {"coins": {"BTC": 110.0, "XYZ": 999.0}, "source": "Coinbase (real-time)"})
    rows = [{"symbol": "BTC-USD", "price": 100.0, "change_1d": 0.0},      # prev close 100 → +10%
            {"symbol": "XYZ-USD", "price": 1.0, "change_1d": 0.0},        # 999 is a different coin: ignored
            {"symbol": "SPY", "price": 500.0, "change_1d": 0.01}]
    assert core.crypto_overlay(rows) == "Coinbase (real-time)"
    assert rows[0]["price"] == 110.0 and abs(rows[0]["change_1d"] - 0.10) < 1e-9 and rows[0]["live"]
    assert rows[1]["price"] == 1.0 and rows[2]["price"] == 500.0
    assert cl.coin_of("BTC-USD") == "BTC" and cl.coin_of("EURUSD=X") is None and cl.coin_of("SPY") is None


def test_stale_universe_is_served_at_once_and_rebuilt_in_the_background(tmp_path, monkeypatch):
    import json as _json
    import threading
    from api import global_universe as gu
    f = tmp_path / "u.json"
    f.write_text(_json.dumps({"stocks": [{"symbol": "OLD"}], "saved_at": 0, "config": gu.config_hash()}))
    monkeypatch.setattr(gu, "FILE", f)
    started = threading.Event()
    monkeypatch.setattr(gu, "build", lambda: (started.set(), {"stocks": [{"symbol": "NEW"}]})[1])
    assert gu.load()["stocks"] == [{"symbol": "OLD"}]          # no 5-minute wait in the request
    assert started.wait(5)                                      # the rebuild runs in the background
