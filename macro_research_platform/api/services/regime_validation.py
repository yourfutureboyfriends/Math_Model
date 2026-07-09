"""
Regime Validation Service — Phase 2: Validate and calibrate regime classifiers.

Validates both threshold-based and HMM regime classification methods:
1. Regime persistence metrics (excessive flipping detection)
2. Threshold grid search [0.05, 0.10, 0.15, 0.20]
3. Threshold vs HMM comparison on historical data
4. Arbitration rule for method selection

Usage:
    from api.services.regime_validation import regime_validator

    # Run threshold optimization
    results = regime_validator.optimize_threshold(
        df=macro_data,
        thresholds=[0.05, 0.10, 0.15, 0.20]
    )

    # Compare methods
    comparison = regime_validator.compare_methods(df=macro_data)

    # Get arbitration decision
    method = regime_validator.select_method(
        hmm_available=True,
        hmm_confidence=0.75,
        data_length_months=36
    )
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json

import numpy as np
import pandas as pd

# Avoid direct imports from HMM to handle optional dependency
try:
    from api.models_ml.regime_hmm import MacroRegimeHMM, get_regime_hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

logger = logging.getLogger(__name__)


class Regime(Enum):
    """Four macro regimes."""
    GOLDILOCKS = "Goldilocks"
    REFLATION = "Reflation"
    STAGFLATION = "Stagflation"
    SLOWDOWN = "Slowdown"


@dataclass
class ThresholdOptimizationResult:
    """Result of threshold grid search."""
    optimal_threshold: float
    all_results: List[Dict[str, Any]]
    metric: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegimePersistenceMetrics:
    """Metrics for regime persistence analysis."""
    regime: str
    n_episodes: int
    avg_duration_months: float
    median_duration: float
    min_duration: int
    max_duration: int
    total_months: int
    pct_of_time: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MethodComparisonResult:
    """Comparison between threshold and HMM methods."""
    threshold: str
    hmm_regime: str
    agreement: bool
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RegimeValidator:
    """
    Validation service for regime classification models.

    Provides:
    - Threshold optimization via grid search
    - Regime persistence metrics (detect excessive flipping)
    - Threshold vs HMM comparison
    - Arbitration rule for method selection
    """

    DEFAULT_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25]
    MIN_PERSISTENCE_MONTHS = 3  # Minimum desirable regime duration

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._optimal_threshold: Optional[float] = None
        self._threshold_grid_results: Optional[List[Dict]] = None

    def classify_with_threshold(
        self,
        growth_score: float,
        inflation_score: float,
        threshold: float = 0.10
    ) -> Regime:
        """
        Classify regime using threshold-based 2x2 matrix.

        Args:
            growth_score: Normalized growth score (-1 to 1)
            inflation_score: Normalized inflation score (-1 to 1)
            threshold: Classification threshold (default 0.10)

        Returns:
            Regime classification
        """
        # High growth
        if growth_score > threshold:
            # Low inflation = Goldilocks, High inflation = Reflation
            if inflation_score > threshold:
                return Regime.GOLDILOCKS
            else:
                return Regime.REFLATION
        # Low growth
        else:
            # Low inflation = Slowdown, High inflation = Stagflation
            if inflation_score > threshold:
                return Regime.SLOWDOWN
            else:
                return Regime.STAGFLATION

    def compute_regime_series(
        self,
        df: pd.DataFrame,
        threshold: float = 0.10,
        direction_window: int = 3
    ) -> pd.Series:
        """
        Compute regime classification for all dates in DataFrame.

        Args:
            df: DataFrame with growth_score and inflation_score columns
            threshold: Classification threshold
            direction_window: Months to look back for direction

        Returns:
            Series of regime classifications
        """
        if 'growth_score' not in df.columns or 'inflation_score' not in df.columns:
            raise ValueError("DataFrame must contain 'growth_score' and 'inflation_score' columns")

        regimes = []
        for i in range(len(df)):
            if i < direction_window:
                regimes.append(None)
                continue

            g_now = df['growth_score'].iloc[i]
            g_past = df['growth_score'].iloc[i - direction_window]
            i_now = df['inflation_score'].iloc[i]
            i_past = df['inflation_score'].iloc[i - direction_window]

            # Compute direction
            g_dir = g_now - g_past
            i_dir = i_now - i_past

            # Classify based on direction and threshold
            if g_dir > threshold:
                if i_dir > threshold:
                    regime = Regime.GOLDILOCKS
                elif i_dir < -threshold:
                    regime = Regime.REFLATION
                else:
                    regime = Regime.GOLDILOCKS  # Default when inflation stable
            elif g_dir < -threshold:
                if i_dir > threshold:
                    regime = Regime.STAGFLATION
                elif i_dir < -threshold:
                    regime = Regime.SLOWDOWN
                else:
                    regime = Regime.SLOWDOWN  # Default when inflation stable
            else:
                # Growth stable - look at inflation only
                if i_dir > threshold:
                    regime = Regime.STAGFLATION
                elif i_dir < -threshold:
                    regime = Regime.SLOWDOWN
                else:
                    # Both stable - use absolute levels
                    if g_now > 0:
                        regime = Regime.GOLDILOCKS if i_now < 0 else Regime.REFLATION
                    else:
                        regime = Regime.SLOWDOWN if i_now < 0 else Regime.STAGFLATION

            regimes.append(regime.value if isinstance(regime, Regime) else regime)

        return pd.Series(regimes, index=df.index, name='regime')

    def compute_persistence_metrics(
        self,
        regime_series: pd.Series
    ) -> List[RegimePersistenceMetrics]:
        """
        Compute regime persistence metrics (duration statistics).

        Args:
            regime_series: Series of regime classifications

        Returns:
            List of persistence metrics per regime
        """
        regimes = regime_series.dropna()

        if len(regimes) < 6:
            return []

        # Identify regime runs
        current_regime = regimes.iloc[0]
        current_start = 0
        runs = []

        for i in range(1, len(regimes)):
            if regimes.iloc[i] != current_regime:
                runs.append({
                    'regime': current_regime,
                    'duration': i - current_start,
                    'start_idx': current_start,
                    'end_idx': i - 1,
                })
                current_regime = regimes.iloc[i]
                current_start = i

        # Add final run
        runs.append({
            'regime': current_regime,
            'duration': len(regimes) - current_start,
            'start_idx': current_start,
            'end_idx': len(regimes) - 1,
        })

        runs_df = pd.DataFrame(runs)

        # Compute statistics by regime
        metrics = []
        for regime in runs_df['regime'].unique():
            regime_runs = runs_df[runs_df['regime'] == regime]

            metrics.append(RegimePersistenceMetrics(
                regime=str(regime),
                n_episodes=int(len(regime_runs)),
                avg_duration_months=float(regime_runs['duration'].mean()),
                median_duration=float(regime_runs['duration'].median()),
                min_duration=int(regime_runs['duration'].min()),
                max_duration=int(regime_runs['duration'].max()),
                total_months=int(regime_runs['duration'].sum()),
                pct_of_time=float(regime_runs['duration'].sum() / len(regimes) * 100)
            ))

        return metrics

    def compute_transition_matrix(
        self,
        regime_series: pd.Series
    ) -> pd.DataFrame:
        """
        Compute regime transition probability matrix.

        Args:
            regime_series: Series of regime classifications

        Returns:
            DataFrame with transition probabilities
        """
        regimes = regime_series.dropna()

        if len(regimes) < 12:
            return pd.DataFrame()

        all_regimes = ['Goldilocks', 'Reflation', 'Slowdown', 'Stagflation']
        transitions = pd.DataFrame(
            0,
            index=all_regimes,
            columns=all_regimes
        )

        # Count transitions
        for i in range(1, len(regimes)):
            prev_regime = regimes.iloc[i - 1]
            curr_regime = regimes.iloc[i]

            if prev_regime in transitions.index and curr_regime in transitions.columns:
                transitions.loc[prev_regime, curr_regime] += 1

        # Convert to probabilities (row sums to 1)
        transition_probs = transitions.div(transitions.sum(axis=1), axis=0).fillna(0)

        return transition_probs

    def count_excessive_switches(
        self,
        regime_series: pd.Series,
        min_persistence: int = 2
    ) -> Dict[str, Any]:
        """
        Count regimes that switch too quickly (choppiness detection).

        Args:
            regime_series: Series of regime classifications
            min_persistence: Minimum desirable regime duration in months

        Returns:
            Dict with switch counts and problematic periods
        """
        regimes = regime_series.dropna()

        if len(regimes) < 6:
            return {'total_switches': 0, 'excessive_switches': 0, 'choppiness_score': 0}

        switches = 0
        excessive_switches = 0
        short_regimes = []

        # Track runs
        current_regime = regimes.iloc[0]
        current_start = 0

        for i in range(1, len(regimes)):
            if regimes.iloc[i] != current_regime:
                duration = i - current_start
                switches += 1

                if duration < min_persistence:
                    excessive_switches += 1
                    short_regimes.append({
                        'regime': current_regime,
                        'duration': duration,
                        'start': current_start,
                        'end': i - 1
                    })

                current_regime = regimes.iloc[i]
                current_start = i

        # Add final run
        final_duration = len(regimes) - current_start
        if final_duration < min_persistence:
            short_regimes.append({
                'regime': current_regime,
                'duration': final_duration,
                'start': current_start,
                'end': len(regimes) - 1
            })

        # Choppiness score: % of regimes that are too short
        total_regimes = len(short_regimes) + (switches - excessive_switches) + 1
        choppiness = excessive_switches / total_regimes if total_regimes > 0 else 0

        return {
            'total_switches': switches,
            'excessive_switches': excessive_switches,
            'choppiness_score': round(choppiness, 4),
            'short_regimes': short_regimes,
            'avg_switch_frequency': switches / len(regimes) if len(regimes) > 0 else 0
        }

    def optimize_threshold(
        self,
        df: pd.DataFrame,
        thresholds: Optional[List[float]] = None,
        optimization_metric: str = 'persistence'
    ) -> ThresholdOptimizationResult:
        """
        Grid search to find optimal threshold.

        Args:
            df: DataFrame with growth_score and inflation_score
            thresholds: List of thresholds to test (default: [0.05, 0.10, 0.15, 0.20, 0.25])
            optimization_metric: 'persistence' (maximize) or 'choppiness' (minimize)

        Returns:
            ThresholdOptimizationResult with optimal threshold and all results
        """
        if thresholds is None:
            thresholds = self.DEFAULT_THRESHOLDS

        results = []

        for threshold in thresholds:
            # Compute regime series with this threshold
            regime_series = self.compute_regime_series(df, threshold=threshold)

            # Compute metrics
            persistence = self.compute_persistence_metrics(regime_series)
            avg_duration = np.mean([p.avg_duration_months for p in persistence]) if persistence else 0
            switches = self.count_excessive_switches(regime_series, min_persistence=2)

            results.append({
                'threshold': threshold,
                'avg_duration_months': round(avg_duration, 2),
                'total_switches': switches['total_switches'],
                'excessive_switches': switches['excessive_switches'],
                'choppiness_score': switches['choppiness_score'],
                'regime_distribution': {p.regime: p.pct_of_time for p in persistence}
            })

        # Find optimal threshold based on metric
        if optimization_metric == 'persistence':
            # Maximize average duration
            best = max(results, key=lambda x: x['avg_duration_months'])
        else:
            # Minimize choppiness
            best = min(results, key=lambda x: x['choppiness_score'])

        self._optimal_threshold = best['threshold']
        self._threshold_grid_results = results

        self._logger.info(
            f"[RegimeValidator] Optimal threshold: {best['threshold']} "
            f"(avg duration: {best['avg_duration_months']:.2f} months)"
        )

        return ThresholdOptimizationResult(
            optimal_threshold=best['threshold'],
            all_results=results,
            metric=optimization_metric
        )

    def get_optimal_threshold(self) -> Optional[float]:
        """Return the optimal threshold from last optimization run."""
        return self._optimal_threshold

    def compare_methods_historical(
        self,
        df: pd.DataFrame,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compare threshold vs HMM methods on historical data.

        Args:
            df: DataFrame with macro features
            threshold: Threshold to use (uses optimal if not specified)

        Returns:
            Comparison metrics including agreement rate and persistence
        """
        if threshold is None:
            threshold = self._optimal_threshold or 0.10

        # Get threshold-based regimes
        threshold_regimes = self.compute_regime_series(df, threshold=threshold)

        # Get HMM regimes (if available)
        hmm_regimes = None
        hmm_trained = False

        if HMM_AVAILABLE:
            try:
                hmm_model = MacroRegimeHMM()
                feature_df = self._prepare_hmm_features(df)

                if len(feature_df) >= 24:
                    hmm_model.fit(feature_df)
                    hmm_sequence = hmm_model.get_historical_sequence(feature_df)
                    hmm_regimes = pd.Series(
                        [s['regime'] for s in hmm_sequence],
                        index=feature_df['date'][:len(hmm_sequence)]
                    )
                    hmm_trained = True
                else:
                    self._logger.warning(f"[RegimeValidator] Insufficient data for HMM: {len(feature_df)} samples")
            except Exception as e:
                self._logger.error(f"[RegimeValidator] HMM comparison failed: {e}")

        # Compute comparison metrics
        comparison = {
            'threshold': threshold,
            'threshold_persistence': [p.to_dict() for p in self.compute_persistence_metrics(threshold_regimes)],
            'threshold_transitions': self.compute_transition_matrix(threshold_regimes).to_dict(),
            'threshold_choppiness': self.count_excessive_switches(threshold_regimes),
            'hmm_available': hmm_trained,
        }

        if hmm_regimes is not None and len(hmm_regimes) > 0:
            # Align series
            common_idx = threshold_regimes.index.intersection(hmm_regimes.index)
            t_aligned = threshold_regimes.loc[common_idx]
            h_aligned = hmm_regimes.loc[common_idx]

            # Compute agreement rate
            agreement = (t_aligned == h_aligned).sum()
            total = len(common_idx)
            agreement_rate = agreement / total if total > 0 else 0

            # Count transitions for HMM
            hmm_persistence = self.compute_persistence_metrics(hmm_regimes)

            comparison.update({
                'agreement_rate': round(agreement_rate, 4),
                'agreement_count': int(agreement),
                'total_comparisons': int(total),
                'hmm_persistence': [p.to_dict() for p in hmm_persistence],
                'hmm_transitions': self.compute_transition_matrix(hmm_regimes).to_dict(),
                'method_comparison': {
                    'threshold_avg_duration': np.mean([p.avg_duration_months for p in self.compute_persistence_metrics(threshold_regimes)]),
                    'hmm_avg_duration': np.mean([p.avg_duration_months for p in hmm_persistence]),
                }
            })

        return comparison

    def _prepare_hmm_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for HMM from DataFrame."""
        result = pd.DataFrame()

        # Date
        if 'date' in df.columns:
            result['date'] = pd.to_datetime(df['date'])
        else:
            result['date'] = df.index

        # Growth z-score
        if 'growth_score' in df.columns:
            g = df['growth_score']
            result['growth_z'] = (g - g.rolling(36, min_periods=12).mean()) / g.rolling(36, min_periods=12).std()
        elif 'growth_z' in df.columns:
            result['growth_z'] = df['growth_z']

        # Inflation z-score
        if 'inflation_score' in df.columns:
            i = df['inflation_score']
            result['inflation_z'] = (i - i.rolling(36, min_periods=12).mean()) / i.rolling(36, min_periods=12).std()
        elif 'inflation_z' in df.columns:
            result['inflation_z'] = df['inflation_z']

        # Yield curve
        if 'yield_curve' in df.columns:
            result['yield_curve'] = df['yield_curve']
        elif 'yield_spread' in df.columns:
            result['yield_curve'] = df['yield_spread']

        # Credit
        if 'credit_z' in df.columns:
            result['credit_z'] = df['credit_z']
        elif 'credit_spreads' in df.columns:
            cs = df['credit_spreads']
            result['credit_z'] = (cs - cs.rolling(36, min_periods=12).mean()) / cs.rolling(36, min_periods=12).std()

        # Drop rows with missing features
        feature_cols = [c for c in result.columns if c != 'date']
        return result.dropna(subset=feature_cols[:2]).reset_index(drop=True)

    def select_method(
        self,
        hmm_available: bool,
        hmm_confidence: float,
        data_length_months: int,
        min_hmm_data: int = 24,
        confidence_threshold: float = 0.70
    ) -> Dict[str, Any]:
        """
        Arbitration rule: Select between HMM and threshold methods.

        DOCUMENTED RULE (from MODEL_INVENTORY_AND_VALIDATION_PLAN.md):
        - If HMM available and data_length >= 24 months:
            - If HMM confidence > 0.70: use HMM
            - Else: use blend (weighted by confidence)
        - Else: use threshold (fallback)

        Args:
            hmm_available: Whether HMM model is fitted
            hmm_confidence: HMM confidence score (0-1)
            data_length_months: Months of data available
            min_hmm_data: Minimum data required for HMM
            confidence_threshold: Confidence threshold for using HMM

        Returns:
            Dict with selected method and rationale
        """
        if hmm_available and data_length_months >= min_hmm_data:
            if hmm_confidence > confidence_threshold:
                return {
                    'method': 'hmm',
                    'weight': 1.0,
                    'rationale': f'HMM confidence ({hmm_confidence:.2f}) exceeds threshold ({confidence_threshold:.2f})',
                    'hmm_confidence': hmm_confidence,
                    'threshold_used': None
                }
            else:
                # Blend by confidence
                hmm_weight = hmm_confidence
                threshold_weight = 1 - hmm_confidence
                return {
                    'method': 'blend',
                    'weight': hmm_weight,
                    'rationale': f'Low HMM confidence ({hmm_confidence:.2f}), blending with threshold',
                    'hmm_confidence': hmm_confidence,
                    'threshold_used': 'current',
                    'blend_weights': {'hmm': hmm_weight, 'threshold': threshold_weight}
                }
        else:
            reason = 'insufficient_data' if data_length_months < min_hmm_data else 'hmm_unavailable'
            return {
                'method': 'threshold',
                'weight': 1.0,
                'rationale': f'Fallback to threshold: {reason}',
                'hmm_confidence': None,
                'threshold_used': self._optimal_threshold or 0.10
            }

    def get_arbitration_rule(self) -> Dict[str, Any]:
        """
        Return the documented arbitration rule.

        This is the SINGLE SOURCE OF TRUTH for how we choose between
        threshold and HMM methods.
        """
        return {
            'name': 'Regime Method Arbitration Rule',
            'version': '1.0',
            'description': 'Selects between threshold-based and HMM regime classifiers',
            'rules': [
                {
                    'condition': 'hmm_available AND data_length >= 24',
                    'sub_conditions': [
                        {
                            'condition': 'hmm_confidence > 0.70',
                            'action': 'use_hmm',
                            'weight': 1.0
                        },
                        {
                            'condition': 'hmm_confidence <= 0.70',
                            'action': 'blend',
                            'weight_formula': 'hmm_confidence'
                        }
                    ]
                },
                {
                    'condition': 'NOT hmm_available OR data_length < 24',
                    'action': 'use_threshold',
                    'weight': 1.0,
                    'fallback': True
                }
            ],
            'parameters': {
                'min_hmm_data_months': 24,
                'confidence_threshold': 0.70,
                'optimal_threshold': self._optimal_threshold or 0.10
            },
            'rationale': 'HMM requires sufficient data and high confidence to be reliable. When uncertain, blend or fall back to interpretable threshold method.'
        }

    def validate_current_classification(
        self,
        regime_series: pd.Series,
        lookback: int = 12
    ) -> Dict[str, Any]:
        """
        Validate the current regime classification context.

        Args:
            regime_series: Historical regime classifications
            lookback: Months to look back for context

        Returns:
            Validation report with warnings if applicable
        """
        if len(regime_series) < lookback:
            return {
                'valid': False,
                'warnings': ['Insufficient history for validation'],
                'current_regime': regime_series.iloc[-1] if len(regime_series) > 0 else None
            }

        recent = regime_series.tail(lookback)
        current = recent.iloc[-1]

        # Count recent switches
        switches = sum(1 for i in range(1, len(recent)) if recent.iloc[i] != recent.iloc[i-1])

        warnings = []

        # Warn if excessive switching
        if switches > lookback / 3:  # More than 1 switch per 3 months
            warnings.append(f'High regime churn: {switches} switches in {lookback} months')

        # Warn if current regime is very short
        current_duration = 1
        for i in range(len(recent) - 2, -1, -1):
            if recent.iloc[i] == current:
                current_duration += 1
            else:
                break

        if current_duration < self.MIN_PERSISTENCE_MONTHS:
            warnings.append(f'Current regime only {current_duration} month(s), may be unstable')

        # Warn if regime is rare historically
        regime_counts = regime_series.value_counts(normalize=True)
        if current in regime_counts and regime_counts[current] < 0.10:
            warnings.append(f'Current regime "{current}" is rare ({regime_counts[current]:.1%} historically)')

        return {
            'valid': len(warnings) == 0,
            'current_regime': current,
            'current_duration_months': current_duration,
            'recent_switches': switches,
            'warnings': warnings,
            'regime_distribution': regime_counts.to_dict()
        }


# Global instance
regime_validator = RegimeValidator()
