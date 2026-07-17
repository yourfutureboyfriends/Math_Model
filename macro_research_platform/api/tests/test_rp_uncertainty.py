"""Known-answer tests for RP risk-contribution uncertainty bands (Phase 2C)."""
import numpy as np
from api.calculations.risk_parity import risk_contribution_bands


def _returns(seed=0):
    rng = np.random.default_rng(seed)
    return np.column_stack([rng.normal(0, 0.005, 300), rng.normal(0, 0.01, 300), rng.normal(0, 0.03, 300)])


def test_bands_available_and_shaped():
    r = risk_contribution_bands(_returns(), n_boot=100)
    assert r["available"]
    assert len(r["per_asset"]) == 3
    for a in r["per_asset"]:
        assert a["p5"] <= a["mean_risk_share"] <= a["p95"]


def test_too_few_obs_unavailable():
    r = risk_contribution_bands(np.zeros((5, 3)), n_boot=10)
    assert not r["available"]


def test_fragility_ratio_present():
    r = risk_contribution_bands(_returns(1), n_boot=100)
    assert "fragility_ratio" in r and r["fragility_ratio"] >= 0
