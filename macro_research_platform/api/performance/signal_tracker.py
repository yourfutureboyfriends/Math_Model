"""
Live Signal Performance Tracker — Real-time signal quality monitoring

Tracks rolling accuracy, Information Coefficient (IC), and Sharpe ratio
per signal module to detect degradation in predictive power.

Academic Basis:
- Rolling IC: Grinold & Kahn (1999) "Active Portfolio Management"
- Signal Decay: Fama & French (2010) "Luck vs Skill"
- Sharpe Ratio: Sharpe (1994) "The Sharpe Ratio"
"""

import logging
import sqlite3
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "macro_terminal.db"

# Rolling window sizes for metrics calculation
ROLLING_WINDOWS = {
    "1d": 1,      # Daily
    "1w": 5,      # Weekly (trading days)
    "1m": 21,     # Monthly
    "3m": 63,     # Quarterly
    "6m": 126,    # Half-year
    "1y": 252,    # Yearly
}

SIGNAL_MODULES = [
    "hmm_regime",
    "kalman_filter",
    "bayesian_aggregator",
    "news_sentiment",
    "multifactor_alpha",
    "sector_rotation",
]


@dataclass
class SignalPrediction:
    """Single signal prediction record."""
    timestamp: datetime
    module: str
    signal_value: float  # -1 to 1 (bearish to bullish)
    confidence: float    # 0 to 1
    direction: str       # "bullish", "bearish", "neutral"
    meta: Optional[Dict] = None


@dataclass
class MarketOutcome:
    """Market outcome for validation."""
    timestamp: datetime
    spy_return_1d: float
    spy_return_5d: float
    spy_direction_1d: int  # 1 = up, -1 = down
    realized_vol: float
    vix: float


class SignalPerformanceTracker:
    """
    Track live signal performance metrics per module.

    Metrics tracked:
    - Directional Accuracy: % correct directional calls
    - Information Coefficient (IC): corr(signal_t, return_t+1)
    - Sharpe Ratio: risk-adjusted returns from signal-following
    - Signal Decay: IC at 1d/5d/10d/20d horizons
    - Calibration: predicted vs actual probability
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._ensure_tables_exist()
        # In-memory cache for recent predictions
        self._prediction_cache: Dict[str, deque] = {
            module: deque(maxlen=500) for module in SIGNAL_MODULES
        }

    def _ensure_tables_exist(self):
        """Create signal performance tables if not exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Main performance metrics table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS signal_performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        module TEXT,
                        window TEXT,
                        directional_accuracy REAL,
                        ic_1d REAL,
                        ic_5d REAL,
                        sharpe_ratio REAL,
                        total_signals INTEGER,
                        correct_signals INTEGER,
                        avg_confidence REAL,
                        calibration_error REAL,
                        status TEXT
                    )
                """)

                # Raw predictions for back-calculation
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS signal_predictions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        module TEXT,
                        signal_value REAL,
                        confidence REAL,
                        direction TEXT,
                        meta TEXT
                    )
                """)

                # Market outcomes for validation
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS market_outcomes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        spy_return_1d REAL,
                        spy_return_5d REAL,
                        spy_direction_1d INTEGER,
                        realized_vol REAL,
                        vix REAL
                    )
                """)

                conn.commit()
                logger.info("[SIGNAL_TRACKER] Tables ensured")
        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to create tables: {e}")

    def record_prediction(self, module: str, signal_value: float,
                          confidence: float, direction: str,
                          meta: Optional[Dict] = None):
        """Record a new signal prediction."""
        timestamp = datetime.now()

        prediction = SignalPrediction(
            timestamp=timestamp,
            module=module,
            signal_value=signal_value,
            confidence=confidence,
            direction=direction,
            meta=meta
        )

        # Store in memory cache
        self._prediction_cache[module].append(prediction)

        # Store in database
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO signal_predictions
                    (timestamp, module, signal_value, confidence, direction, meta)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    timestamp.isoformat(), module, signal_value,
                    confidence, direction, str(meta) if meta else None
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to record prediction: {e}")

    def record_market_outcome(self, spy_return_1d: float,
                               spy_return_5d: float,
                               spy_direction_1d: int,
                               realized_vol: float,
                               vix: float):
        """Record market outcome for signal validation."""
        timestamp = datetime.now()

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO market_outcomes
                    (timestamp, spy_return_1d, spy_return_5d,
                     spy_direction_1d, realized_vol, vix)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    timestamp.isoformat(), spy_return_1d, spy_return_5d,
                    spy_direction_1d, realized_vol, vix
                ))
                conn.commit()
                logger.info(f"[SIGNAL_TRACKER] Market outcome recorded: {spy_return_1d:.2%}")
        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to record outcome: {e}")

    def calculate_metrics(self, module: str, window: str = "1m") -> Dict[str, Any]:
        """
        Calculate performance metrics for a module over specified window.
        Falls back to backtest_results if live predictions are insufficient.

        Args:
            module: Signal module name
            window: One of "1d", "1w", "1m", "3m", "6m", "1y"

        Returns:
            Dict with metrics including accuracy, IC, Sharpe, data_source
        """
        days = ROLLING_WINDOWS.get(window, 21)
        cutoff = datetime.now() - timedelta(days=days)

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get predictions for window
                predictions = conn.execute("""
                    SELECT timestamp, signal_value, confidence, direction
                    FROM signal_predictions
                    WHERE module = ? AND timestamp > ?
                    ORDER BY timestamp
                """, (module, cutoff.isoformat())).fetchall()

                # Get market outcomes for window
                outcomes = conn.execute("""
                    SELECT timestamp, spy_return_1d, spy_return_5d,
                           spy_direction_1d, vix
                    FROM market_outcomes
                    WHERE timestamp > ?
                    ORDER BY timestamp
                """, (cutoff.isoformat(),)).fetchall()

                pred_count = len(predictions)

                # Check if we have enough live data
                if pred_count >= 10 and len(outcomes) >= 10:
                    # Calculate live metrics
                    metrics = self._compute_metrics(predictions, outcomes)
                    metrics["module"] = module
                    metrics["window"] = window
                    metrics["timestamp"] = datetime.now().isoformat()
                    metrics["total_signals"] = pred_count
                    metrics["data_source"] = "live"
                    metrics["warmup_note"] = None

                    # Determine status
                    metrics["status"] = self._determine_status(metrics)

                    return metrics

                # FALLBACK: Use backtest_results for modules with insufficient live data
                return self._get_backtest_fallback_metrics(conn, module, window, pred_count)

        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to calculate metrics: {e}")
            return {
                "module": module,
                "window": window,
                "status": "error",
                "error": str(e),
                "data_source": "error"
            }

    def _get_backtest_fallback_metrics(self, conn: sqlite3.Connection,
                                       module: str, window: str,
                                       live_predictions: int) -> Dict[str, Any]:
        """Get metrics from backtest_results as fallback."""
        # Map module names to backtest module names
        bt_module_map = {
            'hmm_regime': 'hmm_regime',
            'kalman_filter': 'kalman_ic',
            'bayesian_aggregator': 'bayesian_ic',
            'news_sentiment': 'sentiment_accuracy',
            'sector_rotation': 'sector_rotation',
            'multifactor_alpha': None,
        }

        bt_module = bt_module_map.get(module)
        if not bt_module:
            return {
                "module": module,
                "window": window,
                "status": "STARTING",
                "total_signals": live_predictions,
                "message": "No backtest data available",
                "data_source": "none",
                "warmup_note": f"{live_predictions}/10 live predictions — module starting up"
            }

        metrics = {
            "module": module,
            "window": window,
            "timestamp": datetime.now().isoformat(),
            "total_signals": live_predictions,
            "data_source": "backtest",
        }

        # Get accuracy if available
        accuracy_metrics = {
            'hmm_regime': 'regime_accuracy',
            'sentiment_accuracy': 'overall_accuracy',
            'sector_rotation': 'win_rate',
        }
        if module in accuracy_metrics:
            row = conn.execute('''
                SELECT metric_value FROM backtest_results
                WHERE module = ? AND metric_name = ?
                ORDER BY run_date DESC LIMIT 1
            ''', (bt_module, accuracy_metrics[module])).fetchone()
            if row:
                metrics["directional_accuracy"] = float(row[0])

        # Get IC if available
        ic_metrics = {
            'kalman_filter': 'mean_filtered_ic',
            'bayesian_aggregator': 'overall_ic_5d',
        }
        if module in ic_metrics:
            row = conn.execute('''
                SELECT metric_value FROM backtest_results
                WHERE module = ? AND metric_name = ?
                ORDER BY run_date DESC LIMIT 1
            ''', (bt_module, ic_metrics[module])).fetchone()
            if row:
                ic_val = float(row[0])
                metrics["ic_5d"] = ic_val
                metrics["ic_1d"] = ic_val * 0.8

        # Get Sharpe if available
        sharpe_metrics = {
            'sentiment_accuracy': 'directional_sharpe',
            'sector_rotation': 'strategy_sharpe',
        }
        if module in sharpe_metrics:
            row = conn.execute('''
                SELECT metric_value FROM backtest_results
                WHERE module = ? AND metric_name = ?
                ORDER BY run_date DESC LIMIT 1
            ''', (bt_module, sharpe_metrics[module])).fetchone()
            if row:
                metrics["sharpe_ratio"] = float(row[0])

        # Determine status based on available metrics and live prediction count
        if live_predictions == 0:
            metrics["status"] = "STARTING"
            metrics["warmup_note"] = "Module starting — using backtest IC"
        elif live_predictions < 5:
            metrics["status"] = "WARMING_UP"
            metrics["warmup_note"] = f"{live_predictions}/10 live predictions — warming up (backtest shown)"
        elif live_predictions < 10:
            metrics["status"] = "PARTIAL"
            metrics["warmup_note"] = f"{live_predictions}/10 live predictions — partial (backtest shown)"
        else:
            metrics["status"] = self._determine_status(metrics)
            metrics["warmup_note"] = "Backtest-based metrics"

        return metrics

    def _compute_metrics(self, predictions: List, outcomes: List) -> Dict[str, Any]:
        """Compute performance metrics from predictions and outcomes."""
        # Match predictions to subsequent outcomes
        matched = []

        for pred in predictions:
            pred_ts = datetime.fromisoformat(pred[0])
            # Find next market outcome after prediction
            for outcome in outcomes:
                out_ts = datetime.fromisoformat(outcome[0])
                if out_ts > pred_ts:
                    matched.append({
                        "signal": pred[1],
                        "confidence": pred[2],
                        "pred_direction": pred[3],
                        "return_1d": outcome[1],
                        "return_5d": outcome[2],
                        "actual_direction": outcome[3],
                    })
                    break

        if len(matched) < 10:
            return {"status": "insufficient_matched", "matched_count": len(matched)}

        # Directional accuracy
        correct = sum(1 for m in matched
                     if (m["signal"] > 0 and m["actual_direction"] == 1) or
                        (m["signal"] < 0 and m["actual_direction"] == -1))
        accuracy = correct / len(matched)

        # Information Coefficient (rank correlation)
        signals = np.array([m["signal"] for m in matched])
        returns_1d = np.array([m["return_1d"] for m in matched])
        returns_5d = np.array([m["return_5d"] for m in matched])

        ic_1d = np.corrcoef(signals[:-1], returns_1d[1:])[0, 1] if len(signals) > 1 else 0
        ic_5d = np.corrcoef(signals[:-1], returns_5d[1:])[0, 1] if len(signals) > 1 else 0

        # Sharpe ratio from signal-following strategy
        signal_returns = signals[:-1] * returns_1d[1:]
        sharpe = np.mean(signal_returns) / (np.std(signal_returns) + 1e-6) * np.sqrt(252)

        # Average confidence
        avg_confidence = np.mean([m["confidence"] for m in matched])

        # Calibration: how often does confidence match accuracy
        high_conf = [m for m in matched if m["confidence"] > 0.7]
        if high_conf:
            high_conf_correct = sum(1 for m in high_conf
                                     if (m["signal"] > 0 and m["actual_direction"] == 1) or
                                        (m["signal"] < 0 and m["actual_direction"] == -1))
            calibration_error = abs(len(high_conf_correct) / len(high_conf) - avg_confidence)
        else:
            calibration_error = 0

        return {
            "directional_accuracy": accuracy,
            "ic_1d": ic_1d if not np.isnan(ic_1d) else 0,
            "ic_5d": ic_5d if not np.isnan(ic_5d) else 0,
            "sharpe_ratio": sharpe if not np.isnan(sharpe) else 0,
            "total_signals": len(matched),
            "correct_signals": correct,
            "avg_confidence": avg_confidence,
            "calibration_error": calibration_error,
        }

    def _determine_status(self, metrics: Dict) -> str:
        """Determine module health status based on metrics."""
        # Check prediction count for warmup status
        total_signals = metrics.get("total_signals", 0)

        # Tiered warmup status based on prediction count
        if total_signals == 0:
            return "STARTING"
        elif total_signals < 5:
            return "WARMING_UP"
        elif total_signals < 10:
            return "PARTIAL"

        # For 10+ predictions, use computed status
        accuracy = metrics.get("directional_accuracy", 0)
        ic = metrics.get("ic_1d", 0)
        sharpe = metrics.get("sharpe_ratio", 0)

        # HOT: Strong predictive power (>15% IC, >55% accuracy, good Sharpe)
        if ic > 0.15 and accuracy > 0.55 and sharpe > 0.8:
            return "HOT"
        # NORMAL: Good predictive power (>5% IC, >52% accuracy)
        elif ic > 0.05 and accuracy > 0.52 and sharpe > 0.3:
            return "NORMAL"
        # DEGRADING: Weak but positive predictive power
        elif ic > 0.0 and accuracy >= 0.50:
            return "DEGRADING"
        # BROKEN: Negative IC or very low accuracy
        else:
            return "BROKEN"

    def save_metrics(self, metrics: Dict[str, Any]):
        """Save calculated metrics to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO signal_performance
                    (timestamp, module, window, directional_accuracy,
                     ic_1d, ic_5d, sharpe_ratio, total_signals,
                     correct_signals, avg_confidence, calibration_error, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    metrics.get("timestamp"),
                    metrics.get("module"),
                    metrics.get("window"),
                    metrics.get("directional_accuracy"),
                    metrics.get("ic_1d"),
                    metrics.get("ic_5d"),
                    metrics.get("sharpe_ratio"),
                    metrics.get("total_signals"),
                    metrics.get("correct_signals"),
                    metrics.get("avg_confidence"),
                    metrics.get("calibration_error"),
                    metrics.get("status")
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to save metrics: {e}")

    def get_latest_metrics(self, module: Optional[str] = None,
                          window: str = "1m") -> List[Dict]:
        """Get latest performance metrics from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                if module:
                    rows = conn.execute("""
                        SELECT * FROM signal_performance
                        WHERE module = ? AND window = ?
                        ORDER BY timestamp DESC LIMIT 1
                    """, (module, window)).fetchall()
                else:
                    # Get latest for each module
                    rows = conn.execute("""
                        SELECT sp.* FROM signal_performance sp
                        INNER JOIN (
                            SELECT module, MAX(timestamp) as max_ts
                            FROM signal_performance
                            WHERE window = ?
                            GROUP BY module
                        ) latest ON sp.module = latest.module
                        AND sp.timestamp = latest.max_ts
                        WHERE sp.window = ?
                    """, (window, window)).fetchall()

                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[SIGNAL_TRACKER] Failed to get metrics: {e}")
            return []

    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall signal health summary."""
        metrics = self.get_latest_metrics(window="1m")

        if not metrics:
            return {
                "status": "no_data",
                "modules_tracked": 0,
                "healthy_count": 0,
                "degraded_count": 0,
                "unhealthy_count": 0,
            }

        healthy = sum(1 for m in metrics if m.get("status") == "healthy")
        degraded = sum(1 for m in metrics if m.get("status") == "degraded")
        unhealthy = sum(1 for m in metrics if m.get("status") == "unhealthy")

        overall = "healthy" if unhealthy == 0 else "degraded" if unhealthy <= 2 else "critical"

        return {
            "status": overall,
            "modules_tracked": len(metrics),
            "healthy_count": healthy,
            "degraded_count": degraded,
            "unhealthy_count": unhealthy,
            "module_details": metrics,
            "timestamp": datetime.now().isoformat(),
        }

    def record_all_modules(self, signals_data: Dict[str, Any]):
        """Record predictions from all signal modules at once."""
        timestamp = datetime.now()

        module_mapping = {
            "hmm_regime": ("regime_signal", "regime_confidence"),
            "kalman_filter": ("kalman_signal", "kalman_confidence"),
            "bayesian_aggregator": ("bayesian_signal", "bayesian_confidence"),
            "news_sentiment": ("sentiment_signal", "sentiment_confidence"),
            "multifactor_alpha": ("alpha_signal", "alpha_confidence"),
            "sector_rotation": ("rotation_signal", "rotation_confidence"),
        }

        for module, (signal_key, conf_key) in module_mapping.items():
            if signal_key in signals_data:
                signal_val = signals_data.get(signal_key, 0)
                confidence = signals_data.get(conf_key, 0.5)
                direction = "bullish" if signal_val > 0.2 else "bearish" if signal_val < -0.2 else "neutral"

                self.record_prediction(
                    module=module,
                    signal_value=signal_val,
                    confidence=confidence,
                    direction=direction,
                    meta={"source": "live_pipeline"}
                )

        logger.info(f"[SIGNAL_TRACKER] Recorded predictions for {len(module_mapping)} modules")


def get_tracker() -> SignalPerformanceTracker:
    """Get or create signal performance tracker singleton."""
    if not hasattr(get_tracker, '_instance'):
        get_tracker._instance = SignalPerformanceTracker()
    return get_tracker._instance
