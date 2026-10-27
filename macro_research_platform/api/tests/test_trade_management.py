"""Trade management: exit / trim / tighten / add rules, stop placement, and the exit-rule simulator."""
from datetime import date

import numpy as np
import pytest

from api.calculations import trade_management as tm


def _path(rets, start=100.0, spread=0.01):
    c = start * np.cumprod(1 + np.asarray(rets, float))
    return c, c * (1 + spread), c * (1 - spread)


def test_trend_break_and_stop_exit_a_long():
    up = [0.002] * 300
    crash = [-0.02] * 40
    c, h, l = _path(up + crash)
    r = tm.manage_position(c, h, l, entry_idx=250, entry_price=float(c[250]), side=1, today=date(2026, 10, 1))
    assert r["action"] == "EXIT"
    assert {"trend_break", "stop_hit"} & {s["rule"] for s in r["signals"]}


def test_a_clean_uptrend_holds_with_the_initial_stop():
    c, h, l = _path([0.001 + 0.004 * np.sin(i / 7) for i in range(320)])
    r = tm.manage_position(c, h, l, entry_idx=280, entry_price=float(c[280]), side=1, today=date(2026, 10, 1))
    assert r["action"] in ("HOLD", "ADD")
    assert r["stop"] == r["stops"]["initial"] and r["stop"] < r["price"]


def test_target_tightens_instead_of_selling():
    c, h, l = _path([0.002] * 300)
    r = tm.manage_position(c, h, l, entry_idx=200, entry_price=float(c[200]), side=1, target=float(c[-1]) * 0.99,
                           today=date(2026, 10, 1))
    sig = next(s for s in r["signals"] if s["rule"] == "target_reached")
    assert sig["action"] == "TIGHTEN" and r["action"] in ("TIGHTEN", "TRIM")


@pytest.mark.parametrize("seed", range(25))
def test_stop_is_always_on_the_right_side_unless_exiting(seed):
    rng = np.random.default_rng(seed)
    c, h, l = _path(rng.normal(0.0005, 0.02, 320))
    for side in (1, -1):
        r = tm.manage_position(c, h, l, entry_idx=int(rng.integers(220, 300)), entry_price=float(c[260]), side=side,
                               market_ok=bool(seed % 2), vix=35 if seed % 3 == 0 else 15, today=date(2026, 10, 1),
                               revisions=[{"date": "2026-09-20", "action": "down", "target_change": -5}] * 3)
        if r["action"] != "EXIT":
            assert (r["stop"] < r["price"]) if side > 0 else (r["stop"] > r["price"])


def test_fundamental_and_news_warnings():
    c, h, l = _path([0.001] * 300)
    r = tm.manage_position(c, h, l, entry_idx=250, entry_price=float(c[250]), side=1, today=date(2026, 10, 1),
                           revisions=[{"date": "2026-09-25", "action": "down", "target_change": -10},
                                      {"date": "2026-09-20", "action": "down", "target_change": -8}],
                           earnings=[{"date": "2026-09-15", "reported": 1.0, "surprise_pct": -6.0}],
                           news=[{"sentiment": -0.5}] * 4)
    rules = {s["rule"] for s in r["signals"]}
    assert {"analyst_cuts", "earnings_miss", "news_tone"} <= rules
    assert r["action"] == "TRIM"


def test_insider_buying_supports_and_add_needs_profit_and_a_pullback():
    c, h, l = _path([0.002] * 300)
    r = tm.manage_position(c, h, l, entry_idx=200, entry_price=float(c[200]), side=1, entry_verdict="BUY",
                           timing_state="pullback", insiders={"buyers_6m": 3}, today=date(2026, 10, 1))
    assert r["action"] == "ADD" and any(s["rule"] == "insider_buying" for s in r["signals"])
    loser = tm.manage_position(c, h, l, entry_idx=200, entry_price=float(c[-1]) * 1.02, side=1, entry_verdict="BUY",
                               timing_state="pullback", today=date(2026, 10, 1))
    assert loser["action"] != "ADD"                                          # never add to a loser


def test_simulator_fixed_rule_takes_profit_at_2r_and_trend_rule_holds():
    c, h, l = _path([0.003] * 500)
    fixed = tm.simulate_exit(c, h, l, 260, "fixed")
    trend = tm.simulate_exit(c, h, l, 260, "trend")
    assert fixed["r"] == pytest.approx(2.0, abs=0.35) and trend["days"] > fixed["days"]
    s = tm.summarise_trades([fixed, trend])
    assert s["trades"] == 2 and s["win_rate"] == 1.0


def test_entry_buy_waits_while_news_tone_is_strongly_negative(monkeypatch):
    """GET /api/v1/stock/timing: a BUY becomes WAIT when ≥5 headlines in the window average ≤ −0.3 (Tetlock, 2007);
    mildly negative or thin news leaves it alone."""
    import asyncio
    from api import trade_manager
    from api.routers import stock

    async def fake_analyze(sym, with_history=True):
        return {"available": True, "symbol": sym, "verdict": {"code": "BUY", "label": "Buy"}}

    def overlay(count, tone):
        async def f(sym):
            return {"news": {"available": True, "count": count, "avg_tone": tone, "window_days": 14, "items": []},
                    "insiders": {"available": False}}
        return f

    monkeypatch.setattr(stock, "analyze", fake_analyze)
    monkeypatch.setattr(trade_manager, "overlays", overlay(6, -0.45))
    assert asyncio.run(stock.stock_timing("AAPL"))["verdict"]["code"] == "WAIT"
    monkeypatch.setattr(trade_manager, "overlays", overlay(3, -0.6))          # too few headlines
    assert asyncio.run(stock.stock_timing("AAPL"))["verdict"]["code"] == "BUY"
    monkeypatch.setattr(trade_manager, "overlays", overlay(8, -0.1))          # mildly negative
    assert asyncio.run(stock.stock_timing("AAPL"))["verdict"]["code"] == "BUY"
