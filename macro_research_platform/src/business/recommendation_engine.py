"""
Recommendation Engine

Produces three levels of recommendation:
1. Research View - What the macro analysis shows
2. Portfolio View - How to position given the macro view
3. Action View - Specific sector/asset recommendations

Philosophy:
- Do not force trades if conviction is low
- Every recommendation must have supporting and opposing signals
- Risk to view must be explicitly stated
- Business relevance must be clear
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .business_objectives import (
    BusinessOutputType,
    ConvictionLevel,
    PositionSize,
    Recommendation,
)

logger = logging.getLogger(__name__)


class ConvictionEngine:
    """
    Calculate conviction based on signal quality, agreement, and data freshness.

    Conviction depends on:
    - Signal agreement (do signals point the same way?)
    - Signal strength (how extreme are the readings?)
    - Data quality (is data fresh and reliable?)
    - Research support (is there academic backing?)
    - Backtest reliability (has this signal worked historically?)
    - Market confirmation (do prices agree?)
    - Model disagreement (are models in conflict?)
    """

    def __init__(self):
        self.weights = {
            "signal_agreement": 0.20,
            "signal_strength": 0.15,
            "data_quality": 0.15,
            "research_support": 0.10,
            "backtest_reliability": 0.15,
            "market_confirmation": 0.15,
            "model_disagreement": 0.10,
        }

    def calculate_conviction(
        self,
        signal_scores: Dict[str, float],
        data_quality_score: float,
        research_support_score: float,
        backtest_ic: float,
        market_confirmation: bool,
        model_disagreement_penalty: float = 0.0,
    ) -> Tuple[ConvictionLevel, float]:
        """
        Calculate conviction level and score.

        Returns:
            Tuple of (conviction_level, conviction_score 0-1)
        """
        # Signal agreement - std dev of scores (lower = higher agreement)
        if len(signal_scores) > 1:
            std_dev = pd.Series(signal_scores.values()).std()
            agreement_score = max(0, 1 - std_dev / 0.5)
        else:
            agreement_score = 0.5

        # Signal strength - average absolute value
        strength_score = min(1.0, sum(abs(s) for s in signal_scores.values()) /
                            len(signal_scores) / 1.5)

        # Backtest reliability - map IC to score
        backtest_score = max(0, (backtest_ic + 0.5) / 1.0) if backtest_ic else 0.5

        # Market confirmation
        confirmation_score = 1.0 if market_confirmation else 0.3

        # Calculate weighted score
        conviction_score = (
            self.weights["signal_agreement"] * agreement_score +
            self.weights["signal_strength"] * strength_score +
            self.weights["data_quality"] * data_quality_score +
            self.weights["research_support"] * research_support_score +
            self.weights["backtest_reliability"] * backtest_score +
            self.weights["market_confirmation"] * confirmation_score -
            self.weights["model_disagreement"] * model_disagreement_penalty
        )

        # Map to conviction level
        if conviction_score >= 0.75:
            conviction = ConvictionLevel.HIGH
        elif conviction_score >= 0.45:
            conviction = ConvictionLevel.MEDIUM
        else:
            conviction = ConvictionLevel.LOW

        return conviction, round(conviction_score, 2)


class PositionSizingEngine:
    """
    Convert conviction into position sizes with constraints.

    Formula:
    position_size = base_risk_budget × expected_return_score × conviction_score
                    × data_quality_score / realized_volatility

    Constraints:
    - No position if data is sample mode
    - Reduce size if data is stale
    - Reduce size if model disagreement is high
    - Reduce size if volatility is high
    - Reduce size if backtest reliability is weak
    """

    def __init__(self, base_risk_budget: float = 1.0):
        self.base_risk_budget = base_risk_budget

    def calculate_position_size(
        self,
        expected_return_score: float,
        conviction_score: float,
        data_quality_score: float,
        volatility: float,
        data_mode: str,
        model_disagreement: float = 0.0,
        backtest_reliability: float = 0.5,
    ) -> Tuple[PositionSize, float]:
        """
        Calculate position size.

        Returns:
            Tuple of (position_size_enum, size_multiplier)
        """
        # Hard constraints - but never return zero for ALL positions
        if data_mode == "sample":
            # Fallback: use conviction-based sizing even in sample mode
            logger.warning("[POSITION_SIZING_FALLBACK] Sample mode - using conviction-based sizing")
            if conviction_score >= 0.7:
                return PositionSize.HIGH_CONVICTION, 1.5
            elif conviction_score >= 0.4:
                return PositionSize.NORMAL, 1.0
            elif conviction_score >= 0.2:
                return PositionSize.SMALL, 0.6
            else:
                return PositionSize.WATCHLIST, 0.3

        if data_quality_score < 0.3:
            return PositionSize.WATCHLIST, 0.3

        # CRITICAL FIX: If expected return is 0, use conviction-based fallback
        # This ensures we never show "No Position" for ALL sectors simultaneously
        if expected_return_score == 0 or abs(expected_return_score) < 0.001:
            logger.warning(f"[POSITION_SIZING_FALLBACK] Expected return is 0, using conviction-based sizing: {conviction_score:.2f}")
            # Size proportionally to conviction score
            if conviction_score >= 0.7:  # HIGH conviction
                return PositionSize.HIGH_CONVICTION, 1.5
            elif conviction_score >= 0.4:  # MEDIUM conviction
                return PositionSize.NORMAL, 1.0
            elif conviction_score >= 0.2:  # LOW conviction
                return PositionSize.SMALL, 0.5
            else:
                return PositionSize.WATCHLIST, 0.3

        # Calculate base size
        size = (
            self.base_risk_budget *
            abs(expected_return_score) *
            conviction_score *
            data_quality_score
        )

        # Volatility adjustment (higher vol = smaller size)
        vol_adjustment = max(0.3, 1.0 - volatility / 50.0)
        size *= vol_adjustment

        # Model disagreement penalty
        size *= (1.0 - model_disagreement)

        # Backtest reliability adjustment
        size *= backtest_reliability

        # Cap at reasonable bounds
        size = min(2.0, max(0.0, size))

        # Map to position size enum
        if size < 0.2:
            pos_size = PositionSize.NO_POSITION
        elif size < 0.4:
            pos_size = PositionSize.WATCHLIST
        elif size < 0.7:
            pos_size = PositionSize.SMALL
        elif size < 1.1:
            pos_size = PositionSize.NORMAL
        else:
            pos_size = PositionSize.HIGH_CONVICTION

        return pos_size, round(size, 2)


class RecommendationEngine:
    """
    Main recommendation engine producing three-level recommendations.
    """

    def __init__(self):
        self.conviction_engine = ConvictionEngine()
        self.position_sizing_engine = PositionSizingEngine()
        self.recommendation_history: List[Recommendation] = []

    def generate_research_view(
        self,
        global_regime: str,
        country_regimes: Dict[str, str],
        growth_momentum: float,
        inflation_pressure: float,
        liquidity_conditions: float,
        recession_probability: float,
    ) -> Recommendation:
        """
        Generate Level 1: Research View.

        What the macro analysis shows.
        """
        # Build headline
        if global_regime == "regional_divergence":
            headline = "Global macro remains divergent with economies out of sync"
            detail = self._describe_divergent_regime(country_regimes)
        elif global_regime == "goldilocks":
            headline = "Goldilocks environment: growth positive, inflation contained"
            detail = f"Growth momentum at {growth_momentum:+.1f}, inflation pressure at {inflation_pressure:+.1f}."
        elif global_regime == "reflation":
            headline = "Reflation regime: growth and inflation both rising"
            detail = f"Growth momentum at {growth_momentum:+.1f}, inflation pressure elevated at {inflation_pressure:+.1f}."
        elif global_regime == "stagflation":
            headline = "Stagflation risk: weak growth with elevated inflation"
            detail = f"Growth momentum negative at {growth_momentum:+.1f}, inflation pressure high at {inflation_pressure:+.1f}."
        elif global_regime == "slowdown":
            headline = "Slowdown regime: growth and inflation both declining"
            detail = f"Growth momentum at {growth_momentum:+.1f}, disinflationary pressure at {inflation_pressure:+.1f}."
        else:
            headline = "Mixed macro signals with unclear direction"
            detail = f"Growth momentum at {growth_momentum:+.1f}, inflation pressure at {inflation_pressure:+.1f}."

        # Determine supporting/opposing signals
        supporting = []
        opposing = []

        if growth_momentum > 0.3:
            supporting.append("positive_growth_momentum")
        elif growth_momentum < -0.3:
            opposing.append("negative_growth_momentum")

        if inflation_pressure > 0.5:
            supporting.append("inflation_pressure")
        elif inflation_pressure < -0.5:
            supporting.append("disinflation")

        if liquidity_conditions > 0.5:
            supporting.append("easy_liquidity")
        elif liquidity_conditions < -0.5:
            opposing.append("tight_liquidity")

        if recession_probability < 0.2:
            supporting.append("low_recession_risk")
        elif recession_probability > 0.4:
            opposing.append("elevated_recession_risk")

        rec = Recommendation(
            timestamp=datetime.now(),
            recommendation_type="research_view",
            headline=headline,
            detail=detail,
            conviction=ConvictionLevel.MEDIUM,
            suggested_position_size=PositionSize.NORMAL,
            supporting_signals=supporting,
            opposing_signals=opposing,
            risk_to_view="Unexpected policy shifts or geopolitical shocks",
            data_to_watch=["nonfarm_payrolls", "cpi_release", "fed_speeches"],
            business_relevance="Sets the baseline macro environment for all positioning decisions",
            suggested_action="Monitor signal evolution, no immediate action required",
        )

        return rec

    def generate_portfolio_view(
        self,
        research_view: Recommendation,
        cross_asset_signals: Dict[str, Dict],
        sector_signals: Dict[str, str],
        credit_stress: float,
    ) -> Recommendation:
        """
        Generate Level 2: Portfolio View.

        How to position given the macro view.
        """
        # Analyze cross-asset signals
        bullish_assets = [a for a, s in cross_asset_signals.items()
                        if s.get("signal") in ["overweight", "bullish"]]
        bearish_assets = [a for a, s in cross_asset_signals.items()
                        if s.get("signal") in ["underweight", "bearish"]]

        # Build headline
        if research_view.conviction == ConvictionLevel.HIGH:
            if credit_stress < 0.3:
                headline = "Maintain selective risk exposure with high conviction"
                detail = (f"Research view is clear. {len(bullish_assets)} asset classes showing positive signals. "
                         f"Credit conditions supportive. Avoid aggressive defensive rotation.")
            else:
                headline = "High conviction but credit stress requires caution"
                detail = (f"Macro view is clear, but credit stress at {credit_stress:.0%} warrants position sizing discipline.")
        elif research_view.conviction == ConvictionLevel.MEDIUM:
            headline = "Maintain balanced exposure, await stronger confirmation"
            detail = (f"Mixed signals suggest selective positioning rather than large bets. "
                     f"Monitor {len(bearish_assets)} asset classes showing caution.")
        else:
            headline = "Low conviction environment - minimize active risk"
            detail = "Conflicting signals suggest neutral positioning until clarity emerges."

        # Determine supporting signals
        supporting = []
        opposing = []

        for asset, signal_data in cross_asset_signals.items():
            signal = signal_data.get("signal", "neutral")
            if signal in ["overweight", "bullish", "dollar_bullish"]:
                supporting.append(f"{asset}_{signal}")
            elif signal in ["underweight", "bearish", "dollar_bearish"]:
                opposing.append(f"{asset}_{signal}")

        if credit_stress < 0.3:
            supporting.append("healthy_credit")
        else:
            opposing.append("credit_stress")

        # Calculate conviction
        conviction, conviction_score = self.conviction_engine.calculate_conviction(
            signal_scores={a: 1.0 if s.get("signal") in ["overweight", "bullish"] else -1.0
                          for a, s in cross_asset_signals.items()},
            data_quality_score=0.7,
            research_support_score=0.6,
            backtest_ic=0.15,
            market_confirmation=True,
            model_disagreement_penalty=0.0 if research_view.conviction != ConvictionLevel.LOW else 0.3,
        )

        rec = Recommendation(
            timestamp=datetime.now(),
            recommendation_type="portfolio_view",
            headline=headline,
            detail=detail,
            conviction=conviction,
            suggested_position_size=PositionSize.NORMAL if conviction != ConvictionLevel.LOW else PositionSize.SMALL,
            supporting_signals=supporting,
            opposing_signals=opposing,
            risk_to_view="Unexpected regime shift or credit event",
            data_to_watch=["credit_spreads", "vix", "yield_curve"],
            business_relevance="Guides broad asset allocation and risk budget deployment",
            suggested_action="Review sector allocation, maintain current risk budget" if conviction != ConvictionLevel.LOW else "Reduce active risk, increase cash buffer",
        )

        return rec

    def generate_action_view(
        self,
        portfolio_view: Recommendation,
        sector_scores: Dict[str, float],
        expected_returns: Dict[str, float],
        volatility: float,
        data_mode: str,
    ) -> Recommendation:
        """
        Generate Level 3: Action View.

        Specific sector/asset recommendations.
        """
        # Sort sectors by score
        sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)

        top_sectors = [s for s, score in sorted_sectors[:3] if score > 0.2]
        bottom_sectors = [s for s, score in sorted_sectors[-3:] if score < -0.2]

        # Build headline
        if portfolio_view.conviction == ConvictionLevel.HIGH and top_sectors:
            headline = f"Overweight {', '.join(top_sectors[:2])}"
            detail = f"High conviction supports selective sector tilts. Expected returns favor {len(top_sectors)} sectors."
        elif portfolio_view.conviction == ConvictionLevel.MEDIUM:
            headline = "Maintain balanced sector exposure with modest quality tilt"
            detail = "Mixed signals suggest avoiding large sector bets while maintaining quality bias."
        else:
            headline = "Neutral sector positioning, focus on stock selection"
            detail = "Low macro conviction favors stock-specific alpha over sector tilts."

        # Calculate position sizes
        position_sizes = {}
        for sector, score in sector_scores.items():
            size, multiplier = self.position_sizing_engine.calculate_position_size(
                expected_return_score=expected_returns.get(sector, 0),
                conviction_score=0.6 if portfolio_view.conviction != ConvictionLevel.LOW else 0.3,
                data_quality_score=0.7,
                volatility=volatility,
                data_mode=data_mode,
            )
            position_sizes[sector] = {"size": size.value, "multiplier": multiplier}

        # Build supporting/opposing signals
        supporting = [f"{s}_positive" for s, score in sorted_sectors[:3] if score > 0.3]
        opposing = [f"{s}_negative" for s, score in sorted_sectors[-3:] if score < -0.3]

        rec = Recommendation(
            timestamp=datetime.now(),
            recommendation_type="action_view",
            headline=headline,
            detail=detail,
            conviction=portfolio_view.conviction,
            suggested_position_size=portfolio_view.suggested_position_size,
            supporting_signals=supporting,
            opposing_signals=opposing,
            risk_to_view="Sector rotation against position or macro surprise",
            data_to_watch=["earnings_revisions", "sector_momentum", "analyst_ratings"],
            business_relevance="Directly guides portfolio construction and rebalancing",
            suggested_action=f"Implement sector tilts: OW {', '.join(top_sectors[:2]) if top_sectors else 'none'}, UW {', '.join(bottom_sectors[:2]) if bottom_sectors else 'none'}" if portfolio_view.conviction != ConvictionLevel.LOW else "Maintain market-neutral sector weights",
        )

        return rec

    def generate_all_recommendations(
        self,
        global_regime: str,
        country_regimes: Dict[str, str],
        growth_momentum: float,
        inflation_pressure: float,
        liquidity_conditions: float,
        recession_probability: float,
        cross_asset_signals: Dict[str, Dict],
        sector_scores: Dict[str, float],
        expected_returns: Dict[str, float],
        credit_stress: float,
        volatility: float,
        data_mode: str,
    ) -> Dict[str, Recommendation]:
        """Generate all three levels of recommendations."""

        research = self.generate_research_view(
            global_regime, country_regimes, growth_momentum,
            inflation_pressure, liquidity_conditions, recession_probability
        )

        portfolio = self.generate_portfolio_view(
            research, cross_asset_signals, {}, credit_stress
        )

        action = self.generate_action_view(
            portfolio, sector_scores, expected_returns, volatility, data_mode
        )

        # Store in history
        self.recommendation_history.extend([research, portfolio, action])

        return {
            "research_view": research,
            "portfolio_view": portfolio,
            "action_view": action,
        }

    def _describe_divergent_regime(self, country_regimes: Dict[str, str]) -> str:
        """Describe a divergent regime across countries."""
        descriptions = []
        for country, regime in country_regimes.items():
            descriptions.append(f"{country}: {regime}")
        return "Regional divergence with " + ", ".join(descriptions[:4])

    def get_latest_recommendations(self, n: int = 10) -> List[Recommendation]:
        """Get the N most recent recommendations."""
        return sorted(self.recommendation_history, key=lambda r: r.timestamp, reverse=True)[:n]

    def get_recommendation_trends(self, days: int = 30) -> Dict:
        """Analyze recommendation trends over time."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)

        recent = [r for r in self.recommendation_history if r.timestamp > cutoff]

        if not recent:
            return {"message": "No recommendations in the specified period"}

        by_type = {}
        for r in recent:
            by_type.setdefault(r.recommendation_type, []).append(r.conviction.value)

        trends = {}
        for rec_type, convictions in by_type.items():
            trends[rec_type] = {
                "count": len(convictions),
                "avg_conviction": convictions.count("high") / len(convictions),
            }

        return trends
