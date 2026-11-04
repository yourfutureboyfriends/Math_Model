"""Geopolitical tail risk from observed indices (GPR, EPU, STLFSI) and the options panel's Cboe put/call — offline."""
import asyncio

import numpy as np
import pandas as pd
import pytest

from api.handlers import signal_handler as sh


def _series(n=1200, jump=0.0, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-10-20", periods=n)
    v = 100 + rng.normal(0, 5, n)
    v[-10:] += jump
    return [d.strftime("%Y-%m-%d") for d in idx], v.tolist()


def test_component_zscore_and_trend():
    d, v = _series(jump=40)
    c = sh._risk_component(d, v, "x", 7)
    assert c["zscore"] > 2 and c["trend"] == "Rising" and c["asOf"] == "2026-10-20"
    d, v = _series(jump=0)
    assert abs(sh._risk_component(d, v, "x", 7)["zscore"]) < 1.5
    assert sh._risk_component(d[:30], v[:30], "x", 7) is None                  # too short to judge


def test_geopolitical_endpoint_combines_observed_components(monkeypatch):
    from api.marketdata import freedata
    from api.handlers import macro_inputs
    d, v = _series(jump=60, seed=2)
    monkeypatch.setattr(freedata, "gpr_daily", lambda: {"dates": d, "gpr": v, "events": [{"date": "2022-02-25", "event": " Russia / Ukraine "}]})

    class S:
        def __init__(self, dates, values):
            self.dates, self.values = dates, values
    monkeypatch.setattr(macro_inputs, "_fetch_fred_history_sync", lambda sid, days: S(*_series(seed=3 if sid == "USEPUINDXD" else 4)))
    r = asyncio.run(sh.get_geopolitical_data())
    assert set(r["components"]) == {"geopoliticalRisk", "policyUncertainty", "financialStress"}
    zs = [c["zscore"] for c in r["components"].values()]
    assert r["tailRiskScore"] == pytest.approx(round(sum(zs) / 3, 2))
    assert r["tailRiskLevel"] in ("Extreme", "Elevated", "Moderate", "Low")
    assert r["notableEvents"][0]["event"] == "Russia / Ukraine"


def test_geopolitical_endpoint_says_why_when_every_source_fails(monkeypatch):
    from fastapi import HTTPException
    from api.marketdata import freedata
    from api.handlers import macro_inputs

    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(freedata, "gpr_daily", boom)
    monkeypatch.setattr(macro_inputs, "_fetch_fred_history_sync", boom)
    with pytest.raises(HTTPException) as e:
        asyncio.run(sh.get_geopolitical_data())
    assert e.value.status_code == 503 and "GPR unavailable" in e.value.detail
