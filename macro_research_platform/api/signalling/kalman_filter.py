"""
Kalman Filter Signal Cleaner — Optimal Noise Reduction

Implements a Kalman filter for macroeconomic indicator smoothing.
The Kalman filter is optimal for estimating hidden states (true macro signal)
from noisy observations (reported data with sampling error, revision noise).

Mathematical Foundation:
- State equation: x_t = F*x_{t-1} + w_t  (state evolution)
- Observation:   z_t = H*x_t + v_t       (noisy measurement)
- Kalman gain K minimizes posterior estimate covariance

Applied to macro data:
- Measurement noise: data revisions, sampling error, seasonal adjustment residual
- Process noise: true changes in underlying economic conditions
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class KalmanResult:
    """Result from Kalman filter smoothing."""
    original: pd.Series
    smoothed: pd.Series
    trend: pd.Series
    variance: pd.Series
    signal_strength: float


class MacroKalmanFilter:
    """
    One-dimensional Kalman filter for macroeconomic time series.

    Optimized for monthly macro data where:
    - Observations are noisy (revisions, sampling error)
    - True state evolves gradually (economic conditions change slowly)
    """

    def __init__(
        self,
        process_noise: float = 0.01,
        measurement_noise: float = 1.0,
        initial_variance: float = 1.0,
    ):
        self.Q = process_noise  # Process noise variance
        self.R = measurement_noise  # Measurement noise variance
        self.P0 = initial_variance  # Initial estimate variance

    def filter(self, series: pd.Series) -> KalmanResult:
        """
        Apply Kalman filter to smooth a time series.

        Returns both filtered (lagging) and smoothed (using all data) estimates.
        """
        values = series.dropna().values
        dates = series.dropna().index

        if len(values) < 3:
            logger.warning("Insufficient data for Kalman filter (< 3 observations)")
            return KalmanResult(
                original=series,
                smoothed=series,
                trend=series,
                variance=pd.Series(1.0, index=series.index),
                signal_strength=0.0,
            )

        # Initialize
        n = len(values)
        x_filt = np.zeros(n)  # Filtered estimates
        x_pred = np.zeros(n)  # Predicted estimates
        P_filt = np.zeros(n)  # Filtered variance
        P_pred = np.zeros(n)  # Predicted variance

        # Initial conditions
        x_filt[0] = values[0]
        P_filt[0] = self.P0

        # Forward pass (filtering)
        for t in range(1, n):
            # Prediction
            x_pred[t] = x_filt[t - 1]  # Random walk assumption
            P_pred[t] = P_filt[t - 1] + self.Q

            # Update
            K = P_pred[t] / (P_pred[t] + self.R)  # Kalman gain
            x_filt[t] = x_pred[t] + K * (values[t] - x_pred[t])
            P_filt[t] = (1 - K) * P_pred[t]

        # Backward pass (smoothing) - Rauch-Tung-Striebel smoother
        x_smooth = np.zeros(n)
        P_smooth = np.zeros(n)
        x_smooth[-1] = x_filt[-1]
        P_smooth[-1] = P_filt[-1]

        for t in range(n - 2, -1, -1):
            C = P_filt[t] / (P_filt[t] + self.Q)  # Smoother gain
            x_smooth[t] = x_filt[t] + C * (x_smooth[t + 1] - x_pred[t + 1])
            P_smooth[t] = P_filt[t] + C * C * (P_smooth[t + 1] - P_pred[t + 1])

        # Calculate trend (first derivative of smoothed series)
        trend = np.gradient(x_smooth)

        # Signal strength: variance explained by filtered vs original
        signal_strength = 1 - np.var(values - x_smooth) / np.var(values)
        signal_strength = max(0, min(1, signal_strength))  # Bound [0, 1]

        return KalmanResult(
            original=pd.Series(values, index=dates),
            smoothed=pd.Series(x_smooth, index=dates),
            trend=pd.Series(trend, index=dates),
            variance=pd.Series(P_smooth, index=dates),
            signal_strength=round(float(signal_strength), 3),
        )

    def filter_dataframe(
        self, df: pd.DataFrame, columns: Optional[List[str]] = None
    ) -> Dict[str, KalmanResult]:
        """Apply Kalman filter to multiple columns of a DataFrame."""
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns.tolist()

        results = {}
        for col in columns:
            if col in df.columns:
                try:
                    results[col] = self.filter(df[col])
                except Exception as e:
                    logger.warning(f"Kalman filter failed for {col}: {e}")

        return results


def detect_signal_change(
    result: KalmanResult, threshold: float = 2.0
) -> Optional[Dict]:
    """
    Detect statistically significant changes in the smoothed signal.

    Returns dict with change info if detected, None otherwise.
    """
    if len(result.trend) < 2:
        return None

    # Current values
    current_smooth = result.smoothed.iloc[-1]
    current_trend = result.trend.iloc[-1]
    current_var = result.variance.iloc[-1]

    # Historical stats
    hist_std = result.smoothed.std()

    # Detect acceleration/deceleration
    z_score = current_trend / (np.sqrt(current_var) + 1e-6)

    if abs(z_score) > threshold:
        return {
            "detected": True,
            "direction": "accelerating" if z_score > 0 else "decelerating",
            "z_score": round(float(z_score), 2),
            "confidence": round(min(abs(z_score) / 3, 1.0), 2),
            "current_value": round(float(current_smooth), 3),
            "signal_strength": result.signal_strength,
        }

    return {"detected": False, "z_score": round(float(z_score), 2)}


def apply_kalman_to_macro_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function: apply Kalman smoothing to common macro indicators.
    Returns DataFrame with both original and smoothed columns.
    """
    kf = MacroKalmanFilter(process_noise=0.05, measurement_noise=0.5)

    # Common macro columns to smooth
    macro_cols = [
        "gdp_growth", "us_cpi", "core_cpi_yoy", "us_10y_yield",
        "unemployment_rate", "us_pmi", "consumer_confidence",
    ]

    available_cols = [c for c in macro_cols if c in df.columns]
    results = kf.filter_dataframe(df, available_cols)

    # Build output DataFrame
    out_df = df.copy()
    for col, result in results.items():
        out_df[f"{col}_kf"] = result.smoothed
        out_df[f"{col}_kf_trend"] = result.trend

    return out_df
