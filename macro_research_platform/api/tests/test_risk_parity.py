"""Known-answer tests for risk-parity allocation methods (Phase 2)."""
import numpy as np
from api.calculations.risk_parity import (
    inverse_vol_weights, cvar_weights, hrp_weights, return_overlay_weights,
    sixty_forty, backtest,
)


def _returns(seed=0):
    rng = np.random.default_rng(seed)
    # 3 assets: low-vol, mid-vol, high-vol
    return np.column_stack([rng.normal(0, 0.005, 500), rng.normal(0, 0.01, 500), rng.normal(0, 0.03, 500)])


def test_inverse_vol_weights_favor_low_vol():
    w = inverse_vol_weights(_returns())
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] > w[1] > w[2]                     # lowest vol gets the most weight


def test_cvar_weights_sum_to_one_and_favor_low_tail():
    w = cvar_weights(_returns())
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] > w[2]                            # low tail-risk asset weighted higher


def test_hrp_weights_valid():
    w = hrp_weights(_returns())
    assert abs(w.sum() - 1.0) < 1e-9
    assert (w >= 0).all() and len(w) == 3


def test_return_overlay_tilts_toward_high_expected_return():
    r = _returns()
    w_plain = inverse_vol_weights(r)
    w_tilt = return_overlay_weights(r, expected_returns=[1, 1, 10], blend=0.5)
    assert w_tilt[2] > w_plain[2]                 # tilt lifts the high-ER asset


def test_sixty_forty_split():
    w = sixty_forty(["SPX Equity", "US Bonds (TLT)"])
    assert abs(w[0] - 0.6) < 1e-9 and abs(w[1] - 0.4) < 1e-9


def test_backtest_metrics_present():
    m = backtest(inverse_vol_weights(_returns()), _returns())
    for k in ("sharpe", "sortino", "max_drawdown_pct", "ann_return_pct", "ann_vol_pct"):
        assert k in m
    assert m["max_drawdown_pct"] <= 0
