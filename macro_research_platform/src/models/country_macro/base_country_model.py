"""
Base Country Macro Model

Abstract base class for country-specific macro models.
Each country model outputs standardized metrics for aggregation.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CountryMacroOutput:
    """Standardized output from any country macro model."""

    # Identification
    country: str
    region: str  # North America, Europe, Asia, etc.
    currency: str

    # Current State
    current_regime: str
    regime_confidence: float  # 0-1

    # Macro Drivers (z-scores or normalized values)
    growth_momentum: float  # Positive = above trend
    growth_trend: str  # "accelerating", "stable", "decelerating"
    inflation_pressure: float  # Positive = above target
    inflation_trend: str  # "rising", "stable", "falling"
    policy_stance: str  # "tight", "neutral", "loose", "emergency"
    policy_gap: float  # Deviation from neutral
    financial_conditions: float  # Tightness index
    credit_stress: float  # 0-1, higher = more stress

    # Risk Metrics
    recession_risk: float  # 0-1 probability
    recession_probability_12m: float
    currency_pressure: float  # Positive = depreciation pressure
    currency_trend: str  # "appreciating", "stable", "depreciating"

    # Market Confirmation
    market_confirmation: bool  # Do markets agree with model?
    market_lead_indicators: Dict[str, float]

    # Data Quality
    confidence_level: float  # 0-1 based on data quality
    latest_data_date: Optional[datetime]
    data_quality_score: float  # 0-1
    data_warnings: List[str] = field(default_factory=list)

    # Driver Analysis
    top_positive_drivers: List[Tuple[str, float]] = field(default_factory=list)
    top_negative_drivers: List[Tuple[str, float]] = field(default_factory=list)

    # Timestamp
    calculated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "country": self.country,
            "region": self.region,
            "currency": self.currency,
            "current_regime": self.current_regime,
            "regime_confidence": self.regime_confidence,
            "growth_momentum": self.growth_momentum,
            "growth_trend": self.growth_trend,
            "inflation_pressure": self.inflation_pressure,
            "inflation_trend": self.inflation_trend,
            "policy_stance": self.policy_stance,
            "policy_gap": self.policy_gap,
            "financial_conditions": self.financial_conditions,
            "credit_stress": self.credit_stress,
            "recession_risk": self.recession_risk,
            "recession_probability_12m": self.recession_probability_12m,
            "currency_pressure": self.currency_pressure,
            "currency_trend": self.currency_trend,
            "market_confirmation": self.market_confirmation,
            "confidence_level": self.confidence_level,
            "data_quality_score": self.data_quality_score,
            "latest_data_date": self.latest_data_date.isoformat() if self.latest_data_date else None,
            "top_positive_drivers": self.top_positive_drivers,
            "top_negative_drivers": self.top_negative_drivers,
        }


class BaseCountryMacroModel(ABC):
    """
    Abstract base class for country macro models.

    Each country implementation must provide:
    - Data source configuration
    - Regime classification logic
    - Macro indicator calculations
    """

    # Standard regime labels (can be extended by subclasses)
    STANDARD_REGIMES = [
        "goldilocks",  # Growth up, inflation down/stable
        "reflation",  # Growth up, inflation up
        "slowdown",  # Growth down, inflation down
        "stagflation",  # Growth down, inflation up
        "inflation_pressure",  # Late cycle, inflation high
        "policy_support",  # Policy loose, demand weak
        "mixed",  # Conflicting signals
    ]

    def __init__(
        self,
        country_code: str,
        country_name: str,
        region: str,
        currency: str,
        data_sources: List[str],
    ):
        self.country_code = country_code
        self.country_name = country_name
        self.region = region
        self.currency = currency
        self.data_sources = data_sources

        # Data storage
        self.macro_data: Dict[str, pd.Series] = {}
        self.data_availability: Dict[str, Dict] = {}

        # Model parameters
        self.inflation_target: float = 2.0
        self.neutral_rate_estimate: float = 2.5
        self.growth_trend_estimate: float = 2.0

    @abstractmethod
    def load_data(
        self,
        as_of_date: Optional[datetime] = None,
        use_live: bool = False,
    ) -> bool:
        """
        Load macro data for this country.

        Args:
            as_of_date: Point-in-time date
            use_live: Whether to fetch live data

        Returns:
            True if sufficient data loaded
        """
        pass

    @abstractmethod
    def calculate_regime(self) -> Tuple[str, float]:
        """
        Determine current macro regime.

        Returns:
            (regime_name, confidence)
        """
        pass

    @abstractmethod
    def calculate_growth_momentum(self) -> Tuple[float, str]:
        """
        Calculate growth momentum.

        Returns:
            (momentum_score, trend_direction)
        """
        pass

    @abstractmethod
    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        """
        Calculate inflation pressure.

        Returns:
            (pressure_score, trend_direction)
        """
        pass

    @abstractmethod
    def calculate_policy_stance(self) -> Tuple[str, float]:
        """
        Calculate policy stance relative to neutral.

        Returns:
            (stance_description, policy_gap)
        """
        pass

    @abstractmethod
    def calculate_financial_conditions(self) -> float:
        """
        Calculate financial conditions index.

        Returns:
            Financial conditions score (higher = tighter)
        """
        pass

    @abstractmethod
    def calculate_credit_stress(self) -> float:
        """
        Calculate credit stress level.

        Returns:
            Credit stress score 0-1
        """
        pass

    @abstractmethod
    def calculate_recession_risk(self) -> Tuple[float, float]:
        """
        Calculate recession probability.

        Returns:
            (current_risk, 12m_probability)
        """
        pass

    @abstractmethod
    def calculate_currency_pressure(self) -> Tuple[float, str]:
        """
        Calculate currency pressure.

        Returns:
            (pressure_score, trend_direction)
        """
        pass

    def get_data_quality_score(self) -> Tuple[float, List[str]]:
        """
        Calculate overall data quality score.

        Returns:
            (quality_score, warnings)
        """
        if not self.macro_data:
            return 0.0, ["No data loaded"]

        scores = []
        warnings = []

        for indicator, series in self.macro_data.items():
            if series is None or len(series) == 0:
                warnings.append(f"{indicator}: missing")
                continue

            # Check staleness
            latest = series.index[-1]
            days_stale = (datetime.now() - latest).days

            if days_stale > 90:
                scores.append(0.3)
                warnings.append(f"{indicator}: stale ({days_stale} days)")
            elif days_stale > 30:
                scores.append(0.7)
            else:
                scores.append(1.0)

        if not scores:
            return 0.0, warnings

        return sum(scores) / len(scores), warnings

    def identify_drivers(self) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        """
        Identify top positive and negative drivers.

        Returns:
            (positive_drivers, negative_drivers)
        """
        drivers = []

        # Growth contribution
        growth = self.macro_data.get("growth", pd.Series()).iloc[-1] if "growth" in self.macro_data else 0
        if growth > 0.5:
            drivers.append(("growth", growth))
        elif growth < -0.5:
            drivers.append(("growth", growth))

        # Inflation contribution
        inflation = self.macro_data.get("inflation", pd.Series()).iloc[-1] if "inflation" in self.macro_data else 0
        if inflation > 1.0:
            drivers.append(("inflation", inflation))
        elif inflation < -0.5:
            drivers.append(("inflation", inflation))

        # Policy contribution
        policy_gap = self.macro_data.get("policy_gap", pd.Series()).iloc[-1] if "policy_gap" in self.macro_data else 0
        if abs(policy_gap) > 0.5:
            drivers.append(("policy", policy_gap))

        positive = [(d, v) for d, v in drivers if v > 0]
        negative = [(d, v) for d, v in drivers if v < 0]

        # Sort by magnitude
        positive.sort(key=lambda x: x[1], reverse=True)
        negative.sort(key=lambda x: x[1])

        return positive[:3], negative[:3]

    def generate_output(self) -> CountryMacroOutput:
        """
        Generate complete country macro output.

        Returns:
            CountryMacroOutput with all fields populated
        """
        # Calculate all components
        regime, regime_conf = self.calculate_regime()
        growth_mom, growth_trend = self.calculate_growth_momentum()
        inflation_pres, inflation_trend = self.calculate_inflation_pressure()
        policy_stance, policy_gap = self.calculate_policy_stance()
        fin_conditions = self.calculate_financial_conditions()
        credit_stress = self.calculate_credit_stress()
        rec_risk, rec_prob_12m = self.calculate_recession_risk()
        curr_pressure, curr_trend = self.calculate_currency_pressure()

        # Data quality
        data_quality, warnings = self.get_data_quality_score()

        # Latest data date
        latest_dates = [
            s.index[-1] for s in self.macro_data.values()
            if s is not None and len(s) > 0
        ]
        latest_data_date = max(latest_dates) if latest_dates else None

        # Drivers
        pos_drivers, neg_drivers = self.identify_drivers()

        # Market confirmation (simplified)
        market_conf = True  # Would check vs market indicators
        market_lead_indicators = {}  # Would be populated from market data

        # Overall confidence
        confidence = regime_conf * data_quality

        return CountryMacroOutput(
            country=self.country_name,
            region=self.region,
            currency=self.currency,
            current_regime=regime,
            regime_confidence=regime_conf,
            growth_momentum=growth_mom,
            growth_trend=growth_trend,
            inflation_pressure=inflation_pres,
            inflation_trend=inflation_trend,
            policy_stance=policy_stance,
            policy_gap=policy_gap,
            financial_conditions=fin_conditions,
            credit_stress=credit_stress,
            recession_risk=rec_risk,
            recession_probability_12m=rec_prob_12m,
            currency_pressure=curr_pressure,
            currency_trend=curr_trend,
            market_confirmation=market_conf,
            market_lead_indicators=market_lead_indicators,
            confidence_level=confidence,
            latest_data_date=latest_data_date,
            data_quality_score=data_quality,
            data_warnings=warnings,
            top_positive_drivers=pos_drivers,
            top_negative_drivers=neg_drivers,
        )

    @abstractmethod
    def get_sample_data(self) -> Dict[str, pd.Series]:
        """
        Return sample data for testing/demo purposes.

        Returns:
            Dict of indicator to sample series
        """
        pass
