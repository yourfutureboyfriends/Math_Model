"""
Sensitivity Analysis Module

Tests how model outputs change with different parameter assumptions.

Tests:
- Z-score lookback windows
- Momentum windows
- Sector scoring weights
- Recession risk thresholds
- Inflation thresholds

Output: Which assumptions change the model conclusion?
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SensitivityResult:
    """Result of sensitivity test."""
    parameter: str
    tested_values: List[Any]
    outputs: List[Any]
    conclusion_changes: int
    is_sensitive: bool
    recommendation: str


class SensitivityAnalyzer:
    """
    Sensitivity Analyzer

    Tests model robustness to parameter changes.
    """

    def __init__(self, stability_threshold: float = 0.1):
        """
        Args:
            stability_threshold: Max change before considered sensitive
        """
        self.stability_threshold = stability_threshold

    def test_zscore_window(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        windows: List[int] = [36, 48, 60, 72],
    ) -> SensitivityResult:
        """
        Test sensitivity to z-score lookback window.

        Different windows can significantly change z-scores,
        especially around turning points.
        """
        outputs = []

        for window in windows:
            try:
                result = model_func(df, zscore_window=window)
                outputs.append(result)
            except Exception as e:
                logger.warning(f"Model failed with window {window}: {e}")
                outputs.append(None)

        # Check for conclusion changes
        changes = self._count_conclusion_changes(outputs)
        is_sensitive = changes > 0

        return SensitivityResult(
            parameter="zscore_window",
            tested_values=windows,
            outputs=outputs,
            conclusion_changes=changes,
            is_sensitive=is_sensitive,
            recommendation="Use longer window (60 months) for stability" if is_sensitive else "Robust to window choice",
        )

    def test_momentum_window(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        windows: List[int] = [1, 3, 6, 12],
    ) -> SensitivityResult:
        """Test sensitivity to momentum calculation window."""
        outputs = []

        for window in windows:
            try:
                result = model_func(df, momentum_window=window)
                outputs.append(result)
            except Exception as e:
                logger.warning(f"Model failed with momentum {window}: {e}")
                outputs.append(None)

        changes = self._count_conclusion_changes(outputs)
        is_sensitive = changes > 0

        return SensitivityResult(
            parameter="momentum_window",
            tested_values=windows,
            outputs=outputs,
            conclusion_changes=changes,
            is_sensitive=is_sensitive,
            recommendation="3-month momentum is standard" if not is_sensitive else "Momentum window affects conclusions",
        )

    def test_sector_weights(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        weight_variations: List[Dict] = None,
    ) -> SensitivityResult:
        """
        Test sensitivity to sector scoring weights.

        Tests if changing relative weights changes sector signals.
        """
        if weight_variations is None:
            # Default variations
            weight_variations = [
                {"regime": 0.4, "fc": 0.2, "earnings": 0.15, "rate": 0.10, "credit": 0.10, "momentum": 0.05},
                {"regime": 0.3, "fc": 0.3, "earnings": 0.15, "rate": 0.10, "credit": 0.10, "momentum": 0.05},
                {"regime": 0.3, "fc": 0.2, "earnings": 0.20, "rate": 0.15, "credit": 0.10, "momentum": 0.05},
            ]

        outputs = []

        for weights in weight_variations:
            try:
                result = model_func(df, sector_weights=weights)
                outputs.append(result)
            except Exception as e:
                logger.warning(f"Model failed with weights {weights}: {e}")
                outputs.append(None)

        changes = self._count_conclusion_changes(outputs)
        is_sensitive = changes > len(outputs) * 0.2  # >20% changes

        return SensitivityResult(
            parameter="sector_weights",
            tested_values=[str(w) for w in weight_variations],
            outputs=outputs,
            conclusion_changes=changes,
            is_sensitive=is_sensitive,
            recommendation="Sector signals moderately sensitive to weights" if is_sensitive else "Sector signals robust to weight changes",
        )

    def test_recession_threshold(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        thresholds: List[float] = [0.2, 0.3, 0.4, 0.5],
    ) -> SensitivityResult:
        """Test sensitivity to recession probability threshold."""
        outputs = []

        for threshold in thresholds:
            try:
                result = model_func(df, recession_threshold=threshold)
                outputs.append(result)
            except Exception as e:
                logger.warning(f"Model failed with threshold {threshold}: {e}")
                outputs.append(None)

        changes = self._count_conclusion_changes(outputs)
        is_sensitive = changes > 0

        return SensitivityResult(
            parameter="recession_threshold",
            tested_values=thresholds,
            outputs=outputs,
            conclusion_changes=changes,
            is_sensitive=is_sensitive,
            recommendation="Recession warning sensitive to threshold choice" if is_sensitive else "Recession signal robust to threshold",
        )

    def test_inflation_threshold(
        self,
        df: pd.DataFrame,
        model_func: Callable,
        thresholds: List[float] = [2.0, 2.5, 3.0, 3.5],
    ) -> SensitivityResult:
        """Test sensitivity to inflation threshold."""
        outputs = []

        for threshold in thresholds:
            try:
                result = model_func(df, inflation_threshold=threshold)
                outputs.append(result)
            except Exception as e:
                logger.warning(f"Model failed with threshold {threshold}: {e}")
                outputs.append(None)

        changes = self._count_conclusion_changes(outputs)
        is_sensitive = changes > 0

        return SensitivityResult(
            parameter="inflation_threshold",
            tested_values=thresholds,
            outputs=outputs,
            conclusion_changes=changes,
            is_sensitive=is_sensitive,
            recommendation="Inflation regime sensitive to target choice" if is_sensitive else "Inflation regime robust to target",
        )

    def _count_conclusion_changes(self, outputs: List[Any]) -> int:
        """Count how many times conclusion changes between runs."""
        if len(outputs) < 2:
            return 0

        changes = 0
        base = outputs[0]

        for output in outputs[1:]:
            if self._conclusion_differs(base, output):
                changes += 1

        return changes

    def _conclusion_differs(self, a: Any, b: Any) -> bool:
        """Check if two outputs have different conclusions."""
        if a is None or b is None:
            return a != b

        # Handle different types
        if isinstance(a, dict) and isinstance(b, dict):
            # Compare key metrics
            for key in ["regime", "signal", "recommendation"]:
                if key in a and key in b:
                    if a[key] != b[key]:
                        return True
            return False

        elif isinstance(a, str) and isinstance(b, str):
            return a != b

        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(a - b) > self.stability_threshold

        return False

    def run_full_sensitivity_suite(
        self,
        df: pd.DataFrame,
        model_func: Callable,
    ) -> Dict[str, SensitivityResult]:
        """
        Run full sensitivity test suite.

        Returns:
            Dict of parameter name -> SensitivityResult
        """
        results = {}

        logger.info("Running sensitivity analysis...")

        results["zscore_window"] = self.test_zscore_window(df, model_func)
        results["momentum_window"] = self.test_momentum_window(df, model_func)
        results["recession_threshold"] = self.test_recession_threshold(df, model_func)
        results["inflation_threshold"] = self.test_inflation_threshold(df, model_func)

        # Summary
        sensitive_params = [k for k, v in results.items() if v.is_sensitive]

        logger.info(f"Sensitivity analysis complete. Sensitive parameters: {sensitive_params}")

        return results

    def generate_sensitivity_report(
        self,
        results: Dict[str, SensitivityResult],
    ) -> str:
        """Generate markdown report of sensitivity analysis."""
        lines = [
            "# Sensitivity Analysis Report",
            "",
            "## Summary",
            "",
        ]

        sensitive = [k for k, v in results.items() if v.is_sensitive]
        robust = [k for k, v in results.items() if not v.is_sensitive]

        lines.append(f"**Sensitive Parameters:** {', '.join(sensitive) if sensitive else 'None'}")
        lines.append(f"**Robust Parameters:** {', '.join(robust) if robust else 'None'}")
        lines.append("")

        lines.append("## Detailed Results")
        lines.append("")

        for param, result in results.items():
            lines.append(f"### {param}")
            lines.append(f"- Tested values: {result.tested_values}")
            lines.append(f"- Conclusion changes: {result.conclusion_changes}")
            lines.append(f"- Is sensitive: {'Yes' if result.is_sensitive else 'No'}")
            lines.append(f"- Recommendation: {result.recommendation}")
            lines.append("")

        return "\n".join(lines)


# Type hint for Callable
from typing import Callable


def test_model_robustness(
    df: pd.DataFrame,
    model_func: Callable,
) -> Dict[str, SensitivityResult]:
    """
    Convenience function to test model robustness.
    """
    analyzer = SensitivityAnalyzer()
    return analyzer.run_full_sensitivity_suite(df, model_func)
