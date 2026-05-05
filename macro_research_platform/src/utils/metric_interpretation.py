"""
Shared Metric Interpretation Module

Centralizes all metric label logic to ensure consistency across dashboard,
memo generator, model agreement, and business outputs.

Usage:
    from src.utils.metric_interpretation import interpret_inflation, interpret_growth

    inflation = interpret_inflation(score=1.07, change=1.75)
    print(inflation.level)      # "Elevated"
    print(inflation.direction)  # "Rising"
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class MetricInterpretation:
    """Standardized interpretation result for any metric."""
    level: str          # Current level/category (e.g., "Elevated", "Easy")
    direction: str      # Direction of change (e.g., "Rising", "Tightening")
    combined: str       # Combined description (e.g., "Elevated + Rising")
    interpretation: str # Human-readable interpretation
    confidence: str   # "high", "medium", "low"


# Standard thresholds - used consistently across the platform
THRESHOLDS = {
    "level": {
        "strong": 0.5,
        "weak": -0.5,
        "elevated": 0.5,
        "low": -0.5,
        "easy": 0.5,
        "tight": -0.5,
        "risk_on": 0.5,
        "risk_off": -0.5,
    },
    "direction": {
        "significant": 0.25,
        "moderate": 0.10,
    }
}


def interpret_inflation(score: float, change: Optional[float] = None) -> MetricInterpretation:
    """
    Interpret inflation pressure score consistently.

    Convention:
    - Higher score = higher inflation pressure
    - Lower score = lower inflation pressure

    Level:
    - score >= 0.5 = Elevated
    - -0.5 < score < 0.5 = Normal
    - score <= -0.5 = Low

    Direction (3M change):
    - change >= 0.25 = Rising
    - -0.25 < change < 0.25 = Stable
    - change <= -0.25 = Falling

    Args:
        score: Current inflation pressure score (z-score)
        change: 3-month change in score (optional)

    Returns:
        MetricInterpretation with level, direction, combined, and interpretation
    """
    # Determine level
    if score >= THRESHOLDS["level"]["elevated"]:
        level = "Elevated"
    elif score <= THRESHOLDS["level"]["low"]:
        level = "Low"
    else:
        level = "Normal"

    # Determine direction
    if change is not None:
        if change >= THRESHOLDS["direction"]["significant"]:
            direction = "Rising"
        elif change <= -THRESHOLDS["direction"]["significant"]:
            direction = "Falling"
        else:
            direction = "Stable"

        combined = f"{level} + {direction}"

        # Build interpretation
        if level == "Elevated" and direction == "Rising":
            interpretation = "Inflation pressure is elevated and rising"
        elif level == "Elevated" and direction == "Falling":
            interpretation = "Inflation pressure is elevated but easing from high levels"
        elif level == "Low" and direction == "Rising":
            interpretation = "Inflation pressure is rising from a low base"
        elif level == "Low" and direction == "Falling":
            interpretation = "Inflation pressure is low and falling (disinflationary)"
        elif level == "Normal" and direction == "Rising":
            interpretation = "Inflation pressure is rising toward elevated levels"
        elif level == "Normal" and direction == "Falling":
            interpretation = "Inflation pressure is falling toward low levels"
        else:
            interpretation = f"Inflation pressure is {level.lower()} and {direction.lower()}"
    else:
        direction = "Unknown"
        combined = level
        interpretation = f"Inflation pressure is {level.lower()}"

    return MetricInterpretation(
        level=level,
        direction=direction,
        combined=combined,
        interpretation=interpretation,
        confidence="high" if abs(score) > 1.0 else "medium"
    )


def interpret_growth(score: float, change: Optional[float] = None) -> MetricInterpretation:
    """
    Interpret growth momentum score consistently.

    Convention:
    - Higher score = stronger growth
    - Lower score = weaker growth

    Level:
    - score >= 0.5 = Strong
    - -0.5 < score < 0.5 = Neutral
    - score <= -0.5 = Weak

    Direction:
    - change >= 0.25 = Improving
    - -0.25 < change < 0.25 = Stable
    - change <= -0.25 = Deteriorating
    """
    # Determine level
    if score >= THRESHOLDS["level"]["strong"]:
        level = "Strong"
    elif score <= THRESHOLDS["level"]["weak"]:
        level = "Weak"
    else:
        level = "Neutral"

    # Determine direction
    if change is not None:
        if change >= THRESHOLDS["direction"]["significant"]:
            direction = "Improving"
        elif change <= -THRESHOLDS["direction"]["significant"]:
            direction = "Deteriorating"
        else:
            direction = "Stable"

        combined = f"{level} + {direction}"

        # Build interpretation
        if level == "Strong" and direction == "Improving":
            interpretation = "Growth is strong and accelerating"
        elif level == "Weak" and direction == "Deteriorating":
            interpretation = "Growth is weak and decelerating"
        elif level == "Neutral" and direction == "Improving":
            interpretation = "Growth is improving from neutral levels"
        elif level == "Neutral" and direction == "Deteriorating":
            interpretation = "Growth is slowing from neutral levels"
        else:
            interpretation = f"Growth is {level.lower()} and {direction.lower()}"
    else:
        direction = "Unknown"
        combined = level
        interpretation = f"Growth is {level.lower()}"

    return MetricInterpretation(
        level=level,
        direction=direction,
        combined=combined,
        interpretation=interpretation,
        confidence="high" if abs(score) > 1.0 else "medium"
    )


def interpret_financial_conditions_ease(score: float, change: Optional[float] = None) -> MetricInterpretation:
    """
    Interpret financial conditions ease score consistently.

    Convention:
    - Higher score = easier conditions
    - Lower score = tighter conditions

    Level:
    - score >= 0.5 = Easy
    - -0.5 < score < 0.5 = Neutral
    - score <= -0.5 = Tight

    Direction:
    - change >= 0.25 = Easing
    - -0.25 < change < 0.25 = Stable
    - change <= -0.25 = Tightening
    """
    # Determine level
    if score >= THRESHOLDS["level"]["easy"]:
        level = "Easy"
    elif score <= THRESHOLDS["level"]["tight"]:
        level = "Tight"
    else:
        level = "Neutral"

    # Determine direction
    if change is not None:
        if change >= THRESHOLDS["direction"]["significant"]:
            direction = "Easing"
        elif change <= -THRESHOLDS["direction"]["significant"]:
            direction = "Tightening"
        else:
            direction = "Stable"

        combined = f"{level} + {direction}"

        # Build interpretation
        if level == "Easy" and direction == "Tightening":
            interpretation = "Conditions remain easy but the impulse is tightening"
        elif level == "Tight" and direction == "Easing":
            interpretation = "Conditions remain tight but the impulse is easing"
        elif level == "Easy" and direction == "Easing":
            interpretation = "Conditions are easy and easing further"
        elif level == "Tight" and direction == "Tightening":
            interpretation = "Conditions are tight and tightening further"
        else:
            interpretation = f"Conditions are {level.lower()} and {direction.lower()}"
    else:
        direction = "Unknown"
        combined = level
        interpretation = f"Conditions are {level.lower()}"

    return MetricInterpretation(
        level=level,
        direction=direction,
        combined=combined,
        interpretation=interpretation,
        confidence="high" if abs(score) > 1.0 else "medium"
    )


def interpret_risk_appetite(score: float, change: Optional[float] = None) -> MetricInterpretation:
    """
    Interpret risk appetite score consistently.

    Convention:
    - Higher score = more risk-on
    - Lower score = more risk-off

    Level:
    - score >= 0.5 = Risk-On
    - -0.5 < score < 0.5 = Neutral
    - score <= -0.5 = Risk-Off

    Direction:
    - change >= 0.25 = Improving
    - -0.25 < change < 0.25 = Stable
    - change <= -0.25 = Deteriorating
    """
    # Determine level
    if score >= THRESHOLDS["level"]["risk_on"]:
        level = "Risk-On"
    elif score <= THRESHOLDS["level"]["risk_off"]:
        level = "Risk-Off"
    else:
        level = "Neutral"

    # Determine direction
    if change is not None:
        if change >= THRESHOLDS["direction"]["significant"]:
            direction = "Improving"
        elif change <= -THRESHOLDS["direction"]["significant"]:
            direction = "Deteriorating"
        else:
            direction = "Stable"

        combined = f"{level} + {direction}"

        # Build interpretation
        if level == "Risk-On" and direction == "Deteriorating":
            interpretation = "Risk appetite is positive but softening"
        elif level == "Risk-Off" and direction == "Improving":
            interpretation = "Risk appetite is recovering from risk-off levels"
        elif level == "Risk-On" and direction == "Improving":
            interpretation = "Risk appetite is strong and improving"
        elif level == "Risk-Off" and direction == "Deteriorating":
            interpretation = "Risk appetite is weak and deteriorating"
        else:
            interpretation = f"Risk appetite is {level.lower().replace('_', '-')} and {direction.lower()}"
    else:
        direction = "Unknown"
        combined = level
        interpretation = f"Risk appetite is {level.lower().replace('_', '-')}"

    return MetricInterpretation(
        level=level,
        direction=direction,
        combined=combined,
        interpretation=interpretation,
        confidence="high" if abs(score) > 1.0 else "medium"
    )


def interpret_recession_risk(probability: float) -> MetricInterpretation:
    """
    Interpret recession risk probability consistently.

    Level:
    - probability < 15% = Low
    - 15% <= probability < 30% = Moderate
    - probability >= 30% = Elevated
    """
    if probability < 15:
        level = "Low"
        interpretation = f"Recession risk is low ({probability:.0f}%)"
    elif probability < 30:
        level = "Moderate"
        interpretation = f"Recession risk is moderate ({probability:.0f}%)"
    else:
        level = "Elevated"
        interpretation = f"Recession risk is elevated ({probability:.0f}%)"

    return MetricInterpretation(
        level=level,
        direction="N/A",
        combined=level,
        interpretation=interpretation,
        confidence="medium"
    )


def interpret_credit_stress(score: float) -> MetricInterpretation:
    """
    Interpret credit stress score consistently.

    Level:
    - score < -0.5 = Elevated
    - -0.5 <= score <= 0.5 = Normal
    - score > 0.5 = Compressed (favorable)
    """
    if score < -0.5:
        level = "Elevated"
        interpretation = "Credit stress is elevated - caution warranted"
    elif score > 0.5:
        level = "Compressed"
        interpretation = "Credit stress is compressed (favorable conditions)"
    else:
        level = "Normal"
        interpretation = "Credit stress is normal"

    return MetricInterpretation(
        level=level,
        direction="N/A",
        combined=level,
        interpretation=interpretation,
        confidence="medium"
    )


# Convenience function to interpret all metrics at once
def interpret_all_metrics(
    inflation_score: float,
    inflation_change: Optional[float] = None,
    growth_score: float = 0,
    growth_change: Optional[float] = None,
    fc_score: float = 0,
    fc_change: Optional[float] = None,
    risk_score: float = 0,
    risk_change: Optional[float] = None,
    recession_prob: float = 0,
    credit_stress: float = 0,
) -> dict:
    """
    Interpret all metrics at once and return a dictionary.

    Returns:
        Dictionary with all interpretations
    """
    return {
        "inflation": interpret_inflation(inflation_score, inflation_change),
        "growth": interpret_growth(growth_score, growth_change),
        "financial_conditions": interpret_financial_conditions_ease(fc_score, fc_change),
        "risk_appetite": interpret_risk_appetite(risk_score, risk_change),
        "recession_risk": interpret_recession_risk(recession_prob),
        "credit_stress": interpret_credit_stress(credit_stress),
    }


# Backwards compatibility aliases - deprecated, use full names
def get_inflation_level(score: float) -> str:
    """DEPRECATED: Use interpret_inflation().level instead."""
    return interpret_inflation(score).level


def get_inflation_direction(change: float) -> str:
    """DEPRECATED: Use interpret_inflation(score=0, change=change).direction instead."""
    return interpret_inflation(score=0, change=change).direction