"""
inflation_nowcast.py — 1-month ahead CPI nowcast using leading indicators.

Financial context:
  CPI is published with a lag (mid-month for prior month). A "nowcast"
  predicts the upcoming release using data that is already available.
  This provides an information advantage: markets move when CPI surprises,
  not when it confirms expectations.

  Leading indicators for CPI:
    1. PPI (Producer Price Index): upstream costs lead consumer prices by 1-3 months
    2. Oil prices: energy costs feed into transportation, heating, and production
    3. Import prices: global goods prices affect domestic inflation
    4. Trailing CPI momentum: recent trend tends to persist short-term

  Method: Simple dynamic factor / bridge equation approach
    - Regress monthly CPI change on lagged predictors
    - Use rolling window to adapt to changing relationships
    - No look-ahead: only uses data available at prediction time

Model specification:
  CPI_t = alpha + beta1*PPI_{t-1} + beta2*Oil_{t-1} + beta3*Import_{t-1} + beta4*CPI_{t-1} + epsilon_t

Accuracy notes:
  - Typical CPI nowcast RMSE: 0.2-0.3 percentage points
  - Model works best for "stable" inflation periods
  - Large shocks (energy crises, supply disruptions) will be missed
  - Nowcast should be combined with economist survey consensus for robustness
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Default model coefficients (approximate, should be recalibrated quarterly)
DEFAULT_COEFFICIENTS = {
    "intercept": 0.1,
    "ppi_lag1": 0.15,       # PPI has ~0.15 pass-through to CPI with 1M lag
    "oil_lag1": 0.02,       # Oil price change coefficient (scaled)
    "import_lag1": 0.10,    # Import prices pass-through
    "cpi_momentum": 0.50,   # AR(1) component: 50% persistence
}

DEFAULT_WINDOW = 60  # 5 years of rolling history for calibration


class InflationNowcastModel:
    """
    1-month ahead CPI nowcast using bridge equations.

    Uses lagged predictors available before CPI release:
      - PPI (t-1): upstream producer prices
      - Oil prices (t-1): Brent/WTI average
      - Import prices (t-1): if available
      - CPI momentum (t-1): previous month change
    """

    def __init__(
        self,
        coefficients: Optional[Dict[str, float]] = None,
        calibration_window: int = DEFAULT_WINDOW,
    ):
        """
        Initialize the nowcast model.

        Args:
            coefficients: Dict of model coefficients. Uses defaults if None.
            calibration_window: Rolling window for auto-calibration (months)
        """
        self.coefficients = coefficients or DEFAULT_COEFFICIENTS.copy()
        self.window = calibration_window
        self._last_calibration: Optional[pd.Timestamp] = None

    def calibrate(
        self,
        cpi_series: pd.Series,
        ppi_series: pd.Series,
        oil_series: Optional[pd.Series] = None,
        import_series: Optional[pd.Series] = None,
    ) -> Dict[str, float]:
        """
        Calibrate model coefficients using historical data.

        Uses OLS on rolling window to capture changing relationships.

        Args:
            cpi_series: Monthly CPI levels or changes
            ppi_series: Monthly PPI levels or changes
            oil_series: Monthly oil price (optional)
            import_series: Monthly import price index (optional)

        Returns:
            Updated coefficients dict
        """
        # Compute changes (MoM) if levels provided
        cpi_change = cpi_series.diff() if cpi_series.mean() > 10 else cpi_series
        ppi_change = ppi_series.diff() if ppi_series.mean() > 10 else ppi_series

        # Build dataset
        data = pd.DataFrame({
            "cpi": cpi_change,
            "ppi_lag1": ppi_change.shift(1),
            "cpi_lag1": cpi_change.shift(1),
        })

        if oil_series is not None:
            oil_change = oil_series.pct_change() * 100 if oil_series.mean() > 20 else oil_series
            data["oil_lag1"] = oil_change.shift(1)

        if import_series is not None:
            import_change = import_series.diff() if import_series.mean() > 10 else import_series
            data["import_lag1"] = import_change.shift(1)

        # Drop NaN
        data = data.dropna()

        if len(data) < self.window:
            logger.warning(f"Insufficient data for calibration: {len(data)} < {self.window}")
            return self.coefficients

        # Use last N observations for calibration
        train = data.tail(self.window)

        # Build feature matrix
        X_cols = ["ppi_lag1", "cpi_lag1"]
        if "oil_lag1" in train.columns:
            X_cols.append("oil_lag1")
        if "import_lag1" in train.columns:
            X_cols.append("import_lag1")

        X = train[X_cols].values
        y = train["cpi"].values

        # Add intercept
        X_with_intercept = np.column_stack([np.ones(len(X)), X])

        # OLS: beta = (X'X)^-1 X'y
        try:
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]

            self.coefficients["intercept"] = beta[0]
            self.coefficients["ppi_lag1"] = beta[1]
            self.coefficients["cpi_momentum"] = beta[2]

            if "oil_lag1" in X_cols:
                self.coefficients["oil_lag1"] = beta[X_cols.index("oil_lag1") + 1]
            if "import_lag1" in X_cols:
                self.coefficients["import_lag1"] = beta[X_cols.index("import_lag1") + 1]

            self._last_calibration = train.index[-1]

            logger.info(f"Model calibrated on {len(train)} obs: {self.coefficients}")

        except np.linalg.LinAlgError:
            logger.warning("Calibration failed, using default coefficients")

        return self.coefficients

    def nowcast(
        self,
        ppi_current: float,
        cpi_current: float,
        oil_current: Optional[float] = None,
        import_current: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Generate 1-month ahead CPI nowcast.

        Args:
            ppi_current: Current PPI change (t-1)
            cpi_current: Current CPI change (t-1, for momentum)
            oil_current: Current oil price change (t-1), optional
            import_current: Current import price change (t-1), optional

        Returns:
            Tuple of (nowcast_value, confidence_interval_width)
        """
        c = self.coefficients

        # Base prediction
        pred = c["intercept"]
        pred += c.get("ppi_lag1", 0) * ppi_current
        pred += c.get("cpi_momentum", 0) * cpi_current

        if oil_current is not None:
            pred += c.get("oil_lag1", 0) * oil_current

        if import_current is not None:
            pred += c.get("import_lag1", 0) * import_current

        # Simple confidence interval (historical residual std ~0.25)
        confidence_width = 0.25  # ±0.25pp

        return pred, confidence_width

    def nowcast_series(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Generate historical nowcasts for validation.

        Args:
            df: DataFrame with columns: cpi_yoy, ppi_yoy, oil_price (optional)

        Returns:
            DataFrame with nowcast values and actuals for comparison
        """
        # Extract series
        cpi = df.get("cpi_yoy")
        ppi = df.get("ppi_yoy")
        oil = df.get("oil_price")

        if cpi is None or ppi is None:
            logger.warning("Missing CPI or PPI data for nowcast")
            return pd.DataFrame()

        # Compute changes
        cpi_change = cpi.diff()
        ppi_change = ppi.diff()
        oil_change = oil.pct_change() * 100 if oil is not None else None

        results = []
        for i in range(len(df)):
            if i < 2:  # Need at least 2 observations
                results.append({
                    "date": df.index[i],
                    "nowcast": np.nan,
                    "actual": cpi_change.iloc[i],
                    "error": np.nan,
                })
                continue

            # Use only data available at time t (strict no-lookahead)
            ppi_lag = ppi_change.iloc[i-1]
            cpi_lag = cpi_change.iloc[i-1]
            oil_lag = oil_change.iloc[i-1] if oil_change is not None else None

            pred, _ = self.nowcast(ppi_lag, cpi_lag, oil_lag)
            actual = cpi_change.iloc[i]

            results.append({
                "date": df.index[i],
                "nowcast": pred,
                "actual": actual,
                "error": actual - pred,
            })

        return pd.DataFrame(results).set_index("date")


# =============================================================================
# Convenience Functions
# =============================================================================

def get_inflation_nowcast(df: pd.DataFrame) -> Dict[str, float]:
    """
    Get current inflation nowcast from a DataFrame.

    Args:
        df: DataFrame with required indicators

    Returns:
        Dict with nowcast value, confidence interval, and components
    """
    model = InflationNowcastModel()

    # Auto-calibrate if we have enough history
    if len(df) >= 24:
        model.calibrate(
            cpi_series=df["cpi_yoy"],
            ppi_series=df["ppi_yoy"],
            oil_series=df.get("oil_price"),
        )

    # Get latest values
    ppi_change = df["ppi_yoy"].diff().iloc[-1]
    cpi_change = df["cpi_yoy"].diff().iloc[-1]
    oil_change = df["oil_price"].pct_change().iloc[-1] * 100 if "oil_price" in df else None

    pred, conf = model.nowcast(ppi_change, cpi_change, oil_change)

    current_cpi = df["cpi_yoy"].iloc[-1]
    nowcast_level = current_cpi + pred  # Add predicted change to current level

    return {
        "nowcast_value": round(pred, 2),
        "nowcast_level": round(nowcast_level, 2),
        "current_cpi": round(current_cpi, 2),
        "confidence_lower": round(pred - conf, 2),
        "confidence_upper": round(pred + conf, 2),
        "components": {
            "ppi_contribution": round(model.coefficients.get("ppi_lag1", 0) * ppi_change, 2),
            "momentum_contribution": round(model.coefficients.get("cpi_momentum", 0) * cpi_change, 2),
            "oil_contribution": round(
                model.coefficients.get("oil_lag1", 0) * (oil_change or 0), 2
            ),
        }
    }


def validate_nowcast(df: pd.DataFrame) -> Dict[str, float]:
    """
    Validate nowcast accuracy on historical data.

    Args:
        df: DataFrame with historical data

    Returns:
        Dict with accuracy metrics
    """
    model = InflationNowcastModel()

    historical = model.nowcast_series(df)

    if historical.empty:
        return {"error": "Insufficient data for validation"}

    # Drop NaN
    valid = historical.dropna()

    if len(valid) < 10:
        return {"error": "Insufficient valid observations"}

    # Compute metrics
    mae = valid["error"].abs().mean()
    rmse = np.sqrt((valid["error"] ** 2).mean())
    bias = valid["error"].mean()

    return {
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "bias": round(bias, 3),
        "observations": len(valid),
    }
