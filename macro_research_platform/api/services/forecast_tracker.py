"""
Forecast Tracker — Persistent forecast history and realized outcome tracking.

Phase 1 of Model Validation. Tracks:
- Regime predictions (threshold and HMM methods)
- Recession probability forecasts
- Nowcast predictions (GDP growth)
- Expected returns by sector
- Momentum signals
- Portfolio allocations

Usage:
    from api.services.forecast_tracker import forecast_tracker

    # Log a forecast
    forecast_tracker.log_regime(
        regime="Goldilocks",
        confidence=0.75,
        method="threshold",
        growth_score=0.5,
        inflation_score=0.3
    )

    # Log with realized outcome
    forecast_tracker.log_recession_forecast(
        forecast_date="2024-01-01",
        horizon="6M",
        probability=0.65,
        realized_recession=False  # Backfilled later
    )

    # Query accuracy
    metrics = forecast_tracker.get_model_accuracy("regime_threshold")
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from database.db import (
    insert_forecast,
    update_forecast_realized,
    get_forecast_history,
    get_forecasts_without_realized,
    compute_forecast_accuracy,
)

logger = logging.getLogger(__name__)


@dataclass
class ForecastMetrics:
    """Accuracy metrics for a model."""
    model_name: str
    total_forecasts: int
    evaluated: int
    horizon: Optional[str] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    directional_accuracy: Optional[float] = None
    bias: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ForecastTracker:
    """
    Service for logging and tracking forecasts across all models.

    Provides high-level methods for common forecast types and
    handles serialization of model parameters and features.
    """

    # Model name constants for consistency
    REGIME_THRESHOLD = "regime_threshold"
    REGIME_HMM = "regime_hmm"
    RECESSION_ENSEMBLE = "recession_ensemble"
    RECESSION_LOGISTIC = "recession_logistic"
    RECESSION_PROBIT = "recession_probit"
    RECESSION_SAHM = "recession_sahm"
    NOWCAST_GDP = "nowcast_gdp"
    EXPECTED_RETURNS = "expected_returns"
    MOMENTUM_SIGNAL = "momentum_signal"
    PORTFOLIO_ALLOCATION = "portfolio_allocation"

    HORIZON_CURRENT = "current"
    HORIZON_1M = "1M"
    HORIZON_3M = "3M"
    HORIZON_6M = "6M"
    HORIZON_12M = "12M"

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def log_forecast(
        self,
        model_name: str,
        forecast_date: str,
        horizon: Optional[str] = None,
        predicted_value: Optional[float] = None,
        predicted_class: Optional[str] = None,
        confidence_lower: Optional[float] = None,
        confidence_upper: Optional[float] = None,
        model_version: Optional[str] = None,
        model_params: Optional[Dict[str, Any]] = None,
        features_used: Optional[List[str]] = None
    ) -> int:
        """
        Log a generic forecast.

        Args:
            model_name: One of the class constants (e.g., REGIME_THRESHOLD)
            forecast_date: ISO format date string (YYYY-MM-DD)
            horizon: Forecast horizon (e.g., "1M", "6M", "12M", "current")
            predicted_value: Numeric prediction
            predicted_class: Categorical prediction
            confidence_lower: Lower bound of confidence interval
            confidence_upper: Upper bound of confidence interval
            model_version: Model version identifier
            model_params: Dictionary of hyperparameters used
            features_used: List of feature names

        Returns:
            Forecast ID for later updating with realized value
        """
        try:
            forecast_id = insert_forecast(
                model_name=model_name,
                forecast_date=forecast_date,
                horizon=horizon,
                predicted_value=predicted_value,
                predicted_class=predicted_class,
                confidence_lower=confidence_lower,
                confidence_upper=confidence_upper,
                model_version=model_version,
                model_params=model_params,
                features_used=features_used
            )
            self._logger.debug(
                f"[ForecastTracker] Logged {model_name} forecast "
                f"for {forecast_date} (id={forecast_id})"
            )
            return forecast_id
        except Exception as e:
            self._logger.error(f"[ForecastTracker] Failed to log forecast: {e}")
            raise

    def log_regime_forecast(
        self,
        regime: str,
        confidence: float,
        growth_score: float,
        inflation_score: float,
        method: str = "threshold",
        model_params: Optional[Dict] = None
    ) -> int:
        """
        Log a regime classification forecast.

        Args:
            regime: The predicted regime (Goldilocks, Reflation, etc.)
            confidence: Confidence score (0-1)
            growth_score: Growth component score
            inflation_score: Inflation component score
            method: "threshold" or "hmm"
            model_params: Additional model parameters (e.g., threshold value)

        Returns:
            Forecast ID
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        model_name = self.REGIME_THRESHOLD if method == "threshold" else self.REGIME_HMM

        params = model_params or {}
        params.update({
            "growth_score": growth_score,
            "inflation_score": inflation_score,
        })

        return self.log_forecast(
            model_name=model_name,
            forecast_date=today,
            horizon=self.HORIZON_CURRENT,
            predicted_class=regime,
            predicted_value=confidence,
            model_params=params,
            features_used=["growth", "inflation"]
        )

    def log_recession_forecast(
        self,
        forecast_date: str,
        horizon: str,
        probability: float,
        components: Optional[Dict[str, float]] = None,
        model_params: Optional[Dict] = None
    ) -> int:
        """
        Log a recession probability forecast.

        Args:
            forecast_date: Date being forecasted
            horizon: "6M" or "12M"
            probability: Recession probability (0-1)
            components: Dict with keys like 'logistic', 'probit', 'sahm'
            model_params: Model weights and thresholds

        Returns:
            Forecast ID
        """
        features = ["yield_curve", "credit_spreads", "unemployment"]
        if components:
            features.extend(components.keys())

        params = model_params or {}
        if components:
            params["component_probabilities"] = components

        return self.log_forecast(
            model_name=self.RECESSION_ENSEMBLE,
            forecast_date=forecast_date,
            horizon=horizon,
            predicted_value=probability,
            confidence_lower=max(0, probability - 0.15),
            confidence_upper=min(1, probability + 0.15),
            model_params=params,
            features_used=features
        )

    def log_nowcast(
        self,
        forecast_date: str,
        gdp_growth: float,
        components: Dict[str, float],
        confidence_lower: Optional[float] = None,
        confidence_upper: Optional[float] = None,
        model_params: Optional[Dict] = None
    ) -> int:
        """
        Log a GDP nowcast.

        Args:
            forecast_date: Date being forecasted
            gdp_growth: Predicted annualized GDP growth rate
            components: Dict with keys like 'indpro', 'payems', 'rsxfs', 'houst'
            confidence_lower: Lower bound of confidence interval
            confidence_upper: Upper bound of confidence interval
            model_params: Model weights and scaling factors

        Returns:
            Forecast ID
        """
        params = model_params or {}
        params["component_weights"] = components

        return self.log_forecast(
            model_name=self.NOWCAST_GDP,
            forecast_date=forecast_date,
            horizon=self.HORIZON_CURRENT,
            predicted_value=gdp_growth,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            model_params=params,
            features_used=list(components.keys())
        )

    def log_expected_returns(
        self,
        forecast_date: str,
        horizon: str,
        sector: str,
        expected_return: float,
        regime: str,
        earnings_yield: float,
        regime_premium: float,
        confidence_lower: Optional[float] = None,
        confidence_upper: Optional[float] = None
    ) -> int:
        """
        Log an expected return forecast for a sector/asset.

        Args:
            forecast_date: Forecast date
            horizon: "1M", "3M", "6M", "12M"
            sector: Sector or asset class name
            expected_return: Predicted return (annualized)
            regime: Current regime classification
            earnings_yield: Earnings yield component
            regime_premium: Regime premium component
            confidence_lower: Lower CI bound
            confidence_upper: Upper CI bound

        Returns:
            Forecast ID
        """
        model_name = f"{self.EXPECTED_RETURNS}_{sector.lower()}"

        return self.log_forecast(
            model_name=model_name,
            forecast_date=forecast_date,
            horizon=horizon,
            predicted_value=expected_return,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            model_params={
                "regime": regime,
                "earnings_yield": earnings_yield,
                "regime_premium": regime_premium,
            },
            features_used=["earnings_yield", "regime"]
        )

    def log_momentum_signal(
        self,
        forecast_date: str,
        asset: str,
        momentum_score: float,
        signal: str,  # "BUY", "SELL", "NEUTRAL"
        time_series_component: float,
        cross_sectional_component: float,
        vix_level: Optional[float] = None
    ) -> int:
        """
        Log a momentum signal.

        Args:
            forecast_date: Signal date
            asset: Asset symbol or class
            momentum_score: Composite momentum score
            signal: Trading signal classification
            time_series_component: Time-series momentum component
            cross_sectional_component: Cross-sectional momentum component
            vix_level: VIX level at time of signal

        Returns:
            Forecast ID
        """
        model_name = f"{self.MOMENTUM_SIGNAL}_{asset.lower()}"

        params = {
            "time_series_weight": 0.5,
            "cross_sectional_weight": 0.5,
            "time_series_component": time_series_component,
            "cross_sectional_component": cross_sectional_component,
        }
        if vix_level:
            params["vix_level"] = vix_level
            params["crash_suppression_active"] = vix_level > 30

        return self.log_forecast(
            model_name=model_name,
            forecast_date=forecast_date,
            horizon=self.HORIZON_1M,
            predicted_value=momentum_score,
            predicted_class=signal,
            model_params=params,
            features_used=["returns_12m", "returns_1m", "volatility"]
        )

    def log_portfolio_allocation(
        self,
        forecast_date: str,
        weights: Dict[str, float],
        risk_contributions: Optional[Dict[str, float]] = None,
        target_volatility: Optional[float] = None,
        actual_volatility: Optional[float] = None,
        diversification_ratio: Optional[float] = None,
        regime: Optional[str] = None
    ) -> int:
        """
        Log a portfolio allocation decision.

        Args:
            forecast_date: Allocation date
            weights: Asset class weights
            risk_contributions: Risk contribution by asset
            target_volatility: Target volatility level
            actual_volatility: Estimated portfolio volatility
            diversification_ratio: Diversification ratio
            regime: Current regime at time of allocation

        Returns:
            Forecast ID
        """
        params = {
            "weights": weights,
            "method": "risk_parity",
        }
        if risk_contributions:
            params["risk_contributions"] = risk_contributions
        if target_volatility:
            params["target_volatility"] = target_volatility
        if actual_volatility:
            params["actual_volatility"] = actual_volatility
        if diversification_ratio:
            params["diversification_ratio"] = diversification_ratio
        if regime:
            params["regime"] = regime

        return self.log_forecast(
            model_name=self.PORTFOLIO_ALLOCATION,
            forecast_date=forecast_date,
            horizon=self.HORIZON_1M,
            predicted_class="rebalance",
            model_params=params,
            features_used=list(weights.keys())
        )

    def update_realized(
        self,
        forecast_id: int,
        realized_value: Optional[float] = None,
        realized_class: Optional[str] = None
    ) -> bool:
        """
        Update a forecast with its realized outcome.

        Automatically computes error metrics (MAE, RMSE, directional accuracy).

        Args:
            forecast_id: The forecast ID from log_forecast
            realized_value: The actual realized value
            realized_class: The actual realized class

        Returns:
            True if update successful
        """
        try:
            result = update_forecast_realized(
                forecast_id=forecast_id,
                realized_value=realized_value,
                realized_class=realized_class
            )
            if result:
                self._logger.debug(
                    f"[ForecastTracker] Updated forecast {forecast_id} "
                    f"with realized value={realized_value}, class={realized_class}"
                )
            return result
        except Exception as e:
            self._logger.error(f"[ForecastTracker] Failed to update realized: {e}")
            return False

    def backfill_regime_realized(
        self,
        forecast_date: str,
        realized_regime: str
    ) -> int:
        """
        Backfill realized regime for all forecasts on a given date.

        This is used when actual regime data becomes available (computed ex-post).

        Args:
            forecast_date: The date forecasts were made for
            realized_regime: The actual regime that occurred

        Returns:
            Number of forecasts updated
        """
        from database.db import get_db

        updated = 0
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, predicted_class FROM forecast_history
                WHERE forecast_date = ?
                AND model_name IN (?, ?)
                AND realized_class IS NULL
            """, (forecast_date, self.REGIME_THRESHOLD, self.REGIME_HMM))

            rows = cursor.fetchall()
            for row in rows:
                forecast_id = row['id']
                predicted = row['predicted_class']
                directional_hit = 1 if predicted == realized_regime else 0

                cursor.execute("""
                    UPDATE forecast_history
                    SET realized_class = ?,
                        realized_timestamp = ?,
                        directional_hit = ?
                    WHERE id = ?
                """, (
                    realized_regime,
                    datetime.utcnow().isoformat(),
                    directional_hit,
                    forecast_id
                ))
                updated += 1

            conn.commit()

        if updated > 0:
            self._logger.info(
                f"[ForecastTracker] Backfilled {updated} regime forecasts for {forecast_date}"
            )
        return updated

    def get_history(
        self,
        model_name: Optional[str] = None,
        horizon: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get forecast history with optional filtering.

        Args:
            model_name: Filter by model
            horizon: Filter by horizon
            limit: Maximum number of records

        Returns:
            List of forecast records
        """
        return get_forecast_history(model_name, horizon, limit)

    def get_unrealized(
        self,
        model_name: Optional[str] = None,
        before_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get forecasts awaiting realized values.

        Useful for batch backfilling once data becomes available.

        Args:
            model_name: Filter by model
            before_date: Only forecasts before this date

        Returns:
            List of unrealized forecasts
        """
        return get_forecasts_without_realized(model_name, before_date)

    def get_model_accuracy(
        self,
        model_name: str,
        horizon: Optional[str] = None
    ) -> ForecastMetrics:
        """
        Get accuracy metrics for a model.

        Args:
            model_name: The model to evaluate
            horizon: Optional horizon filter

        Returns:
            ForecastMetrics with MAE, RMSE, directional accuracy, etc.
        """
        result = compute_forecast_accuracy(model_name, horizon)
        return ForecastMetrics(
            model_name=result['model_name'],
            horizon=result['horizon'],
            total_forecasts=result['total_forecasts'],
            evaluated=result['evaluated'],
            mae=result['mae'],
            rmse=result['rmse'],
            directional_accuracy=result['directional_accuracy'],
            bias=result['bias']
        )

    def get_accuracy_summary(self) -> Dict[str, Any]:
        """
        Get accuracy summary for all tracked models.

        Returns:
            Dictionary mapping model names to their accuracy metrics
        """
        from database.db import get_db

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT model_name FROM forecast_history
            """)
            models = [row['model_name'] for row in cursor.fetchall()]

        summary = {}
        for model in models:
            summary[model] = self.get_model_accuracy(model).to_dict()

        return summary

    def get_regime_comparison(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare threshold vs HMM regime classification accuracy.

        Returns:
            Dictionary with agreement rate and individual accuracies
        """
        from database.db import get_db

        with get_db() as conn:
            cursor = conn.cursor()

            # Build query
            query = """
                SELECT
                    model_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN directional_hit = 1 THEN 1 ELSE 0 END) as correct
                FROM forecast_history
                WHERE model_name IN (?, ?)
                AND realized_class IS NOT NULL
            """
            params = [self.REGIME_THRESHOLD, self.REGIME_HMM]

            if start_date:
                query += " AND forecast_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND forecast_date <= ?"
                params.append(end_date)

            query += " GROUP BY model_name"

            cursor.execute(query, params)

            results = {}
            for row in cursor.fetchall():
                total = row['total']
                correct = row['correct'] or 0
                results[row['model_name']] = {
                    'total': total,
                    'correct': correct,
                    'accuracy': round(correct / total, 4) if total > 0 else 0
                }

            # Calculate agreement rate
            cursor.execute("""
                SELECT
                    t.forecast_date,
                    t.predicted_class as threshold_regime,
                    h.predicted_class as hmm_regime
                FROM forecast_history t
                JOIN forecast_history h ON t.forecast_date = h.forecast_date
                WHERE t.model_name = ? AND h.model_name = ?
            """, (self.REGIME_THRESHOLD, self.REGIME_HMM))

            agreements = 0
            total_pairs = 0
            for row in cursor.fetchall():
                total_pairs += 1
                if row['threshold_regime'] == row['hmm_regime']:
                    agreements += 1

            return {
                'threshold_accuracy': results.get(self.REGIME_THRESHOLD, {}),
                'hmm_accuracy': results.get(self.REGIME_HMM, {}),
                'agreement_rate': round(agreements / total_pairs, 4) if total_pairs > 0 else 0,
                'agreement_count': agreements,
                'total_comparisons': total_pairs
            }


# Global instance
forecast_tracker = ForecastTracker()
