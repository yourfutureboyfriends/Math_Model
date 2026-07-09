"""
Signal Stack Validation Service — Phase 3: Calibrate 8-layer signal hierarchy.

Validates each layer's contribution to final signal:
1. Correlation with forward returns
2. Information Coefficient (rank correlation)
3. Hit rate (sign prediction accuracy)
4. Layer contribution analysis
5. Override threshold calibration
6. Dead layer detection

Usage:
    from api.services.signal_validation import signal_validator

    # Log signal stack
    signal_validator.log_signal_stack(
        date="2024-01-15",
        layers={
            1: {"value": "Goldilocks", "confidence": 0.7},
            2: {"value": "0.45", "confidence": 0.8},
            # ... all 8 layers
        },
        final_signal="DEFENSIVE"
    )

    # Analyze layer contribution
    contributions = signal_validator.compute_layer_contribution()

    # Get recommendations
    recommendations = signal_validator.get_calibration_recommendations()
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json

import numpy as np
import pandas as pd

from database.db import get_db

logger = logging.getLogger(__name__)


class SignalLayer(Enum):
    """Signal stack layers (from MODEL_INVENTORY)."""
    REGIME_NOWCAST = 1
    RECESSION = 2
    LIQUIDITY = 3
    SENTIMENT = 4
    VALUATION = 5
    SECTOR = 6
    GEOPOLITICAL = 7
    OPTIONS = 8


@dataclass
class LayerMetrics:
    """Metrics for a single signal layer."""
    layer_id: int
    layer_name: str
    correlation: Optional[float] = None
    rank_correlation: Optional[float] = None  # Information Coefficient
    hit_rate: Optional[float] = None
    n_predictions: int = 0
    n_evaluated: int = 0
    contribution_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OverrideAnalysis:
    """Analysis of override triggers."""
    trigger_name: str
    trigger_count: int
    true_positive: int
    false_positive: int
    precision: Optional[float] = None
    calibration_recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalValidator:
    """
    Validation service for signal stack calibration.

    Tracks historical performance of each layer and identifies:
    - Layers with negative contribution (candidates for removal)
    - Override thresholds needing calibration
    - Layer reliability scores for Bayesian weighting
    """

    LAYER_NAMES = {
        1: "Regime + Nowcast",
        2: "Recession Probability",
        3: "Liquidity + FCI",
        4: "Sentiment + Momentum",
        5: "Valuation Filter",
        6: "Sector Output",
        7: "Geopolitical Risk",
        8: "Options Intelligence",
    }

    LAYER_KEYS = {
        1: "regime_nowcast",
        2: "recession",
        3: "liquidity",
        4: "sentiment",
        5: "valuation",
        6: "sector",
        7: "geopolitical",
        8: "options",
    }

    # Override thresholds from MODEL_INVENTORY
    OVERRIDE_THRESHOLDS = {
        "recession_prob": 0.60,
        "liquidity_stress": -1.0,
        "sentiment_divergence": 0.50,
        "valuation_stretched": "STRETCHED",
    }

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._layer_reliability: Dict[int, float] = {}

    def log_signal_stack(
        self,
        date: str,
        layers: Dict[int, Dict[str, Any]],
        final_signal: str,
        risk_budget: float,
        overrides_active: List[str],
        market_return_1m: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log complete signal stack for a given date.

        Args:
            date: ISO format date string
            layers: Dict mapping layer_id -> {value, confidence, override_flag}
            final_signal: Final aggregated signal
            risk_budget: Risk budget output (0-1)
            overrides_active: List of active override names
            market_return_1m: Actual market return 1 month forward (for validation)
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure signal_stack_history table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_stack_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        layer_1_value TEXT,
                        layer_1_confidence REAL,
                        layer_2_value TEXT,
                        layer_2_confidence REAL,
                        layer_3_value TEXT,
                        layer_3_confidence REAL,
                        layer_4_value TEXT,
                        layer_4_confidence REAL,
                        layer_5_value TEXT,
                        layer_5_confidence REAL,
                        layer_6_value TEXT,
                        layer_6_confidence REAL,
                        layer_7_value TEXT,
                        layer_7_confidence REAL,
                        layer_8_value TEXT,
                        layer_8_confidence REAL,
                        final_signal TEXT,
                        risk_budget REAL,
                        overrides_active TEXT,
                        market_return_1m REAL,
                        metadata TEXT
                    )
                """)

                cursor.execute("""
                    INSERT INTO signal_stack_history (
                        date, recorded_at,
                        layer_1_value, layer_1_confidence,
                        layer_2_value, layer_2_confidence,
                        layer_3_value, layer_3_confidence,
                        layer_4_value, layer_4_confidence,
                        layer_5_value, layer_5_confidence,
                        layer_6_value, layer_6_confidence,
                        layer_7_value, layer_7_confidence,
                        layer_8_value, layer_8_confidence,
                        final_signal, risk_budget, overrides_active,
                        market_return_1m, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    datetime.utcnow().isoformat(),
                    layers.get(1, {}).get('value'),
                    layers.get(1, {}).get('confidence'),
                    layers.get(2, {}).get('value'),
                    layers.get(2, {}).get('confidence'),
                    layers.get(3, {}).get('value'),
                    layers.get(3, {}).get('confidence'),
                    layers.get(4, {}).get('value'),
                    layers.get(4, {}).get('confidence'),
                    layers.get(5, {}).get('value'),
                    layers.get(5, {}).get('confidence'),
                    layers.get(6, {}).get('value'),
                    layers.get(6, {}).get('confidence'),
                    layers.get(7, {}).get('value'),
                    layers.get(7, {}).get('confidence'),
                    layers.get(8, {}).get('value'),
                    layers.get(8, {}).get('confidence'),
                    final_signal,
                    risk_budget,
                    json.dumps(overrides_active) if overrides_active else None,
                    market_return_1m,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(f"[SignalValidator] Logged signal stack for {date} (id={log_id})")
                return log_id

        except Exception as e:
            self._logger.error(f"[SignalValidator] Failed to log signal stack: {e}")
            raise

    def get_signal_stack_history(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Retrieve signal stack history as DataFrame.

        Args:
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum records

        Returns:
            DataFrame with signal stack history
        """
        try:
            with get_db() as conn:
                query = """
                    SELECT * FROM signal_stack_history
                    WHERE 1=1
                """
                params = []

                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date)

                query += " ORDER BY date DESC LIMIT ?"
                params.append(limit)

                df = pd.read_sql_query(query, conn, params=params)
                return df

        except Exception as e:
            self._logger.error(f"[SignalValidator] Failed to get history: {e}")
            return pd.DataFrame()

    def compute_layer_metrics(
        self,
        layer_id: int,
        min_observations: int = 12
    ) -> Optional[LayerMetrics]:
        """
        Compute validation metrics for a single layer.

        Args:
            layer_id: Layer number (1-8)
            min_observations: Minimum observations required

        Returns:
            LayerMetrics or None if insufficient data
        """
        df = self.get_signal_stack_history(limit=500)

        if len(df) < min_observations:
            return None

        if 'market_return_1m' not in df.columns or df['market_return_1m'].isna().all():
            return LayerMetrics(
                layer_id=layer_id,
                layer_name=self.LAYER_NAMES.get(layer_id, f"Layer {layer_id}"),
                n_predictions=len(df),
                n_evaluated=0
            )

        # Get layer value column
        value_col = f'layer_{layer_id}_value'
        if value_col not in df.columns:
            return None

        # Filter to rows with realized returns
        df_valid = df.dropna(subset=['market_return_1m', value_col])

        if len(df_valid) < min_observations:
            return LayerMetrics(
                layer_id=layer_id,
                layer_name=self.LAYER_NAMES.get(layer_id, f"Layer {layer_id}"),
                n_predictions=len(df),
                n_evaluated=len(df_valid)
            )

        # Convert layer values to numeric signals
        signals = self._layer_value_to_signal(df_valid[value_col], layer_id)
        returns = df_valid['market_return_1m'].astype(float)

        # Compute metrics
        correlation = signals.corr(returns)

        # Rank correlation (Information Coefficient)
        try:
            rank_corr = signals.corr(returns, method='spearman')
        except (ValueError, TypeError):
            # Correlation fails with insufficient data or type mismatch
            rank_corr = None

        # Hit rate (correct directional prediction)
        signal_direction = np.sign(signals)
        return_direction = np.sign(returns)
        hits = (signal_direction == return_direction).sum()
        hit_rate = hits / len(signals) if len(signals) > 0 else None

        # Contribution score: correlation weighted by hit rate
        contribution = (correlation * hit_rate) if hit_rate else correlation

        return LayerMetrics(
            layer_id=layer_id,
            layer_name=self.LAYER_NAMES.get(layer_id, f"Layer {layer_id}"),
            correlation=round(correlation, 4) if not np.isnan(correlation) else None,
            rank_correlation=round(rank_corr, 4) if rank_corr and not np.isnan(rank_corr) else None,
            hit_rate=round(hit_rate, 4) if hit_rate else None,
            n_predictions=len(df),
            n_evaluated=len(df_valid),
            contribution_score=round(contribution, 4) if not np.isnan(contribution) else None
        )

    def _layer_value_to_signal(
        self,
        values: pd.Series,
        layer_id: int
    ) -> pd.Series:
        """Convert layer values to numeric signals (-1, 0, 1)."""
        if layer_id == 1:  # Regime
            mapping = {
                'Goldilocks': 1.0,
                'Reflation': 0.5,
                'Slowdown': -0.5,
                'Stagflation': -1.0,
            }
            return values.map(lambda x: mapping.get(str(x), 0.0))

        elif layer_id == 2:  # Recession probability
            # Convert "45%" or "0.45" to signal
            def parse_recession(val):
                if pd.isna(val):
                    return 0.0
                try:
                    if isinstance(val, str) and '%' in val:
                        prob = float(val.replace('%', '')) / 100
                    else:
                        prob = float(val)
                    return -1.0 if prob > 0.60 else 0.0
                except (ValueError, TypeError):
                    return 0.0
            return values.apply(parse_recession)

        elif layer_id == 3:  # Liquidity
            # Parse "+0.50" or "-0.30"
            def parse_liquidity(val):
                if pd.isna(val):
                    return 0.0
                try:
                    num = float(str(val).replace('+', ''))
                    return 1.0 if num > 0 else -1.0 if num < -1.0 else num
                except (ValueError, TypeError):
                    return 0.0
            return values.apply(parse_liquidity)

        elif layer_id == 4:  # Sentiment
            mapping = {
                'RISK_ON': 1.0,
                'BULLISH': 1.0,
                'NEUTRAL': 0.0,
                'RISK_OFF': -1.0,
                'BEARISH': -1.0,
            }
            return values.map(lambda x: mapping.get(str(x).upper(), 0.0))

        elif layer_id == 5:  # Valuation
            mapping = {
                'CHEAP': 1.0,
                'FAIR': 0.0,
                'EXPENSIVE': -0.5,
                'STRETCHED': -1.0,
            }
            return values.map(lambda x: mapping.get(str(x).upper(), 0.0))

        elif layer_id == 6:  # Sector
            mapping = {
                'BULLISH': 1.0,
                'NEUTRAL': 0.0,
                'BEARISH': -1.0,
            }
            return values.map(lambda x: mapping.get(str(x).upper(), 0.0))

        elif layer_id == 7:  # Geopolitical
            mapping = {
                'NORMAL': 0.0,
                'ELEVATED': -0.5,
                'CRITICAL': -1.0,
            }
            return values.map(lambda x: mapping.get(str(x).upper(), 0.0))

        elif layer_id == 8:  # Options
            mapping = {
                'EXTREME_FEAR': 1.0,  # Contrarian buy
                'FEAR': 0.5,
                'NEUTRAL': 0.0,
                'GREED': -0.5,
                'EXTREME_GREED': -1.0,  # Contrarian sell
            }
            return values.map(lambda x: mapping.get(str(x).upper(), 0.0))

        return pd.Series([0.0] * len(values))

    def compute_all_layer_metrics(self) -> List[LayerMetrics]:
        """Compute metrics for all 8 layers."""
        metrics = []
        for layer_id in range(1, 9):
            m = self.compute_layer_metrics(layer_id)
            if m:
                metrics.append(m)
        return metrics

    def analyze_override_performance(
        self,
        override_name: str,
        min_triggers: int = 5
    ) -> Optional[OverrideAnalysis]:
        """
        Analyze performance of a specific override trigger.

        Args:
            override_name: Name of override to analyze
            min_triggers: Minimum triggers required

        Returns:
            OverrideAnalysis or None
        """
        df = self.get_signal_stack_history(limit=500)

        if 'overrides_active' not in df.columns or 'market_return_1m' not in df.columns:
            return None

        # Parse overrides_active JSON
        df['has_override'] = df['overrides_active'].apply(
            lambda x: override_name in json.loads(x) if x else False
        )

        triggered = df[df['has_override'] == True]

        if len(triggered) < min_triggers:
            return OverrideAnalysis(
                trigger_name=override_name,
                trigger_count=len(triggered),
                true_positive=0,
                false_positive=0,
                calibration_recommendation="Insufficient data for calibration"
            )

        # Evaluate: override should predict negative returns
        triggered_returns = triggered['market_return_1m'].dropna()

        if len(triggered_returns) == 0:
            return None

        # True positive: override triggered AND returns were negative
        true_pos = (triggered_returns < 0).sum()
        false_pos = (triggered_returns >= 0).sum()
        precision = true_pos / len(triggered_returns) if len(triggered_returns) > 0 else 0

        # Recommendation
        if precision < 0.5:
            rec = f"Threshold too sensitive - consider raising threshold"
        elif precision > 0.8:
            rec = f"Threshold well calibrated"
        else:
            rec = f"Consider fine-tuning threshold"

        return OverrideAnalysis(
            trigger_name=override_name,
            trigger_count=len(triggered),
            true_positive=int(true_pos),
            false_positive=int(false_pos),
            precision=round(precision, 4),
            calibration_recommendation=rec
        )

    def get_dead_layers(self, contribution_threshold: float = 0.0) -> List[int]:
        """
        Identify layers with negative or minimal contribution.

        Args:
            contribution_threshold: Minimum acceptable contribution

        Returns:
            List of layer IDs with contribution <= threshold
        """
        dead_layers = []
        for layer_id in range(1, 9):
            metrics = self.compute_layer_metrics(layer_id)
            if metrics and metrics.contribution_score is not None:
                if metrics.contribution_score <= contribution_threshold:
                    dead_layers.append(layer_id)
        return dead_layers

    def get_calibration_recommendations(self) -> Dict[str, Any]:
        """
        Generate calibration recommendations based on analysis.

        Returns:
            Dict with recommendations for layers and overrides
        """
        recommendations = {
            "timestamp": datetime.utcnow().isoformat(),
            "layer_recommendations": [],
            "override_recommendations": [],
            "dead_layers": [],
            "reliability_scores": {}
        }

        # Analyze each layer
        for layer_id in range(1, 9):
            metrics = self.compute_layer_metrics(layer_id)
            if not metrics:
                continue

            # Layer reliability for Bayesian weighting
            if metrics.hit_rate:
                recommendations["reliability_scores"][self.LAYER_KEYS[layer_id]] = round(metrics.hit_rate, 4)

            # Check for dead layers
            if metrics.contribution_score is not None and metrics.contribution_score <= 0:
                recommendations["dead_layers"].append({
                    "layer_id": layer_id,
                    "layer_name": self.LAYER_NAMES.get(layer_id),
                    "contribution_score": metrics.contribution_score,
                    "recommendation": "Consider removing or revising layer logic"
                })

            # Check for low correlation
            if metrics.correlation is not None and abs(metrics.correlation) < 0.1:
                recommendations["layer_recommendations"].append({
                    "layer_id": layer_id,
                    "layer_name": self.LAYER_NAMES.get(layer_id),
                    "issue": "Low correlation with forward returns",
                    "correlation": metrics.correlation,
                    "recommendation": "Review layer logic or consider removal"
                })

            # Check for low hit rate
            if metrics.hit_rate is not None and metrics.hit_rate < 0.5:
                recommendations["layer_recommendations"].append({
                    "layer_id": layer_id,
                    "layer_name": self.LAYER_NAMES.get(layer_id),
                    "issue": "Below-random hit rate",
                    "hit_rate": metrics.hit_rate,
                    "recommendation": "Layer may be inverted - check signal direction"
                })

        # Analyze overrides
        for override_name in ["Recession probability > 60%", "Liquidity stress", "Sentiment-regime divergence"]:
            analysis = self.analyze_override_performance(override_name)
            if analysis:
                recommendations["override_recommendations"].append(analysis.to_dict())

        return recommendations

    def get_bayesian_weights(self) -> Dict[str, float]:
        """
        Get layer weights for Bayesian aggregation based on historical accuracy.

        Returns:
            Dict mapping layer key to reliability weight
        """
        weights = {}
        for layer_id in range(1, 9):
            metrics = self.compute_layer_metrics(layer_id)
            if metrics and metrics.hit_rate:
                weights[self.LAYER_KEYS[layer_id]] = round(metrics.hit_rate, 4)
            else:
                weights[self.LAYER_KEYS[layer_id]] = 0.5  # Default weight
        return weights

    def update_realized_returns(
        self,
        date: str,
        market_return_1m: float
    ) -> bool:
        """
        Backfill realized returns for a historical signal stack entry.

        Args:
            date: Date of signal
            market_return_1m: Actual 1-month market return

        Returns:
            True if update successful
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE signal_stack_history
                    SET market_return_1m = ?
                    WHERE date = ?
                """, (market_return_1m, date))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self._logger.error(f"[SignalValidator] Failed to update returns: {e}")
            return False


# Global instance
signal_validator = SignalValidator()
