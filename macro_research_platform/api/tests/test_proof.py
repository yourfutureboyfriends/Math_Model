"""What-works scorecard: the deflated Sharpe ratio penalises many trials, CAPM alpha is measured right, and verdicts
separate alpha from beta."""
import numpy as np
import pytest

from api.quant import proof


def test_deflated_sharpe_falls_as_more_strategies_were_tried():
    rng = np.random.default_rng(3)
    r = rng.normal(0.0006, 0.01, 2500)                     # a decent daily Sharpe of ~0.06 (≈ 1 a year)
    one = proof.deflated_sharpe(r, 2, sr_var=0.0004)
    many = proof.deflated_sharpe(r, 200, sr_var=0.0004)
    assert one > many and 0 <= many <= 1
    assert proof.deflated_sharpe(rng.normal(0, 0.01, 2500), 50, 0.0004) < 0.5


def test_capm_separates_alpha_from_beta():
    rng = np.random.default_rng(4)
    b = rng.normal(0.0004, 0.01, 3000)
    pure_beta = 1.2 * b
    with_alpha = 0.8 * b + 0.0004 + rng.normal(0, 0.002, 3000)
    a = proof._capm(pure_beta, b)
    assert a["beta"] == pytest.approx(1.2) and abs(a["alpha"]) < 1e-9
    c = proof._capm(with_alpha, b)
    assert c["beta"] == pytest.approx(0.8, abs=0.02) and c["alpha"] == pytest.approx(0.1, abs=0.02) and c["alpha_t"] > 3


def test_verdicts():
    assert proof._verdict(0.04, 2.6, 0.95, 1.0) == "alpha"
    assert proof._verdict(0.04, 2.6, 0.5, 1.0) == "promising"          # significant but not after multiple testing
    assert proof._verdict(-0.001, -0.1, 0.8, 1.25) == "beta"
    assert proof._verdict(-0.02, -1.3, 0.0, 0.2) == "no edge"
    assert proof._verdict(0.0018, 2.5, 1.0, 0.0) == "no edge"           # significant but under 1% a year: not worth it
