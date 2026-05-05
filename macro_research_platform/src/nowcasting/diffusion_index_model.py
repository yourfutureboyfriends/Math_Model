"""
Diffusion Index Model

Implements diffusion index-based nowcasting for business conditions.

A diffusion index measures the proportion of indicators that are
improving vs deteriorating. Values above 50 indicate expansion,
below 50 indicate contraction.

Inspired by the Chicago Fed National Activity Index (CFNAI) and
PMI-style business surveys.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class DiffusionIndex:
    """Result of diffusion index calculation."""
    index_value: float  # 0-100, 50 = neutral
    timestamp: pd.Timestamp
    n_improving: int
    n_deteriorating: int
    n_stable: int
    total_series: int
    dominant_direction: str  # improving, deteriorating, stable
    breadth_score: float  # How widespread the move is


@dataclass
class IndicatorSignal:
    """Signal from a single indicator."""
    series_id: str
    current_value: float
    mom_change: float  # Month-over-month change
    trend_direction: str  # improving, deteriorating, stable
    zscore: float
    weight: float


class DiffusionIndexModel:
    """
    Calculate diffusion indices from macro indicators.

    Models business conditions by tracking the breadth of
    improvement/deterioration across multiple indicators.
    """

    # Standard series for different aspects of economy
    ACTIVITY_INDICATORS = {
        "production": ["INDPRO", "TOTALSA"],  # Industrial production, vehicles
        "employment": ["PAYEMS", "AWHMAN", "CLAIMS"],  # Payrolls, hours, claims
        "consumption": ["PCEC1", "RETSAL"],  # PCE, retail sales
        "orders": ["AMTMNO", "NEWORDER"],  # Manufacturing orders
        "income": ["DSPIC96", "W875RX1"],  # Disposable income
    }

    PRICES_INDICATORS = {
        "cpi": ["CPIAUCSL"],
        "ppi": ["PPIACO"],
        "pce": ["PCEPI"],
        "wages": ["CES0500000003"],
    }

    def __init__(self, threshold: float = 0.0):
        """
        Args:
            threshold: Minimum z-score change to count as improving/deteriorating
        """
        self.threshold = threshold
        self.indicator_weights: Dict[str, float] = {}
        self.history: List[DiffusionIndex] = []

    def calculate_indicator_signal(
        self,
        series: pd.Series,
        lookback: int = 3,
    ) -> Optional[IndicatorSignal]:
        """
        Calculate signal from a single indicator series.

        Args:
            series: Time series of indicator values
            lookback: Months to assess trend

        Returns:
            IndicatorSignal with direction and strength
        """
        if len(series) < lookback + 1:
            return None

        # Get recent values
        current = series.iloc[-1]
        previous = series.iloc[-(lookback + 1)]

        # Handle missing data
        if pd.isna(current) or pd.isna(previous):
            return None

        # Calculate month-over-month change
        mom = series.diff().iloc[-lookback:].mean()

        # Calculate z-score (recent vs historical)
        historical = series.dropna()
        if len(historical) < 24:
            zscore = 0.0
        else:
            zscore = (current - historical.mean()) / historical.std()

        # Determine direction
        if mom > self.threshold:
            direction = "improving"
        elif mom < -self.threshold:
            direction = "deteriorating"
        else:
            direction = "stable"

        return IndicatorSignal(
            series_id=series.name,
            current_value=current,
            mom_change=mom,
            trend_direction=direction,
            zscore=zscore,
            weight=self.indicator_weights.get(series.name, 1.0),
        )

    def calculate_diffusion_index(
        self,
        signals: List[IndicatorSignal],
        timestamp: Optional[pd.Timestamp] = None,
    ) -> DiffusionIndex:
        """
        Calculate diffusion index from indicator signals.

        Args:
            signals: List of indicator signals
            timestamp: Timestamp for the index

        Returns:
            DiffusionIndex result
        """
        if not signals:
            return DiffusionIndex(
                index_value=50.0,
                timestamp=timestamp or pd.Timestamp.now(),
                n_improving=0,
                n_deteriorating=0,
                n_stable=0,
                total_series=0,
                dominant_direction="stable",
                breadth_score=0.0,
            )

        # Count directions (weighted)
        weighted_improving = sum(
            s.weight for s in signals if s.trend_direction == "improving"
        )
        weighted_deteriorating = sum(
            s.weight for s in signals if s.trend_direction == "deteriorating"
        )
        weighted_stable = sum(
            s.weight for s in signals if s.trend_direction == "stable"
        )
        total_weight = weighted_improving + weighted_deteriorating + weighted_stable

        if total_weight == 0:
            return DiffusionIndex(
                index_value=50.0,
                timestamp=timestamp or pd.Timestamp.now(),
                n_improving=0,
                n_deteriorating=0,
                n_stable=0,
                total_series=0,
                dominant_direction="stable",
                breadth_score=0.0,
            )

        # Calculate diffusion index (0-100, 50 = neutral)
        # Formula: 50 + 50 * (% improving - % deteriorating)
        pct_improving = weighted_improving / total_weight
        pct_deteriorating = weighted_deteriorating / total_weight

        index_value = 50 + 50 * (pct_improving - pct_deteriorating)

        # Determine dominant direction
        if pct_improving > pct_deteriorating + 0.1:
            dominant = "improving"
        elif pct_deteriorating > pct_improving + 0.1:
            dominant = "deteriorating"
        else:
            dominant = "stable"

        # Breadth score (how widespread is the move)
        breadth = abs(pct_improving - pct_deteriorating)

        return DiffusionIndex(
            index_value=round(index_value, 1),
            timestamp=timestamp or pd.Timestamp.now(),
            n_improving=int(weighted_improving),
            n_deteriorating=int(weighted_deteriorating),
            n_stable=int(weighted_stable),
            total_series=len(signals),
            dominant_direction=dominant,
            breadth_score=round(breadth, 2),
        )

    def calculate_multi_category_diffusion(
        self,
        data: Dict[str, pd.DataFrame],
        categories: Dict[str, List[str]],
    ) -> Dict[str, DiffusionIndex]:
        """
        Calculate diffusion indices for multiple categories.

        Args:
            data: Dict mapping category name to DataFrame of indicators
            categories: Dict mapping category to list of series IDs

        Returns:
            Dict of category diffusion indices
        """
        results = {}

        for category, series_list in categories.items():
            df = data.get(category)
            if df is None:
                continue

            signals = []
            for series_id in series_list:
                if series_id in df.columns:
                    signal = self.calculate_indicator_signal(df[series_id])
                    if signal:
                        signals.append(signal)

            diffusion = self.calculate_diffusion_index(
                signals, timestamp=df.index[-1] if len(df) > 0 else None
            )
            results[category] = diffusion

        return results

    def calculate_composite_diffusion(
        self,
        category_indices: Dict[str, DiffusionIndex],
        weights: Optional[Dict[str, float]] = None,
    ) -> DiffusionIndex:
        """
        Calculate weighted composite diffusion index.

        Args:
            category_indices: Diffusion indices by category
            weights: Optional weights by category

        Returns:
            Composite DiffusionIndex
        """
        if not category_indices:
            return DiffusionIndex(
                index_value=50.0,
                timestamp=pd.Timestamp.now(),
                n_improving=0,
                n_deteriorating=0,
                n_stable=0,
                total_series=0,
                dominant_direction="stable",
                breadth_score=0.0,
            )

        # Default equal weights
        if weights is None:
            weights = {cat: 1.0 for cat in category_indices}

        # Calculate weighted average
        total_weight = 0
        weighted_sum = 0
        n_improving = 0
        n_deteriorating = 0

        for category, idx in category_indices.items():
            w = weights.get(category, 1.0)
            weighted_sum += idx.index_value * w
            total_weight += w

            if idx.dominant_direction == "improving":
                n_improving += 1
            elif idx.dominant_direction == "deteriorating":
                n_deteriorating += 1

        if total_weight == 0:
            return DiffusionIndex(
                index_value=50.0,
                timestamp=pd.Timestamp.now(),
                n_improving=0,
                n_deteriorating=0,
                n_stable=0,
                total_series=0,
                dominant_direction="stable",
                breadth_score=0.0,
            )

        composite_value = weighted_sum / total_weight

        # Determine composite direction
        if composite_value > 55:
            dominant = "improving"
        elif composite_value < 45:
            dominant = "deteriorating"
        else:
            dominant = "stable"

        return DiffusionIndex(
            index_value=round(composite_value, 1),
            timestamp=list(category_indices.values())[0].timestamp,
            n_improving=n_improving,
            n_deteriorating=n_deteriorating,
            n_stable=len(category_indices) - n_improving - n_deteriorating,
            total_series=len(category_indices),
            dominant_direction=dominant,
            breadth_score=round(
                abs(n_improving - n_deteriorating) / len(category_indices), 2
            ),
        )

    def interpret_diffusion_value(self, value: float) -> Dict:
        """
        Interpret diffusion index value.

        Returns:
            Dict with interpretation
        """
        if value >= 60:
            return {
                "regime": "strong_expansion",
                "description": "Broad-based expansion",
                "recession_probability": 0.0,
            }
        elif value >= 55:
            return {
                "regime": "expansion",
                "description": "Moderate expansion",
                "recession_probability": 0.05,
            }
        elif value >= 45:
            return {
                "regime": "neutral",
                "description": "Neutral conditions",
                "recession_probability": 0.15,
            }
        elif value >= 40:
            return {
                "regime": "slowing",
                "description": "Growth slowing",
                "recession_probability": 0.30,
            }
        elif value >= 30:
            return {
                "regime": "contraction",
                "description": "Moderate contraction",
                "recession_probability": 0.55,
            }
        else:
            return {
                "regime": "strong_contraction",
                "description": "Broad-based contraction",
                "recession_probability": 0.80,
            }

    def get_leading_indicators(
        self,
        signals: List[IndicatorSignal],
        n_top: int = 3,
    ) -> List[IndicatorSignal]:
        """Get indicators leading the trend."""
        if not signals:
            return []

        # Sort by zscore (most extreme moves first)
        sorted_signals = sorted(signals, key=lambda s: abs(s.zscore), reverse=True)

        return sorted_signals[:n_top]

    def generate_diffusion_report(
        self,
        signals: List[IndicatorSignal],
        timestamp: Optional[pd.Timestamp] = None,
    ) -> Dict:
        """Generate comprehensive diffusion index report."""
        diffusion = self.calculate_diffusion_index(signals, timestamp)
        interpretation = self.interpret_diffusion_value(diffusion.index_value)
        leaders = self.get_leading_indicators(signals)

        # Category breakdown
        category_counts = {}
        for signal in signals:
            cat = signal.series_id.split("_")[0] if "_" in signal.series_id else "other"
            if cat not in category_counts:
                category_counts[cat] = {"improving": 0, "deteriorating": 0, "stable": 0}
            category_counts[cat][signal.trend_direction] += 1

        return {
            "diffusion_index": diffusion.index_value,
            "interpretation": interpretation,
            "timestamp": diffusion.timestamp,
            "summary": {
                "total_indicators": diffusion.total_series,
                "improving": diffusion.n_improving,
                "deteriorating": diffusion.n_deteriorating,
                "stable": diffusion.n_stable,
                "breadth_score": diffusion.breadth_score,
            },
            "category_breakdown": category_counts,
            "leading_indicators": [
                {
                    "series": s.series_id,
                    "direction": s.trend_direction,
                    "zscore": round(s.zscore, 2),
                    "mom_change": round(s.mom_change, 3),
                }
                for s in leaders
            ],
            "historical_context": self._get_historical_context(diffusion.index_value),
        }

    def _get_historical_context(self, current_value: float) -> Dict:
        """Provide historical context for current diffusion value."""
        # Simplified - would use actual historical distribution
        percentile = 50 + (current_value - 50) * 0.5
        percentile = max(0, min(100, percentile))

        return {
            "percentile": round(percentile, 1),
            "vs_6m_ago": None,  # Would calculate from history
            "vs_12m_ago": None,
            "trend": "improving" if current_value > 50 else "deteriorating",
        }


def calculate_3m_3m_diffusion(
    data: pd.DataFrame,
    lookback_months: int = 3,
) -> pd.Series:
    """
    Calculate 3-month vs 3-month diffusion index.

    This is a common nowcasting technique that compares
    the last 3 months to the prior 3 months.

    Args:
        data: DataFrame with indicator columns
        lookback_months: Months to compare

    Returns:
        Time series of diffusion values
    """
    diffusion_values = []

    for i in range(lookback_months * 2, len(data)):
        window = data.iloc[i - lookback_months * 2 : i]
        recent = window.iloc[lookback_months:]
        prior = window.iloc[:lookback_months]

        # Count improving series
        improving = 0
        deteriorating = 0
        total = 0

        for col in data.columns:
            if col in recent.columns and col in prior.columns:
                recent_mean = recent[col].mean()
                prior_mean = prior[col].mean()

                if pd.notna(recent_mean) and pd.notna(prior_mean):
                    total += 1
                    if recent_mean > prior_mean:
                        improving += 1
                    elif recent_mean < prior_mean:
                        deteriorating += 1

        if total > 0:
            diffusion = 50 + 50 * (improving - deteriorating) / total
            diffusion_values.append((data.index[i], diffusion))

    return pd.Series(
        [v for _, v in diffusion_values],
        index=[d for d, _ in diffusion_values],
    )


def identify_turning_points(
    diffusion_series: pd.Series,
    threshold: float = 45,
) -> List[Dict]:
    """
    Identify potential turning points in the diffusion series.

    Args:
        diffusion_series: Time series of diffusion values
        threshold: Level to flag as potential turn

    Returns:
        List of turning point events
    """
    turning_points = []

    for i in range(1, len(diffusion_series) - 1):
        current = diffusion_series.iloc[i]
        prev = diffusion_series.iloc[i - 1]
        next_val = diffusion_series.iloc[i + 1]

        # Peak (local maximum above threshold)
        if current > prev and current > next_val and current > 55:
            turning_points.append({
                "date": diffusion_series.index[i],
                "type": "peak",
                "value": current,
            })

        # Trough (local minimum below threshold)
        if current < prev and current < next_val and current < threshold:
            turning_points.append({
                "date": diffusion_series.index[i],
                "type": "trough",
                "value": current,
            })

    return turning_points
