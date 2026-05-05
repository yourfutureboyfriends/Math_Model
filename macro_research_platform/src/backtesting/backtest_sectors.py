"""
backtest_sectors.py — Backtest sector allocation signals with historical simulation.

Financial context:
  A backtest answers: "How would these signals have performed historically?"
  This is essential before deploying any systematic strategy.

  Key requirements for a valid backtest:
    1. No lookahead bias — use only data available at time t
    2. Walk-forward calculation — recompute signals each period
    3. Realistic assumptions — transaction costs, slippage
    4. Out-of-sample validation — test on data not used for calibration

  For this model:
    - At each date, compute signals using data available UP TO that date
    - Compare OW/UW signals to subsequent returns (1M, 3M, 6M)
    - Track hit rate: % of times OW sectors outperformed UW sectors
    - Track return spread: avg return when OW vs UW

Synthetic sector returns:
  Until real sector ETF data is integrated, we generate synthetic returns
  loosely correlated with relevant macro factors:
    - Technology: negatively correlated with real rates (10Y - inflation)
    - Energy: positively correlated with oil prices and inflation
    - Banks: positively correlated with yield curve slope
    - etc.

  This demonstrates the backtesting framework and can be replaced with
  real returns (e.g., XLF, XLK, XLE, etc.) later.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Synthetic Sector Return Generator
# =============================================================================

def generate_synthetic_sector_returns(
    df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic monthly sector returns correlated with macro factors.

    This is a placeholder until real sector ETF data is integrated.
    Returns are designed to plausibly reflect historical relationships.

    Args:
        df: DataFrame with macro indicators (cpi_yoy, pmi, yield_curve, etc.)
        seed: Random seed for reproducibility

    Returns:
        DataFrame with monthly returns for each sector
    """
    np.random.seed(seed)
    n = len(df)

    # Ensure we have monthly frequency
    returns = pd.DataFrame(index=df.index)

    # Get macro factor changes
    cpi_change = df.get("cpi_yoy", pd.Series(0, index=df.index)).diff()
    pmi_change = df.get("pmi", pd.Series(50, index=df.index)).diff()
    yield_curve = df.get("yield_curve", pd.Series(0, index=df.index))
    oil_change = df.get("oil_price", pd.Series(50, index=df.index)).pct_change() * 100

    # Market noise (common factor)
    market_noise = np.random.normal(0, 0.04, n)  # 4% monthly volatility

    # Technology: hurt by rising rates, helped by growth
    # Beta: -0.5 to real rates, +0.3 to growth
    real_rates = df.get("yield_10y", pd.Series(2, index=df.index)) - df.get("cpi_yoy", pd.Series(2, index=df.index))
    real_rate_change = real_rates.diff()
    returns["Technology"] = (
        0.005 +  # Base drift
        0.3 * pmi_change +  # Growth sensitivity
        -0.5 * real_rate_change +  # Rate sensitivity
        0.8 * market_noise +  # Market correlation
        np.random.normal(0, 0.03, n)  # Idiosyncratic noise
    )

    # Energy: driven by oil prices and inflation
    returns["Energy"] = (
        0.004 +
        0.4 * oil_change.fillna(0) +
        0.2 * cpi_change +
        1.0 * market_noise +
        np.random.normal(0, 0.06, n)  # Higher volatility
    )

    # Banks: driven by yield curve and credit conditions
    credit_spreads = df.get("credit_spreads", pd.Series(100, index=df.index))
    credit_change = credit_spreads.diff()
    returns["Banks"] = (
        0.006 +
        0.3 * yield_curve.diff() +
        -0.1 * credit_change.fillna(0) +
        1.1 * market_noise +
        np.random.normal(0, 0.05, n)
    )

    # Consumer Discretionary: driven by employment and real wages
    unemp = df.get("unemployment_rate", pd.Series(4, index=df.index))
    unemp_change = unemp.diff()
    returns["Consumer Discretionary"] = (
        0.005 +
        -0.4 * unemp_change.fillna(0) +  # Lower unemployment is good
        0.3 * pmi_change +
        1.0 * market_noise +
        np.random.normal(0, 0.04, n)
    )

    # Utilities: defensive, bond-like, hurt by rising rates
    returns["Utilities"] = (
        0.003 +
        -0.3 * real_rate_change.fillna(0) +
        0.5 * market_noise +
        np.random.normal(0, 0.03, n)
    )

    # Industrials: cyclical, driven by PMI
    returns["Industrials"] = (
        0.005 +
        0.5 * pmi_change +
        1.1 * market_noise +
        np.random.normal(0, 0.04, n)
    )

    # Healthcare: defensive, less cyclical
    returns["Healthcare"] = (
        0.004 +
        0.2 * pmi_change +
        0.6 * market_noise +
        np.random.normal(0, 0.03, n)
    )

    # Annualize monthly returns (already in decimal)
    # No conversion needed — we're generating monthly returns directly

    return returns


# =============================================================================
# Sector Backtester
# =============================================================================

class SectorBacktester:
    """
    Walk-forward backtest of sector allocation signals.

    Simulates the strategy of following model signals historically,
    computing hit rates and return distributions.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        sector_returns: Optional[pd.DataFrame] = None,
        transaction_cost: float = 0.001,  # 10 bps per trade
    ):
        """
        Initialize the backtester.

        Args:
            df: DataFrame with macro indicators
            sector_returns: DataFrame with sector returns (generates synthetic if None)
            transaction_cost: Cost per trade as decimal (e.g., 0.001 = 0.1%)
        """
        self.df = df.copy()
        self.transaction_cost = transaction_cost

        # Generate or use provided sector returns
        if sector_returns is None:
            self.sector_returns = generate_synthetic_sector_returns(df)
        else:
            self.sector_returns = sector_returns.copy()

        # Results storage
        self.results: Optional[pd.DataFrame] = None

    def _compute_signals_at_date(
        self,
        date: pd.Timestamp,
    ) -> Dict[str, str]:
        """
        Compute sector signals using only data up to the given date.

        Critical: NO LOOKAHEAD — uses historical data only.

        Args:
            date: Current date for signal calculation

        Returns:
            Dict mapping sector to signal (Overweight/Neutral/Underweight)
        """
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.data_loader import load_macro_data
        from src.transformations import compute_all_transforms
        from src.scoring import compute_group_scores
        from src.regimes import classify_regime, get_regime_history
        from src.sector_model import compute_sector_scores, get_sector_signals

        # Get data up to this date
        historical = self.df.loc[:date]

        if len(historical) < 13:  # Need at least 13 months for YoY changes
            return {s: "Neutral" for s in self.sector_returns.columns}

        # Compute transforms on historical data only
        df_trans = compute_all_transforms(historical)

        # Compute scores
        scores_df = compute_group_scores(df_trans)

        if len(scores_df) < 4:  # Need at least 4 observations
            return {s: "Neutral" for s in self.sector_returns.columns}

        # Get current scores and directions
        current_scores = scores_df.iloc[-1]
        past_scores = scores_df.iloc[-4] if len(scores_df) >= 4 else scores_df.iloc[0]

        growth_score = current_scores.get("growth_score", 0)
        infl_score = current_scores.get("inflation_score", 0)
        liq_score = current_scores.get("liquidity_score", 0)
        risk_score = current_scores.get("risk_score", 0)

        # Determine directions (3-month change)
        growth_dir = "improving" if growth_score > past_scores.get("growth_score", 0) + 0.1 else \
                     "deteriorating" if growth_score < past_scores.get("growth_score", 0) - 0.1 else "stable"
        infl_dir = "rising" if infl_score > past_scores.get("inflation_score", 0) + 0.1 else \
                   "falling" if infl_score < past_scores.get("inflation_score", 0) - 0.1 else "stable"

        # Classify regime
        regime = classify_regime(growth_dir, infl_dir)

        # Compute sector scores
        sector_scores = compute_sector_scores(
            regime,
            growth_score,
            liq_score,
            risk_score,
        )

        # Convert to signals
        signals = get_sector_signals(sector_scores)

        return signals

    def run(
        self,
        forward_windows: List[int] = [1, 3, 6],
        min_history: int = 24,
    ) -> pd.DataFrame:
        """
        Run walk-forward backtest.

        Args:
            forward_windows: List of forward return windows in months
            min_history: Minimum months of history before starting

        Returns:
            DataFrame with backtest results
        """
        results = []

        # Get valid dates (after min_history and with sector return data)
        valid_dates = self.df.index[min_history:]

        for i, date in enumerate(valid_dates):
            if i % 12 == 0:  # Progress update every year
                logger.info(f"Backtesting: {date.strftime('%Y-%m')} ({i}/{len(valid_dates)})")

            # Compute signals at this date (no lookahead)
            try:
                signals = self._compute_signals_at_date(date)
            except Exception as e:
                logger.warning(f"Failed to compute signals at {date}: {e}")
                continue

            # Get forward returns
            date_idx = self.sector_returns.index.get_loc(date)

            for window in forward_windows:
                if date_idx + window >= len(self.sector_returns):
                    continue

                fwd_returns = self.sector_returns.iloc[date_idx + 1:date_idx + window + 1].sum()

                for sector, signal in signals.items():
                    if sector not in fwd_returns:
                        continue

                    ret = fwd_returns[sector]

                    results.append({
                        "date": date,
                        "sector": sector,
                        "signal": signal,
                        "forward_return": ret,
                        "window": window,
                    })

        self.results = pd.DataFrame(results)
        return self.results

    def compute_metrics(self) -> pd.DataFrame:
        """
        Compute hit rate and return metrics by signal.

        Returns:
            DataFrame with metrics for each signal type
        """
        if self.results is None or self.results.empty:
            return pd.DataFrame()

        metrics = []

        for window in self.results["window"].unique():
            window_data = self.results[self.results["window"] == window]

            for signal in ["Overweight", "Neutral", "Underweight"]:
                signal_data = window_data[window_data["signal"] == signal]

                if len(signal_data) < 5:
                    continue

                returns = signal_data["forward_return"]

                metrics.append({
                    "window_months": window,
                    "signal": signal,
                    "count": len(returns),
                    "mean_return": returns.mean(),
                    "std_return": returns.std(),
                    "sharpe": returns.mean() / (returns.std() or 1) * np.sqrt(12 / window),
                    "hit_rate": (returns > 0).mean(),
                    "win_loss_ratio": returns[returns > 0].mean() / abs(returns[returns < 0].mean()) if (returns < 0).any() else np.nan,
                })

        return pd.DataFrame(metrics)

    def compute_spread_metrics(self) -> pd.DataFrame:
        """
        Compute OW - UW spread metrics.

        Returns:
            DataFrame with spread analysis
        """
        if self.results is None or self.results.empty:
            return pd.DataFrame()

        spreads = []

        for window in self.results["window"].unique():
            window_data = self.results[self.results["window"] == window]

            ow_data = window_data[window_data["signal"] == "Overweight"]
            uw_data = window_data[window_data["signal"] == "Underweight"]

            if len(ow_data) == 0 or len(uw_data) == 0:
                continue

            ow_returns = ow_data.groupby("date")["forward_return"].mean()
            uw_returns = uw_data.groupby("date")["forward_return"].mean()

            # Align dates
            common_dates = ow_returns.index.intersection(uw_returns.index)
            if len(common_dates) < 5:
                continue

            spread = ow_returns[common_dates] - uw_returns[common_dates]

            spreads.append({
                "window_months": window,
                "mean_spread": spread.mean(),
                "std_spread": spread.std(),
                "t_stat": spread.mean() / (spread.std() / np.sqrt(len(spread))),
                "positive_pct": (spread > 0).mean(),
                "sharpe": spread.mean() / (spread.std() or 1) * np.sqrt(12 / window),
            })

        return pd.DataFrame(spreads)

    def save_results(self, path: Optional[Path] = None) -> Path:
        """
        Save backtest results to CSV.

        Args:
            path: Output path (uses default if None)

        Returns:
            Path to saved file
        """
        if path is None:
            path = Path(__file__).parent.parent / "data" / "processed" / "backtest_results" / "sector_backtest.csv"

        path.parent.mkdir(parents=True, exist_ok=True)

        # Save detailed results
        if self.results is not None:
            self.results.to_csv(path, index=False)

        # Save summary metrics
        metrics = self.compute_metrics()
        if not metrics.empty:
            metrics.to_csv(path.parent / "sector_metrics.csv", index=False)

        spread_metrics = self.compute_spread_metrics()
        if not spread_metrics.empty:
            spread_metrics.to_csv(path.parent / "spread_metrics.csv", index=False)

        logger.info(f"Backtest results saved to {path}")
        return path


# =============================================================================
# Convenience Functions
# =============================================================================

def backtest_sector_signals(
    df: pd.DataFrame,
    sector_returns: Optional[pd.DataFrame] = None,
    forward_windows: List[int] = [1, 3, 6],
) -> Dict[str, pd.DataFrame]:
    """
    Run complete sector signal backtest and return all results.

    Args:
        df: DataFrame with macro indicators
        sector_returns: Optional DataFrame with actual sector returns
        forward_windows: Forward return windows to analyze

    Returns:
        Dict with results DataFrames
    """
    backtester = SectorBacktester(df, sector_returns)
    backtester.run(forward_windows=forward_windows)

    return {
        "results": backtester.results,
        "metrics": backtester.compute_metrics(),
        "spreads": backtester.compute_spread_metrics(),
    }
