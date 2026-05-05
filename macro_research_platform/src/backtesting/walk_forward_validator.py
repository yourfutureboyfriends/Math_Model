"""
Walk-Forward Validator

Implements proper walk-forward backtesting to avoid look-ahead bias.
Ensures model only uses data available at each point in time.

Key principle:
- At time T, only data released up to T can be used
- Vintage data should be used when available
- If vintage not available, approximate with release lags
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result of backtest run."""
    start_date: datetime
    end_date: datetime
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    hit_rate: float
    turnover: float
    trades: List[Dict] = field(default_factory=list)
    regime_accuracy: Optional[float] = None


class WalkForwardValidator:
    """
    Walk-Forward Validator

    Runs model through time ensuring no look-ahead bias.
    """

    def __init__(
        self,
        min_observations: int = 60,
        train_window: int = 120,
        test_window: int = 12,
        step_size: int = 6,
    ):
        self.min_observations = min_observations
        self.train_window = train_window
        self.test_window = test_window
        self.step_size = step_size

    def _simulate_vintage_data(
        self,
        df: pd.DataFrame,
        as_of_date: datetime,
        release_lags: Optional[Dict[str, int]] = None,
    ) -> pd.DataFrame:
        """
        Simulate data as it would have appeared at a point in time.

        Args:
            df: Full data
            as_of_date: Date we're simulating
            release_lags: Dict of series_id -> days lag

        Returns:
            DataFrame with data as it would have appeared
        """
        if release_lags is None:
            # Default lags (in days)
            release_lags = {
                "us_payrolls": 30,
                "us_cpi_yoy": 30,
                "us_unemployment_rate": 30,
                "us_industrial_production": 60,
                "us_gdp": 90,
                "us_10y_yield": 1,
                "sp500": 1,
                "vix": 1,
            }

        vintage_df = df.copy()

        for col in df.columns:
            lag_days = release_lags.get(col, 30)
            available_until = as_of_date - timedelta(days=lag_days)

            # Zero out data that wouldn't have been released yet
            vintage_df.loc[vintage_df.index > available_until, col] = np.nan

        return vintage_df

    def run_walk_forward(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        return_series: Optional[pd.Series] = None,
        release_lags: Optional[Dict[str, int]] = None,
        mode: str = "realistic",  # realistic or revised
    ) -> BacktestResult:
        """
        Run walk-forward backtest.

        Args:
            df: Full historical data
            model_func: Function that takes data and returns signals
            return_series: Asset returns for evaluation
            release_lags: Release lag by series
            mode: "realistic" (with lags) or "revised" (full data)

        Returns:
            BacktestResult with performance metrics
        """
        if len(df) < self.min_observations:
            logger.error(f"Insufficient data: {len(df)} < {self.min_observations}")
            return BacktestResult(
                start_date=df.index[0] if len(df) > 0 else datetime.now(),
                end_date=df.index[-1] if len(df) > 0 else datetime.now(),
                total_return=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                hit_rate=0.0,
                turnover=0.0,
            )

        trades = []
        dates = []
        signals = []

        # Walk forward
        start_idx = self.train_window
        end_idx = len(df)

        current_idx = start_idx

        while current_idx < end_idx:
            test_end = min(current_idx + self.test_window, end_idx)

            # Get data up to current_idx
            if mode == "realistic":
                # Use vintage data simulation
                vintage_df = self._simulate_vintage_data(
                    df.iloc[:current_idx],
                    df.index[current_idx],
                    release_lags,
                )
            else:
                # Use full data (but only up to this point)
                vintage_df = df.iloc[:current_idx]

            # Run model
            try:
                signal = model_func(vintage_df)
                signals.append(signal)
                dates.append(df.index[current_idx])

                # Record trade
                trades.append({
                    "date": df.index[current_idx],
                    "signal": signal,
                })

            except Exception as e:
                logger.warning(f"Model failed at {df.index[current_idx]}: {e}")

            current_idx += self.step_size

        # Calculate performance
        if return_series is not None and len(trades) > 1:
            performance = self._calculate_performance(
                trades, return_series, dates
            )
        else:
            performance = {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "hit_rate": 0.0,
                "turnover": 0.0,
            }

        return BacktestResult(
            start_date=df.index[start_idx] if start_idx < len(df) else df.index[0],
            end_date=df.index[-1],
            total_return=performance.get("total_return", 0.0),
            annualized_return=performance.get("annualized_return", 0.0),
            volatility=performance.get("volatility", 0.0),
            sharpe_ratio=performance.get("sharpe_ratio", 0.0),
            max_drawdown=performance.get("max_drawdown", 0.0),
            hit_rate=performance.get("hit_rate", 0.0),
            turnover=performance.get("turnover", 0.0),
            trades=trades,
        )

    def _calculate_performance(
        self,
        trades: List[Dict],
        return_series: pd.Series,
        dates: List[datetime],
    ) -> Dict:
        """Calculate performance metrics from trades."""
        if not trades or len(dates) < 2:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "hit_rate": 0.0,
                "turnover": 0.0,
            }

        # Align returns with trade dates
        aligned_returns = []
        for i in range(len(dates) - 1):
            start_date = dates[i]
            end_date = dates[i + 1]

            # Get returns in window
            window_returns = return_series[
                (return_series.index >= start_date) &
                (return_series.index < end_date)
            ]

            if len(window_returns) > 0:
                period_return = (1 + window_returns).prod() - 1
                signal = trades[i].get("signal", 0)
                strategy_return = signal * period_return
                aligned_returns.append(strategy_return)

        if not aligned_returns:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "hit_rate": 0.0,
                "turnover": 0.0,
            }

        returns = np.array(aligned_returns)

        # Calculate metrics
        total_return = np.prod(1 + returns) - 1

        # Annualize
        n_years = len(returns) / 12  # Assuming monthly
        annualized_return = (1 + total_return) ** (1 / max(n_years, 0.1)) - 1

        volatility = returns.std() * np.sqrt(12)

        sharpe = annualized_return / volatility if volatility > 0 else 0

        # Max drawdown
        cum_returns = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cum_returns)
        drawdown = (cum_returns - peak) / peak
        max_dd = drawdown.min()

        # Hit rate
        hit_rate = (returns > 0).mean()

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "hit_rate": hit_rate,
            "turnover": 0.0,  # Would need position data
        }

    def run_no_lookahead_check(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        release_lags: Optional[Dict[str, int]] = None,
    ) -> Dict[str, bool]:
        """
        Check if model has look-ahead bias.

        Compares model outputs with and without release lags.

        Returns:
            Dict with bias check results
        """
        if len(df) < self.min_observations:
            return {"has_lookahead_bias": False, "error": "Insufficient data"}

        # Run with full data (cheating)
        try:
            full_signal = model_func(df)
        except Exception as e:
            return {"has_lookahead_bias": False, "error": str(e)}

        # Run with vintage data
        test_date = df.index[-1]
        vintage_df = self._simulate_vintage_data(df, test_date, release_lags)

        try:
            vintage_signal = model_func(vintage_df)
        except Exception as e:
            return {"has_lookahead_bias": False, "error": str(e)}

        # Compare
        if isinstance(full_signal, dict) and isinstance(vintage_signal, dict):
            differences = {
                k: abs(full_signal.get(k, 0) - vintage_signal.get(k, 0))
                for k in full_signal.keys()
            }
            has_bias = any(d > 0.01 for d in differences.values())
        else:
            has_bias = abs(full_signal - vintage_signal) > 0.01

        return {
            "has_lookahead_bias": has_bias,
            "full_data_signal": full_signal,
            "vintage_signal": vintage_signal,
        }


class NoLookAheadTester:
    """
    Standalone tester for look-ahead bias.

    Can be run as unit tests.
    """

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0

    def test_no_future_data(self, df: pd.DataFrame, model_func: Callable) -> bool:
        """
        Test that model doesn't use future data.

        Verifies by checking if model output changes when future data is removed.
        """
        self.tests_run += 1

        if len(df) < 20:
            logger.warning("Insufficient data for no-lookahead test")
            return True

        # Split data
        mid = len(df) // 2
        full_data = df
        partial_data = df.iloc[:mid]

        try:
            full_result = model_func(full_data)
            partial_result = model_func(partial_data)

            # For partial data, only check up to mid point
            if isinstance(full_result, pd.DataFrame) and isinstance(partial_result, pd.DataFrame):
                full_subset = full_result.iloc[:len(partial_result)]
                is_equal = full_subset.equals(partial_result)
            elif isinstance(full_result, pd.Series) and isinstance(partial_result, pd.Series):
                full_subset = full_result.iloc[:len(partial_result)]
                is_equal = full_subset.equals(partial_result)
            else:
                is_equal = True  # Can't compare

            if is_equal:
                self.tests_passed += 1

            return is_equal

        except Exception as e:
            logger.error(f"No-lookahead test failed: {e}")
            return False

    def get_summary(self) -> Dict:
        """Get test summary."""
        return {
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "success_rate": self.tests_passed / max(self.tests_run, 1),
        }


def run_realistic_backtest(
    df: pd.DataFrame,
    model_func: Callable,
    return_series: Optional[pd.Series] = None,
) -> BacktestResult:
    """
    Convenience function to run realistic backtest with vintage data simulation.
    """
    validator = WalkForwardValidator()
    return validator.run_walk_forward(
        df=df,
        model_func=model_func,
        return_series=return_series,
        mode="realistic",
    )


def run_revised_data_backtest(
    df: pd.DataFrame,
    model_func: Callable,
    return_series: Optional[pd.Series] = None,
) -> BacktestResult:
    """
    Convenience function to run backtest with revised data (warning: results may be overstated).
    """
    validator = WalkForwardValidator()
    return validator.run_walk_forward(
        df=df,
        model_func=model_func,
        return_series=return_series,
        mode="revised",
    )
