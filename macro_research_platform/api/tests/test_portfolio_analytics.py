import math

import numpy as np
import pytest

from api.calculations.portfolio_analytics import (
    holdings_by_day, brinson_day, carino_link, ex_ante_tracking_error, corwin_schultz_spread,
    liquidity_profile, fifo_lots, tca_row, idea_pnl)


def test_holdings_rebuilt_from_trades_and_entry_dates():
    pos = [{"symbol": "AAA", "quantity": 100, "entry_date": "2026-01-05"},
           {"symbol": "BBB", "quantity": 50, "entry_date": "2026-01-01"}]
    trades = [{"ts": "2026-01-03T10:00", "symbol": "BBB", "side": "BUY", "quantity": 30}]
    h = holdings_by_day(pos, trades, ["2026-01-02", "2026-01-04", "2026-01-06"])
    assert h["2026-01-02"] == {"BBB": 20}            # 50 − the 30 bought later
    assert h["2026-01-04"] == {"BBB": 50}            # AAA not yet entered
    assert h["2026-01-06"] == {"AAA": 100, "BBB": 50}


def test_brinson_effects_sum_to_active_return_single_period():
    pw, pr = {"Tech": 0.7, "Energy": 0.3}, {"Tech": 0.05, "Energy": -0.02}
    bw, br = {"Tech": 0.5, "Energy": 0.5}, {"Tech": 0.03, "Energy": 0.01}
    eff = brinson_day(pw, pr, bw, br)
    active = sum(pw[s] * pr[s] for s in pw) - sum(bw[s] * br[s] for s in bw)
    total = sum(sum(e.values()) for e in eff.values())
    assert total == pytest.approx(active, abs=1e-12)


def test_carino_linking_matches_geometric_active_return():
    rng = np.random.default_rng(1)
    daily, rp, rb = [], [], []
    for _ in range(40):
        pw = {"A": 0.6, "B": 0.4}
        pr = {"A": rng.normal(0, 0.01), "B": rng.normal(0, 0.01)}
        bw = {"A": 0.5, "B": 0.5}
        br = {"A": rng.normal(0, 0.01), "B": rng.normal(0, 0.01)}
        daily.append(brinson_day(pw, pr, bw, br))
        rp.append(sum(pw[s] * pr[s] for s in pw))
        rb.append(sum(bw[s] * br[s] for s in bw))
    linked = carino_link(daily, rp, rb)
    total = sum(sum(e.values()) for e in linked.values())
    assert total == pytest.approx(math.prod(1 + r for r in rp) - math.prod(1 + b for b in rb), abs=1e-10)


def test_tracking_error_zero_when_matching_benchmark():
    cov = np.array([[1e-4, 2e-5], [2e-5, 2e-4]])
    assert ex_ante_tracking_error([0.0, 0.0], cov) == 0
    assert ex_ante_tracking_error([0.1, -0.1], cov) == pytest.approx(math.sqrt(252 * (1e-6 + 2e-6 - 4e-7)))


def test_corwin_schultz_positive_for_wider_ranges():
    hi, lo = [101, 101.2, 100.9, 101.1], [99, 99.1, 98.8, 99.2]
    s = corwin_schultz_spread(hi, lo)
    assert s is not None and 0 <= s < 0.05


def test_liquidity_profile_days_to_liquidate():
    p = liquidity_profile(qty=-20_000, price=50, adv_shares=100_000, spread=0.001)
    assert p["days_to_liquidate"] == 1.0 and p["pct_of_adv"] == 20.0
    assert p["liquidity_cost"] == 0.5 * 0.001 * 1_000_000


def test_fifo_lots_closes_oldest_first():
    lots = fifo_lots([{"date": "2026-01-01", "side": "BUY", "quantity": 10, "price": 100},
                      {"date": "2026-02-01", "side": "BUY", "quantity": 10, "price": 110},
                      {"date": "2026-03-01", "side": "SELL", "quantity": 15, "price": 120}])
    assert lots == [{"date": "2026-02-01", "quantity": 5.0, "price": 110.0, "source": None}]


def test_tca_signs_cost_positive_for_buys_above_arrival():
    r = tca_row(+1, 100, fill=101, arrival=100, high=102, low=99, close=100)
    assert r["vs_arrival_bps"] == 100.0 and r["shortfall_usd"] == 100.0
    s = tca_row(-1, 100, fill=99, arrival=100, high=102, low=99, close=100)
    assert s["vs_arrival_bps"] == 100.0


def test_idea_pnl_stop_before_target_and_short_side():
    path = [("d1", 105, 99, 104), ("d2", 111, 103, 110)]
    long = idea_pnl("LONG", 100, path, stop=98, target=110)
    assert long["status"] == "target" and long["return"] == pytest.approx(0.10)
    short = idea_pnl("SHORT", 100, path, stop=108, target=90)
    assert short["status"] == "stop" and short["return"] == pytest.approx(-0.08)



def test_earnings_gate_waits_then_halves():
    from datetime import date
    from api.calculations.stock_timing import earnings_gate
    buy = {"code": "BUY", "label": "Buy — set-up and entry aligned", "detail": ""}
    lv = {"shares": 100, "notional": 10000.0, "notional_local": 10000.0, "pct_nav": 0.001, "risk_usd": 50.0, "sizing_basis": "x"}
    today = date(2026, 10, 19)
    near = earnings_gate([{"date": "2026-10-22", "reported": None}], today, buy, lv)
    assert near["verdict"]["code"] == "WAIT" and near["days"] == 3 and near["applied"] == "wait"
    mid = earnings_gate([{"date": "2026-10-27", "reported": None}], today, buy, lv)
    assert mid["verdict"]["code"] == "BUY" and mid["levels"]["shares"] == 50 and mid["levels"]["risk_usd"] == 25.0
    far = earnings_gate([{"date": "2026-11-30", "reported": None}, {"date": "2026-07-20", "reported": 1.2}], today, buy, lv)
    assert far["applied"] is None and far["levels"]["shares"] == 100
    watch = earnings_gate([{"date": "2026-10-20", "reported": None}], today, {"code": "WATCH"}, lv)
    assert watch["verdict"]["code"] == "WATCH"


def test_backed_out_weights_reverse_relative_performance():
    from api.calculations.portfolio_analytics import backed_out_weights
    # A doubled since then and B flat: today 2/3 vs 1/3 means they were equal then
    w = backed_out_weights({"A": 2 / 3, "B": 1 / 3}, {"A": 50, "B": 100}, {"A": 100, "B": 100})
    assert w["A"] == pytest.approx(0.5) and w["B"] == pytest.approx(0.5)
