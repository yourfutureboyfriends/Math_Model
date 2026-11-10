"""Bridgewater frameworks — maths on synthetic data (offline)."""
import math

import numpy as np
import pandas as pd
import pytest

from api.marketdata import bridgewater as B, core


def test_quadrant_classification_signs(monkeypatch):
    idx = pd.date_range("2000-01-31", periods=60, freq="ME")
    ip = pd.Series(np.exp(np.linspace(0, 0.5, 60) ** 2), index=idx)          # accelerating growth
    cpi = pd.Series(np.exp(-np.linspace(0, 0.3, 60) ** 2) * 100, index=idx)   # decelerating prices
    monkeypatch.setattr(B, "_fred_monthly", lambda sid, years=90: ip if sid == "INDPRO" else cpi)
    core._cache.pop("bw:quads:6", None)
    q = B._quadrants()
    assert (q["g"].iloc[-12:] == 1).all() and (q["i"].iloc[-12:] == -1).all()
    assert B.SHORT[(1, -1)] == "Goldilocks"
    core._cache.pop("bw:quads:6", None)


def test_equal_risk_per_environment():
    rng = np.random.default_rng(3)
    syms = ["A", "B", "C", "D"]
    R = pd.DataFrame(rng.normal(0, [0.01, 0.02, 0.005, 0.015], size=(500, 4)), columns=syms)
    cov = R.cov() * 252
    w = B._inv_vol(cov, ["A", "B"])
    w = w / B._port_vol(w, cov)
    assert B._port_vol(w, cov) == pytest.approx(1.0)                          # one unit of risk
    assert w["A"] > w["B"]                                                    # less volatile → bigger weight


def test_holy_grail_curve_matches_formula():
    out = B.holy_grail([])
    row15 = next(r for r in out["curve"] if r["n"] == 15)
    assert row15["rho0"] == pytest.approx(math.sqrt(1 / 15))
    assert row15["rho60"] == pytest.approx(math.sqrt(1 / 15 + (14 / 15) * 0.6))
    assert row15["rho0"] < 0.3                                                # ~75% risk cut with 15 uncorrelated streams


def test_holy_grail_effective_bets(monkeypatch):
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2021-01-01", periods=800)
    base = rng.normal(0, 0.01, len(idx))
    cols = {"X1": base, "X2": base + rng.normal(0, 0.001, len(idx)), "Y": rng.normal(0, 0.01, len(idx)), "Z": rng.normal(0, 0.01, len(idx))}
    px = pd.DataFrame({k: 100 * np.cumprod(1 + v) for k, v in cols.items()}, index=idx)
    df = pd.concat({k: pd.DataFrame({"Close": px[k]}) for k in px}, axis=1)
    monkeypatch.setattr(B, "yahoo_download", lambda *a, **k: df)
    out = B.holy_grail(["X1", "X2", "Y", "Z"])
    assert 2.5 < out["effective_bets"] < 3.5                                  # X1 and X2 are the same bet
    assert out["most_correlated"][0]["rho"] > 0.9


def test_trader_targets_tilt_shifts_risk(monkeypatch):
    rng = np.random.default_rng(5)
    syms = sorted({s for v in B.TRADER_BUCKETS.values() for s in v})
    idx = pd.bdate_range("2023-01-01", periods=400)
    closes = {s: pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))}, index=idx) for s in syms}
    monkeypatch.setattr(B, "environments", lambda: {"current": {"nickname": "Stagflation"}})
    flat = B.all_weather_targets(False, 1.0, closes)
    tilt = B.all_weather_targets(True, 1.0, closes)
    assert sum(flat["weights"].values()) == pytest.approx(1.0)
    assert tilt["regime"] == "Stagflation"
    assert tilt["weights"]["GLD"] > flat["weights"]["GLD"]                    # rising-inflation assets gain risk
    assert tilt["weights"]["SPY"] < flat["weights"]["SPY"]                    # rising-growth / falling-inflation assets lose it
