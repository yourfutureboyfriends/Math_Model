"""
Signal Base Classes

Base classes for all systematic trading signals.

A signal is a rule-based expression of a research hypothesis
that can be backtested, validated, and combined with other signals.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SignalDirection(Enum):
    """Direction of a signal."""
    LONG = 1
    SHORT = -1
    NEUTRAL = 0


class SignalConfidence(Enum):
    """Confidence level in signal."""
    VERY_HIGH = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    VERY_LOW = 1


@dataclass
class SignalOutput:
    """Output from a signal calculation."""
    timestamp: datetime
    direction: SignalDirection
    strength: float  # 0-1 normalized
    confidence: SignalConfidence
    expected_return: Optional[float] = None
    expected_volatility: Optional[float] = None
    time_horizon: str = "medium"  # short, medium, long
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.strength < 0 or self.strength > 1:
            raise ValueError("Signal strength must be between 0 and 1")


@dataclass
class SignalPerformance:
    """Performance metrics for a signal."""
    signal_name: str
    n_signals: int
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    information_coefficient: float
    turnover: float

    # By regime
    performance_by_regime: Dict[str, Dict] = field(default_factory=dict)


class Signal(ABC):
    """
    Abstract base class for all signals.

    Signals implement specific macro-to-asset relationships.
    They must be:
    - Systematic (rule-based)
    - Testable (backtestable)
    - Documented (hypothesis clear)
    """

    def __init__(
        self,
        name: str,
        description: str,
        asset_universe: List[str],
        frequency: str = "daily",
    ):
        self.name = name
        self.description = description
        self.asset_universe = asset_universe
        self.frequency = frequency
        self.signal_history: List[SignalOutput] = []
        self.is_active = True

        # Signal parameters (can be overridden)
        self.parameters: Dict[str, Any] = {}

    @abstractmethod
    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """
        Calculate signal output.

        Args:
            data: Dictionary of DataFrames keyed by series/asset
            as_of_date: Point-in-time calculation date

        Returns:
            SignalOutput with direction, strength, confidence
        """
        pass

    def update_parameters(self, parameters: Dict[str, Any]) -> None:
        """Update signal parameters."""
        self.parameters.update(parameters)
        logger.info(f"Updated parameters for signal {self.name}: {parameters}")

    def validate(self, data: Dict[str, pd.DataFrame]) -> Tuple[bool, str]:
        """
        Validate that required data is available.

        Returns:
            (is_valid, error_message)
        """
        return True, ""

    def get_latest_signal(self) -> Optional[SignalOutput]:
        """Get most recent signal output."""
        if not self.signal_history:
            return None
        return self.signal_history[-1]

    def get_signal_history(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[SignalOutput]:
        """Get signal history for date range."""
        signals = self.signal_history

        if start_date:
            signals = [s for s in signals if s.timestamp >= start_date]
        if end_date:
            signals = [s for s in signals if s.timestamp <= end_date]

        return signals

    def to_dataframe(self) -> pd.DataFrame:
        """Convert signal history to DataFrame."""
        if not self.signal_history:
            return pd.DataFrame()

        records = []
        for s in self.signal_history:
            records.append({
                "timestamp": s.timestamp,
                "direction": s.direction.value,
                "strength": s.strength,
                "confidence": s.confidence.value,
                "expected_return": s.expected_return,
                "rationale": s.rationale,
            })

        return pd.DataFrame(records)


class MacroSignal(Signal):
    """
    Base class for macro-driven signals.

    These signals depend on macroeconomic relationships
    (e.g., growth → equities, inflation → rates).
    """

    def __init__(
        self,
        name: str,
        description: str,
        asset_universe: List[str],
        required_macros: List[str],
        frequency: str = "daily",
    ):
        super().__init__(name, description, asset_universe, frequency)
        self.required_macros = required_macros

    def validate(self, data: Dict[str, pd.DataFrame]) -> Tuple[bool, str]:
        """Validate macro data availability."""
        missing = []
        for macro in self.required_macros:
            if macro not in data:
                missing.append(macro)
            elif data[macro].empty:
                missing.append(f"{macro} (empty)")

        if missing:
            return False, f"Missing required macro data: {missing}"

        return True, ""


class TechnicalSignal(Signal):
    """
    Base class for technical/price-based signals.

    These signals depend on price action, momentum, etc.
    """

    def __init__(
        self,
        name: str,
        description: str,
        asset_universe: List[str],
        lookback_periods: List[int] = None,
        frequency: str = "daily",
    ):
        super().__init__(name, description, asset_universe, frequency)
        self.lookback_periods = lookback_periods or [20, 60, 120]


class CrossAssetSignal(Signal):
    """
    Base class for cross-asset signals.

    These signals depend on relationships between assets
    (e.g., rates → FX, commodities → equities).
    """

    def __init__(
        self,
        name: str,
        description: str,
        primary_asset: str,
        secondary_asset: str,
        relationship_type: str,  # "lead_lag", "cointegration", "correlation"
        frequency: str = "daily",
    ):
        super().__init__(name, description, [primary_asset, secondary_asset], frequency)
        self.primary_asset = primary_asset
        self.secondary_asset = secondary_asset
        self.relationship_type = relationship_type


class CompositeSignal(Signal):
    """
    Composite signal that combines multiple sub-signals.

    Allows building hierarchical signal structures.
    """

    def __init__(
        self,
        name: str,
        description: str,
        asset_universe: List[str],
        sub_signals: List[Signal],
        combination_method: str = "weighted_average",
    ):
        super().__init__(name, description, asset_universe)
        self.sub_signals = sub_signals
        self.combination_method = combination_method
        self.signal_weights: Dict[str, float] = {}

    def set_weights(self, weights: Dict[str, float]) -> None:
        """Set weights for combining sub-signals."""
        if abs(sum(weights.values()) - 1.0) > 0.01:
            raise ValueError("Signal weights must sum to 1.0")
        self.signal_weights = weights

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Calculate composite signal from sub-signals."""
        # Calculate all sub-signals
        sub_outputs = []
        for signal in self.sub_signals:
            output = signal.calculate(data, as_of_date)
            sub_outputs.append((signal.name, output))

        # Combine based on method
        if self.combination_method == "weighted_average":
            return self._weighted_combine(sub_outputs, as_of_date)
        elif self.combination_method == "majority_vote":
            return self._majority_vote(sub_outputs, as_of_date)
        else:
            return self._weighted_combine(sub_outputs, as_of_date)

    def _weighted_combine(
        self,
        sub_outputs: List[Tuple[str, SignalOutput]],
        as_of_date: Optional[datetime],
    ) -> SignalOutput:
        """Combine signals using weighted average."""
        total_weight = 0
        weighted_direction = 0
        weighted_strength = 0
        min_confidence = 5

        for name, output in sub_outputs:
            weight = self.signal_weights.get(name, 1.0 / len(sub_outputs))
            total_weight += weight

            weighted_direction += output.direction.value * weight * output.strength
            weighted_strength += output.strength * weight
            min_confidence = min(min_confidence, output.confidence.value)

        if total_weight > 0:
            weighted_direction /= total_weight
            weighted_strength /= total_weight

        # Normalize direction
        if weighted_direction > 0.3:
            direction = SignalDirection.LONG
        elif weighted_direction < -0.3:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=min(1.0, weighted_strength),
            confidence=SignalConfidence(min_confidence),
            rationale=f"Composite of {[n for n, _ in sub_outputs]}",
        )

    def _majority_vote(
        self,
        sub_outputs: List[Tuple[str, SignalOutput]],
        as_of_date: Optional[datetime],
    ) -> SignalOutput:
        """Combine signals using majority vote."""
        votes = {SignalDirection.LONG: 0, SignalDirection.SHORT: 0, SignalDirection.NEUTRAL: 0}

        for name, output in sub_outputs:
            weight = self.signal_weights.get(name, 1.0)
            votes[output.direction] += weight

        # Winner takes all
        direction = max(votes, key=votes.get)
        total_votes = sum(votes.values())
        strength = votes[direction] / total_votes if total_votes > 0 else 0

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=f"Majority vote: {direction.name}",
        )


def calculate_signal_performance(
    signals: List[SignalOutput],
    returns: pd.Series,
    holding_period: int = 21,  # Days
) -> SignalPerformance:
    """
    Calculate performance metrics for a signal series.

    Args:
        signals: List of signal outputs
        returns: Asset returns series (daily)
        holding_period: How long to hold signal

    Returns:
        SignalPerformance metrics
    """
    if not signals or returns.empty:
        return SignalPerformance(
            signal_name="unknown",
            n_signals=0,
            win_rate=0.0,
            avg_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            calmar_ratio=0.0,
            information_coefficient=0.0,
            turnover=0.0,
        )

    # Calculate signal returns
    signal_returns = []

    for signal in signals:
        # Find return period
        start_idx = returns.index.get_loc(signal.timestamp, method='nearest')
        end_idx = min(start_idx + holding_period, len(returns) - 1)

        period_return = returns.iloc[start_idx:end_idx].sum()
        signal_returns.append(period_return * signal.direction.value)

    signal_returns = pd.Series(signal_returns)

    # Performance metrics
    win_rate = (signal_returns > 0).mean()
    avg_return = signal_returns.mean()

    # Sharpe ratio (annualized)
    if signal_returns.std() > 0:
        sharpe = (avg_return / signal_returns.std()) * np.sqrt(252 / holding_period)
    else:
        sharpe = 0.0

    # Max drawdown
    cumulative = (1 + signal_returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_dd = drawdown.min()

    # Calmar ratio
    calmar = avg_return / abs(max_dd) if max_dd != 0 else 0.0

    # Information coefficient (correlation with subsequent returns)
    ic = 0.0  # Would calculate properly with aligned data

    # Turnover (simplified)
    turnover = 1.0 / holding_period

    return SignalPerformance(
        signal_name="signal",
        n_signals=len(signals),
        win_rate=round(win_rate, 3),
        avg_return=round(avg_return, 4),
        sharpe_ratio=round(sharpe, 3),
        max_drawdown=round(max_dd, 3),
        calmar_ratio=round(calmar, 3),
        information_coefficient=round(ic, 3),
        turnover=round(turnover, 3),
    )
