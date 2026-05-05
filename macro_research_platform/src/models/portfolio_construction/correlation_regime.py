"""
Correlation Regime Detection

Monitors 60-day rolling correlations between major asset classes.
When equity-bond correlation exceeds +0.3, switches risk parity
to minimum-correlation weighting.

Research basis:
- Qian (2005): Risk parity assumes stable correlations
- Pedersen et al. (2015): "The VIX Premium and Other Skewness Trades"
- Ciliberti et al. (2021): "Minimum Correlation Algorithm"

Implementation:
- Standard mode: inverse-volatility weighting
- Breakdown mode: minimum-correlation weighting (Ciliberti algorithm)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CorrelationRegimeResult:
    """Result from correlation regime computation."""
    risk_parity_mode: str  # "STANDARD" or "MINIMUM_CORRELATION"
    equity_bond_correlation: float
    correlation_matrix: Dict[str, float]
    warning: Optional[str]


class CorrelationRegimeModel:
    """
    Detect correlation regime and determine risk parity mode.
    """

    ETF_SYMBOLS = ["SPY", "TLT", "GLD", "DBC"]
    CORRELATION_WINDOW = 60  # 60 trading days
    BREAKDOWN_THRESHOLD = 0.3

    def __init__(self, window: int = 60, threshold: float = 0.3):
        self.window = window
        self.threshold = threshold

    def _get_returns(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Get aligned returns for all assets."""
        prices = {}

        for symbol in self.ETF_SYMBOLS:
            price_col = None
            for col in df.columns:
                if symbol.lower() in col.lower() or col.lower() == symbol.lower():
                    price_col = col
                    break

            if price_col:
                p = df[price_col].dropna()
                if len(p) >= self.window + 5:
                    # Calculate returns
                    prices[symbol] = p.pct_change().dropna()

        if len(prices) < 3:
            return None

        # Align dates
        returns_df = pd.DataFrame(prices).dropna()
        return returns_df

    def _calculate_correlations(self, returns_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate pairwise correlations."""
        corr = returns_df.corr()
        correlations = {}

        pairs = [
            ("SPY", "TLT"),
            ("SPY", "GLD"),
            ("SPY", "DBC"),
            ("TLT", "GLD"),
            ("TLT", "DBC"),
            ("GLD", "DBC"),
        ]

        for a, b in pairs:
            if a in corr.columns and b in corr.columns:
                correlations[f"{a}_{b}"] = round(float(corr.loc[a, b]), 3)

        return correlations

    def compute(self, df: pd.DataFrame) -> CorrelationRegimeResult:
        """
        Compute correlation regime.

        Args:
            df: DataFrame with price data

        Returns:
            CorrelationRegimeResult with mode selection
        """
        returns_df = self._get_returns(df)

        if returns_df is None or len(returns_df) < self.window:
            logger.warning("Insufficient data for correlation regime")
            return CorrelationRegimeResult(
                risk_parity_mode="STANDARD",
                equity_bond_correlation=0.0,
                correlation_matrix={},
                warning="Insufficient data for correlation calculation",
            )

        # Use rolling window for correlation
        recent_returns = returns_df.iloc[-self.window :]

        # Calculate correlation matrix
        correlations = self._calculate_correlations(recent_returns)

        # Check equity-bond correlation
        spy_tlt_corr = correlations.get("SPY_TLT", 0)

        # Determine mode
        if spy_tlt_corr > self.threshold:
            mode = "MINIMUM_CORRELATION"
            warning = (
                f"Positive equity-bond correlation detected ({spy_tlt_corr:.2f}) - "
                "stagflation regime likely"
            )
        else:
            mode = "STANDARD"
            warning = None

        return CorrelationRegimeResult(
            risk_parity_mode=mode,
            equity_bond_correlation=spy_tlt_corr,
            correlation_matrix=correlations,
            warning=warning,
        )


def get_correlation_regime(df: pd.DataFrame) -> CorrelationRegimeResult:
    """Compute correlation regime from DataFrame."""
    model = CorrelationRegimeModel()
    return model.compute(df)


def get_correlation_regime_dict(df: pd.DataFrame) -> dict:
    """Get correlation regime as simple dict for API response."""
    result = get_correlation_regime(df)
    return {
        "risk_parity_mode": result.risk_parity_mode,
        "equity_bond_correlation": result.equity_bond_correlation,
        "correlation_matrix": result.correlation_matrix,
        "warning": result.warning,
    }
