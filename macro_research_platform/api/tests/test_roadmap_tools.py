"""Roadmap tools (Nov 2026): signal decay monitor and related helpers."""


def _monthly(values):
    return [(2010 + (i + 0.5) / 12, v) for i, v in enumerate(values)]


def test_decay_flags_a_signal_whose_edge_has_gone():
    from api.quant.decay import assess
    a = assess(_monthly([0.04] * 60 + [-0.01] * 36), 12)
    assert a["status"] == "gone" and a["retire"] is True and a["ic_recent"] < 0 < a["ic_early"]


def test_decay_half_life_and_fading():
    from api.quant.decay import assess
    a = assess(_monthly([0.04] * 60 + [0.02] * 36), 12)                 # halved: positive, watched, not retired
    assert a["status"] == "fading" and a["retire"] is False and a["half_life_years"] and a["half_life_years"] > 0


def test_decay_holding_up_emerging_and_short_history():
    from api.quant.decay import assess
    assert assess(_monthly([0.03] * 96), 12)["status"] == "holding up"
    assert assess(_monthly([-0.02] * 60 + [0.02] * 36), 12)["status"] == "emerging"
    assert assess(_monthly([0.03] * 10), 12)["status"] == "insufficient history"
    assert assess(_monthly([-0.01] * 96), 12)["status"] == "never worked"


def test_crisis_behaviour_separates_a_hedge_from_beta():
    import numpy as np
    import pandas as pd
    from api.quant.proof import _crisis
    days = pd.bdate_range("2015-01-01", "2022-12-30")
    rng = np.random.default_rng(1)
    b = rng.normal(0.0004, 0.01, len(days))
    beta = b.copy()                                   # moves with the index
    hedge = -0.3 * b + rng.normal(0.0002, 0.002, len(days))
    dates = [d.strftime("%Y-%m-%d") for d in days]
    hb, hh = _crisis(beta, b, dates), _crisis(hedge, b, dates)
    assert hb["crisis_return"] < 0 and hb["role"] is None and abs(hb["downside_capture"] - 1) < 1e-6
    assert hh["crisis_return"] > 0 and hh["role"] == "crisis diversifier"
