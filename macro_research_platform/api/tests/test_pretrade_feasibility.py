"""Pre-trade feasibility logic on fixed inputs (no network): liquidity, costs, mandate, events, valuation."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from api.handlers import pretrade_feasibility as pf


@pytest.fixture()
def env(monkeypatch, tmp_path):
    from api import fund_store, pitches, portfolio_store
    from api.calculations import benchmark as bm, fx_accounting as fa
    from api.handlers import portfolio_analytics as pa
    from api.marketdata import core, security
    path = str(tmp_path / "p.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)
    fund_store.update_settings({"capital": 1_000_000.0, "base_currency": "GBP", "benchmark": "BIFS", "cost_bps": 5.0})
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=300)
    px = pd.Series(np.linspace(11000, 12800, len(idx)), index=idx)
    bars = pd.DataFrame({"open": px, "high": px * 1.01, "low": px * 0.99, "close": px, "volume": 10_000.0}, index=idx)
    monkeypatch.setattr(pf, "_bars_frame", lambda s, period="5y": bars)
    state = {"earnings": str(date.today() + timedelta(days=2))}
    monkeypatch.setattr(core, "quote", lambda s: {"price": 12800.0, "currency": "GBp", "market_state": "REGULAR",
                                                 "bid": 12798.0, "ask": 12802.0, "name": "Test plc", "exchange": "LSE"})
    monkeypatch.setattr(core, "statements", lambda s: {"ratios": {"operating_margin": 0.25}})
    monkeypatch.setattr(core, "profile", lambda s: {"sector": "Healthcare"})
    monkeypatch.setattr(security, "earnings", lambda s: {"upcoming": [{"date": state["earnings"]}], "beat_rate": 0.8})
    monkeypatch.setattr(security, "dividends", lambda s: {})
    monkeypatch.setattr(fa, "usd_per_unit", lambda ccy, on=None: 0.013)
    monkeypatch.setattr(fa, "base_per_usd", lambda base, on=None: 1 / 1.3)
    monkeypatch.setattr(bm, "series", lambda code, base: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(pa, "book_in_base", lambda book=None: {"nav": 1_000_000.0, "positions": [], "base": "GBP"})
    from api.marketdata import econ, workbench
    from api.handlers import cb_decisions
    monkeypatch.setattr(econ, "calendar", lambda *a, **k: {"events": []})
    monkeypatch.setattr(cb_decisions, "next_decisions", lambda *a, **k: {"banks": []})
    monkeypatch.setattr(workbench, "exchanges", lambda: {"exchanges": []})
    return state, pitches


def test_liquidity_costs_and_staging(env):
    r = pf.assess("TEST.L", "BUY", quantity=3000)
    liq = r["liquidity"]
    assert liq["order_pct_adv20"] == pytest.approx(0.30) and liq["sessions_at_cap"] == 3      # 3,000 vs 10,000/day at 10%
    c = r["costs"]
    assert c["taxes_bps"]["value"] == 50.0                                                   # UK stamp duty on a buy
    assert c["half_spread_bps"]["basis"].startswith("observed") and c["half_spread_bps"]["value"] == pytest.approx(4 / 12800 * 1e4 / 2, abs=0.01)
    assert c["impact_bps"]["staged_at_cap"] == pytest.approx(11.2 * (10 ** 0.5), abs=0.01)
    assert c["fx_conversion_bps"]["value"] == 0.0                                            # GBp in a GBP fund
    assert r["size"]["notional_base"] == pytest.approx(3000 * 128.0)
    areas = {(f["level"], f["area"]) for f in r["flags"]}
    assert ("warn", "liquidity") in areas and ("warn", "events") in areas                    # 30% of ADV; earnings in 2 days
    assert ("warn", "approval") in areas                                                     # no pitch on file


def test_mandate_blocks(env):
    r = pf.assess("TEST.L", "SELL", quantity=10)
    assert any(f["level"] == "block" and "Long-only" in f["message"] for f in r["flags"])
    big = pf.assess("TEST.L", "BUY", amount_base=150_000.0)                                 # 15% of NAV
    assert any(f["level"] == "block" and "Max position" in f["message"] for f in big["flags"])
    many = pf.assess("TEST.L", "BUY", quantity=8000)                                         # 8 sessions at 10%
    assert any(f["level"] == "block" and "sessions" in f["message"] for f in many["flags"])
    assert many["assessment"]["verdict"] == "do not proceed as proposed"


def test_pitch_valuation_and_kill_criteria(env):
    state, pitches = env
    body = {"thesis": "A long enough investment thesis for the record.", "horizon_years": 2,
            "scenarios": {"bear": {"value": 13000, "probability": 0.3}, "base": {"value": 15000, "probability": 0.5},
                          "bull": {"value": 18000, "probability": 0.2}},
            "entry_range": {"low": 11000, "high": 12500},
            "kill_criteria": [{"type": "metric_below", "metric": "operating_margin", "threshold": 0.3, "description": "margin below 30%"}]}
    p = pitches.create("TEST.L", "Test", "analyst", body)
    state["earnings"] = str(date.today() + timedelta(days=40))
    r = pf.assess("TEST.L", "BUY", quantity=100)
    v = r["pitch"]["valuation"]
    assert v["expected_value"] == pytest.approx(0.3 * 13000 + 0.5 * 15000 + 0.2 * 18000) and v["in_entry_range"] is False
    msgs = " | ".join(f["message"] for f in r["flags"])
    assert "not PMC-approved" in msgs and "outside the pitch's entry range" in msgs and "Kill criteria triggered" in msgs
    pitches.transition(p["id"], "analyst", "submitted")
    pitches.transition(p["id"], "pm", "approved")
    r2 = pf.assess("TEST.L", "BUY", quantity=100)
    assert not any("not PMC-approved" in f["message"] for f in r2["flags"])
