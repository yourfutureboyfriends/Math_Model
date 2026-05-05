"""
Signal Validation

Statistical validation of trading signals.

Tests:
- Backtest performance
- Information coefficient
- Regime consistency
- Transaction cost sensitivity
- Out-of-sample robustness
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of signal validation."""
    signal_name: str
    validated: bool
    sharpe_ratio: float
    information_coefficient: float
    win_rate: float
    max_drawdown: float
    turnover: float
    sample_size: int
    out_of_sample_sharpe: float
    regime_consistency: float
    transaction_cost_impact: float
    failure_reasons: List[str]


class SignalValidator:
    """
    Validate trading signals through statistical testing.

    Implements multiple validation checks to ensure
    signals are robust before production.
    """

    # Validation thresholds
    MIN_SHARPE = 0.5
    MIN_IC = 0.05
    MAX_DRAWDOWN = 0.25
    MAX_TURNOVER = 2.0
    MIN_OUT_OF_SAMPLE = 0.3
    MIN_WIN_RATE = 0.45

    def __init__(
        self,
        min_sharpe: float = 0.5,
        min_ic: float = 0.05,
        max_drawdown: float = 0.25,
    ):
        self.min_sharpe = min_sharpe
        self.min_ic = min_ic
        self.max_drawdown = max_drawdown

    def validate_signal(
        self,
        signal_name: str,
        signal_series: pd.Series,
        returns: pd.Series,
        in_sample_split: float = 0.7,
        transaction_cost: float = 0.001,
    ) -> ValidationResult:
        """
        Run full validation suite on a signal.

        Args:
            signal_name: Name of the signal
            signal_series: Signal values (time series)
            returns: Asset returns (time series)
            in_sample_split: Fraction for in-sample
            transaction_cost: Cost per trade

        Returns:
            ValidationResult
        """
        failure_reasons = []

        # Align series
        aligned_data = pd.DataFrame({"signal": signal_series, "returns": returns}).dropna()

        if len(aligned_data) < 60:
            return ValidationResult(
                signal_name=signal_name,
                validated=False,
                sharpe_ratio=0.0,
                information_coefficient=0.0,
                win_rate=0.0,
                max_drawdown=0.0,
                turnover=0.0,
                sample_size=len(aligned_data),
                out_of_sample_sharpe=0.0,
                regime_consistency=0.0,
                transaction_cost_impact=0.0,
                failure_reasons=["Insufficient data (< 60 observations)"],
            )

        # Split in-sample / out-of-sample
        split_idx = int(len(aligned_data) * in_sample_split)
        in_sample = aligned_data.iloc[:split_idx]
        out_of_sample = aligned_data.iloc[split_idx:]

        # Calculate metrics
        sharpe = self._calculate_sharpe(in_sample)
        ic = self._calculate_ic(in_sample)
        win_rate = self._calculate_win_rate(in_sample)
        max_dd = self._calculate_max_drawdown(in_sample)
        turnover = self._calculate_turnover(in_sample["signal"])

        # Out-of-sample test
        oos_sharpe = self._calculate_sharpe(out_of_sample) if len(out_of_sample) >= 20 else 0.0

        # Regime consistency
        regime_consistency = self._test_regime_consistency(aligned_data)

        # Transaction cost impact
        cost_impact = self._estimate_transaction_cost_impact(in_sample, transaction_cost)

        # Determine if validated
        validated = True

        if sharpe < self.min_sharpe:
            validated = False
            failure_reasons.append(f"Sharpe {sharpe:.2f} < {self.min_sharpe}")

        if abs(ic) < self.min_ic:
            validated = False
            failure_reasons.append(f"IC {ic:.3f} < {self.min_ic}")

        if max_dd > self.max_drawdown:
            validated = False
            failure_reasons.append(f"Max DD {max_dd:.1%} > {self.max_drawdown}")

        if win_rate < self.MIN_WIN_RATE:
            validated = False
            failure_reasons.append(f"Win rate {win_rate:.1%} < {self.MIN_WIN_RATE}")

        if oos_sharpe < sharpe * self.MIN_OUT_OF_SAMPLE:
            validated = False
            failure_reasons.append(f"OOS Sharpe {oos_sharpe:.2f} significantly lower than IS {sharpe:.2f}")

        if cost_impact > sharpe * 0.5:
            validated = False
            failure_reasons.append(f"Transaction costs too high: {cost_impact:.2f}")

        return ValidationResult(
            signal_name=signal_name,
            validated=validated,
            sharpe_ratio=round(sharpe, 2),
            information_coefficient=round(ic, 3),
            win_rate=round(win_rate, 3),
            max_drawdown=round(max_dd, 4),
            turnover=round(turnover, 2),
            sample_size=len(aligned_data),
            out_of_sample_sharpe=round(oos_sharpe, 2),
            regime_consistency=round(regime_consistency, 2),
            transaction_cost_impact=round(cost_impact, 2),
            failure_reasons=failure_reasons,
        )

    def _calculate_sharpe(self, data: pd.DataFrame) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(data) < 20:
            return 0.0

        # Signal-weighted returns
        signal_returns = data["signal"].shift(1) * data["returns"]
        signal_returns = signal_returns.dropna()

        if len(signal_returns) < 10:
            return 0.0

        mean_return = signal_returns.mean()
        std_return = signal_returns.std()

        if std_return == 0:
            return 0.0

        # Annualize (assuming daily data)
        return (mean_return / std_return) * np.sqrt(252)

    def _calculate_ic(self, data: pd.DataFrame) -> float:
        """Calculate Information Coefficient (rank correlation)."""
        # Lead signal by 1 period
        aligned = pd.DataFrame({
            "signal": data["signal"].shift(1),
            "returns": data["returns"],
        }).dropna()

        if len(aligned) < 10:
            return 0.0

        # Spearman rank correlation
        correlation, p_value = stats.spearmanr(aligned["signal"], aligned["returns"])

        return correlation if not np.isnan(correlation) else 0.0

    def _calculate_win_rate(self, data: pd.DataFrame) -> float:
        """Calculate percentage of profitable trades."""
        signal_returns = data["signal"].shift(1) * data["returns"]
        signal_returns = signal_returns.dropna()

        if len(signal_returns) == 0:
            return 0.0

        return (signal_returns > 0).mean()

    def _calculate_max_drawdown(self, data: pd.DataFrame) -> float:
        """Calculate maximum drawdown."""
        signal_returns = data["signal"].shift(1) * data["returns"]
        signal_returns = signal_returns.dropna()

        if len(signal_returns) < 2:
            return 0.0

        cumulative = (1 + signal_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max

        return abs(drawdown.min())

    def _calculate_turnover(self, signal: pd.Series) -> float:
        """Calculate annualized turnover."""
        if len(signal) < 2:
            return 0.0

        # Turnover = sum of absolute changes
        changes = signal.diff().abs().sum()
        avg_position = signal.abs().mean()

        if avg_position == 0:
            return 0.0

        # Annualize (assuming daily data, 252 days/year)
        periods = len(signal)
        turnover = (changes / avg_position) * (252 / periods)

        return turnover

    def _test_regime_consistency(self, data: pd.DataFrame) -> float:
        """Test if signal works across different regimes."""
        # Split by return regime
        high_vol = data["returns"].abs() > data["returns"].abs().median()
        up_market = data["returns"] > 0

        regimes = {
            "high_vol": data[high_vol],
            "low_vol": data[~high_vol],
            "up_market": data[up_market],
            "down_market": data[~up_market],
        }

        sharpe_by_regime = {}
        for regime_name, regime_data in regimes.items():
            if len(regime_data) >= 20:
                sharpe_by_regime[regime_name] = self._calculate_sharpe(regime_data)

        if not sharpe_by_regime:
            return 0.0

        # Consistency = fraction of regimes with positive Sharpe
        positive_regimes = sum(1 for s in sharpe_by_regime.values() if s > 0)
        return positive_regimes / len(sharpe_by_regime)

    def _estimate_transaction_cost_impact(
        self,
        data: pd.DataFrame,
        cost_per_trade: float,
    ) -> float:
        """Estimate impact of transaction costs on Sharpe."""
        turnover = self._calculate_turnover(data["signal"])

        # Annual cost = turnover * cost per trade
        annual_cost = turnover * cost_per_trade

        # Impact on Sharpe (approximate)
        gross_sharpe = self._calculate_sharpe(data)

        if gross_sharpe == 0:
            return 0.0

        # Simplified: subtract cost from numerator
        signal_vol = (data["signal"].shift(1) * data["returns"]).std() * np.sqrt(252)
        net_sharpe = gross_sharpe - (annual_cost / signal_vol if signal_vol > 0 else 0)

        return gross_sharpe - net_sharpe

    def cross_validate_signal(
        self,
        signal_series: pd.Series,
        returns: pd.Series,
        n_folds: int = 5,
    ) -> Dict:
        """
        Perform cross-validation on signal.

        Args:
            signal_series: Signal values
            returns: Returns
            n_folds: Number of folds

        Returns:
            Cross-validation results
        """
        data = pd.DataFrame({"signal": signal_series, "returns": returns}).dropna()
        fold_size = len(data) // n_folds

        fold_results = []
        for i in range(n_folds):
            test_start = i * fold_size
            test_end = test_start + fold_size

            test_data = data.iloc[test_start:test_end]
            train_data = pd.concat([data.iloc[:test_start], data.iloc[test_end:]])

            train_sharpe = self._calculate_sharpe(train_data)
            test_sharpe = self._calculate_sharpe(test_data)

            fold_results.append({
                "fold": i + 1,
                "train_sharpe": train_sharpe,
                "test_sharpe": test_sharpe,
                "sharpe_decay": train_sharpe - test_sharpe,
            })

        avg_decay = np.mean([r["sharpe_decay"] for r in fold_results])

        return {
            "folds": fold_results,
            "average_train_sharpe": np.mean([r["train_sharpe"] for r in fold_results]),
            "average_test_sharpe": np.mean([r["test_sharpe"] for r in fold_results]),
            "average_decay": round(avg_decay, 2),
            "is_robust": avg_decay < 0.3,
        }

    def generate_validation_report(
        self,
        results: List[ValidationResult],
    ) -> Dict:
        """Generate validation report for multiple signals."""
        validated = [r for r in results if r.validated]
        rejected = [r for r in results if not r.validated]

        return {
            "summary": {
                "total_signals": len(results),
                "validated": len(validated),
                "rejected": len(rejected),
                "validation_rate": len(validated) / len(results) if results else 0,
            },
            "validated_signals": [
                {
                    "name": r.signal_name,
                    "sharpe": r.sharpe_ratio,
                    "ic": r.information_coefficient,
                    "win_rate": r.win_rate,
                }
                for r in validated
            ],
            "rejected_signals": [
                {
                    "name": r.signal_name,
                    "reasons": r.failure_reasons,
                }
                for r in rejected
            ],
            "statistics": {
                "avg_sharpe": np.mean([r.sharpe_ratio for r in results]),
                "avg_ic": np.mean([r.information_coefficient for r in results]),
                "avg_win_rate": np.mean([r.win_rate for r in results]),
            },
        }
