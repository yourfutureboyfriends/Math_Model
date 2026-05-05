"""
Position Sizing

Implements position sizing rules based on:
- Kelly Criterion
- Volatility targeting
- Maximum drawdown constraints
- Correlation-adjusted sizing
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Position sizing result."""
    asset: str
    base_size: float  # Base sizing (0-1)
    adjusted_size: float  # After adjustments
    confidence_adjustment: float
    vol_adjustment: float
    correlation_adjustment: float
    rationale: str


class PositionSizingEngine:
    """
    Calculate position sizes with risk adjustments.

    Implements multiple sizing methodologies with safety constraints.
    """

    def __init__(
        self,
        target_volatility: float = 0.10,
        max_position_size: float = 0.25,
        min_position_size: float = 0.0,
        max_correlation_adjustment: float = 0.5,
    ):
        """
        Initialize position sizing engine.

        Args:
            target_volatility: Target portfolio volatility
            max_position_size: Maximum position size (gross)
            min_position_size: Minimum position size
            max_correlation_adjustment: Maximum correlation penalty
        """
        self.target_volatility = target_volatility
        self.max_position_size = max_position_size
        self.min_position_size = min_position_size
        self.max_correlation_adjustment = max_correlation_adjustment

    def calculate_kelly_fraction(
        self,
        expected_return: float,
        variance: float,
        win_rate: float,
        payoff_ratio: float,
        fraction: float = 0.5,  # Half Kelly for safety
    ) -> float:
        """
        Calculate Kelly Criterion position size.

        Kelly = (p*b - q) / b
        where p = win rate, q = loss rate, b = payoff ratio

        Args:
            expected_return: Expected return
            variance: Return variance
            win_rate: Probability of winning
            payoff_ratio: Average win / average loss
            fraction: Kelly fraction (0.5 = Half Kelly)

        Returns:
            Position size as fraction of capital
        """
        if variance == 0 or payoff_ratio <= 0:
            return 0

        # Kelly fraction based on mean-variance
        kelly = expected_return / variance

        # Alternative based on win rate and payoff
        # p = win_rate, q = 1 - win_rate
        # kelly = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio

        # Apply safety fraction
        safe_kelly = kelly * fraction

        # Cap at max position size
        return min(safe_kelly, self.max_position_size)

    def calculate_volatility_targeted_size(
        self,
        asset_volatility: float,
        asset_beta: float = 1.0,
        expected_sharpe: float = 0.5,
    ) -> float:
        """
        Calculate position size based on volatility targeting.

        Args:
            asset_volatility: Asset volatility (annualized)
            asset_beta: Asset beta to portfolio
            expected_sharpe: Expected Sharpe ratio

        Returns:
            Position size
        """
        if asset_volatility == 0:
            return 0

        # Volatility targeting formula
        # Position = Target vol / (Asset vol * |beta|)
        position = self.target_volatility / (asset_volatility * abs(asset_beta))

        # Adjust by expected Sharpe (higher Sharpe = larger position)
        position = position * (expected_sharpe / 0.5)

        return min(position, self.max_position_size)

    def calculate_confidence_adjustment(
        self,
        signal_confidence: float,
        min_confidence: float = 0.3,
    ) -> float:
        """
        Adjust position size by signal confidence.

        Args:
            signal_confidence: Signal confidence (0-1)
            min_confidence: Minimum confidence to trade

        Returns:
            Confidence adjustment factor (0-1)
        """
        if signal_confidence < min_confidence:
            return 0

        # Linear adjustment
        adjustment = (signal_confidence - min_confidence) / (1 - min_confidence)

        return max(0, min(1, adjustment))

    def calculate_correlation_adjustment(
        self,
        asset_returns: pd.Series,
        portfolio_returns: pd.Series,
        max_correlation: float = 0.7,
    ) -> float:
        """
        Adjust position size based on correlation to portfolio.

        High correlation assets get penalized (diversification benefit).

        Args:
            asset_returns: Asset return series
            portfolio_returns: Portfolio return series
            max_correlation: Maximum correlation before full penalty

        Returns:
            Correlation adjustment factor
        """
        if len(asset_returns) < 30 or len(portfolio_returns) < 30:
            return 1.0

        # Align series
        common_index = asset_returns.index.intersection(portfolio_returns.index)
        if len(common_index) < 30:
            return 1.0

        asset_aligned = asset_returns.loc[common_index]
        portfolio_aligned = portfolio_returns.loc[common_index]

        # Calculate correlation
        correlation = asset_aligned.corr(portfolio_aligned)

        if pd.isna(correlation):
            return 1.0

        # Adjustment: higher correlation = smaller position
        if correlation > max_correlation:
            adjustment = 1 - self.max_correlation_adjustment
        else:
            # Linear scaling
            adjustment = 1 - (correlation / max_correlation) * self.max_correlation_adjustment

        return max(0, min(1, adjustment))

    def calculate_max_drawdown_adjustment(
        self,
        current_drawdown: float,
        max_allowed_drawdown: float = 0.15,
    ) -> float:
        """
        Reduce position sizes when drawdown exceeds threshold.

        Args:
            current_drawdown: Current drawdown (positive = underwater)
            max_allowed_drawdown: Maximum allowed drawdown

        Returns:
            Drawdown adjustment factor
        """
        if current_drawdown <= 0:
            return 1.0

        if current_drawdown >= max_allowed_drawdown:
            return 0.0  # Full stop

        # Proportional reduction
        adjustment = 1 - (current_drawdown / max_allowed_drawdown)

        return max(0, min(1, adjustment))

    def size_position(
        self,
        asset: str,
        expected_return: float,
        volatility: float,
        signal_confidence: float,
        asset_returns: Optional[pd.Series] = None,
        portfolio_returns: Optional[pd.Series] = None,
        current_drawdown: float = 0.0,
    ) -> PositionSize:
        """
        Calculate complete position size with all adjustments.

        Args:
            asset: Asset name
            expected_return: Expected return
            volatility: Volatility
            signal_confidence: Signal confidence
            asset_returns: Historical returns for correlation
            portfolio_returns: Portfolio returns for correlation
            current_drawdown: Current drawdown

        Returns:
            PositionSize with adjustments
        """
        # Base size: volatility targeting
        base_size = self.calculate_volatility_targeted_size(volatility)

        # Confidence adjustment
        conf_adj = self.calculate_confidence_adjustment(signal_confidence)

        # Correlation adjustment
        corr_adj = 1.0
        if asset_returns is not None and portfolio_returns is not None:
            corr_adj = self.calculate_correlation_adjustment(asset_returns, portfolio_returns)

        # Drawdown adjustment
        dd_adj = self.calculate_max_drawdown_adjustment(current_drawdown)

        # Volatility adjustment (reduce size in high vol)
        vol_adj = self.target_volatility / volatility if volatility > 0 else 1.0
        vol_adj = min(1.5, max(0.5, vol_adj))  # Cap adjustments

        # Combined adjustment
        total_adjustment = conf_adj * corr_adj * dd_adj * vol_adj

        # Final size
        adjusted_size = base_size * total_adjustment

        # Apply limits
        adjusted_size = max(self.min_position_size, min(self.max_position_size, adjusted_size))

        return PositionSize(
            asset=asset,
            base_size=round(base_size, 4),
            adjusted_size=round(adjusted_size, 4),
            confidence_adjustment=round(conf_adj, 2),
            vol_adjustment=round(vol_adj, 2),
            correlation_adjustment=round(corr_adj, 2),
            rationale=f"Base {base_size:.2%} x Conf {conf_adj:.2f} x Corr {corr_adj:.2f} x DD {dd_adj:.2f} x Vol {vol_adj:.2f} = {adjusted_size:.2%}",
        )

    def size_portfolio(
        self,
        expected_returns: Dict[str, float],
        volatilities: Dict[str, float],
        confidences: Dict[str, float],
        returns_data: Optional[pd.DataFrame] = None,
        current_drawdown: float = 0.0,
    ) -> Dict[str, PositionSize]:
        """
        Size all positions in portfolio.

        Args:
            expected_returns: Dict of asset to expected return
            volatilities: Dict of asset to volatility
            confidences: Dict of asset to signal confidence
            returns_data: Historical returns DataFrame
            current_drawdown: Current drawdown

        Returns:
            Dict of asset to PositionSize
        """
        positions = {}

        # Calculate portfolio returns for correlation adjustment
        if returns_data is not None:
            # Estimate current portfolio returns (equal weight proxy)
            portfolio_returns = returns_data.mean(axis=1)
        else:
            portfolio_returns = None

        for asset in expected_returns:
            asset_returns = returns_data[asset] if returns_data is not None and asset in returns_data.columns else None

            positions[asset] = self.size_position(
                asset=asset,
                expected_return=expected_returns[asset],
                volatility=volatilities.get(asset, 0.15),
                signal_confidence=confidences.get(asset, 0.5),
                asset_returns=asset_returns,
                portfolio_returns=portfolio_returns,
                current_drawdown=current_drawdown,
            )

        return positions


def calculate_optimal_leverage(
    returns: pd.Series,
    target_drawdown: float = 0.20,
    confidence_level: float = 0.95,
) -> float:
    """
    Calculate optimal leverage based on historical returns.

    Uses historical drawdown to determine max safe leverage.

    Args:
        returns: Historical return series
        target_drawdown: Maximum acceptable drawdown
        confidence_level: Confidence level for drawdown estimate

    Returns:
        Optimal leverage ratio
    """
    if len(returns) < 60:
        return 1.0

    # Calculate historical drawdowns
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdowns = (cumulative - running_max) / running_max

    # Worst drawdown
    worst_dd = abs(drawdowns.min())

    if worst_dd == 0:
        return 1.0

    # Leverage = target / historical worst
    leverage = target_drawdown / worst_dd

    # Cap at reasonable level
    return min(2.0, max(0.5, leverage))


def volatility_scaling(
    returns: pd.Series,
    target_vol: float = 0.10,
    lookback: int = 60,
) -> pd.Series:
    """
    Calculate volatility-scaled position size over time.

    Args:
        returns: Return series
        target_vol: Target volatility
        lookback: Lookback period for volatility

    Returns:
        Position size multiplier series
    """
    # Rolling volatility
    rolling_vol = returns.rolling(lookback).std() * np.sqrt(252)

    # Scale to target
    position_size = target_vol / rolling_vol

    # Cap extreme values
    return position_size.clip(0.5, 2.0)
