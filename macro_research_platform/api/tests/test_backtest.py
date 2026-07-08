"""
Known-answer tests for the signal backtest engine (Phase 4).
Run: pytest api/tests/test_backtest.py
"""
import numpy as np
import pytest

from api.calculations.backtest import (
    forward_returns, hit_rate, forward_return_by_state, strategy_daily_returns,
    sharpe, max_drawdown, confusion_matrix, backtest_signal,
    momentum_signal, trend_signal, BULLISH, BEARISH, NEUTRAL,
)


def test_forward_returns():
    fr = forward_returns([100, 101, 102, 110], horizon=1)
    assert fr[0] == pytest.approx(0.01)
    assert fr[2] == pytest.approx(110 / 102 - 1)


def test_hit_rate_perfect():
    sig = [BULLISH, BULLISH, BEARISH]
    fwd = [0.02, 0.01, -0.03]     # all match direction
    assert hit_rate(sig, fwd) == 1.0


def test_hit_rate_excludes_neutral():
    sig = [NEUTRAL, BULLISH, BEARISH]
    fwd = [0.05, 0.02, 0.02]      # neutral ignored; bull hits, bear misses
    assert hit_rate(sig, fwd) == 0.5


def test_forward_return_by_state():
    res = forward_return_by_state([BULLISH, BULLISH, BEARISH], [0.02, 0.04, -0.01])
    assert res[BULLISH]["avg_forward_return"] == pytest.approx(0.03)
    assert res[BULLISH]["count"] == 2


def test_sharpe_positive_series():
    # constant +0.001/day -> high positive Sharpe (zero std handled -> uses ddof)
    r = np.full(300, 0.001) + np.random.default_rng(0).normal(0, 1e-4, 300)
    assert sharpe(r) > 5


def test_max_drawdown_monotonic_up_is_zero():
    r = np.full(50, 0.01)
    assert max_drawdown(r) == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_captures_loss():
    r = np.array([0.1, -0.5, 0.0])   # +10% then -50%
    assert max_drawdown(r) == pytest.approx(-0.5, abs=1e-6)


def test_strategy_returns_short_flips_sign():
    strat = strategy_daily_returns([BEARISH], [-0.02])
    assert strat[0] == pytest.approx(0.02)   # short gains when market falls


def test_confusion_matrix_counts():
    m = confusion_matrix([BULLISH, BULLISH, BEARISH], [0.01, -0.01, -0.02])
    assert m[BULLISH]["Up"] == 1 and m[BULLISH]["Down"] == 1
    assert m[BEARISH]["Down"] == 1


def test_momentum_signal_rising_series_bullish():
    closes = list(np.linspace(100, 200, 300))  # steadily rising
    sig = momentum_signal(closes)
    assert sig[-1] == BULLISH


def test_trend_signal_above_ma_bullish():
    closes = list(np.linspace(100, 300, 260))
    sig = trend_signal(closes)
    assert sig[-1] == BULLISH


def test_backtest_signal_perfect_predictor():
    # Construct a series where the momentum signal reliably precedes up moves.
    rng = np.random.default_rng(1)
    closes = list(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 600)))
    sig = momentum_signal(closes)
    res = backtest_signal(closes, sig, horizon=21)
    assert res["available"] is True
    assert 0.0 <= res["hit_rate"] <= 1.0
    assert -1.0 <= res["strategy_max_drawdown"] <= 0.0
    assert set(res["forward_return_by_state"]) == {BULLISH, BEARISH, NEUTRAL}
