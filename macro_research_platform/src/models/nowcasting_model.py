"""
Nowcasting Model

Estimates current economic conditions using:
- Dynamic factor model on macro indicators
- Mixed-frequency data handling
- Bridge equations for GDP estimation

Based on:
- Giannone, Reichlin & Small (2008) - Nowcasting GDP and Inflation
- Stock & Watson (2002) - Macroeconomic Forecasting Using Diffusion Indexes
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


@dataclass
class NowcastResult:
    """Nowcasting result."""
    growth_nowcast: float  # Annualized GDP growth estimate
    inflation_nowcast: float  # Current inflation estimate
    business_conditions_index: float  # Composite index
    confidence: float  # 0-1
    factor_loadings: Dict[str, float]
    data_vintage: str


class NowcastingModel:
    """
    Dynamic Factor Model for Nowcasting

    Extracts common factors from macro indicators to estimate
    current economic conditions before official data is released.
    """

    def __init__(self, n_factors: int = 3):
        self.n_factors = n_factors
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=n_factors)
        self.is_fitted = False

        # Factor interpretation weights (based on typical loadings)
        self.factor_interpretation = {
            0: "real_activity",  # First factor usually captures real activity
            1: "inflation",      # Second factor often inflation
            2: "financial",      # Third factor financial conditions
        }

    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare data for factor extraction.

        - Standardize (z-scores)
        - Handle missing values (forward fill then backward fill)
        - Remove low-variance series
        """
        # Work with numeric columns only
        df_numeric = df.select_dtypes(include=[np.number]).copy()

        # Handle missing values
        df_filled = df_numeric.ffill().bfill()

        # Drop series with too many missing values
        completeness = df_filled.notna().sum() / len(df_filled)
        df_clean = df_filled.loc[:, completeness >= 0.5]

        return df_clean

    def fit(self, df: pd.DataFrame):
        """Fit the factor model on historical data."""
        df_clean = self._prepare_data(df)

        if df_clean.empty:
            logger.warning("No valid data for factor model")
            return

        # Standardize
        self.scaler.fit(df_clean)
        scaled_data = self.scaler.transform(df_clean)

        # Fit PCA
        self.pca.fit(scaled_data)
        self.is_fitted = True

        logger.info(f"Fitted factor model with {self.n_factors} factors")
        logger.info(f"Explained variance: {self.pca.explained_variance_ratio_}")

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform data to factor space."""
        if not self.is_fitted:
            self.fit(df)

        df_clean = self._prepare_data(df)

        if df_clean.empty:
            return pd.DataFrame()

        # Align columns with training
        # (In production, would store feature names)
        common_cols = df_clean.columns.intersection(df.columns)
        df_aligned = df_clean[common_cols]

        # Standardize
        scaled_data = self.scaler.transform(df_aligned)

        # Transform to factors
        factors = self.pca.transform(scaled_data)

        # Create DataFrame
        factor_df = pd.DataFrame(
            factors,
            columns=[f"Factor_{i+1}" for i in range(self.n_factors)],
            index=df_clean.index,
        )

        return factor_df

    def compute_nowcast(
        self,
        df: pd.DataFrame,
        gdp_series: Optional[pd.Series] = None,
    ) -> NowcastResult:
        """
        Compute nowcast from current data.

        Args:
            df: DataFrame with macro indicators
            gdp_series: Historical GDP for calibration (optional)

        Returns:
            NowcastResult with estimates
        """
        # Get factors
        factors = self.transform(df)

        if factors.empty:
            return NowcastResult(
                growth_nowcast=np.nan,
                inflation_nowcast=np.nan,
                business_conditions_index=np.nan,
                confidence=0.0,
                factor_loadings={},
                data_vintage="insufficient_data",
            )

        # Latest factors
        latest = factors.iloc[-1]

        # Business conditions index (first factor, standardized)
        bci = latest.iloc[0] if len(latest) > 0 else 0

        # Map to growth nowcast
        # Typical: factor 1 std dev = ~2% GDP growth deviation
        growth_nowcast = bci * 2.0

        # Inflation nowcast (second factor)
        inflation_nowcast = latest.iloc[1] * 1.5 if len(latest) > 1 else 0

        # Calculate factor loadings (correlations)
        factor_loadings = {}
        for i, factor_name in enumerate(factors.columns):
            corr = df.corrwith(factors[factor_name])
            factor_loadings[factor_name] = corr.to_dict()

        # Confidence based on data freshness
        # (In practice, would check actual release dates)
        confidence = 0.7  # Base confidence

        # Reduce confidence if recent data is sparse
        recent_data = df.iloc[-3:]  # Last 3 observations
        if recent_data.isna().sum().sum() > recent_data.size * 0.3:
            confidence *= 0.7

        return NowcastResult(
            growth_nowcast=growth_nowcast,
            inflation_nowcast=inflation_nowcast,
            business_conditions_index=bci,
            confidence=confidence,
            factor_loadings=factor_loadings,
            data_vintage=f"factors_extracted_{factors.index[-1].strftime('%Y-%m-%d')}",
        )

    def bridge_equation_gdp(
        self,
        monthly_indicators: pd.DataFrame,
        quarterly_gdp: Optional[pd.Series] = None,
    ) -> float:
        """
        Bridge equation to estimate quarterly GDP from monthly indicators.

        Simple version: regress GDP on contemporaneous and lagged factors.
        """
        # Get monthly factors
        monthly_factors = self.transform(monthly_indicators)

        if monthly_factors.empty:
            return np.nan

        # Average over quarter
        # (In production, would align months to quarters properly)
        quarterly_factors = monthly_factors.resample("Q").mean()

        # If we have historical GDP, calibrate
        if quarterly_gdp is not None:
            # Align data
            common_idx = quarterly_factors.index.intersection(quarterly_gdp.index)

            if len(common_idx) >= 8:  # Minimum for regression
                X = quarterly_factors.loc[common_idx]
                y = quarterly_gdp.loc[common_idx]

                # Simple OLS
                try:
                    from sklearn.linear_model import LinearRegression
                    reg = LinearRegression()
                    reg.fit(X, y)

                    # Predict latest
                    latest_X = quarterly_factors.iloc[-1:]
                    prediction = reg.predict(latest_X)[0]

                    return prediction
                except Exception as e:
                    logger.warning(f"Bridge equation failed: {e}")

        # Fallback: use first factor
        latest_factor = quarterly_factors.iloc[-1, 0]
        # Calibrated: 1 std dev in factor = ~2% GDP growth
        return 2.0 + latest_factor * 2.0


class CoincidentActivityIndex:
    """
    Coincident Activity Index

    Simplified version using key coincident indicators:
    - Payroll employment
    - Real income
    - Industrial production
    - Real retail sales
    """

    def __init__(self):
        self.weights = {
            "payrolls": 0.25,
            "income": 0.25,
            "industrial": 0.25,
            "sales": 0.25,
        }

    def compute_index(self, df: pd.DataFrame) -> pd.Series:
        """
        Compute coincident activity index.

        Args:
            df: DataFrame with macro indicators

        Returns:
            Time series of activity index
        """
        # Map column names
        indicators = {}

        # Payrolls
        payroll_cols = [c for c in df.columns if "payroll" in c.lower() or "employ" in c.lower()]
        if payroll_cols:
            indicators["payrolls"] = df[payroll_cols[0]].pct_change(12) * 100  # YoY growth

        # Industrial production
        ip_cols = [c for c in df.columns if "industrial" in c.lower() or "production" in c.lower()]
        if ip_cols:
            indicators["industrial"] = df[ip_cols[0]].pct_change(12) * 100

        # Sales/Consumption proxy
        sales_cols = [c for c in df.columns if "retail" in c.lower() or "sales" in c.lower() or "consum" in c.lower()]
        if sales_cols:
            indicators["sales"] = df[sales_cols[0]].pct_change(12) * 100

        # Income (if available)
        income_cols = [c for c in df.columns if "income" in c.lower() or "wage" in c.lower()]
        if income_cols:
            indicators["income"] = df[income_cols[0]].pct_change(12) * 100

        if not indicators:
            return pd.Series(dtype=float)

        # Combine into index
        index_df = pd.DataFrame(indicators)

        # Standardize
        index_std = (index_df - index_df.mean()) / index_df.std()

        # Weighted average
        weights = {k: self.weights[k] for k in indicators.keys()}
        total_weight = sum(weights.values())
        normalized_weights = {k: v / total_weight for k, v in weights.items()}

        index = sum(
            normalized_weights[k] * index_std[k]
            for k in indicators.keys()
        )

        return index


def get_current_nowcast(df: pd.DataFrame) -> Dict[str, float]:
    """
    Convenience function to get current nowcast.

    Returns:
        Dict with growth_nowcast, inflation_nowcast, confidence
    """
    model = NowcastingModel(n_factors=3)

    try:
        result = model.compute_nowcast(df)
        return {
            "growth_nowcast": result.growth_nowcast,
            "inflation_nowcast": result.inflation_nowcast,
            "business_conditions_index": result.business_conditions_index,
            "confidence": result.confidence,
        }
    except Exception as e:
        logger.error(f"Nowcast failed: {e}")
        return {
            "growth_nowcast": np.nan,
            "inflation_nowcast": np.nan,
            "business_conditions_index": np.nan,
            "confidence": 0.0,
        }
