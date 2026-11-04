"""Stock-level optimiser: constraints, method properties, Black-Litterman views, no look-ahead."""
import numpy as np
import pytest

from api.calculations import optimizer as op


def _returns(n=6, T=900, seed=3):
    rng = np.random.default_rng(seed)
    vols = np.linspace(0.01, 0.03, n)
    common = rng.standard_normal(T)
    eps = rng.standard_normal((T, n))
    return 0.0003 + vols * (0.6 * common[:, None] + 0.8 * eps)


@pytest.mark.parametrize("method", op.METHODS)
def test_weights_valid_and_capped(method):
    r = _returns()
    cov = op.shrunk_cov(r)
    w = op.weights_for(method, r, cov, max_w=0.30, setup_scores=[0.5, -0.2, 0.1, 0.8, None, 0.0])
    assert w.shape == (6,) and abs(w.sum() - 1) < 1e-8 and (w >= -1e-12).all() and w.max() <= 0.30 + 1e-8


def test_method_properties():
    r = _returns()
    cov = op.shrunk_cov(r)
    ws = {m: op.weights_for(m, r, cov, max_w=1.0) for m in ("equal_weight", "min_variance", "erc", "max_diversification")}
    vol = {m: float(np.sqrt(w @ cov @ w)) for m, w in ws.items()}
    assert vol["min_variance"] <= min(vol.values()) + 1e-9
    rc = op.describe(ws["erc"], cov)["risk_contributions"]
    assert max(rc) - min(rc) < 0.01, "ERC equalises risk contributions"
    dr = {m: op.diversification_ratio(w, cov) for m, w in ws.items()}
    assert dr["max_diversification"] >= max(dr.values()) - 1e-6


def test_black_litterman_tilts_toward_positive_view():
    r = _returns()
    cov = op.shrunk_cov(r)
    flat = op.weights_for("black_litterman", r, cov, 1.0, setup_scores=[0.0] * 6)
    tilt = op.weights_for("black_litterman", r, cov, 1.0, setup_scores=[0.0, 0.0, 0.9, 0.0, 0.0, 0.0])
    assert tilt[2] > flat[2]


def test_cap_weights_redistributes():
    w = op.cap_weights(np.array([0.7, 0.2, 0.1]), 0.4)
    assert abs(w.sum() - 1) < 1e-12 and w.max() <= 0.4 + 1e-12 and w[1] > 0.2


def test_walk_forward_has_no_lookahead():
    r = _returns(T=700)
    a = op.walk_forward(r, "erc", 0.5, lookback=252, rebalance=21)
    r2 = r.copy()
    r2[600:] *= -3                                     # change only the future
    b = op.walk_forward(r2, "erc", 0.5, lookback=252, rebalance=21)
    k = 600 - 252
    assert np.allclose(a["nav"][:k], b["nav"][:k])


def test_infeasible_cap_is_raised_so_methods_can_differ(monkeypatch):
    from api import portfolio_optimizer as po
    r = _returns(n=3, T=800)
    dates = [f"2023-01-{k:04d}" for k in range(r.shape[0])]
    monkeypatch.setattr(po, "_usd_returns", lambda syms, years=3: (dates, ["A", "B", "C"], r,
                                                                 np.zeros_like(r), {"A": 1.0, "B": 1.0, "C": 1.0}))
    out = po.optimise(["A", "B", "C"], {"A": 1, "B": 1, "C": 1}, max_weight=0.25)
    assert abs(out["max_weight"] - 2 / 3) < 1e-9 and out["cap_note"]
    mv = next(m for m in out["methods"] if m["method"] == "min_variance")["weights"]
    assert max(mv.values()) > 0.34, "min-variance no longer forced to 1/N"
