"""Deep backtest analysis (api/quant/deep.py) on synthetic data, and the stock-book endpoint."""
import json
import math

import numpy as np
import pandas as pd
import pytest

from api.quant import deep


def _series(n=2520, mu=0.0004, sd=0.01, seed=1):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("2012-01-02", periods=n)
    return [x.strftime("%Y-%m-%d") for x in d], rng.normal(mu, sd, n)


def test_summary_and_drawdowns_are_consistent(monkeypatch):
    from api.quant import rates
    monkeypatch.setattr(rates, "daily", lambda idx: pd.Series(0.04 / 252, index=pd.DatetimeIndex(pd.to_datetime(list(idx)))))
    dates, r = _series()
    rep = deep.report(dates, r, 252, label="s")
    s = rep["summary"]
    eq = np.cumprod(1 + r)
    assert s["max_drawdown"] == pytest.approx((eq / np.maximum.accumulate(eq) - 1).min(), abs=1e-4)
    assert rep["drawdowns"][0]["depth"] == pytest.approx(s["max_drawdown"], abs=1e-4)          # worst episode = max drawdown
    ex = r - 0.04 / 252                                                                         # Sharpe is on returns above cash
    assert s["sharpe"] == pytest.approx(ex.mean() / ex.std(ddof=1) * math.sqrt(252), rel=1e-3)
    assert s["cash_rate"] == pytest.approx(0.04, abs=1e-4)
    tot = 1.0
    for y in rep["calendar"]:
        tot *= 1 + y["total"]
    assert tot - 1 == pytest.approx(s["total_return"], rel=1e-3)                               # calendar compounds to the total


def test_benchmark_relative_beta_and_alpha():
    dates, b = _series(seed=2)
    rng = np.random.default_rng(3)
    s = 0.5 * b + 0.0002 + rng.normal(0, 0.002, len(b))                                       # beta 0.5 plus alpha
    rel = deep.report(dates, s, 252, benchmark=b)["relative"]
    assert rel["beta"] == pytest.approx(0.5, abs=0.03)
    assert rel["alpha"] == pytest.approx(0.0002 * 252, abs=0.02)
    assert rel["down_capture"] < 1


def test_robustness_bootstrap_and_track_record():
    dates, r = _series(mu=0.0008)
    rb = deep.report(dates, r, 252)["robustness"]
    assert rb["bootstrap"]["5y"]["prob_loss"] <= rb["bootstrap"]["1y"]["prob_loss"]           # longer horizon, less chance of a loss
    assert rb["psr"] > 0.9 and rb["min_track_record_years"] is not None
    assert rb["first_half"] and rb["second_half"]


def test_trade_analytics():
    dates, r = _series(n=600)
    trades = [{"symbol": f"S{i}", "entry_date": "2013-01-02", "exit_date": "2013-01-10", "reason": "target" if i % 3 == 0 else "stop",
               "r": 2.0 if i % 3 == 0 else -1.0, "days": 5 + i % 30, "sector": "Tech" if i % 2 else "Energy"} for i in range(60)]
    t = deep.report(dates, r, 252, trades=trades, trade_group="sector")["trades"]
    assert t["trades"] == 60 and t["win_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert t["expectancy"] == pytest.approx((20 * 2 - 40) / 60, abs=1e-3)
    assert t["profit_factor"] == pytest.approx(1.0, abs=1e-3)
    assert {g["group"] for g in t["by_exit"]} == {"target", "stop"}
    assert t["group_name"] == "sector"


def test_monthly_input():
    d = pd.date_range("2000-01-31", periods=240, freq="ME")
    r = np.random.default_rng(4).normal(0.006, 0.03, 240)
    rep = deep.report([x.strftime("%Y-%m-%d") for x in d], r, 12)
    assert rep["frequency"] == "monthly" and len(rep["calendar"]) == 20


def test_stock_backtest_deep_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import stock_backtest as sb
    from api.main import app
    client = TestClient(app)
    dates, r = _series(n=800)
    _, c = _series(n=800, seed=9)
    f = tmp_path / "sb.json"
    f.write_text(json.dumps({"available": True, "daily": {"dates": dates, "model": r.tolist(), "control": c.tolist()},
                             "trade_list": [{"symbol": "AAA", "entry_date": "2012-02-01", "exit_date": "2012-02-08", "reason": "target",
                                             "r": 2.0, "days": 6, "region": "Americas"}] * 10}))
    monkeypatch.setattr(sb, "RESULT_FILE", f)
    res = client.get("/api/v1/stock/backtest/deep")
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["summary"]["periods"] == 800 and j["relative"] and j["trades"]["trades"] == 10
    # older results (curve only) still work, without the trade section
    f.write_text(json.dumps({"available": True, "sample": {"years": 3},
                             "curve": [{"date": d, "model": float(v), "control": 1.0} for d, v in zip(dates[::5], np.cumprod(1 + r)[::5])]}))
    j2 = client.get("/api/v1/stock/backtest/deep").json()
    assert j2["trades"] is None and "trades_note" in j2
