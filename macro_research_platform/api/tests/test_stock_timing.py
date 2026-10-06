"""Stock entry timing: component scores, verdict rules, levels/sizing, and no look-ahead."""
from datetime import date

import numpy as np
import pytest

from api.calculations import stock_timing as st


def _uptrend(n=600, drift=0.0008, vol=0.01, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    return c, c * 1.01, c * 0.99


def test_indicators():
    c = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], dtype=float)
    assert st.rsi(c) == 100.0                               # only gains
    assert st.sma(c, 4) == pytest.approx(14.5)
    h, l = c + 1, c - 1
    assert st.atr(h, l, c) == pytest.approx(2.0)


def test_uptrend_scores_positive_and_downtrend_negative():
    c, h, l = _uptrend()
    assert st.trend_component(c)["score"] == 1.0
    assert st.momentum_component(c)["score"] > 0.5
    d, _, _ = _uptrend(drift=-0.0012)                       # steady decline
    assert st.trend_component(d)["score"] == -1.0
    assert st.momentum_component(d)["score"] < 0


def test_timing_pullback_vs_extended():
    c, h, l = _uptrend()
    stretched = np.concatenate([c, c[-1] * np.cumprod(np.full(10, 1.03))])
    t = st.timing_component(stretched, stretched * 1.01, stretched * 0.99)
    assert t["state"] == "extended" and t["score"] <= st.EXTENDED_TIMING
    dip = np.concatenate([c, c[-1] * np.cumprod(np.full(6, 0.975))])
    t2 = st.timing_component(dip, dip * 1.01, dip * 0.99)
    assert t2["score"] > 0.4


def test_earnings_drift_decays():
    today = date(2026, 10, 6)
    recent = st.earnings_component([{"date": "2026-09-20", "surprise_pct": 8.0}], today)
    old = st.earnings_component([{"date": "2026-05-01", "surprise_pct": 8.0}], today)
    assert recent["score"] == pytest.approx(0.8) and old["score"] == 0.0


def test_analyst_component_counts_revisions():
    today = date(2026, 10, 6)
    info = {"recommendationMean": 1.5, "targetMeanPrice": 125.0, "numberOfAnalystOpinions": 30}
    revs = [{"date": "2026-09-01", "action": "up", "target_change": 10},
            {"date": "2026-09-15", "action": "main", "target_change": 5},
            {"date": "2026-03-01", "action": "down", "target_change": -10}]     # outside 90d
    a = st.analyst_component(info, revs, 100.0, today)
    assert a["upgrades"] == 1 and a["downgrades"] == 0 and a["target_raises"] == 2
    assert a["upside"] == pytest.approx(0.25) and a["score"] > 0.8


def test_verdict_rules():
    ok = {"ok": True}
    assert st.verdict(0.6, {"score": 0.3}, ok, 2.0)["code"] == "BUY"
    assert st.verdict(0.6, {"score": -0.5}, ok, 2.0)["code"] == "WAIT"
    assert st.verdict(0.6, {"score": 0.3}, ok, 0.8)["code"] == "WAIT"          # poor reward:risk
    assert st.verdict(0.6, {"score": 0.3}, {"ok": False}, 2.0)["code"] == "BUY_SMALL"
    assert st.verdict(0.1, {"score": 0.3}, ok)["code"] == "WATCH"
    assert st.verdict(-0.3, {"score": 0.3}, ok)["code"] == "AVOID"


def test_levels_and_sizing():
    timing = {"score": 0.3, "atr14": 2.0, "sma20": 98.0}
    lv = st.levels(100.0, timing, high_52w=110.0, target_mean=120.0, nav=10_000_000)
    assert lv["entry_low"] == 98.0 and lv["entry_high"] == 100.0
    assert lv["stop"] == pytest.approx(99.0 - 5.0) and lv["target"] == 120.0
    assert lv["risk_usd"] <= 0.005 * 10_000_000 + 1e-6 and lv["pct_nav"] <= 0.10


def test_price_signal_has_no_look_ahead():
    c, h, l = _uptrend(800)
    base = st.price_signal_history(c, h, l)
    rng = np.random.default_rng(9)
    future = c.copy()
    future[500:] = future[500:] * np.exp(np.cumsum(rng.normal(-0.01, 0.03, 300)))   # rewrite the future
    alt = st.price_signal_history(future, future * 1.01, future * 0.99)
    assert np.array_equal(base[:500], alt[:500])


def test_evaluate_signal_counts_non_overlapping():
    c = np.linspace(100, 200, 600)
    sig = np.zeros(600)
    sig[300:320] = 1                                          # 20 consecutive days
    ev = st.evaluate_signal(c, sig, horizons=(21,))
    assert ev["21d"]["signals"] == 1 and ev["21d"]["hit_rate"] == 1.0


def test_sizing_converts_quote_currency_to_usd():
    timing = {"score": 0.3, "atr14": 20.0, "sma20": 980.0}          # a London stock in pence
    usd_lv = st.levels(1000.0, timing, None, 1200.0, nav=10_000_000, px_to_usd=0.01 / 0.75)
    # risk to stop = 0.5% of NAV in USD regardless of quote unit
    assert usd_lv["risk_usd"] == pytest.approx(50_000, rel=0.01)
    assert usd_lv["pct_nav"] <= 0.10 and usd_lv["notional_local"] > usd_lv["notional"]


def test_no_consensus_target_uses_2r_and_skips_rr_gate():
    timing = {"score": 0.3, "atr14": 2.0, "sma20": 98.0}
    lv = st.levels(100.0, timing, high_52w=101.0, target_mean=None, nav=None)
    assert lv["target_basis"].startswith("2R") and lv["reward_risk"] == pytest.approx(2.0)
    assert st.verdict(0.6, {"score": 0.3}, {"ok": True}, 1.2, target_is_consensus=False)["code"] == "BUY"
