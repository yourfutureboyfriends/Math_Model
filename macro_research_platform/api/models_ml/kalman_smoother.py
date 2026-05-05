"""
Kalman Filter Signal Smoother for macro signal scores.

Academic basis:
  Kalman, R.E. (1960). A New Approach to Linear Filtering and
  Prediction Problems. Journal of Basic Engineering, 82(1), 35-45.

  Rauch, H.E., Tung, F. & Striebel, C.T. (1965). Maximum
  Likelihood Estimates of Linear Dynamic Systems.
  AIAA Journal, 3(8), 1445-1450.

Key insight:
  Signal scores are noisy observations of an underlying latent
  state. The Kalman filter provides optimal (MSE) estimates
  of this state, with the RTS smoother providing optimal
  offline estimates using all available data.

Model specification:
  State:     x_t = F * x_{t-1} + w_t   (constant velocity)
  Observation: z_t = H * x_t + v_t

  F = [[1, dt],     H = [[1, 0]]
       [0,  1 ]]

  w_t ~ N(0, Q), v_t ~ N(0, R)

Usage:
  smoother = SignalKalmanSmoother()
  smoothed = smoother.smooth(signal_scores, timestamps)

  # Singleton access
  smoother = get_signal_smoother()
  result = smoother.apply_to_dataframe(df, 'growth_score')
"""

import numpy as np
import pandas as pd
from typing import Optional, Union
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

try:
    from filterpy.kalman import KalmanFilter
    from filterpy.common import Q_discrete_white_noise
    FILTERPY_AVAILABLE = True
except ImportError:
    logger.warning("[KALMAN] filterpy not installed. Using fallback EWMA smoother.")
    FILTERPY_AVAILABLE = False


class SignalKalmanSmoother:
    """
    Kalman Filter + RTS Smoother for signal denoising.

    Uses constant-velocity motion model with adaptive
    process noise based on observed signal variance.
    """

    def __init__(
        self,
        dt: float = 1.0,
        dim_z: int = 1,
        process_noise: Optional[float] = None,
        measurement_noise: Optional[float] = None,
    ):
        """
        Initialize smoother.

        Args:
            dt: Time step (default 1.0 for monthly data)
            dim_z: Observation dimension (1 for scalar signals)
            process_noise: Q scalar (auto-estimated if None)
            measurement_noise: R scalar (auto-estimated if None)
        """
        self.dt = dt
        self.dim_z = dim_z
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self._kf: Optional['KalmanFilter'] = None
        self.fitted = False
        self.fit_stats: dict = {}

    def _build_filter(self) -> 'KalmanFilter':
        """Construct constant-velocity Kalman filter."""
        if not FILTERPY_AVAILABLE:
            raise RuntimeError("filterpy required for KalmanFilter")

        kf = KalmanFilter(dim_x=2, dim_z=self.dim_z)

        # State transition: constant velocity model
        # x = [position, velocity]'
        kf.F = np.array([
            [1.0, self.dt],
            [0.0, 1.0],
        ])

        # Observation matrix: observe position only
        kf.H = np.array([[1.0, 0.0]])

        # Process noise covariance
        if self.process_noise is not None:
            # Manual Q
            q = self.process_noise
            kf.Q = np.array([
                [q * self.dt**4 / 4, q * self.dt**3 / 2],
                [q * self.dt**3 / 2, q * self.dt**2],
            ])
        else:
            # Use filterpy's white noise model
            kf.Q = Q_discrete_white_noise(dim=2, dt=self.dt, var=0.01)

        # Measurement noise
        if self.measurement_noise is not None:
            kf.R = np.array([[self.measurement_noise]])
        else:
            kf.R = np.array([[0.1]])  # Default, will be estimated

        return kf

    def fit(self, measurements: np.ndarray) -> dict:
        """
        Estimate noise parameters from data.

        Uses first-difference variance for Q and
        residual variance after detrending for R.
        """
        if len(measurements) < 10:
            logger.warning(f"[KALMAN] Only {len(measurements)} samples for fitting")
            return {"error": "insufficient_data"}

        # Estimate process noise from velocity variance
        diffs = np.diff(measurements.flatten())
        q_estimate = float(np.var(diffs)) if len(diffs) > 0 else 0.01

        # Estimate measurement noise from residuals after EWMA detrend
        ewma = pd.Series(measurements.flatten()).ewm(span=6).mean().values
        residuals = measurements.flatten() - ewma
        r_estimate = float(np.var(residuals))

        self.process_noise = self.process_noise or max(q_estimate, 1e-6)
        self.measurement_noise = self.measurement_noise or max(r_estimate, 1e-6)

        self.fit_stats = {
            "n_samples": len(measurements),
            "process_noise_Q": round(self.process_noise, 6),
            "measurement_noise_R": round(self.measurement_noise, 6),
            "signal_variance": round(float(np.var(measurements)), 4),
            "fitted_at": datetime.utcnow().isoformat(),
        }

        self.fitted = True
        logger.info(
            f"[KALMAN] Fit complete: Q={self.process_noise:.4f}, R={self.measurement_noise:.4f}"
        )
        return self.fit_stats

    def smooth(
        self,
        measurements: Union[np.ndarray, list, pd.Series],
        timestamps: Optional[Union[pd.DatetimeIndex, list]] = None,
    ) -> dict:
        """
        Apply Kalman filter and RTS smoother to signal.

        Args:
            measurements: Raw signal values (n_samples,)
            timestamps: Optional timestamps for output alignment

        Returns:
            dict with smoothed values, filter output, and diagnostics
        """
        if not FILTERPY_AVAILABLE:
            return self._ewma_fallback(measurements, timestamps)

        z = np.atleast_1d(measurements).flatten()
        n = len(z)

        if n < 2:
            return {
                "smoothed": z.tolist(),
                "method": "kalman",
                "error": "insufficient_data",
            }

        # Auto-fit if not done
        if not self.fitted:
            self.fit(z)

        # Build and initialize filter
        kf = self._build_filter()

        # Initialize state: position = first measurement, velocity = 0
        kf.x = np.array([[z[0]], [0.0]])
        kf.P = np.array([[self.measurement_noise, 0.0],
                         [0.0, self.process_noise]])

        # Run forward filter
        means = []
        covariances = []

        for i, zi in enumerate(z):
            kf.predict()
            kf.update(np.array([[zi]]))
            means.append(kf.x.copy())
            covariances.append(kf.P.copy())

        # RTS Smoother (backward pass)
        n_states = len(means)
        smoothed = [means[-1]]  # Start with last filtered estimate

        for k in range(n_states - 2, -1, -1):
            # Predict from k to k+1
            x_pred = kf.F @ means[k]
            P_pred = kf.F @ covariances[k] @ kf.F.T + kf.Q

            # Smoother gain
            try:
                J = covariances[k] @ kf.F.T @ np.linalg.inv(P_pred)
            except np.linalg.LinAlgError:
                J = np.zeros((2, 2))

            # Smoothed estimate
            x_smooth = means[k] + J @ (smoothed[0] - x_pred)
            smoothed.insert(0, x_smooth)

        # Extract smoothed positions
        smoothed_positions = [float(s[0]) for s in smoothed]
        filtered_positions = [float(m[0]) for m in means]

        # Estimate uncertainty
        uncertainties = [float(np.sqrt(c[0, 0])) for c in covariances]

        # Compute smoothing gain (variance reduction)
        raw_var = np.var(z)
        smooth_var = np.var(smoothed_positions)
        noise_reduction = 1 - (smooth_var / raw_var) if raw_var > 0 else 0

        result = {
            "smoothed": smoothed_positions,
            "filtered": filtered_positions,
            "uncertainty": uncertainties,
            "raw": z.tolist(),
            "method": "kalman_rts",
            "noise_reduction_pct": round(noise_reduction * 100, 2),
            "n_samples": n,
            "params": {
                "dt": self.dt,
                "Q": self.process_noise,
                "R": self.measurement_noise,
            },
        }

        if timestamps is not None:
            result["timestamps"] = [str(t) for t in timestamps]

        return result

    def _ewma_fallback(
        self,
        measurements: Union[np.ndarray, list, pd.Series],
        timestamps: Optional[Union[pd.DatetimeIndex, list]] = None,
    ) -> dict:
        """EWMA fallback when filterpy unavailable."""
        z = pd.Series(measurements)
        smoothed = z.ewm(span=6, adjust=False).mean()

        result = {
            "smoothed": smoothed.tolist(),
            "raw": z.tolist(),
            "method": "ewma_fallback",
            "noise_reduction_pct": None,
        }

        if timestamps is not None:
            result["timestamps"] = [str(t) for t in timestamps]

        return result

    def apply_to_dataframe(
        self,
        df: pd.DataFrame,
        column: str,
        output_col: Optional[str] = None,
        date_col: str = "date",
    ) -> pd.DataFrame:
        """
        Apply smoothing to a DataFrame column.

        Args:
            df: Input DataFrame
            column: Column name to smooth
            output_col: Output column name (default: {column}_smoothed)
            date_col: Date column for alignment

        Returns:
            DataFrame with smoothed column added
        """
        output_col = output_col or f"{column}_smoothed"

        if column not in df.columns:
            logger.warning(f"[KALMAN] Column {column} not in DataFrame")
            return df

        values = df[column].values
        timestamps = df.get(date_col, df.index)

        result = self.smooth(values, timestamps)

        df[output_col] = result["smoothed"]
        df[f"{column}_uncertainty"] = result.get("uncertainty", [None] * len(df))

        return df


# ── Singleton ───────────────────────────────────────────

_kalman_smoother: Optional[SignalKalmanSmoother] = None


def get_signal_smoother() -> SignalKalmanSmoother:
    """Return singleton. Creates on first call."""
    global _kalman_smoother
    if _kalman_smoother is None:
        _kalman_smoother = SignalKalmanSmoother()
    return _kalman_smoother


def reset_smoother() -> SignalKalmanSmoother:
    """Force new instance with fresh parameters."""
    global _kalman_smoother
    _kalman_smoother = SignalKalmanSmoother()
    return _kalman_smoother
