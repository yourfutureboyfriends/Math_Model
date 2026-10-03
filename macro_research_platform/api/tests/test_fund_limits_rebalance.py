"""
Known-answer tests for the hedge-fund layer: NAV/track record, risk limits & pre-trade
compliance, and the regime rebalance engine.
Run: pytest api/tests/test_fund_limits_rebalance.py
"""
import numpy as np
import pytest

from api.calculations.fund import (
    compute_nav, exposures_pct_nav, track_record, proforma_nav, drawdown_from_peak,
)
from api.calculations.limits import (
    DEFAULT_LIMITS, merge_limits, evaluate_limits, pretrade_check,
)
from api.calculations.rebalance import (
    regime_budgets, risk_budget_weights, risk_contributions, target_portfolio,
    rebalance_orders, UNIVERSE,
)


# ── Fund / NAV ───────────────────────────────────────────────────────────────
def test_nav_is_capital_plus_pnl():
    assert compute_nav(10_000_000, 125_000.5, realized_pnl=-25_000) == 10_100_000.5


def test_exposures_as_pct_of_nav():
    s = {"long_market_value": 8e6, "short_market_value": -3e6,
         "gross_exposure": 11e6, "net_exposure": 5e6}
    e = exposures_pct_nav(s, 10e6)
    assert e == {"long": 0.8, "short": -0.3, "gross": 1.1, "net": 0.5}
    assert exposures_pct_nav(s, 0)["gross"] is None


def test_track_record_known_answers():
    navs = [100, 110, 99, 105]                 # +10%, -10%, +6.06%
    tr = track_record(navs)
    assert tr["total_return"] == pytest.approx(0.05)
    assert tr["max_drawdown"] == pytest.approx(99 / 110 - 1, abs=1e-4)
    assert tr["current_drawdown"] == pytest.approx(105 / 110 - 1, abs=1e-4)
    assert tr["hit_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert tr["worst_day"] == pytest.approx(-0.1)


def test_track_record_needs_two_points():
    assert track_record([100])["available"] is False


def test_proforma_ends_at_current_nav_and_reflects_moves():
    closes = {"A": {"d1": 100.0, "d2": 110.0, "d3": 99.0}}
    pf = proforma_nav(1_000_000, {"A": 500_000}, closes, days=5)
    assert pf["dates"] == ["d1", "d2", "d3"]
    assert pf["nav"][-1] == 1_000_000
    # Day 3 return on $500k = -10% -> NAV on d2 was $50k higher
    assert pf["nav"][-2] == pytest.approx(1_050_000)


def test_drawdown_from_peak():
    assert drawdown_from_peak([100, 120, 90]) == -0.25


# ── Limits & pre-trade ───────────────────────────────────────────────────────
def test_merge_limits_keeps_soft_below_hard():
    m = merge_limits({"single_name": {"soft": 0.30, "hard": 0.20}, "bogus": {"hard": 1}})
    assert m["single_name"]["hard"] == 0.20 and m["single_name"]["soft"] == 0.20
    assert "bogus" not in m


def test_evaluate_limits_status_and_utilization():
    lim = merge_limits(None)
    ev = evaluate_limits({"gross_exposure": 1.7, "single_name": 0.05, "var95_1d": 0.025}, lim)
    by = {r["metric"]: r for r in ev["limits"]}
    assert by["gross_exposure"]["status"] == "WARN"
    assert by["single_name"]["status"] == "OK"
    assert by["var95_1d"]["status"] == "BREACH"
    assert by["var95_1d"]["utilization"] == pytest.approx(1.25)
    assert ev["overall"] == "BREACH"
    assert by["drawdown"]["available"] is False


def test_pretrade_blocks_new_hard_breach_and_allows_reductions():
    lim = merge_limits(None)
    block = pretrade_check({"single_name": 0.09}, {"single_name": 0.18}, lim)
    assert block["decision"] == "BLOCK"
    assert block["reasons"] == ["Largest single name: 9.0% NAV → 18.0% NAV "
                                "(over hard limit 15.0% NAV) — BLOCK"]
    warn = pretrade_check({"gross_exposure": 1.2}, {"gross_exposure": 1.6}, lim)
    assert warn["decision"] == "WARN"
    # Reducing an existing hard breach is allowed
    reduce = pretrade_check({"var95_1d": 0.03}, {"var95_1d": 0.025}, lim)
    assert reduce["decision"] == "PASS"


# ── Rebalance engine ─────────────────────────────────────────────────────────
def test_regime_budgets_follow_playbook():
    b = regime_budgets("slowdown")            # duration long, commodities underweight
    assert b["TLT"] > b["DBC"]
    r = regime_budgets("reflation")           # duration short, commodities overweight
    assert r["DBC"] > r["TLT"]
    assert sum(b.values()) == pytest.approx(1.0, abs=1e-5)
    assert len(regime_budgets("unknown-regime")) == len(UNIVERSE)


def test_risk_budget_weights_hit_budgets():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (2000, 3)) @ np.array([[1, .3, .1], [0, 1, .2], [0, 0, 1]])
    X *= np.array([0.02, 0.01, 0.005])
    cov = np.cov(X, rowvar=False)
    budgets = np.array([0.5, 0.3, 0.2])
    w = risk_budget_weights(cov, budgets)
    assert w.sum() == pytest.approx(1.0) and (w > 0).all()
    assert risk_contributions(cov, w) == pytest.approx(budgets, abs=1e-4)


def test_target_portfolio_hits_vol_target_and_caps_gross():
    rng = np.random.default_rng(1)
    rets = {a: rng.normal(0, 0.01, 300) for a in UNIVERSE}
    tp = target_portfolio("goldilocks", rets, vol_target=0.08, max_gross=3.0)
    assert tp["available"] and tp["expected_vol"] == pytest.approx(0.08, abs=1e-3)
    capped = target_portfolio("goldilocks", rets, vol_target=0.50, max_gross=1.5)
    assert capped["gross_capped"] and capped["leverage"] == pytest.approx(1.5)
    assert sum(w["weight"] for w in capped["weights"]) == pytest.approx(1.5, abs=1e-3)


def test_rebalance_orders_buy_sell_exit_and_threshold():
    out = rebalance_orders(
        target_weights={"SPY": 0.40, "TLT": 0.10},
        nav=1_000_000, prices={"SPY": 500.0, "TLT": 100.0, "XYZ": 50.0},
        current_qty={"SPY": 600, "TLT": 999, "XYZ": 100}, min_trade_pct=0.0025, cost_bps=10)
    by = {o["symbol"]: o for o in out["orders"]}
    assert by["SPY"]["side"] == "BUY" and by["SPY"]["quantity"] == 200       # 800 target
    assert "TLT" not in by                                                    # 1 share diff < threshold
    assert by["XYZ"]["action"] == "EXIT" and by["XYZ"]["side"] == "SELL"
    assert out["est_total_cost"] == pytest.approx((100_000 + 5_000) * 10 / 1e4)


# ── Blotter accounting ───────────────────────────────────────────────────────
from api.calculations.blotter import apply_fill, cash_balance, side_to_signed, blotter_totals, commission
from api.calculations.scorecard import transition_backtest, resolve_recession_forecasts


def test_apply_fill_average_cost_and_realized():
    q, a, r = apply_fill(0, 0, 100, 10.0)                 # open
    assert (q, a, r) == (100, 10.0, 0.0)
    q, a, r = apply_fill(q, a, 100, 12.0)                 # add
    assert q == 200 and a == pytest.approx(11.0) and r == 0
    q, a, r = apply_fill(q, a, -50, 15.0)                 # partial close
    assert q == 150 and a == pytest.approx(11.0) and r == pytest.approx(200.0)
    q, a, r = apply_fill(q, a, -200, 9.0)                 # close 150, flip short 50 @ 9
    assert q == -50 and a == 9.0 and r == pytest.approx((9 - 11) * 150)
    q, a, r = apply_fill(q, a, 50, 8.0)                   # cover short at a profit
    assert q == 0 and a == 0 and r == pytest.approx(50.0)


def test_cash_and_nav_identity():
    positions = [{"quantity": 100, "avg_cost": 50.0}, {"quantity": -20, "avg_cost": 100.0}]
    cash = cash_balance(1_000_000, positions, realized_pnl=1_500, commissions=25)
    assert cash == pytest.approx(1_000_000 - (5_000 - 2_000) + 1_500 - 25)
    # NAV = cash + MV = capital + realized + unrealized - commissions
    mv = 100 * 55 + (-20) * 90
    unrealized = 100 * (55 - 50) + (-20) * (90 - 100)
    assert cash + mv == pytest.approx(1_000_000 + 1_500 + unrealized - 25)


def test_side_and_totals():
    assert side_to_signed("BUY", 10) == 10 and side_to_signed("sell", 10) == -10
    with pytest.raises(ValueError):
        side_to_signed("HOLD", 1)
    t = blotter_totals([{"realized_pnl": 10, "commission": 1, "quantity": -5, "price": 20}])
    assert t == {"realized_pnl": 10.0, "commissions": 1.0, "traded_notional": 100.0, "trades": 1}
    assert commission(-100_000, 5) == 50.0


# ── Scorecard ────────────────────────────────────────────────────────────────
def test_transition_backtest_beats_naive_on_alternating_series():
    seq = ["A", "B"] * 60                                  # always switches
    bt = transition_backtest(seq, min_train=10)
    assert bt["hit_rate"] == 1.0 and bt["naive_persistence_hit_rate"] == 0.0
    assert bt["brier"] < 0.01 and bt["verdict"].startswith("adds skill")
    flat = transition_backtest(["A"] * 40 + ["B"] * 40, min_train=10)
    assert flat["skill_vs_naive"] <= 0 and flat["verdict"].startswith("no skill")
    assert transition_backtest(["A"] * 5, min_train=10) is None


def test_recession_forecasts_resolve_only_after_horizon():
    usrec = {"2020-04-01": 1.0, "2021-01-01": 0.0}
    fc = [("2019-04-15", 0.8), ("2020-01-10", 0.1), ("2026-09-01", 0.06)]
    r = resolve_recession_forecasts(fc, usrec, horizon_months=12)
    assert r["resolved"] == 2 and r["pending"] == 1
    assert r["brier"] == pytest.approx(((0.8 - 1) ** 2 + (0.1 - 0) ** 2) / 2)
    assert r["next_resolution"] == "2027-09-01"
