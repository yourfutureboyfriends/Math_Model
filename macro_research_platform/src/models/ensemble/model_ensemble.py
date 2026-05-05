"""
Model Ensemble and Signal Confidence

Combines outputs from multiple models into a unified macro view
with confidence scoring and disagreement tracking.

Research inspiration:
- Model averaging and Bayesian model combination
- Tetlock - Expert Political Judgment (fox vs hedgehog)
- Kahneman and Tversky - confidence calibration
- Forecast aggregation literature

Key principle: When models disagree, show it clearly.
Don't force a fake clean conclusion.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelOutput:
    """Output from a single model."""
    model_name: str
    signal: str  # bullish/neutral/bearish or specific regime
    strength: float  # 0 to 1
    confidence: str  # high/moderate/low
    drivers: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)


@dataclass
class EnsembleResult:
    """Combined ensemble output."""
    # Overall view
    macro_regime: str
    business_conditions: str
    recession_risk: str
    financial_conditions: str
    inflation_pressure: str
    market_confirmation: str

    # Aggregation
    final_view: str
    confidence_level: str  # high/moderate/low/very_low
    disagreement_score: float  # 0 = full agreement, 1 = max disagreement

    # Components
    model_outputs: Dict[str, ModelOutput]
    agreeing_models: List[str]
    disagreeing_models: List[str]

    # Risk factors
    key_risks: List[str]
    positive_factors: List[str]

    # Meta
    data_freshness: str
    data_coverage: float
    ensemble_timestamp: datetime = field(default_factory=datetime.now)


class ModelEnsemble:
    """
    Combines multiple macro models into unified view.

    Financial logic:
      No single model captures the full macro picture. A regime
      model may point to slowdown while credit stress is contained
      and equity momentum remains positive. The ensemble weights
      these signals and flags when models disagree.
    """

    # Model weights (can be adjusted based on backtest performance)
    DEFAULT_WEIGHTS = {
        "macro_regime": 0.25,
        "business_conditions": 0.20,
        "recession_risk": 0.15,
        "financial_conditions": 0.15,
        "credit_stress": 0.10,
        "market_confirmation": 0.15,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def combine(
        self,
        outputs: Dict[str, ModelOutput],
        data_freshness: str = "unknown",
        data_coverage: float = 0.0,
    ) -> EnsembleResult:
        """
        Combine model outputs into ensemble view.

        Args:
            outputs: Dict of model_name -> ModelOutput
            data_freshness: Overall data freshness status
            data_coverage: Percentage of required data available

        Returns:
            EnsembleResult with combined view
        """
        # Extract individual signals
        regime = outputs.get("macro_regime", ModelOutput("macro_regime", "neutral", 0.5, "low"))
        business = outputs.get("business_conditions", ModelOutput("business_conditions", "stable", 0.5, "low"))
        recession = outputs.get("recession_risk", ModelOutput("recession_risk", "low", 0.5, "low"))
        financial = outputs.get("financial_conditions", ModelOutput("financial_conditions", "neutral", 0.5, "low"))
        inflation = outputs.get("inflation_shock", ModelOutput("inflation_shock", "neutral", 0.5, "low"))
        market = outputs.get("market_confirmation", ModelOutput("market_confirmation", "neutral", 0.5, "low"))

        # Calculate disagreement
        disagreement = self._calc_disagreement(outputs)
        agreeing, disagreeing = self._identify_agreement(outputs)

        # Determine final view
        final_view = self._synthesize_view(outputs, disagreement)

        # Calculate confidence
        confidence = self._calc_ensemble_confidence(outputs, data_freshness, data_coverage)

        # Identify key factors
        positive, risks = self._identify_factors(outputs)

        return EnsembleResult(
            macro_regime=regime.signal,
            business_conditions=business.signal,
            recession_risk=recession.signal,
            financial_conditions=financial.signal,
            inflation_pressure=inflation.signal,
            market_confirmation=market.signal,
            final_view=final_view,
            confidence_level=confidence,
            disagreement_score=disagreement,
            model_outputs=outputs,
            agreeing_models=agreeing,
            disagreeing_models=disagreeing,
            key_risks=risks,
            positive_factors=positive,
            data_freshness=data_freshness,
            data_coverage=data_coverage,
        )

    def _calc_disagreement(self, outputs: Dict[str, ModelOutput]) -> float:
        """
        Calculate disagreement score between models.

        Returns 0 for full agreement, 1 for maximum disagreement.
        """
        if len(outputs) < 2:
            return 0.0

        # Map signals to numeric scores
        signal_map = {
            # Growth direction
            "improving": 1.0,
            "stable": 0.0,
            "deteriorating": -1.0,
            # Regime
            "Goldilocks": 1.0,
            "Reflation": 0.5,
            "Slowdown": -0.5,
            "Stagflation": -1.0,
            # Risk
            "low": 0.0,
            "moderate": 0.5,
            "high": 1.0,
            # General
            "bullish": 1.0,
            "neutral": 0.0,
            "bearish": -1.0,
        }

        scores = []
        for model, output in outputs.items():
            score = signal_map.get(output.signal, 0.0)
            # Weight by model confidence
            conf_weight = {"high": 1.0, "moderate": 0.7, "low": 0.4}.get(output.confidence, 0.5)
            scores.append(score * conf_weight)

        if not scores:
            return 0.0

        # Disagreement = standard deviation of scores
        disagreement = np.std(scores)
        return min(disagreement, 1.0)  # Cap at 1.0

    def _identify_agreement(self, outputs: Dict[str, ModelOutput]) -> Tuple[List[str], List[str]]:
        """Identify which models agree and disagree with consensus."""
        if len(outputs) < 2:
            return list(outputs.keys()), []

        # Simple agreement check - group by signal direction
        bullish = [name for name, out in outputs.items()
                   if out.signal in ["improving", "Goldilocks", "Reflation", "bullish", "low"]]
        bearish = [name for name, out in outputs.items()
                   if out.signal in ["deteriorating", "Slowdown", "Stagflation", "bearish", "high"]]
        neutral = [name for name, out in outputs.items()
                   if out.signal in ["stable", "neutral", "moderate"]]

        # Find majority
        groups = [g for g in [bullish, bearish, neutral] if len(g) > 0]
        if not groups:
            return [], list(outputs.keys())

        majority = max(groups, key=len)
        minority = [name for name in outputs.keys() if name not in majority]

        return majority, minority

    def _synthesize_view(self, outputs: Dict[str, ModelOutput], disagreement: float) -> str:
        """Synthesize final view from model outputs."""
        # Get key signals
        regime = outputs.get("macro_regime", ModelOutput("macro_regime", "neutral", 0.0, "low"))
        recession = outputs.get("recession_risk", ModelOutput("recession_risk", "low", 0.0, "low"))
        business = outputs.get("business_conditions", ModelOutput("business_conditions", "stable", 0.0, "low"))

        # High disagreement = cautious view
        if disagreement > 0.5:
            return "mixed_signals_caution"

        # Synthesize based on main drivers
        if regime.signal == "Slowdown" and recession.signal in ["moderate", "high"]:
            return "late_cycle_defensive"

        if regime.signal == "Slowdown" and recession.signal == "low":
            return "slowdown_selective"

        if regime.signal == "Goldilocks":
            return "expansion_risk_on"

        if regime.signal == "Reflation":
            return "reflation_cyclical"

        if regime.signal == "Stagflation":
            return "stagflation_protection"

        if business.signal == "deteriorating":
            return "weakening_cautious"

        return "neutral_balanced"

    def _calc_ensemble_confidence(
        self,
        outputs: Dict[str, ModelOutput],
        data_freshness: str,
        data_coverage: float,
    ) -> str:
        """Calculate overall confidence level."""
        # Check model confidence
        high_conf = sum(1 for o in outputs.values() if o.confidence == "high")
        total = len(outputs)

        if total == 0:
            return "very_low"

        model_conf_ratio = high_conf / total

        # Data quality check
        data_penalty = 0.0
        if data_freshness == "stale":
            data_penalty = 0.3
        elif data_freshness == "very_stale":
            data_penalty = 0.5

        if data_coverage < 0.5:
            data_penalty += 0.3

        # Final score
        score = model_conf_ratio - data_penalty

        if score > 0.7:
            return "high"
        elif score > 0.4:
            return "moderate"
        elif score > 0.2:
            return "low"
        else:
            return "very_low"

    def _identify_factors(self, outputs: Dict[str, ModelOutput]) -> Tuple[List[str], List[str]]:
        """Identify positive and risk factors across all models."""
        positive = []
        risks = []

        for name, output in outputs.items():
            positive.extend([f"{name}: {d}" for d in output.drivers])
            risks.extend([f"{name}: {c}" for c in output.concerns])

        return positive[:5], risks[:5]


def format_ensemble_summary(result: EnsembleResult) -> str:
    """Format ensemble result as hedge fund style summary."""
    lines = []

    lines.append(f"Macro Regime: {result.macro_regime}")
    lines.append(f"Business Conditions: {result.business_conditions}")
    lines.append(f"Recession Risk: {result.recession_risk}")
    lines.append(f"Financial Conditions: {result.financial_conditions}")
    lines.append(f"Inflation Pressure: {result.inflation_pressure}")
    lines.append(f"Market Confirmation: {result.market_confirmation}")
    lines.append("")
    lines.append(f"Ensemble View: {result.final_view}")
    lines.append(f"Confidence: {result.confidence_level}")
    lines.append(f"Disagreement Score: {result.disagreement_score:.2f}")

    if result.disagreeing_models:
        lines.append(f"Model Disagreement: {', '.join(result.disagreeing_models)} differ from consensus")

    if result.positive_factors:
        lines.append(f"Positive Factors: {', '.join(result.positive_factors[:3])}")

    if result.key_risks:
        lines.append(f"Key Risks: {', '.join(result.key_risks[:3])}")

    return "\n".join(lines)
