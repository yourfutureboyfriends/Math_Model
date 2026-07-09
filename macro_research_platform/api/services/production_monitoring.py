"""
Production Monitoring Service — Phase 10: Real-time monitoring and drift detection.

Monitors model performance in production:
1. Real-time Accuracy Tracking — Track prediction errors as they occur
2. Drift Detection — Detect input and concept drift
3. Alert Thresholds — Configurable thresholds for anomalies
4. Dashboard Integration — Metrics export for monitoring dashboards

Usage:
    from api.services.production_monitoring import production_monitor

    # Log production prediction
    production_monitor.log_prediction(
        model="regime_threshold",
        prediction="Goldilocks",
        confidence=0.75,
        inputs={"growth": 0.5, "inflation": 0.3}
    )

    # Check for drift
    drift_report = production_monitor.detect_drift()

    # Get alert status
    alerts = production_monitor.check_alert_thresholds()
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
import statistics

import numpy as np
import pandas as pd

from database.db import get_db

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftReport:
    """Drift detection report."""
    variable: str
    drift_detected: bool
    drift_score: float
    baseline_mean: float
    current_mean: float
    p_value: Optional[float] = None
    severity: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Alert:
    """Production alert."""
    alert_type: str
    severity: str
    message: str
    timestamp: str
    metric_value: Optional[float] = None
    threshold: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelHealth:
    """Model health metrics."""
    model_name: str
    status: str  # "healthy", "degraded", "failing"
    last_prediction: Optional[str]
    predictions_last_hour: int
    avg_latency_ms: float
    error_rate: float
    drift_status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProductionMonitor:
    """
    Production monitoring service for real-time model validation.

    Monitors:
    - Real-time prediction accuracy
    - Input drift detection
    - Concept drift detection
    - Latency and error rates
    - Alert generation
    """

    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "error_rate": 0.10,  # 10% error rate triggers warning
        "latency_ms": 1000,  # 1 second latency threshold
        "drift_score": 0.50,  # Drift detection threshold
        "accuracy_drop": 0.15,  # 15% accuracy drop triggers alert
        "prediction_volume": 10,  # Min predictions per hour
    }

    # Models to monitor
    MONITORED_MODELS = [
        "regime_threshold",
        "regime_hmm",
        "recession_ensemble",
        "expected_returns",
        "momentum_factor",
    ]

    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        self._logger = logging.getLogger(__name__)
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS.copy()

    def log_prediction(
        self,
        model: str,
        prediction: Any,
        confidence: float,
        inputs: Dict[str, float],
        latency_ms: float,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log a production prediction.

        Args:
            model: Model name
            prediction: Model output
            confidence: Confidence score (0-1)
            inputs: Model inputs/features
            latency_ms: Prediction latency in milliseconds
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure production_predictions table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS production_predictions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        model TEXT NOT NULL,
                        prediction TEXT,
                        confidence REAL,
                        inputs TEXT,
                        latency_ms REAL,
                        realized_outcome TEXT,
                        prediction_error REAL,
                        metadata TEXT
                    )
                """)

                cursor.execute("""
                    INSERT INTO production_predictions (
                        timestamp, model, prediction, confidence,
                        inputs, latency_ms, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.utcnow().isoformat(),
                    model,
                    json.dumps(prediction) if isinstance(prediction, (dict, list)) else str(prediction),
                    confidence,
                    json.dumps(inputs),
                    latency_ms,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(
                    f"[ProductionMonitor] Logged prediction for {model} (id={log_id})"
                )
                return log_id

        except Exception as e:
            self._logger.error(f"[ProductionMonitor] Failed to log prediction: {e}")
            raise

    def update_realized(
        self,
        prediction_id: int,
        realized_outcome: Any,
        prediction_error: Optional[float] = None
    ) -> bool:
        """
        Update realized outcome for a prediction.

        Args:
            prediction_id: Prediction log ID
            realized_outcome: Actual realized value
            prediction_error: Computed error (optional)

        Returns:
            True if update successful
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE production_predictions
                    SET realized_outcome = ?,
                        prediction_error = ?
                    WHERE id = ?
                """, (
                    json.dumps(realized_outcome) if isinstance(realized_outcome, (dict, list)) else str(realized_outcome),
                    prediction_error,
                    prediction_id
                ))

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            self._logger.error(f"[ProductionMonitor] Failed to update realized: {e}")
            return False

    def get_recent_predictions(
        self,
        model: Optional[str] = None,
        hours: int = 24
    ) -> pd.DataFrame:
        """
        Get recent predictions.

        Args:
            model: Filter by model
            hours: Lookback hours

        Returns:
            DataFrame with recent predictions
        """
        try:
            with get_db() as conn:
                cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

                query = """
                    SELECT * FROM production_predictions
                    WHERE timestamp > ?
                """
                params = [cutoff]

                if model:
                    query += " AND model = ?"
                    params.append(model)

                query += " ORDER BY timestamp DESC"

                df = pd.read_sql_query(query, conn, params=params)
                return df

        except Exception as e:
            self._logger.error(f"[ProductionMonitor] Failed to get predictions: {e}")
            return pd.DataFrame()

    def compute_realtime_accuracy(
        self,
        model: str,
        window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Compute real-time accuracy metrics.

        Args:
            model: Model name
            window_hours: Time window for analysis

        Returns:
            Real-time accuracy metrics
        """
        df = self.get_recent_predictions(model=model, hours=window_hours)

        if len(df) == 0:
            return {
                "model": model,
                "window_hours": window_hours,
                "status": "no_data",
                "n_predictions": 0
            }

        df_evaluated = df.dropna(subset=["prediction_error"])

        if len(df_evaluated) == 0:
            return {
                "model": model,
                "window_hours": window_hours,
                "status": "awaiting_realized",
                "n_predictions": len(df),
                "n_evaluated": 0
            }

        errors = df_evaluated["prediction_error"].astype(float)

        return {
            "model": model,
            "window_hours": window_hours,
            "status": "active",
            "n_predictions": len(df),
            "n_evaluated": len(df_evaluated),
            "mean_absolute_error": round(errors.abs().mean(), 4),
            "rmse": round(np.sqrt((errors ** 2).mean()), 4),
            "max_error": round(errors.abs().max(), 4),
            "accuracy": round(1 - (errors.abs() > 0.5).mean(), 4) if len(errors) > 0 else None,
            "last_updated": datetime.utcnow().isoformat()
        }

    def detect_input_drift(
        self,
        model: str,
        baseline_hours: int = 168,  # 1 week
        current_hours: int = 24
    ) -> List[DriftReport]:
        """
        Detect input drift by comparing baseline vs recent input distributions.

        Args:
            model: Model to analyze
            baseline_hours: Baseline period
            current_hours: Current period

        Returns:
            List of drift reports per input variable
        """
        try:
            with get_db() as conn:
                # Get baseline data
                baseline_cutoff = (datetime.utcnow() - timedelta(hours=baseline_hours)).isoformat()
                current_cutoff = (datetime.utcnow() - timedelta(hours=current_hours)).isoformat()

                cursor = conn.cursor()
                cursor.execute("""
                    SELECT inputs FROM production_predictions
                    WHERE model = ? AND timestamp > ? AND timestamp <= ?
                """, (model, baseline_cutoff, current_cutoff))

                baseline_rows = cursor.fetchall()

                cursor.execute("""
                    SELECT inputs FROM production_predictions
                    WHERE model = ? AND timestamp > ?
                """, (model, current_cutoff))

                current_rows = cursor.fetchall()

                if len(baseline_rows) < 10 or len(current_rows) < 5:
                    return []

                # Parse inputs
                baseline_inputs = []
                for row in baseline_rows:
                    try:
                        inputs = json.loads(row["inputs"])
                        baseline_inputs.append(inputs)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Skip rows with invalid JSON or missing inputs
                        continue

                current_inputs = []
                for row in current_rows:
                    try:
                        inputs = json.loads(row["inputs"])
                        current_inputs.append(inputs)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Skip rows with invalid JSON or missing inputs
                        continue

                if not baseline_inputs or not current_inputs:
                    return []

                # Calculate drift for each feature
                reports = []
                feature_names = set(baseline_inputs[0].keys()) if baseline_inputs else set()

                for feature in feature_names:
                    baseline_values = [inp.get(feature) for inp in baseline_inputs if feature in inp and isinstance(inp.get(feature), (int, float))]
                    current_values = [inp.get(feature) for inp in current_inputs if feature in inp and isinstance(inp.get(feature), (int, float))]

                    if len(baseline_values) < 5 or len(current_values) < 3:
                        continue

                    baseline_mean = statistics.mean(baseline_values)
                    current_mean = statistics.mean(current_values)

                    # Simple drift score: normalized difference
                    baseline_std = statistics.stdev(baseline_values) if len(baseline_values) > 1 else 1
                    drift_score = abs(current_mean - baseline_mean) / (baseline_std + 1e-6)

                    drift_detected = drift_score > self.thresholds["drift_score"]
                    severity = "critical" if drift_score > 1.0 else "warning" if drift_score > 0.5 else "info"

                    reports.append(DriftReport(
                        variable=feature,
                        drift_detected=drift_detected,
                        drift_score=round(drift_score, 4),
                        baseline_mean=round(baseline_mean, 4),
                        current_mean=round(current_mean, 4),
                        severity=severity
                    ))

                return reports

        except Exception as e:
            self._logger.error(f"[ProductionMonitor] Failed to detect drift: {e}")
            return []

    def check_alert_thresholds(
        self,
        window_hours: int = 24
    ) -> List[Alert]:
        """
        Check all models for alert conditions.

        Args:
            window_hours: Time window for analysis

        Returns:
            List of active alerts
        """
        alerts = []

        for model in self.MONITORED_MODELS:
            df = self.get_recent_predictions(model=model, hours=window_hours)

            if len(df) == 0:
                continue

            # Check prediction volume
            if len(df) < self.thresholds["prediction_volume"]:
                alerts.append(Alert(
                    alert_type="low_volume",
                    severity="warning",
                    message=f"{model}: Low prediction volume ({len(df)} in {window_hours}h)",
                    timestamp=datetime.utcnow().isoformat(),
                    metric_value=len(df),
                    threshold=self.thresholds["prediction_volume"]
                ))

            # Check latency
            avg_latency = df["latency_ms"].mean() if "latency_ms" in df.columns else 0
            if avg_latency > self.thresholds["latency_ms"]:
                alerts.append(Alert(
                    alert_type="high_latency",
                    severity="critical" if avg_latency > self.thresholds["latency_ms"] * 2 else "warning",
                    message=f"{model}: High latency ({avg_latency:.0f}ms)",
                    timestamp=datetime.utcnow().isoformat(),
                    metric_value=round(avg_latency, 2),
                    threshold=self.thresholds["latency_ms"]
                ))

            # Check error rate
            df_with_errors = df.dropna(subset=["prediction_error"])
            if len(df_with_errors) > 0:
                error_rate = (df_with_errors["prediction_error"].abs() > 0.5).mean()
                if error_rate > self.thresholds["error_rate"]:
                    alerts.append(Alert(
                        alert_type="high_error_rate",
                        severity="critical" if error_rate > 0.20 else "warning",
                        message=f"{model}: High error rate ({error_rate:.1%})",
                        timestamp=datetime.utcnow().isoformat(),
                        metric_value=round(error_rate, 4),
                        threshold=self.thresholds["error_rate"]
                    ))

            # Check for drift
            drift_reports = self.detect_input_drift(model)
            for report in drift_reports:
                if report.drift_detected:
                    alerts.append(Alert(
                        alert_type="input_drift",
                        severity=report.severity,
                        message=f"{model}: Drift detected in {report.variable} (score: {report.drift_score:.2f})",
                        timestamp=datetime.utcnow().isoformat(),
                        metric_value=report.drift_score,
                        threshold=self.thresholds["drift_score"]
                    ))

        return alerts

    def get_model_health(
        self,
        window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get health status for all monitored models.

        Args:
            window_hours: Time window for analysis

        Returns:
            Model health summary
        """
        health_status = []

        for model in self.MONITORED_MODELS:
            df = self.get_recent_predictions(model=model, hours=window_hours)

            if len(df) == 0:
                health_status.append(ModelHealth(
                    model_name=model,
                    status="no_data",
                    last_prediction=None,
                    predictions_last_hour=0,
                    avg_latency_ms=0,
                    error_rate=0,
                    drift_status="unknown"
                ).to_dict())
                continue

            # Calculate metrics
            last_pred = df.iloc[0]["prediction"] if len(df) > 0 else None
            last_hour = df[df["timestamp"] > (datetime.utcnow() - timedelta(hours=1)).isoformat()]
            pred_count = len(last_hour)
            avg_latency = df["latency_ms"].mean() if "latency_ms" in df.columns else 0

            df_with_errors = df.dropna(subset=["prediction_error"])
            error_rate = (df_with_errors["prediction_error"].abs() > 0.5).mean() if len(df_with_errors) > 0 else 0

            # Check for drift
            drift_reports = self.detect_input_drift(model)
            drift_detected = any(r.drift_detected for r in drift_reports)
            drift_status = "drift_detected" if drift_detected else "stable"

            # Determine status
            if error_rate > 0.20 or avg_latency > 2000:
                status = "failing"
            elif error_rate > 0.10 or avg_latency > 1000 or drift_detected:
                status = "degraded"
            else:
                status = "healthy"

            health_status.append(ModelHealth(
                model_name=model,
                status=status,
                last_prediction=str(last_pred) if last_pred else None,
                predictions_last_hour=pred_count,
                avg_latency_ms=round(avg_latency, 2),
                error_rate=round(error_rate, 4),
                drift_status=drift_status
            ).to_dict())

        # Overall system status
        failing_count = sum(1 for h in health_status if h["status"] == "failing")
        degraded_count = sum(1 for h in health_status if h["status"] == "degraded")

        if failing_count > 0:
            overall_status = "critical"
        elif degraded_count > 1:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "window_hours": window_hours,
            "overall_status": overall_status,
            "models": health_status,
            "failing_count": failing_count,
            "degraded_count": degraded_count,
            "healthy_count": len(health_status) - failing_count - degraded_count
        }

    def export_dashboard_metrics(self) -> Dict[str, Any]:
        """
        Export metrics for external dashboard integration.

        Returns:
            Dashboard-compatible metrics
        """
        health = self.get_model_health()
        alerts = self.check_alert_thresholds()

        # Format for dashboard
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system_status": health["overall_status"],
            "active_alerts": len([a for a in alerts if a.severity in ["warning", "critical"]]),
            "critical_alerts": len([a for a in alerts if a.severity == "critical"]),
            "model_metrics": [
                {
                    "model": m["model_name"],
                    "status": m["status"],
                    "predictions_last_hour": m["predictions_last_hour"],
                    "latency_ms": m["avg_latency_ms"],
                    "error_rate": m["error_rate"],
                    "drift": m["drift_status"]
                }
                for m in health["models"]
            ],
            "alert_summary": [
                {
                    "type": a.alert_type,
                    "severity": a.severity,
                    "message": a.message,
                    "timestamp": a.timestamp
                }
                for a in alerts[:10]  # Top 10 alerts
            ]
        }

    def get_monitoring_summary(self) -> Dict[str, Any]:
        """
        Get complete monitoring summary.

        Returns:
            Comprehensive monitoring summary
        """
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "thresholds": self.thresholds,
            "model_health": self.get_model_health(),
            "active_alerts": [a.to_dict() for a in self.check_alert_thresholds()],
            "dashboard_metrics": self.export_dashboard_metrics(),
            "recommendations": self._generate_recommendations()
        }

    def _generate_recommendations(self) -> List[str]:
        """Generate monitoring recommendations."""
        recommendations = []
        health = self.get_model_health()
        alerts = self.check_alert_thresholds()

        # Check for failing models
        failing = [m for m in health["models"] if m["status"] == "failing"]
        if failing:
            recommendations.append(
                f"CRITICAL: {len(failing)} model(s) failing - immediate attention required"
            )

        # Check for drift
        drift_alerts = [a for a in alerts if a.alert_type == "input_drift"]
        if drift_alerts:
            recommendations.append(
                f"Input drift detected in {len(drift_alerts)} variable(s) - consider model retraining"
            )

        # Check for high latency
        latency_alerts = [a for a in alerts if a.alert_type == "high_latency"]
        if latency_alerts:
            recommendations.append(
                "High prediction latency detected - check infrastructure"
            )

        if not recommendations:
            recommendations.append("All systems operating normally")

        return recommendations


# Global instance
production_monitor = ProductionMonitor()
