"""
Research Module

Research hypothesis tracking, validation, and postmortem analysis.
"""

from .hypothesis_registry import (
    HypothesisRegistry,
    Hypothesis,
    HypothesisStatus,
    HypothesisType,
    create_macro_hypothesis,
    create_signal_hypothesis,
)
from .signal_validation import (
    SignalValidator,
    ValidationResult,
)
from .postmortem_engine import (
    PostmortemEngine,
    PostmortemAnalysis,
    calculate_alpha_decay,
    detect_regime_change,
)

__all__ = [
    "HypothesisRegistry",
    "Hypothesis",
    "HypothesisStatus",
    "HypothesisType",
    "create_macro_hypothesis",
    "create_signal_hypothesis",
    "SignalValidator",
    "ValidationResult",
    "PostmortemEngine",
    "PostmortemAnalysis",
    "calculate_alpha_decay",
    "detect_regime_change",
]
