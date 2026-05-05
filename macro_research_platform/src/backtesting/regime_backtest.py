"""
regime_backtest.py — Analyze asset class returns by regime historically.

Financial context:
  The core thesis of regime-based investing is that different regimes have
different return distributions for different asset classes. This module
quantifies those differences.

Key analyses:
  1. Return distribution by regime: mean, volatility, Sharpe for each
  2. Regime persistence: how long do regimes typically last?
  3. Transition probabilities: likelihood of moving from regime A to B
  4. Drawdown analysis: worst periods in each regime

Asset classes covered:
  - Equities (broad market)
  - Government bonds (duration)
  - Credit (corporate bonds)
  - Commodities (basket)

Synthetic returns:
  Until real ETF data is integrated, we generate synthetic returns:
    - Equities: correlated with growth and negatively with real rates
    - Bonds: positively correlated with falling inflation and rates
    - Credit: hybrid of equities and bonds, sensitive to spreads
    - Commodities: driven by inflation and supply/demand

  This can be replaced with real returns (SPY, TLT, HYG, GLD, etc.).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Synthetic Asset Return Generator
# =============================================================================

def generate_synthetic_asset_returns(
    df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic monthly returns for major asset classes.

    Args:
        df: DataFrame with macro indicators
        seed: Random seed for reproducibility

    Returns:
        DataFrame with monthly returns for each asset class
    """
    np.random.seed(seed)
    n = len(df)

    returns = pd.DataFrame(index=df.index)

    # Common market factor
    market_factor = np.random.normal(0, 0.04, n)

    # Get macro changes
    cpi_change = df.get("cpi_yoy", pd.Series(2, index=df.index)).diff()
    pmi_change = df.get("pmi", pd.Series(50, index=df.index)).diff()
    yield_curve = df.get("yield_curve", pd.Series(0, index=df.index))
    credit_spreads = df.get("credit_spreads", pd.Series(100, index=df.index))
    spread_change = credit_spreads.diff()
    oil_change = df.get("oil_price", pd.Series(50, index=df.index)).pct_change() * 100

    # 10Y Treasury yield
    treasury_yield = df.get("yield_10y", pd.Series(3, index=df.index))
    yield_change = treasury_yield.diff()

    # Real rates (approximate)
    real_rates = treasury_yield - df.get("cpi_yoy", pd.Series(2, index=df.index))
    real_rate_change = real_rates.diff()

    # Equities (broad market)
    # Driven by: growth (+), real rates (-), credit spreads (-)
    returns["Equities"] = (
        0.006 +  # Base drift (7% annual / 12)
        0.4 * pmi_change +  # Growth sensitivity
        -0.3 * real_rate_change.fillna(0) +  # Rate sensitivity
        -0.05 * spread_change.fillna(0) +  # Credit spread sensitivity
        1.0 * market_factor +
        np.random.normal(0, 0.03, n)
    )

    # Government Bonds (10Y duration)
    # Driven by: rate changes (-), inflation falling (+)
    returns["Bonds"] = (
        0.002 +  # Lower base drift
        -0.8 * yield_change.fillna(0) +  # Duration: rates down = prices up
        -0.2 * cpi_change +  # Lower inflation helps bonds
        0.3 * market_factor +  # Flight-to-quality correlation
        np.random.normal(0, 0.02, n)  # Lower volatility
    )

    # Credit (corporate bonds)
    # Hybrid of equities and bonds, sensitive to spreads
    returns["Credit"] = (
        0.004 +
        0.5 * returns["Equities"] +  # Equity component
        0.5 * returns["Bonds"] +  # Duration component
        -0.1 * spread_change.fillna(0) +  # Spread widening hurts
        np.random.normal(0, 0.025, n)
    )

    # Commodities
    # Driven by: inflation (+), growth (+), oil prices
    returns["Commodities"] = (
        0.003 +
        0.3 * cpi_change +  # Inflation hedge
        0.2 * pmi_change +  # Growth sensitivity
        0.3 * oil_change.fillna(0) +  # Oil correlation
        0.4 * market_factor +
        np.random.normal(0, 0.05, n)  # High volatility
    )

    return returns


# =============================================================================
# Regime Backtester
# =============================================================================

class RegimeBacktester:
    """
    Analyze historical asset class performance by regime.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        asset_returns: Optional[pd.DataFrame] = None,
    ):
        """
        Initialize the regime backtester.

        Args:
            df: DataFrame with macro indicators
            asset_returns: DataFrame with asset returns (generates synthetic if None)
        """
        self.df = df.copy()

        # Generate or use provided asset returns
        if asset_returns is None:
            self.asset_returns = generate_synthetic_asset_returns(df)
        else:
            self.asset_returns = asset_returns.copy()

        # Compute regime history
        self.regime_series = self._compute_regime_history()

    def _compute_regime_history(self) -> pd.Series:
        """Compute regime classification for all dates."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.transformations import compute_all_transforms
        from src.scoring import compute_group_scores
        from src.regimes import classify_regime

        df_trans = compute_all_transforms(self.df)
        scores_df = compute_group_scores(df_trans)

        regimes = []
        for i in range(len(scores_df)):
            if i < 3:
                regimes.append(None)
                continue

            g_now = scores_df["growth_score"].iloc[i]
            g_past = scores_df["growth_score"].iloc[i - 3]
            i_now = scores_df["inflation_score"].iloc[i]
            i_past = scores_df["inflation_score"].iloc[i - 3]

            THRESHOLD = 0.10
            g_dir = "improving" if (g_now - g_past) > THRESHOLD else \
                    "deteriorating" if (g_now - g_past) < -THRESHOLD else "stable"
            i_dir = "rising" if (i_now - i_past) > THRESHOLD else \
                    "falling" if (i_now - i_past) < -THRESHOLD else "stable"

            regime = classify_regime(g_dir, i_dir)
            regimes.append(regime)

        return pd.Series(regimes, index=scores_df.index, name="regime")

    def analyze_regime_returns(self) -> pd.DataFrame:
        """
        Compute return statistics by regime and asset class.

        Returns:
            DataFrame with mean, std, Sharpe for each regime/asset combination
        """
        results = []

        # Align indices
        common_idx = self.regime_series.index.intersection(self.asset_returns.index)
        regimes = self.regime_series.loc[common_idx]
        returns = self.asset_returns.loc[common_idx]

        for regime in ["Goldilocks", "Reflation", "Slowdown", "Stagflation"]:
            regime_mask = regimes == regime
            regime_returns = returns[regime_mask]

            if len(regime_returns) < 6:
                continue

            for asset in returns.columns:
                asset_rets = regime_returns[asset]

                if len(asset_rets) < 6:
                    continue

                # Annualize
                mean_annual = asset_rets.mean() * 12
                std_annual = asset_rets.std() * np.sqrt(12)

                results.append({
                    "regime": regime,
                    "asset_class": asset,
                    "n_months": len(asset_rets),
                    "mean_annual": mean_annual,
                    "std_annual": std_annual,
                    "sharpe": mean_annual / (std_annual or 1),
                    "win_rate": (asset_rets > 0).mean(),
                    "max_drawdown": self._compute_max_drawdown(asset_rets),
                })

        return pd.DataFrame(results)

    def _compute_max_drawdown(self, returns: pd.Series) -> float:
        """Compute maximum drawdown from returns series."""
        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdown = cumulative / rolling_max - 1
        return drawdown.min()

    def analyze_regime_transitions(self) -> pd.DataFrame:
        """
        Analyze regime transition probabilities and persistence.

        Returns:
            DataFrame with transition matrix
        """
        regimes = self.regime_series.dropna()

        if len(regimes) < 12:
            return pd.DataFrame()

        transitions = pd.DataFrame(
            0,
            index=["Goldilocks", "Reflation", "Slowdown", "Stagflation"],
            columns=["Goldilocks", "Reflation", "Slowdown", "Stagflation"],
        )

        # Count transitions
        for i in range(1, len(regimes)):
            prev_regime = regimes.iloc[i - 1]
            curr_regime = regimes.iloc[i]

            if prev_regime in transitions.index and curr_regime in transitions.columns:
                transitions.loc[prev_regime, curr_regime] += 1

        # Convert to probabilities (row sums to 1)
        transition_probs = transitions.div(transitions.sum(axis=1), axis=0).fillna(0)

        return transition_probs

    def analyze_regime_persistence(self) -> pd.DataFrame:
        """
        Analyze how long regimes typically persist.

        Returns:
            DataFrame with regime duration statistics
        """
        regimes = self.regime_series.dropna()

        if len(regimes) < 6:
            return pd.DataFrame()

        # Identify regime runs
        current_regime = regimes.iloc[0]
        current_start = 0
        runs = []

        for i in range(1, len(regimes)):
            if regimes.iloc[i] != current_regime:
                runs.append({
                    "regime": current_regime,
                    "duration": i - current_start,
                    "start_idx": current_start,
                    "end_idx": i - 1,
                })
                current_regime = regimes.iloc[i]
                current_start = i

        # Add final run
        runs.append({
            "regime": current_regime,
            "duration": len(regimes) - current_start,
            "start_idx": current_start,
            "end_idx": len(regimes) - 1,
        })

        runs_df = pd.DataFrame(runs)

        # Compute statistics by regime
        stats = []
        for regime in runs_df["regime"].unique():
            regime_runs = runs_df[runs_df["regime"] == regime]

            stats.append({
                "regime": regime,
                "n_episodes": len(regime_runs),
                "avg_duration_months": regime_runs["duration"].mean(),
                "median_duration": regime_runs["duration"].median(),
                "min_duration": regime_runs["duration"].min(),
                "max_duration": regime_runs["duration"].max(),
                "total_months": regime_runs["duration"].sum(),
                "pct_of_time": regime_runs["duration"].sum() / len(regimes) * 100,
            })

        return pd.DataFrame(stats)

    def save_results(self, path: Optional[Path] = None) -> Path:
        """Save regime backtest results to CSV."""
        if path is None:
            path = Path(__file__).parent.parent / "data" / "processed" / "backtest_results"

        path.mkdir(parents=True, exist_ok=True)

        # Save regime returns
        returns_df = self.analyze_regime_returns()
        if not returns_df.empty:
            returns_df.to_csv(path / "regime_returns.csv", index=False)

        # Save transitions
        transitions = self.analyze_regime_transitions()
        if not transitions.empty:
            transitions.to_csv(path / "regime_transitions.csv")

        # Save persistence
        persistence = self.analyze_regime_persistence()
        if not persistence.empty:
            persistence.to_csv(path / "regime_persistence.csv", index=False)

        # Save regime series
        self.regime_series.to_frame().to_csv(path / "regime_history.csv")

        logger.info(f"Regime backtest results saved to {path}")
        return path


# =============================================================================
# Convenience Functions
# =============================================================================

def analyze_regime_returns(
    df: pd.DataFrame,
    asset_returns: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Complete regime backtest analysis.

    Args:
        df: DataFrame with macro indicators
        asset_returns: Optional DataFrame with actual asset returns

    Returns:
        Dict with analysis DataFrames
    """
    backtester = RegimeBacktester(df, asset_returns)

    return {
        "returns": backtester.analyze_regime_returns(),
        "transitions": backtester.analyze_regime_transitions(),
        "persistence": backtester.analyze_regime_persistence(),
        "regime_series": backtester.regime_series,
    }
