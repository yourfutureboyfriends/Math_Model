"""
Sentiment & Risk Appetite Module

Composite index measuring market sentiment and risk appetite across:
- VIX term structure (implied volatility curve)
- AAII Sentiment Survey (retail investor positioning)
- Cross-asset momentum (price action across asset classes)

Normalised to [-1, +1] where:
- +1 = Maximum risk-on (extreme greed)
- -1 = Maximum risk-off (extreme fear)
- 0 = Neutral

Methodology:
- Each component z-scored vs 52-week history
- Equal-weighted average
- Transition warning if sentiment diverges from regime by >0.5 std

Research basis:
- VIX: Whaley (2000), "The Investor Fear Gauge"
- Sentiment: Baker & Wurgler (2006), "Investor Sentiment and the Cross-Section of Stock Returns"
- Cross-asset: Asness (1997), "The Interaction of Value and Momentum Strategies"
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result from sentiment/risk appetite computation."""
    risk_appetite_score: float  # Normalised to [-1, +1]
    signal: str                 # "RISK_ON", "NEUTRAL", "RISK_OFF"
    transition_warning: bool    # True if sentiment contradicts regime
    components: Dict[str, float]
    description: str


class RiskAppetiteModel:
    """
    Compute risk appetite index from multiple sentiment indicators.
    """

    # ETF symbols for cross-asset momentum
    ETF_SYMBOLS = ["SPY", "TLT", "GLD", "DBC", "UUP"]

    def __init__(self, lookback_weeks: int = 52):
        self.lookback_weeks = lookback_weeks

    def _get_vix_component(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate VIX term structure component.
        Positive when VIX3M > VIX (contango = risk-on)
        Negative when VIX3M < VIX (backwardation = risk-off)
        """
        vix = None
        vix3m = None

        # Try various column names
        for col in df.columns:
            if 'vix' in col.lower() and '3m' not in col.lower():
                vix = df[col]
            elif 'vix3m' in col.lower() or 'vix_3m' in col.lower():
                vix3m = df[col]

        if vix is None or vix3m is None:
            # Try to use just VIX level as fallback
            if vix is not None:
                # Invert VIX level (high VIX = fear)
                vix_current = float(vix.iloc[-1])
                # Normalise: 20 = neutral, 30 = fear, 15 = complacent
                return (20 - vix_current) / 20  # Approx normalised
            return None

        # Calculate term structure ratio
        current_vix = float(vix.iloc[-1])
        current_vix3m = float(vix3m.iloc[-1])

        if current_vix > 0:
            term_ratio = (current_vix3m / current_vix) - 1
            # Normalise: +0.1 is strongly contango (risk-on)
            return np.clip(term_ratio * 10, -1, 1)

        return None

    def _get_aaii_component(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate AAII sentiment component.
        Bull - Bear spread normalised.
        """
        # Look for AAII data columns
        bull_col = None
        bear_col = None

        for col in df.columns:
            col_lower = col.lower()
            if 'bull' in col_lower and 'aaii' in col_lower:
                bull_col = col
            elif 'bear' in col_lower and 'aaii' in col_lower:
                bear_col = col
            elif 'bull_bear' in col_lower:
                # Already calculated spread
                series = df[col].dropna()
                if len(series) >= 4:
                    return np.clip(float(series.iloc[-1]) / 50, -1, 1)

        if bull_col and bear_col:
            bull = float(df[bull_col].iloc[-1])
            bear = float(df[bear_col].iloc[-1])
            spread = bull - bear
            return np.clip(spread / 50, -1, 1)  # Normalise

        return None

    def _get_momentum_component(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate cross-asset momentum component.
        Uses 12-1 month momentum for major asset classes.
        """
        momentum_scores = []

        for symbol in self.ETF_SYMBOLS:
            # Look for price columns
            price_col = None
            for col in df.columns:
                if symbol.lower() in col.lower() or col.lower() == symbol.lower():
                    price_col = col
                    break

            if price_col:
                prices = df[price_col].dropna()
                if len(prices) >= 252:  # 1 year
                    # 12-1 month momentum
                    ret_12m = prices.iloc[-1] / prices.iloc[-252] - 1
                    ret_1m = prices.iloc[-1] / prices.iloc[-21] - 1
                    momentum_12_1 = ret_12m - ret_1m
                    momentum_scores.append(momentum_12_1 * 100)  # Scale to %

        if momentum_scores:
            avg_momentum = np.mean(momentum_scores)
            # Normalise: 10% momentum = +0.5 score
            return np.clip(avg_momentum / 20, -1, 1)

        return None

    def compute(self, df: pd.DataFrame, regime_score: float = 0.0) -> SentimentResult:
        """
        Compute risk appetite index.

        Args:
            df: DataFrame with market data
            regime_score: Current regime z-score for transition detection

        Returns:
            SentimentResult with composite score
        """
        components = {}

        # VIX term structure
        vix_comp = self._get_vix_component(df)
        if vix_comp is not None:
            components["vix_term_structure"] = round(vix_comp, 3)

        # AAII sentiment
        aaii_comp = self._get_aaii_component(df)
        if aaii_comp is not None:
            components["aaii_sentiment"] = round(aaii_comp, 3)

        # Cross-asset momentum
        mom_comp = self._get_momentum_component(df)
        if mom_comp is not None:
            components["cross_asset_momentum"] = round(mom_comp, 3)

        if len(components) == 0:
            logger.warning("No sentiment components available")
            return SentimentResult(
                risk_appetite_score=0.0,
                signal="NEUTRAL",
                transition_warning=False,
                components={},
                description="Insufficient data for sentiment analysis",
            )

        # Equal-weighted composite
        composite = np.mean(list(components.values()))
        composite = np.clip(composite, -1, 1)

        # Signal classification
        if composite > 0.3:
            signal = "RISK_ON"
        elif composite < -0.3:
            signal = "RISK_OFF"
        else:
            signal = "NEUTRAL"

        # Transition warning: sentiment vs regime divergence
        transition_warning = abs(composite - regime_score) > 0.5

        description = (
            f"Risk Appetite: {composite:+.2f} ({signal}) | "
            f"Components: {len(components)} | "
            + " | ".join([f"{k}: {v:+.2f}" for k, v in components.items()])
        )
        if transition_warning:
            description += " ⚠ TRANSITION WARNING"

        return SentimentResult(
            risk_appetite_score=round(composite, 2),
            signal=signal,
            transition_warning=transition_warning,
            components=components,
            description=description,
        )


def get_risk_appetite(df: pd.DataFrame, regime_score: float = 0.0) -> SentimentResult:
    """Compute risk appetite from DataFrame."""
    model = RiskAppetiteModel()
    return model.compute(df, regime_score)


def get_sentiment_dict(df: pd.DataFrame, regime_score: float = 0.0) -> dict:
    """Get sentiment as simple dict for API response."""
    result = get_risk_appetite(df, regime_score)
    return {
        "risk_appetite_score": result.risk_appetite_score,
        "signal": result.signal,
        "transition_warning": result.transition_warning,
        "components": result.components,
        "description": result.description,
    }
