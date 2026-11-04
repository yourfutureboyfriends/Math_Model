"""Code Lab: cost-aware engine, walk-forward, Monte Carlo, sandbox and API — offline (synthetic data)."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab, sandbox
from api.tests.test_quant_api import client  # noqa: F401 — fixture


def _data(n=1500, k=3, seed=0, vol=0.01, dv=1e9):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=n)
    r = rng.normal(0.0003, vol, (n, k))
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=[f"A{i}" for i in range(k)])
    open_ = close.shift(1).fillna(close.iloc[0])               # open = prior close: no overnight gap
    volume = pd.DataFrame(dv / close.to_numpy(), index=idx, columns=close.columns)
    return codelab.Data(close, open_, close, close, volume, rf=pd.Series(0.0, index=idx))


ZERO = {"commission_bps": 0, "spread_mult": 0, "impact_coef_bps": 0, "sec_fee_bps": 0, "borrow_fee": 0, "financing_spread": 0}


def test_buy_and_hold_without_costs_matches_the_asset():
    d = _data(k=1)
    w = pd.DataFrame(1.0, index=d.close.index, columns=d.close.columns)
    res = codelab.backtest(w, d, {**ZERO, "no_trade_band": 0})
    eq = (1 + res["ret"]).prod()
    # bought at day 1's open (= day 0 close), held to the end
    assert eq == pytest.approx(d.close.iloc[-1, 0] / d.close.iloc[0, 0], rel=1e-9)


def test_trades_only_on_new_decisions_and_charges_commission():
    d = _data(k=2)
    w = codelab.hold_monthly(pd.DataFrame(0.5, index=d.close.index, columns=d.close.columns))
    res = codelab.backtest(w, d, {**ZERO, "commission_bps": 10, "no_trade_band": 0})
    traded_days = (res["turnover"] > 0).sum()
    months = len(set(d.close.index.to_period("M")))
    assert traded_days <= months + 1                            # monthly, not daily drift-chasing
    assert res["commission"].sum() == pytest.approx(10e-4 * res["turnover"].sum())


def test_impact_grows_with_capital_like_a_square_root():
    d = _data(k=1, dv=1e10)                                    # deep market: NAV barely moves with costs
    w = pd.DataFrame(np.tile([1.0, 0.0], 750)[:, None], index=d.close.index, columns=d.close.columns)   # daily round trips
    small = codelab.backtest(w, d, {**ZERO, "impact_coef_bps": 11.21, "capital": 1e5})["impact"].sum()
    big = codelab.backtest(w, d, {**ZERO, "impact_coef_bps": 11.21, "capital": 1e7})["impact"].sum()
    assert big / small == pytest.approx(10, rel=0.15)           # 100× capital → 10× cost per $ (√), ±path effects


def test_leverage_pays_financing_and_cash_earns_rf():
    d = _data(k=1)
    d.rf = pd.Series(0.04 / 252, index=d.close.index)
    levered = codelab.backtest(pd.DataFrame(2.0, index=d.close.index, columns=d.close.columns), d, {**ZERO, "financing_spread": 0.01})
    cash = codelab.backtest(pd.DataFrame(0.0, index=d.close.index, columns=d.close.columns), d, ZERO)
    assert levered["financing"].iloc[10] == pytest.approx(-1 * (0.04 / 252 + 0.01 / 252), rel=0.05)
    assert cash["ret"].iloc[10] == pytest.approx(0.04 / 252)


def test_spread_model_is_tight_for_liquid_and_wide_for_illiquid():
    idx = pd.bdate_range("2020-01-01", periods=200)
    rng = np.random.default_rng(1)
    px = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, [0.01, 0.03], (200, 2)), axis=0), index=idx, columns=["LIQ", "ILL"])
    vol = pd.DataFrame({"LIQ": 3e10 / px["LIQ"], "ILL": 2e6 / px["ILL"]})
    hs = codelab.half_spread_bps(px, vol).iloc[-1]
    assert hs["LIQ"] < 1 and 8 < hs["ILL"] < 30                 # calibration: ≈15 bp at 3% daily vol, $2m/day


def test_walk_forward_uses_only_the_past():
    idx = pd.bdate_range("2010-01-01", "2019-12-31")
    early = idx < pd.Timestamp("2015-01-01")
    a = pd.Series(np.where(early, 0.001, -0.001), index=idx)      # good early, bad late
    b = pd.Series(np.where(early, -0.0005, 0.002), index=idx)
    wf = codelab.walk_forward(lambda p: a if p["x"] == "a" else b, {"x": ["a", "b"]}, warmup_years=3)
    picks = {c["year"]: c["params"]["x"] for c in wf["chosen"]}
    assert picks[2013] == "a" and picks[2015] == "a"            # 2015 decided on data to end-2014
    assert picks[2019] == "b"                                    # once the past favours b


def test_monte_carlo_sizes_leverage_and_refuses_negative_edges():
    idx = pd.bdate_range("2010-01-01", periods=2500)
    rng = np.random.default_rng(3)
    good = pd.Series(rng.normal(0.0006, 0.008, 2500), index=idx)
    mc = codelab.monte_carlo(good, years=5, paths=400)
    assert mc["recommended_leverage"] <= 2 and mc["recommended_leverage"] <= mc["kelly_full"] / 2 + 0.25
    assert len(mc["fan"]) > 50 and mc["fan"][-1]["p5"] <= mc["fan"][-1]["p50"] <= mc["fan"][-1]["p95"]
    bad = pd.Series(rng.normal(-0.0005, 0.01, 2500), index=idx)
    assert codelab.monte_carlo(bad, years=5, paths=300)["recommended_leverage"] == 0.0


def test_sandbox_static_rules():
    ok = 'UNIVERSE = ["SPY"]\nPARAMS = {"n": [1, 2]}\ndef strategy(data, n=1):\n    return data.close * 0 + 1\n'
    assert sandbox.check(ok)["universe"] == ["SPY"]
    for fine in ('UNIVERSE=["SPY"]\ndef strategy(d):\n    return d.close if d.close.__class__ else d.close',
                 'UNIVERSE=["SP"+"Y"]\ndef strategy(d):\n    return d.close',
                 'UNIVERSE=["SPY"]\nPARAMS={"a": list(range(50))}\ndef strategy(d, a=1):\n    return d.close'):
        assert sandbox.check(fine)["universe"] == ["SPY"]          # ordinary Python, computed settings, bigger grids
    for bad in ('import os\nUNIVERSE=["SPY"]\ndef strategy(d):\n    return d.close',
                'import requests\nUNIVERSE=["SPY"]\ndef strategy(d):\n    return d.close',
                'UNIVERSE=["SPY"]\ndef strategy(d):\n    return eval("d.close")',
                'UNIVERSE=["SPY"]\ndef strategy(d):\n    return strategy.__globals__',
                'UNIVERSE=["SPY"]\nPARAMS={"a": list(range(30)), "b": list(range(30))}\ndef strategy(d, a=1, b=1):\n    return d.close'):
        with pytest.raises(sandbox.SandboxError):
            sandbox.check(bad)


def test_sandbox_runs_code_in_a_separate_process(monkeypatch):
    from api.quant import codeserver
    d = _data(k=2)
    d.close.columns = d.open.columns = d.high.columns = d.low.columns = d.volume.columns = ["SPY", "TLT"]
    d.tickers = ["SPY", "TLT"]
    monkeypatch.setattr(codeserver, "load_data", lambda u, s, end=None, **kw: d)
    monkeypatch.setattr(codeserver, "_index_series", lambda sym, start: d.close["SPY"])
    code = 'UNIVERSE = ["SPY", "TLT"]\nSTART = "2013-01-01"\ndef strategy(data):\n    return hold_monthly(data.close * 0 + 0.5)\n'
    res = sandbox.run(code)
    assert res["metrics"]["years"] > 3 and len(res["returns"]) == len(res["dates"])
    with pytest.raises(sandbox.SandboxError, match="KeyError"):
        sandbox.run('UNIVERSE = ["SPY"]\ndef strategy(data):\n    return data.close["NOPE"]\n')


def test_code_api_check_analyze_and_save(client, monkeypatch):  # noqa: F811
    from api.quant import codeserver
    monkeypatch.setattr(codeserver, "rf_for", lambda dates, account="USD": pd.Series(0.0, index=pd.to_datetime(dates)))
    good = 'UNIVERSE = ["SPY"]\ndef strategy(data):\n    return data.close * 0 + 1\n'
    assert client.post("/api/v1/quant/code/check", json={"code": good}).json()["ok"] is True
    assert client.post("/api/v1/quant/code/check", json={"code": "import os"}).json()["ok"] is False
    idx = pd.bdate_range("2015-01-01", periods=800)
    rets = list(np.random.default_rng(0).normal(0.0004, 0.01, 800))
    r = client.post("/api/v1/quant/code/analyze", json={"dates": [d.strftime("%Y-%m-%d") for d in idx], "returns": rets, "mc_paths": 300, "mc_years": 3})
    assert r.status_code == 200 and "monte_carlo" in r.json() and "deep" in r.json()
    s = client.post("/api/v1/quant/strategies", json={"spec": {"kind": "code", "name": "Mine", "code": good}})
    assert s.status_code == 200
    bad = client.post("/api/v1/quant/strategies", json={"spec": {"kind": "code", "name": "Bad", "code": "import os"}})
    assert bad.status_code == 400
    assert client.get("/api/v1/quant/code/engine").text.startswith('"""')


def test_monte_carlo_does_not_lever_a_weak_edge():
    idx = pd.bdate_range("2010-01-01", periods=2500)
    weak = pd.Series(np.random.default_rng(9).normal(0.00004, 0.002, 2500), index=idx)   # Sharpe ≈ 0.3 or less
    mc = codelab.monte_carlo(weak, years=5, paths=300)
    if mc["sharpe_excess"] < 0.3:
        assert mc["recommended_leverage"] <= 1.0


def test_stored_runs_round_trip_and_are_private(client):  # noqa: F811
    res = {"metrics": {"cagr": 0.1, "sharpe": 1.0}, "dates": ["2020-01-02", "2021-01-04"], "returns": [0.0, 0.01],
           "provenance": {"code_hash": "abc", "engine_version": "x", "universe": ["SPY"]},
           "validation": {"causality": {"passed": True}, "pbo": {"pbo": 0.2}}}
    r = client.post("/api/v1/quant/code/runs", json={"label": "My run", "result": res, "code": "UNIVERSE = ['SPY']"})
    assert r.status_code == 200
    rid = r.json()["id"]
    lst = client.get("/api/v1/quant/code/runs").json()["runs"]
    row = next(x for x in lst if x["id"] == rid)
    assert row["summary"]["sharpe"] == 1.0 and row["summary"]["causality"] is True and row["summary"]["pbo"] == 0.2
    full = client.get(f"/api/v1/quant/code/runs/{rid}").json()
    assert full["result"]["returns"] == [0.0, 0.01] and full["code"].startswith("UNIVERSE")
    assert client.delete(f"/api/v1/quant/code/runs/{rid}").json()["deleted"] is True
    assert client.get(f"/api/v1/quant/code/runs/{rid}").status_code == 404
