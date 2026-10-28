"""Shadow reconciliation: the formula engine on the shared ledger vs the legacy simulator it replaced."""
import numpy as np
import pandas as pd
import pytest

from api.quant import engine, rates


@pytest.fixture(autouse=True)
def no_cash_rate(monkeypatch):
    monkeypatch.setattr(rates, "known", lambda: False)        # the legacy simulator paid no interest on cash


def _prep(spec, seed=0, n=900):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    syms = ["A", "B", "C", "D"]
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, (n, 4)), axis=0), index=idx, columns=syms)
    open_ = close.shift(1) * (1 + rng.normal(0, 0.002, (n, 4)))
    open_.iloc[0] = close.iloc[0]
    pan = {"close": close, "open": open_, "high": close, "low": close, "volume": close * 0 + 1e6}
    score = close.pct_change(126)
    vol = np.log(close / close.shift(1)).rolling(63, min_periods=40).std() * np.sqrt(252)
    return {"pan": pan, "uni": syms, "missing": [], "survivorship": False, "score": score, "filter": None, "vol": vol}


def _spec(**kw):
    base = {"universe": {"symbols": ["A", "B", "C", "D"]}, "signal": "mom(126)", "selection": {"mode": "top_n", "n": 2},
            "weighting": "equal", "rebalance": "monthly", "execution": "next_open", "costs": {"bps": 0, "borrow_bps": 0},
            "start": "2015-09-01"}
    base.update(kw)
    return engine.normalize(base)


@pytest.mark.parametrize("execution", ["next_open", "next_close"])
def test_zero_cost_ledger_matches_legacy_exactly(execution):
    spec = _spec(execution=execution)
    prep = _prep(spec)
    new, old = engine.simulate(spec, prep), engine.simulate_legacy(spec, prep)
    assert new["dates"] == old["dates"]
    np.testing.assert_allclose(np.cumprod(1 + new["net"]), np.cumprod(1 + old["net"]), rtol=1e-9, atol=1e-9)


def test_with_costs_the_ledger_differs_only_by_post_cost_sizing():
    spec = _spec(costs={"bps": 10, "borrow_bps": 0})
    prep = _prep(spec, seed=3)
    new, old = engine.simulate(spec, prep), engine.simulate_legacy(spec, prep)
    a, b = np.prod(1 + new["net"]), np.prod(1 + old["net"])
    assert a == pytest.approx(b, rel=2e-3)                      # same trades, fees paid from cash vs from weights
    assert new["ledger"]["reconciles"]


def test_long_short_and_delay_paths_run_on_the_ledger():
    spec = _spec(selection={"mode": "long_short", "n": 1}, costs={"bps": 5, "borrow_bps": 50})
    prep = _prep(spec, seed=5)
    new, lag = engine.simulate(spec, prep), engine.simulate(spec, prep, extra_lag=1)
    old = engine.simulate_legacy(spec, prep)
    assert np.prod(1 + new["net"]) == pytest.approx(np.prod(1 + old["net"]), rel=5e-3)
    assert not np.allclose(new["net"], lag["net"])            # the delay test really delays
    # exposures drift between monthly rebalances the same way in both
    assert new["gross_exp"].max() == pytest.approx(old["gross_exp"].max(), rel=0.02)
