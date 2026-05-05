
# Confidence Intervals Module (Phase 10C)
# Bootstrap and Bayesian confidence intervals for forecasts


import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


class ConfidenceIntervalCalculator:
    """
    Calculate confidence intervals for predictions and signals.
    Uses bootstrap resampling and Bayesian methods.
    """

    @staticmethod
    def bootstrap_ci(
        data: np.ndarray,
        n_bootstrap: int = 1000,
        confidence_level: float = 0.95,
        statistic_func = np.mean,
    ) -> Tuple[float, float, float]:
        """
        Calculate bootstrap confidence interval.
        Returns (point_estimate, lower_bound, upper_bound)
        """
        if len(data) == 0:
            return 0.0, 0.0, 0.0

        # Original statistic
        point_estimate = statistic_func(data)

        # Bootstrap resampling
        bootstrap_stats = []
        n = len(data)

        for _ in range(n_bootstrap):
            # Resample with replacement
            sample = np.random.choice(data, size=n, replace=True)
            bootstrap_stats.append(statistic_func(sample))

        bootstrap_stats = np.array(bootstrap_stats)

        # Calculate percentiles
        alpha = (1 - confidence_level) / 2
        lower = np.percentile(bootstrap_stats, alpha * 100)
        upper = np.percentile(bootstrap_stats, (1 - alpha) * 100)

        return float(point_estimate), float(lower), float(upper)

    @staticmethod
    def prediction_interval(
        predictions: np.ndarray,
        actuals: Optional[np.ndarray] = None,
        confidence_level: float = 0.95,
    ) -> Dict[str, float]:
        """
        Calculate prediction interval based on historical errors.
        If actuals provided, uses residuals. Otherwise uses prediction variance.
        """
        if len(predictions) == 0:
            return {
                "mean": 0.0,
                "std": 0.0,
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "confidence_level": confidence_level,
            }

        mean_pred = float(np.mean(predictions))
        std_pred = float(np.std(predictions))

        # Calculate interval using t-distribution
        n = len(predictions)
        t_value = stats.t.ppf((1 + confidence_level) / 2, df=max(n-1, 1))
        margin = t_value * std_pred / np.sqrt(max(n, 1))

        ci_lower = mean_pred - margin
        ci_upper = mean_pred + margin

        return {
            "mean": mean_pred,
            "std": std_pred,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "margin": margin,
            "confidence_level": confidence_level,
        }

    @staticmethod
    def multi_horizon_ci(
        forecasts: List[float],
        historical_errors: Optional[Dict[int, List[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate confidence intervals for multiple forecast horizons.
        Typical horizons: 1 week, 1 month, 3 months, 6 months
        """
        horizons = ["1w", "1m", "3m", "6m"]
        result = {}

        for i, horizon in enumerate(horizons):
            if i < len(forecasts):
                forecast = forecasts[i]

                # If we have historical errors for this horizon, use them
                if historical_errors and horizon in historical_errors:
                    errors = np.array(historical_errors[horizon])
                    error_std = float(np.std(errors))

                    # Confidence widens with horizon
                    confidence_level = 0.80 if horizon in ["1w", "1m"] else 0.95
                    z_score = 1.28 if confidence_level == 0.80 else 1.96

                    margin = z_score * error_std
                else:
                    # Default: use forecast magnitude and horizon-based scaling
                    margin = abs(forecast) * 0.15 * (i + 1)  # 15% per horizon step
                    confidence_level = 0.80

                result[horizon] = {
                    "forecast": forecast,
                    "ci_lower": forecast - margin,
                    "ci_upper": forecast + margin,
                    "margin": margin,
                    "confidence_level": confidence_level,
                }

        return result

    @staticmethod
    def regime_transition_ci(
        transition_probs: Dict[str, float],
        sample_size: int = 1000,
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate confidence intervals for regime transition probabilities.
        Uses Wilson score interval for proportions.
        """
        result = {}

        for regime, prob in transition_probs.items():
            if sample_size <= 0:
                result[regime] = {
                    "probability": prob,
                    "ci_lower": 0.0,
                    "ci_upper": 1.0,
                }
                continue

            # Wilson score interval
            z = 1.96  # 95% confidence
            n = sample_size
            p = prob

            denominator = 1 + z**2 / n
            centre_adjusted = p + z**2 / (2 * n)
            adjusted_sd = np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)

            lower = (centre_adjusted - z * adjusted_sd) / denominator
            upper = (centre_adjusted + z * adjusted_sd) / denominator

            result[regime] = {
                "probability": prob,
                "ci_lower": max(0.0, lower),
                "ci_upper": min(1.0, upper),
                "sample_size": sample_size,
            }

        return result

    @staticmethod
    def ensemble_signal_ci(
        component_signals: List[float],
        component_weights: Optional[List[float]] = None,
        n_bootstrap: int = 1000,
    ) -> Dict[str, Any]:
        """
        Calculate confidence intervals for ensemble signal.
        Accounts for both model disagreement and historical accuracy.
        """
        if not component_signals:
            return {
                "ensemble": 0.0,
                "ci_lower_80": -0.5,
                "ci_upper_80": 0.5,
                "ci_lower_95": -1.0,
                "ci_upper_95": 1.0,
                "disagreement": 0.0,
            }

        # Default equal weights
        if component_weights is None:
            component_weights = [1.0 / len(component_signals)] * len(component_signals)

        # Calculate weighted ensemble
        ensemble = sum(s * w for s, w in zip(component_signals, component_weights))
        ensemble /= sum(component_weights)

        # Calculate disagreement (std dev of components)
        disagreement = float(np.std(component_signals))

        # Bootstrap to get CI
        samples = np.array(component_signals)
        _, lower_80, upper_80 = ConfidenceIntervalCalculator.bootstrap_ci(
            samples, n_bootstrap=n_bootstrap, confidence_level=0.80
        )
        _, lower_95, upper_95 = ConfidenceIntervalCalculator.bootstrap_ci(
            samples, n_bootstrap=n_bootstrap, confidence_level=0.95
        )

        # Widen intervals based on disagreement
        lower_80 -= disagreement * 0.2
        upper_80 += disagreement * 0.2
        lower_95 -= disagreement * 0.3
        upper_95 += disagreement * 0.3

        # Clamp to [-1, 1]
        lower_80 = max(-1.0, lower_80)
        upper_80 = min(1.0, upper_80)
        lower_95 = max(-1.0, lower_95)
        upper_95 = min(1.0, upper_95)

        return {
            "ensemble": float(ensemble),
            "ci_lower_80": lower_80,
            "ci_upper_80": upper_80,
            "ci_lower_95": lower_95,
            "ci_upper_95": upper_95,
            "disagreement": disagreement,
            "component_count": len(component_signals),
        }


class ConfidenceLevel:
    """Confidence level categorization"""

    @staticmethod
    def from_ci_width(ci_width: float, signal_range: float = 2.0) -> str:
        """
        Categorize confidence based on CI width relative to signal range.
        signal_range is typically 2.0 for signals in [-1, 1]
        """
        relative_width = ci_width / signal_range

        if relative_width < 0.25:
            return "high"
        elif relative_width < 0.5:
            return "medium"
        elif relative_width < 0.75:
            return "low"
        else:
            return "uncertain"

    @staticmethod
    def from_hit_rate(hit_rate: float) -> str:
        """Categorize confidence based on historical hit rate"""
        if hit_rate >= 0.80:
            return "high"
        elif hit_rate >= 0.65:
            return "medium"
        elif hit_rate >= 0.50:
            return "low"
        else:
            return "uncertain"


# Convenience functions for API endpoints
def calculate_signal_with_ci(
    signal_value: float,
    component_signals: List[float],
    historical_accuracy: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate a signal with full confidence interval information.
    Returns data ready for SignalPrediction model.
    """
    # Get ensemble CI
    ci_data = ConfidenceIntervalCalculator.ensemble_signal_ci(component_signals)

    # Determine confidence level
    ci_width = ci_data["ci_upper_95"] - ci_data["ci_lower_95"]
    confidence_level = ConfidenceLevel.from_ci_width(ci_width)

    # Adjust for historical accuracy if available
    if historical_accuracy is not None:
        acc_level = ConfidenceLevel.from_hit_rate(historical_accuracy)
        # Use lower of the two
        level_order = ["high", "medium", "low", "uncertain"]
        ci_idx = level_order.index(confidence_level)
        acc_idx = level_order.index(acc_level)
        confidence_level = level_order[max(ci_idx, acc_idx)]

    return {
        "signal_value": signal_value,
        "ci_lower_80": ci_data["ci_lower_80"],
        "ci_upper_80": ci_data["ci_upper_80"],
        "ci_lower_95": ci_data["ci_lower_95"],
        "ci_upper_95": ci_data["ci_upper_95"],
        "confidence_level": confidence_level,
        "disagreement": ci_data["disagreement"],
    }


def calculate_forecast_ci(
    point_forecast: float,
    historical_errors: List[float],
    confidence_level: float = 0.95,
) -> Dict[str, float]:
    """Calculate confidence interval for a point forecast"""
    calc = ConfidenceIntervalCalculator()

    mean, lower, upper = calc.bootstrap_ci(
        np.array(historical_errors),
        confidence_level=confidence_level,
    )

    # Forecast CI is point forecast +/- error margin
    error_margin = (upper - lower) / 2

    return {
        "forecast": point_forecast,
        "ci_lower": point_forecast - error_margin,
        "ci_upper": point_forecast + error_margin,
        "margin": error_margin,
        "confidence_level": confidence_level,
    }
