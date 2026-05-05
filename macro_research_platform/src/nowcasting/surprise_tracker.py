"""
Macro Data Surprise Tracker

Tracks macroeconomic data surprises vs consensus expectations.

Data surprises drive short-term market movements and can signal
shifts in economic momentum before they're fully priced in.

Inspired by the Bloomberg Economic Surprise Index and Citigroup
Economic Surprise Index frameworks.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataSurprise:
    """A single data surprise event."""
    series_id: str
    release_date: datetime
    observation_date: datetime
    actual: float
    consensus: float
    prior: float
    surprise_zscore: float
    surprise_pct: float
    market_importance: float  # 0-1, how much markets care


@dataclass
class SurpriseIndex:
    """Cumulative surprise index value."""
    timestamp: datetime
    index_value: float
    n_beat: int
    n_miss: int
    n_in_line: int
    momentum: float  # Recent trend in surprises
    breadth: float  # How widespread surprises are


class MacroSurpriseTracker:
    """
    Track macroeconomic data surprises vs consensus.

    Creates surprise indices that show whether data is beating
    or missing expectations on balance.
    """

    # Major US macro releases with typical importance weights
    MAJOR_RELEASES = {
        "NFP": {"name": "Nonfarm Payrolls", "weight": 1.0, "freq": "M"},
        "CPI": {"name": "Consumer Price Index", "weight": 0.9, "freq": "M"},
        "PPI": {"name": "Producer Price Index", "weight": 0.6, "freq": "M"},
        "GDP": {"name": "GDP", "weight": 1.0, "freq": "Q"},
        "ISM_MFG": {"name": "ISM Manufacturing", "weight": 0.8, "freq": "M"},
        "ISM_SVC": {"name": "ISM Services", "weight": 0.7, "freq": "M"},
        "RETAIL_SALES": {"name": "Retail Sales", "weight": 0.7, "freq": "M"},
        "INDUSTRIAL_PRODUCTION": {"name": "Industrial Production", "weight": 0.5, "freq": "M"},
        "HOUSING_STARTS": {"name": "Housing Starts", "weight": 0.5, "freq": "M"},
        "CONSUMER_CONFIDENCE": {"name": "Consumer Confidence", "weight": 0.6, "freq": "M"},
        "UNEMPLOYMENT_RATE": {"name": "Unemployment Rate", "weight": 0.9, "freq": "M"},
        "AVERAGE_HOURLY_EARNINGS": {"name": "Avg Hourly Earnings", "weight": 0.6, "freq": "M"},
        "PCE": {"name": "Personal Consumption Expenditures", "weight": 0.7, "freq": "M"},
        "FED_DECISION": {"name": "FOMC Decision", "weight": 1.0, "freq": "M"},
    }

    def __init__(self, lookback_days: int = 90):
        """
        Args:
            lookback_days: Days to include in surprise index calculation
        """
        self.lookback_days = lookback_days
        self.surprises: List[DataSurprise] = []
        self.index_history: List[SurpriseIndex] = []
        self.consensus_history: Dict[str, List[Tuple[datetime, float]]] = {}

    def record_surprise(
        self,
        series_id: str,
        actual: float,
        consensus: float,
        prior: float,
        release_date: datetime,
        observation_date: Optional[datetime] = None,
    ) -> DataSurprise:
        """
        Record a new data surprise.

        Args:
            series_id: Identifier for the data series
            actual: Actual released value
            consensus: Consensus expectation
            prior: Prior period value
            release_date: When data was released
            observation_date: Period the data represents

        Returns:
            DataSurprise object
        """
        # Calculate surprise in standard deviations
        # Use historical distribution for z-score
        historical_std = self._get_historical_std(series_id)

        if historical_std > 0:
            surprise_z = (actual - consensus) / historical_std
        else:
            surprise_z = 0.0

        # Percentage surprise
        if consensus != 0:
            surprise_pct = (actual - consensus) / abs(consensus) * 100
        else:
            surprise_pct = 0.0

        # Get market importance
        importance = self.MAJOR_RELEASES.get(series_id, {}).get("weight", 0.5)

        surprise = DataSurprise(
            series_id=series_id,
            release_date=release_date,
            observation_date=observation_date or release_date,
            actual=actual,
            consensus=consensus,
            prior=prior,
            surprise_zscore=surprise_z,
            surprise_pct=surprise_pct,
            market_importance=importance,
        )

        self.surprises.append(surprise)

        # Store consensus for history
        if series_id not in self.consensus_history:
            self.consensus_history[series_id] = []
        self.consensus_history[series_id].append((release_date, consensus))

        return surprise

    def _get_historical_std(self, series_id: str) -> float:
        """Get historical standard deviation of surprises for a series."""
        series_surprises = [
            s.surprise_zscore for s in self.surprises if s.series_id == series_id
        ]

        if len(series_surprises) < 5:
            return 1.0  # Default

        return np.std(series_surprises)

    def calculate_surprise_index(
        self,
        as_of_date: Optional[datetime] = None,
        lookback_days: Optional[int] = None,
    ) -> SurpriseIndex:
        """
        Calculate cumulative surprise index.

        Args:
            as_of_date: Calculate index as of this date
            lookback_days: Override default lookback

        Returns:
            SurpriseIndex with current value
        """
        cutoff = as_of_date or datetime.now()
        lookback = lookback_days or self.lookback_days

        # Filter to relevant surprises
        recent = [
            s for s in self.surprises
            if s.release_date >= cutoff - timedelta(days=lookback)
            and s.release_date <= cutoff
        ]

        if not recent:
            return SurpriseIndex(
                timestamp=cutoff,
                index_value=0.0,
                n_beat=0,
                n_miss=0,
                n_in_line=0,
                momentum=0.0,
                breadth=0.0,
            )

        # Weight by market importance
        weighted_surprises = []
        n_beat = n_miss = n_in_line = 0

        for s in recent:
            weighted = s.surprise_zscore * s.market_importance
            weighted_surprises.append(weighted)

            if abs(s.surprise_zscore) < 0.5:
                n_in_line += 1
            elif s.surprise_zscore > 0:
                n_beat += 1
            else:
                n_miss += 1

        # Calculate index (cumulative weighted surprise)
        # Scale so that typical range is -100 to +100
        index_value = np.mean(weighted_surprises) * 25

        # Calculate momentum (recent vs earlier in period)
        if len(weighted_surprises) >= 10:
            mid = len(weighted_surprises) // 2
            recent_mean = np.mean(weighted_surprises[mid:])
            prior_mean = np.mean(weighted_surprises[:mid])
            momentum = recent_mean - prior_mean
        else:
            momentum = 0.0

        # Breadth: how many different series showing surprises
        unique_series = len(set(s.series_id for s in recent))
        total_major = len(self.MAJOR_RELEASES)
        breadth = unique_series / total_major if total_major > 0 else 0

        index = SurpriseIndex(
            timestamp=cutoff,
            index_value=round(index_value, 2),
            n_beat=n_beat,
            n_miss=n_miss,
            n_in_line=n_in_line,
            momentum=round(momentum, 2),
            breadth=round(breadth, 2),
        )

        self.index_history.append(index)

        return index

    def calculate_surprise_indices_by_category(
        self,
        as_of_date: Optional[datetime] = None,
    ) -> Dict[str, SurpriseIndex]:
        """
        Calculate surprise indices by category.

        Categories:
        - labor: Employment data
        - prices: Inflation data
        - activity: Growth/production data
        - sentiment: Confidence/sentiment
        """
        categories = {
            "labor": ["NFP", "UNEMPLOYMENT_RATE", "AVERAGE_HOURLY_EARNINGS"],
            "prices": ["CPI", "PPI", "PCE"],
            "activity": ["GDP", "INDUSTRIAL_PRODUCTION", "RETAIL_SALES", "ISM_MFG"],
            "sentiment": ["CONSUMER_CONFIDENCE", "ISM_SVC"],
        }

        results = {}
        for category, series_list in categories.items():
            # Filter surprises to this category
            cat_surprises = [
                s for s in self.surprises if s.series_id in series_list
            ]

            # Temporarily replace surprises for calculation
            old_surprises = self.surprises
            self.surprises = cat_surprises

            results[category] = self.calculate_surprise_index(as_of_date)

            self.surprises = old_surprises

        return results

    def get_surprise_trend(
        self,
        series_id: str,
        window: int = 6,
    ) -> Dict:
        """
        Get surprise trend for a specific series.

        Args:
            series_id: Series to analyze
            window: Number of releases to look back

        Returns:
            Trend analysis
        """
        series_surprises = [
            s for s in self.surprises if s.series_id == series_id
        ]

        if len(series_surprises) < 3:
            return {
                "trend": "insufficient_data",
                "avg_surprise": 0.0,
                "consistency": "unknown",
            }

        recent = series_surprises[-window:]

        surprises = [s.surprise_zscore for s in recent]
        avg_surprise = np.mean(surprises)

        # Trend direction
        if len(surprises) >= 6:
            first_half = np.mean(surprises[: len(surprises) // 2])
            second_half = np.mean(surprises[len(surprises) // 2 :])
            trend_delta = second_half - first_half

            if trend_delta > 0.5:
                trend = "improving"
            elif trend_delta < -0.5:
                trend = "deteriorating"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
            trend_delta = 0.0

        # Consistency (same direction)
        positive_count = sum(1 for s in surprises if s > 0)
        consistency = positive_count / len(surprises)

        if consistency > 0.7:
            consistency_label = "consistently_positive"
        elif consistency < 0.3:
            consistency_label = "consistently_negative"
        else:
            consistency_label = "mixed"

        return {
            "trend": trend,
            "trend_delta": round(trend_delta, 2),
            "avg_surprise": round(avg_surprise, 2),
            "consistency": consistency_label,
            "consistency_pct": round(consistency, 2),
            "n_observations": len(recent),
        }

    def analyze_consensus_bias(
        self,
        series_id: str,
        window: int = 12,
    ) -> Dict:
        """
        Analyze if consensus has systematic bias.

        Checks if consensus systematically over/under estimates.

        Args:
            series_id: Series to analyze
            window: Number of releases to analyze

        Returns:
            Bias analysis
        """
        series_surprises = [
            s for s in self.surprises if s.series_id == series_id
        ]

        if len(series_surprises) < window:
            return {"error": "Insufficient data"}

        recent = series_surprises[-window:]
        surprises = [s.actual - s.consensus for s in recent]

        avg_bias = np.mean(surprises)
        bias_std = np.std(surprises)

        # Test if bias is statistically significant
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(surprises, 0)

        is_significant = p_value < 0.05

        if is_significant and avg_bias > 0:
            bias_direction = "consensus_too_low"
        elif is_significant and avg_bias < 0:
            bias_direction = "consensus_too_high"
        else:
            bias_direction = "unbiased"

        return {
            "avg_bias": round(avg_bias, 3),
            "bias_std": round(bias_std, 3),
            "t_statistic": round(t_stat, 2),
            "p_value": round(p_value, 3),
            "is_significant": is_significant,
            "bias_direction": bias_direction,
            "recommendation": "adjust_consensus_up" if bias_direction == "consensus_too_low"
            else "adjust_consensus_down" if bias_direction == "consensus_too_high"
            else "use_consensus_directly",
        }

    def generate_surprise_report(
        self,
        as_of_date: Optional[datetime] = None,
    ) -> Dict:
        """Generate comprehensive surprise report."""
        # Overall surprise index
        overall = self.calculate_surprise_index(as_of_date)

        # Category indices
        by_category = self.calculate_surprise_indices_by_category(as_of_date)

        # Recent surprises
        recent_surprises = sorted(
            self.surprises,
            key=lambda s: s.release_date,
            reverse=True,
        )[:10]

        # Trend analysis for major releases
        trends = {}
        for series_id in self.MAJOR_RELEASES:
            trends[series_id] = self.get_surprise_trend(series_id)

        return {
            "summary": {
                "surprise_index": overall.index_value,
                "n_beat": overall.n_beat,
                "n_miss": overall.n_miss,
                "momentum": overall.momentum,
                "breadth": overall.breadth,
                "interpretation": self._interpret_surprise_index(overall),
            },
            "by_category": {
                cat: {
                    "index": idx.index_value,
                    "n_beat": idx.n_beat,
                    "n_miss": idx.n_miss,
                }
                for cat, idx in by_category.items()
            },
            "recent_surprises": [
                {
                    "series": s.series_id,
                    "date": s.release_date,
                    "actual": s.actual,
                    "consensus": s.consensus,
                    "surprise_z": round(s.surprise_zscore, 2),
                    "surprise_pct": round(s.surprise_pct, 2),
                }
                for s in recent_surprises
            ],
            "trends": trends,
        }

    def _interpret_surprise_index(self, index: SurpriseIndex) -> str:
        """Interpret the surprise index value."""
        value = index.index_value

        if value > 50:
            return "data_consistently_beating"
        elif value > 25:
            return "data_generally_beating"
        elif value > -25:
            return "data_mixed"
        elif value > -50:
            return "data_generally_missing"
        else:
            return "data_consistently_missing"


def calculate_surprise_zscore(
    actual: float,
    consensus: float,
    historical_std: float,
) -> float:
    """
    Calculate standardized surprise score.

    Args:
        actual: Actual value
        consensus: Consensus expectation
        historical_std: Historical std dev of surprises

    Returns:
        Z-score of surprise
    """
    if historical_std <= 0:
        return 0.0

    return (actual - consensus) / historical_std


def calculate_surprise_impact(
    surprise_zscore: float,
    market_importance: float,
    asset_sensitivity: float,
) -> float:
    """
    Estimate likely market impact of a surprise.

    Args:
        surprise_zscore: Standardized surprise
        market_importance: 0-1 importance weight
        asset_sensitivity: Asset-specific sensitivity to this release

    Returns:
        Estimated impact score
    """
    return abs(surprise_zscore) * market_importance * asset_sensitivity


def identify_surprise_regime(
    surprise_history: List[float],
    window: int = 20,
) -> str:
    """
    Identify surprise regime from recent history.

    Args:
        surprise_history: List of surprise values
        window: Lookback window

    Returns:
        Regime classification
    """
    if len(surprise_history) < window:
        return "insufficient_data"

    recent = surprise_history[-window:]
    avg = np.mean(recent)
    std = np.std(recent)

    if avg > std and avg > 0.5:
        return "positive_surprise_regime"
    elif avg < -std and avg < -0.5:
        return "negative_surprise_regime"
    elif abs(avg) < 0.3:
        return "neutral_regime"
    else:
        return "mixed_regime"
