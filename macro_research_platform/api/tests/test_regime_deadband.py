"""A coin-flip axis (within the dead band of 0.5) keeps the previous regime's side instead of flipping on one day's
move; a clear move still switches regime."""
from api.calculations.regime import classify_regime


def test_dead_band_keeps_the_previous_regime():
    assert classify_regime(0.49, 0.62, 0.64)[0] == "stagflation"            # no history: the 0.5 split decides
    reg, conf, _ = classify_regime(0.49, 0.62, 0.64, previous="reflation")
    assert reg == "reflation" and conf == 0.5                               # inside the band: keep it, lower confidence


def test_a_clear_move_still_changes_regime():
    assert classify_regime(0.30, 0.62, 0.64, previous="reflation")[0] == "stagflation"
    assert classify_regime(0.47, 0.52, 0.50, previous="slowdown")[0] == "slowdown"   # both axes undecided: stay
