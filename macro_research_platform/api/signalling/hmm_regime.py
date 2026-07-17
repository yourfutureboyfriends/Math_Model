"""
Hidden Markov Model Regime Detection — Probabilistic Regime Classification

Implements HMM-based regime detection using hmmlearn.
Unlike rule-based regime classification, HMM provides:
1. Probabilistic regime assignment (soft classification)
2. Transition probability matrix between regimes
3. Expected regime duration (from transition matrix)

Academic Reference:
- Hamilton (1989) "A New Approach to the Economic Analysis of Nonstationary Time Series"
- Applications in market regime detection: Nguyen (2014), etc.

Model specification:
- States: 4 macro regimes (Goldilocks, Reflation, Stagflation, Slowdown)
- Observations: Growth and inflation z-scores (2D Gaussian emissions)
- Transition: Estimated from data or constrained by economic theory
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    from hmmlearn import hmm
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False
    logger.warning("hmmlearn not installed. HMM regime detection disabled.")


@dataclass
class HMMRegimeResult:
    """Result from HMM regime detection."""
    regime_probs: pd.DataFrame  # Probabilities for each regime
    decoded_regime: pd.Series   # Most likely regime sequence
    transition_matrix: pd.DataFrame
    regime_stability: float      # 1 - probability of switching
    current_regime: str
    regime_confidence: float
    expected_duration: Dict[str, float]
    log_likelihood: float
    aic: float
    bic: float


# Economic regime definitions (matching existing framework)
REGIME_NAMES = ["Goldilocks", "Reflation", "Stagflation", "Slowdown"]


class HMMRegimeDetector:
    """
    Hidden Markov Model for macro regime detection.

    Uses 2D observations (growth, inflation) to classify into 4 regimes.
    Can be trained on historical data or use prior constraints.
    """

    def __init__(
        self,
        n_regimes: int = 4,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: int = 42,
    ):
        self.n_regimes = n_regimes
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state
        self.model: Optional[hmm.GaussianHMM] = None

    def fit(self, observations: np.ndarray) -> "HMMRegimeDetector":
        """
        Fit HMM to historical observations.

        Args:
            observations: Array of shape (n_samples, n_features)
                         Typically [[growth_zscore, inflation_zscore], ...]
        """
        if not HMMLEARN_AVAILABLE:
            raise ImportError("hmmlearn required for HMM regime detection")

        if len(observations) < 24:
            raise ValueError("Need at least 24 observations to fit HMM")

        # Initialize with specific transition constraints (economic regimes are sticky)
        self.model = hmm.GaussianHMM(
            n_components=self.n_regimes,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.random_state,
        )

        # Fit model
        self.model.fit(observations)

        logger.info(
            f"HMM fitted: log_likelihood={self.model.monitor_.history[-1]:.2f}, "
            f"converged={self.model.monitor_.converged}"
        )

        return self

    def decode(self, observations: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Decode most likely regime sequence using Viterbi algorithm.

        Returns:
            log_prob: Log probability of sequence
            state_sequence: Most likely regime at each time
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        return self.model.decode(observations)

    def predict_regimes(self, observations: np.ndarray) -> HMMRegimeResult:
        """
        Predict regime probabilities for observations.

        Returns full result object with probabilities, decoded regime,
        transition matrix, and diagnostics.
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        # Get regime probabilities at each time
        probs = self.model.predict_proba(observations)

        # Decode most likely sequence
        log_prob, decoded = self.model.decode(observations)

        # Build DataFrames
        n_samples = len(observations)
        regime_names = REGIME_NAMES[: self.n_regimes]

        prob_df = pd.DataFrame(
            probs,
            columns=[f"{r}_prob" for r in regime_names],
        )
        prob_df["most_likely"] = [regime_names[i] for i in decoded]

        # Transition matrix
        trans_df = pd.DataFrame(
            self.model.transmat_,
            index=regime_names,
            columns=regime_names,
        )

        # Current regime (last observation)
        current_idx = decoded[-1]
        current_regime = regime_names[current_idx]
        current_probs = probs[-1]
        regime_confidence = float(current_probs[current_idx])

        # Regime stability (1 - probability of switching)
        stability = np.trace(self.model.transmat_) / self.n_regimes

        # Expected duration in each regime (geometric distribution mean)
        expected_duration = {}
        for i, name in enumerate(regime_names):
            p_stay = self.model.transmat_[i, i]
            expected_duration[name] = round(1 / (1 - p_stay + 1e-6), 1)

        # Information criteria
        n_params = (
            self.n_regimes * 2  # means
            + self.n_regimes * 4  # covariances (full)
            + self.n_regimes * (self.n_regimes - 1)  # transitions
        )
        aic = -2 * log_prob + 2 * n_params
        bic = -2 * log_prob + n_params * np.log(n_samples)

        return HMMRegimeResult(
            regime_probs=prob_df,
            decoded_regime=pd.Series(
                [regime_names[i] for i in decoded],
                index=range(n_samples),
            ),
            transition_matrix=trans_df,
            regime_stability=round(float(stability), 3),
            current_regime=current_regime,
            regime_confidence=round(regime_confidence, 3),
            expected_duration=expected_duration,
            log_likelihood=round(float(log_prob), 2),
            aic=round(float(aic), 2),
            bic=round(float(bic), 2),
        )


def prepare_observations(
    df: pd.DataFrame,
    growth_col: str = "gdp_growth",
    inflation_col: str = "us_cpi",
) -> Tuple[np.ndarray, pd.DatetimeIndex]:
    """
    Prepare macro data for HMM regime detection.

    Returns observations array and dates for alignment.
    """
    # Get z-scores for stationarity
    growth = df[growth_col].dropna()
    inflation = df[inflation_col].dropna()

    # Align dates
    common_idx = growth.index.intersection(inflation.index)
    growth = growth.loc[common_idx]
    inflation = inflation.loc[common_idx]

    # Calculate z-scores (standardize)
    growth_z = (growth - growth.mean()) / growth.std()
    inflation_z = (inflation - inflation.mean()) / inflation.std()

    observations = np.column_stack([growth_z.values, inflation_z.values])

    return observations, common_idx


def detect_regime_with_hmm(
    df: pd.DataFrame,
    growth_col: str = "gdp_growth",
    inflation_col: str = "us_cpi",
) -> Optional[HMMRegimeResult]:
    """
    Convenience function: detect regime using HMM on macro data.

    Fits HMM and returns full result object.
    """
    if not HMMLEARN_AVAILABLE:
        logger.warning("hmmlearn not available, skipping HMM regime detection")
        return None

    try:
        observations, dates = prepare_observations(df, growth_col, inflation_col)

        if len(observations) < 24:
            logger.warning("Insufficient data for HMM regime detection")
            return None

        detector = HMMRegimeDetector(n_regimes=4)
        detector.fit(observations)
        result = detector.predict_regimes(observations)

        return result

    except Exception as e:
        logger.error(f"HMM regime detection failed: {e}")
        return None


def get_regime_transition_summary(result: HMMRegimeResult) -> Dict:
    """
    Generate human-readable summary of regime transitions.
    """
    trans = result.transition_matrix

    # Most likely next regime from current
    current = result.current_regime
    next_probs = trans.loc[current].sort_values(ascending=False)

    return {
        "current_regime": current,
        "regime_confidence": result.regime_confidence,
        "stability_score": result.regime_stability,
        "most_likely_transitions": {
            regime: round(prob, 3)
            for regime, prob in next_probs.head(2).items()
        },
        "expected_duration_months": result.expected_duration.get(current, 0),
        "model_fit": {
            "log_likelihood": result.log_likelihood,
            "aic": result.aic,
            "bic": result.bic,
        },
    }
