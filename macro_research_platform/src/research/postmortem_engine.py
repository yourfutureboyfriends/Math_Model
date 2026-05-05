"""
Postmortem Engine

Analyzes why signals or strategies failed.

Key questions:
1. Was the hypothesis wrong?
2. Did the regime change?
3. Was it an execution issue?
4. Was it bad luck (statistical variance)?
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class PostmortemAnalysis:
    """Result of postmortem analysis."""
    signal_name: str
    analysis_date: datetime
    performance_period: tuple  # (start, end)
    total_return: float
    expected_return: float
    return_gap: float  # Actual - Expected

    # Attribution
    alpha_attribution: Dict[str, float]  # Factor contributions
    timing_attribution: Dict[str, float]  # Timing contributions
    stock_selection: float  # Security selection

    # Root causes
    primary_failure_mode: str
    secondary_factors: List[str]
    confidence: float  # 0-1

    # Recommendations
    recommended_action: str
    parameter_adjustments: Dict[str, float]
    regime_restrictions: List[str]


class PostmortemEngine:
    """
    Analyze strategy and signal failures.

    Implements systematic postmortem to learn from losses
    and improve future performance.
    """

    FAILURE_MODES = {
        "regime_change": "Economic regime changed, signal no longer applicable",
        "factor_crowding": "Too many investors using similar signal, alpha decay",
        "model_misspecification": "Model didn't capture true relationship",
        "data_lookahead": "Lookahead bias in backtest",
        "execution_slippage": "Execution costs higher than expected",
        "tail_event": "Unexpected tail event, bad luck",
        "overfitting": "Signal overfit to historical data",
        "structural_break": "Structural change in relationship",
    }

    def __init__(self):
        self.analyses: Dict[str, List[PostmortemAnalysis]] = {}

    def analyze_signal_failure(
        self,
        signal_name: str,
        signal_series: pd.Series,
        returns: pd.Series,
        expected_returns: pd.Series,
        regime_data: Optional[pd.Series] = None,
        benchmark_returns: Optional[pd.Series] = None,
    ) -> PostmortemAnalysis:
        """
        Analyze why a signal underperformed.

        Args:
            signal_name: Name of signal
            signal_series: Signal values
            returns: Actual returns
            expected_returns: Expected returns from model
            regime_data: Regime classification
            benchmark_returns: Benchmark for comparison

        Returns:
            PostmortemAnalysis
        """
        # Calculate performance
        actual_return = returns.sum()
        expected_return = expected_returns.sum()
        return_gap = actual_return - expected_return

        # Attribution analysis
        attribution = self._perform_attribution(signal_series, returns, expected_returns)

        # Identify failure mode
        failure_mode, confidence = self._identify_failure_mode(
            signal_series, returns, regime_data
        )

        # Secondary factors
        secondary = self._identify_secondary_factors(
            signal_series, returns, benchmark_returns
        )

        # Recommendations
        recommendation = self._generate_recommendation(failure_mode, confidence)
        adjustments = self._suggest_parameter_adjustments(failure_mode, signal_series)
        restrictions = self._suggest_regime_restrictions(failure_mode, regime_data)

        analysis = PostmortemAnalysis(
            signal_name=signal_name,
            analysis_date=datetime.now(),
            performance_period=(returns.index[0], returns.index[-1]),
            total_return=round(actual_return, 4),
            expected_return=round(expected_return, 4),
            return_gap=round(return_gap, 4),
            alpha_attribution=attribution.get("alpha", {}),
            timing_attribution=attribution.get("timing", {}),
            stock_selection=attribution.get("selection", 0.0),
            primary_failure_mode=failure_mode,
            secondary_factors=secondary,
            confidence=round(confidence, 2),
            recommended_action=recommendation,
            parameter_adjustments=adjustments,
            regime_restrictions=restrictions,
        )

        # Store analysis
        if signal_name not in self.analyses:
            self.analyses[signal_name] = []
        self.analyses[signal_name].append(analysis)

        return analysis

    def _perform_attribution(
        self,
        signal: pd.Series,
        returns: pd.Series,
        expected_returns: pd.Series,
    ) -> Dict:
        """Perform return attribution."""
        # Timing attribution
        signal_lag = signal.shift(1).dropna()
        aligned_returns = returns[returns.index.isin(signal_lag.index)]

        if len(aligned_returns) < 10:
            return {"alpha": {}, "timing": {}, "selection": 0.0}

        # Correlation with timing
        timing_corr = np.corrcoef(signal_lag, aligned_returns)[0, 1]
        if np.isnan(timing_corr):
            timing_corr = 0.0

        # Selection attribution (simplified)
        selection = (aligned_returns - expected_returns[expected_returns.index.isin(aligned_returns.index)]).mean()

        return {
            "alpha": {"signal_contribution": timing_corr * aligned_returns.std()},
            "timing": {"correlation": timing_corr},
            "selection": selection,
        }

    def _identify_failure_mode(
        self,
        signal: pd.Series,
        returns: pd.Series,
        regime_data: Optional[pd.Series],
    ) -> tuple:
        """Identify primary failure mode."""
        scores = {}

        # Regime change check
        if regime_data is not None and len(regime_data) > 10:
            recent_regime = regime_data.iloc[-1]
            historical_regime = regime_data.iloc[:-10].mode()
            if len(historical_regime) > 0 and recent_regime != historical_regime[0]:
                scores["regime_change"] = 0.8

        # Overfitting check (Sharpe decay)
        if len(returns) >= 60:
            first_half = returns.iloc[: len(returns) // 2]
            second_half = returns.iloc[len(returns) // 2 :]

            if len(first_half) > 0 and len(second_half) > 0:
                first_sharpe = first_half.mean() / first_half.std() if first_half.std() > 0 else 0
                second_sharpe = second_half.mean() / second_half.std() if second_half.std() > 0 else 0

                if first_sharpe > 0.5 and second_sharpe < 0:
                    scores["overfitting"] = 0.7

        # Tail event check
        return_vol = returns.std()
        if return_vol > 0:
            z_scores = (returns - returns.mean()) / return_vol
            tail_events = (np.abs(z_scores) > 3).sum()
            if tail_events > len(returns) * 0.05:
                scores["tail_event"] = 0.6

        # Factor crowding (high correlation with recent market)
        if returns.std() > 0:
            signal_returns = signal.shift(1) * returns
            if signal_returns.std() > 0:
                # Check if alpha decayed
                recent_alpha = signal_returns.iloc[-20:].mean()
                historical_alpha = signal_returns.iloc[:-20].mean()
                if historical_alpha > 0 and recent_alpha < 0:
                    scores["factor_crowding"] = 0.5

        # Default to model misspecification if no clear signal
        if not scores:
            return "model_misspecification", 0.5

        # Return highest scoring failure mode
        best_mode = max(scores, key=scores.get)
        return best_mode, scores[best_mode]

    def _identify_secondary_factors(
        self,
        signal: pd.Series,
        returns: pd.Series,
        benchmark: Optional[pd.Series],
    ) -> List[str]:
        """Identify secondary contributing factors."""
        factors = []

        # Check for high volatility
        if returns.std() > 0.03:  # Daily vol > 3%
            factors.append("high_volatility_environment")

        # Check for benchmark divergence
        if benchmark is not None:
            common_idx = returns.index.intersection(benchmark.index)
            if len(common_idx) > 20:
                bench_aligned = benchmark.loc[common_idx]
                returns_aligned = returns.loc[common_idx]
                corr = np.corrcoef(returns_aligned, bench_aligned)[0, 1]
                if np.isnan(corr) or abs(corr) < 0.3:
                    factors.append("low_correlation_to_benchmark")

        # Check for signal decay
        if len(signal) >= 60:
            early_signal = signal.iloc[:30].std()
            late_signal = signal.iloc[-30:].std()
            if early_signal > 0 and late_signal / early_signal < 0.5:
                factors.append("signal_magnitude_decay")

        return factors

    def _generate_recommendation(
        self,
        failure_mode: str,
        confidence: float,
    ) -> str:
        """Generate recommended action."""
        recommendations = {
            "regime_change": "Temporarily disable signal, retrain on new regime",
            "factor_crowding": "Reduce position size, seek uncorrelated signals",
            "model_misspecification": "Rebuild model with different assumptions",
            "data_lookahead": "Investigate data pipeline for lookahead bias",
            "execution_slippage": "Review execution strategy and cost assumptions",
            "tail_event": "Implement tail risk hedging, maintain signal",
            "overfitting": "Increase regularization, simplify model",
            "structural_break": "Retrain model from structural break date",
        }

        if confidence < 0.5:
            return "Investigate further - confidence too low for specific recommendation"

        return recommendations.get(failure_mode, "Investigate and monitor closely")

    def _suggest_parameter_adjustments(
        self,
        failure_mode: str,
        signal: pd.Series,
    ) -> Dict[str, float]:
        """Suggest parameter adjustments."""
        adjustments = {}

        if failure_mode == "overfitting":
            # Increase smoothing
            adjustments["smoothing_factor"] = 0.5
            adjustments["lookback_periods"] = int(len(signal) * 0.3)

        elif failure_mode == "regime_change":
            # Shorter lookback for faster adaptation
            adjustments["lookback_periods"] = int(len(signal) * 0.15)
            adjustments["regime_detection_sensitivity"] = 0.8

        elif failure_mode == "factor_crowding":
            # Reduce position sizes
            adjustments["position_size_multiplier"] = 0.5
            adjustments["confidence_threshold"] = 0.7

        return adjustments

    def _suggest_regime_restrictions(
        self,
        failure_mode: str,
        regime_data: Optional[pd.Series],
    ) -> List[str]:
        """Suggest regime-based restrictions."""
        restrictions = []

        if failure_mode == "regime_change" and regime_data is not None:
            current_regime = regime_data.iloc[-1]
            restrictions.append(f"disable_in_{current_regime}_regime")

        if failure_mode == "tail_event":
            restrictions.append("reduce_size_in_high_vol")
            restrictions.append("implement_stop_loss")

        return restrictions

    def generate_postmortem_report(
        self,
        signal_name: str,
    ) -> Dict:
        """Generate comprehensive postmortem report."""
        analyses = self.analyses.get(signal_name, [])

        if not analyses:
            return {"error": "No analyses found for signal"}

        latest = analyses[-1]

        # Pattern analysis
        failure_modes = [a.primary_failure_mode for a in analyses]
        mode_frequency = {}
        for mode in failure_modes:
            mode_frequency[mode] = mode_frequency.get(mode, 0) + 1

        most_common = max(mode_frequency, key=mode_frequency.get)

        return {
            "signal": signal_name,
            "latest_analysis": {
                "date": latest.analysis_date,
                "failure_mode": latest.primary_failure_mode,
                "confidence": latest.confidence,
                "return_gap": latest.return_gap,
                "recommendation": latest.recommended_action,
            },
            "historical_pattern": {
                "total_analyses": len(analyses),
                "most_common_failure": most_common,
                "frequency": mode_frequency[most_common] / len(analyses),
            },
            "improvement_suggestions": [
                f"Address {most_common} which has occurred {mode_frequency[most_common]} times",
                "Review parameter adjustments suggested in recent analyses",
                "Consider regime-based signal switching",
            ],
        }


def calculate_alpha_decay(
    signal_series: pd.Series,
    returns: pd.Series,
    window: int = 60,
) -> pd.Series:
    """
    Calculate rolling alpha decay.

    Args:
        signal_series: Signal values
        returns: Returns
        window: Rolling window

    Returns:
        Alpha decay series
    """
    if len(signal_series) < window:
        return pd.Series(index=signal_series.index)

    alpha_decay = []

    for i in range(window, len(signal_series)):
        window_signal = signal_series.iloc[i - window : i]
        window_returns = returns.iloc[i - window : i]

        # Calculate signal effectiveness in window
        signal_returns = window_signal.shift(1) * window_returns
        if signal_returns.std() > 0:
            sharpe = signal_returns.mean() / signal_returns.std() * np.sqrt(252)
        else:
            sharpe = 0

        alpha_decay.append(sharpe)

    return pd.Series(alpha_decay, index=signal_series.index[window:])


def detect_regime_change(
    returns: pd.Series,
    lookback: int = 60,
    threshold: float = 2.0,
) -> Optional[datetime]:
    """
    Detect structural regime change using Chow test.

    Args:
        returns: Return series
        lookback: Lookback period
        threshold: Statistical threshold

    Returns:
        Date of regime change or None
    """
    if len(returns) < lookback * 2:
        return None

    # Simplified: look for large change in mean/vol
    rolling_mean = returns.rolling(lookback).mean()
    rolling_vol = returns.rolling(lookback).std()

    # Z-score of current vs historical
    mean_z = (rolling_mean - rolling_mean.mean()) / rolling_mean.std()
    vol_z = (rolling_vol - rolling_vol.mean()) / rolling_vol.std()

    # Find where both exceed threshold
    regime_change = (np.abs(mean_z) > threshold) & (np.abs(vol_z) > threshold)

    if regime_change.any():
        return regime_change.idxmax()

    return None
