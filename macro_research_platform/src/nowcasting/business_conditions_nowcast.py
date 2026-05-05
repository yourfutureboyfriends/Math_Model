"""
Business Conditions Nowcast

Real-time assessment of current business cycle conditions.

Integrates multiple data sources to estimate:
- Current GDP growth (nowcast)
- Recession probability
- Growth impulse direction
- Leading indicator composite

Uses bridge equations, factor models, and mixed-frequency approaches.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    Ridge = None
    StandardScaler = None

logger = logging.getLogger(__name__)


@dataclass
class NowcastResult:
    """Result of nowcast calculation."""
    target_variable: str
    nowcast_value: float
    nowcast_date: datetime
    forecast_std: float
    model_contributions: Dict[str, float]
    data_used: List[str]
    data_missing: List[str]
    last_update: datetime


@dataclass
class RecessionIndicator:
    """Recession probability indicator."""
    probability: float
    timestamp: datetime
    factors: Dict[str, float]
    lead_time_months: Optional[int]


class BusinessConditionsNowcast:
    """
    Nowcast business conditions using mixed-frequency data.

    Combines monthly and quarterly data to estimate current
    economic conditions in real-time.
    """

    # Standard indicators for nowcasting
    MONTHLY_INDICATORS = {
        # Labor market
        "PAYEMS": {"weight": 0.20, "freq": "M", "category": "labor"},
        "AWHMAN": {"weight": 0.10, "freq": "M", "category": "labor"},
        "ICSA": {"weight": 0.10, "freq": "W", "category": "labor"},

        # Production
        "INDPRO": {"weight": 0.15, "freq": "M", "category": "production"},
        "CAPUTLB50006SQ": {"weight": 0.05, "freq": "M", "category": "production"},

        # Consumption
        "PCEC1": {"weight": 0.15, "freq": "M", "category": "consumption"},
        "RETSAL": {"weight": 0.10, "freq": "M", "category": "consumption"},

        # Business activity
        "NAPM": {"weight": 0.10, "freq": "M", "category": "activity"},
        "AMTMNO": {"weight": 0.05, "freq": "M", "category": "activity"},
    }

    # Recession indicator thresholds
    RECESSION_THRESHOLDS = {
        "sahm_rule": 0.50,  # 3mo avg unemployment - 12mo min > 0.5
        "yield_curve": 0,  # 10Y-2Y spread < 0
        "leading_index": -1.0,  # Index decline
    }

    def __init__(self):
        self.models: Dict[str, any] = {}
        self.scalers: Dict[str, StandardScaler] = {}
        self.indicator_weights = self.MONTHLY_INDICATORS.copy()
        self.nowcast_history: List[NowcastResult] = []

    def load_data(
        self,
        data: Dict[str, pd.Series],
        as_of_date: Optional[datetime] = None,
    ) -> Dict[str, pd.Series]:
        """
        Load data as of a specific date (point-in-time).

        Args:
            data: Dict of series_id to Series
            as_of_date: Cutoff date for point-in-time data

        Returns:
            Filtered data available as of date
        """
        if as_of_date is None:
            return data

        filtered = {}
        for series_id, series in data.items():
            # Filter to data available as of date
            # Account for release lags (simplified - would use actual release dates)
            indicator_info = self.indicator_weights.get(series_id, {})
            freq = indicator_info.get("freq", "M")

            # Typical release lags
            lag_days = {"M": 30, "W": 7, "Q": 60}.get(freq, 30)

            available_date = as_of_date - pd.Timedelta(days=lag_days)
            filtered[series_id] = series[series.index <= available_date]

        return filtered

    def calculate_bridge_equation(
        self,
        indicators: Dict[str, pd.Series],
        target: str = "GDPC1",
    ) -> Dict:
        """
        Calculate nowcast using bridge equation approach.

        Bridge equations relate monthly indicators to quarterly GDP.

        Args:
            indicators: Dict of monthly indicator series
            target: Target variable to nowcast

        Returns:
            Nowcast result with contributions
        """
        # Align to quarterly frequency
        quarterly_data = {}

        for name, series in indicators.items():
            if len(series) < 3:
                continue

            # Convert monthly to quarterly (last month of quarter)
            quarterly = series.resample("Q").last()
            quarterly_data[name] = quarterly

        if len(quarterly_data) < 3:
            return {
                "nowcast": None,
                "error": "Insufficient data for bridge equation",
            }

        # Create DataFrame
        df = pd.DataFrame(quarterly_data)

        # Calculate quarterly changes
        for col in df.columns:
            df[f"{col}_chg"] = df[col].pct_change(4) * 100  # YoY change

        # Simple weighted average of indicator changes
        weights = {
            name: info["weight"]
            for name, info in self.indicator_weights.items()
            if name in df.columns
        }

        total_weight = sum(weights.values())
        if total_weight == 0:
            return {"nowcast": None, "error": "No valid indicators"}

        # Weighted average
        weighted_sum = 0
        contributions = {}

        for name, weight in weights.items():
            chg_col = f"{name}_chg"
            if chg_col in df.columns:
                value = df[chg_col].iloc[-1]
                if pd.notna(value):
                    normalized_weight = weight / total_weight
                    weighted_sum += value * normalized_weight
                    contributions[name] = value * normalized_weight

        # Historical average GDP growth (simplified adjustment)
        historical_gdp_avg = 2.5
        nowcast = historical_gdp_avg + weighted_sum * 0.5

        return {
            "nowcast": round(nowcast, 2),
            "contributions": {k: round(v, 2) for k, v in contributions.items()},
            "method": "bridge_equation",
        }

    def calculate_factor_nowcast(
        self,
        data: pd.DataFrame,
        n_factors: int = 3,
    ) -> Dict:
        """
        Calculate nowcast using dynamic factor model.

        Extracts common factors from multiple series.

        Args:
            data: DataFrame with indicator columns
            n_factors: Number of factors to extract

        Returns:
            Nowcast result with factor loadings
        """
        if not HAS_SKLEARN:
            return {
                "nowcast": None,
                "error": "sklearn not installed - factor model unavailable",
            }

        if len(data) < 24 or len(data.columns) < 5:
            return {
                "nowcast": None,
                "error": "Insufficient data for factor model",
            }

        from sklearn.decomposition import PCA

        # Standardize
        scaler = StandardScaler()
        standardized = scaler.fit_transform(data.dropna())

        # Simple PCA approximation (using correlations)
        # In practice would use proper dynamic factor model
        pca = PCA(n_components=n_factors)
        factors = pca.fit_transform(standardized)

        # First factor is typically the "activity" factor
        activity_factor = factors[:, 0]

        # Map factor to GDP growth estimate (simplified)
        # Historical relationship: 1 std dev in factor ≈ 1.5% GDP growth
        current_factor = activity_factor[-1]
        nowcast = 2.5 + current_factor * 1.5

        # Factor interpretation
        factor_loadings = pd.DataFrame(
            pca.components_.T,
            columns=[f"Factor_{i+1}" for i in range(n_factors)],
            index=data.columns,
        )

        return {
            "nowcast": round(nowcast, 2),
            "activity_factor": round(current_factor, 2),
            "explained_variance": round(pca.explained_variance_ratio_[0], 2),
            "top_contributors": factor_loadings["Factor_1"]
            .abs()
            .nlargest(5)
            .to_dict(),
            "method": "factor_model",
        }

    def calculate_recession_probability(
        self,
        data: Dict[str, pd.Series],
        model: str = "composite",
    ) -> RecessionIndicator:
        """
        Calculate real-time recession probability.

        Args:
            data: Dict of indicator series
            model: Which model to use

        Returns:
            Recession probability indicator
        """
        factors = {}

        # Sahm Rule
        if "UNRATE" in data:
            unrate = data["UNRATE"]
            if len(unrate) >= 13:
                current_3m = unrate.iloc[-3:].mean()
                min_12m = unrate.iloc[-12:].min()
                sahm = current_3m - min_12m
                factors["sahm_rule"] = sahm

        # Yield curve
        if "T10Y2Y" in data:
            spread = data["T10Y2Y"].iloc[-1]
            factors["yield_curve"] = spread

        # Credit spreads
        if "BAA10Y" in data:
            spread = data["BAA10Y"].iloc[-1]
            factors["credit_spreads"] = spread

        # Calculate composite probability
        prob_inputs = []

        if "sahm_rule" in factors:
            # Sahm rule: >0.5 indicates recession
            sahm_prob = min(1.0, max(0.0, factors["sahm_rule"] / 0.5))
            prob_inputs.append(sahm_prob * 0.4)  # 40% weight

        if "yield_curve" in factors:
            # Inverted yield curve indicator
            yc_prob = 0.3 if factors["yield_curve"] < 0 else 0.0
            prob_inputs.append(yc_prob * 0.3)  # 30% weight

        if "credit_spreads" in factors:
            # High credit spreads
            cs_prob = min(1.0, max(0.0, (factors["credit_spreads"] - 200) / 300))
            prob_inputs.append(cs_prob * 0.3)  # 30% weight

        if prob_inputs:
            probability = sum(prob_inputs)
        else:
            probability = 0.15  # Baseline

        return RecessionIndicator(
            probability=round(probability, 2),
            timestamp=datetime.now(),
            factors=factors,
            lead_time_months=None,
        )

    def generate_nowcast_report(
        self,
        data: Dict[str, pd.Series],
        as_of_date: Optional[datetime] = None,
    ) -> Dict:
        """
        Generate comprehensive nowcast report.

        Args:
            data: Dict of available indicator series
            as_of_date: Point-in-time date

        Returns:
            Complete nowcast report
        """
        # Load data as of date
        pit_data = self.load_data(data, as_of_date)

        # Calculate multiple nowcasts
        bridge_result = self.calculate_bridge_equation(pit_data)

        # Factor model (if we have panel data)
        try:
            df = pd.DataFrame({k: v for k, v in pit_data.items()})
            factor_result = self.calculate_factor_nowcast(df)
        except Exception:
            factor_result = {"nowcast": None, "error": "Factor model failed"}

        # Recession probability
        recession = self.calculate_recession_probability(pit_data)

        # Combine nowcasts (simple average if both available)
        nowcasts = []
        if bridge_result.get("nowcast") is not None:
            nowcasts.append(bridge_result["nowcast"])
        if factor_result.get("nowcast") is not None:
            nowcasts.append(factor_result["nowcast"])

        if nowcasts:
            composite = np.mean(nowcasts)
        else:
            composite = None

        # Data availability
        available = [k for k, v in pit_data.items() if len(v) > 0]
        missing = [k for k in self.indicator_weights if k not in available]

        return {
            "as_of_date": as_of_date or datetime.now(),
            "nowcast": {
                "composite_gdp_growth": round(composite, 2) if composite else None,
                "bridge_equation": bridge_result,
                "factor_model": factor_result,
            },
            "recession_probability": {
                "current": recession.probability,
                "factors": recession.factors,
            },
            "data_status": {
                "available_indicators": available,
                "missing_indicators": missing,
                "data_completeness": len(available) / len(self.indicator_weights),
            },
            "confidence": self._calculate_confidence(len(available), len(missing)),
        }

    def _calculate_confidence(
        self,
        n_available: int,
        n_missing: int,
    ) -> str:
        """Calculate confidence level based on data availability."""
        total = n_available + n_missing
        if total == 0:
            return "low"

        ratio = n_available / total

        if ratio >= 0.8:
            return "high"
        elif ratio >= 0.5:
            return "medium"
        else:
            return "low"


def calculate_growth_impulse(
    data: pd.DataFrame,
    window: int = 3,
) -> pd.Series:
    """
    Calculate growth impulse indicator.

    Measures whether growth momentum is improving or deteriorating.

    Args:
        data: DataFrame of monthly indicators
        window: Rolling window for momentum

    Returns:
        Growth impulse series
    """
    # Calculate momentum for each series
    momentum = data.diff(window)

    # Count improving vs deteriorating
    impulse = []
    for i in range(len(momentum)):
        row = momentum.iloc[i]
        improving = (row > 0).sum()
        deteriorating = (row < 0).sum()
        total = improving + deteriorating

        if total > 0:
            score = (improving - deteriorating) / total
        else:
            score = 0

        impulse.append(score)

    return pd.Series(impulse, index=data.index)


def create_leading_index(
    data: pd.DataFrame,
    target: pd.Series,
    max_lag: int = 6,
) -> Tuple[pd.Series, Dict]:
    """
    Create composite leading index using Granger causality.

    Args:
        data: DataFrame of candidate leading indicators
        target: Target series to predict
        max_lag: Maximum lag to test

    Returns:
        Leading index and metadata
    """
    from scipy.stats import pearsonr

    correlations = {}
    best_lags = {}

    for col in data.columns:
        if col not in data:
            continue

        series = data[col]
        best_corr = 0
        best_lag = 0

        # Test different lags
        for lag in range(1, max_lag + 1):
            if len(series) <= lag:
                continue

            lagged = series.shift(lag)
            aligned_target = target[target.index.isin(lagged.index)]
            aligned_lagged = lagged[lagged.index.isin(target.index)]

            if len(aligned_target) < 12:
                continue

            corr, _ = pearsonr(aligned_lagged.dropna(), aligned_target.dropna())
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag

        correlations[col] = best_corr
        best_lags[col] = best_lag

    # Select top predictors (positive correlation with leads)
    top_predictors = sorted(
        correlations.items(),
        key=lambda x: abs(x[1]),
        reverse=True,
    )[:5]

    # Create weighted leading index
    weights = {name: abs(corr) for name, corr in top_predictors}
    total_weight = sum(weights.values())

    if total_weight == 0:
        return pd.Series(), {}

    # Normalize weights
    weights = {k: v / total_weight for k, v in weights.items()}

    # Calculate index
    index = pd.Series(0.0, index=data.index)
    for name, weight in weights.items():
        lag = best_lags[name]
        index += data[name].shift(-lag) * weight * np.sign(correlations[name])

    return index.dropna(), {
        "predictors": top_predictors,
        "optimal_lags": best_lags,
        "weights": weights,
    }
