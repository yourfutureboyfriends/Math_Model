"""Auto (paper) portfolio: selection, sizing, risk scaling, and full trading cycles on a
temporary database with fake prices — no network, no broker."""
import asyncio

import numpy as np
import pytest

from api import auto_trader as at


def _idea(sym, price=100.0, stop=95.0, setup=0.6, verdict="BUY", cls="Developed", sector="Tech", ccy="USD"):
    return {"symbol": sym, "name": sym, "price": price, "stop": stop, "setup_score": setup, "verdict": verdict,
            "market_class": cls, "sector": sector, "currency": ccy, "country": "US"}


def test_candidates_filter_rank_and_sector_cap():
    ideas = [_idea("A", setup=0.5), _idea("B", setup=0.9), _idea("C", verdict="BUY_SMALL"),
             _idea("D", cls="Frontier"), _idea("E", stop=99.9), _idea("F", setup=0.7), _idea("G", setup=0.8, sector="Energy")]
    out = [i["symbol"] for i in at.candidate_orders(ideas, held={"A"}, pending=set(), slots=10,
                                                    sector_counts={"Tech": 1}, max_per_sector=2)]
    # C risk-off, D frontier, E stop too tight, A held; Tech has one already → only one more Tech (B)
    assert out == ["B", "G"]


def test_size_respects_risk_name_and_gross_caps():
    s = {**at.DEFAULTS}
    # 0.5% of 1M = 5,000 risk; $5 risk/share → 1,000 shares = $100k = 10% (name cap binds equally)
    assert at.size_shares(1_000_000, 0, 100, 5, 1.0, s) == 1000
    assert at.size_shares(1_000_000, 0, 100, 1, 1.0, s) == 1000          # name cap (10%) binds
    assert at.size_shares(1_000_000, 950_000, 100, 5, 1.0, s) == 500     # only $50k gross room
    assert at.size_shares(1_000_000, 0, 100, 5, 1.0, s, risk_scale=0.5) == 500
    assert at.size_shares(1_000_000, 0, 100, 5, 0.01, s) == 100_000      # minor-unit FX (pence)


def test_drawdown_and_vol_multipliers():
    assert at.drawdown_multiplier(100, 100, 0.15) == 1.0
    assert abs(at.drawdown_multiplier(92.5, 100, 0.15) - 0.5) < 1e-9
    assert at.drawdown_multiplier(80, 100, 0.15) == 0.0
    calm = list(100 * np.cumprod(1 + np.full(25, 0.0005)))
    assert at.vol_multiplier(calm, 0.12)[0] == 1.0
    rng = np.random.default_rng(1)
    wild = list(100 * np.cumprod(1 + 0.03 * rng.standard_normal(25)))
    m, vol = at.vol_multiplier(wild, 0.12)
    assert vol > 0.3 and abs(m - 0.12 / vol) < 1e-9


@pytest.fixture
def book(tmp_path, monkeypatch):
    import api.core.app_db as adb
    monkeypatch.setattr(adb, "app_db_path", lambda: str(tmp_path / "auto.db"))
    state = {"ideas": [], "bars": {}}

    def fake_bars(symbols):
        return {s: state["bars"][s] for s in symbols if s in state["bars"]}

    async def fake_fx(ccy):
        return 1.0

    monkeypatch.setattr(at, "_bars", fake_bars)
    monkeypatch.setattr(at, "_fx", fake_fx)
    monkeypatch.setattr(at, "_ideas", lambda: {"fresh": True, "as_of": "x", "buy": state["ideas"]})
    at.reset(100_000)
    return state


def _set_bars(state, sym, rows):
    dates = [r[0] for r in rows]
    arr = np.array([r[1:] for r in rows], dtype=float)
    state["bars"][sym] = (dates, {"Open": arr[:, 0], "High": arr[:, 1], "Low": arr[:, 2], "Close": arr[:, 3]})


def test_full_cycle_order_fill_target_exit(book):
    book["ideas"] = [_idea("AAA", price=100, stop=95)]
    r1 = asyncio.run(at.run(today="2026-01-05"))
    assert r1["ordered"] == ["AAA"] and not r1["filled"]

    # next session: opens 101 → fills; risk 5 → stop 96, target 111; 0.5% risk allows 100 sh,
    # the 10% name cap 99 (100k × 10% / 101) — the cap binds
    _set_bars(book, "AAA", [("2026-01-05", 99, 100, 98, 100), ("2026-01-06", 101, 103, 100, 102)])
    book["ideas"] = []
    r2 = asyncio.run(at.run(today="2026-01-06"))
    assert r2["filled"] == ["AAA"]
    st = asyncio.run(at.status())
    p = st["positions"][0]
    assert p["shares"] == 99 and p["stop"] == 96 and p["target"] == 111

    # later session trades through the target → exit at 111
    _set_bars(book, "AAA", [("2026-01-05", 99, 100, 98, 100), ("2026-01-06", 101, 103, 100, 102),
                            ("2026-01-07", 104, 112, 103, 110)])
    r3 = asyncio.run(at.run(today="2026-01-07"))
    assert r3["exited"] == ["AAA"]
    st = asyncio.run(at.status())
    c = st["closed"][0]
    assert c["exit_reason"] == "target" and c["exit_price"] == 111
    assert st["positions"] == [] and abs(st["equity"] - st["cash"]) < 1e-6
    gross_pnl = 99 * (111 - 101)
    assert 0 < c["pnl_usd"] < gross_pnl and abs(c["r_multiple"] - c["pnl_usd"] / (99 * 5)) < 1e-9
    assert abs(st["cash"] - (100_000 + c["pnl_usd"])) < 0.01          # cash reported to the cent


def test_gap_through_stop_cancels_order(book):
    book["ideas"] = [_idea("BBB", price=100, stop=95)]
    asyncio.run(at.run(today="2026-02-02"))
    _set_bars(book, "BBB", [("2026-02-02", 99, 100, 98, 100), ("2026-02-03", 94, 96, 93, 95)])
    book["ideas"] = []
    r = asyncio.run(at.run(today="2026-02-03"))
    assert r["cancelled"] == ["BBB"] and not r["filled"]


def test_disabled_book_does_not_trade(book):
    at.update_settings({"enabled": False})
    book["ideas"] = [_idea("CCC")]
    assert asyncio.run(at.run(today="2026-03-02"))["ran"] is False
    with pytest.raises(ValueError):
        at.update_settings({"risk_per_trade": 0.5})          # outside the allowed range


def test_rolling_peak_rearms_drawdown_control(book):
    """After a year below an old high the book is sized from the recent peak, not the old one."""
    from api import auto_trader as a
    with a._db() as c:
        c.execute("INSERT INTO auto_nav(date, equity, cash, invested, positions) VALUES('2024-01-01', 200000, 0, 0, 0)")
        for k in range(300):
            c.execute("INSERT INTO auto_nav(date, equity, cash, invested, positions) VALUES(?, 100000, 0, 0, 0)",
                      (f"2025-{k:04d}",))
    st = asyncio.run(a.status())
    assert st["risk"]["drawdown_multiplier"] == 1.0          # all-time peak (200k) would give 0
