"""
Backtesting module for macro regime model.

Provides:
- Walk-forward validation with no look-ahead bias
- Sensitivity analysis
- Performance metrics
- Look-ahead bias testing
"""

from .walk_forward_validator import (
    WalkForwardValidator,
    NoLookAheadTester,
    BacktestResult,
    run_realistic_backtest,
    run_revised_data_backtest,
)

from .sensitivity_analysis import (
    SensitivityAnalyzer,
    SensitivityResult,
    test_model_robustness,
)

__all__ = [
    # Walk-forward validation
    "WalkForwardValidator",
    "NoLookAheadTester",
    "BacktestResult",
    "run_realistic_backtest",
    "run_revised_data_backtest",
    # Sensitivity analysis
    "SensitivityAnalyzer",
    "SensitivityResult",
    "test_model_robustness",
]
