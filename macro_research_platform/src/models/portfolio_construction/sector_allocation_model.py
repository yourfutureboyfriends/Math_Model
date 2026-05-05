"""
Sector Allocation Model - Config Driven

Professional sector allocation using:
- Regime fit from YAML config
- Financial conditions alignment
- Earnings sensitivity
- Rate sensitivity
- Credit sensitivity
- Momentum confirmation
- Recession risk penalty

Based on sector_rules.yaml configuration
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SectorScore:
    """Sector scoring result."""
    sector: str
    total_score: float
    signal: str  # Overweight, Neutral, Underweight
    components: Dict[str, float]
    rationale: str
    confidence: float


class ConfigDrivenSectorModel:
    """
    Config-driven sector allocation model.

    Uses sector_rules.yaml for all scoring logic.
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Go up 3 levels from src/models/portfolio_construction/ to reach project root
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "sector_rules.yaml"

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.sectors = self.config.get("sectors", {})
        self.weights = self.config.get("scoring_components", {})
        self.thresholds = self.config.get("signal_thresholds", {})

    def _score_regime_fit(
        self,
        sector: str,
        regime: str,
    ) -> Tuple[float, str]:
        """Score sector fit for current regime."""
        sector_config = self.sectors.get(sector, {})
        regime_perf = sector_config.get("regime_performance", {})

        regime_data = regime_perf.get(regime, {})
        score = regime_data.get("score", 0.0)
        rationale = regime_data.get("rationale", "No regime data")

        return score, rationale

    def _score_financial_conditions_fit(
        self,
        sector: str,
        fc_impulse: str,  # easing, neutral, tightening
    ) -> Tuple[float, str]:
        """Score alignment with financial conditions."""
        sector_config = self.sectors.get(sector, {})
        fc_impact = sector_config.get("financial_conditions_impact", {})

        score = fc_impact.get(fc_impulse, 0.0)

        descriptions = {
            "easing": "Benefits from easing financial conditions",
            "neutral": "Neutral to financial conditions",
            "tightening": "Hurt by tightening financial conditions",
        }

        return score, descriptions.get(fc_impulse, "Unknown")

    def _score_earnings_sensitivity(
        self,
        sector: str,
        growth_score: float,
    ) -> Tuple[float, str]:
        """Score based on cyclical earnings sensitivity."""
        sector_config = self.sectors.get(sector, {})
        characteristics = sector_config.get("characteristics", {})

        beta = characteristics.get("cyclical_beta", 1.0)

        # Higher beta sectors get more extreme scores
        score = growth_score * beta

        if beta > 1.0:
            rationale = f"Cyclical (beta={beta:.1f})"
        elif beta < 0.7:
            rationale = f"Defensive (beta={beta:.1f})"
        else:
            rationale = f"Moderate cyclicality (beta={beta:.1f})"

        return score, rationale

    def _score_rate_sensitivity(
        self,
        sector: str,
        liquidity_score: float,
    ) -> Tuple[float, str]:
        """Score based on rate sensitivity."""
        sector_config = self.sectors.get(sector, {})
        characteristics = sector_config.get("characteristics", {})

        sensitivity = characteristics.get("rate_sensitivity", "medium")

        sensitivity_mult = {
            "very_high": 2.0,
            "high": 1.5,
            "medium": 1.0,
            "low": 0.5,
        }.get(sensitivity, 1.0)

        # Liquidity score is inversely related to rate pressure
        score = liquidity_score * sensitivity_mult

        return score, f"{sensitivity} rate sensitivity"

    def _score_credit_sensitivity(
        self,
        sector: str,
        credit_stress_score: float,
    ) -> Tuple[float, str]:
        """Score based on credit market sensitivity."""
        sector_config = self.sectors.get(sector, {})
        characteristics = sector_config.get("characteristics", {})

        earnings_vol = characteristics.get("earnings_volatility", "medium")

        # High volatility sectors more sensitive to credit stress
        vol_mult = {
            "very_high": 1.5,
            "high": 1.2,
            "medium": 1.0,
            "low": 0.7,
        }.get(earnings_vol, 1.0)

        # Negative correlation with credit stress
        score = -credit_stress_score * vol_mult

        return score, f"Credit sensitivity ({earnings_vol})"

    def _score_momentum(
        self,
        sector: str,
        sector_momentum: Optional[float] = None,
    ) -> Tuple[float, str]:
        """Score momentum confirmation."""
        if sector_momentum is None:
            return 0.0, "No momentum data"

        # Scale momentum to score
        score = np.clip(sector_momentum * 2, -0.5, 0.5)

        if score > 0.2:
            rationale = "Positive momentum"
        elif score < -0.2:
            rationale = "Negative momentum"
        else:
            rationale = "Mixed momentum"

        return score, rationale

    def _apply_recession_penalty(
        self,
        base_score: float,
        recession_prob: float,
    ) -> float:
        """Apply recession risk penalty."""
        # Penalty increases with recession probability
        # At 50% recession prob, score reduced by ~0.25
        penalty = recession_prob * 0.5
        return base_score - penalty

    def score_sector(
        self,
        sector: str,
        regime: str,
        growth_score: float,
        liquidity_score: float,
        credit_stress_score: float,
        financial_conditions: str = "neutral",
        recession_prob: float = 0.0,
        sector_momentum: Optional[float] = None,
    ) -> SectorScore:
        """
        Calculate full sector score.

        Implements scoring_formula from config:
            sector_score =
                (regime_fit * 0.30) +
                (financial_conditions_fit * 0.20) +
                (earnings_sensitivity * 0.15) +
                (rate_sensitivity * 0.10) +
                (credit_sensitivity * 0.10) +
                (momentum * 0.10) +
                (valuation * 0.05) -
                (recession_penalty)
        """
        components = {}
        rationales = []

        # 1. Regime fit (30%)
        regime_score, regime_rationale = self._score_regime_fit(sector, regime)
        components["regime_fit"] = regime_score * self.weights.get("regime_fit", {}).get("weight", 0.30)
        rationales.append(f"Regime: {regime_rationale}")

        # 2. Financial conditions fit (20%)
        fc_score, fc_rationale = self._score_financial_conditions_fit(sector, financial_conditions)
        components["financial_conditions"] = fc_score * self.weights.get("financial_conditions_fit", {}).get("weight", 0.20)
        rationales.append(f"FC: {fc_rationale}")

        # 3. Earnings sensitivity (15%)
        earn_score, earn_rationale = self._score_earnings_sensitivity(sector, growth_score)
        components["earnings"] = earn_score * self.weights.get("earnings_sensitivity", {}).get("weight", 0.15)
        rationales.append(earn_rationale)

        # 4. Rate sensitivity (10%)
        rate_score, rate_rationale = self._score_rate_sensitivity(sector, liquidity_score)
        components["rate"] = rate_score * self.weights.get("rate_sensitivity", {}).get("weight", 0.10)
        rationales.append(rate_rationale)

        # 5. Credit sensitivity (10%)
        credit_score, credit_rationale = self._score_credit_sensitivity(sector, credit_stress_score)
        components["credit"] = credit_score * self.weights.get("credit_sensitivity", {}).get("weight", 0.10)
        rationales.append(credit_rationale)

        # 6. Momentum (10%)
        mom_score, mom_rationale = self._score_momentum(sector, sector_momentum)
        components["momentum"] = mom_score * self.weights.get("momentum_confirmation", {}).get("weight", 0.10)
        rationales.append(mom_rationale)

        # Valuation placeholder (5%)
        components["valuation"] = 0.0  # Would need valuation data

        # Calculate base score
        base_score = sum(components.values())

        # Apply recession penalty
        total_score = self._apply_recession_penalty(base_score, recession_prob)

        # Determine signal
        if total_score >= self.thresholds.get("overweight", 0.4):
            signal = "Overweight"
        elif total_score <= self.thresholds.get("underweight", -0.4):
            signal = "Underweight"
        else:
            signal = "Neutral"

        # Build rationale
        sector_config = self.sectors.get(sector, {})
        sector_name = sector_config.get("name", sector)

        if signal == "Overweight":
            primary_rationale = sector_config.get("regime_performance", {}).get(regime, {}).get("rationale", "")
            if not primary_rationale:
                primary_rationale = "Macro conditions supportive"
        elif signal == "Underweight":
            primary_rationale = f"Challenged in {regime} environment"
        else:
            primary_rationale = "Mixed signals"

        # Confidence based on component coverage
        non_zero_components = sum(1 for v in components.values() if abs(v) > 0.01)
        confidence = min(0.9, 0.5 + non_zero_components * 0.1)

        return SectorScore(
            sector=sector_name,
            total_score=round(total_score, 2),
            signal=signal,
            components={k: round(v, 2) for k, v in components.items()},
            rationale=primary_rationale,
            confidence=round(confidence, 2),
        )

    def score_all_sectors(
        self,
        regime: str,
        growth_score: float,
        liquidity_score: float,
        credit_stress_score: float,
        financial_conditions: str = "neutral",
        recession_prob: float = 0.0,
    ) -> pd.DataFrame:
        """Score all configured sectors."""
        results = []

        for sector_key in self.sectors.keys():
            score = self.score_sector(
                sector=sector_key,
                regime=regime,
                growth_score=growth_score,
                liquidity_score=liquidity_score,
                credit_stress_score=credit_stress_score,
                financial_conditions=financial_conditions,
                recession_prob=recession_prob,
            )

            results.append({
                "Sector": score.sector,
                "Signal": score.signal,
                "Score": score.total_score,
                "Confidence": score.confidence,
                "Rationale": score.rationale,
            })

        return pd.DataFrame(results)


def get_sector_allocation_table(
    regime: str,
    growth_score: float,
    liquidity_score: float,
    credit_stress_score: float = 0.0,
    financial_conditions: str = "neutral",
    recession_prob: float = 0.0,
) -> pd.DataFrame:
    """
    Convenience function to get sector allocation table.
    """
    model = ConfigDrivenSectorModel()
    return model.score_all_sectors(
        regime=regime,
        growth_score=growth_score,
        liquidity_score=liquidity_score,
        credit_stress_score=credit_stress_score,
        financial_conditions=financial_conditions,
        recession_prob=recession_prob,
    )
