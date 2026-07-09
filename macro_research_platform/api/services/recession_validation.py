"""
Recession Model Validation Service — Phase 5: Validate 3-model ensemble.

Validates recession prediction models:
1. Component validation (logistic, probit, Sahm individually)
2. ROC AUC for each component
3. Precision/recall at different thresholds
4. False positive rate analysis
5. Blend weight optimization (grid search)
6. Lead time before recessions

Usage:
    from api.services.recession_validation import recession_validator

    # Log recession forecast
    recession_validator.log_recession_forecast(
        date="2024-01-15",
        horizon="12M",
        components={
            "logistic": 0.45,
            "probit": 0.50,
            "sahm": 0.30,
        },
        blended_probability=0.44
    )

    # Update with realized outcome
    recession_validator.update_realized_outcome("2024-01-15", "12M", False)

    # Analyze validation metrics
    metrics = recession_validator.compute_component_metrics()

    # Optimize blend weights
    optimal = recession_validator.optimize_blend_weights()
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json

import numpy as np
import pandas as pd

from database.db import get_db

logger = logging.getLogger(__name__)


@dataclass
class ComponentMetrics:
    """Metrics for a single recession model component."""
    component: str
    n_forecasts: int
    n_evaluated: int
    auc_roc: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    false_positive_rate: Optional[float] = None
    true_positive_rate: Optional[float] = None
    accuracy: Optional[float] = None
    hit_rate: Optional[float] = None
    avg_lead_time_months: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlendOptimizationResult:
    """Result of blend weight optimization."""
    optimal_weights: Dict[str, float]
    current_weights: Dict[str, float]
    improvement: float
    all_results: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RecessionValidator:
    """
    Validation service for recession ensemble models.

    Validates the 3-model blend (40% logistic, 40% probit, 20% Sahm)
    and provides calibration recommendations.
    """

    # Current blend weights from MODEL_INVENTORY
    CURRENT_WEIGHTS = {
        "logistic": 0.40,
        "probit": 0.40,
        "sahm": 0.20,
    }

    # Thresholds for classification
    DEFAULT_THRESHOLD = 0.50
    HIGH_CONFIDENCE_THRESHOLD = 0.60

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def log_recession_forecast(
        self,
        date: str,
        horizon: str,
        components: Dict[str, float],
        blended_probability: float,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log recession forecast with component breakdown.

        Args:
            date: ISO format date
            horizon: "6M" or "12M"
            components: Dict with keys 'logistic', 'probit', 'sahm'
            blended_probability: Final blended probability (0-1)
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure recession_forecast_history table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recession_forecast_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        horizon TEXT NOT NULL,
                        logistic_prob REAL,
                        probit_prob REAL,
                        sahm_prob REAL,
                        blended_prob REAL NOT NULL,
                        weights_logistic REAL,
                        weights_probit REAL,
                        weights_sahm REAL,
                        realized_recession INTEGER,
                        realized_date TEXT,
                        lead_time_months REAL,
                        metadata TEXT
                    )
                """)

                cursor.execute("""
                    INSERT INTO recession_forecast_history (
                        date, recorded_at, horizon,
                        logistic_prob, probit_prob, sahm_prob, blended_prob,
                        weights_logistic, weights_probit, weights_sahm,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    datetime.utcnow().isoformat(),
                    horizon,
                    components.get('logistic'),
                    components.get('probit'),
                    components.get('sahm'),
                    blended_probability,
                    self.CURRENT_WEIGHTS['logistic'],
                    self.CURRENT_WEIGHTS['probit'],
                    self.CURRENT_WEIGHTS['sahm'],
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(
                    f"[RecessionValidator] Logged {horizon} forecast for {date} (id={log_id})"
                )
                return log_id

        except Exception as e:
            self._logger.error(f"[RecessionValidator] Failed to log forecast: {e}")
            raise

    def update_realized_outcome(
        self,
        date: str,
        horizon: str,
        realized_recession: bool,
        realized_date: Optional[str] = None,
        lead_time_months: Optional[float] = None
    ) -> bool:
        """
        Update forecast with realized recession outcome.

        Args:
            date: Forecast date
            horizon: Forecast horizon
            realized_recession: Whether recession occurred
            realized_date: When recession was confirmed (if applicable)
            lead_time_months: Months of lead time before recession start

        Returns:
            True if update successful
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE recession_forecast_history
                    SET realized_recession = ?,
                        realized_date = ?,
                        lead_time_months = ?
                    WHERE date = ? AND horizon = ?
                """, (
                    1 if realized_recession else 0,
                    realized_date,
                    lead_time_months,
                    date,
                    horizon
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self._logger.error(f"[RecessionValidator] Failed to update outcome: {e}")
            return False

    def get_recession_history(
        self,
        component: Optional[str] = None,
        horizon: Optional[str] = None,
        min_observations: int = 30
    ) -> pd.DataFrame:
        """
        Retrieve recession forecast history.

        Args:
            component: Filter by component
            horizon: Filter by horizon
            min_observations: Minimum observations required

        Returns:
            DataFrame with recession forecast history
        """
        try:
            with get_db() as conn:
                query = """
                    SELECT * FROM recession_forecast_history
                    WHERE blended_prob IS NOT NULL
                """
                params = []

                if horizon:
                    query += " AND horizon = ?"
                    params.append(horizon)

                query += " ORDER BY date DESC"

                df = pd.read_sql_query(query, conn, params=params)

                if len(df) < min_observations:
                    self._logger.warning(
                        f"[RecessionValidator] Insufficient data: {len(df)} observations"
                    )

                return df

        except Exception as e:
            self._logger.error(f"[RecessionValidator] Failed to get history: {e}")
            return pd.DataFrame()

    def compute_component_metrics(
        self,
        component: str,
        horizon: str = "12M",
        threshold: float = 0.50
    ) -> Optional[ComponentMetrics]:
        """
        Compute validation metrics for a single component.

        Args:
            component: 'logistic', 'probit', or 'sahm'
            horizon: Forecast horizon
            threshold: Probability threshold for classification

        Returns:
            ComponentMetrics with ROC AUC, precision, recall, etc.
        """
        df = self.get_recession_history(horizon=horizon)

        if len(df) < 20:
            return ComponentMetrics(
                component=component,
                n_forecasts=len(df),
                n_evaluated=0
            )

        prob_col = f"{component}_prob"
        if prob_col not in df.columns:
            return ComponentMetrics(
                component=component,
                n_forecasts=len(df),
                n_evaluated=0
            )

        # Filter to rows with realized outcomes
        df_valid = df.dropna(subset=[prob_col, 'realized_recession'])

        if len(df_valid) < 10:
            return ComponentMetrics(
                component=component,
                n_forecasts=len(df),
                n_evaluated=len(df_valid)
            )

        y_true = df_valid['realized_recession'].astype(int).values
        y_prob = df_valid[prob_col].astype(float).values
        y_pred = (y_prob >= threshold).astype(int)

        # Compute metrics
        tp = ((y_pred == 1) & (y_true == 1)).sum()
        fp = ((y_pred == 1) & (y_true == 0)).sum()
        tn = ((y_pred == 0) & (y_true == 0)).sum()
        fn = ((y_pred == 0) & (y_true == 1)).sum()

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        tpr = recall
        accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0

        # ROC AUC
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_true, y_prob)
        except ImportError:
            # Manual AUC calculation
            auc = self._manual_auc(y_true, y_prob)

        # Average lead time
        lead_times = df_valid[df_valid['lead_time_months'].notna()]['lead_time_months']
        avg_lead = lead_times.mean() if len(lead_times) > 0 else None

        return ComponentMetrics(
            component=component,
            n_forecasts=len(df),
            n_evaluated=len(df_valid),
            auc_roc=round(auc, 4) if auc else None,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            false_positive_rate=round(fpr, 4),
            true_positive_rate=round(tpr, 4),
            accuracy=round(accuracy, 4),
            hit_rate=round(accuracy, 4),
            avg_lead_time_months=round(avg_lead, 2) if avg_lead else None
        )

    def _manual_auc(self, y_true: np.ndarray, y_prob: np.ndarray) -> float:
        """Manual AUC calculation (fallback without sklearn)."""
        # Sort by probability
        order = np.argsort(y_prob)[::-1]
        y_true_sorted = y_true[order]

        # Calculate TPR and FPR at different thresholds
        tprs = []
        fprs = []

        for i in range(len(y_prob)):
            threshold = y_prob[order[i]]
            y_pred = (y_prob >= threshold).astype(int)

            tp = ((y_pred == 1) & (y_true == 1)).sum()
            fp = ((y_pred == 1) & (y_true == 0)).sum()
            tn = ((y_pred == 0) & (y_true == 0)).sum()
            fn = ((y_pred == 0) & (y_true == 1)).sum()

            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

            tprs.append(tpr)
            fprs.append(fpr)

        # Trapezoidal rule for AUC
        auc = 0
        for i in range(len(fprs) - 1):
            auc += (fprs[i+1] - fprs[i]) * (tprs[i+1] + tprs[i]) / 2

        return abs(auc)

    def compute_all_component_metrics(
        self,
        horizon: str = "12M"
    ) -> Dict[str, ComponentMetrics]:
        """Compute metrics for all three components."""
        metrics = {}
        for component in ['logistic', 'probit', 'sahm']:
            m = self.compute_component_metrics(component, horizon)
            if m:
                metrics[component] = m
        return metrics

    def analyze_threshold_performance(
        self,
        component: str,
        horizon: str = "12M",
        thresholds: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze precision/recall at different thresholds.

        Args:
            component: Component to analyze
            horizon: Forecast horizon
            thresholds: List of thresholds to test

        Returns:
            List of metrics at each threshold
        """
        if thresholds is None:
            thresholds = [0.30, 0.40, 0.50, 0.60, 0.70]

        results = []
        for threshold in thresholds:
            metrics = self.compute_component_metrics(component, horizon, threshold)
            if metrics:
                results.append({
                    'threshold': threshold,
                    'precision': metrics.precision,
                    'recall': metrics.recall,
                    'f1_score': metrics.f1_score,
                    'false_positive_rate': metrics.false_positive_rate,
                    'true_positive_rate': metrics.true_positive_rate,
                })

        return results

    def optimize_blend_weights(
        self,
        horizon: str = "12M",
        weight_grid: Optional[List[float]] = None
    ) -> BlendOptimizationResult:
        """
        Grid search to optimize blend weights.

        Tests different weight combinations to maximize AUC.

        Args:
            horizon: Forecast horizon
            weight_grid: Grid of weights to test [0.2, 0.3, 0.4, 0.5]

        Returns:
            BlendOptimizationResult with optimal weights
        """
        if weight_grid is None:
            weight_grid = [0.2, 0.3, 0.4, 0.5]

        df = self.get_recession_history(horizon=horizon)

        if len(df) < 20:
            return BlendOptimizationResult(
                optimal_weights=self.CURRENT_WEIGHTS,
                current_weights=self.CURRENT_WEIGHTS,
                improvement=0.0,
                all_results=[]
            )

        # Filter to rows with all components and realized outcomes
        df_valid = df.dropna(
            subset=['logistic_prob', 'probit_prob', 'sahm_prob', 'realized_recession']
        )

        if len(df_valid) < 10:
            return BlendOptimizationResult(
                optimal_weights=self.CURRENT_WEIGHTS,
                current_weights=self.CURRENT_WEIGHTS,
                improvement=0.0,
                all_results=[]
            )

        y_true = df_valid['realized_recession'].astype(int).values

        results = []
        best_auc = 0
        best_weights = self.CURRENT_WEIGHTS

        # Grid search (constrained: sum to 1.0)
        for w_logistic in weight_grid:
            for w_probit in weight_grid:
                w_sahm = 1.0 - w_logistic - w_probit
                if w_sahm < 0.1 or w_sahm > 0.5:
                    continue

                # Compute blended probabilities
                blended = (
                    w_logistic * df_valid['logistic_prob'].values +
                    w_probit * df_valid['probit_prob'].values +
                    w_sahm * df_valid['sahm_prob'].values
                )

                # Compute AUC
                try:
                    from sklearn.metrics import roc_auc_score
                    auc = roc_auc_score(y_true, blended)
                except ImportError:
                    auc = self._manual_auc(y_true, blended)

                results.append({
                    'weights': {
                        'logistic': w_logistic,
                        'probit': w_probit,
                        'sahm': w_sahm,
                    },
                    'auc_roc': round(auc, 4)
                })

                if auc > best_auc:
                    best_auc = auc
                    best_weights = {
                        'logistic': w_logistic,
                        'probit': w_probit,
                        'sahm': w_sahm,
                    }

        # Compute current AUC
        current_blended = (
            self.CURRENT_WEIGHTS['logistic'] * df_valid['logistic_prob'].values +
            self.CURRENT_WEIGHTS['probit'] * df_valid['probit_prob'].values +
            self.CURRENT_WEIGHTS['sahm'] * df_valid['sahm_prob'].values
        )

        try:
            from sklearn.metrics import roc_auc_score
            current_auc = roc_auc_score(y_true, current_blended)
        except ImportError:
            current_auc = self._manual_auc(y_true, current_blended)

        improvement = best_auc - current_auc

        return BlendOptimizationResult(
            optimal_weights=best_weights,
            current_weights=self.CURRENT_WEIGHTS,
            improvement=round(improvement, 4),
            all_results=results
        )

    def analyze_false_positives(
        self,
        component: str = "blended",
        horizon: str = "12M",
        threshold: float = 0.50
    ) -> Dict[str, Any]:
        """
        Analyze false positive patterns.

        Args:
            component: Component to analyze or 'blended'
            horizon: Forecast horizon
            threshold: Probability threshold

        Returns:
            Dict with FP analysis
        """
        df = self.get_recession_history(horizon=horizon)

        if len(df) < 20:
            return {
                "component": component,
                "error": "Insufficient data",
                "observations": len(df)
            }

        # Get probability column
        if component == "blended":
            prob_col = "blended_prob"
        else:
            prob_col = f"{component}_prob"

        if prob_col not in df.columns:
            return {
                "component": component,
                "error": f"Column {prob_col} not found"
            }

        df_valid = df.dropna(subset=[prob_col, 'realized_recession'])

        if len(df_valid) < 10:
            return {
                "component": component,
                "error": "Insufficient realized data",
                "observations": len(df_valid)
            }

        y_true = df_valid['realized_recession'].astype(int).values
        y_prob = df_valid[prob_col].astype(float).values
        y_pred = (y_prob >= threshold).astype(int)

        # Identify false positives
        fp_mask = (y_pred == 1) & (y_true == 0)
        fp_count = fp_mask.sum()

        # False positive rate
        total_negatives = (y_true == 0).sum()
        fpr = fp_count / total_negatives if total_negatives > 0 else 0

        # Average probability of false positives
        fp_avg_prob = y_prob[fp_mask].mean() if fp_count > 0 else 0

        return {
            "component": component,
            "threshold": threshold,
            "false_positives": int(fp_count),
            "total_negatives": int(total_negatives),
            "false_positive_rate": round(fpr, 4),
            "fp_avg_probability": round(float(fp_avg_prob), 4) if fp_count > 0 else None,
            "recommendation": (
                "Consider raising threshold" if fpr > 0.20
                else "Threshold well calibrated"
            ),
        }

    def analyze_lead_times(
        self,
        component: str = "blended",
        horizon: str = "12M"
    ) -> Dict[str, Any]:
        """
        Analyze lead time before recessions.

        Args:
            component: Component to analyze
            horizon: Forecast horizon

        Returns:
            Dict with lead time statistics
        """
        df = self.get_recession_history(horizon=horizon)

        if 'lead_time_months' not in df.columns:
            return {
                "error": "Lead time data not available"
            }

        lead_times = df[df['lead_time_months'].notna()]['lead_time_months']

        if len(lead_times) < 3:
            return {
                "error": "Insufficient lead time data",
                "observations": len(lead_times)
            }

        return {
            "component": component,
            "horizon": horizon,
            "observations": len(lead_times),
            "mean_lead_months": round(lead_times.mean(), 2),
            "median_lead_months": round(lead_times.median(), 2),
            "min_lead_months": round(lead_times.min(), 2),
            "max_lead_months": round(lead_times.max(), 2),
            "std_lead_months": round(lead_times.std(), 2),
        }

    def get_calibration_recommendations(self) -> Dict[str, Any]:
        """
        Generate calibration recommendations.

        Returns:
            Dict with specific recommendations
        """
        recommendations = {
            "timestamp": datetime.utcnow().isoformat(),
            "component_metrics": {},
            "blend_optimization": None,
            "false_positive_analysis": {},
            "general_recommendations": [],
        }

        # Component metrics
        for component in ['logistic', 'probit', 'sahm']:
            metrics = self.compute_component_metrics(component)
            if metrics:
                recommendations["component_metrics"][component] = metrics.to_dict()

                # Check AUC
                if metrics.auc_roc and metrics.auc_roc < 0.70:
                    recommendations["general_recommendations"].append(
                        f"{component}: AUC {metrics.auc_roc:.2f} below threshold, review model"
                    )

                # Check FPR
                if metrics.false_positive_rate and metrics.false_positive_rate > 0.20:
                    recommendations["general_recommendations"].append(
                        f"{component}: FPR {metrics.false_positive_rate:.1%} above 20%, consider raising threshold"
                    )

        # Blend optimization
        opt_result = self.optimize_blend_weights()
        recommendations["blend_optimization"] = opt_result.to_dict()

        if opt_result.improvement > 0.02:
            recommendations["general_recommendations"].append(
                f"Consider updating blend weights to {opt_result.optimal_weights} "
                f"for +{opt_result.improvement:.2f} AUC improvement"
            )

        # False positive analysis
        for component in ['logistic', 'probit', 'sahm', 'blended']:
            fp_analysis = self.analyze_false_positives(component)
            recommendations["false_positive_analysis"][component] = fp_analysis

        return recommendations


# Global instance
recession_validator = RecessionValidator()
