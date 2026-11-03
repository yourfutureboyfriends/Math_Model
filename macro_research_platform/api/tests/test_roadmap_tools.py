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
