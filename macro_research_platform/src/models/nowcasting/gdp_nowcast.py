"""
GDP Nowcasting Model - Dynamic Factor Model (DFM)

Implements a simplified DFM using PCA to extract a latent growth factor
from high-frequency monthly indicators, aligned to quarterly GDP growth.

Academic basis:
- Mariano & Murasawa (2010): "A coincident recession index... with mixed-frequency data"
- Giannone et al. (2008): "Nowcasting GDP with real-time data"

Methodology:
1. Standardise input series (z-score)
2. Extract first principal component (PC1) = latent growth factor
3. Scale PC1 to approximate GDP growth units
4. Validate against actual GDPC1 releases

Inputs:
- INDPRO: Industrial Production
- PAYEMS: Nonfarm Payrolls
- RSXFS: Retail Sales ex-Food Services
- HOUST: Housing Starts
- ICSA: Initial Jobless Claims (weekly, converted to monthly average)

Output:
- Nowcasted annualised GDP growth rate
- Confidence interval based on historical RMSE
- Component loadings showing each indicator's contribution
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


@dataclass
class NowcastResult:
    """Result from GDP nowcast computation."""
    nowcast_gdp_growth: float      # Annualised QoQ SAAR%
    confidence_interval_low: float
    confidence_interval_high: float
    last_updated: str
    input_series: Dict[str, float]  # Current z-scores of inputs
    component_loadings: Dict[str, float]  # PCA loadings
    mae_vs_gdpc1: float            # Mean absolute error vs actual
    latent_factor: float            # The extracted PC1 value
    description: str


class GDPNowcastModel:
    """
    Dynamic Factor Model for GDP nowcasting using PCA.
    """

    # Target series for validation
    GDP_SERIES = "GDPC1"

    # Input series from FRED
    INPUT_SERIES = {
        "INDPRO": "industrial_production",
        "PAYEMS": "nonfarm_payrolls",
        "RSXFS": "retail_sales",
        "HOUST": "housing_starts",
        "ICSA": "initial_claims",
    }

    # Historical RMSE for confidence intervals (typical DFM accuracy)
    HISTORICAL_RMSE = 1.2

    def __init__(self, lookback_months: int = 24):
        self.lookback_months = lookback_months
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=1)  # Extract single growth factor

    def _get_series(self, df: pd.DataFrame, series_id: str) -> Optional[pd.Series]:
        """Find series in DataFrame by ID or alias."""
        # Direct match
        if series_id in df.columns:
            return df[series_id].copy()

        # Try aliases
        aliases = self.INPUT_SERIES.get(series_id, [])
        if isinstance(aliases, str):
            aliases = [aliases]

        for alias in [series_id] + list(aliases):
            if alias in df.columns:
                return df[alias].copy()
            # Try common variations
            variations = [
                alias.lower(),
                alias.upper(),
                f"us_{alias.lower()}",
                alias.lower().replace("_", ""),
            ]
            for var in variations:
                if var in df.columns:
                    return df[var].copy()

        return None

    def _transform_to_growth_rate(self, series: pd.Series) -> pd.Series:
        """Convert series to YoY growth rate (approximate for monthly data)."""
        # Use 12-month pct change for monthly series
        if len(series) >= 13:
            growth = series.pct_change(12) * 100
        else:
            # Fallback: use shorter window
            growth = series.pct_change(3) * 400  # Annualise quarterly change
        return growth.dropna()

    def compute(self, df: pd.DataFrame) -> NowcastResult:
        """
        Compute GDP nowcast from available data.

        Args:
            df: DataFrame with macro indicators (FRED series)

        Returns:
            NowcastResult with nowcasted GDP growth
        """
        # Collect available series
        series_data = {}
        current_values = {}

        for fred_code, alias in self.INPUT_SERIES.items():
            series = self._get_series(df, fred_code)
            if series is not None and not series.dropna().empty:
                # Transform to growth rate
                growth = self._transform_to_growth_rate(series)
                if not growth.dropna().empty:
                    series_data[fred_code] = growth
                    current_values[fred_code] = float(growth.iloc[-1])
                    logger.debug(f"Nowcast: using {fred_code}")

        if len(series_data) < 3:
            logger.warning(f"Insufficient data for nowcast: {len(series_data)} series")
            # Return neutral nowcast
            return NowcastResult(
                nowcast_gdp_growth=2.0,  # Neutral assumption
                confidence_interval_low=-1.0,
                confidence_interval_high=5.0,
                last_updated=datetime.now().strftime("%Y-%m-%d"),
                input_series=current_values,
                component_loadings={},
                mae_vs_gdpc1=float('nan'),
                latent_factor=0.0,
                description=f"Nowcast: insufficient data ({len(series_data)} series). Using neutral assumption.",
            )

        # Align series to common dates
        aligned_df = pd.DataFrame(series_data).dropna()

        if len(aligned_df) < 12:
            logger.warning(f"Insufficient aligned observations: {len(aligned_df)}")
            return NowcastResult(
                nowcast_gdp_growth=2.0,
                confidence_interval_low=-1.0,
                confidence_interval_high=5.0,
                last_updated=datetime.now().strftime("%Y-%m-%d"),
                input_series=current_values,
                component_loadings={},
                mae_vs_gdpc1=float('nan'),
                latent_factor=0.0,
                description=f"Nowcast: insufficient aligned data ({len(aligned_df)} obs). Using neutral assumption.",
            )

        # Standardise (z-score)
        standardized = self.scaler.fit_transform(aligned_df)

        # Extract first principal component (latent growth factor)
        pc1 = self.pca.fit_transform(standardized)
        pc1_series = pd.Series(pc1.flatten(), index=aligned_df.index)

        # Scale PC1 to approximate GDP growth
        # Historical calibration: PC1 std ~ 2.5% GDP std
        current_pc1 = float(pc1_series.iloc[-1])
        calibrated_growth = current_pc1 * 2.5  # Scale factor

        # Ensure nowcast is reasonable (typical GDP range: -5% to +8%)
        nowcast_gdp = np.clip(calibrated_growth + 2.0, -5.0, 8.0)

        # Component loadings (correlation with PC1)
        loadings = {}
        for i, col in enumerate(aligned_df.columns):
            loadings[col] = float(self.pca.components_[0][i])

        # Calculate MAE vs actual GDP if available
        mae = None
        gdp_actual = self._get_series(df, self.GDP_SERIES)
        if gdp_actual is not None and not gdp_actual.dropna().empty:
            mae_calc = self._calculate_mae(pc1_series, gdp_actual)
            if not np.isnan(mae_calc):
                mae = mae_calc
                logger.info(f"Nowcast MAE vs GDPC1: {mae:.2f}%")

        # Confidence interval (95%)
        ci_low = nowcast_gdp - 1.96 * self.HISTORICAL_RMSE
        ci_high = nowcast_gdp + 1.96 * self.HISTORICAL_RMSE

        description = (
            f"DFM Nowcast: {nowcast_gdp:.2f}% SAAR | "
            f"PC1 factor: {current_pc1:+.2f} | "
            f"Components: {', '.join(series_data.keys())} | "
            f"MAE: {mae:.2f}%"
        )

        return NowcastResult(
            nowcast_gdp_growth=round(nowcast_gdp, 2),
            confidence_interval_low=round(ci_low, 2),
            confidence_interval_high=round(ci_high, 2),
            last_updated=datetime.now().strftime("%Y-%m-%d"),
            input_series=current_values,
            component_loadings=loadings,
            mae_vs_gdpc1=round(mae, 2) if not np.isnan(mae) else None,
            latent_factor=round(current_pc1, 3),
            description=description,
        )

    def _calculate_mae(self, pc1_series: pd.Series, gdp_actual: pd.Series) -> Optional[float]:
        """Calculate Mean Absolute Error between PC1 and actual GDP growth."""
        try:
            # Convert GDP to monthly frequency (forward fill)
            gdp_monthly = gdp_actual.resample('MS').ffill()

            # Align dates
            common_idx = pc1_series.index.intersection(gdp_monthly.index)
            if len(common_idx) < 4:
                return None

            pc1_aligned = pc1_series.loc[common_idx]
            gdp_aligned = gdp_monthly.loc[common_idx]

            # Scale PC1 to match GDP units (using linear regression)
            from sklearn.linear_model import LinearRegression
            X = pc1_aligned.values.reshape(-1, 1)
            y = gdp_aligned.values
            reg = LinearRegression().fit(X, y)
            pc1_scaled = reg.predict(X)

            # Calculate MAE
            mae = float(np.mean(np.abs(pc1_scaled - y)))
            return mae

        except Exception as e:
            logger.warning(f"Failed to calculate MAE: {e}")
            return None


def get_gdp_nowcast(df: pd.DataFrame) -> NowcastResult:
    """Compute GDP nowcast from DataFrame."""
    model = GDPNowcastModel()
    return model.compute(df)


def get_nowcast_dict(df: pd.DataFrame) -> dict:
    """Get nowcast as simple dict for API response."""
    result = get_gdp_nowcast(df)
    return {
        "nowcast_gdp_growth": result.nowcast_gdp_growth,
        "confidence_interval_low": result.confidence_interval_low,
        "confidence_interval_high": result.confidence_interval_high,
        "last_updated": result.last_updated,
        "input_series": result.input_series,
        "mae_vs_gdpc1": result.mae_vs_gdpc1,
        "description": result.description,
    }
