"""
Market Confirmation Model

Validates macro signals against market price action.
Key principle: "Markets lead the economy, not the other way around"

Uses trend-following and momentum signals to:
1. Confirm macro regime classifications
2. Identify divergences (macro vs market disagreement)
3. Provide early warning of regime shifts

Based on:
- Moskowitz, Ooi & Pedersen (2012) - Time series momentum
- Hurst, Ooi & Pedersen (2017) - Momentum in macro factors
- Asness value/momentum research
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TrendSignal(Enum):
    STRONG_CONFIRM = "strong_confirm"
    CONFIRM = "confirm"
    NEUTRAL = "neutral"
    DIVERGE = "diverge"
    STRONG_DIVERGE = "strong_diverge"


@dataclass
class TrendConfirmationResult:
    """Trend confirmation result."""
    overall_signal: TrendSignal
    confirmation_score: float  # -1 to 1, positive = confirms
    macro_market_alignment: float  # 0-1, 1 = perfect alignment
    asset_signals: Dict[str, Dict]
    divergence_warnings: List[str]
    confidence: float


class MarketConfirmationModel:
    """
    Market Confirmation Model

    Compares macro regime signals with actual market trends
    to validate or flag potential divergences.
    """

    # Asset class mappings by regime preference
    REGIME_ASSET_PREFERENCE = {
        "Goldilocks": {
            "equities": 1.0,
            "credit": 0.5,
            "rates": -0.3,  # Rates rise
            "commodities": 0.3,
            "dollar": -0.2,
        },
        "Reflation": {
            "equities": 0.8,
            "credit": 0.3,
            "rates": -0.5,  # Rates rise more
            "commodities": 0.8,
            "dollar": -0.1,
        },
        "Slowdown": {
            "equities": -0.5,
            "credit": -0.3,
            "rates": 0.5,  # Rates fall
            "commodities": -0.5,
            "dollar": 0.2,
        },
        "Stagflation": {
            "equities": -0.8,
            "credit": -0.5,
            "rates": -0.3,  # Rates constrained
            "commodities": 0.8,
            "dollar": 0.0,
        },
        # Intermediate/Mixed regimes - map to closest primary
        "Inflation Pressure / Late-Cycle": {
            "equities": -0.2,  # Slightly negative as valuations pressured
            "credit": -0.2,
            "rates": -0.3,  # Rates rising
            "commodities": 0.5,
            "dollar": 0.1,
        },
        "Recovery / Mixed": {
            "equities": 0.3,  # Cautiously positive
            "credit": 0.2,
            "rates": -0.2,
            "commodities": 0.2,
            "dollar": -0.1,
        },
        "Mixed / Transition": {
            "equities": 0.0,  # Neutral/uncertain
            "credit": 0.0,
            "rates": 0.0,
            "commodities": 0.0,
            "dollar": 0.0,
        },
    }

    def __init__(self):
        self.lookback_periods = {
            "short": 1,    # 1 month
            "medium": 3,   # 3 months
            "long": 6,     # 6 months
        }
        self.weights = {
            "short": 0.2,
            "medium": 0.5,
            "long": 0.3,
        }

    def _calculate_trend_score(self, series: pd.Series, period: int) -> float:
        """
        Calculate trend score for a given period.

        Returns score from -1 (strong downtrend) to +1 (strong uptrend)
        """
        if len(series) < period + 1:
            return 0.0

        # Get start and end values
        recent = series.iloc[-period:]

        # Multiple trend measures
        # 1. Simple return
        total_return = (series.iloc[-1] / series.iloc[-period-1]) - 1

        # 2. Regression slope (normalized) - handle NaN/inf
        clean_recent = recent.replace([np.inf, -np.inf], np.nan).dropna()
        if len(clean_recent) >= 2:
            x = np.arange(len(clean_recent))
            y = clean_recent.values
            try:
                slope = np.polyfit(x, y, 1)[0]
                slope_normalized = slope / (clean_recent.mean() + 1e-10) * len(clean_recent)
            except (np.linalg.LinAlgError, ValueError):
                slope_normalized = 0.0
        else:
            slope_normalized = 0.0

        # 3. Percentage of positive months
        monthly_returns = recent.pct_change().dropna()
        pos_ratio = (monthly_returns > 0).mean() if len(monthly_returns) > 0 else 0.5

        # Combine measures
        score = (
            np.sign(total_return) * min(abs(total_return) * 4, 1.0) * 0.4 +
            np.clip(slope_normalized, -1, 1) * 0.4 +
            (pos_ratio - 0.5) * 2 * 0.2
        )

        return np.clip(score, -1, 1)

    def _get_asset_trend(self, df: pd.DataFrame, asset: str) -> Dict:
        """Get trend analysis for a specific asset."""
        # Map asset to column
        col_map = {
            "equities": ["sp500", "equity", "stock"],
            "credit": ["credit", "hy", "spread"],
            "rates": ["yield", "treasury", "rate"],
            "commodities": ["commodity", "oil", "gold"],
            "dollar": ["dxy", "dollar", "usd"],
        }

        # Find matching column
        keywords = col_map.get(asset, [asset])
        col = None
        for keyword in keywords:
            matches = [c for c in df.columns if keyword.lower() in c.lower()]
            if matches:
                col = matches[0]
                break

        if col is None or col not in df.columns:
            return {"available": False, "score": 0.0}

        series = df[col].dropna()
        if len(series) < 3:
            return {"available": False, "score": 0.0}

        # Calculate trends for each period
        trends = {}
        for name, period in self.lookback_periods.items():
            if len(series) >= period + 1:
                trends[name] = self._calculate_trend_score(series, period)
            else:
                trends[name] = 0.0

        # Weighted average
        weighted_score = sum(
            trends[name] * self.weights[name]
            for name in self.lookback_periods.keys()
        )

        return {
            "available": True,
            "column": col,
            "trends": trends,
            "score": weighted_score,
            "current_level": series.iloc[-1],
            "recent_return": (series.iloc[-1] / series.iloc[-min(2, len(series))]) - 1 if len(series) >= 2 else 0,
        }

    def confirm_regime(
        self,
        df: pd.DataFrame,
        regime: str,
        macro_scores: Dict[str, float],
    ) -> TrendConfirmationResult:
        """
        Confirm macro regime against market trends.

        Args:
            df: DataFrame with market price data
            regime: Current macro regime classification
            macro_scores: Dict of macro factor scores

        Returns:
            TrendConfirmationResult with alignment analysis
        """
        if regime not in self.REGIME_ASSET_PREFERENCE:
            logger.warning(f"Unknown regime: {regime}")
            return TrendConfirmationResult(
                overall_signal=TrendSignal.NEUTRAL,
                confirmation_score=0.0,
                macro_market_alignment=0.0,
                asset_signals={},
                divergence_warnings=["Unknown regime"],
                confidence=0.0,
            )

        # Get expected asset directions for this regime
        expected_directions = self.REGIME_ASSET_PREFERENCE[regime]

        # Analyze each asset class
        asset_signals = {}
        alignment_scores = []
        divergence_warnings = []

        for asset, expected_sign in expected_directions.items():
            trend = self._get_asset_trend(df, asset)

            if not trend["available"]:
                continue

            actual_trend = trend["score"]

            # Determine alignment
            if expected_sign > 0.3:  # Expect rising
                if actual_trend > 0.3:
                    alignment = 1.0
                    signal = "confirming"
                elif actual_trend > -0.3:
                    alignment = 0.5
                    signal = "neutral"
                    divergence_warnings.append(f"{asset}: Expected rally, seeing sideways action")
                else:
                    alignment = 0.0
                    signal = "diverging"
                    divergence_warnings.append(f"{asset}: Expected rally, seeing decline (MAJOR DIVERGENCE)")

            elif expected_sign < -0.3:  # Expect falling
                if actual_trend < -0.3:
                    alignment = 1.0
                    signal = "confirming"
                elif actual_trend < 0.3:
                    alignment = 0.5
                    signal = "neutral"
                    divergence_warnings.append(f"{asset}: Expected decline, seeing sideways")
                else:
                    alignment = 0.0
                    signal = "diverging"
                    divergence_warnings.append(f"{asset}: Expected decline, seeing rally (MAJOR DIVERGENCE)")

            else:  # Expect neutral
                alignment = 1.0 - abs(actual_trend)
                signal = "neutral"

            asset_signals[asset] = {
                "expected": expected_sign,
                "actual_trend": actual_trend,
                "alignment": alignment,
                "signal": signal,
                "details": trend,
            }

            alignment_scores.append(alignment)

        # Calculate overall alignment
        if alignment_scores:
            macro_market_alignment = sum(alignment_scores) / len(alignment_scores)
        else:
            macro_market_alignment = 0.0

        # Determine confirmation score and signal
        # Positive = markets confirming macro view
        confirmation_score = macro_market_alignment * 2 - 1  # Scale to -1 to 1

        if confirmation_score > 0.6:
            overall_signal = TrendSignal.STRONG_CONFIRM
        elif confirmation_score > 0.2:
            overall_signal = TrendSignal.CONFIRM
        elif confirmation_score > -0.2:
            overall_signal = TrendSignal.NEUTRAL
        elif confirmation_score > -0.6:
            overall_signal = TrendSignal.DIVERGE
        else:
            overall_signal = TrendSignal.STRONG_DIVERGE

        # Confidence based on data availability
        confidence = len(asset_signals) / len(expected_directions)

        return TrendConfirmationResult(
            overall_signal=overall_signal,
            confirmation_score=confirmation_score,
            macro_market_alignment=macro_market_alignment,
            asset_signals=asset_signals,
            divergence_warnings=divergence_warnings,
            confidence=confidence,
        )

    def get_confirmation_summary(self, result: TrendConfirmationResult) -> str:
        """Get plain-English summary of confirmation."""
        signal_desc = {
            TrendSignal.STRONG_CONFIRM: "Markets strongly confirm the macro view",
            TrendSignal.CONFIRM: "Markets generally confirm the macro view",
            TrendSignal.NEUTRAL: "Mixed signals - no clear confirmation or divergence",
            TrendSignal.DIVERGE: "Markets diverging from macro view - caution warranted",
            TrendSignal.STRONG_DIVERGE: "Major divergence - macro view may be wrong",
        }

        summary = signal_desc.get(result.overall_signal, "Unknown")

        if result.divergence_warnings:
            summary += "\n\nDivergences detected:\n"
            for warning in result.divergence_warnings[:3]:  # Top 3
                summary += f"  • {warning}\n"

        return summary


def calculate_market_regime_alignment(
    df: pd.DataFrame,
    regime: str,
    scores: Dict[str, float],
) -> TrendConfirmationResult:
    """Convenience function to calculate market confirmation."""
    model = MarketConfirmationModel()
    return model.confirm_regime(df, regime, scores)
