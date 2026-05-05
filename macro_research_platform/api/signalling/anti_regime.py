"""
RESEARCH-1: Anti-Regime Detector (SSRN 5164863, 2025)

Academic basis: Periods maximally dissimilar to today predict the OPPOSITE
of what those periods subsequently produced. This is a contrarian signal
with significant out-of-sample alpha.

Reference: Man Group / AQR Research, March 2025
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass

# State variables for similarity comparison
STATE_VARS = [
    'GDPC1',      # Real GDP
    'CPIAUCSL',   # CPI
    'FEDFUNDS',   # Fed Funds Rate
    'T10Y2Y',     # Yield curve spread
    'BAMLH0A0HYM2',  # HY spreads
    'VIXCLS',     # VIX
    'M2SL',       # M2 Money Supply
    'ICSA',       # Jobless Claims
]

# Asset columns for forward return calculation
ASSET_COLS = ['SP500', 'GS10', 'GOLDAMGBD228NLBM', 'DCOILWTICO']


@dataclass
class AntiRegimeResult:
    """Result from anti-regime detection."""
    signal: str  # BULLISH or BEARISH
    anti_periods: List[str]  # Dates of anti-regime periods
    asset_signals: Dict[str, Dict]  # Per-asset contrarian signals
    k_periods: int
    description: str
    confidence: float


class AntiRegimeDetector:
    """
    Finds K historical periods most dissimilar to current state.
    Inverts their subsequent returns as a contrarian signal.

    Per SSRN 5164863 (Man Group / AQR, March 2025).
    """

    def __init__(self, k: int = 10, forward_horizon: int = 3):
        """
        Initialize detector.

        Args:
            k: Number of most dissimilar periods to find
            forward_horizon: Months ahead to calculate forward returns
        """
        self.k = k
        self.forward_horizon = forward_horizon

    def detect(self, df: pd.DataFrame) -> AntiRegimeResult:
        """
        Detect anti-regime signal from historical data.

        Args:
            df: DataFrame with macroeconomic time series

        Returns:
            AntiRegimeResult with contrarian signal
        """
        available_cols = [c for c in STATE_VARS if c in df.columns]
        if len(available_cols) < 3:
            return AntiRegimeResult(
                signal="INSUFFICIENT_DATA",
                anti_periods=[],
                asset_signals={},
                k_periods=self.k,
                description="Insufficient state variables for anti-regime detection",
                confidence=0.0
            )

        # Normalise state space
        state_df = df[available_cols].dropna()
        if len(state_df) < self.k + self.forward_horizon + 10:
            return AntiRegimeResult(
                signal="INSUFFICIENT_DATA",
                anti_periods=[],
                asset_signals={},
                k_periods=self.k,
                description="Insufficient historical data for anti-regime detection",
                confidence=0.0
            )

        # Z-score normalization
        means = state_df.mean()
        stds = state_df.std()
        # Avoid division by zero
        stds = stds.replace(0, 1e-8)
        normed = (state_df - means) / stds

        # Current state (last observation)
        today = normed.iloc[-1].values

        # Euclidean distance from today for each historical row
        distances = normed.iloc[:-self.forward_horizon].apply(
            lambda row: float(np.linalg.norm(row.values - today)),
            axis=1
        )

        # Get K most dissimilar periods (largest distance)
        anti_idx = distances.nlargest(self.k).index

        # Calculate forward returns after each anti-period
        anti_signals = {}
        for col in ASSET_COLS:
            if col not in df.columns:
                continue

            fwd_rets = []
            for idx in anti_idx:
                loc = df.index.get_loc(idx)
                ahead = loc + self.forward_horizon
                if ahead < len(df):
                    try:
                        ret = float(df[col].iloc[ahead] / df[col].iloc[loc] - 1)
                        fwd_rets.append(ret)
                    except (TypeError, ZeroDivisionError):
                        continue

            if fwd_rets:
                mean_ret = float(np.mean(fwd_rets))
                # Invert: anti-regime return → contrarian signal
                anti_signals[col] = {
                    "anti_regime_return": round(mean_ret, 4),
                    "contrarian_signal": "BULLISH" if mean_ret < 0 else "BEARISH",
                    "magnitude": round(abs(mean_ret), 4),
                }

        # Summary signal based on majority of assets
        if anti_signals:
            bullish_count = sum(
                1 for v in anti_signals.values()
                if v['contrarian_signal'] == 'BULLISH'
            )
            net_signal = (
                "BULLISH"
                if bullish_count > len(anti_signals) / 2
                else "BEARISH"
            )
            confidence = max(bullish_count, len(anti_signals) - bullish_count) / len(anti_signals)
        else:
            net_signal = "NEUTRAL"
            confidence = 0.0

        return AntiRegimeResult(
            signal=net_signal,
            anti_periods=[str(i.date()) for i in anti_idx[:5]],
            asset_signals=anti_signals,
            k_periods=self.k,
            description=(
                f"Top {self.k} most dissimilar historical periods identified. "
                f"Contrarian signal: {net_signal} with {confidence:.0%} confidence."
            ),
            confidence=round(confidence, 2)
        )

    def to_dict(self, result: AntiRegimeResult) -> Dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "signal": result.signal,
            "anti_periods": result.anti_periods,
            "asset_signals": result.asset_signals,
            "k_periods": result.k_periods,
            "description": result.description,
            "confidence": result.confidence,
        }


def compute_anti_regime_signal(df: pd.DataFrame, k: int = 10) -> Dict:
    """
    Convenience function to compute anti-regime signal.

    Args:
        df: DataFrame with macroeconomic data
        k: Number of periods to analyze

    Returns:
        Dictionary with anti-regime signal data
    """
    detector = AntiRegimeDetector(k=k)
    result = detector.detect(df)
    return detector.to_dict(result)
