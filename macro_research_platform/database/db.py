"""
Persistent database layer for Macro Research Platform.
SQLite with WAL mode for concurrent reads during writes.
"""

import sqlite3
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator

# Ensure database directory exists
DB_DIR = Path(__file__).parent
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "macro_platform.db"

logger = logging.getLogger(__name__)


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    WAL mode enables concurrent reads during writes.
    """
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema. Safe to re-run (IF NOT EXISTS)."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Regime history (replaces in-memory REGIME_HISTORY list)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS regime_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                date_label TEXT NOT NULL,
                regime TEXT NOT NULL,
                confidence REAL NOT NULL,
                growth_score REAL,
                inflation_score REAL,
                liquidity_score REAL,
                risk_score REAL,
                raw_data TEXT
            )
        """)

        # Signal history (replaces SIGNAL_HISTORY array)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                period_label TEXT NOT NULL,
                growth REAL,
                inflation REAL,
                liquidity REAL,
                risk REAL,
                recession_prob REAL,
                lei_zscore REAL,
                credit_impulse REAL,
                vix_norm REAL,
                ensemble_score REAL,
                risk_budget REAL
            )
        """)

        # Alert log (replaces in-memory ALERTS list)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                action TEXT,
                acknowledged INTEGER DEFAULT 0,
                dismissed INTEGER DEFAULT 0
            )
        """)

        # Prediction log (replaces PREDICTION_LOG list)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                predicted_regime TEXT NOT NULL,
                actual_regime TEXT,
                ensemble_score REAL,
                model_signals TEXT,
                correct INTEGER
            )
        """)

        # Portfolio snapshots (daily)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL UNIQUE,
                weights TEXT NOT NULL,
                returns_1d REAL,
                cumulative_return REAL,
                sharpe_rolling REAL,
                max_drawdown REAL,
                regime TEXT
            )
        """)

        # LSTM model weights (persist between restarts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ml_model_state (
                id INTEGER PRIMARY KEY,
                updated_at TEXT NOT NULL,
                w_out TEXT NOT NULL,
                trained_steps INTEGER DEFAULT 0
            )
        """)

        # Data fetch log (audit trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                source TEXT NOT NULL,
                series_key TEXT NOT NULL,
                success INTEGER,
                error_message TEXT,
                response_time_ms INTEGER
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_regime_history_date
            ON regime_history(recorded_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_history_period
            ON signal_history(recorded_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_log_created
            ON alert_log(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_log_status
            ON alert_log(dismissed, acknowledged)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fetch_log_time
            ON data_fetch_log(fetched_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fetch_log_source
            ON data_fetch_log(source, series_key)
        """)

        # Forecast history for model validation (Phase 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forecast_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                forecast_timestamp TEXT NOT NULL,
                forecast_date TEXT NOT NULL,
                horizon TEXT,
                predicted_value REAL,
                predicted_class TEXT,
                confidence_lower REAL,
                confidence_upper REAL,
                model_version TEXT,
                model_params TEXT,
                features_used TEXT,
                realized_value REAL,
                realized_class TEXT,
                realized_timestamp TEXT,
                forecast_error REAL,
                absolute_error REAL,
                squared_error REAL,
                directional_hit INTEGER
            )
        """)

        # Create indexes for forecast_history
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_model_date
            ON forecast_history(model_name, forecast_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_timestamp
            ON forecast_history(forecast_timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_model_horizon
            ON forecast_history(model_name, horizon)
        """)

        # ═══════════════════════════════════════════════════════════════════════════════
        # EXPECTED RETURNS HISTORY (Phase 6)
        # ═══════════════════════════════════════════════════════════════════════════════
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expected_returns_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                sector TEXT NOT NULL,
                expected_return REAL NOT NULL,
                earnings_yield REAL,
                regime_premium REAL,
                regime TEXT,
                confidence REAL,
                realized_return REAL,
                forecast_error REAL,
                absolute_error REAL,
                squared_error REAL,
                directional_hit INTEGER,
                metadata TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expected_returns_date
            ON expected_returns_history(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expected_returns_sector
            ON expected_returns_history(sector)
        """)

        # ═══════════════════════════════════════════════════════════════════════════════
        # PORTFOLIO ALLOCATION HISTORY (Phase 7)
        # ═══════════════════════════════════════════════════════════════════════════════
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_allocation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                method TEXT NOT NULL,
                regime TEXT,
                weights TEXT NOT NULL,
                risk_budget REAL,
                concentration_hhi REAL,
                realized_return REAL,
                turnover REAL,
                transaction_costs REAL,
                metadata TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_allocation_date
            ON portfolio_allocation_history(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_allocation_method
            ON portfolio_allocation_history(method)
        """)

        # ═══════════════════════════════════════════════════════════════════════════════
        # NOWCAST HISTORY (Phase 9)
        # ═══════════════════════════════════════════════════════════════════════════════
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nowcast_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                variable TEXT NOT NULL,
                nowcast_value REAL NOT NULL,
                vintage TEXT NOT NULL,
                predictors TEXT,
                confidence_lower REAL,
                confidence_upper REAL,
                regime TEXT,
                realized_value REAL,
                realized_vintage TEXT,
                forecast_error REAL,
                absolute_error REAL,
                squared_error REAL,
                revision_impact REAL,
                metadata TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nowcast_date
            ON nowcast_history(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nowcast_variable
            ON nowcast_history(variable)
        """)

        # ═══════════════════════════════════════════════════════════════════════════════
        # MOMENTUM SIGNAL HISTORY (Phase 8)
        # ═══════════════════════════════════════════════════════════════════════════════
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS momentum_signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                sector TEXT NOT NULL,
                formation_period TEXT NOT NULL,
                momentum_score REAL NOT NULL,
                lookback_return REAL,
                regime TEXT,
                realized_return REAL,
                realized_alpha REAL,
                carhart_alpha REAL,
                metadata TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_momentum_date
            ON momentum_signal_history(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_momentum_sector
            ON momentum_signal_history(sector)
        """)

        conn.commit()
        logger.info("[DB] Database initialized successfully")


def cleanup_old_logs(days: int = 30) -> None:
    """Purge data_fetch_log entries older than specified days."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM data_fetch_log
            WHERE fetched_at < datetime('now', ?)
        """, (f'-{days} days',))
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            logger.info(f"[DB] Cleaned up {deleted} old fetch log entries")


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME HISTORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def insert_regime(
    date_label: str,
    regime: str,
    confidence: float,
    growth_score: Optional[float] = None,
    inflation_score: Optional[float] = None,
    liquidity_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    raw_data: Optional[Dict] = None
) -> int:
    """Insert a new regime record. Returns the new row ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO regime_history
            (recorded_at, date_label, regime, confidence, growth_score,
             inflation_score, liquidity_score, risk_score, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            date_label,
            regime,
            confidence,
            growth_score,
            inflation_score,
            liquidity_score,
            risk_score,
            json.dumps(raw_data) if raw_data else None
        ))
        conn.commit()
        return cursor.lastrowid


def get_regime_history(limit: int = 24) -> List[Dict[str, Any]]:
    """Get regime history, most recent first."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM regime_history
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_regime_count() -> int:
    """Get total number of regime records."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM regime_history")
        return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL HISTORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def insert_signal(
    period_label: str,
    growth: Optional[float] = None,
    inflation: Optional[float] = None,
    liquidity: Optional[float] = None,
    risk: Optional[float] = None,
    recession_prob: Optional[float] = None,
    lei_zscore: Optional[float] = None,
    credit_impulse: Optional[float] = None,
    vix_norm: Optional[float] = None,
    ensemble_score: Optional[float] = None,
    risk_budget: Optional[float] = None
) -> int:
    """Insert a new signal record."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signal_history
            (recorded_at, period_label, growth, inflation, liquidity, risk,
             recession_prob, lei_zscore, credit_impulse, vix_norm,
             ensemble_score, risk_budget)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            period_label,
            growth,
            inflation,
            liquidity,
            risk,
            recession_prob,
            lei_zscore,
            credit_impulse,
            vix_norm,
            ensemble_score,
            risk_budget
        ))
        conn.commit()
        return cursor.lastrowid


def get_signal_history(limit: int = 24) -> List[Dict[str, Any]]:
    """Get signal history for LSTM training and sparklines."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signal_history
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_signal_count() -> int:
    """Get total number of signal records."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signal_history")
        return cursor.fetchone()[0]


def get_signals_for_lstm(limit: int = 24) -> List[List[float]]:
    """Get signal history formatted for LSTM training (numpy-ready)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT growth, inflation, liquidity, risk, recession_prob,
                   lei_zscore, credit_impulse, vix_norm, ensemble_score
            FROM signal_history
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        # Reverse to get chronological order
        return [list(row) for row in reversed(rows)]


# ═══════════════════════════════════════════════════════════════════════════════
# ALERT LOG OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def insert_alert(
    severity: str,
    category: str,
    title: str,
    message: str,
    action: Optional[str] = None
) -> int:
    """Insert a new alert. Returns the new alert ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alert_log
            (created_at, severity, category, title, message, action, acknowledged, dismissed)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        """, (
            datetime.utcnow().isoformat(),
            severity,
            category,
            title,
            message,
            action
        ))
        conn.commit()
        return cursor.lastrowid


def get_active_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    """Get non-dismissed alerts."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM alert_log
            WHERE dismissed = 0
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_alert_history(
    days: int = 30,
    severity: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get alert history with optional severity filter."""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()

        if severity and severity != 'all':
            cursor.execute("""
                SELECT * FROM alert_log
                WHERE created_at > ? AND severity = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (since, severity, limit))
        else:
            cursor.execute("""
                SELECT * FROM alert_log
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (since, limit))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def acknowledge_alert(alert_id: int) -> bool:
    """Mark alert as acknowledged."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE alert_log SET acknowledged = 1 WHERE id = ?",
            (alert_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def dismiss_alert(alert_id: int) -> bool:
    """Mark alert as dismissed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE alert_log SET dismissed = 1 WHERE id = ?",
            (alert_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_alert_count() -> int:
    """Get total number of alert records."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alert_log")
        return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════════════════════════
# PREDICTION LOG OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def insert_prediction(
    predicted_regime: str,
    ensemble_score: Optional[float] = None,
    model_signals: Optional[Dict] = None
) -> int:
    """Insert a new prediction."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prediction_log
            (recorded_at, predicted_regime, ensemble_score, model_signals, correct)
            VALUES (?, ?, ?, ?, NULL)
        """, (
            datetime.utcnow().isoformat(),
            predicted_regime,
            ensemble_score,
            json.dumps(model_signals) if model_signals else None
        ))
        conn.commit()
        return cursor.lastrowid


def update_prediction_result(
    prediction_id: int,
    actual_regime: str
) -> bool:
    """Update prediction with actual outcome."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get the predicted regime first
        cursor.execute(
            "SELECT predicted_regime FROM prediction_log WHERE id = ?",
            (prediction_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False

        predicted = row['predicted_regime']
        correct = 1 if predicted == actual_regime else 0

        cursor.execute("""
            UPDATE prediction_log
            SET actual_regime = ?, correct = ?
            WHERE id = ?
        """, (actual_regime, correct, prediction_id))
        conn.commit()
        return cursor.rowcount > 0


def get_prediction_history(limit: int = 100) -> List[Dict[str, Any]]:
    """Get prediction history with accuracy metrics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM prediction_log
            ORDER BY recorded_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_prediction_accuracy() -> Dict[str, Any]:
    """Get prediction accuracy statistics from signal_predictions table."""
    from pathlib import Path
    signal_db_path = Path(__file__).parent.parent / "macro_terminal.db"

    # Try signal_predictions first (new live tracker), fall back to prediction_log
    try:
        conn = sqlite3.connect(str(signal_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Extract correct from meta JSON (backfilled data stores correctness here)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN json_extract(meta, '$.correct') = 1 THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN json_extract(meta, '$.correct') IS NOT NULL THEN 1 ELSE 0 END) as evaluated
            FROM signal_predictions
            WHERE meta IS NOT NULL
        """)
        row = cursor.fetchone()
        conn.close()

        total = row['total'] or 0
        correct = row['correct'] or 0
        evaluated = row['evaluated'] or 0

        if evaluated > 0:
            accuracy = correct / evaluated
            return {
                'total_predictions': total,
                'evaluated': evaluated,
                'correct': correct,
                'accuracy': round(accuracy, 4)
            }
    except Exception as e:
        logger.debug(f"[DB] signal_predictions query failed: {e}")

    # Fall back to prediction_log (legacy table)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN correct IS NOT NULL THEN 1 ELSE 0 END) as evaluated
            FROM prediction_log
        """)
        row = cursor.fetchone()
        total = row['total'] or 0
        correct = row['correct'] or 0
        evaluated = row['evaluated'] or 0

        accuracy = correct / evaluated if evaluated > 0 else 0
        return {
            'total_predictions': total,
            'evaluated': evaluated,
            'correct': correct,
            'accuracy': round(accuracy, 4)
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO SNAPSHOT OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def insert_portfolio_snapshot(
    snapshot_date: str,
    weights: Dict[str, float],
    returns_1d: Optional[float] = None,
    cumulative_return: Optional[float] = None,
    sharpe_rolling: Optional[float] = None,
    max_drawdown: Optional[float] = None,
    regime: Optional[str] = None
) -> int:
    """Insert a portfolio snapshot."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO portfolio_snapshots
            (snapshot_date, weights, returns_1d, cumulative_return,
             sharpe_rolling, max_drawdown, regime)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_date,
            json.dumps(weights),
            returns_1d,
            cumulative_return,
            sharpe_rolling,
            max_drawdown,
            regime
        ))
        conn.commit()
        return cursor.lastrowid


def get_portfolio_history(months: int = 12) -> List[Dict[str, Any]]:
    """Get portfolio snapshots for drawdown charts."""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.utcnow() - timedelta(days=months * 30)).isoformat()
        cursor.execute("""
            SELECT * FROM portfolio_snapshots
            WHERE snapshot_date > ?
            ORDER BY snapshot_date ASC
        """, (since,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_latest_portfolio_snapshot() -> Optional[Dict[str, Any]]:
    """Get the most recent portfolio snapshot."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM portfolio_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════════════════════
# ML MODEL STATE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def save_model_weights(w_out: List[List[float]], trained_steps: int = 0) -> bool:
    """Save LSTM weights. Uses UPSERT (id=1 always)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ml_model_state (id, updated_at, w_out, trained_steps)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                w_out = excluded.w_out,
                trained_steps = excluded.trained_steps
        """, (
            datetime.utcnow().isoformat(),
            json.dumps(w_out),
            trained_steps
        ))
        conn.commit()
        return cursor.rowcount > 0


def load_model_weights() -> Optional[Dict[str, Any]]:
    """Load LSTM weights. Returns None if no weights stored."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ml_model_state WHERE id = 1")
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['w_out'] = json.loads(result['w_out'])
            return result
        return None


def get_model_training_steps() -> int:
    """Get number of training steps completed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT trained_steps FROM ml_model_state WHERE id = 1")
        row = cursor.fetchone()
        return row['trained_steps'] if row else 0


# ═══════════════════════════════════════════════════════════════════════════════
# DATA FETCH LOG OPERATIONS (AUDIT TRAIL)
# ═══════════════════════════════════════════════════════════════════════════════

def log_fetch(
    source: str,
    series_key: str,
    success: bool,
    response_time_ms: Optional[int] = None,
    error_message: Optional[str] = None
) -> int:
    """Log a data fetch operation. Thread-safe."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO data_fetch_log
                (fetched_at, source, series_key, success, error_message, response_time_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat(),
                source,
                series_key,
                1 if success else 0,
                error_message,
                response_time_ms
            ))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"[DB] Failed to log fetch: {e}")
        return -1


def log_fetch_async(
    source: str,
    series_key: str,
    success: bool,
    response_time_ms: Optional[int] = None,
    error_message: Optional[str] = None
) -> None:
    """Log a data fetch operation asynchronously (non-blocking)."""
    threading.Thread(
        target=log_fetch,
        args=(source, series_key, success, response_time_ms, error_message),
        daemon=True
    ).start()


def get_fetch_audit(hours: int = 24) -> List[Dict[str, Any]]:
    """Get fetch audit log."""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cursor.execute("""
            SELECT * FROM data_fetch_log
            WHERE fetched_at > ?
            ORDER BY fetched_at DESC
        """, (since,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_fetch_summary(hours: int = 24) -> Dict[str, Any]:
    """Get summary statistics for data fetches."""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(response_time_ms) as avg_response_time,
                MAX(response_time_ms) as max_response_time
            FROM data_fetch_log
            WHERE fetched_at > ?
        """, (since,))

        row = cursor.fetchone()
        total = row['total'] or 0
        successful = row['successful'] or 0

        return {
            'total_fetches': total,
            'successful': successful,
            'failed': total - successful,
            'success_rate': round(successful / total, 4) if total > 0 else 0,
            'avg_response_time_ms': round(row['avg_response_time'], 2) if row['avg_response_time'] else 0,
            'max_response_time_ms': row['max_response_time'] or 0,
            'period_hours': hours
        }


def get_fetch_stats_by_source(hours: int = 24) -> List[Dict[str, Any]]:
    """Get fetch statistics grouped by source."""
    with get_db() as conn:
        cursor = conn.cursor()
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        cursor.execute("""
            SELECT
                source,
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(response_time_ms) as avg_response_time
            FROM data_fetch_log
            WHERE fetched_at > ?
            GROUP BY source
            ORDER BY total DESC
        """, (since,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# FORECAST HISTORY OPERATIONS (Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

def insert_forecast(
    model_name: str,
    forecast_date: str,
    horizon: Optional[str] = None,
    predicted_value: Optional[float] = None,
    predicted_class: Optional[str] = None,
    confidence_lower: Optional[float] = None,
    confidence_upper: Optional[float] = None,
    model_version: Optional[str] = None,
    model_params: Optional[Dict] = None,
    features_used: Optional[List[str]] = None
) -> int:
    """
    Insert a new forecast record.

    Args:
        model_name: e.g., 'regime_threshold', 'regime_hmm', 'recession_ensemble'
        forecast_date: The date being forecasted (ISO format)
        horizon: Forecast horizon ('1M', '3M', '6M', '12M', 'current')
        predicted_value: Numeric prediction (e.g., GDP growth, probability)
        predicted_class: Categorical prediction (e.g., 'Goldilocks', 'Recession')
        confidence_lower: Lower bound of confidence interval
        confidence_upper: Upper bound of confidence interval
        model_version: Version string of the model
        model_params: Dictionary of model hyperparameters
        features_used: List of feature names used

    Returns:
        The new forecast ID
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO forecast_history
            (model_name, forecast_timestamp, forecast_date, horizon,
             predicted_value, predicted_class, confidence_lower, confidence_upper,
             model_version, model_params, features_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            model_name,
            datetime.utcnow().isoformat(),
            forecast_date,
            horizon,
            predicted_value,
            predicted_class,
            confidence_lower,
            confidence_upper,
            model_version,
            json.dumps(model_params) if model_params else None,
            json.dumps(features_used) if features_used else None
        ))
        conn.commit()
        return cursor.lastrowid


def update_forecast_realized(
    forecast_id: int,
    realized_value: Optional[float] = None,
    realized_class: Optional[str] = None
) -> bool:
    """
    Update a forecast with its realized outcome.

    Automatically computes forecast_error, absolute_error, squared_error,
    and directional_hit if predicted_value and realized_value are both present.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Get the original forecast
        cursor.execute("""
            SELECT predicted_value, predicted_class
            FROM forecast_history WHERE id = ?
        """, (forecast_id,))
        row = cursor.fetchone()
        if not row:
            return False

        predicted_value = row['predicted_value']
        predicted_class = row['predicted_class']

        # Compute error metrics
        forecast_error = None
        absolute_error = None
        squared_error = None
        directional_hit = None

        if predicted_value is not None and realized_value is not None:
            forecast_error = realized_value - predicted_value
            absolute_error = abs(forecast_error)
            squared_error = forecast_error ** 2

            # Directional hit: did we get the sign right?
            if predicted_value != 0:
                pred_sign = 1 if predicted_value > 0 else -1 if predicted_value < 0 else 0
                real_sign = 1 if realized_value > 0 else -1 if realized_value < 0 else 0
                if pred_sign != 0 and real_sign != 0:
                    directional_hit = 1 if pred_sign == real_sign else 0

        # Also check class prediction
        if predicted_class and realized_class and directional_hit is None:
            directional_hit = 1 if predicted_class == realized_class else 0

        cursor.execute("""
            UPDATE forecast_history
            SET realized_value = ?,
                realized_class = ?,
                realized_timestamp = ?,
                forecast_error = ?,
                absolute_error = ?,
                squared_error = ?,
                directional_hit = ?
            WHERE id = ?
        """, (
            realized_value,
            realized_class,
            datetime.utcnow().isoformat(),
            forecast_error,
            absolute_error,
            squared_error,
            directional_hit,
            forecast_id
        ))
        conn.commit()
        return cursor.rowcount > 0


def get_forecast_history(
    model_name: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get forecast history with optional filtering."""
    with get_db() as conn:
        cursor = conn.cursor()

        if model_name and horizon:
            cursor.execute("""
                SELECT * FROM forecast_history
                WHERE model_name = ? AND horizon = ?
                ORDER BY forecast_timestamp DESC
                LIMIT ?
            """, (model_name, horizon, limit))
        elif model_name:
            cursor.execute("""
                SELECT * FROM forecast_history
                WHERE model_name = ?
                ORDER BY forecast_timestamp DESC
                LIMIT ?
            """, (model_name, limit))
        else:
            cursor.execute("""
                SELECT * FROM forecast_history
                ORDER BY forecast_timestamp DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('model_params'):
                d['model_params'] = json.loads(d['model_params'])
            if d.get('features_used'):
                d['features_used'] = json.loads(d['features_used'])
            result.append(d)
        return result


def get_forecasts_without_realized(
    model_name: Optional[str] = None,
    before_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get forecasts that need realized values backfilled.

    Useful for batch updating forecasts once actual data becomes available.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        query = """
            SELECT * FROM forecast_history
            WHERE realized_value IS NULL AND realized_class IS NULL
        """
        params = []

        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)

        if before_date:
            query += " AND forecast_date < ?"
            params.append(before_date)

        query += " ORDER BY forecast_date ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def compute_forecast_accuracy(model_name: str, horizon: Optional[str] = None) -> Dict[str, Any]:
    """
    Compute accuracy metrics for a model.

    Returns:
        Dictionary with MAE, RMSE, directional accuracy, and count.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        query = """
            SELECT
                COUNT(*) as total,
                COUNT(realized_value) as evaluated,
                AVG(absolute_error) as mae,
                AVG(squared_error) as mse,
                AVG(CASE WHEN directional_hit IS NOT NULL THEN directional_hit END) as directional_accuracy,
                AVG(realized_value - predicted_value) as bias
            FROM forecast_history
            WHERE model_name = ? AND realized_value IS NOT NULL
        """
        params = [model_name]

        if horizon:
            query += " AND horizon = ?"
            params.append(horizon)

        cursor.execute(query, params)
        row = cursor.fetchone()

        total = row['total'] or 0
        evaluated = row['evaluated'] or 0
        mae = row['mae']
        mse = row['mse']
        rmse = mse ** 0.5 if mse else None
        directional = row['directional_accuracy']
        bias = row['bias']

        return {
            'model_name': model_name,
            'horizon': horizon,
            'total_forecasts': total,
            'evaluated': evaluated,
            'mae': round(mae, 4) if mae else None,
            'rmse': round(rmse, 4) if rmse else None,
            'directional_accuracy': round(directional, 4) if directional else None,
            'bias': round(bias, 4) if bias else None,
        }


def get_forecast_count() -> int:
    """Get total number of forecast records."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM forecast_history")
        return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def get_db_status() -> Dict[str, Any]:
    """Get overall database status summary."""
    return {
        'regime_records': get_regime_count(),
        'signal_records': get_signal_count(),
        'alert_records': get_alert_count(),
        'predictions': get_prediction_accuracy(),
        'forecast_records': get_forecast_count(),
        'fetch_summary': get_fetch_summary(hours=24),
        'db_path': str(DB_PATH),
        'db_exists': DB_PATH.exists()
    }


# Initialize on module import
init_db()
cleanup_old_logs(days=30)
