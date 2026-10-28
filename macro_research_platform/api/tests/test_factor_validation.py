"""Known-answer tests for factor OOS validation (Phase 4)."""
import numpy as np
from api.calculations.factor_validation import validate_factor, validate_factors


def test_stable_factor_survives_oos():
    rng = np.random.default_rng(1)
    f = rng.normal(0, 0.01, 300)
    asset = 1.2 * f + rng.normal(0, 0.002, 300)      # genuine, persistent exposure
    r = validate_factor("real", f, asset)
    assert r["available"] and not r["unstable"]
    assert r["out_of_sample_r2"] > 0.5


def test_spurious_factor_flagged_unstable():
    rng = np.random.default_rng(2)
    f = rng.normal(0, 0.01, 200)
    asset = rng.normal(0, 0.01, 200)                 # no real relationship
    r = validate_factor("noise", f, asset)
    assert r["available"] and r["unstable"]


def test_too_few_obs_unavailable():
    r = validate_factor("tiny", [0.1] * 10, [0.2] * 10)
    assert not r["available"]


def test_validate_factors_summary():
    rng = np.random.default_rng(3)
    f_real = rng.normal(0, 0.01, 300)
    asset = 1.0 * f_real + rng.normal(0, 0.002, 300)
    f_noise = rng.normal(0, 0.01, 300)
    out = validate_factors({"real": f_real, "noise": f_noise}, asset)
    assert out["n_tested"] == 2
    assert "noise" in out["unstable_factors"]
